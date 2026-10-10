# CPU options

Every setting that changes how the GameCube / Wii CPU is emulated, what it does, its default and
when to change it.

**Most players never need this page.** Leave *Emulated CPU Clock* on *Auto* and keep the *Game
Settings Center* on: it applies settings tested for each game automatically.

## Where the settings go

- **In the menu:** *Settings → Performance* in the launcher (all games, or one game from Triangle
  → *Game Settings*), or the in-game menu (L3 + R3).
- **In `ps4.ini`:** `/data/DolphinPS4/ps4.ini`, edited over FTP. One `key=value` per line.
  - Lines **before** the first `[GAME ID]` apply to every game.
  - Lines under `[GAME ID]` apply to that game only. Use 3 characters for every region of a game
    (`[RMC]` = Mario Kart Wii) or 6 for one disc (`[RMCE01]`).
  - `ps4.ini` wins over the app's defaults and the Game Settings Center; settings changed in the
    menu win over `ps4.ini`.

Example:

```ini
cpu_clock=auto

[GOW]
# Need for Speed: Most Wanted only
jit_accurate_singles=off
```

Options marked **Lab** are only in Dolphin Lab for now; the others are also in the normal app.

## Rounding (`jit_accurate_singles`)

This is the rounding option. A GameCube/Wii does single-precision float math (32-bit numbers); the
PS4's CPU is made to do it in double precision and round each result to single, which costs time
in float-heavy games.

| Value | What it does |
|---|---|
| `on` (default) | Rounds like the real console. Always correct. |
| `off` | No rounding at all. Fastest: Need for Speed: Most Wanted gained about 21% FPS in races. **Can break menus**: Mario Kart Wii's and NFS's menus went black. |
| `results` | **Lab.** Only the results are rounded; the multiply inputs are not. Menus keep working, but it measured no faster than `on`. |
| `operands` | **Lab.** Only the multiply inputs are rounded; results are not. Breaks menus like `off`. |

**How to use it:** one game at a time. In Dolphin Lab it is in the menu: Triangle on the game →
*Game Settings → Performance → Float Rounding* (*Accurate* = `on`, *Fast* = `off`). In the normal
app, put it under the game's `[ID]` in `ps4.ini`. Try *Fast*; if a menu, HUD or text goes missing,
go back to *Accurate*.

`accurate_fmadds` is a related, smaller rounding setting: `on` rounds multiply-add instructions
exactly as the console does. The app's default is `off` (cheaper; no game has needed it so far).

## Clock and threads

