#!/usr/bin/env bash
# Package the PS4 Dolphin build (after scripts/configure-dolphin.sh + ninja) as DLPH00010:
# eboot.bin, Dolphin's Data/Sys as /app0/Sys, and the Piglet/shader compiler modules.
#   package-dolphin.sh [upload]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ps4-env.sh"
SRC="${DOLPHIN_SRC:-$PS4_BUILD_ROOT/src/dolphin}"
BUILD="$PS4_BUILD_ROOT/build/dolphin"
EBOOT="$BUILD/Source/Core/DolphinNoGUI/dolphin-nogui_eboot/eboot.bin"
VERSION="${DOLPHIN_PS4_VERSION:-01.00}"
HOST="ftp://${PS4_HOST:-192.168.0.90}:${PS4_FTP_PORT:-2121}"

[ -f "$EBOOT" ] || { echo "missing $EBOOT: build first" >&2; exit 1; }
STAGE="$PS4_BUILD_ROOT/build/dolphin-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/sce_sys"
cp "$EBOOT" "$STAGE/eboot.bin"
cp "$HERE/../sce_sys/icon0.png" "$STAGE/sce_sys/"
cp -r "$SRC/Data/Sys" "$STAGE/Sys"
# PkgTool's pkg_build crashes ("Sequence contains no elements") on these two folders. Themes are
# Qt GUI icons (unused here); Load holds optional graphics mods.
rm -rf "$STAGE/Sys/Themes" "$STAGE/Sys/Load"
# The XMB launcher's fonts and sounds (DolphinNoGUI/PS4XMB.cpp reads /app0/xmb).
cp -r "$HERE/../xmb" "$STAGE/xmb"
# The app version, for the logs and the XMB's About (PlatformPS4.cpp AppVersion).
echo "$VERSION" > "$STAGE/xmb/version.txt"
# Vulkan (RADV on GNM) runs under the plain homebrew identity (4.5 GiB of direct memory);
# SFO_STYLE=retroarch + PS4_PAID 0x3100000000000002 for the OpenGL (Piglet) backend.
# PS4_TITLE_ID / PS4_APP_NAME / PS4_CONTENT_LABEL: experimental builds install as a separate app
# ("Dolphin Lab", DLPH00011) next to the normal one, which they never replace.
PKG="$(SFO_STYLE="${SFO_STYLE:-plain}" "$HERE/make-pkg.sh" "$STAGE" "${PS4_TITLE_ID:-DLPH00010}"     "${PS4_APP_NAME:-Dolphin}" "$VERSION" "${PS4_CONTENT_LABEL:-DOLPHIN}" "$PS4_BUILD_ROOT/out" | tail -1)"
ls -la "$PKG"
# Keep the symbols of every packaged build: profiles and crash logs from the console must be
# symbolized against the exact binary that produced them, not a later rebuild.
mkdir -p "$PS4_BUILD_ROOT/oelf"
cp "${EBOOT%/eboot.bin}/dolphin-nogui.oelf" "$PS4_BUILD_ROOT/oelf/v$VERSION.oelf"
if [ "${1:-}" = upload ]; then
    curl -sS -T "$PKG" "$HOST/data/pkg/"
    echo "uploaded $(basename "$PKG")"
fi
