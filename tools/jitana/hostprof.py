#!/usr/bin/env python3
"""hostprof.py <prof.txt> <perf map dir> [thread name prefix] [top N]: the PC test bench's sampling
profile (PS4JIT_PROF) per thread: Dolphin functions (symbols of the binary), JIT blocks (perf map),
system libraries."""
import bisect, collections, glob, os, re, subprocess, sys

prof, mapdir = sys.argv[1], sys.argv[2]
want = sys.argv[3] if len(sys.argv) > 3 else None
top = int(sys.argv[4]) if len(sys.argv) > 4 else 40

samples, names, maps = [], {}, []
for line in open(prof):
    if line.startswith("thread "):
        _, tid, *name = line.split()
        names[int(tid)] = " ".join(name)
    elif line.startswith("map "):
        m = re.match(r"map ([0-9a-f]+)-([0-9a-f]+) (\S+) ([0-9a-f]+) \S+ \S+\s*(.*)", line)
        if m:
            maps.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3), int(m.group(4), 16),
                         m.group(5).strip()))
    else:
        tid, rip = line.split()
        samples.append((int(tid), int(rip, 16)))

# The binary: load base = start of its offset-0 mapping (PIE).
binary = next(p for (_, _, _, _, p) in maps if p.endswith("dolphin-emu-nogui"))
base = min(s for (s, _, _, off, p) in maps if p == binary and off == 0)
out = subprocess.run(["llvm-nm-21", "-n", "--demangle", binary], capture_output=True, text=True).stdout
syms = []
for line in out.splitlines():
    p = line.split(" ", 2)
    if len(p) == 3 and p[1] in "tTwW" and p[0].strip():
        syms.append((int(p[0], 16), p[2]))
syms.sort()
saddr = [a for a, _ in syms]

jit = []
for path in glob.glob(os.path.join(mapdir, "perf-*.map")):
    for line in open(path, errors="replace"):
        m = re.match(r"0x([0-9a-f]+) ([0-9a-f]+) (\S+)", line)
        if m:
            jit.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3)))
jit.sort()
jaddr = [a for a, _, _ in jit]


libsyms = {}


def libsym(path, rel):
    if path not in libsyms:
        out = subprocess.run(["llvm-nm-21", "-n", "-D", "--defined-only", path], capture_output=True,
                             text=True).stdout
        table = []
        for line in out.splitlines():
            p = line.split(" ", 2)
            if len(p) == 3 and p[1] in "tTwWiI":
                table.append((int(p[0], 16), p[2]))
        table.sort()
        libsyms[path] = ([a for a, _ in table], table)
    addrs, table = libsyms[path]
    i = bisect.bisect_right(addrs, rel) - 1
    return table[i][1] if i >= 0 else "?"


def where(rip):
    for (s, e, perms, off, path) in maps:
        if s <= rip < e:
            if path == binary:
                i = bisect.bisect_right(saddr, rip - base) - 1
                return "dolphin", syms[i][1] if i >= 0 else "?"
            if path.startswith("/"):
                lib_base = min(ms for (ms, _, _, o, p2) in maps if p2 == path and o == 0)
                return "system", os.path.basename(path) + ":" + libsym(path, rip - lib_base)
            if path:
                return "system", path
            break
    i = bisect.bisect_right(jaddr, rip) - 1
    if i >= 0 and jit[i][0] <= rip < jit[i][0] + max(jit[i][1], 1):
        name = jit[i][2]
        return ("jit", "JIT block" if name.startswith("JIT_PPC") else name)
    return "jit", "JIT (unmapped: far code / trampolines)"


per_thread = collections.defaultdict(collections.Counter)
kinds = collections.defaultdict(collections.Counter)
for tid, rip in samples:
    t = names.get(tid, str(tid))
    k, n = where(rip)
    per_thread[t][(k, n)] += 1
    kinds[t][k] += 1

total = len(samples)
for t, c in sorted(per_thread.items(), key=lambda kv: -sum(kv[1].values())):
    if want and not t.startswith(want):
        continue
    n = sum(c.values())
    print("== %s: %d samples (%.0f%% of all)  %s" % (t, n, 100 * n / total,
          "  ".join("%s %.0f%%" % (k, 100 * v / n) for k, v in kinds[t].most_common())))
    for (k, name), v in c.most_common(top if want else 8):
        print("   %5.1f%%  %-7s %s" % (100 * v / n, k, name[:120]))
