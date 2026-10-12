#!/usr/bin/env python3
"""JIT profile analysis for the PS4 port.

jitana.py <dir> [t0 t1] [--blocks N] [--thread NAME]
  <dir> holds samples.log, perf-*.map, jitcode.bin, mem1.bin from /data/DolphinPS4.
Prints per thread where JIT time goes (blocks by guest address, asm routines, unmapped = far
code / trampolines), then for the hottest blocks the x86 with per-16-byte sample shares and the
guest code.
"""
import bisect, collections, glob, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(zip(sys.argv[1::1], sys.argv[2::1]))
d = args[0]
t0, t1 = (float(args[1]), float(args[2])) if len(args) >= 3 else (0, 1e9)
nblocks = int(opts.get("--blocks", 12))
only_thread = opts.get("--thread")

# --- JIT block map (latest registration wins for an address) ---
sys.path.insert(0, HERE)
from mapload import load_map
entries = load_map(d)
starts = sorted(entries)


def block_of(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0:
        s = starts[i]
        size, name = entries[s]
        if a < s + max(size, 1):
            return s, size, name
    return None


# --- samples ---
per_thread = collections.defaultdict(collections.Counter)  # thread -> bucket -> pct-sum
windows = collections.Counter()
thread = None
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"== ([\d.]+) s, (.*?): (\d+) samples", line)
    if m:
        t = float(m.group(1))
        thread = m.group(2) if t0 <= t <= t1 else None
        if thread:
            windows[thread] += 1
        continue
    if not thread:
        continue
    m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
    if m:
        per_thread[thread][int(m.group(2), 16)] += float(m.group(1))

# --- code dumps ---
code = {}
jc = os.path.join(d, "jitcode.bin")
if os.path.exists(jc):
    data = open(jc, "rb").read()
    o = 0
    while o + 16 <= len(data):
        addr, size = struct.unpack_from("<QQ", data, o)
        code[addr] = data[o + 16:o + 16 + size]
        o += 16 + size


def read_code(a, n):
    out = b""
    while n > 0:
        chunk = a & ~0xFFFF
        if chunk not in code:
            return None
        off = a - chunk
        take = min(n, 0x10000 - off)
        out += code[chunk][off:off + take]
        a += take
        n -= take
    return out


def x86(a, n, heat):
    b = read_code(a, n)
    if b is None:
        return "    (code not in jitcode.bin)\n"
    with tempfile.TemporaryDirectory() as tmp:
        raw, elf = os.path.join(tmp, "c.bin"), os.path.join(tmp, "c.o")
        open(raw, "wb").write(b)
        subprocess.run(["llvm-objcopy-21", "-I", "binary", "-O", "elf64-x86-64",
                        "--rename-section", ".data=.text,code", raw, elf], check=True)
        out = subprocess.run(["llvm-objdump-21", "-d", "--no-show-raw-insn",
                              "--adjust-vma=%#x" % a, elf], capture_output=True, text=True).stdout
    lines = []
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(.*)", line)
        if not m:
            continue
        ia = a + int(m.group(1), 16)
        h = heat.get(ia & ~0xF, 0)
        mark = ("%5.2f%%" % h) if h and (ia & ~0xF) not in seen_bucket else "      "
        seen_bucket.add(ia & ~0xF)
        lines.append("    %s %x: %s" % (mark, ia, m.group(2)))
    return "\n".join(lines) + "\n"


def guest(pc, n):
    mem = os.path.join(d, "mem1.bin")
    if not os.path.exists(mem):
        return ""
    out = subprocess.run([os.path.join(HERE, "gekkodis"), mem, "%x" % pc, str(n)],
                         capture_output=True, text=True).stdout
    res = []
    for line in out.splitlines():
        res.append("    " + line)
        ins = line.split(None, 2)[2] if len(line.split(None, 2)) > 2 else ""
        if re.match(r"(b|blr|bctr|rfi)\b", ins):
            break
    return "\n".join(res) + "\n"


for th, buckets in per_thread.items():
    if only_thread and only_thread not in th:
        continue
    n = windows[th]
    total = sum(buckets.values()) / n
    groups = collections.Counter()
    heat_by_block = collections.defaultdict(dict)
    for a, pct in buckets.items():
        b = block_of(a)
        if b:
            s, size, name = b
            key = name if not name.startswith("JIT_PPC_") else "%s @%#x" % (name, s)
            groups[key] += pct / n
            heat_by_block[key][a] = pct / n
        else:
            groups["[unmapped %#x]" % (a >> 20 << 20)] += pct / n
    print("#### %s: JIT %.1f%% of samples (%d windows)" % (th, total, n))
    for k, v in groups.most_common(40):
        print("  %5.2f%%  %s" % (v, k))
    print()
    for k, v in groups.most_common():
        if not k.startswith("JIT_PPC_") or nblocks <= 0:
            continue
        nblocks -= 1
        s = int(k.split("@")[1], 16)
        size, name = entries[s]
        pc = int(name.rsplit("_", 1)[1], 16)
        print("==== %s  %.2f%%  (x86 %d bytes)" % (k, v, size))
        print(guest(pc, 80))
        seen_bucket = set()
        print(x86(s, size, heat_by_block[k]))
