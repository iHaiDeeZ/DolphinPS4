# Building Dolphin for PS4

Dolphin for PS4 cross-compiles in **WSL (Ubuntu)** into a PS4 package (`.pkg`). You don't need a
console to build, but you need one to run the result.

## What you need

- **WSL 2 with Ubuntu** (or Linux).
- **clang 21** with `lld`, `llvm-ar`, **cmake**, **ninja**, **python3** (with Pillow), **git**
  and **curl**.
- The **OpenOrbis** PS4 toolchain from **PacBrew**, installed in `/opt/pacbrew/ps4/openorbis`
  (set `OPENORBIS` if yours is elsewhere).
- For Mesa: **meson**, **mako** and **pyyaml** (the scripts use a venv in the build tree) and a
  host `glslangValidator`.

## Where things go

The build tree lives in WSL, at `~/dolphinps4-build` (`PSB` in
[`toolchain/env.sh`](toolchain/env.sh)):

```
~/dolphinps4-build/
├── src/dolphin/   Dolphin, with patches/dolphin-ps4.patch applied
├── src/mesa/      Mesa 26.0.8, with patches/mesa-ps4.patch applied
├── sysroot/       libc++ and the runtime for the PS4 target
├── build/         build directories
└── out/           packages
```

## Steps

1. **Sysroot.** libc++ 21 for the PS4 target (this also prepares the header overlay), then the
   runtime pieces linked ahead of OpenOrbis' C library:

   ```sh
   toolchain/build-libcxx.sh
   toolchain/build-runtime.sh
   ```

2. **Dolphin source.** Check out the revision the patch is made against and apply it:

   ```sh
   git clone https://github.com/dolphin-emu/dolphin ~/dolphinps4-build/src/dolphin
   cd ~/dolphinps4-build/src/dolphin
   git checkout 771fb154059c5812d6a715a23226249cc42877a2
   git submodule update --init --recursive
   git apply /path/to/DolphinPS4/patches/dolphin-ps4.patch
   ```

3. **Mesa (RADV for the PS4 GPU).** Put Mesa 26.0.8 in `~/dolphinps4-build/src/mesa`, apply
   [`patches/mesa-ps4.patch`](patches/mesa-ps4.patch), then:

   ```sh
   scripts/build-mesa.sh setup
   ```

   The GNM winsys that lets RADV submit to the PS4 GPU is in [`port/mesa`](port/mesa).

4. **Dolphin.**

   ```sh
   scripts/configure-dolphin.sh
   scripts/build-dolphin.sh
   ```

   Run `configure-dolphin.sh` again after changing CMake files or the toolchain.

5. **Network shares (optional).** Prepare the library sources and build their PS4 static
   libraries. The libnfs patch is maintained against a fixed revision; the build script rejects
   other revisions so it cannot silently skip an incompatible patch.

   ```sh
   mkdir -p ~/dolphinps4-build/src
   git clone https://github.com/sahlberg/libnfs.git ~/dolphinps4-build/src/libnfs
   git -C ~/dolphinps4-build/src/libnfs checkout 7613236464317bee2d9636f087f995148de4db27
   git clone https://github.com/sahlberg/libsmb2.git ~/dolphinps4-build/src/libsmb2
   scripts/build-netlibs.sh
   ```

6. **Package.** `DOLPHIN_PS4_VERSION` is the version shown under Settings → About:

   ```sh
   DOLPHIN_PS4_VERSION=02.95 scripts/package-dolphin.sh
   ```

   The package lands in `~/dolphinps4-build/out/`. Add `upload` to copy it to the console's
   `/data/pkg/` over FTP (`PS4_HOST` and `PS4_FTP_PORT` set the address).

Each script's comments explain its steps and options.

## What's in this repository

| Path | What |
|---|---|
| `patches/` | The changes to Dolphin and Mesa, and the base revisions (`BASE.txt`) |
| `port/` | PS4 runtime: startup, memory allocator, string routines, crash log, profiler; the Mesa GNM winsys |
| `toolchain/` | Compiler wrappers, CMake toolchain files, linker script, sysroot scripts |
| `scripts/` | Build, package and console scripts, and the asset generators (icon, menu sounds, start-up animation) |
| `xmb/` | Menu assets: fonts, sounds, start-up animation, built-in default settings, CA bundle |
| `sce_sys/` | App icon and its source artwork |
| `probe*/` | Small test apps used while bringing up the toolchain, Vulkan and GNM |
