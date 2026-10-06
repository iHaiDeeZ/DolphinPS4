// PS4 runtime fixes, based on love-ps4 (src/common/ps4_heap.cpp and ps4.cpp), which runs on the
// test console:
//
// - The OpenOrbis libc creates its heap on the first malloc by mapping 2.5 GiB of system
//   flexible memory; that fails on retail consoles and malloc then crashes at address 0x38,
//   before main(). The malloc family is redirected here with the linker's --wrap
//   (toolchain/ps4-love-style.cmake).
// - The heap is dlmalloc (port/ps4_dlmalloc.c) over a block of memory mapped here. Sony's
//   sceLibcMspace (what love-ps4 uses) stopped returning memory in Dolphin's static
//   initialisation after ~800 small allocations; dlmalloc also checks for corruption and
//   foreign frees, which are logged with the caller.
// - libc++abi runs thread_local destructors through __cxa_thread_atexit_impl, which the PS4
//   libc lacks (and create-fself refuses unresolved imports).

#include <pthread.h>
#include <sched.h>
#include <errno.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#include <atomic>
#include <sys/types.h>

// Declared by hand: the toolchain headers give these the wrong (or no) prototypes.
extern "C" {
int32_t sceKernelDebugOutText(int32_t channel, const char* fmt, ...);
int32_t sceKernelAvailableFlexibleMemorySize(size_t* size);
int32_t sceKernelReserveVirtualRange(void** addr, size_t len, int32_t flags, size_t alignment);
int32_t sceKernelMunmap(void* addr, size_t len);
int32_t sceKernelMapNamedFlexibleMemory(void** addr, size_t len, int32_t prot, int32_t flags, const char* name);
int32_t sceKernelMapNamedSystemFlexibleMemory(void** addr, size_t len, int32_t prot, int32_t flags,
                                              const char* name);
size_t sceKernelGetDirectMemorySize(void);
int32_t sceKernelAllocateDirectMemory(off_t start, off_t end, size_t len, size_t align, int32_t type,
                                      off_t* physOut);
int32_t sceKernelMapDirectMemory(void** addr, size_t len, int32_t prot, int32_t flags, off_t phys,
                                 size_t align);
int32_t sceKernelMprotect(const void* addr, size_t len, int32_t prot);
int32_t sceKernelJitCreateSharedMemory(const char* name, size_t len, int32_t max_prot, int32_t* fd);
int32_t sceKernelJitCreateAliasOfSharedMemory(int32_t fd, int32_t max_prot, int32_t* alias_fd);
int32_t sceKernelClose(int32_t fd);

// dlmalloc mspace API (port/ps4_dlmalloc.c).
typedef void* mspace;
mspace create_mspace_with_base(void* base, size_t capacity, int locked);
void* mspace_malloc(mspace msp, size_t bytes);
void mspace_free(mspace msp, void* mem);
void* mspace_calloc(mspace msp, size_t n_elements, size_t elem_size);
void* mspace_realloc(mspace msp, void* mem, size_t newsize);
void* mspace_memalign(mspace msp, size_t alignment, size_t bytes);
size_t mspace_usable_size(const void* mem);
size_t mspace_footprint(mspace msp);
size_t mspace_max_footprint(mspace msp);
void* memcpy(void* dst, const void* src, size_t n);

// port/ps4_crashlog.cpp (weak: a program may link without it).
__attribute__((weak)) void ps4_boot_trace(const char* stage);
int ps4_heap_ok(void* msp);  // port/ps4_dlmalloc.c

extern char __text_start[];  // OpenOrbis link.x: start of .text (ELF address 0)
}

