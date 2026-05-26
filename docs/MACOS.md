# macOS support (Apple Silicon & Intel)

This fork of dhewm3 is being modernized as a stable build for current macOS,
with **Apple Silicon (arm64) as the primary target** and **Intel (x86_64) as a
secondary, best-effort target**.

---

## Quick start

```sh
# 1. Install Homebrew (https://brew.sh) if you haven't already.

# 2. Build — installs deps, auto-detects your CPU, and compiles dhewm3:
./scripts/macos-setup.sh

# 3. Launch — auto-discovers Steam / GOG Doom 3 data:
./scripts/macos-run.sh

# Or supply your Doom 3 installation path directly:
./scripts/macos-run.sh /path/to/doom3/
```

That is all most users need. The rest of this document covers architecture
options, game-data setup, CMake presets, CI, troubleshooting, and releases.

---

## Support matrix

| Architecture              | Status              | Minimum macOS    | Notes                                            |
| ------------------------- | ------------------- | ---------------- | ------------------------------------------------ |
| `arm64` (Apple Silicon)   | **Primary**         | 11.0 (Big Sur)   | Default for builds on Apple Silicon hosts.       |
| `x86_64` (Intel)          | Secondary, optional | 10.15 (Catalina) | Builds and runs; not all maintainers test it.    |
| Universal (`arm64;x86_64`)| Opt-in, release-only| 11.0             | Used for distributable release builds only.      |
| `i386` / `ppc`            | **Unsupported**     | —                | Removed; modern macOS cannot run these binaries. |

The build system enforces these via canonical CMake variables
(`CMAKE_OSX_ARCHITECTURES`, `CMAKE_OSX_DEPLOYMENT_TARGET`). Requesting any
other architecture produces an actionable CMake error.

### Universal binary policy

