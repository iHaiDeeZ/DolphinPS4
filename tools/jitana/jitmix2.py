#!/usr/bin/env python3
"""jitmix.py <dir> <t0> <t1>: what the sampled JIT code of the CPU thread does, by instruction
kind (dir has samples.log and jitcode.bin). ppcState = [rbp+x] (RPPCSTATE), guest memory =
[rbx+..] (RMEM) or movbe."""
import collections, os, re, struct, subprocess, sys, tempfile

d = sys.argv[1]
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
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
code = {}
o = 0
while o + 16 <= len(data):
    a, s = struct.unpack_from("<QQ", data, o)
    code[a] = data[o + 16:o + 16 + s]
    o += 16 + s


def kind(mn, ops):
    mem = "(" in ops
    if mn.startswith("movbe"):
        return "guest memory (movbe)"
    if "(%rbx" in ops or ",%rbx," in ops:
        return "guest memory (other)"
    if "%rbp)" in ops and mem:
        if mn.startswith(("mov", "vmov")):
            return "ppcState load/store (register spill/reload)"
        return "ppcState as operand"
    if mn.startswith(("j", "call", "ret")):
        return "branch/call"
    if mn.startswith("cmp") or mn.startswith("test"):
        return "compare/test"
    if re.match(r"v?(add|sub|mul|div|min|max|sqrt|fmadd|and|or|xor|andn)[ps][sd]$", mn) or \
            re.match(r"v?cvt", mn) or mn.startswith(("vpand", "pand", "por", "vpor", "pxor", "vpxor",
                                                   "shufp", "vshufp", "movddup", "vmovddup",
                                                   "unpck", "blend", "vblend", "psrl", "psll",
                                                   "vpsrl", "vpsll", "movsd", "movss", "movap",
                                                   "vmovap", "movhlps", "movlhps", "movq", "movd",
                                                   "vmovq", "vmovd", "pshuf", "ptest", "cmpsd",
                                                   "cmpps", "cmppd", "vcmp")):
        return "floating point / SSE"
    if mn.startswith(("mov", "lea", "xchg")) and not mem:
        return "register move/lea"
    if mem:
        return "other memory (constants, tables)"
    return "integer ALU"


cats = collections.Counter()
offs = collections.Counter()
total = 0.0
for chunk, b in code.items():
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
        if m:
            per[(chunk + int(m.group(1), 16)) & ~0xF].append((m.group(2), m.group(3)))
    for bk, ins in per.items():
        w = buckets.get(bk, 0) / max(n, 1)
        if not w:
            continue
        total += w
        for mn, ops in ins:
            cats[kind(mn, ops)] += w / len(ins)
            mo = re.search(r"(-?0x[0-9a-f]+|-?\d+)?\(%rbp\)", ops)
            if mo and "(%rbp)" in ops:
                offs[int(mo.group(1), 0) if mo.group(1) else 0] += w / len(ins)
print("windows %d, sampled JIT share %.1f%% of the CPU thread" % (n, total))
for k, v in cats.most_common():
    print("  %5.1f%%  (%4.1f%% of JIT)  %s" % (v, 100 * v / max(total, 1e-9), k))

print("ppcState offsets (from RPPCSTATE = state + 0x80):")
for o, v in offs.most_common(24):
    print("  %+5d (state+%#x)  %5.2f%%" % (o, o + 0x80, v))
