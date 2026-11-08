# Performance audit, November 2026 (JIT Lab v60.59 → v60.60)

Three read-only audits of the code (recompiler, video thread, threads/sync), checked against the
profiles of Super Mario Galaxy, Bully, Crash, Shadow, Mario Kart Wii and NBA Street.

**Where the time goes.** Every slow game hits one of three limits:

- **The CPU thread.** The game's recompiled code takes 50–80% of it, spread flat over thousands
  of blocks.
- **The video thread.** Per-command and per-draw overhead.
- **Waiting.** The CPU and video threads take turns, plus flips and disc reads.

A base PS4 core runs at 1.6 GHz, about half of what heavy games need on a PC. Not every game can
reach 60 FPS; the work below raises the ceiling for all of them.

## Done in v60.60 (low risk, still to be measured)

| Change | Where | Expected |
|---|---|---|
| The flip thread got cores 0 and 4 at priority 400. It had inherited the video thread's core 3, so a busy video thread could delay flips (missed vblanks). | VKSwapChain.cpp | Vsync-bound games; probably why the flip thread slowed Bully and Soulcalibur II |
| The `dsp_async` AX worker moved off the CPU thread's core, which it had inherited and could only use while the CPU thread waited. | AX.cpp | Makes `dsp_async` worth re-testing (~2%) |
| The main thread is limited to cores 0, 4 and 6, so the main loop, DVD, sampler, hook and memcard threads stay off cores 1, 2, 3 and 5. | MainNoGUI.cpp | Removes occasional preemption |
| jit_hot sampling (1 kHz signals) only runs with the PS4 recompiler. | MainNoGUI.cpp | 0.5–2% of the CPU thread on Jit64 games |
| VK recorder: release stores instead of a locked xchg per record, a cached read position, and the read position published per batch and per submit. | PS4CommandRecorder.cpp | ~2–4% of the video thread (about 200k records/s in SMG) |
| XF memory loads with unchanged values skip the flush and the dirty marks. | XFStructs.cpp | Fewer split draws and 4 KB constant uploads |
| MATINDEX/VCD writes no longer turn off run stretching: the CP/XF check now runs once per run. | VertexLoaderManager.cpp | 1–4% of the video thread |
| Indirect exits (bctr) reload pc only when Cleanup() used the register. | JitPS4/Jit.cpp | Small |
| The clock-read counter is per thread, so it no longer moves between cores. | port/ps4_runtime.cpp | Small |

## Next, ranked (bigger or riskier)

### CPU thread (JitPS4)
1. **Single-precision register state.** Keep singles as singles: `ADDSS`/`MULSS` on singles,
   lfs/stfs without converting. Float round/convert is 9–11% of block time in Bully, and the
   hottest blocks are limited by `cvtss2sd`/`cvtsd2ss` chains. Results stay identical for + − × ÷ √
   on single inputs. Generalise `PS4AnalyzeRawSingles`. Size L; the gain is 4–7% of block time.
2. **Second tier for hot blocks only.** Pick the top ~300–500 blocks with the existing jit_hot
   sampler, then recompile them with traces, joins and loop back-edges in the hot area. The PC's
   +22% from jit_trace was lost on the PS4 because every block was instrumented. Needs `PS4CanJoin`
   to allow pins. Size L; the gain is 5–15% of JIT time, unmeasured.
3. **Dead-store elimination.** Don't store registers right after their last write when every exit
   kills them (`gpr.Flush(...Undirty)` at Jit.cpp:2779). This also gives jit_cross_dead something to
   remove. Size S–M; the gain is 1–2%.
4. **fcmp without branches.** Build CR with CMOV, and branch on the UCOMISD flags when merged with
   bc. About 3.7k sites. Size S–M; the gain is 1–3% in float code.
5. **Constant GQR from mtspr.** Use the inline psq paths instead of the generic routines (2.3% of
   JIT in Bully). Size S.
6. **perfmon=on.** It currently calls C++ at every block exit; inline the PMC adds. This matters
   only for games that program MMCR.
7. **Code size.** Move conditional exit stubs to far code, and use a 32-bit BLR key. 1–3%,
   uncertain.

### Video thread
1. **Shader UIDs.** Skip rebuilding the UIDs when no UID-relevant BP/XF state changed (54k flushes
   a second in SMG). Size M; the gain is 2–5%.
2. **Constant uploads.** Don't copy the 2.5 KB of matrix arrays when the vertex format has no matrix
   indices, and stop the pixel constants at `konst`. Size M; the gain is 1.5–3%.
3. **Vertex worker Sync.** Move the Sync in Fifo.cpp:524 (on every FIFO catch-up) to the idle,
   sleep, interrupt and breakpoint points. This is the 5% the video thread spends waiting for the
   worker. Medium risk.
4. **Flush-time work.** Skip `CalculateZSlope` until a game uses zfreeze, and run `FlushCaches`
   only at vertex format changes. 1–2.5%.
5. **EFB copy hashing.** Bound the scan in `PS4ForgetTextureHashes` by address range, and don't hash
   the constant XFB pattern. 1–2%.
6. **BP flushes.** Skip `FlushPipeline` for BP registers that don't affect drawing (copy setup,
   clear values, perf counters).

### Waiting / system
1. **Shared EOP event queue.** Waiters share one queue, so a wakeup can be lost and cost a 1 ms
   timeout. First count `ps4_sleep` wakeups with count==0 after completion; then give each waiter
   its own queue, or spin briefly with PAUSE. Could cut part of the video thread's fence waits.
2. **4 display buffers with the flip thread.**
3. **Blocking requests.** Spin briefly before blocking on EFB peek, BBox and perf-query round
   trips.
4. **Core layout to try** (ps4.ini only): `cpu_thread_core=4 audio_thread_core=5 vk_thread_core=2`
   gives the CPU thread a module of its own.
5. **Disc stalls (Bully).** Read ahead 1–2 MiB on a cache miss.

## How to measure

With JIT Lab and Settings › Diagnostics › Hook on:

```bash
python tools/ps4hook.py --ip <ps4> gaps 30
```

A/B a live setting with the scratchpad's `hookexp.py`. Compare CPU-thread time per emulated
frame at a fixed clock, not FPS alone: gains of 3–5% are within FPS noise.
