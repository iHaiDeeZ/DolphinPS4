#!/usr/bin/env python3
"""What a second-stage JIT could remove, from a lab profile (samples.log, perf-*.map, jitcode.bin).

tier2scan.py <dir> [t0 t1]
Weights every hot x86 instruction of the CPU thread's JIT code by its 16-byte bucket's samples
(spread evenly over the bucket's instructions) and sorts it into: guest register traffic (memory
operands on %rbp = ppcState, which isn't game memory), guest memory (%rbx = fastmem base, or
movbe), downcount/exception bookkeeping, control flow, the rest. Then: the share of JIT time in
blocks that jump back to their own start (loops a second stage could keep in registers), and the
share in blocks whose exits link to a block that links straight back (two-block loops).
"""
import bisect, collections, glob, os, re, struct, subprocess, sys, tempfile

d = sys.argv[1]
t0, t1 = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) >= 4 else (30, 1e9)

entries = {}
for path in glob.glob(os.path.join(d, "perf-*.map")):
    for line in open(path, errors="replace"):
        m = re.match(r"(0x[0-9a-f]+) ([0-9a-f]+) (\S+)", line)
        if m and m.group(3).startswith("JIT_PPC_"):
            entries[int(m.group(1), 16)] = (int(m.group(2), 16), m.group(3))
starts = sorted(entries)


def block_of(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and a < starts[i] + max(entries[starts[i]][0], 1):
        return starts[i]
    return None


buckets = collections.Counter()
n = 0
on = False
for line in open(os.path.join(d, "samples.log"), errors="replace"):
    m = re.match(r"== ([\d.]+) s, (.*?): ", line)
    if m:
        on = m.group(2) == "CPU thread" and t0 <= float(m.group(1)) <= t1
        n += on
        continue
    if on:
        m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
        if m:
            buckets[int(m.group(2), 16)] += float(m.group(1))

data = open(os.path.join(d, "jitcode.bin"), "rb").read()
chunks = {}
o = 0
while o + 16 <= len(data):
    a, s = struct.unpack_from("<QQ", data, o)
    chunks[a] = data[o + 16:o + 16 + s]
    o += 16 + s

cats = collections.Counter()
fields = collections.Counter()
block_weight = collections.Counter()
block_targets = collections.defaultdict(set)  # block -> blocks its jmps go to
total = 0.0
for chunk, b in chunks.items():
    with tempfile.TemporaryDirectory() as t:
        raw = os.path.join(t, "c.bin")
        elf = os.path.join(t, "c.o")
        open(raw, "wb").write(b)
        subprocess.run(["llvm-objcopy-21", "-I", "binary", "-O", "elf64-x86-64", "--rename-section",
                        ".data=.text,code", raw, elf], check=True)
        out = subprocess.run(["llvm-objdump-21", "-d", "--no-show-raw-insn", elf],
                             capture_output=True, text=True).stdout
    per = collections.defaultdict(list)
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if not m:
            continue
        addr = chunk + int(m.group(1), 16)
        op, args = m.group(2), m.group(3)
        per[addr & ~0xF].append((addr, op, args))
        # Branch targets (objdump prints them relative to the raw chunk: add the base).
        if op.startswith("j"):
            tm = re.match(r"(0x[0-9a-f]+)", args)
            if tm:
                src = block_of(addr)
                target = chunk + int(tm.group(1), 16)
                dst = block_of(target)
                # A link to a block's entry (its first bytes: checked/normal entry), not a jump
                # inside a block.
                if src is not None and dst is not None and target - dst < 0x20 and addr - src >= 0x20:
                    block_targets[src].add(dst)
    for bk, ins in per.items():
        w = buckets.get(bk, 0) / max(n, 1)
        if not w:
            continue
        total += w
        blk = block_of(bk)
        if blk is not None:
            block_weight[blk] += w
        share = w / len(ins)
        for _, op, args in ins:
            if "(%rbp)" in args or "(%rbp," in args:
                dm = re.search(r"(-?0x[0-9a-f]+)?\(%rbp", args)
                disp = int(dm.group(1), 16) if dm and dm.group(1) else 0
                field = ("pc" if disp in (-0x80, -0x7c) else "gather pipe ptr" if -0x78 <= disp < -0x60
                         else "GPR" if -0x60 <= disp < 0x20 else "CR" if 0x20 <= disp < 0x60
                         else "msr/fpscr/flags" if 0x60 <= disp < 0x70 else "downcount" if disp == 0x70
                         else "xer" if 0x74 <= disp < 0x78 else "FPR" if 0x80 <= disp < 0x300
                         else "sr/spr" if disp >= 0x300 else "other")
                first = args.split(",")[0]
                direction = "load" if "(%rbp" in first else "store"
                fields[field + " " + direction] += share
                if re.search(r"\b(sub|add)l?\s.*0x[0-9a-f]+\(%rbp\)", op + " " + args) and op.startswith("sub"):
                    cats["downcount/bookkeeping (ppcState)"] += share
                else:
                    cats["guest register traffic (ppcState)"] += share
            elif op.startswith("movbe") or "(%rbx," in args or "(%rbx)" in args:
                cats["guest memory (fastmem)"] += share
            elif op.startswith("j") or op.startswith("call") or op.startswith("ret"):
                cats["control flow"] += share
            elif op.startswith(("cvt", "mulss", "mulsd", "addss", "addsd", "subss", "subsd", "divs",
                                "fmadd", "mulp", "addp", "subp", "movap", "movsd", "movss", "shufp",
                                "unpck", "movddup", "movhlps", "movlhps", "blend", "andp", "orp",
                                "xorp", "pand", "por", "pxor", "sqrt", "rsqrt", "rcp", "min", "max",
                                "ucomis", "comis", "round")):
                cats["floating point / SIMD"] += share
            else:
                cats["integer / other"] += share

print("== %s: JIT %.1f%% of CPU-thread samples analysed (%d windows)" % (d, total, n))
for k, v in cats.most_common():
    print("  %5.1f%%  %s" % (100 * v / max(total, 1e-9), k))
print("  ppcState traffic by field (share of all JIT instructions):")
for k, v in fields.most_common(14):
    print("    %5.1f%%  %s" % (100 * v / max(total, 1e-9), k))
in_blocks = sum(block_weight.values())
self_loops = sum(w for b, w in block_weight.items() if b in block_targets[b])
two_loops = sum(w for b, w in block_weight.items()
                if b not in block_targets[b] and any(b in block_targets[t] for t in block_targets[b]))
print("  self-looping blocks: %.1f%% of block time; two-block loops: %.1f%%"
      % (100 * self_loops / max(in_blocks, 1e-9), 100 * two_loops / max(in_blocks, 1e-9)))
top = block_weight.most_common(12)
print("  hottest blocks (share of block time, self-loop, size):")
for b, w in top:
    print("    %5.1f%%  %s  %s  %d bytes" % (100 * w / in_blocks, entries[b][1],
                                         "loop" if b in block_targets[b] else "    ", entries[b][0]))
