#!/usr/bin/env bash
# LAB: headless PC (Linux/WSL) build of the lab Dolphin, for the parallelism oracle.
# Builds src/dolphin-lab into build/dolphin-host; no graphics, sound or controllers.
set -euo pipefail
cd ~/dolphinps4-build
cmake -S src/dolphin-lab -B build/dolphin-host -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang-21 -DCMAKE_CXX_COMPILER=clang++-21 \
  -DENABLE_QT=OFF -DENABLE_NOGUI=ON -DENABLE_HEADLESS=ON -DENABLE_X11=OFF -DENABLE_EGL=OFF \
  -DENABLE_VULKAN=OFF -DENABLE_LLVM=OFF -DENABLE_TESTS=OFF -DENABLE_ALSA=OFF -DENABLE_PULSEAUDIO=OFF \
  -DENABLE_CUBEB=OFF -DENABLE_SDL=OFF -DENABLE_EVDEV=OFF -DENABLE_HWDB=OFF -DENABLE_AUTOUPDATE=OFF \
  -DENABLE_ANALYTICS=OFF -DUSE_DISCORD_PRESENCE=OFF -DUSE_MGBA=OFF -DUSE_RETRO_ACHIEVEMENTS=OFF \
  -DUSE_UPNP=OFF -DENCODE_FRAMEDUMPS=OFF -DENABLE_LTO=OFF -DENABLE_BLUEZ=OFF -DUSE_SYSTEM_LIBS=OFF \
  > ~/dolphinps4-build/host-configure.log 2>&1
ninja -C build/dolphin-host -j"$(nproc)" dolphin-emu-nogui
