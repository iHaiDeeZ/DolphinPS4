#!/usr/bin/env python3
"""hints.py <blocks.txt> <mem1.bin>: do the branches' static prediction bits (the y bit) agree with
the measured profile? For every conditional bc with a measured taken rate."""
import collections, struct, sys
prof, mem1 = sys.argv[1], sys.argv[2]
mem = open(mem1, "rb").read()
def word(a):
    o = a & 0x01ffffff
    return struct.unpack(">I", mem[o:o + 4])[0]
blocks, taken = [], collections.Counter()
for line in open(prof):
    p = line.split()
    if p[0] == "B":
        blocks.append((int(p[1], 16), int(p[2]), int(p[3])))
    elif int(p[1], 16) != 0xFFFFFFFF:
        taken[(int(p[3], 16), int(p[1], 16))] += int(p[2])
stats = collections.Counter()
weight = collections.Counter()
for (src, dest), n in taken.items():
    ins = word(src)
    if ins >> 26 != 16 or ins & 1:
        continue
    bo = (ins >> 21) & 31
    if (bo & 0x14) == 0x14:
        continue
    reach = sum(r for (s, l, r) in blocks if s <= src < s + 4 * l)
    if not reach:
        continue
    p = n / reach
    backward = dest < src
    y = (bo & 1) != 0
    hint_taken = (not y) if backward else y  # the y bit reverses the default (backward taken)
    real = "taken>=70%" if p >= 0.7 else "taken<30%" if p < 0.3 else "mixed"
    stats[(real, "hint taken" if hint_taken else "hint not taken")] += 1
    weight[(real, "hint taken" if hint_taken else "hint not taken")] += n
for k in sorted(stats):
    print("%-12s %-16s %5d branches  %12d taken exits" % (k[0], k[1], stats[k], weight[k]))
