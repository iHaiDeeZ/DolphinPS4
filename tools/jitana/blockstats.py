#!/usr/bin/env python3
"""blockstats.py <ana dir>: what a super-block (trace) optimizer could cover, from the PC bench's
block counts (PS4JIT_COUNT: blocks.txt) and CPU-thread samples (PS4JIT_PROF: samples.log + map)."""
import bisect, collections, glob, os, re, sys

d = sys.argv[1]
runs = collections.Counter()
length = {}
exits = collections.defaultdict(collections.Counter)
cur = None
for line in open(os.path.join(d, "blocks.txt")):
    p = line.split()
    if p[0] == "B":
        cur = int(p[1], 16)
        runs[cur] += int(p[3])
        length[cur] = max(length.get(cur, 0), int(p[2]))
    else:
        exits[cur][int(p[1], 16)] += int(p[2])

# Time per guest block from the samples (JIT buckets -> perf map block names).
starts, names = [], {}
for path in glob.glob(os.path.join(d, "perf-*.map")):
    for line in open(path, errors="replace"):
        m = re.match(r"0x([0-9a-f]+) ([0-9a-f]+) (\S+)", line)
        if m:
            s = int(m.group(1), 16)
            starts.append(s)
            names[s] = (int(m.group(2), 16), m.group(3))
starts.sort()
time = collections.Counter()
total_samples = 0.0
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"\s+([\d.]+)% jit 0x([0-9a-f]+)", line)
    if not m:
        continue
    w, a = float(m.group(1)), int(m.group(2), 16)
    total_samples += w
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and starts[i] + names[starts[i]][0] > a:
        mm = re.match(r"JIT_PPC_(?:\S+_)?([0-9a-f]{8})$", names[starts[i]][1])
        if mm:
            time[0x80000000 | int(mm.group(1), 16)] += w
jit_time = sum(time.values())

R = sum(runs.values())
I = sum(runs[b] * length[b] for b in runs)
print("block runs: %.0f M, guest instructions (upper bound) %.0f M, %.1f per block run" %
      (R / 1e6, I / 1e6, I / R))
indirect = sum(c[0xFFFFFFFF] for c in exits.values())
total_exits = sum(sum(c.values()) for c in exits.values())
print("exits: %.0f M, indirect (blr / bctr: returns, jump tables) %.1f%%" %
      (total_exits / 1e6, 100 * indirect / total_exits))
pred = 0
for b, c in exits.items():
    t = sum(c.values())
    if t and c.most_common(1)[0][1] / t >= 0.9 and c.most_common(1)[0][0] != 0xFFFFFFFF:
        pred += t
print("exits from blocks with one direct successor >= 90%%: %.1f%% (chainable into traces)" %
      (100 * pred / total_exits))

print("time in JIT blocks: %.1f%% of CPU-thread samples" % jit_time)
ranked = sorted(time.items(), key=lambda kv: -kv[1])
cum = 0
for n in (10, 50, 100, 200, 500, 1000):
    share = sum(v for _, v in ranked[:n])
    print("   hottest %4d blocks: %5.1f%% of JIT block time" % (n, 100 * share / jit_time))
print("hottest blocks: share of JIT time, runs/s (30 s window), guest instructions, ns per run")
for b, v in ranked[:15]:
    r = runs.get(b, 0)
    ns = (v / 100) * 30e9 / r if r else 0
    top = exits[b].most_common(2)
    print("   %08x %5.2f%%  %8.0f/s  %3d instr  %6.0f ns   exits %s" %
          (b, 100 * v / jit_time, r / 30, length.get(b, 0), ns,
           ", ".join("%s %.0f%%" % ("ind" if e == 0xFFFFFFFF else "%08x" % e,
                                     100 * c / max(1, sum(exits[b].values()))) for e, c in top)))
