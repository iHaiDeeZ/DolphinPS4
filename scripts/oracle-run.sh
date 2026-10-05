#!/usr/bin/env bash
# LAB: runs a game under the parallelism oracle (interpreter + Core/PowerPC/Interpreter/ParallelismOracle.cpp).
#   oracle-run.sh <seconds> <report file> [game]   (needs scripts/build-host-oracle.sh first)
set -uo pipefail
cd ~/dolphinps4-build
GAME="${3:-/mnt/c/Users/Shiro/Downloads/Super Smash Bros. Melee (USA) (En,Ja).rvz}"
sed -i 's/^CPUCore = .*/CPUCore = 0/' oracle-user/Config/Dolphin.ini
SECONDS_TO_RUN="${1:-60}"
OUT="${2:-$HOME/dolphinps4-build/oracle-melee.txt}"
DOLPHIN_ORACLE_OUT="$OUT" timeout "$SECONDS_TO_RUN" build/dolphin-host/Binaries/dolphin-emu-nogui -p headless -u "$PWD/oracle-user" -e "$GAME" > oracle-run.log 2>&1
echo "exit $?"