Universal binaries are **not** built by default. They roughly double build
time and binary size and are only worthwhile for distributable releases.
Maintainers cutting a release should produce a universal binary explicitly
(see [Release builds](#release-builds) below). Day-to-day development should
use a single-arch build matching the host.

> **Note:** Doom 3 savegames embed the build's CPU architecture string. A
> universal binary will report the slice it was launched as, which is fine for
> normal play but means a savegame written on arm64 may print a warning when
> loaded on x86_64 (and vice versa). This matches upstream dhewm3 behavior.

---

## Game data

dhewm3 is an engine; it needs the original Doom 3 game data (version 1.3.1) to
run. The data is **not** included in this repository.

### Where to get it

- **Steam** — buy *DOOM 3* at <https://store.steampowered.com/app/208200/DOOM_3/>.
  After installing, data lives in:  
  `~/Library/Application Support/Steam/steamapps/common/Doom 3/`
- **GOG / disc** — install and note the folder. It must contain a `base/`
  subfolder with `pak000.pk4` through `pak008.pk4`.
- **Patching** — if your copy predates patch 1.3.1, see the
  [dhewm3 FAQ](https://github.com/dhewm/dhewm3/wiki/FAQ) for patching
  instructions, including how to extract data from Steam on another OS.

### How dhewm3 finds the data

`./scripts/macos-run.sh` checks these locations in order:

1. Path given on the command line.
2. `~/Library/Application Support/Steam/steamapps/common/Doom 3`
3. `/Volumes/Steam/steamapps/common/Doom 3` (external Steam library)
4. `~/Games/Doom 3`
5. `/Applications/Doom 3`

If none are found, the script prints the path to supply manually:

```sh
./scripts/macos-run.sh /path/to/doom3/
```

You can also pass the path directly to the binary:

```sh
./build/dhewm3 +set fs_basepath /path/to/doom3/
```

---

## Building

### Prerequisites

Install [Homebrew](https://brew.sh) and the runtime dependencies:

```sh
brew install cmake openal-soft sdl2 curl
```

The build system auto-detects Homebrew at either `/opt/homebrew` (Apple
Silicon) or `/usr/local` (Intel) and configures `find_package()` accordingly.
You do **not** need to pass `-DOPENAL_LIBRARY=...` / `-DOPENAL_INCLUDE_DIR=...`
manually.

### Using the setup script (recommended)

```sh
./scripts/macos-setup.sh           # auto-detects arm64 or x86_64
./scripts/macos-setup.sh arm64     # force Apple Silicon
./scripts/macos-setup.sh x86_64    # force Intel
./scripts/macos-setup.sh universal # universal binary (release use only)
```

### Using CMake presets directly

Named presets are defined in `neo/CMakePresets.json` (requires CMake 3.21+,
which Homebrew provides):

```sh
# Apple Silicon
cmake -S neo --preset macos-arm64
cmake --build build --parallel

# Intel
cmake -S neo --preset macos-intel
cmake --build build --parallel
```

| Preset            | Arch              | Min macOS | Build dir       |
| ----------------- | ----------------- | --------- | --------------- |
| `macos-arm64`     | `arm64`           | 11.0      | `build/`        |
| `macos-intel`     | `x86_64`          | 10.15     | `build/`        |
| `macos-universal` | `arm64;x86_64`    | 11.0      | `build-release/`|

### Manual CMake invocation (without presets)

All presets translate to plain `-D` flags if needed:

```sh
# Apple Silicon
cmake -S neo -B build \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0
cmake --build build --parallel

# Intel (native or from Rosetta)
cmake -S neo -B build \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_ARCHITECTURES=x86_64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=10.15
cmake --build build --parallel
```

> Cross-building to x86_64 from an Apple Silicon host requires an x86_64
> Homebrew installation under `/usr/local` (Homebrew does not provide x86_64
> bottles under `/opt/homebrew`). If you only have arm64 Homebrew, run the
> Intel build on an Intel host or in a Rosetta shell with a separate x86_64
> Homebrew.

---

## Quick verification

After a successful build, run these commands to confirm everything is working:

```sh
# 1. Check the binary exists and is the right architecture
file build/dhewm3
# Expected (Apple Silicon): build/dhewm3: Mach-O 64-bit executable arm64
# Expected (Intel):          build/dhewm3: Mach-O 64-bit executable x86_64

# 2. Confirm it links correctly and prints usage
./build/dhewm3 -h 2>&1 | head -5
# Expected: a short usage/help message (exit code may be non-zero — that is normal)

# 3. Verify Homebrew dylibs are found
otool -L build/dhewm3 | grep -E 'openal|sdl2|SDL2|curl'
# Expected: lines pointing to Homebrew paths like /opt/homebrew/… or /usr/local/…
```

For a universal binary (release builds):

```sh
file build-release/dhewm3
# Expected: build-release/dhewm3: Mach-O universal binary with 2 architectures: [x86_64:…] [arm64:…]
lipo -info build-release/dhewm3
# Expected: Architectures in the fat file: build-release/dhewm3 are: x86_64 arm64
```

---

## CI

GitHub Actions builds this fork on every push/PR via
[`.github/workflows/macos.yml`](../.github/workflows/macos.yml):

| Job                         | Runner      | Preset         | Status    |
| --------------------------- | ----------- | -------------- | --------- |
| macOS arm64 (Apple Silicon) | `macos-14`  | `macos-arm64`  | Primary   |
| macOS x86_64 (Intel)        | `macos-13`  | `macos-intel`  | Secondary |

Each job runs: install deps → configure with the named preset → build →
smoke check (`dhewm3 -h`) → upload binary as an artifact
(`dhewm3-macos-arm64` or `dhewm3-macos-x86_64`).

Artifacts from passing CI runs are downloadable from the **Actions** tab and
are the recommended way for users to get pre-built binaries without compiling.

---

## Release builds

For distributable releases, produce a universal binary using the
`macos-universal` preset (or the setup script):

```sh
# Via script
./scripts/macos-setup.sh universal

# Via preset
cmake -S neo --preset macos-universal
cmake --build build-release --parallel
```

Verify the result:

```sh
file build-release/dhewm3
lipo -info build-release/dhewm3
# Both x86_64 and arm64 must be listed.
```

> For a universal release the x86_64 Homebrew prefix (`/usr/local`) must
> contain x86_64 builds of `openal-soft` and `sdl2`. The typical approach is
> to build on an Intel Mac (which can also cross-compile to arm64), or to
> assemble the universal binary from per-arch builds using `lipo`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OpenAL not found` | `openal-soft` not installed or not found | `brew install openal-soft`; if it still fails: `cmake -S neo --preset macos-arm64 -DCMAKE_PREFIX_PATH="$(brew --prefix openal-soft)"` |
| `SDL2 not found` | `sdl2` not installed | `brew install sdl2` |
| `"Unsupported macOS architecture"` CMake error | Passing an unsupported `-DCMAKE_OSX_ARCHITECTURES` value | Use `arm64`, `x86_64`, or `"arm64;x86_64"`. `i386` and `ppc` are not supported. |
| Build picks up wrong Homebrew prefix | Non-standard Homebrew install | `cmake -S neo --preset macos-arm64 -DHOMEBREW_PREFIX=/your/brew/prefix` |
| `dhewm3 -h` exits non-zero | Expected — dhewm3 exits with code 1 after printing help | This is normal; check the output, not the exit code. |
| `pak*.pk4 not found` at startup | `fs_basepath` points to wrong directory | Directory must contain `base/pak000.pk4`. Run `./scripts/macos-run.sh /correct/path/` |
| Game crashes immediately on arm64 | OpenAL Soft from Apple's SDK (not Homebrew) linked in | `brew install openal-soft`; confirm with `otool -L build/dhewm3 \| grep openal` that it links Homebrew's copy, not `/System/Library/…`. |
| Universal build missing x86_64 slice | x86_64 Homebrew deps absent | Install x86_64 Homebrew at `/usr/local` and ensure `openal-soft` and `sdl2` are present there. |
