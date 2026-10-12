#!/usr/bin/env bash
# Throughput: emulated CPU at 20%, no speed limit -> the CPU thread never idles; emulated
# cycles per second (20 s -> 50 s) measure how fast the translated code runs.
S=/mnt/j/DolphinPS4-lab/scripts
G=~/dolphinps4-build/games-host
INI=~/dolphinps4-build/jit-user/Config/Dolphin.ini
sed -i "s/^Overclock = .*/Overclock = 0.20000000/; s/^EmulationSpeed = .*/EmulationSpeed = 0.00000000/" $INI
run() {
  local name="$1"; shift
  for r in 1 2 3; do
    env PS4JIT_BENCH=1 "$@" $S/jit-test.sh 55 /tmp/th-$name-$r.log $G/Bully.nkit.iso $G/RB7E54-new.s01 > /dev/null
    a=$(grep -a "\[bench\] 20 s" /tmp/th-$name-$r.log | sed -E "s/.*, ([0-9]+) M cycles.*/\1/")
    b=$(grep -a "\[bench\] 50 s" /tmp/th-$name-$r.log | sed -E "s/.*, ([0-9]+) M cycles.*/\1/")
    ca=$(grep -a "\[bench\] 20 s" /tmp/th-$name-$r.log | sed -E "s/.*CPU thread ([0-9.]+) s.*/\1/")
    cb=$(grep -a "\[bench\] 50 s" /tmp/th-$name-$r.log | sed -E "s/.*CPU thread ([0-9.]+) s.*/\1/")
    echo "$name run $r: $(( (b - a) / 30 )) M emulated cycles/s, CPU thread $(echo "($cb - $ca)/30" | bc -l | cut -c1-5) busy"
  done
}

run pins_auto PS4JIT_PIN=1,3,4,31 PS4JIT_TRACE=auto


sed -i "s/^Overclock = .*/Overclock = 0.35000000/; s/^EmulationSpeed = .*/EmulationSpeed = 1.00000000/" $INI