| Option | Values (default first) | What it does |
|---|---|---|
| `cpu_clock` | `auto`, `50`…`150` | *Emulated CPU Clock* in the menu. A lower clock gives the game fewer CPU cycles per frame, so the PS4 has less to emulate: faster when the CPU is the limit, but a game that needs those cycles may run slower inside. `auto` lowers the clock only while the game can't keep full speed, and raises it again when it can. |
| `cpu_clock_min` | `50` | The lowest clock `auto` may use. Some games set their own floor in the Game Settings Center (Bully 35, Mario Kart Wii and MW3 40). Too low can stop a game from booting (Bully at 30). |
| `cpu_clock_max` | `100` | The highest clock `auto` may use. |
| `dual_core` | `on`, `force`, `off` | *Dual Core* in the menu. `on` emulates the GPU on its own thread; much faster. `force` keeps it on even for games whose Dolphin settings turn it off. `off` is slow, only for testing. |
| `sync_gpu` | `off`, `on` | *Synchronize GPU Thread* in the menu. `on` stops the CPU thread from running too far ahead of the GPU thread. Safer for a few games, but slower (Bully: 78% vs 95% speed). |
| `sync_gpu_distance` | `1000000` | With `sync_gpu=on`: how far ahead (in emulated cycles) the CPU may run before it waits. Bigger means fewer waits. |
| `sync_on_idle` | `on`, `off`, `frame` | When the game idles, whether the CPU thread first waits for the GPU thread to finish. `off` lets them keep overlapping (faster, slightly less safe). |
| `cpu_thread_core`, `gpu_thread_core` | `2`, `3` | Which PS4 core runs the emulated CPU and the video thread (0–5; -1 lets the system choose). |
| `thread_priority` | `0` | Priority for those threads (256–767; 0 keeps the system's). |

## Speed features (the port's shortcuts)

*Speed Features* in the menu (`speed_mode`): **Fast** (default) or **Compatible**. Compatible
turns off all of the shortcuts in this section, for a game that glitches or freezes.

| Option | Default | What it does |
|---|---|---|
| `fifo_batch` | `on` | The video thread takes GPU commands in batches of up to 1 KiB instead of 32 bytes. Helps games that send many commands (Crash). |
| `fifo_defer` | `off` | Lets GPU commands collect in the CPU's write buffer before they are handed over (Crash: 16% → 5% of the time spent handing over). **Off by default since 2026-10-10:** it froze Metroid Prime, Call of Duty MW3, Sonic the Fighters and Killer7 ("FIFO: Unknown Opcode"). Crash Bandicoot: The Wrath of Cortex turns it on through the Game Settings Center. |
| `jit_gp_fuse` | `on` | The JIT updates the write buffer's pointer once per group of writes instead of after each one. |
| `jit_lazy_lfs` | `on` | Single-precision loads that are only stored again skip the float conversion. |
| `gpu_lazy_flush` | `on` | The video thread doesn't flush its draws every time it runs out of commands. |

## JIT (the CPU recompiler)

The JIT translates the game's PowerPC code into PS4 code. All of these are on by default; turning
one `off` is only for finding a bug.

| Option | What it does when on |
|---|---|
| `cpu_core` | `jit` (default), `cachedinterpreter`, `interpreter`. The interpreters are many times slower; only for testing. |
| `jit_memory` | Where the JIT's code lives (`regular` in the app's defaults). Leave it. |
| `fastmem` | Game memory accesses go straight to PS4 memory. `off` is much slower. |
| `jit_fcmp_merge` | A float compare and the branch after it are compiled together. |
| `jit_follow` | How many branches a compiled block may follow (1–16, default 2). |
| `jit_inline_dispatch` | Jumps between compiled blocks skip the central dispatcher. |
| `jit_lazy_pc` | Block exits store the program counter only when needed. |
| `jit_unroll` | Small loops are compiled as one longer block. |
| `jit_gp_dynamic` | Writes to the GPU write buffer go straight to it. |
| `jit_lfs_forward` | A single-precision value loaded and stored in the same block is copied, not converted twice. |
| `jit_tlb_inline` | The page-table cache is checked inside the compiled code (games that use the MMU). |
| `jit_pin` | **Lab, off by default.** Keeps up to four guest registers in PS4 registers across blocks, e.g. `jit_pin=1,3,4,31`. Measured: less register traffic, no speed gain. |

## Memory and page table

| Option | Default | What it does |
|---|---|---|
| `pagetable_fastmem` | `off` | Dolphin's fast mappings for games that use the page table. Off on PS4: remapping took a quarter of the CPU thread in Ultimate Spider-Man. `deferred` remaps once per sync. |
| `soft_tlb` | `precise` | `flush` empties the whole page-table cache on every invalidation (the old behaviour). |
| `perfmon` | `on` | Emulates the CPU's performance counters. `off` is about 2% faster in games that don't read them (Crash: The Wrath of Cortex). |
| `game_hle` | `on` | Native PS4 versions of a few known hot game routines. |

## Other

| Option | Default | What it does |
|---|---|---|
| `cpu_cull` | `game` | Culling of hidden triangles on the video thread (the game's own setting). `off` saves video-thread time in a few games (tested on Metroid Prime). |
| `fast_disc` | `on` | *Fast Disc Speed* in the menu: shorter loading pauses. |
| `dsp_async` | `off` | **Lab.** Audio command lists on their own thread. About 2% faster, risky; off. |
| `dvd_async` | `off` | A late disc read delays the emulated drive instead of the CPU. Broke Bully; off. |
| `disc_cache` | `off` | Disc reads through a 16 MiB cache. Didn't help (Bully's slow reads were new areas); off. |

## What helped in practice

- **CPU-limited game** (busy scenes slow, CPU thread maxed): keep `cpu_clock=auto`; a lower
  `cpu_clock_min` lets it go further (35–40 helped Bully, Mario Kart Wii and MW3).
- **Float-heavy game** with simple menus: try `jit_accurate_singles=off` for that game only.
- **A game freezes with "FIFO: Unknown Opcode"** in `dolphin.log`: make sure `fifo_defer=off`, or
  set *Speed Features* to *Compatible*.
- **Video thread waiting on the TV's refresh** (a 60 FPS game just under full speed): that's
  `flip_thread=on` with `display_buffers=6`, not a CPU option. It helped Mario Kart Wii and Star Fox
  Adventures, and made Soulcalibur II slower.