namespace {

const size_t MB = 1024 * 1024;
const size_t PAGE = 16 * 1024;
// Regular flexible memory left for Piglet (OpenGL ES) when the heap has to come from there.
const size_t RESERVE_FOR_SYSTEM = 320 * MB;
const int32_t PROT_CPU_RW = 0x3;
const int32_t MAP_FIXED_FLAG = 0x10;

mspace g_heap = nullptr;
const char* g_heapPool = "none";
uintptr_t g_heapBase = 0;
size_t g_heapSize = 0;

// sceKernelDebugOutText doesn't format its arguments; vsnprintf doesn't allocate.
__attribute__((format(printf, 1, 2))) void heapLog(const char* fmt, ...) {
    char line[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    sceKernelDebugOutText(0, line);
    if (ps4_boot_trace)
        ps4_boot_trace(line);
}

unsigned long long elf(const void* address) {
    return static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(address) -
                                           reinterpret_cast<uintptr_t>(__text_start));
}

// Logs the code addresses on the current stack (no frame pointers in release builds).
void logStack() {
    const uintptr_t base = reinterpret_cast<uintptr_t>(__text_start);
    const auto* stack = static_cast<const uintptr_t*>(__builtin_frame_address(0));
    int found = 0;
    for (int i = 0; i < 512 && found < 16; i++) {
        if (stack[i] >= base && stack[i] < base + 0x1000000) {
            heapLog("[dolphin] heap:   stack elf 0x%llx\n", static_cast<unsigned long long>(stack[i] - base));
            found++;
        }
    }
}

mspace createMspace(const char* pool, void* base, size_t size) {
    mspace msp = create_mspace_with_base(base, size, 1);
    if (!msp) {
        heapLog("[dolphin] heap: create_mspace_with_base on %zu MiB of %s failed\n", size / MB, pool);
        return nullptr;
    }
    void* test = mspace_malloc(msp, 4096);
    if (!test) {
        heapLog("[dolphin] heap: %zu MiB of %s at %p: self-test allocation failed\n", size / MB, pool, base);
        return nullptr;
    }
    mspace_free(msp, test);
    g_heapPool = pool;
    g_heapBase = reinterpret_cast<uintptr_t>(base);
    g_heapSize = size;
    heapLog("[dolphin] heap: dlmalloc on %zu MiB of %s at %p\n", size / MB, pool, base);
    return msp;
}

// The PS4 kernel library allocates its own objects (pthread attributes, ...) at 0x200000000,
// where a kernel-placed reservation of ours also lands; those allocations wiped the heap's
// control block. Ask for an address well above that instead.
void* reserveAwayFromKernel(size_t size) {
    const uintptr_t hints[] = {0x1000000000ull, 0x800000000ull, 0x600000000ull};
    for (uintptr_t hint : hints) {
        void* address = reinterpret_cast<void*>(hint);
        if (sceKernelReserveVirtualRange(&address, size, 0, PAGE) == 0) {
            if (reinterpret_cast<uintptr_t>(address) >= 0x400000000ull)
                return address;
            heapLog("[dolphin] heap: reservation hint %p gave %p, trying another\n", reinterpret_cast<void*>(hint),
                    address);
        }
    }
    return nullptr;
}

mspace mapAndCreate(bool systemPool, size_t size) {
    // Reserve one extra page in front of the heap and leave it inaccessible: a stray write
    // just before the heap's control block then faults where it happens (see crash.log).
    void* guard = reserveAwayFromKernel(size + PAGE);
    if (!guard)
        return nullptr;
    void* base = static_cast<char*>(guard) + PAGE;
    int32_t ret = systemPool
                      ? sceKernelMapNamedSystemFlexibleMemory(&base, size, PROT_CPU_RW, MAP_FIXED_FLAG, "dolphin heap")
                      : sceKernelMapNamedFlexibleMemory(&base, size, PROT_CPU_RW, MAP_FIXED_FLAG, "dolphin heap");
    if (ret != 0) {
        heapLog("[dolphin] heap: mapping %zu MiB of %s flexible memory failed (0x%x)\n", size / MB,
                systemPool ? "system" : "regular", ret);
        return nullptr;  // the leaked VA reservation doesn't matter in a 47-bit address space
    }
    return createMspace(systemPool ? "system flexible memory" : "flexible memory", base, size);
}

// Last resort (PSChrome's heap): direct memory.
mspace createDirectHeap(size_t size) {
    off_t phys = 0;
    if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, 2 * MB, 0, &phys) != 0)
        return nullptr;
    void* base = nullptr;
    if (sceKernelMapDirectMemory(&base, size, PROT_CPU_RW, 0, phys, 2 * MB) != 0)
        return nullptr;
    return createMspace("direct memory", base, size);
}

mspace createHeap() {
    size_t available = 0;
    int32_t ret = sceKernelAvailableFlexibleMemorySize(&available);
    heapLog("[dolphin] heap: flexible memory available %zu MiB (0x%x)\n", available / MB, ret);
    // Where does the kernel library put its own objects? (8 bytes reserved even if the
    // headers' pthread_mutexattr_t is the 4-byte musl one.)
    void* attr[2] = {nullptr, nullptr};
    if (pthread_mutexattr_init(reinterpret_cast<pthread_mutexattr_t*>(attr)) == 0) {
        heapLog("[dolphin] heap: kernel pthread objects live around %p\n", attr[0]);
        pthread_mutexattr_destroy(reinterpret_cast<pthread_mutexattr_t*>(attr));
    }
    // Preferred: the system flexible memory pool, leaving regular flexible memory to Piglet.
    // Not all of it: the kernel's own objects ("ScePthread internal memory") and the system libc
    // heap that Sony modules (Piglet's shader compiler) grow on demand come from the same pool.
    // With a 1 GiB heap, compiling Dolphin's larger shaders ran the system out of memory.
    const size_t systemSizes[] = {512 * MB, 384 * MB, 256 * MB, 192 * MB, 128 * MB};
    for (size_t size : systemSizes) {
        if (mspace msp = mapAndCreate(true, size))
            return msp;
    }
    size_t size = 0;
    if (ret == 0 && available > RESERVE_FOR_SYSTEM + 32 * MB)
        size = (available - RESERVE_FOR_SYSTEM) & ~(PAGE - 1);
    for (; size >= 32 * MB; size = (size / 2) & ~(PAGE - 1)) {
        if (mspace msp = mapAndCreate(false, size))
            return msp;
    }
    const size_t directSizes[] = {256 * MB, 128 * MB};
    for (size_t direct : directSizes) {
        if (mspace msp = createDirectHeap(direct))
            return msp;
    }
    heapLog("[dolphin] heap: could not create a heap, out of memory\n");
    return nullptr;
}

