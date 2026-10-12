#!/usr/bin/env python3
"""groupagg.py <samples.log> <t0> <t1> <thread>: one thread's samples grouped by subsystem
(OELF env: the build's symbols). Prints groups, then the top functions of each group."""
import bisect, collections, os, re, subprocess, sys

O = os.environ["OELF"]
out = subprocess.run(["llvm-nm-21", "-n", "--demangle", O], capture_output=True, text=True).stdout
syms = []
for line in out.splitlines():
    p = line.split(" ", 2)
    if len(p) == 3 and p[1] in "tTwW" and p[0].strip():
        syms.append((int(p[0], 16), p[2]))
syms.sort()
addrs = [a for a, _ in syms]


def name(v):
    i = bisect.bisect_right(addrs, v) - 1
    return syms[i][1] if i >= 0 else "?"


GROUPS = [
    ("waiting", r"^SYS<-"),
    ("radv/vulkan driver", r"^radv_|^vk_|^ac_|^si_|^ac_ps4|^ws_|^amdgpu|^radv"),
    ("Vulkan backend", r"^Vulkan::"),
    ("texture cache", r"TextureCache|TCacheEntry|TextureInfo|TMEM::|TexDecoder|TextureDecoder|PS4TextureHash|GetHash64|TexDecode|TextureConversion"),
    ("vertex loading", r"VertexLoader|AddList|AddStrip|AddQuads|AddFan|IndexGenerator|GetRemainingIndices|NativeVertexFormat|CheckCPConfiguration|VertexLoaderX64|VertexLoaderManager"),
    ("GX command decode", r"OpcodeDecoder|RunFifo|LoadBPReg|LoadXFReg|LoadCPReg|BPWritten|XFMemWritten|RunCallback"),
    ("shader uids/managers", r"GetPixelShaderUid|GetVertexShaderUid|GetGeometryShaderUid|ShaderManager|SetConstants|PixelShaderManager|VertexShaderManager|GeometryShaderManager|ShaderCache|UberShader|PipelineConfig|GetPipeline"),
    ("vertex manager / draw", r"VertexManagerBase|VertexManager::|CalculateZSlope|Flush\b|DoDraw|UploadUniforms|CommitBuffer"),
    ("FIFO / GPU loop", r"Fifo::|CommandProcessor|BlockingLoop|RunGpu"),
    ("framebuffer / EFB", r"FramebufferManager|EFB|PeekCache|Bbox|BoundingBox"),
    ("memcpy/memset/libc", r"^memcpy|^memset|^memcmp|^bcmp|^memmove|^strlen|^__"),
]


def group(n):
    for g, pat in GROUPS:
        if re.search(pat, n):
            return g
    return "other"


log, lo, hi, want = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
groups = collections.Counter()
funcs = collections.defaultdict(collections.Counter)
windows = 0
on = False
for line in open(log, errors="replace"):
    m = re.match(r"== ([\d.]+) s, (.*?): (\d+) samples", line)
    if m:
        on = lo <= float(m.group(1)) <= hi and m.group(2) == want
        windows += on
        continue
    if not on:
        continue
    m = re.match(r"\s+([\d.]+)% (elf|syscall from elf|jit|sys) (0x[0-9a-f]+)", line)
    if not m:
        continue
    pct, kind, a = float(m.group(1)), m.group(2), int(m.group(3), 16)
    if kind == "jit":
        n = "JIT code"
    elif kind == "sys":
        n = "system library"
    elif kind.startswith("syscall"):
        n = "SYS<- " + name(a)
    else:
        n = name(a)
    g = "JIT code" if kind == "jit" else group(n)
    groups[g] += pct
    funcs[g][n[:90]] += pct
print("%s, %d windows" % (want, windows))
for g, v in groups.most_common():
    print("  %5.1f%%  %s" % (v / windows, g))
    for f, w in funcs[g].most_common(6):
        print("            %5.2f%%  %s" % (w / windows, f))
