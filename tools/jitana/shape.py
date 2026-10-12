#!/usr/bin/env python3
"""shape.py <dir> t0 t1: the shape of the CPU thread's hot guest code, sample-weighted.
For each sampled JIT block: its guest code from the block start up to the first blr / bctr /
rfi / unconditional b, and the conditional branches in it: forward targets inside that stretch
("if" skips that rejoin), backward targets inside it (loops), or targets outside (real exits)."""
import collections, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapload import load_map

d, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
mem = open(os.path.join(d, "mem1.bin"), "rb").read()


def word(a):
    o = a & 0x01ffffff
    return struct.unpack(">I", mem[o:o + 4])[0] if o + 4 <= len(mem) else 0


def sext(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


entries = load_map(d)
weights = collections.Counter()
thread = False
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"== ([\d.]+) s, (.*?): (\d+) samples", line)
    if m:
        thread = m.group(2) == "CPU thread" and t0 <= float(m.group(1)) <= t1
        continue
    if thread:
        m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
        if m:
            weights[int(m.group(2), 16)] += float(m.group(1))

import bisect
starts = sorted(entries)
block_w = collections.Counter()
for b, w in weights.items():
    i = bisect.bisect_right(starts, b) - 1
    if i >= 0 and starts[i] + entries[starts[i]][0] > b:
        name = entries[starts[i]][1]
        m = re.match(r"JIT_PPC_(?:\S+_)?([0-9a-f]{8})$", name)
        if m:
            block_w[0x80000000 | int(m.group(1), 16)] += w

tot = sum(block_w.values())
lengths = 0.0
kinds = collections.Counter()
ends = collections.Counter()
for start, w in block_w.items():
    a = start
    branches = []
    end = "limit"
    for n in range(400):
        ins = word(a)
        op = ins >> 26
        if op == 16:  # bc
            bo = (ins >> 21) & 31
            target = a + sext(ins & 0xfffc, 16) if not (ins & 2) else sext(ins & 0xfffc, 16)
            if ins & 1:
                branches.append(("call", target))
            elif (bo & 0x14) == 0x14:
                end = "b"
                a += 4
                break
            else:
                branches.append(("cond", target))
        elif op == 18:  # b
            if ins & 1:
                branches.append(("call", a + sext(ins & 0x3fffffc, 26)))
            else:
                end = "b"
                a += 4
                break
        elif op == 19 and ((ins >> 1) & 0x3ff) in (16, 528, 50):  # bclr, bcctr, rfi
            bo = (ins >> 21) & 31
            if (bo & 0x14) == 0x14 or ((ins >> 1) & 0x3ff) == 50:
                end = {16: "blr", 528: "bctr", 50: "rfi"}[(ins >> 1) & 0x3ff]
                a += 4
                break
            branches.append(("condret", 0))
        a += 4
    length = (a - start) // 4
    lengths += w * length
    ends[end] += w
    for kind, target in branches:
        if kind == "cond":
            if start <= target < a and target > start:
                kinds["forward inside (if/else rejoins)"] += w
            elif target == start or (start <= target < a):
                kinds["back to the block (loop)"] += w
            else:
                kinds["exits elsewhere"] += w
        else:
            kinds[kind] += w

print("hot blocks: %d, average guest length %.1f instructions (weighted)" % (len(block_w), lengths / tot))
print("ends:", ", ".join("%s %.0f%%" % (k, 100 * v / tot) for k, v in ends.most_common()))
print("branches per block (weighted average):")
for k, v in kinds.most_common():
    print("   %.2f  %s" % (v / tot, k))
