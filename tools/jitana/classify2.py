#!/usr/bin/env python3
"""classify.py <dir> t0 t1 [thread]: where the CPU thread's sampled JIT time goes by x86 instruction
kind. Each 128-byte sample bucket's weight is spread over the instructions in it (disassembled from
the start of the block that holds it, so instructions are aligned)."""
import bisect, collections, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapload import load_map

d, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
want = sys.argv[4] if len(sys.argv) > 4 else "CPU thread"
entries = load_map(d)
starts = sorted(entries)

buckets = collections.Counter()
nwin = 0
thread = None
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"== ([\d.]+) s, (.*?): (\d+) samples", line)
    if m:
        thread = m.group(2) == want and t0 <= float(m.group(1)) <= t1
        nwin += thread
        continue
    if thread:
        m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
        if m:
            buckets[int(m.group(2), 16)] += float(m.group(1))

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
        return []
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


def kind(op, args):
    if op.startswith("call"):
        return "call (helper/asm routine)"
    if op in ("movbel", "movbew", "movbeq") or op.startswith("bswap"):
        return "guest memory (fastmem)"
    if "(%rbx," in args or "(%rbx)" in args:
        return "guest memory (fastmem)"
    if op in ("cvtsd2ss", "cvtss2sd", "cvtpd2ps", "cvtps2pd"):
        return "float rounding/convert"
    if op.startswith("ucomis") or op == "jp" or op == "jnp":
        return "float NaN checks"
    if op.startswith("j") or op == "ret":
        return "branches/jumps"
    if "(%rbp)" in args:
        return "ppcState (spill/fill/flags)"
    if "%xmm" in args:
        return "float/paired math+moves"
    return "integer ALU/moves"


blocks_needed = collections.defaultdict(list)
miss = 0.0
for b, w in buckets.items():
    i = bisect.bisect_right(starts, b + 127) - 1
    found = False
    while i >= 0 and starts[i] + max(entries[starts[i]][0], 1) > b:
        s = starts[i]
        size, name = entries[s]
        blocks_needed[s].append((b, w))
        found = True
        break
    if not found:
        miss += w

total = sum(buckets.values())
kinds = collections.Counter()
ops = collections.Counter()
routines = collections.Counter()
for s, lst in blocks_needed.items():
    size, name = entries[s]
    if not name.startswith("JIT_PPC"):
        for b, w in lst:
            routines[name] += w
        continue
    ins = disasm(s, size)
    for b, w in lst:
        inb = [x for x in ins if b <= x[0] < b + 128]
        if not inb:
            miss += w
            continue
        for a, op, args in inb:
            kinds[kind(op, args)] += w / len(inb)
            ops[op] += w / len(inb)

print("%s: %.1f%% of samples in listed JIT buckets (%d windows); per-window avg" % (want, total / nwin, nwin))
print("asm routines/dispatcher: %.2f%%  not mapped: %.2f%%" % (sum(routines.values()) / nwin, miss / nwin))
for k, v in routines.most_common(12):
    print("   %6.2f%%  %s" % (v / nwin, k))
print("block code by kind (share of block-code time):")
bt = sum(kinds.values())
for k, v in kinds.most_common():
    print("   %5.1f%%  %s" % (100 * v / bt, k))
print("top x86 ops:")
for k, v in ops.most_common(25):
    print("   %5.1f%%  %s" % (100 * v / bt, k))

# --- ppcState accesses: which state, load or store (rbp = &ppcState + 0x80) ---
def region(off):
    o = off + 0x80
    if 0x20 <= o < 0xA0: return "gpr"
    if 0xA0 <= o < 0xE0: return "cr"
    if o == 0xF0: return "downcount"
    if o in (0xF4, 0xF5): return "xer"
    if 0x100 <= o < 0x300: return "ps (fpr)"
    if o in (0, 4): return "pc/npc"
    if o == 0xEC: return "exceptions"
    if 0xE0 <= o < 0xEC: return "msr/fpscr"
    return "other (spr etc.)"

st = collections.Counter()
for s, lst in blocks_needed.items():
    size, name = entries[s]
    if not name.startswith("JIT_PPC"):
        continue
    ins = disasm(s, size)
    for b, w in lst:
        inb = [x for x in ins if b <= x[0] < b + 128]
        for a, op, args in inb:
            m = re.search(r"(-?0x[0-9a-f]+|)\(%rbp\)", args)
            if not m or op.startswith("call"):
                continue
            off = int(m.group(1), 16) if m.group(1) else 0
            parts = args.split(", ")
            dirn = "load" if parts[0].endswith("(%rbp)") and len(parts) > 1 else "store/rmw"
            if op.startswith("cmp") or op.startswith("test"):
                dirn = "compare"
            st[(region(off), dirn)] += w / len(inb)
tt = sum(st.values())
gr = collections.Counter()
pos = collections.Counter()
for s_, lst in blocks_needed.items():
    size, name = entries[s_]
    if not name.startswith("JIT_PPC"):
        continue
    ins = disasm(s_, size)
    n_ins = len(ins)
    for b, w in lst:
        inb = [x for x in ins if b <= x[0] < b + 128]
        for a, op, args in inb:
            m = re.search(r"(-?0x[0-9a-f]+|)\(%rbp\)", args)
            if not m or op.startswith("call"):
                continue
            off = int(m.group(1), 16) if m.group(1) else 0
            if region(off) != "gpr":
                continue
            reg = (off + 0x80 - 0x20) // 4
            parts = args.split(", ")
            dirn = "load" if parts[0].endswith("(%rbp)") and len(parts) > 1 else "store"
            gr[(reg, dirn)] += w / len(inb)
            idx = next(i for i, x in enumerate(ins) if x[0] == a)
            # where in the block: the first 8 instructions, or within 8 before a jmp/ret (exit)
            near_exit = any(x[1].startswith("jmp") or x[1] == "ret" for x in ins[idx + 1:idx + 9])
            where = "block start" if idx < 8 else "before an exit" if near_exit else "middle"
            pos[(where, dirn)] += w / len(inb)
gt = sum(gr.values())
print("GPR accesses by guest register:")
for (r, d_), v in sorted(gr.items(), key=lambda kv: -kv[1])[:20]:
    print("   %5.1f%%  r%d %s" % (100 * v / gt, r, d_))
print("GPR accesses by place in the block:")
for k, v in pos.most_common():
    print("   %5.1f%%  %s %s" % (100 * v / gt, *k))
print("ppcState accesses:")
for k, v in st.most_common(16):
    print("   %5.1f%%  %s %s" % (100 * v / tt, *k))
