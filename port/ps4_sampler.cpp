// Sampling profiler for PS4 test builds.
//
// PS4 has no perf/Razor access for homebrew, so the app samples itself: a helper thread sends
// SIGPROF to each registered thread every millisecond, and the handler records the interrupted
// instruction pointer. Every 10 seconds the samples are aggregated and appended to
// /data/DolphinPS4/samples.log: per thread, the busiest eboot addresses (ELF virtual addresses,
// symbolize with `llvm-symbolizer --obj=<oelf> 0x...`), system module addresses ("sys") and JIT
// code addresses ("jit", 16-byte buckets). Every 60 s the busiest JIT code (64 KiB chunks) is
// copied to /data/DolphinPS4/jitcode.bin and the emulated MEM1 to mem1.bin, so the generated x86
// and the guest code behind it can be disassembled offline (blocks: the jit-perf map written by
// Common/JitRegister).
//
// Started by ps4_sampler_start() (DolphinNoGUI, ps4.ini profile=on); threads register
// themselves with ps4_sampler_register_thread().

#include <string>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>

// Dolphin Lab: the profile files carry the game ID (samples-RB7E54.log, jitcode-RB7E54.bin,
// mem1-RB7E54.bin), set by PlatformPS4 before the sampler starts, so one game's run never
// replaces another's.
extern "C" char ps4_profile_tag[32];
char ps4_profile_tag[32] = "";
static std::string profilePath(const char* name, const char* extension) {
    return std::string("/data/DolphinPS4/") + name + (ps4_profile_tag[0] ? "-" : "") + ps4_profile_tag + "." + extension;
}

extern "C" char __text_start[];  // defined by the OpenOrbis link.x at the start of .text
extern "C" int pthread_getthreadid_np(void);  // libkernel (FreeBSD libthr)
extern "C" void ps4_boot_trace(const char* stage);

