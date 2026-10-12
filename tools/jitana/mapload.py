import bisect, glob, os, re


def load_map(d):
    """perf-*.map entries in registration order; a newer block replaces every older one it
    overlaps (the JIT reuses freed code space). Returns {start: (size, name)}."""
    starts, info = [], {}
    paths = sorted(glob.glob(os.path.join(d, "perf-*.map")), key=os.path.getmtime)
    for path in paths:
        for line in open(path, errors="replace"):
            m = re.match(r"(0x[0-9a-f]+) ([0-9a-f]+) (\S+)", line)
            if not m:
                continue
            s, size, name = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            e = s + max(size, 1)
            i = bisect.bisect_left(starts, s)
            if i > 0 and starts[i - 1] + max(info[starts[i - 1]][0], 1) > s:
                i -= 1
            j = i
            while j < len(starts) and starts[j] < e:
                del info[starts[j]]
                j += 1
            starts[i:j] = [s]
            info[s] = (size, name)
    return info
