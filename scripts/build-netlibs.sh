#!/usr/bin/env bash
# Network shares (DolphinNoGUI/PS4NetFS.cpp): libnfs (NFS v3/v4) and libsmb2 (SMB 2/3), user-space
# clients (LGPL-2.1+), built static with Dolphin's PS4 toolchain into PS4_SYSROOT.
#   build-netlibs.sh        (sources: ~/dolphinps4-build/src/libnfs, src/libsmb2 from GitHub sahlberg/)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/ps4-env.sh"
SYSROOT="${PS4_SYSROOT:-$PS4_BUILD_ROOT/sysroot}"
TOOLCHAIN="$HERE/../toolchain/ps4-love-modern.cmake"
LIBNFS_REVISION=7613236464317bee2d9636f087f995148de4db27
build() {
    local name="$1"; shift
    local build="$PS4_BUILD_ROOT/build/$name"
    rm -rf "$build"
    mkdir -p "$build"
    env -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u LDFLAGS -u LIBS \
        cmake -S "$PS4_BUILD_ROOT/src/$name" -B "$build" -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_INSTALL_PREFIX="$SYSROOT" \
        -DBUILD_SHARED_LIBS=OFF "$@" > "$build.configure.log" 2>&1 ||
        { tail -30 "$build.configure.log"; exit 1; }
    ninja -C "$build" install > "$build.build.log" 2>&1 || { grep -B2 -A8 "error" "$build.build.log" | head -60; exit 1; }
    echo "$name: built"
}

libnfs_source="$PS4_BUILD_ROOT/src/libnfs"
if [[ ! -d "$libnfs_source/.git" ]]; then
    echo "Missing libnfs Git checkout: $libnfs_source" >&2
    exit 1
fi
actual_revision="$(git -C "$libnfs_source" rev-parse HEAD)"
if [[ "$actual_revision" != "$LIBNFS_REVISION" ]]; then
    echo "libnfs must be at $LIBNFS_REVISION (found $actual_revision)" >&2
    exit 1
fi

for lib in libnfs libsmb2; do
    source="$PS4_BUILD_ROOT/src/$lib"
    patch="$HERE/../patches/$lib-ps4.patch"
    if [[ ! -d "$source/.git" ]]; then
        echo "Missing $lib Git checkout: $source" >&2
        exit 1
    fi
    if git -C "$source" apply --check "$patch" >/dev/null 2>&1; then
        continue
    elif git -C "$source" apply --reverse --check "$patch" >/dev/null 2>&1; then
        echo "$lib: PS4 patch already applied"
    else
        echo "Cannot apply $patch to $source (or patch is partially applied)" >&2
        exit 1
    fi
done

for lib in libnfs libsmb2; do
    source="$PS4_BUILD_ROOT/src/$lib"
    patch="$HERE/../patches/$lib-ps4.patch"
    if git -C "$source" apply --check "$patch" >/dev/null 2>&1; then
        git -C "$source" apply "$patch"
    fi
done
build libsmb2 -DENABLE_EXAMPLES=OFF -DENABLE_UTILS=OFF -DENABLE_LIBKRB5=OFF -DENABLE_GSSAPI=OFF \
    -DENABLE_LIBDCERPC=OFF
build libnfs -DENABLE_TESTS=OFF -DENABLE_DOCUMENTATION=OFF -DENABLE_UTILS=OFF -DENABLE_EXAMPLES=OFF \
    -DENABLE_MULTITHREADING=OFF
ls -la "$SYSROOT/lib/libsmb2.a" "$SYSROOT/lib/libnfs.a"