namespace {

constexpr int kSigProf = 27;    // FreeBSD value
constexpr int kSaSiginfo = 0x40, kSaRestart = 0x0002;
constexpr int kMcontextOffset = 0x40;  // measured on hardware (see ps4_crashlog.cpp)
constexpr int kRipIndex = 20, kRspIndex = 23;
constexpr int kRbpIndex = 9;  // mc_rbp (the order in ps4_crashlog.cpp's kRegNames)
// Samples in system libraries (libkernel/libc at 0x800000000+) are attributed to the eboot
// function that called into them: the first eboot code address on the stack, tagged.
constexpr uint64_t kSystemLibs = 0x800000000ULL, kCallerTag = 1ULL << 62;
// A system-module sample whose Dolphin caller was found on the frame-pointer chain (a build with
// frame pointers, PS4_FRAME_POINTERS): the caller's ELF address, reported as "syscall from elf".
constexpr uint64_t kWaitTag = 1ULL << 61;
constexpr uintptr_t kTextWindow = 0x4000000;
constexpr int kMaxThreads = 4;
constexpr int kMaxSamples = 16384;  // per thread and window (10 s at 1 kHz fits)

struct ThreadSamples {
    std::atomic<pthread_t> thread{};
    const char* name = nullptr;
    uint64_t stack_top = 0;  // ps4_sampler_register_thread: the frame-pointer walk's limit
    uint64_t samples[kMaxSamples];
    std::atomic<int> count{0};
};

ThreadSamples g_threads[kMaxThreads];
std::atomic<int> g_thread_count{0};

void profHandler(int, siginfo_t*, void* context) {
    const pthread_t self = pthread_self();
    for (int i = 0; i < g_thread_count.load(std::memory_order_acquire); i++) {
        ThreadSamples& t = g_threads[i];
        if (t.thread.load(std::memory_order_relaxed) != self)
            continue;
        const auto* regs =
            reinterpret_cast<const uint64_t*>(static_cast<char*>(context) + kMcontextOffset);
        const int n = t.count.load(std::memory_order_relaxed);
        if (n < kMaxSamples) {
            uint64_t sample = regs[kRipIndex];
            // Inside a system module: keep the exact address (tagged). The module list at the
            // top of samples.log maps it to a module offset, which the decrypted modules' symbol
            // tables name. (Blaming "the first eboot address on the stack" picked up stale
            // values and named the wrong callers.)
            if (sample >= kSystemLibs && sample < 2 * kSystemLibs) {
                // With frame pointers the chain is exact: the first eboot return address on it is
                // the Dolphin code that waits. Every frame read stays inside this thread's stack
                // (from the interrupted rsp up to where the thread registered).
                const uintptr_t text = reinterpret_cast<uintptr_t>(__text_start);
                const uint64_t sp = regs[kRspIndex];
                const uint64_t top = t.stack_top;
                uint64_t fp = regs[kRbpIndex];
                uint64_t caller = 0;
                for (int depth = 0; depth < 16 && top; depth++) {
                    if (fp < sp || fp + 16 > top || (fp & 7))
                        break;
                    const uint64_t* frame = reinterpret_cast<const uint64_t*>(fp);
                    const uint64_t ret = frame[1];
                    if (ret >= text && ret < text + kTextWindow) {
                        caller = ret - text;
                        break;
                    }
                    if (frame[0] <= fp)
                        break;
                    fp = frame[0];
                }
                sample = caller ? (caller | kWaitTag) : (sample | kCallerTag);
            }
            t.samples[n] = sample;
            t.count.store(n + 1, std::memory_order_release);
        }
        return;
    }
}

void writeLine(int fd, const char* text) {
    size_t length = strlen(text);
    while (length > 0) {
        const ssize_t written = write(fd, text, length);
        if (written <= 0)
            return;
        text += written;
        length -= static_cast<size_t>(written);
    }
}

void noteHotJit(uint64_t address, int count);

// jitsamples-<ID>.log: every CPU-thread sample in JIT code at its exact address, per window
// ("== <s> <samples>" then "<address> <count>"), nothing dropped. The game's JIT time is spread
// over thousands of blocks; the samples log keeps only 128-byte buckets seen twice (Bully: a third
// of its JIT samples). Their code goes to jitcode.bin with the next dump.
int g_jit_fd = -1;

void writeJitSamples(const uint64_t* samples, int n, double window_start) {
    static uint64_t a[kMaxSamples];
    const uintptr_t text = reinterpret_cast<uintptr_t>(__text_start);
    int m = 0;
    for (int i = 0; i < n; i++) {
        if (samples[i] & (kCallerTag | kWaitTag))
            continue;
        if (samples[i] >= text && samples[i] < text + kTextWindow)
            continue;
        a[m++] = samples[i];
    }
    std::sort(a, a + m);
    char line[64];
    snprintf(line, sizeof(line), "== %.0f %d\n", window_start, n);
    writeLine(g_jit_fd, line);
    for (int i = 0; i < m;) {
        int j = i;
        while (j < m && a[j] == a[i])
            j++;
        snprintf(line, sizeof(line), "%llx %d\n", static_cast<unsigned long long>(a[i]), j - i);
        writeLine(g_jit_fd, line);
        noteHotJit(a[i], 1000);  // its 64 KiB chunk goes to jitcode.bin
        i = j;
    }
}

// Aggregates one thread's window: sorts the samples in place and prints the top entries.
void report(int fd, ThreadSamples& t, double window_start) {
    // Copy first: the handler keeps writing into t.samples once count is reset.
    static uint64_t s[kMaxSamples];
    const int n = std::min(t.count.load(std::memory_order_acquire), kMaxSamples);
    memcpy(s, t.samples, sizeof(uint64_t) * n);
    t.count.store(0, std::memory_order_release);
    if (n == 0)
        return;
    const uintptr_t text = reinterpret_cast<uintptr_t>(__text_start);
    if (g_jit_fd >= 0 && t.name && strcmp(t.name, "CPU thread") == 0)
        writeJitSamples(s, n, window_start);

    // Eboot code: bucket by 16 bytes (addresses relative to .text). JIT code (tagged with bit 63):
    // by 128 bytes - a game's code is spread thin over thousands of small blocks, and 16-byte
    // buckets seen once per window were all dropped (Mario Kart Wii: 80% of its JIT time).
    // Every sample is counted by kind first, before anything is dropped.
    int kind_jit = 0, kind_eboot = 0, kind_sys = 0, kind_wait = 0;
    for (int i = 0; i < n; i++) {
        if (s[i] & kCallerTag) {
            s[i] &= ~0xFULL;  // system module address (see the module list)
            kind_sys++;
            continue;
        }
        if (s[i] & kWaitTag) {
            kind_wait++;
            continue;  // a waiting Dolphin function's return address (exact)
        }
        const bool eboot = s[i] >= text && s[i] < text + kTextWindow;
        if (eboot)
            kind_eboot++;
        else
            kind_jit++;
        s[i] = eboot ? ((s[i] - text) & ~0xFULL) : (s[i] | (1ULL << 63)) & ~0x7FULL;
    }
    std::sort(s, s + n);
    struct Entry { uint64_t key; int count; };
    static Entry entries[kMaxSamples];
    int unique = 0, eboot_samples = 0;
    for (int i = 0; i < n;) {
        int j = i;
        while (j < n && s[j] == s[i])
            j++;
        entries[unique++] = {s[i], j - i};
        if (!(s[i] >> 61))
            eboot_samples += j - i;
        i = j;
    }
    std::sort(entries, entries + unique, [](const Entry& a, const Entry& b) { return a.count > b.count; });

    char line[256];
    snprintf(line, sizeof(line), "== %.0f s, %s: %d samples, %d in eboot code (%.0f%%)\n",
             window_start, t.name, n, eboot_samples, 100.0 * eboot_samples / n);
    writeLine(fd, line);
    snprintf(line, sizeof(line), "   kinds: jit %.1f%% eboot %.1f%% system %.1f%% waiting %.1f%%\n",
             100.0 * kind_jit / n, 100.0 * kind_eboot / n, 100.0 * kind_sys / n,
             100.0 * kind_wait / n);
    writeLine(fd, line);
    // Every bucket seen at least twice (up to 1500): a function spread over many 16-byte buckets
    // fell below a top-60 cut, hiding about half of a busy thread. Aggregated per function
    // offline (symbolizer, JIT block map).
    for (int i = 0; i < unique && i < 3000 && entries[i].count >= 2; i++) {
        if (entries[i].key >> 63) {
            const uint64_t address = entries[i].key & ~(1ULL << 63);
            snprintf(line, sizeof(line), "  %5.1f%% jit 0x%llx\n", 100.0 * entries[i].count / n,
                     static_cast<unsigned long long>(address));
            noteHotJit(address, entries[i].count);
        }
        else if (entries[i].key & kCallerTag)
            snprintf(line, sizeof(line), "  %5.1f%% sys 0x%llx\n",
                     100.0 * entries[i].count / n,
                     static_cast<unsigned long long>(entries[i].key & ~kCallerTag));
        else if (entries[i].key & kWaitTag)
            snprintf(line, sizeof(line), "  %5.1f%% syscall from elf 0x%llx\n",
                     100.0 * entries[i].count / n,
                     static_cast<unsigned long long>(entries[i].key & ~kWaitTag));
        else
            snprintf(line, sizeof(line), "  %5.1f%% elf 0x%llx\n", 100.0 * entries[i].count / n,
                     static_cast<unsigned long long>(entries[i].key));
        writeLine(fd, line);
    }
}

// 64 KiB chunks of JIT code sampled since the last dump (dumpJitCode).
constexpr int kMaxHotChunks = 192;
uint64_t g_hot_chunks[kMaxHotChunks];
int g_hot_chunk_count = 0;

void noteHotJit(uint64_t address, int count) {
    if (count < 3)
        return;
    const uint64_t chunk = address & ~0xFFFFULL;
    for (int i = 0; i < g_hot_chunk_count; i++) {
        if (g_hot_chunks[i] == chunk)
            return;
    }
    if (g_hot_chunk_count < kMaxHotChunks)
        g_hot_chunks[g_hot_chunk_count++] = chunk;
}

double now() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) / 1e9;
}

