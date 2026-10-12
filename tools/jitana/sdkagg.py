#!/usr/bin/env python3
"""sdkagg.py <dir> <GAMEID>: the CPU thread's JIT time by guest function, named.

Inputs (from the PS4, profiler on): jitsamples-<ID>.log (every JIT sample at its exact address),
perf-*.map (JIT block -> guest PC), symbols-<ID>.txt (the game's functions; Nintendo SDK ones named
from Dolphin's signature database). Each JIT sample is charged to the guest function holding its
block's guest start address. Prints the hottest functions with their share of the CPU thread's
samples and of its JIT samples, SDK names first in a summary.
"""
import bisect, collections, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapload import load_map

d, gid = sys.argv[1], sys.argv[2]

# JIT blocks: host start -> (size, guest pc).
blocks = {}
for host, (size, name) in load_map(d).items():
    m = re.match(r"JIT_PPC_(?:\S+_)?([0-9a-f]{8})$", name)
    if m:
        pc = int(m.group(1), 16)
        # The map has physical addresses for MEM1 code; symbols are effective (0x8xxxxxxx).
        if pc < 0x01800000:
            pc |= 0x80000000
        blocks[host] = (size, pc)
starts = sorted(blocks)


def guest_of(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0:
        s = starts[i]
        size, pc = blocks[s]
        if a < s + max(size, 1):
            return pc
    return None


# Guest functions.
funcs = []
for line in open(os.path.join(d, "symbols-%s.txt" % gid), errors="replace"):
    parts = line.rstrip("\n").split(" ", 2)
    if len(parts) == 3:
        funcs.append((int(parts[0], 16), int(parts[1]), parts[2]))
funcs.sort()
fstarts = [f[0] for f in funcs]


def func_of(pc):
    i = bisect.bisect_right(fstarts, pc) - 1
    if i >= 0:
        a, size, name = funcs[i]
        if pc < a + max(size, 4):
            return name, a
    return None


total = 0
jit = collections.Counter()
by_func = collections.Counter()
unmapped = 0
for line in open(os.path.join(d, "jitsamples-%s.log" % gid), errors="replace"):
    if line.startswith("=="):
        m = re.match(r"== \S+ (\d+)", line)
        if m:
            total += int(m.group(1))
        continue
    parts = line.split()
    if len(parts) != 2:
        continue
    a, n = int(parts[0], 16), int(parts[1])
    pc = guest_of(a)
    if pc is None:
        unmapped += n
        continue
    f = func_of(pc)
    by_func[f if f else ("?%08x" % pc, pc)] += n

jit_total = sum(by_func.values()) + unmapped
print("CPU-thread samples %d, in JIT %d (%.1f%%), not mapped to a block %d" %
      (total, jit_total, 100.0 * jit_total / max(total, 1), unmapped))
print("\nhottest guest functions (share of CPU thread, of JIT):")
for (name, a), n in by_func.most_common(40):
    print("  %5.2f%%  %5.2f%%  %08x  %s" % (100.0 * n / max(total, 1), 100.0 * n / max(jit_total, 1),
                                          a, name))
sdk = [(k, n) for k, n in by_func.items() if not k[0].startswith(("zz_", "?"))]
sdk.sort(key=lambda x: -x[1])
print("\nnamed (SDK) functions:")
for (name, a), n in sdk[:30]:
    print("  %5.2f%%  %08x  %s" % (100.0 * n / max(total, 1), a, name))
print("  all named together: %.2f%% of the CPU thread" % (100.0 * sum(n for _, n in sdk) / max(total, 1)))
