#!/usr/bin/env python3
"""ps4hook.py - talk to Dolphin for PS4's hook (Settings > Diagnostics > Hook, TCP 9520).

  ps4hook.py [--ip IP] <command ...>   one command, e.g. "status", "jit top 20", "press cross"
  ps4hook.py [--ip IP]                 interactive (type "help" for the console's commands)
  ps4hook.py [--ip IP] top [thread] [--oelf F]   where each thread's time goes, by function
  ps4hook.py [--ip IP] gaps [seconds]  watch the game, then say what limits it and where to look
  ps4hook.py [--ip IP] record <file.csv> [seconds]   the monitor's numbers, one row per report
  ps4hook.py [--ip IP] script <file>   run commands from a file ("#" comments), replies printed

Dolphin code is named with the build's symbols: ~/dolphinps4-build/oelf/lab-v<version>.oelf (the
package script keeps one per JIT Lab version), or --oelf. Needs llvm-nm-21 (in WSL; called
through wsl.exe from Windows).
"""
import bisect, collections, os, pickle, re, socket, subprocess, sys, time

DEFAULT_IP = os.environ.get("PS4_IP", "192.168.0.225")
PORT = 9520


class Hook:
    def __init__(self, ip, timeout=30):
        self.sock = socket.create_connection((ip, PORT), timeout=10)
        self.sock.settimeout(timeout)
        self.buf = b""
        self.banner = self._reply()

    def _line(self):
        while b"\n" not in self.buf:
            data = self.sock.recv(65536)
            if not data:
                raise ConnectionError("the console closed the connection")
            self.buf += data
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", "replace")

    def _reply(self, on_line=None):
        lines = []
        while True:
            line = self._line()
            if line == ".":
                return "\n".join(lines)
            if on_line:
                on_line(line)
            else:
                lines.append(line)

    def cmd(self, text, on_line=None):
        self.sock.sendall((text + "\n").encode())
        return self._reply(on_line)

    def close(self):
        try:
            self.sock.sendall(b"quit\n")
        except OSError:
            pass
        self.sock.close()


# --- symbols -------------------------------------------------------------------------------------

def wsl_path(path):
    m = re.match(r"^\\\\wsl(?:\.localhost|\$)\\[^\\]+(\\.*)$", path)
    return m.group(1).replace("\\", "/") if m else path


def find_oelf(version):
    v = version.lstrip("v")
    if os.name == "nt":
        base = r"\\wsl.localhost\Ubuntu\home\shiro\dolphinps4-build\oelf"
    else:
        base = os.path.expanduser("~/dolphinps4-build/oelf")
    for name in ("lab-v%s.oelf" % v, "v%s.oelf" % v):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return None


class Symbols:
    def __init__(self, oelf):
        cache = os.path.join(os.path.expanduser("~"), ".cache", "ps4hook")
        os.makedirs(cache, exist_ok=True)
        key = os.path.join(cache, re.sub(r"[^A-Za-z0-9.]", "_", oelf) + "-%d.pkl" % os.path.getmtime(oelf))
        if os.path.exists(key):
            self.syms = pickle.load(open(key, "rb"))
        else:
            if os.name == "nt":
                args = ["wsl.exe", "-d", "Ubuntu", "--", "llvm-nm-21", "-n", "--demangle", wsl_path(oelf)]
            else:
                args = ["llvm-nm-21", "-n", "--demangle", oelf]
            out = subprocess.run(args, capture_output=True, text=True, errors="replace").stdout
            syms = []
            for line in out.splitlines():
                p = line.split(" ", 2)
                if len(p) == 3 and p[1] in "tTwW" and p[0].strip():
                    syms.append((int(p[0], 16), p[2]))
            syms.sort()
            self.syms = syms
            pickle.dump(syms, open(key, "wb"))
        self.addrs = [a for a, _ in self.syms]

    def name(self, offset):
        i = bisect.bisect_right(self.addrs, offset) - 1
        if i < 0:
            return "0x%x" % offset
        n = self.syms[i][1]
        return re.sub(r"\(.*$", "", n) if len(n) > 90 else n


