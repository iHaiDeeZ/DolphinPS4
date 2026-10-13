#!/usr/bin/env bash
# The PS4 JIT on the PC (build-host-oracle.sh first): runs a game - from a save state copied from
# the PS4 - headless, at 100% speed, with the PS4 JIT (CPU core 6, user dir ~/dolphinps4-build/jit-user:
# MMU off, CPUCore 6, CPUThread on, GFXBackend Null, EmulationSpeed 1).
#   jit-test.sh <seconds> <log> <game> [state]
# Environment: PS4JIT_VERIFY=1 (recompiler check), PS4JIT_BENCH=1 (CPU thread time every 10 s),
# PS4JIT_PIN=1,3,4,31, PS4JIT_JOIN=1, PS4JIT_SINGLES=0, PS4JIT_JOINLOG=<block address>.
# Some games (Bully) don't shut down here: the run is killed 10 s after <seconds>.
cd ~/dolphinps4-build
SECS="$1"; LOG="$2"; GAME="$3"; STATE="${4:-}"
ARGS=(-p headless -u "$PWD/jit-user" -e "$GAME")
[ -n "$STATE" ] && ARGS+=(-s "$STATE")
/usr/bin/time -f "wall %e s, user %U s" timeout -k 10 "$SECS" ${DOLPHIN_HOST_BUILD:-build/dolphin-jit-host}/Binaries/dolphin-emu-nogui "${ARGS[@]}" > "$LOG" 2>&1
echo "exit $?"