bool g_creatingHeap = false;

inline mspace getHeap() {
    // The first allocation happens in a static constructor, before any threads exist. While the
    // heap is being created, nested allocations (if a kernel call allocates) just fail.
    if (g_heap == nullptr && !g_creatingHeap) {
        g_creatingHeap = true;
        g_heap = createHeap();
        g_creatingHeap = false;
    }
    return g_heap;
}

// Overflow heap: direct memory, mapped the first time the main heap can't serve a request.
// Spider-Man 2 fills most of the 512 MiB main heap; a save state then needed one 99 MiB block
// (148 MiB in Mario Kart: Double Dash!!), the allocation failed and the app crashed. Direct
// memory is a separate 4.5 GiB pool (the GPU's); with FOOTERS, free and realloc find this heap
// from the chunk itself.
mspace g_overflow = nullptr;
uintptr_t g_overflowBase = 0;
size_t g_overflowSize = 0;
bool g_overflowTried = false;

mspace overflowHeap() {
    if (mspace msp = __atomic_load_n(&g_overflow, __ATOMIC_ACQUIRE))
        return msp;
    if (__atomic_exchange_n(&g_overflowTried, true, __ATOMIC_ACQ_REL))
        return __atomic_load_n(&g_overflow, __ATOMIC_ACQUIRE);  // another thread is (or was) at it
    const size_t sizes[] = {512 * MB, 384 * MB, 256 * MB, 128 * MB};
    for (size_t size : sizes) {
        off_t phys = 0;
        if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), size, 2 * MB, 0, &phys) != 0)
            continue;
        // A hint well above 0x200000000, where the kernel library puts its own objects.
        void* base = reinterpret_cast<void*>(0x1800000000ull);
        const int32_t ret = sceKernelMapDirectMemory(&base, size, PROT_CPU_RW, 0, phys, 2 * MB);
        if (ret != 0 || reinterpret_cast<uintptr_t>(base) < 0x400000000ull) {
            heapLog("[dolphin] heap: overflow heap: mapping %zu MiB of direct memory failed (0x%x, %p)\n",
                    size / MB, ret, base);
            continue;
        }
        mspace msp = create_mspace_with_base(base, size, 1);
        if (!msp)
            continue;
        g_overflowBase = reinterpret_cast<uintptr_t>(base);
        g_overflowSize = size;
        __atomic_store_n(&g_overflow, msp, __ATOMIC_RELEASE);
        heapLog("[dolphin] heap: main heap full: overflow heap of %zu MiB of direct memory at %p\n", size / MB,
                base);
        return msp;
    }
    heapLog("[dolphin] heap: main heap full and no direct memory for an overflow heap\n");
    return nullptr;
}

bool ownsPointer(const void* p) {
    const uintptr_t address = reinterpret_cast<uintptr_t>(p);
    return (address >= g_heapBase && address < g_heapBase + g_heapSize) ||
           (address >= g_overflowBase && address < g_overflowBase + g_overflowSize);
}

// The operation in progress, for error reports (thread-local: allocations happen on any thread).
// initial-exec: the executable's own TLS, so access never goes through __tls_get_addr.
__attribute__((tls_model("initial-exec"))) thread_local const char* t_op = "?";
__attribute__((tls_model("initial-exec"))) thread_local const void* t_caller = nullptr;
int g_errors = 0;

// Per-thread arenas. One locked heap made Dolphin's busy threads (CPU, video, Vulkan submission,
// shader compilers) contend: dlmalloc's spin lock then yields to the kernel, and in Ultimate
// Spider-Man the video thread spent ~9% (likely more) of its time there. Each of those threads
// gets a private dlmalloc arena carved out of the main heap; with FOOTERS every chunk records
// its arena, so free/realloc from any thread return memory to the right one. A full arena falls
// back to the main heap.
constexpr size_t ARENA_SIZE = 8 * MB;
constexpr int MAX_ARENAS = 12;
__attribute__((tls_model("initial-exec"))) thread_local mspace t_arena = nullptr;
std::atomic<int> g_arenaCount{0};
// Arenas of threads that have exited, for the next busy thread (the audio thread is recreated
// every time the in-game menu closes, the shader compilers when their count changes): without
// reuse each restart took a fresh 8 MiB until MAX_ARENAS ran out.
mspace g_freeArenas[MAX_ARENAS];
int g_freeArenaCount = 0;
std::atomic_flag g_freeArenaLock = ATOMIC_FLAG_INIT;
pthread_key_t g_arenaKey;
std::atomic<bool> g_arenaKeyReady{false};

void lockFreeArenas() {
    while (g_freeArenaLock.test_and_set(std::memory_order_acquire))
        sched_yield();
}
void unlockFreeArenas() { g_freeArenaLock.clear(std::memory_order_release); }