GROUPS = [
    ("radv/vulkan driver", r"^radv_|^vk_|^ac_|^si_|^ws_|^amdgpu|^nir_|^aco"),
    ("Vulkan backend", r"^Vulkan::"),
    ("texture cache", r"TextureCache|TCacheEntry|TextureInfo|TMEM::|TexDecoder|TextureDecoder|PS4TextureHash|GetHash64|TexDecode|TextureConversion"),
    ("vertex loading", r"VertexLoader|AddList|AddStrip|AddQuads|AddFan|IndexGenerator|NativeVertexFormat|CheckCPConfiguration"),
    ("GX command decode", r"OpcodeDecoder|RunFifo|LoadBPReg|LoadXFReg|LoadCPReg|BPWritten|XFMemWritten|RunCallback"),
    ("shaders/pipelines", r"ShaderUid|ShaderManager|SetConstants|ShaderCache|UberShader|PipelineConfig|GetPipeline"),
    ("vertex manager / draw", r"VertexManagerBase|VertexManager::|CalculateZSlope|DoDraw|UploadUniforms|CommitBuffer"),
    ("FIFO / GPU loop", r"Fifo::|CommandProcessor|BlockingLoop|RunGpu|GatherPipe"),
    ("framebuffer / EFB", r"FramebufferManager|EFB|PeekCache|BoundingBox"),
    ("MMU / memory", r"PowerPC::MMU|Memory::|SoftTLB|ReadFromJit|WriteFromJit"),
    ("recompiler (compiling)", r"Jit64::|JitPS4::|JitBase|JitCache|PPCAnalyst|Gen::|EmuCodeBlock|RegCache"),
    ("interpreter", r"Interpreter"),
    ("CoreTiming / HW", r"CoreTiming|SystemTimers|VideoInterface|SerialInterface|ProcessorInterface|ExpansionInterface|DSP"),
    ("audio", r"Mixer|DSPHLE|AX|Zelda|AudioCommon|Sound"),
    ("libc / memcpy", r"^memcpy|^memset|^memcmp|^bcmp|^memmove|^strlen|^__|^std::"),
]


def group(name):
    for g, pat in GROUPS:
        if re.search(pat, name):
            return g
    return "other Dolphin code"


def parse_samples(text):
    """samples reply -> {thread: (total, [(count, kind, a, b)])}"""
    threads, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"thread (\d+) (.+) samples (\d+)$", line)
        if m:
            cur = m.group(2)
            threads[cur] = (int(m.group(3)), [])
            continue
        p = line.split()
        if cur is None or len(p) < 2 or not p[0].isdigit():
            continue
        a = int(p[2], 16) if len(p) > 2 else 0
        b = int(p[3], 16) if len(p) > 3 else 0
        threads[cur][1].append((int(p[0]), p[1], a, b))
    return threads


def top(hook, which, oelf=None, lines=25, quiet=False):
    info = dict(l.split(" ", 1) for l in hook.cmd("info").splitlines() if " " in l)
    if info.get("profiler") != "on":
        print("profiler was off: turning it on, sampling 4 s ...")
        hook.cmd("profiler on")
        time.sleep(4.5)
    oelf = oelf or find_oelf(info.get("version", ""))
    syms = Symbols(oelf) if oelf else None
    if not syms:
        print("(no symbols for version %s: --oelf <file>)" % info.get("version"))
    threads = parse_samples(hook.cmd("samples %s" % (which or "all")))
    report = {}
    for tname, (total, entries) in threads.items():
        if not total:
            continue
        funcs, groups = collections.Counter(), collections.Counter()
        for count, kind, a, b in entries:
            if kind == "e":
                n = syms.name(a) if syms else "elf 0x%x" % a
                funcs[n] += count
                groups[group(n)] += count
            elif kind == "j":
                funcs["[game code, recompiled]"] += count
                groups["game code (JIT)"] += count
            elif kind == "w":
                n = syms.name(a) if syms else "elf 0x%x" % a
                if b and syms:
                    n += " <- " + syms.name(b)
                funcs["[waiting] " + n] += count
                groups["waiting / system calls"] += count
            else:
                funcs["[system module 0x%x]" % a] += count
                groups["system modules"] += count
        report[tname] = (total, funcs, groups)
        if quiet:
            continue
        print("\n== %s: %d samples (%.1f s)" % (tname, total, total / 1000.0))
        for g, c in groups.most_common():
            print("  %5.1f%%  %s" % (100.0 * c / total, g))
        print("  -- functions")
        for f, c in funcs.most_common(lines):
            print("  %5.1f%%  %s" % (100.0 * c / total, f))
    return report


