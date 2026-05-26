#!/usr/bin/env bash
# macos-setup.sh — install dependencies, configure, and build dhewm3 for this Mac.
#
# Usage:
#   ./scripts/macos-setup.sh           # auto-detects arm64 or x86_64
#   ./scripts/macos-setup.sh arm64     # force Apple Silicon build
#   ./scripts/macos-setup.sh x86_64    # force Intel build
#   ./scripts/macos-setup.sh universal # build universal binary (release use only)
#
# Requires: Homebrew — https://brew.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 1. Check for Homebrew ────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  echo "Error: Homebrew is not installed."
  echo "Install it from https://brew.sh, then re-run this script."
  exit 1
fi

# ── 2. Install dependencies ──────────────────────────────────────────────────
echo "==> Installing build dependencies via Homebrew…"
brew install cmake openal-soft sdl2 curl

# ── 3. Select CMake preset ───────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
  REQUESTED="$1"
  case "$REQUESTED" in
    arm64)     PRESET="macos-arm64"    ;;
    x86_64)    PRESET="macos-intel"    ;;
    universal) PRESET="macos-universal" ;;
    *)
      echo "Unknown target '$REQUESTED'. Use: arm64 | x86_64 | universal"
      exit 1
      ;;
  esac
else
  # Auto-detect from host CPU
  HOST_ARCH="$(uname -m)"
  case "$HOST_ARCH" in
    arm64)  PRESET="macos-arm64"  ;;
    x86_64) PRESET="macos-intel"  ;;
    *)
      echo "Unknown host architecture '$HOST_ARCH'."
      echo "Pass an explicit target: arm64 | x86_64 | universal"
      exit 1
      ;;
  esac
  echo "==> Detected host CPU: $HOST_ARCH  →  using preset '$PRESET'"
fi

# Universal builds place artifacts in build-release/ instead of build/
if [[ "$PRESET" == "macos-universal" ]]; then
  BUILD_DIR="$REPO_ROOT/build-release"
else
  BUILD_DIR="$REPO_ROOT/build"
fi

# ── 4. Configure ─────────────────────────────────────────────────────────────
echo "==> Configuring (preset: $PRESET)…"
cmake -S "$REPO_ROOT/neo" --preset "$PRESET" -B "$BUILD_DIR"

# ── 5. Build ──────────────────────────────────────────────────────────────────
echo "==> Building…"
cmake --build "$BUILD_DIR" --parallel

# ── 6. Verify ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Verifying binary…"
file "$BUILD_DIR/dhewm3"

echo ""
echo "Build successful!  Binary: $BUILD_DIR/dhewm3"
echo ""
echo "To launch dhewm3, run:"
echo "  ./scripts/macos-run.sh"
echo "Or supply your Doom 3 data path directly:"
echo "  ./scripts/macos-run.sh /path/to/doom3/"
