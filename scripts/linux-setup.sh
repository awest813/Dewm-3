#!/usr/bin/env bash
# linux-setup.sh — install dependencies, configure, and build dhewm3 for Linux.
#
# Usage:
#   ./scripts/linux-setup.sh           # auto-detects x86_64 or arm64
#   ./scripts/linux-setup.sh x86_64    # force 64-bit Intel/AMD build
#   ./scripts/linux-setup.sh arm64     # force 64-bit ARM build
#   ./scripts/linux-setup.sh release   # optimised portable release build
#
# Supported distros (dependency install):
#   Debian / Ubuntu (apt)
#   Fedora / RHEL / CentOS Stream (dnf)
#   Arch Linux / Manjaro (pacman)
#   openSUSE Tumbleweed / Leap (zypper)
#   Void Linux (xbps-install)
#   Gentoo (emerge) — packages listed; user must run manually
#
# On unsupported distros, install these manually then re-run with --no-deps:
#   cmake >= 3.21, gcc/clang, SDL2, openal-soft, libcurl, libbacktrace (optional)
#
# Options:
#   --no-deps    skip automatic dependency installation
#   --no-bundle  skip packaging step (just build; useful for dev iterations)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Parse arguments ────────────────────────────────────────────────────────────
SKIP_DEPS=false
SKIP_BUNDLE=false
ARCH_ARG=""

for arg in "$@"; do
  case "$arg" in
    --no-deps)   SKIP_DEPS=true ;;
    --no-bundle) SKIP_BUNDLE=true ;;
    x86_64|arm64|release) ARCH_ARG="$arg" ;;
    -*)
      echo "Unknown option: $arg"
      echo "Usage: $0 [x86_64|arm64|release] [--no-deps] [--no-bundle]"
      exit 1
      ;;
  esac
done

# ── 1. Detect distribution and install dependencies ───────────────────────────
install_deps_debian() {
  echo "==> Installing build dependencies (apt)…"
  sudo apt-get update -q
  sudo apt-get install -y \
    git cmake build-essential \
    libsdl2-dev libopenal-dev libcurl4-openssl-dev \
    libbacktrace-dev 2>/dev/null \
    || sudo apt-get install -y \
         git cmake build-essential \
         libsdl2-dev libopenal-dev libcurl4-openssl-dev
}

install_deps_fedora() {
  echo "==> Installing build dependencies (dnf)…"
  sudo dnf install -y \
    git cmake gcc-c++ make \
    SDL2-devel openal-soft-devel libcurl-devel
}

install_deps_arch() {
  echo "==> Installing build dependencies (pacman)…"
  sudo pacman -Sy --noconfirm \
    git cmake base-devel \
    sdl2 openal libcurl-gnutls
}

install_deps_suse() {
  echo "==> Installing build dependencies (zypper)…"
  sudo zypper install -y \
    git cmake gcc-c++ make \
    libSDL2-devel openal-soft-devel libcurl-devel
}

install_deps_void() {
  echo "==> Installing build dependencies (xbps-install)…"
  sudo xbps-install -Sy \
    git cmake gcc make \
    SDL2-devel openal-soft-devel libcurl-devel
}

install_deps_gentoo() {
  echo "==> Gentoo detected. Please install the following packages manually:"
  echo "    dev-vcs/git dev-build/cmake"
  echo "    media-libs/libsdl2 media-libs/openal media-libs/libsdl2"
  echo "    net-misc/curl"
  echo ""
  echo "Then re-run this script with --no-deps."
  exit 0
}

if [[ "$SKIP_DEPS" == "false" ]]; then
  if command -v apt-get &>/dev/null; then
    install_deps_debian
  elif command -v dnf &>/dev/null; then
    install_deps_fedora
  elif command -v pacman &>/dev/null; then
    install_deps_arch
  elif command -v zypper &>/dev/null; then
    install_deps_suse
  elif command -v xbps-install &>/dev/null; then
    install_deps_void
  elif command -v emerge &>/dev/null; then
    install_deps_gentoo
  else
    echo "WARNING: Unknown package manager. Skipping automatic dependency install."
    echo "         Install cmake, SDL2, openal-soft, and libcurl manually, then"
    echo "         re-run this script with --no-deps."
  fi
fi

# ── 2. Select CMake preset ────────────────────────────────────────────────────
if [[ -n "$ARCH_ARG" ]]; then
  case "$ARCH_ARG" in
    x86_64)  PRESET="linux-x86_64"  ;;
    arm64)   PRESET="linux-arm64"   ;;
    release) PRESET="linux-release" ;;
  esac
else
  HOST_ARCH="$(uname -m)"
  case "$HOST_ARCH" in
    x86_64)           PRESET="linux-x86_64" ;;
    aarch64|arm64)    PRESET="linux-arm64"  ;;
    *)
      echo "Unknown host architecture '$HOST_ARCH'."
      echo "Pass an explicit target: x86_64 | arm64 | release"
      exit 1
      ;;
  esac
  echo "==> Detected host CPU: $HOST_ARCH  →  using preset '$PRESET'"
fi

BUILD_DIR="$REPO_ROOT/build"
if [[ "$PRESET" == "linux-release" ]]; then
  BUILD_DIR="$REPO_ROOT/build-release"
fi

# ── 3. Configure ──────────────────────────────────────────────────────────────
echo "==> Configuring (preset: $PRESET)…"
cmake -S "$REPO_ROOT/neo" --preset "$PRESET" -B "$BUILD_DIR"

# ── 4. Build ──────────────────────────────────────────────────────────────────
echo "==> Building…"
NPROC="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
cmake --build "$BUILD_DIR" --parallel "$NPROC"

# ── 5. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Verifying binary…"
file "$BUILD_DIR/dhewm3"

echo ""
echo "Build successful!  Binary: $BUILD_DIR/dhewm3"
echo ""

# ── 6. Package (tarball / AppImage) ───────────────────────────────────────────
if [[ "$SKIP_BUNDLE" == "false" ]]; then
  echo "==> Packaging dhewm3…"
  "$REPO_ROOT/scripts/linux-package.sh" "$BUILD_DIR"
fi

echo ""
echo "To launch dhewm3, run:"
echo "  ./scripts/linux-run.sh"
echo "Or supply your Doom 3 data path directly:"
echo "  ./scripts/linux-run.sh /path/to/doom3/"