// Thread exit (pthread key destructor): its arena goes back on the free list. Chunks other
// threads still hold stay valid - FOOTERS returns them to this arena when freed.
void releaseArena(void* arena) {
    if (!arena)
        return;
    lockFreeArenas();
    if (g_freeArenaCount < MAX_ARENAS)
        g_freeArenas[g_freeArenaCount++] = static_cast<mspace>(arena);
    unlockFreeArenas();
}

// Checks the heap's control block before every operation; the first time it is found
// overwritten, logs when (operation number, current and previous caller) and what it now holds.
unsigned long long g_ops = 0;
const char* g_prevOp = "none";
const void* g_prevCaller = nullptr;
bool g_heapBroken = false;

void checkHeap(const char* op, const void* caller) {
    g_ops++;
    if (g_heap && !g_heapBroken && !ps4_heap_ok(g_heap)) {
        g_heapBroken = true;
        heapLog("[dolphin] heap: CONTROL BLOCK OVERWRITTEN, noticed at operation #%llu (%s from elf 0x%llx); "
                "previous operation %s from elf 0x%llx\n",
                g_ops, op, elf(caller), g_prevOp, elf(g_prevCaller));
        const auto* words = reinterpret_cast<const unsigned long long*>(g_heapBase);
        for (int i = 0; i < 16; i += 4)
            heapLog("[dolphin] heap:   +0x%02x: %016llx %016llx %016llx %016llx\n", i * 8, words[i], words[i + 1],
                    words[i + 2], words[i + 3]);
        logStack();
    }
    g_prevOp = op;
    g_prevCaller = caller;
}

void reportFailure(const char* what, size_t size) {
    if (g_errors++ < 8) {
        heapLog("[dolphin] heap: %s(%zu) failed, caller elf 0x%llx\n", what, size, elf(t_caller));
        logStack();
    }
}

struct ThreadDtor {
    void (*dtor)(void*);
    void* obj;
    ThreadDtor* next;
};
pthread_key_t g_threadDtorKey;
pthread_once_t g_threadDtorOnce = PTHREAD_ONCE_INIT;

void runThreadDtors(void* p) {
    auto* head = static_cast<ThreadDtor*>(p);
    while (head) {
        ThreadDtor* next = head->next;
        head->dtor(head->obj);
        free(head);
        head = next;
    }
}

void createThreadDtorKey() { pthread_key_create(&g_threadDtorKey, runThreadDtors); }

}  // namespace

