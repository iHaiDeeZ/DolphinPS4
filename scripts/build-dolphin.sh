#!/usr/bin/env bash
# Build Dolphin for PS4 (run scripts/configure-dolphin.sh first). Extra args go to ninja.
#   build-dolphin.sh [ninja args...]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ps4-env.sh"  # also puts PacBrew ld.lld's libxml2 compat link on LD_LIBRARY_PATH
# LAB COPY (experiment/split-cpu): builds the experimental Dolphin from src/dolphin-lab into
# build/dolphin-lab, packaged as the separate app "Dolphin Lab" (DLPH00011). The stable port is
# J:\DolphinPS4 with src/dolphin and build/dolphin; the two never share a build.
ninja -C "${DOLPHIN_BUILD:-$PS4_BUILD_ROOT/build/dolphin-lab}" -j"${JOBS:-8}" "$@"