# --- the monitor line ----------------------------------------------------------------------------

FIELDS = {
    "speed": r"speed (-?[\d.]+)%", "max_speed": r"\(max (-?[\d.]+)%\)", "fps": r"([\d.]+) FPS",
    "vps": r"([\d.]+) VPS", "gpu_busy": r"gpu busy (-?[\d.]+)%", "cpu_busy": r"thread busy: cpu (-?[\d.]+)%",
    "video_busy": r" video (-?[\d.]+)% vk", "vk_busy": r" vk (-?[\d.]+)% vtx", "vtx_busy": r" vtx (-?[\d.]+)%,",
    "cpu_clock": r"cpu clock (\d+)%", "wait_cpu_for_gpu": r"cpu-for-gpu (\d+)", "wait_gpu_idle": r"gpu-idle (\d+)",
    "wait_vk_drain": r"vk-drain (\d+)", "wait_fences": r"fences (\d+)", "draws": r"draws (\d+)",
    "vertices": r"vertices (\d+)", "efb_copies": r"efb copies (\d+)", "efb_peeks": r"peeks (\d+)",
    "tex_uploads": r"tex uploads (\d+)", "compiles": r"compiles (\d+)/s", "compile_ms": r"compiles \d+/s (\d+) ms/s",
    "flexible_mib": r"(\d+) MiB flexible", "flip_slot": r"flip ms/s: slot (\d+)",
}


def parse_monitor(line):
    out = {}
    for k, pat in FIELDS.items():
        m = re.search(pat, line)
        if m:
            out[k] = float(m.group(1))
    m = re.search(r"monitor: (\d+) s", line)
    if m:
        out["t"] = float(m.group(1))
    return out


def watch_monitor(hook, seconds, on_row=None):
    rows = []

    def got(line):
        if "monitor:" in line:
            r = parse_monitor(line)
            rows.append(r)
            if on_row:
                on_row(r)
        elif "hitch" in line or "auto clock" in line:
            print("  " + line)
    hook.cmd("watch %d" % seconds, got)
    return rows


def avg(rows, key):
    v = [r[key] for r in rows if key in r and r[key] >= 0]
    return sum(v) / len(v) if v else None