// Loaded modules and their segments, so "sys" samples can be mapped to module offsets.
struct ModuleSegment {
    void* address;
    uint32_t size;
    int32_t prot;
};
struct ModuleInfo {
    size_t size;
    char name[256];
    ModuleSegment segments[4];
    uint32_t segment_count;
    uint8_t fingerprint[20];
};
extern "C" int32_t sceKernelGetModuleList(int32_t* handles, size_t count, size_t* available);
extern "C" int32_t sceKernelGetModuleInfo(int32_t handle, ModuleInfo* info);

void writeModuleList(int fd) {
    int32_t handles[256];
    size_t count = 0;
    static size_t s_listed = 0;  // relisted when modules get loaded (e.g. RADV's GnmDriver)
    if (sceKernelGetModuleList(handles, 256, &count) != 0 || count == s_listed)
        return;
    s_listed = count;
    char line[512];
    for (size_t m = 0; m < count && m < 256; m++) {
        ModuleInfo info;
        memset(&info, 0, sizeof(info));
        info.size = sizeof(info);
        if (sceKernelGetModuleInfo(handles[m], &info) != 0)
            continue;
        int len = snprintf(line, sizeof(line), "module %s", info.name);
        for (uint32_t g = 0; g < info.segment_count && g < 4; g++)
            len += snprintf(line + len, sizeof(line) - len, " seg %p+0x%x/%d",
                            info.segments[g].address, info.segments[g].size, info.segments[g].prot);
        snprintf(line + len, sizeof(line) - len, "\n");
        writeLine(fd, line);
    }
}

}  // namespace

