import re, struct, sys, os, glob, bisect, collections
d, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
mem = open(os.path.join(d, "mem1.bin"), "rb").read()
def word(a):
    o = a & 0x01ffffff
    return struct.unpack(">I", mem[o:o+4])[0] if o + 4 <= len(mem) else 0
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapload import load_map
entries = {}
for a, (size, name) in load_map(d).items():
    m = re.match(r"JIT_PPC_(?:\S+_)?([0-9a-f]{8})$", name)
    if m: entries[a] = (size, int(m.group(1), 16))
starts = sorted(entries)
def block(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0:
        s = starts[i]; size, pc = entries[s]
        if a < s + max(size, 1): return pc
    return None
fcache = {}
def func(pc):
    if pc in fcache: return fcache[pc]
    a = pc | 0x80000000
    for k in range(6000):
        if (word(a) & 0xffff0000) == 0x94210000: break
        a -= 4
    fcache[pc] = a; return a
tot = collections.Counter(); n = 0; on = False; jit = 0
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"== ([\d.]+) s, (.*?): ", line)
    if m: on = m.group(2) == "CPU thread" and t0 <= float(m.group(1)) <= t1; n += on; continue
    if on:
        m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
        if m:
            pc = block(int(m.group(2), 16)); v = float(m.group(1)); jit += v
            if pc: tot[func(pc)] += v
print("windows %d, visible JIT %.1f%%" % (n, jit / n))
acc = 0
for f, v in tot.most_common(25):
    acc += v / n; print("  %5.2f%%  (cum %5.1f%%)  function %08x" % (v / n, acc, f))
