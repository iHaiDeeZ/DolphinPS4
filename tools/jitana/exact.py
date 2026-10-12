#!/usr/bin/env python3
"""exact.py <dir> <id>: jitsamples-<id>.log (v50.52+) against jitcode.bin and perf-*.map. Uses the
windows between the last two "== dump" lines (their code is in jitcode.bin). Each sample is the
interrupted instruction; "prev" views charge the instruction before it (sampling skid: a slow
instruction is often seen as the one after it)."""
import bisect, collections, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapload import load_map

d, gid = sys.argv[1], sys.argv[2]
seg = int(sys.argv[3]) if len(sys.argv) > 3 else 1  # 1 = windows before the last dump

lines = open(os.path.join(d, "jitsamples-%s.log" % gid)).read().splitlines()
dumps = [i for i, l in enumerate(lines) if l == "== dump"]
lo = dumps[-1 - seg] if len(dumps) > seg else 0
hi = dumps[-seg] if dumps else len(lines)
samples = collections.Counter()
total_cpu = 0
nwin = 0
for l in lines[lo:hi]:
    if l.startswith("== ") and l != "== dump":
        total_cpu += int(l.split()[2])
        nwin += 1
    elif l and not l.startswith("=="):
        a, c = l.split()
        samples[int(a, 16)] += int(c)
jit_total = sum(samples.values())

entries = load_map(d)
starts = sorted(entries)
code = {}
data = open(os.path.join(d, "jitcode.bin"), "rb").read()
o = 0
while o + 16 <= len(data):
    a, n = struct.unpack_from("<QQ", data, o)
    code[a] = data[o + 16:o + 16 + n]
    o += 16 + n


def read_code(a, n):
    out = b""
    while n > 0:
        c = a & ~0xFFFF
        if c not in code:
            return None
        off = a - c
        t = min(n, 0x10000 - off)
        out += code[c][off:off + t]
        a += t
        n -= t
    return out


