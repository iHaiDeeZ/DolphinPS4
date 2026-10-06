#!/usr/bin/env bash
# Package the PS4 Dolphin build (after scripts/configure-dolphin.sh + ninja) as DLPH00010:
# eboot.bin, Dolphin's Data/Sys as /app0/Sys, and the Piglet/shader compiler modules.
#   package-dolphin.sh [upload]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ps4-env.sh"
# LAB COPY (experiment/split-cpu): builds the experimental Dolphin from src/dolphin-lab into
# build/dolphin-lab, packaged as the separate app "Dolphin Lab" (DLPH00011). The stable port is
# J:\DolphinPS4 with src/dolphin and build/dolphin; the two never share a build.
SRC="${DOLPHIN_SRC:-$PS4_BUILD_ROOT/src/dolphin-lab}"
BUILD="${DOLPHIN_BUILD:-$PS4_BUILD_ROOT/build/dolphin-lab}"
EBOOT="$BUILD/Source/Core/DolphinNoGUI/dolphin-nogui_eboot/eboot.bin"
VERSION="${DOLPHIN_PS4_VERSION:-01.00}"
HOST="ftp://${PS4_HOST:-192.168.0.90}:${PS4_FTP_PORT:-2121}"

[ -f "$EBOOT" ] || { echo "missing $EBOOT: build first" >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9][0-9]\.[0-9][0-9]$ ]] || { echo "version must look like 03.07" >&2; exit 1; }
# Lab: its own staging folder next to its build (never the stable app's).
STAGE="$BUILD-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/sce_sys"
# The version goes into the program itself (PlatformPS4.cpp ps4_built_version): a downloaded
# update tells itself apart from the installed program by it. Same length, so the ELF's layout
# doesn't change; create-fself then runs exactly as the build ran it.
ELF="$BUILD/Binaries/dolphin-emu-nogui"
# Same length as "Binaries": create-fself stores the input path, so the size check stays exact.
WORK="$BUILD/PkgEboot"
rm -rf "$WORK" && mkdir -p "$WORK"
python3 - "$ELF" "$WORK/dolphin-emu-nogui" "$VERSION" <<'PY'
import sys
src, dst, version = sys.argv[1:]
data = open(src, "rb").read()
old = b"DOLPHINPS4-VERSION:00.00"
assert data.count(old) == 1, "version marker found %d times" % data.count(old)
open(dst, "wb").write(data.replace(old, b"DOLPHINPS4-VERSION:" + version.encode()))
PY
FSELF_ARGS="$(grep -o -- '--paid [^ ]* --authinfo [^ ]*' "$BUILD/build.ninja" | head -1)"
[ -n "$FSELF_ARGS" ] || { echo "create-fself arguments not found in build.ninja" >&2; exit 1; }
# shellcheck disable=SC2086
OO_PS4_TOOLCHAIN=/opt/pacbrew/ps4/openorbis /opt/pacbrew/ps4/openorbis/bin/create-fself \
    -in="$WORK/dolphin-emu-nogui" -out="$WORK/dolphin-nogui.oelf" --eboot "$WORK/eboot.bin" \
    $FSELF_ARGS > "$WORK/create-fself.log"
[ "$(stat -c %s "$WORK/eboot.bin")" = "$(stat -c %s "$EBOOT")" ] || {
    echo "the versioned eboot.bin differs in size from the build's: not packaging" >&2; exit 1; }
cp "$WORK/eboot.bin" "$STAGE/eboot.bin"
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
PKG="$(SFO_STYLE="${SFO_STYLE:-plain}" "$HERE/make-pkg.sh" "$STAGE" "${PS4_TITLE_ID:-DLPH00011}"     "${PS4_APP_NAME:-Dolphin Lab}" "$VERSION" "${PS4_CONTENT_LABEL:-DOLPHINLAB}" "$PS4_BUILD_ROOT/out" | tail -1)"
ls -la "$PKG"
# The update archive for the in-app updater (PS4Updater.h): the program, the menu files and Sys,
# unpacked into /data/DolphinPS4/app. The Sony modules and sce_sys stay in the installed package.
UPDATE_TAR="$PS4_BUILD_ROOT/out/DolphinPS4-v$VERSION-update.tar"
tar --format=ustar -C "$STAGE" -cf "$UPDATE_TAR" eboot.bin xmb Sys
ls -la "$UPDATE_TAR"
# Keep the symbols of every packaged build: profiles and crash logs from the console must be
# symbolized against the exact binary that produced them, not a later rebuild.
mkdir -p "$PS4_BUILD_ROOT/oelf-lab"
cp "$WORK/dolphin-nogui.oelf" "$PS4_BUILD_ROOT/oelf-lab/v$VERSION.oelf"
if [ "${1:-}" = upload ]; then
    curl -sS -T "$PKG" "$HOST/data/pkg/"
    echo "uploaded $(basename "$PKG")"
fi
