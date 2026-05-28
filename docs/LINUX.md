# Linux support (x86_64 & arm64)

This fork of dhewm3 ships first-class Linux support alongside its macOS focus.
**x86_64** is the primary Linux target; **arm64** (aarch64) is a supported secondary target.

---

## Fastest way to run on Linux

> **Quick start — no script required.**

1. **Get Doom 3 game data** — buy *DOOM 3* on [Steam](https://store.steampowered.com/app/208200/DOOM_3/) or GOG and install it. You need patch 1.3.1; the Steam version is already patched.

2. **Download the latest tarball** from the [Releases page](../../releases/latest):
   - `dhewm3-linux-x86_64.tar.gz` — 64-bit Intel/AMD
   - `dhewm3-linux-arm64.tar.gz` — 64-bit ARM (Raspberry Pi 4/5, Ampere, etc.)

3. **Extract and run:**

   ```sh
   tar -xzf dhewm3-linux-x86_64.tar.gz
   cd dhewm3
   ./dhewm3 +set fs_basepath /path/to/doom3/
   ```

That's it. The rest of this document covers build-from-source, CMake presets, and CI.

---

## Quick start (build from source)

```sh
# 1. Install dependencies (Debian/Ubuntu shown; see "Prerequisites" for others):
sudo apt install cmake build-essential libsdl2-dev libopenal-dev libcurl4-openssl-dev

# 2. Build — auto-detects your CPU, compiles dhewm3, and creates a tarball:
./scripts/linux-setup.sh

# 3. Launch:
./scripts/linux-run.sh                       # auto-discover game data
./scripts/linux-run.sh /path/to/doom3/       # explicit path
```

---

## Support matrix

| Architecture     | Status              | Minimum glibc | Notes                                              |
| ---------------- | ------------------- | ------------- | -------------------------------------------------- |
| `x86_64`         | **Primary**         | 2.31 (Ubuntu 20.04+) | Default for most desktop and server Linux. |
| `arm64` / `aarch64` | Supported        | 2.31          | Raspberry Pi 4/5, Ampere, AWS Graviton, etc.       |
| `x86` (32-bit)   | Best-effort         | —             | Use `cmake -DCMAKE_C_FLAGS=-m32` if needed.        |
| `armhf` (32-bit ARM) | Best-effort    | —             | Community-supported; not CI-tested.                |

---

## Game data

dhewm3 is an engine; it needs the original Doom 3 game data (version 1.3.1) to run.

### Where to get it

- **Steam** — buy *DOOM 3* at <https://store.steampowered.com/app/208200/DOOM_3/>.
  After installing on Linux, data lives in:
  `~/.local/share/Steam/steamapps/common/Doom 3/`
- **GOG / disc** — install and note the folder. It must contain a `base/`
  subfolder with `pak000.pk4` through `pak008.pk4`.

### How dhewm3 finds the data

`./scripts/linux-run.sh` checks these locations in order:

1. Saved path (`~/.local/share/dhewm3/gamepath`) from a previous run.
2. Path given on the command line.
3. `~/.local/share/Steam/steamapps/common/Doom 3`
4. `~/.steam/steam/steamapps/common/Doom 3` (legacy Steam symlink location)
5. Flatpak Steam: `~/.var/app/com.valvesoftware.Steam/…/Doom 3`
6. Extra Steam library roots parsed from `libraryfolders.vdf`
7. `~/Games/Doom 3`, `~/games/doom3`, `/usr/local/games/doom3`, `/opt/doom3`

If none are found, the script prints the path to supply manually:

```sh
./scripts/linux-run.sh /path/to/doom3/
```

You can also pass the path directly to the binary:

```sh
./build/dhewm3 +set fs_basepath /path/to/doom3/
```

---

## Building

### Prerequisites

Install the required libraries using your distribution's package manager:

**Debian / Ubuntu**
```sh
sudo apt install cmake build-essential libsdl2-dev libopenal-dev libcurl4-openssl-dev
```

**Fedora / RHEL / CentOS Stream**
```sh
sudo dnf install cmake gcc-c++ make SDL2-devel openal-soft-devel libcurl-devel
```

**Arch Linux / Manjaro**
```sh
sudo pacman -S cmake base-devel sdl2 openal libcurl-gnutls
```

**openSUSE**
```sh
sudo zypper install cmake gcc-c++ make libSDL2-devel openal-soft-devel libcurl-devel
```

**Void Linux**
```sh
sudo xbps-install cmake gcc make SDL2-devel openal-soft-devel libcurl-devel
```

`libbacktrace` is optional but provides better crash backtraces:

```sh
# Debian/Ubuntu
sudo apt install libbacktrace-dev
```

### Using the setup script (recommended)

```sh
./scripts/linux-setup.sh           # auto-detects x86_64 or arm64
./scripts/linux-setup.sh x86_64    # force 64-bit Intel/AMD
./scripts/linux-setup.sh arm64     # force 64-bit ARM
./scripts/linux-setup.sh release   # optimised portable build (RPATH=$ORIGIN/libs/)
./scripts/linux-setup.sh --no-deps # skip package manager step
```

### Using CMake presets directly

Named presets are defined in `neo/CMakePresets.json` (requires CMake 3.21+):

```sh
# x86_64
cmake -S neo --preset linux-x86_64
cmake --build build --parallel

# arm64
cmake -S neo --preset linux-arm64
cmake --build build --parallel

# Portable release build
cmake -S neo --preset linux-release
cmake --build build-release --parallel
```

| Preset           | Arch       | Build type       | Build dir       |
| ---------------- | ---------- | ---------------- | --------------- |
| `linux-x86_64`   | x86_64     | RelWithDebInfo   | `build/`        |
| `linux-arm64`    | arm64      | RelWithDebInfo   | `build/`        |
| `linux-release`  | host arch  | Release          | `build-release/`|

### Manual CMake invocation (without presets)

```sh
mkdir build && cd build
cmake ../neo/ -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j$(nproc)
./dhewm3 +set fs_basepath /path/to/doom3/
```

For a portable release binary with bundled library support:

```sh
mkdir build-release && cd build-release
cmake ../neo/ -DCMAKE_BUILD_TYPE=Release -DLINUX_RELEASE_BINS=ON
make -j$(nproc)
```

With `LINUX_RELEASE_BINS=ON`, the binary's RPATH is set to `$ORIGIN/libs/` so you can
place runtime `.so` files in a `libs/` directory next to the binary.

---

## Quick verification

After a successful build:

```sh
# 1. Check the binary exists and is the right architecture
file build/dhewm3
# Expected: build/dhewm3: ELF 64-bit LSB executable, x86-64, …

# 2. Confirm runtime library dependencies
ldd build/dhewm3 | grep -E 'openal|SDL2|curl'
# Expected: lines pointing to system libraries

# 3. Smoke-test (exit code may be non-zero — that is normal)
./build/dhewm3 -h 2>&1 | head -5
```

---

## Packaging

`./scripts/linux-package.sh` creates a portable tarball from any build directory:

```sh
./scripts/linux-package.sh build          # produces dhewm3-linux-x86_64.tar.gz
./scripts/linux-package.sh build-release  # portable build
```

### AppImage

If [`appimagetool`](https://github.com/AppImage/AppImageKit/releases) is installed,
`linux-package.sh` also produces a self-contained `dhewm3-linux-<arch>.AppImage`:

```sh
# Download appimagetool and put it on PATH, then:
./scripts/linux-package.sh build
# → dhewm3-linux-x86_64.tar.gz  (always)
# → dhewm3-linux-x86_64.AppImage  (when appimagetool is found)
```

---

## CI

### `linux.yml` — continuous integration (every push / PR)

[`.github/workflows/linux.yml`](../.github/workflows/linux.yml)

| Job              | Runner           | Preset          | Status    |
| ---------------- | ---------------- | --------------- | --------- |
| Linux x86_64     | `ubuntu-22.04`   | `linux-x86_64`  | Primary   |
| Linux arm64      | `ubuntu-22.04-arm` | `linux-arm64` | Secondary |

Each job runs: install deps → configure with the named preset → build →
smoke check (`dhewm3 -h`) → package (tarball) → upload artifacts.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OpenAL not found` | `libopenal-dev` / `openal-soft-devel` not installed | Install via package manager; see Prerequisites above |
| `SDL2 not found` | `libsdl2-dev` not installed | `sudo apt install libsdl2-dev` (or distro equivalent) |
| `pak*.pk4 not found` at startup | `fs_basepath` points to wrong directory | Directory must contain `base/pak000.pk4`. Pass correct path: `./dhewm3 +set fs_basepath /path/to/doom3/` |
| `dhewm3 -h` exits non-zero | Expected — dhewm3 exits with code 1 after printing help | This is normal; check the output, not the exit code |
| Game crashes immediately | Missing runtime libs | Run `ldd build/dhewm3` and install any libraries marked `not found` |
| Permission denied running binary | Missing execute bit | `chmod +x build/dhewm3` |
| Wayland / display issues | SDL2 backend selection | Try `SDL_VIDEODRIVER=x11 ./dhewm3 …` or ensure `libsdl2-dev` is up to date |
| Saved path not used | XDG path mismatch | Check `~/.local/share/dhewm3/gamepath`; delete the file to reset |