def disasm(a, n):
    b = read_code(a, n)
    if b is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        raw, elf = os.path.join(tmp, "c.bin"), os.path.join(tmp, "c.o")
        open(raw, "wb").write(b)
        subprocess.run(["llvm-objcopy-21", "-I", "binary", "-O", "elf64-x86-64",
                        "--rename-section", ".data=.text,code", raw, elf], check=True)
        out = subprocess.run(["llvm-objdump-21", "-d", "--no-show-raw-insn",
                              "--adjust-vma=%#x" % a, elf], capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if m:
            x = int(m.group(1), 16)
            res.append((x if x >= a else a + x, m.group(2), m.group(3)))
    return res


def region(off):
    o = off + 0x80
    if 0x20 <= o < 0xA0: return "gpr"
    if 0xA0 <= o < 0xE0: return "cr"
    if o == 0xF0: return "downcount"
    if o in (0xF4, 0xF5): return "xer"
    if 0x100 <= o < 0x300: return "fpr"
    if o in (0, 4): return "pc/npc"
    if o == 0xEC: return "exceptions"
    if 0xE0 <= o < 0xEC: return "msr/fpscr"
    return "spr/other"


def kind(op, args):
    if op.startswith("call"):
        return "call"
    m = re.search(r"(-?0x[0-9a-f]+|)\(%rbp\)", args)
    if m:
        off = int(m.group(1), 16) if m.group(1) else 0
        parts = args.split(", ")
        if op.startswith("cmp") or op.startswith("test"):
            dirn = "test"
        elif parts[0].endswith("(%rbp)") and len(parts) > 1:
            dirn = "load"
        else:
            dirn = "store"
        return "ppcState %s %s" % (region(off), dirn)
    if op.startswith("movbe") or op.startswith("bswap") or "(%rbx," in args or "(%rbx)" in args:
        return "guest memory"
    if op in ("cvtsd2ss", "cvtss2sd", "cvtpd2ps", "cvtps2pd"):
        return "float round/convert"
    if op.startswith("ucomis"):
        return "float NaN check"
    if op == "jmp":
        return "jmp"
    if op.startswith("j"):
        return "cond branch"
    if "%xmm" in args:
        return "float math/moves"
    return "integer ALU/moves"


by_block = collections.defaultdict(list)
routines = collections.Counter()
unmapped = 0
for a, c in samples.items():
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and a < starts[i] + max(entries[starts[i]][0], 1):
        s = starts[i]
        if entries[s][1].startswith("JIT_PPC"):
            by_block[s].append((a, c))
        else:
            routines[entries[s][1]] += c
    else:
        unmapped += c

K = collections.Counter()      # interrupted instruction
KP = collections.Counter()     # instruction before it
pos = collections.Counter()
ops = collections.Counter()
nocode = 0
blockheat = collections.Counter()
for s, lst in by_block.items():
    size, name = entries[s]
    ins = disasm(s, size)
    if not ins:
        nocode += sum(c for _, c in lst)
        continue
    addrs = [x[0] for x in ins]
    for a, c in lst:
        j = bisect.bisect_right(addrs, a) - 1
        if j < 0:
            continue
        blockheat[name] += c
        _, op, args = ins[j]
        K[kind(op, args)] += c
        ops[op] += c
        if j > 0:
            KP[kind(ins[j - 1][1], ins[j - 1][2])] += c
        else:
            KP["(block entry)"] += c
        pos["first instruction" if j == 0 else "instructions 2-4" if j < 4 else "rest"] += c

bt = sum(K.values())
print("%d windows, CPU thread %d samples, JIT %d (%.1f%%)" % (nwin, total_cpu, jit_total, 100.0 * jit_total / max(total_cpu, 1)))
print("of JIT samples: blocks %.1f%%, asm routines %.1f%%, unmapped %.1f%%, block code missing %.1f%%" % (
    100.0 * bt / jit_total, 100.0 * sum(routines.values()) / jit_total, 100.0 * unmapped / jit_total,
    100.0 * nocode / jit_total))
for k, v in routines.most_common(10):
    print("   %5.2f%% of JIT  %s" % (100.0 * v / jit_total, k))
print("blocks hit: %d; top 10 blocks = %.1f%%, top 100 = %.1f%%, top 1000 = %.1f%% of block time" % (
    len(blockheat), *[100.0 * sum(v for _, v in blockheat.most_common(k)) / bt for k in (10, 100, 1000)]))
print("position in block:", {k: "%.1f%%" % (100.0 * v / bt) for k, v in pos.items()})
print("\n%-34s %7s %7s" % ("kind (share of block time)", "exact", "prev"))
for k in sorted(set(K) | set(KP), key=lambda k: -(K[k] + KP[k])):
    print("%-34s %6.1f%% %6.1f%%" % (k, 100.0 * K[k] / bt, 100.0 * KP[k] / bt))
print("\ntop ops:", ", ".join("%s %.1f%%" % (k, 100.0 * v / bt) for k, v in ops.most_common(20)))

# --- optional: the hottest blocks, instruction by instruction ---
show = int(sys.argv[4]) if len(sys.argv) > 4 else 0
if show:
    byname = {entries[s][1]: s for s in by_block}
    for name, heat in blockheat.most_common(show):
        s = byname[name]
        ins = disasm(s, entries[s][0])
        hits = collections.Counter()
        for a, c in by_block[s]:
            hits[a] += c
        print("\n==== %s @%#x  %.2f%% of block time, %d bytes" % (name, s, 100.0 * heat / bt, entries[s][0]))
        for a, op, args in ins:
            h = hits.get(a, 0)
            print("  %6s %x: %-9s %s" % ("%.1f%%" % (100.0 * h / heat) if h else "", a, op, args[:70]))

# --- which guest GPRs the ppcState gpr loads/stores are for (exact + the instruction after) ---
G = collections.Counter()
static = collections.Counter()
for s, lst in by_block.items():
    ins = disasm(s, entries[s][0])
    if not ins:
        continue
    addrs = [x[0] for x in ins]
    heat = collections.Counter()
    for a, c in lst:
        j = bisect.bisect_right(addrs, a) - 1
        if j >= 0:
            heat[j] += c
            if j > 0:
                heat[j - 1] += c
    w = sum(c for _, c in lst)
    for j, (a, op, args) in enumerate(ins):
        m = re.search(r"(-?0x[0-9a-f]+|)\(%rbp\)", args)
        if not m or op.startswith("call"):
            continue
        off = (int(m.group(1), 16) if m.group(1) else 0) + 0x80
        if 0x20 <= off < 0xA0:
            r = (off - 0x20) // 4
            d2 = "load" if args.split(", ")[0].endswith("(%rbp)") and "," in args else "store"
            G[(r, d2)] += heat[j]
            static[(r, d2)] += w  # executed-weighted: block heat x occurrences
tg = sum(G.values())
ts = sum(static.values())
print("\nguest GPR loads/stores by register (sample heat on/after the access; block-heat weighted count):")
regs = collections.Counter()
for (r, d2), v in G.items():
    regs[r] += v
regs_s = collections.Counter()
for (r, d2), v in static.items():
    regs_s[r] += v
for r, v in regs.most_common(14):
    print("  r%-2d  heat %5.1f%%  (load %4.1f%% store %4.1f%%)   weighted count %5.1f%%" % (
        r, 100.0 * v / tg, 100.0 * G[(r, "load")] / tg, 100.0 * G[(r, "store")] / tg, 100.0 * regs_s[r] / ts))