extern "C" int32_t sceKernelQueryMemoryProtection(void* address, void** start, void** end,
                                                  uint32_t* protection);
// Modules loaded into this process that aren't the app or Sony's system libraries: GoldHEN
// plugins and other injected code (OrbisNet, cheat menus, ...), which can hook the functions the
// app relies on. "<when>: no injected modules" or "<when>: injected modules: A B ..." in the boot
// trace, every time (not only when profiling).
extern "C" void ps4_log_injected_modules(const char* when) {
    int32_t handles[256];
    size_t count = 0;
    if (sceKernelGetModuleList(handles, 256, &count) != 0)
        return;
    char line[1024];
    int len = snprintf(line, sizeof(line), "%s: ", when);
    int injected = 0;
    for (size_t m = 0; m < count && m < 256; m++) {
        ModuleInfo info;
        memset(&info, 0, sizeof(info));
        info.size = sizeof(info);
        if (sceKernelGetModuleInfo(handles[m], &info) != 0)
            continue;
        const char* name = info.name;
        if (strcmp(name, "eboot.bin") == 0 || strncmp(name, "libSce", 6) == 0 ||
            strncmp(name, "libkernel", 9) == 0 || strcmp(name, "libc.sprx") == 0 ||
            strcmp(name, "libc.prx") == 0)
            continue;
        if (len < static_cast<int>(sizeof(line)) - 80)
            len += snprintf(line + len, sizeof(line) - len, "%s%s", injected ? " " : "injected modules: ", name);
        injected++;
    }
    if (!injected)
        snprintf(line + len, sizeof(line) - len, "no injected modules (%zu system modules)", count);
    ps4_boot_trace(line);
}

// Emulated MEM1 (set by Core/HW/Memmap.cpp), dumped with the JIT code.
extern "C" void* ps4_profile_guest_ram;
extern "C" uint32_t ps4_profile_guest_ram_size;
extern "C" {
void* ps4_profile_guest_ram = nullptr;
uint32_t ps4_profile_guest_ram_size = 0;
}

