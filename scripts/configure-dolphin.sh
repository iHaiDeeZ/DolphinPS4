#!/usr/bin/env bash
# Configure Dolphin for PS4 with the modern love-ps4-style toolchain: the NoGUI frontend with the
# PS4 platform, linked like love-ps4 (ps4-love-style.cmake is included into the top-level project).
# USE_SYSTEM_CURL=OFF: Dolphin's bundled curl, built for its own mbedtls 2.28. PacBrew's libcurl
# was compiled against mbedtls 2.16 headers but ended up linked with Dolphin's 2.28 library (mismatched
# structures: certificate checks failed, and 2.28 code could write past curl's smaller structs).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ps4-env.sh"
# LAB COPY (experiment/split-cpu): builds the experimental Dolphin from src/dolphin-lab into
# build/dolphin-lab, packaged as the separate app "Dolphin Lab" (DLPH00011). The stable port is
# J:\DolphinPS4 with src/dolphin and build/dolphin; the two never share a build.
SRC="${DOLPHIN_SRC:-$PS4_BUILD_ROOT/src/dolphin-lab}"
BUILD="${DOLPHIN_BUILD:-$PS4_BUILD_ROOT/build/dolphin-lab}"
ps4_cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$HERE/../toolchain/ps4-love-modern.cmake" \
    "-DCMAKE_PROJECT_dolphin-emu_INCLUDE=$HERE/../toolchain/ps4-love-style.cmake" \
    -DENABLE_QT=OFF -DENABLE_NOGUI=ON -DENABLE_HEADLESS=ON -DENABLE_CLI_TOOL=OFF \
    -DENABLE_X11=OFF -DENABLE_EGL=OFF -DENABLE_VULKAN=ON -DENABLE_LLVM=OFF -DENABLE_TESTS=OFF \
    -DENABLE_ALSA=OFF -DENABLE_PULSEAUDIO=OFF -DENABLE_CUBEB=OFF -DENABLE_SDL=OFF \
    -DENABLE_EVDEV=OFF -DENABLE_HWDB=OFF -DENABLE_AUTOUPDATE=OFF -DENABLE_ANALYTICS=OFF \
    -DUSE_DISCORD_PRESENCE=OFF -DUSE_MGBA=OFF -DUSE_RETRO_ACHIEVEMENTS=OFF -DUSE_UPNP=OFF \
    -DENCODE_FRAMEDUMPS=OFF -DENABLE_LTO=OFF -DENABLE_GENERIC=OFF \
    -DUSE_SYSTEM_CURL=OFF \
    -DPS4_PAID="${PS4_PAID:-0x3800000000000035}" \
    "$@"
