import re, struct, subprocess, sys, os, tempfile, collections
d = sys.argv[1]; t0, t1 = float(sys.argv[2]), float(sys.argv[3])
# samples (CPU thread jit buckets)
buckets = collections.Counter(); n = 0; on = False
for line in open(os.path.join(d, "samples.log")):
    m = re.match(r"== ([\d.]+) s, (.*?): ", line)
    if m:
        on = m.group(2) == "CPU thread" and t0 <= float(m.group(1)) <= t1; n += on; continue
    if on:
        m = re.match(r"\s+([\d.]+)% jit (0x[0-9a-f]+)", line)
        if m: buckets[int(m.group(2), 16)] += float(m.group(1))
data = open(os.path.join(d, "jitcode.bin"), "rb").read()
code = {}; o = 0
while o + 16 <= len(data):
    a, s = struct.unpack_from("<QQ", data, o); code[a] = data[o+16:o+16+s]; o += 16 + s
cats = collections.Counter(); total = 0
for chunk, b in code.items():
    with tempfile.TemporaryDirectory() as t:
        raw = os.path.join(t, "c.bin"); elf = os.path.join(t, "c.o"); open(raw, "wb").write(b)
        subprocess.run(["llvm-objcopy-21", "-I", "binary", "-O", "elf64-x86-64", "--rename-section", ".data=.text,code", raw, elf], check=True)
        out = subprocess.run(["llvm-objdump-21", "-d", "--no-show-raw-insn", "--adjust-vma=%#x" % chunk, elf], capture_output=True, text=True).stdout
    per = collections.defaultdict(list)
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(\S+)", line)
        if m: per[(chunk + int(m.group(1), 16)) & ~0xF].append(m.group(2))
    for bk, ins in per.items():
        w = buckets.get(bk, 0) / max(n, 1)
        if not w: continue
        total += w
        for i in ins:
            key = "rounding (cvtpd2ps/cvtps2pd)" if i in ("cvtpd2ps", "cvtps2pd", "vcvtpd2ps", "vcvtps2pd") else \
                  "single->double load (cvtss2sd)" if i in ("cvtss2sd",) else \
                  "fp math" if re.match(r"v?(add|sub|mul|div|min|max)[ps][sd]$", i) else \
                  "movbe (guest memory)" if i.startswith("movbe") else \
                  "loads/stores ppcState etc (mov)" if i.startswith("mov") else "other"
            cats[key] += w / len(ins)
print(len(buckets), n, sum(len(code[c]) for c in code)); print("sampled JIT share %.1f%% of CPU thread" % total)
for k, v in cats.most_common(): print("  %5.1f%%  %s" % (v, k))