def gaps(hook, seconds, oelf=None):
    print("watching %d s (the game should be in the part that is slow) ..." % seconds)
    hook.cmd("profiler on")
    rows = watch_monitor(hook, seconds, lambda r: print(
        "  %3.0f%% speed (max %3.0f%%) %5.1f FPS | busy cpu %3.0f%% video %3.0f%% gpu %3.0f%% | clock %s%%" % (
            r.get("speed", -1), r.get("max_speed", -1), r.get("fps", -1), r.get("cpu_busy", -1),
            r.get("video_busy", -1), r.get("gpu_busy", -1), int(r.get("cpu_clock", 0)))))
    if not rows:
        print("no monitor lines (is a game running?)")
        return
    a = {k: avg(rows, k) for k in FIELDS}
    rep = top(hook, "all", oelf, quiet=True)
    jit = hook.cmd("jit top 15")
    print("\n=== averages over %d reports" % len(rows))
    for k in ("speed", "max_speed", "fps", "cpu_busy", "video_busy", "vk_busy", "vtx_busy", "gpu_busy",
              "cpu_clock", "wait_cpu_for_gpu", "wait_gpu_idle", "wait_fences", "draws", "efb_copies",
              "efb_peeks", "tex_uploads", "compiles", "compile_ms"):
        if a.get(k) is not None:
            print("  %-18s %8.1f" % (k, a[k]))
    print("\n=== what limits the game")
    speed, mx = a.get("speed") or 0, a.get("max_speed") or 0
    cpu, video, gpu = a.get("cpu_busy") or 0, a.get("video_busy") or 0, a.get("gpu_busy") or 0
    findings = []
    if speed >= 98 and mx >= 105:
        findings.append("Full speed with headroom (max %.0f%%): the frame rate is the game's own." % mx)
    if cpu >= 90 and mx < 102:
        findings.append("CPU thread (emulated PowerPC) is the limit: %.0f%% busy, max speed %.0f%%." % (cpu, mx))
    if video >= 90:
        findings.append("Video thread (GX commands -> Vulkan) is the limit: %.0f%% busy; the CPU thread "
                        "waits %.0f ms/s for it." % (video, a.get("wait_cpu_for_gpu") or 0))
    if gpu >= 85:
        findings.append("The GPU itself is busy %.0f%%: resolution / effects." % gpu)
    if speed < 95 and cpu < 85 and video < 85 and gpu < 70:
        findings.append("Nothing is saturated but speed is %.0f%%: time is lost waiting (sync, fences, "
                        "flips, compiles) - see the waits above." % speed)
    if (a.get("compile_ms") or 0) > 50:
        findings.append("Shader compiles cost %.0f ms/s." % a["compile_ms"])
    for f in findings or ["No clear limit found in these numbers."]:
        print("  - " + f)
    for tname in ("CPU thread", "Video thread", "GPU thread"):
        for name, (total, funcs, groups) in rep.items():
            if name.lower().startswith(tname.lower().split()[0].lower()):
                print("\n  %s (%d samples):" % (name, total))
                for g, c in groups.most_common(6):
                    print("    %5.1f%%  %s" % (100.0 * c / total, g))
                for f, c in funcs.most_common(8):
                    print("      %5.1f%%  %s" % (100.0 * c / total, f))
    print("\n=== hottest game code (CPU thread)\n" + jit)


def record(hook, path, seconds):
    keys = ["t"] + list(FIELDS)
    with open(path, "w") as f:
        f.write(",".join(keys) + "\n")

        def row(r):
            f.write(",".join("%g" % r[k] if k in r else "" for k in keys) + "\n")
            f.flush()
            print("  %s" % {k: r[k] for k in ("t", "speed", "fps", "cpu_busy", "video_busy") if k in r})
        watch_monitor(hook, seconds, row)
    print("wrote " + path)


def main():
    args = sys.argv[1:]
    ip, oelf = DEFAULT_IP, None
    if "--ip" in args:
        i = args.index("--ip")
        ip = args[i + 1]
        del args[i:i + 2]
    if "--oelf" in args:
        i = args.index("--oelf")
        oelf = args[i + 1]
        del args[i:i + 2]
    hook = Hook(ip, timeout=700)
    try:
        if not args:
            print(hook.banner)
            while True:
                try:
                    line = input("ps4> ").strip()
                except EOFError:
                    break
                if line in ("quit", "exit"):
                    break
                if line:
                    print(hook.cmd(line, print) if line.startswith("watch") else hook.cmd(line))
        elif args[0] == "top":
            top(hook, args[1] if len(args) > 1 else "all", oelf)
        elif args[0] == "gaps":
            gaps(hook, int(args[1]) if len(args) > 1 else 20, oelf)
        elif args[0] == "record":
            record(hook, args[1], int(args[2]) if len(args) > 2 else 60)
        elif args[0] == "script":
            for line in open(args[1]):
                line = line.strip()
                if line and not line.startswith("#"):
                    print("ps4> " + line)
                    print(hook.cmd(line, print) if line.startswith("watch") else hook.cmd(line))
        else:
            cmd = " ".join(args)
            out = hook.cmd(cmd, print if args[0] == "watch" else None)
            if out:
                print(out)
    finally:
        hook.close()


if __name__ == "__main__":
    main()
