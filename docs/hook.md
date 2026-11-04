# The hook: look inside a running game from a PC

JIT Lab v60.58 and later. Turn it on in **Settings > Diagnostics > Hook**. It's off by default,
because anyone on your network can use it while it's on.

When it's on, the app listens on **TCP port 9520** while a game runs. The protocol is plain text:
send one command per line, and every reply ends with a line containing only `.`. You can talk to
it with `nc` or the client script.

```bash
python3 tools/ps4hook.py --ip 192.168.0.225 status
python3 tools/ps4hook.py --ip 192.168.0.225              # interactive, type "help"
python3 tools/ps4hook.py --ip 192.168.0.225 gaps 30      # what limits the game, and where to look
python3 tools/ps4hook.py --ip 192.168.0.225 top "Video thread"
python3 tools/ps4hook.py --ip 192.168.0.225 record run.csv 120
```

## Reading

| Command | What it gives |
|---|---|
| `info` | App version, game, state, CPU core, speed, recompiler block count |
| `status` / `watch [s]` | The monitor line: speed, FPS, thread busy %, GPU busy, waits, draws, EFB copies. `watch` also streams trace lines (hitches, auto clock) |
| `trace [n]` | The last lines of `boot-trace.log` |
| `profiler on\|off` | The 1 kHz sampler for every thread |
| `samples [thread] [n]` | Each thread's last n samples, grouped: Dolphin code (ELF address), game code, waits (caller), system modules |
| `jit top [n]` | The game code blocks the CPU thread spends its time in (guest address, share, size) |
| `jit stats` | Block count and free code space |
| `regs`, `read`, `dis` | PowerPC registers, guest memory, disassembly |
| `stacks` | Every thread's stack, written to `/data/DolphinPS4/hook-stacks.txt` |

`ps4hook.py top` and `gaps` name the Dolphin functions using the symbol file of the exact build
(`~/dolphinps4-build/oelf/lab-v<version>.oelf`).

## Control

| Command | What it does |
|---|---|
| `pause`, `resume`, `step` | Pause, resume, or advance one frame |
| `speed <percent>` | Speed limit for this run (0 = unlimited) |
| `settings [filter]`, `get <key>` | The port's settings and what each choice means |
| `set <key> <value>` | Applies a live setting for this run only (not saved) |
| `save <key> <value> [game]` | Saves a setting globally or for this game |
| `config <System.Section.Key> [value]` | Any Dolphin config value, for this run, e.g. `config GFX.Settings.InternalResolution 2` |
| `write <addr> <hex>`, `jit clear` | Patch guest memory, clear the recompiler cache |
| `state save\|load <n>`, `screenshot` | Save state slots 1–10, screenshot |
| `press <b>[+<b>] [ms]`, `hold`, `release`, `stick lx ly [rx ry]`, `stick off`, `wait <ms>` | Controller input on top of the player's (cross circle square triangle up down left right l1 r1 l2 r2 l3 r3 start select); everything is released when the client leaves |
| `mark <text>` | Writes a marker line into the trace |

A command that touches the emulator runs on the app's main loop, the same thread as the in-game
menu. Read-only commands (`status`, `watch`, `trace`, `samples`, controller input) run on the
hook's own thread and don't disturb the game. `regs`, `read`, `jit top` and `jit clear` pause the
CPU thread for a moment.

`script <file>` in the client runs a list of commands. For example, a repeatable benchmark:

```
state load 1
mark bench start
watch 30
mark bench end
```