namespace {

bool isReadable(uint64_t address, uint64_t size) {
    void* start = nullptr;
    void* end = nullptr;
    uint32_t protection = 0;
    return sceKernelQueryMemoryProtection(reinterpret_cast<void*>(address), &start, &end,
                                          &protection) == 0 &&
           (protection & 1) && address + size <= reinterpret_cast<uintptr_t>(end);
}

// The game is stopping (ps4_sampler_shutdown): no more snapshots of its memory, which is about to
// be released. g_sampler_dumping is set before g_sampler_stopping is checked, and the shutdown
// sets g_sampler_stopping before it waits on g_sampler_dumping, so a snapshot either sees the stop
// or is waited for (a copy of MEM1 during Quit Game crashed the app in v50.32).
std::atomic<bool> g_sampler_stopping{false};
std::atomic<bool> g_sampler_dumping{false};

// jitcode.bin: records of {u64 address, u64 size, bytes}. Copied through a buffer first so the
// kernel never reads JIT memory for the file write.
void dumpJitCode() {
    const int fd = open(profilePath("jitcode", "bin").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd >= 0) {
        static uint8_t buffer[0x10000];
        for (int i = 0; i < g_hot_chunk_count; i++) {
            if (!isReadable(g_hot_chunks[i], sizeof(buffer)))
                continue;
            memcpy(buffer, reinterpret_cast<const void*>(g_hot_chunks[i]), sizeof(buffer));
            const uint64_t header[2] = {g_hot_chunks[i], sizeof(buffer)};
            write(fd, header, sizeof(header));
            write(fd, buffer, sizeof(buffer));
        }
        close(fd);
    }
    g_hot_chunk_count = 0;
    if (ps4_profile_guest_ram && ps4_profile_guest_ram_size) {
        const int ram = open(profilePath("mem1", "bin").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
        if (ram >= 0) {
            static uint8_t copy[0x100000];
            for (uint32_t offset = 0; offset < ps4_profile_guest_ram_size; offset += sizeof(copy)) {
                if (g_sampler_stopping.load())
                    break;
                const uint32_t size =
                    std::min<uint32_t>(sizeof(copy), ps4_profile_guest_ram_size - offset);
                memcpy(copy, static_cast<const uint8_t*>(ps4_profile_guest_ram) + offset, size);
                write(ram, copy, size);
            }
            close(ram);
        }
    }
}

std::atomic<bool> g_sampler_on{false};

void* samplerThread(void*) {
    const int fd = open(profilePath("samples", "log").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0)
        return nullptr;
    writeModuleList(fd);
    g_jit_fd = open(profilePath("jitsamples", "log").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    const double start = now();
    double window_start = start, last_dump = start;
    const timespec period = {0, 1000000}, paused = {0, 100000000};
    for (;;) {
        if (g_sampler_stopping.load())
            return nullptr;
        // Profiler switched off in the menus: no signals, no new windows until it is back on.
        if (!g_sampler_on.load(std::memory_order_relaxed)) {
            nanosleep(&paused, nullptr);
            window_start = now();
            continue;
        }
        nanosleep(&period, nullptr);
        const int threads = g_thread_count.load(std::memory_order_acquire);
        for (int i = 0; i < threads; i++)
            pthread_kill(g_threads[i].thread.load(std::memory_order_relaxed), kSigProf);
        if (now() - window_start >= 10.0) {
            writeModuleList(fd);
            for (int i = 0; i < threads; i++)
                report(fd, g_threads[i], window_start - start);
            window_start = now();
            if (window_start - last_dump >= 60.0) {
                g_sampler_dumping.store(true);
                if (!g_sampler_stopping.load())
                    dumpJitCode();
                g_sampler_dumping.store(false);
                last_dump = window_start = now();
                writeLine(fd, "(jitcode.bin and mem1.bin updated)\n");
                if (g_jit_fd >= 0)
                    writeLine(g_jit_fd, "== dump\n");  // jitcode.bin matches the windows before it
            }
        }
    }
    return nullptr;
}

}  // namespace

// ---------------------------------------------------------------------------------------------
// Hang dumps: every thread that matters registers here (ps4_watch_thread, also done by
// ps4_sampler_register_thread). ps4_dump_thread_stacks() signals each one; the handler records
// its instruction pointer and every eboot code address on its stack (return addresses, newest
// first). Used by DolphinNoGUI's watchdog when emulation stops advancing.
namespace {
constexpr int kSigDump = 30;  // SIGUSR1 (FreeBSD)
constexpr int kMaxWatched = 16, kMaxFrames = 48;

struct WatchedThread {
    std::atomic<pthread_t> thread{};
    char name[32] = {};  // copied: some callers pass temporaries
    // Highest stack address the dump may read: the thread's stack position when it registered
    // (plus its caller's frame). Reading a fixed amount above rsp ran off the top of small thread
    // stacks (the Wiimote scanner's) and crashed the app in the middle of a hang dump.
    uintptr_t stack_limit = 0;
    int tid = 0;  // kernel thread id (pthread_getthreadid_np): mutex objects record their owner's
    uint64_t rip = 0;
    uint64_t frames[kMaxFrames];
    int frame_count = 0;
    // Blocked in _umtx_op (the kernel's wait for mutexes, condition variables, semaphores): its
    // arguments - object, operation, value, second object (condition variable waits: the mutex) -
    // and the first 16 bytes of both objects (a FreeBSD mutex starts with its owner's thread id).
    bool in_umtx = false;
    uint64_t umtx_obj = 0, umtx_op = 0, umtx_val = 0, umtx_obj2 = 0;
    uint32_t umtx_words[4] = {}, umtx_words2[4] = {};
    std::atomic<int> done{0};
};
WatchedThread g_watched[kMaxWatched];
std::atomic<int> g_watched_count{0};

void dumpHandler(int, siginfo_t*, void* context) {
    const pthread_t self = pthread_self();
    const uintptr_t text = reinterpret_cast<uintptr_t>(__text_start);
    for (int i = 0; i < g_watched_count.load(std::memory_order_acquire); i++) {
        WatchedThread& t = g_watched[i];
        if (t.thread.load(std::memory_order_relaxed) != self)
            continue;
        const auto* regs =
            reinterpret_cast<const uint64_t*>(static_cast<char*>(context) + kMcontextOffset);
        t.rip = regs[kRipIndex];
        // libkernel's _umtx_op stub: "mov $0x1c6, %rax; mov %rcx, %r10; syscall" (12 bytes), the
        // interrupted thread sits right after the syscall. FreeBSD mcontext: rdi 1, rsi 2, rdx 3,
        // r10 10. Only then are the argument registers known to be the wait's.
        t.in_umtx = false;
        if (t.rip >= kSystemLibs && t.rip < 2 * kSystemLibs) {
            const auto* code = reinterpret_cast<const uint8_t*>(t.rip - 12);
            static const uint8_t kUmtxStub[12] = {0x48, 0xc7, 0xc0, 0xc6, 0x01, 0x00,
                                                  0x00, 0x49, 0x89, 0xca, 0x0f, 0x05};
            if (memcmp(code, kUmtxStub, sizeof(kUmtxStub)) == 0) {
                // Registers only: the objects are read by the dumping thread, after checking that
                // they are mapped (a register that wasn't a pointer crashed v02.37 here).
                t.in_umtx = true;
                t.umtx_obj = regs[1];
                t.umtx_op = regs[2];
                t.umtx_val = regs[3];
                t.umtx_obj2 = regs[10];
            }
        }
        // Only scan a stack that is plausibly this registration's: a thread that registered and
        // exited can leave its pthread handle to a new thread, whose stack is elsewhere (a v02.34
        // hang dump crashed scanning from one thread's rsp to another's stack limit).
        const uint64_t rsp = regs[kRspIndex];
        const bool same_thread = pthread_getthreadid_np() == t.tid;
        const bool sane = t.stack_limit > rsp && t.stack_limit - rsp <= (1u << 20);
        const auto* stack = reinterpret_cast<const uint64_t*>(rsp);
        const auto* limit =
            reinterpret_cast<const uint64_t*>(same_thread && sane ? t.stack_limit : rsp);
        int n = 0;
        for (const uint64_t* p = stack; p < limit && n < kMaxFrames; p++) {
            if (*p >= text && *p < text + kTextWindow)
                t.frames[n++] = *p - text;
        }
        t.frame_count = n;
        t.done.store(1, std::memory_order_release);
        return;
    }
}

void installDumpHandler() {
    static std::atomic<bool> installed{false};
    if (installed.exchange(true))
        return;
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    void (*handler)(int, siginfo_t*, void*) = dumpHandler;
    memcpy(&action, &handler, sizeof(handler));
    action.sa_flags = kSaSiginfo | kSaRestart;
    sigemptyset(&action.sa_mask);
    sigaction(kSigDump, &action, nullptr);
}
}  // namespace

extern "C" void ps4_heap_private_arena(const char* name);  // ps4_runtime.cpp

extern "C" void ps4_watch_thread(const char* name) {
    installDumpHandler();
    ps4_heap_private_arena(name);
    const pthread_t self = pthread_self();
    for (int i = 0; i < std::min(g_watched_count.load(), kMaxWatched); i++) {
        if (g_watched[i].thread.load() == self)
            return;  // already watched (e.g. registered for sampling and named)
    }
    const int index = g_watched_count.fetch_add(1);
    if (index >= kMaxWatched)
        return;
    snprintf(g_watched[index].name, sizeof(g_watched[index].name), "%s", name ? name : "?");
    // Up to and including this function's own return address (frame + 16): threads that register
    // first thing (e.g. the analytics reporter) sit within 256 bytes of their stack's top, and a
    // larger margin read past it. Where a thread is stuck lies deeper than this anyway.
    g_watched[index].stack_limit = reinterpret_cast<uintptr_t>(__builtin_frame_address(0)) + 16;
    g_watched[index].tid = pthread_getthreadid_np();
    g_watched[index].thread.store(self);
}

extern "C" int32_t sceKernelQueryMemoryProtection(void* address, void** start, void** end,
                                                  uint32_t* protection);

// Copies 16 bytes at `address` if they lie in readable memory (else leaves zeros).
static void readIfMapped(uint64_t address, uint32_t (&words)[4]) {
    memset(words, 0, sizeof(words));
    void* start = nullptr;
    void* end = nullptr;
    uint32_t protection = 0;
    if (address < 0x10000 ||
        sceKernelQueryMemoryProtection(reinterpret_cast<void*>(address), &start, &end,
                                       &protection) != 0 ||
        !(protection & 1) || address + 16 > reinterpret_cast<uintptr_t>(end))
        return;
    memcpy(words, reinterpret_cast<const void*>(address), sizeof(words));
}

// Writes every watched thread's stack to `path` (appending), headed by `reason`.
extern "C" void ps4_dump_thread_stacks(const char* path, const char* reason) {
    const int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd < 0)
        return;
    char line[256];
    snprintf(line, sizeof(line), "==== %s (eboot addresses relative to .text, symbolize with "
                                 "llvm-symbolizer --obj=<oelf>)\n", reason);
    writeLine(fd, line);
    const uintptr_t text = reinterpret_cast<uintptr_t>(__text_start);
    const int count = std::min(g_watched_count.load(std::memory_order_acquire), kMaxWatched);
    for (int i = 0; i < count; i++) {
        WatchedThread& t = g_watched[i];
        t.done.store(0);
        if (pthread_kill(t.thread.load(), kSigDump) != 0) {
            snprintf(line, sizeof(line), "-- %s: signal failed (thread gone?)\n", t.name);
            writeLine(fd, line);
            continue;
        }
        const timespec pause = {0, 1000000};
        for (int w = 0; w < 200 && !t.done.load(std::memory_order_acquire); w++)
            nanosleep(&pause, nullptr);
        if (!t.done.load(std::memory_order_acquire)) {
            snprintf(line, sizeof(line), "-- %s: no answer (signals blocked?)\n", t.name);
            writeLine(fd, line);
            continue;
        }
        const bool in_eboot = t.rip >= text && t.rip < text + kTextWindow;
        snprintf(line, sizeof(line), "-- %s (thread id %d): rip %s0x%llx\n", t.name, t.tid,
                 in_eboot ? "elf " : "(system/JIT) ",
                 static_cast<unsigned long long>(in_eboot ? t.rip - text : t.rip));
        writeLine(fd, line);
        if (t.in_umtx) {
            readIfMapped(t.umtx_obj, t.umtx_words);
            readIfMapped(t.umtx_obj2, t.umtx_words2);
            snprintf(line, sizeof(line),
                     "   blocked in _umtx_op(obj %#llx, op %llu, val %#llx, obj2 %#llx); obj: %08x "
                     "%08x %08x %08x; obj2: %08x %08x %08x %08x\n",
                     static_cast<unsigned long long>(t.umtx_obj),
                     static_cast<unsigned long long>(t.umtx_op),
                     static_cast<unsigned long long>(t.umtx_val),
                     static_cast<unsigned long long>(t.umtx_obj2), t.umtx_words[0], t.umtx_words[1],
                     t.umtx_words[2], t.umtx_words[3], t.umtx_words2[0], t.umtx_words2[1],
                     t.umtx_words2[2], t.umtx_words2[3]);
            writeLine(fd, line);
        }
        writeLine(fd, "   stack:");
        for (int f = 0; f < t.frame_count; f++) {
            snprintf(line, sizeof(line), " 0x%llx", static_cast<unsigned long long>(t.frames[f]));
            writeLine(fd, line);
        }
        writeLine(fd, "\n");
    }
    close(fd);
}

// Per-thread CPU time for the monitor: busy threads (CPU thread 0, video thread 1) read their own
// CPU clock now and then; the monitor divides the growth by wall time. Shows how close a thread
// is to its limit and whether something else shares its core (the sampler can't see that).
namespace {
constexpr clockid_t kThreadCpuClock = 14;  // FreeBSD CLOCK_THREAD_CPUTIME_ID
std::atomic<uint64_t> g_thread_cpu_ns[2];
}  // namespace

extern "C" void ps4_thread_cpu_sample(int slot) {
    timespec ts;
    if (slot < 0 || slot > 1 || clock_gettime(kThreadCpuClock, &ts) != 0)
        return;
    g_thread_cpu_ns[slot].store(static_cast<uint64_t>(ts.tv_sec) * 1000000000ull +
                                    static_cast<uint64_t>(ts.tv_nsec),
                                std::memory_order_relaxed);
}

// Wait-time counters for the monitor (ns): 0 CPU thread waiting for the GPU thread (FlushGpu),
// 1 GPU loop sleeping for lack of work, 2 video thread waiting for the Vulkan recording thread,
// 3 vkWaitForFences.
namespace {
std::atomic<long long> g_wait_ns[6];  // 4: video-thread pipeline compile ns, 5: their count
}  // namespace

extern "C" void ps4_wait_add(int slot, long long ns) {
    if (slot >= 0 && slot < 6 && ns > 0)
        g_wait_ns[slot].fetch_add(ns, std::memory_order_relaxed);
}

extern "C" long long ps4_wait_total(int slot) {
    return slot >= 0 && slot < 6 ? g_wait_ns[slot].load(std::memory_order_relaxed) : 0;
}

extern "C" double ps4_thread_cpu_seconds(int slot) {
    if (slot < 0 || slot > 1)
        return 0;
    return g_thread_cpu_ns[slot].load(std::memory_order_relaxed) / 1e9;
}

extern "C" void ps4_sampler_register_thread(const char* name) {
    ps4_watch_thread(name);
    const int index = g_thread_count.load();
    if (index >= kMaxThreads)
        return;
    g_threads[index].name = name;
    // The stack above this point belongs to the thread: the frame-pointer walk stays below it.
    uint64_t rsp;
    asm volatile("mov %%rsp, %0" : "=r"(rsp));
    g_threads[index].stack_top = rsp + 0x400;
    g_threads[index].thread.store(pthread_self());
    g_thread_count.store(index + 1, std::memory_order_release);
}

extern "C" void ps4_sampler_start() {
    static std::atomic<bool> s_started{false};
    g_sampler_on.store(true);
    if (s_started.exchange(true))
        return;
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    void (*handler)(int, siginfo_t*, void*) = profHandler;
    memcpy(&action, &handler, sizeof(handler));  // the handler union's member names differ
    action.sa_flags = kSaSiginfo | kSaRestart;
    sigemptyset(&action.sa_mask);
    sigaction(kSigProf, &action, nullptr);

    pthread_t thread;
    if (pthread_create(&thread, nullptr, samplerThread, nullptr) == 0)
        ps4_boot_trace(("sampler: started, writing " + profilePath("samples", "log") + " every 10 s").c_str());
}

// The game is stopping (MainNoGUI's core state callback, PlatformPS4's exit): the sampler stops
// for good, after a snapshot of the game's memory in progress.
extern "C" void ps4_sampler_shutdown() {
    g_sampler_stopping.store(true);
    g_sampler_on.store(false);
    for (int i = 0; i < 300 && g_sampler_dumping.load(); i++)
        usleep(10000);
}

// The menus' Profiler switch: starts the sampler the first time, then pauses / resumes it.
extern "C" void ps4_sampler_set_enabled(int on) {
    if (on)
        ps4_sampler_start();
    else if (g_sampler_on.exchange(false))
        ps4_boot_trace("sampler: paused");
}
