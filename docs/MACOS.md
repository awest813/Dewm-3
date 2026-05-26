# macOS support (Apple Silicon & Intel)

This fork of dhewm3 is being modernized as a stable build for current macOS,
with **Apple Silicon (arm64) as the primary target** and **Intel (x86_64) as a
secondary, best-effort target**.

## Support matrix

| Architecture        | Status              | Minimum macOS | Notes                                             |
| ------------------- | ------------------- | ------------- | ------------------------------------------------- |
| `arm64` (Apple Silicon) | **Primary**     | 11.0 (Big Sur) | Default for builds on Apple Silicon hosts.        |
| `x86_64` (Intel)    | Secondary, optional | 10.15 (Catalina) | Builds and runs; not all maintainers test it.   |
| Universal (`arm64;x86_64`) | Opt-in, release-only | 11.0       | Used for distributable release builds only.       |
| `i386` / `ppc`      | **Unsupported**     | -             | Removed; modern macOS cannot run these binaries.  |

The build system enforces these via canonical CMake variables
(`CMAKE_OSX_ARCHITECTURES`, `CMAKE_OSX_DEPLOYMENT_TARGET`). Requesting any
other architecture produces an actionable CMake error.

### Universal binary policy

Universal binaries are **not** built by default. They roughly double build
time and binary size and are only worthwhile for distributable releases.
Maintainers cutting a release should produce a universal binary explicitly
(see "Release builds" below). Day-to-day development should use a single-arch
build matching the host.

> **Note:** Doom 3 savegames embed the build's CPU architecture string. A
> universal binary will report the slice it was launched as, which is fine for
> normal play but means a savegame written on arm64 may print a warning when
> loaded on x86_64 (and vice versa). This matches upstream dhewm3 behavior.

## Building

### Prerequisites

Install [Homebrew](https://brew.sh) and the runtime dependencies:

```sh
brew install cmake openal-soft sdl2 curl
```

The build system auto-detects Homebrew at either `/opt/homebrew` (Apple
Silicon) or `/usr/local` (Intel) and configures `find_package()` accordingly.
You no longer need to pass `-DOPENAL_LIBRARY=...` / `-DOPENAL_INCLUDE_DIR=...`
manually in the common case.

### Apple Silicon (default on an M-series Mac)

```sh
cmake -S neo -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel
```

### Intel (default on an Intel Mac, or cross-build from arm64)

```sh
cmake -S neo -B build \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_ARCHITECTURES=x86_64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=10.15
cmake --build build --parallel
```

> Cross-building to x86_64 from an Apple Silicon host requires an x86_64
> Homebrew installation under `/usr/local` (Homebrew does not provide x86_64
> bottles under `/opt/homebrew`). If you only have arm64 Homebrew installed,
> run the Intel build on an Intel host or in a Rosetta shell with a separate
> x86_64 Homebrew.

## Maintainer guide: release builds

For distributable releases, produce a universal binary explicitly:

```sh
cmake -S neo -B build-release \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
  -DREPRODUCIBLE_BUILD=ON
cmake --build build-release --parallel
```

Verify the resulting binary contains both slices:

```sh
file build-release/dhewm3
lipo -info build-release/dhewm3
```

You should see both `x86_64` and `arm64` listed.

For a universal release the x86_64 Homebrew prefix (`/usr/local`) must
contain x86_64 builds of `openal-soft` and `sdl2`. The typical approach is to
build the universal binary on an Intel Mac with arm64 cross-compile support,
or to assemble the universal binary from per-arch builds using `lipo`.

## CI

GitHub Actions builds this fork on every push/PR via
[`.github/workflows/macos.yml`](../.github/workflows/macos.yml):

- `macos-14` runner builds the arm64 slice (primary).
- `macos-13` runner builds the x86_64 slice (secondary).

Both jobs run a configure → build → basic smoke step (`dhewm3 -h`) and upload
the resulting binary as an artifact.

## Troubleshooting

- **`OpenAL not found`** — install with `brew install openal-soft`. The build
  system auto-discovers Homebrew's keg-only openal-soft; if it still fails,
  pass `-DCMAKE_PREFIX_PATH="$(brew --prefix openal-soft);$(brew --prefix sdl2)"`.
- **`SDL2 not found`** — `brew install sdl2`. As above, the build auto-detects
  the Homebrew prefix.
- **"Unsupported macOS architecture" CMake error** — pass a supported value:
  `-DCMAKE_OSX_ARCHITECTURES=arm64` or `=x86_64` (or `"arm64;x86_64"` for
  universal). `i386` and `ppc` are no longer supported.
- **Build picks up the wrong Homebrew prefix** — set `-DHOMEBREW_PREFIX=...`
  on the CMake command line to force a specific prefix.
- **`dhewm3 -h` prints nothing in CI** — some shells route output oddly; the
  CI logs capture stderr too, check there.
