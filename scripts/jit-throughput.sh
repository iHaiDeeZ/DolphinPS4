#!/usr/bin/env bash
# Throughput: emulated CPU at 35% (Bully's floor - at 20% it stalls and draws nothing), no speed
# limit -> game frames per second of CPU-thread time (20 s -> 50 s) measure how fast the
# translated code runs the game. Check the frame count: 0 frames means the game isn't running.
#   STATE=RB7E54-fight.s01 jit-throughput.sh [name "ENV=1 ENV2=..."]...
S=/mnt/j/DolphinPS4-jit/scripts
G=~/dolphinps4-build/games-host
INI=~/dolphinps4-build/jit-user/Config/Dolphin.ini
sed -i "s/^Overclock = .*/Overclock = ${OC:-0.35000000}/; s/^EmulationSpeed = .*/EmulationSpeed = ${SPEED:-0.00000000}/" $INI
val() { grep -a "\[bench\] $1 s:.*frames" "$2" | sed -E "s/.*: ([0-9]+) frames.*CPU thread ([0-9.]+) s.*/\1 \2/"; }
run() {
  local name="$1"; shift
  for r in 1 2 3; do
    env PS4JIT_BENCH=1 "$@" $S/jit-test.sh 55 /tmp/th-$name-$r.log $G/Bully.nkit.iso $G/${STATE:-RB7E54-fight.s01} > /dev/null
    read fa ca <<< "$(val 20 /tmp/th-$name-$r.log)"
    read fb cb <<< "$(val 50 /tmp/th-$name-$r.log)"
    echo "$name run $r: $((fb - fa)) frames in $(echo "$cb - $ca" | bc -l | cut -c1-6) s CPU thread = $(echo "($fb - $fa) / ($cb - $ca)" | bc -l | cut -c1-6) frames per CPU second"
  done
}
if [ $# -eq 0 ]; then set -- pins "PS4JIT_PIN=1,3,4,31"; fi
while [ $# -ge 2 ]; do run "$1" $2; shift 2; done
sed -i "s/^Overclock = .*/Overclock = 0.35000000/; s/^EmulationSpeed = .*/EmulationSpeed = 1.00000000/" $INI