extern "C" {

// dlmalloc found a corrupted heap (corruption = 1) or was asked to free/realloc something it
// didn't allocate (corruption = 0).
void ps4_heap_error(void* msp, void* chunk, int corruption) {
    heapLog("[dolphin] heap: %s during %s from elf 0x%llx (chunk %p)\n",
            corruption ? "CORRUPTION DETECTED" : "invalid pointer", t_op, elf(t_caller), chunk);
    logStack();
    if (corruption)
        abort();
}

void* __wrap_malloc(size_t size) {
    t_op = "malloc";
    t_caller = __builtin_return_address(0);
    checkHeap(t_op, t_caller);
    void* p = t_arena ? mspace_malloc(t_arena, size) : nullptr;
    if (!p)
        p = mspace_malloc(getHeap(), size);
    if (!p)
        if (mspace overflow = overflowHeap())
            p = mspace_malloc(overflow, size);
    if (!p)
        reportFailure("malloc", size);
    return p;
}

void __wrap_free(void* ptr) {
    if (!ptr)
        return;
    t_op = "free";
    t_caller = __builtin_return_address(0);
    checkHeap(t_op, t_caller);
    if (!ownsPointer(ptr)) {
        if (g_errors++ < 8) {
            heapLog("[dolphin] heap: free(%p) of memory not from this heap, caller elf 0x%llx (ignored)\n", ptr,
                    elf(t_caller));
            logStack();
        }
        return;
    }
    mspace_free(getHeap(), ptr);
}

void* __wrap_calloc(size_t nelem, size_t size) {
    t_op = "calloc";
    t_caller = __builtin_return_address(0);
    checkHeap(t_op, t_caller);
    void* p = t_arena ? mspace_calloc(t_arena, nelem, size) : nullptr;
    if (!p)
        p = mspace_calloc(getHeap(), nelem, size);
    if (!p)
        if (mspace overflow = overflowHeap())
            p = mspace_calloc(overflow, nelem, size);
    if (!p)
        reportFailure("calloc", nelem * size);
    return p;
}

void* __wrap_realloc(void* ptr, size_t size) {
    t_op = "realloc";
    t_caller = __builtin_return_address(0);
    checkHeap(t_op, t_caller);
    if (ptr && !ownsPointer(ptr)) {
        heapLog("[dolphin] heap: realloc(%p) of memory not from this heap, caller elf 0x%llx\n", ptr,
                elf(t_caller));
        logStack();
        return nullptr;
    }
    if (ptr && size == 0) {
        mspace_free(getHeap(), ptr);
        return nullptr;
    }
    // With FOOTERS this grows the chunk inside the arena it came from (the mspace argument is
    // only used for new allocations); when that arena is full, move it to this thread's.
    void* p = ptr ? mspace_realloc(getHeap(), ptr, size) : nullptr;
    if (!p) {
        p = t_arena ? mspace_malloc(t_arena, size) : nullptr;
        if (!p)
            p = mspace_malloc(getHeap(), size);
        if (!p)
            if (mspace overflow = overflowHeap())
                p = mspace_malloc(overflow, size);
        if (p && ptr) {
            const size_t old_size = mspace_usable_size(ptr);
            memcpy(p, ptr, old_size < size ? old_size : size);
            mspace_free(getHeap(), ptr);
        }
    }
    if (!p)
        reportFailure("realloc", size);
    return p;
}

void* __wrap_memalign(size_t alignment, size_t size) {
    t_op = "memalign";
    t_caller = __builtin_return_address(0);
    checkHeap(t_op, t_caller);
    void* p = t_arena ? mspace_memalign(t_arena, alignment, size) : nullptr;
    if (!p)
        p = mspace_memalign(getHeap(), alignment, size);
    if (!p)
        if (mspace overflow = overflowHeap())
            p = mspace_memalign(overflow, alignment, size);
    if (!p)
        reportFailure("memalign", size);
    return p;
}

// Gives the calling thread a private arena if it is one of Dolphin's busy threads (called when
// a thread names itself: Common::SetCurrentThreadName -> ps4_watch_thread).
void ps4_heap_private_arena(const char* name) {
    static const char* const busy[] = {"CPU thread", "CPU-GPU thread", "Video thread",
                                       "VK submission thread", "AsyncShaderCompiler Worker",
                                       "DVD thread", "Audio thread - PS4"};
    if (t_arena || !name || !getHeap())
        return;
    bool wanted = false;
    for (const char* b : busy)
        wanted |= strcmp(name, b) == 0;
    if (!wanted)
        return;
    if (!g_arenaKeyReady.load(std::memory_order_acquire)) {
        static std::atomic_flag s_creating = ATOMIC_FLAG_INIT;
        if (!s_creating.test_and_set()) {
            pthread_key_create(&g_arenaKey, releaseArena);
            g_arenaKeyReady.store(true, std::memory_order_release);
        }
        while (!g_arenaKeyReady.load(std::memory_order_acquire))
            sched_yield();
    }
    // An exited thread's arena first.
    lockFreeArenas();
    if (g_freeArenaCount > 0)
        t_arena = g_freeArenas[--g_freeArenaCount];
    unlockFreeArenas();
    if (t_arena) {
        pthread_setspecific(g_arenaKey, t_arena);
        heapLog("[dolphin] heap: reused arena for '%s'\n", name);
        return;
    }
    if (g_arenaCount.fetch_add(1) >= MAX_ARENAS)
        return;
    void* block = mspace_malloc(getHeap(), ARENA_SIZE);
    if (!block)
        return;
    t_arena = create_mspace_with_base(block, ARENA_SIZE, 1);
    if (t_arena)
        pthread_setspecific(g_arenaKey, t_arena);
    heapLog("[dolphin] heap: private %zu MiB arena for '%s'%s\n", ARENA_SIZE / MB, name,
            t_arena ? "" : " FAILED");
}

// posix_memalign and aligned_alloc in libc.a are built on __memalign.
void* __wrap___memalign(size_t alignment, size_t size) { return __wrap_memalign(alignment, size); }

// System libc malloc replacement (port/ps4_crt1.S, _sceLibcMallocReplace): the system libc
// forwards every malloc of the process here - Sony's system modules too (Piglet, its shader
// compiler) - instead of serving it from its own ~12.7 MiB heap, which they exhausted.
int ps4_replace_malloc_init(void) {
    getHeap();
    return 0;
}
int ps4_replace_malloc_finalize(void) { return 0; }
void* ps4_replace_malloc(size_t size) { return __wrap_malloc(size); }
void ps4_replace_free(void* ptr) { __wrap_free(ptr); }
void* ps4_replace_calloc(size_t nelem, size_t size) { return __wrap_calloc(nelem, size); }
void* ps4_replace_realloc(void* ptr, size_t size) { return __wrap_realloc(ptr, size); }
void* ps4_replace_memalign(size_t boundary, size_t size) { return __wrap_memalign(boundary, size); }
void* ps4_replace_reallocalign(void* ptr, size_t size, size_t boundary) {
    if (!ptr)
        return __wrap_memalign(boundary, size);
    if (size == 0) {
        __wrap_free(ptr);
        return nullptr;
    }
    void* p = __wrap_memalign(boundary, size);
    if (!p)
        return nullptr;
    const size_t old_size = mspace_usable_size(ptr);
    memcpy(p, ptr, old_size < size ? old_size : size);
    __wrap_free(ptr);
    return p;
}
int ps4_replace_posix_memalign(void** out, size_t boundary, size_t size) {
    void* p = __wrap_memalign(boundary, size);
    if (!p)
        return 12;  // ENOMEM
    *out = p;
    return 0;
}
// SceLibcMallocManagedSize: u16 size, u16 version, u32 reserved, then 4 sizes. Report the heap.
struct MallocManagedSize {
    uint16_t size;
    uint16_t version;
    uint32_t reserved;
    size_t max_system_size, current_system_size, max_inuse_size, current_inuse_size;
};
int ps4_replace_malloc_stats(void* out) {
    auto* stats = static_cast<MallocManagedSize*>(out);
    if (!stats)
        return 0x80020016;  // EINVAL
    const size_t footprint = mspace_footprint(getHeap());
    stats->max_system_size = mspace_max_footprint(getHeap());
    stats->current_system_size = footprint;
    stats->max_inuse_size = footprint;
    stats->current_inuse_size = footprint;
    return 0;
}
int ps4_replace_malloc_stats_fast(void* out) { return ps4_replace_malloc_stats(out); }
size_t ps4_replace_malloc_usable_size(void* ptr) { return ptr ? mspace_usable_size(ptr) : 0; }

// Large anonymous mmaps (--wrap=mmap): Dolphin's JIT code buffers, DSP ARAM, FIFO, ... would
// otherwise come out of the regular flexible memory pool (255 MiB), which Piglet (OpenGL ES)
// needs for all GPU memory - it ran out of it entirely. Take them from the system flexible pool
// (like the heap) instead; fall back to a normal mmap if that fails (e.g. for executable memory).
// Port switches, set by the app before emulation starts (DolphinPS4 ps4.ini).
int ps4_jit_in_system_pool = 1;           // executable mappings from the system pool too
unsigned long long ps4_fault_count = 0;   // fastmem faults seen by Dolphin's handler

void* __real_mmap(void* addr, size_t len, int prot, int flags, int fd, off_t offset);

// Executable memory for the JIT. Jailbreaks differ in what they let a homebrew app map as code it
// writes itself: a plain read/write/execute mmap works on some, others refuse it (seen on PS4 Pro
// consoles on firmware 11.00) but may allow it another way. ps4_exec_probe() tries each way once
// at startup (a 6-byte function run under a fault handler); the mmap wrapper then maps every
// executable request the way that worked.
int ps4_exec_method = 0;  // 0 mmap, 1 mmap + mprotect, 2 flexible, 3 system flexible, 4 JIT shm

namespace {
const char* const EXEC_METHOD_NAMES[] = {"mmap", "mmap+mprotect", "flexible memory",
                                         "system flexible memory", "JIT shared memory"};
const int32_t PROT_CPU_RWX = 0x7;
static int g_execError = 0;  // why the last mapExec failed (errno or SCE error)

void* mapExec(int method, size_t len) {
    g_execError = 0;
    switch (method) {
    case 0:
    case 1: {
        void* p = __real_mmap(nullptr, len, method == 0 ? PROT_CPU_RWX : PROT_CPU_RW, MAP_ANON | MAP_PRIVATE, -1, 0);
        if (p == MAP_FAILED) {
            g_execError = errno;
            return nullptr;
        }
        if (method == 1) {
            const int32_t ret = sceKernelMprotect(p, len, PROT_CPU_RWX);
            if (ret != 0) {
                g_execError = ret;
                sceKernelMunmap(p, len);
                return nullptr;
            }
        }
        return p;
    }
    case 2:
    case 3: {
        void* base = reserveAwayFromKernel(len);
        if (!base) {
            g_execError = -1;
            return nullptr;
        }
        const int32_t ret =
            method == 2 ? sceKernelMapNamedFlexibleMemory(&base, len, PROT_CPU_RWX, MAP_FIXED_FLAG, "dolphin jit")
                        : sceKernelMapNamedSystemFlexibleMemory(&base, len, PROT_CPU_RWX, MAP_FIXED_FLAG, "dolphin jit");
        if (ret != 0) {
            g_execError = ret;
            sceKernelMunmap(base, len);
            return nullptr;
        }
        return base;
    }
    case 4: {
        int32_t shm = -1;
        int32_t ret = sceKernelJitCreateSharedMemory(nullptr, len, PROT_CPU_RWX, &shm);
        if (ret != 0) {
            g_execError = ret;
            return nullptr;
        }
        void* p = __real_mmap(nullptr, len, PROT_CPU_RWX, MAP_SHARED, shm, 0);
        if (p == MAP_FAILED)
            g_execError = errno;
        sceKernelClose(shm);  // the mapping keeps the memory
        return p == MAP_FAILED ? nullptr : p;
    }
    }
    return nullptr;
}

static sigjmp_buf g_execJump;
void execFault(int) { siglongjmp(g_execJump, 1); }

// Runs `mov eax, 0x1234; ret` at `code`: true if it came back with that value.
bool runs(void* code) {
    struct sigaction fault = {}, old_segv = {}, old_bus = {};
    fault.sa_handler = execFault;
    sigemptyset(&fault.sa_mask);
    sigaction(SIGSEGV, &fault, &old_segv);
    sigaction(SIGBUS, &fault, &old_bus);
    volatile int result = 0;
    if (sigsetjmp(g_execJump, 1) == 0)
        result = reinterpret_cast<int (*)()>(code)();
    sigaction(SIGSEGV, &old_segv, nullptr);
    sigaction(SIGBUS, &old_bus, nullptr);
    return result == 0x1234;
}

const unsigned char EXEC_TEST_CODE[] = {0xB8, 0x34, 0x12, 0x00, 0x00, 0xC3};

// Only logged: Sony's own way (one read/execute view and a read/write alias of the same memory),
// which Dolphin's JIT can't use yet - it writes its code where it runs it.
void probeJitAlias() {
    int32_t shm = -1, alias = -1;
    int32_t ret = sceKernelJitCreateSharedMemory(nullptr, PAGE, PROT_CPU_RWX, &shm);
    if (ret != 0) {
        heapLog("[dolphin] exec: JIT alias: shared memory refused (%#x)\n", ret);
        return;
    }
    ret = sceKernelJitCreateAliasOfSharedMemory(shm, PROT_CPU_RW, &alias);
    void* exec = ret == 0 ? __real_mmap(nullptr, PAGE, PROT_READ | PROT_EXEC, MAP_SHARED, shm, 0) : MAP_FAILED;
    void* write = ret == 0 ? __real_mmap(nullptr, PAGE, PROT_CPU_RW, MAP_SHARED, alias, 0) : MAP_FAILED;
    if (ret != 0)
        heapLog("[dolphin] exec: JIT alias: alias refused (%#x)\n", ret);
    else if (exec == MAP_FAILED || write == MAP_FAILED)
        heapLog("[dolphin] exec: JIT alias: mapping refused (exec %s, write %s, errno %d)\n",
                exec == MAP_FAILED ? "no" : "ok", write == MAP_FAILED ? "no" : "ok", errno);
    else {
        memcpy(write, EXEC_TEST_CODE, sizeof(EXEC_TEST_CODE));
        heapLog("[dolphin] exec: JIT alias (separate write and execute views): %s\n",
                runs(exec) ? "works" : "faults");
    }
    if (exec != MAP_FAILED)
        sceKernelMunmap(exec, PAGE);
    if (write != MAP_FAILED)
        sceKernelMunmap(write, PAGE);
    if (alias >= 0)
        sceKernelClose(alias);
    sceKernelClose(shm);
}
}  // namespace

// The first way of mapping executable memory that works (also stored in ps4_exec_method), or -1.
// A plain mmap is tried first and, when it works, nothing else is (the usual case).
int ps4_exec_probe() {
    for (int method = 0; method < 5; method++) {
        void* page = mapExec(method, PAGE);
        if (!page) {
            heapLog("[dolphin] exec: %s refused (%#x)\n", EXEC_METHOD_NAMES[method],
                    static_cast<unsigned>(g_execError));
            continue;
        }
        memcpy(page, EXEC_TEST_CODE, sizeof(EXEC_TEST_CODE));
        const bool ok = runs(page);
        sceKernelMunmap(page, PAGE);
        if (ok) {
            ps4_exec_method = method;
            if (method != 0)
                heapLog("[dolphin] exec: executable memory from %s\n", EXEC_METHOD_NAMES[method]);
            return method;
        }
        heapLog("[dolphin] exec: %s maps, but running code there faults\n", EXEC_METHOD_NAMES[method]);
    }
    probeJitAlias();
    ps4_exec_method = -1;
    return -1;
}

void* __wrap_mmap(void* addr, size_t len, int prot, int flags, int fd, off_t offset) {
    const bool anonymous = fd == -1 && (flags & MAP_ANON) && !(flags & MAP_FIXED);
    if (anonymous && (prot & PROT_EXEC) && ps4_exec_method > 0) {
        // The way the startup probe found (a plain mmap is refused on this console).
        void* p = mapExec(ps4_exec_method, (len + PAGE - 1) & ~(PAGE - 1));
        if (p) {
            heapLog("[dolphin] mmap: %zu KiB executable from %s at %p\n", len / 1024,
                    EXEC_METHOD_NAMES[ps4_exec_method], p);
            return p;
        }
        heapLog("[dolphin] mmap: %zu KiB executable from %s failed (%#x)\n", len / 1024,
                EXEC_METHOD_NAMES[ps4_exec_method], static_cast<unsigned>(g_execError));
        errno = ENOMEM;
        return MAP_FAILED;
    }
    const bool allowed = !(prot & PROT_EXEC) || ps4_jit_in_system_pool;
    if (anonymous && allowed && len >= MB) {
        const size_t size = (len + PAGE - 1) & ~(PAGE - 1);
        void* base = reserveAwayFromKernel(size);
        if (base) {
            const int32_t ret = sceKernelMapNamedSystemFlexibleMemory(&base, size, prot & 0x7, MAP_FIXED_FLAG,
                                                                      "dolphin mmap");
            if (ret == 0) {
                heapLog("[dolphin] mmap: %zu KiB prot %d from system flexible memory at %p, caller elf 0x%llx\n",
                        size / 1024, prot, base, elf(__builtin_return_address(0)));
                return base;
            }
            heapLog("[dolphin] mmap: %zu KiB prot %d not possible from system flexible memory (0x%x)\n",
                    size / 1024, prot, ret);
            sceKernelMunmap(base, size);
        }
    }
    void* result = __real_mmap(addr, len, prot, flags, fd, offset);
    if (anonymous && len >= MB) {
        size_t available = 0;
        sceKernelAvailableFlexibleMemorySize(&available);
        heapLog("[dolphin] mmap: %zu KiB prot %d from regular flexible memory = %p, caller elf 0x%llx, "
                "%zu MiB flexible left\n",
                len / 1024, prot, result, elf(__builtin_return_address(0)), available / MB);
    }
    return result;
}

// clock_gettime for every caller (--wrap): CLOCK_MONOTONIC from the CPU's time stamp counter.
// The kernel's clock_gettime is a system call (FreeBSD 9 has no user-space time page), and
// Dolphin reads the monotonic clock thousands of times a second on both emulation threads
// (CoreTiming's throttle, std::chrono timeouts, the port's wait timers): ~6-9% of each thread in
// FIFA Street 2. The counter is invariant on the PS4's Jaguar cores; it is anchored to the
// kernel's clock on first use, so absolute times from both agree. Other clocks go to the kernel.
int __real_clock_gettime(clockid_t id, struct timespec* ts);
uint64_t sceKernelGetTscFrequency_ps4() __asm__("sceKernelGetTscFrequency");
unsigned long long ps4_clock_reads;  // DolphinNoGUI monitor (approximate, unsynchronised)

int __wrap_clock_gettime(clockid_t id, struct timespec* ts) {
    if (id != CLOCK_MONOTONIC)
        return __real_clock_gettime(id, ts);
    struct Anchor {
        uint64_t tsc = 0, ns = 0, mult = 0;  // ns per tick as 32.32 fixed point
        bool ok = false;
    };
    static const Anchor anchor = [] {
        Anchor a;
        const uint64_t freq = static_cast<uint64_t>(sceKernelGetTscFrequency_ps4());
        struct timespec now;
        if (freq < 1000000 || __real_clock_gettime(CLOCK_MONOTONIC, &now) != 0)
            return a;
        a.tsc = __builtin_ia32_rdtsc();
        a.ns = static_cast<uint64_t>(now.tv_sec) * 1000000000ull + static_cast<uint64_t>(now.tv_nsec);
        a.mult = (1000000000ull << 32) / freq;
        a.ok = true;
        return a;
    }();
    if (!anchor.ok)
        return __real_clock_gettime(id, ts);
    ps4_clock_reads++;
    const uint64_t ticks = __builtin_ia32_rdtsc() - anchor.tsc;
    const uint64_t ns =
        anchor.ns + static_cast<uint64_t>((static_cast<unsigned __int128>(ticks) * anchor.mult) >> 32);
    ts->tv_sec = static_cast<time_t>(ns / 1000000000ull);
    ts->tv_nsec = static_cast<long>(ns % 1000000000ull);
    return 0;
}

// pthread_once for every caller (--wrap): the kernel's (FreeBSD) version treats pthread_once_t
// as a 16-byte struct, but the OpenOrbis headers - and the prebuilt libc.a (newlocale,
// call_once, ...) - use a 4-byte int, which it overflowed. This one only uses those 4 bytes:
// 0 = not run (PTHREAD_ONCE_INIT), 1 = running, 2 = done.
int __wrap_pthread_once(pthread_once_t* once, void (*init)(void)) {
    auto* state = reinterpret_cast<int*>(once);
    if (__atomic_load_n(state, __ATOMIC_ACQUIRE) == 2)
        return 0;
    int expected = 0;
    if (__atomic_compare_exchange_n(state, &expected, 1, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        init();
        __atomic_store_n(state, 2, __ATOMIC_RELEASE);
        return 0;
    }
    while (__atomic_load_n(state, __ATOMIC_ACQUIRE) != 2)
        sched_yield();
    return 0;
}

int __cxa_thread_atexit_impl(void (*dtor)(void*), void* obj, void* /*dso_symbol*/) {
    pthread_once(&g_threadDtorOnce, createThreadDtorKey);
    auto* entry = static_cast<ThreadDtor*>(malloc(sizeof(ThreadDtor)));
    if (!entry)
        return -1;
    // Destructors run in reverse order of registration, so push to the front.
    entry->dtor = dtor;
    entry->obj = obj;
    entry->next = static_cast<ThreadDtor*>(pthread_getspecific(g_threadDtorKey));
    pthread_setspecific(g_threadDtorKey, entry);
    return 0;
}

// Diagnostics.
const char* ps4rt_heap_source(void) {
    getHeap();
    return g_heapPool;
}
size_t ps4rt_heap_size(void) {
    getHeap();
    return g_heapSize;
}

}  // extern "C"
