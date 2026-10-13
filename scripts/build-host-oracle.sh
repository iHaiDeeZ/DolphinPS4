#!/usr/bin/env bash
# JIT LAB (experiment/jit-trace): headless PC (Linux/WSL) build of src/dolphin-jit, for the PS4 JIT
# test bench and the parallelism oracle (DOLPHIN_SRC / DOLPHIN_HOST_BUILD change the folders).
# No graphics, sound or controllers. The test
# bench for the PS4 JIT (CPU core 6): DOLPHIN_PS4_HOST turns on the lab code it relies on.
set -euo pipefail
cd ~/dolphinps4-build
cmake -S "${DOLPHIN_SRC:-src/dolphin-jit}" -B "${DOLPHIN_HOST_BUILD:-build/dolphin-jit-host}" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang-21 -DCMAKE_CXX_COMPILER=clang++-21 \
  -DCMAKE_C_FLAGS=-DDOLPHIN_PS4_HOST -DCMAKE_CXX_FLAGS=-DDOLPHIN_PS4_HOST \
  -DENABLE_QT=OFF -DENABLE_NOGUI=ON -DENABLE_HEADLESS=ON -DENABLE_X11=OFF -DENABLE_EGL=OFF \
  -DENABLE_VULKAN=OFF -DENABLE_LLVM=OFF -DENABLE_TESTS=OFF -DENABLE_ALSA=OFF -DENABLE_PULSEAUDIO=OFF \
  -DENABLE_CUBEB=OFF -DENABLE_SDL=OFF -DENABLE_EVDEV=OFF -DENABLE_HWDB=OFF -DENABLE_AUTOUPDATE=OFF \
  -DENABLE_ANALYTICS=OFF -DUSE_DISCORD_PRESENCE=OFF -DUSE_MGBA=OFF -DUSE_RETRO_ACHIEVEMENTS=OFF \
  -DUSE_UPNP=OFF -DENCODE_FRAMEDUMPS=OFF -DENABLE_LTO=OFF -DENABLE_BLUEZ=OFF -DUSE_SYSTEM_LIBS=OFF \
  > ~/dolphinps4-build/host-configure.log 2>&1
ninja -C "${DOLPHIN_HOST_BUILD:-build/dolphin-jit-host}" -j"$(nproc)" dolphin-emu-nogui
