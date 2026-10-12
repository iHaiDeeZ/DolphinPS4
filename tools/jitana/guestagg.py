#!/usr/bin/env python3
"""guestagg.py <dir> <ID> [t0] [t1]: JIT samples by guest function (function starts found by
scanning back to the stwu r1 prologue in mem1.bin; no symbols needed)."""
import bisect, collections, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapload import load_map

d, gid = sys.argv[1], sys.argv[2]
t0 = float(sys.argv[3]) if len(sys.argv) > 3 else 0
t1 = float(sys.argv[4]) if len(sys.argv) > 4 else 1e9
mem = open(os.path.join(d, "mem1.bin"), "rb").read()


def word(a):
    o = a & 0x01ffffff
    return struct.unpack(">I", mem[o:o + 4])[0] if o + 4 <= len(mem) else 0


blocks = {}
for host, (size, name) in load_map(d).items():
    m = re.match(r"JIT_PPC_(?:\S+_)?([0-9a-f]{8})$", name)
    if m:
        blocks[host] = (size, int(m.group(1), 16))
starts = sorted(blocks)
fc = {}


def func(pc):
    if pc in fc:
        return fc[pc]
    a = pc | 0x80000000
    for _ in range(8000):
        if (word(a) & 0xffff0000) == 0x94210000:
            break
        a -= 4
    fc[pc] = a
    return a


total = 0
by = collections.Counter()
blk = collections.Counter()
unm = 0
on = False
for line in open(os.path.join(d, "jitsamples-%s.log" % gid)):
    if line.startswith("=="):
        m = re.match(r"== (\S+) (\d+)", line)
        on = m and t0 <= float(m.group(1)) <= t1
        if on:
            total += int(m.group(2))
        continue
    if not on:
        continue
    p = line.split()
    if len(p) != 2:
        continue
    a, n = int(p[0], 16), int(p[1])
    i = bisect.bisect_right(starts, a) - 1
    if i < 0 or a >= starts[i] + max(blocks[starts[i]][0], 1):
        unm += n
        continue
    pc = blocks[starts[i]][1]
    by[func(pc)] += n
    blk[pc] += n
js = sum(by.values()) + unm
print("CPU-thread samples %d, JIT %d (%.1f%%), unmapped %d" % (total, js, 100.0 * js / max(total, 1), unm))
print("hottest guest functions (%% of CPU thread):")
acc = 0
for f, n in by.most_common(30):
    acc += n
    print("  %5.2f%%  (cum %5.1f%%)  %08x" % (100.0 * n / total, 100.0 * acc / total, f))
print("hottest blocks:")
for b, n in blk.most_common(15):
    print("  %5.2f%%  %08x" % (100.0 * n / total, b))
