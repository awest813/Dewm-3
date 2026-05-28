#!/usr/bin/env bash
# linux-package.sh — create a portable Linux tarball from a completed build.
#
# Usage (called automatically by linux-setup.sh, or manually):
#   ./scripts/linux-package.sh [BUILD_DIR]          # default: build/
#   ./scripts/linux-package.sh build-release/       # release build
#
# Output:
#   dhewm3-linux-<arch>.tar.gz  — portable tarball in the repo root
#
# The tarball contains:
#   dhewm3                       — engine binary
#   *.so                         — game libraries (base.so, d3xp.so, etc.)
#   run.sh                       — convenience launcher wrapper
#   README.txt                   — quick-start instructions
#
# To also build an AppImage, install appimagetool from
# https://github.com/AppImage/AppImageKit/releases and re-run this script;
# it will detect appimagetool automatically.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${1:-$REPO_ROOT/build}"
BINARY="$BUILD_DIR/dhewm3"

# ── Validate build ────────────────────────────────────────────────────────────
if [[ ! -x "$BINARY" ]]; then
  echo "Error: dhewm3 binary not found at $BINARY"
  echo "Run ./scripts/linux-setup.sh first to build it."
  exit 1
fi

# ── Determine arch ────────────────────────────────────────────────────────────
ARCH="$(file "$BINARY" | grep -oP '(?<=ELF 64-bit LSB )\S+' | head -1 || uname -m)"
case "$ARCH" in
  x86-64|x86_64) ARCH="x86_64" ;;
  aarch64|arm64)  ARCH="arm64"  ;;
  *)              ARCH="$(uname -m)" ;;
esac

echo "==> Packaging dhewm3 (arch: $ARCH)…"

# ── Staging directory ─────────────────────────────────────────────────────────
STAGING="$(mktemp -d)"
STAGE_DIR="$STAGING/dhewm3"
mkdir -p "$STAGE_DIR"

# Engine binary
cp "$BINARY" "$STAGE_DIR/dhewm3"
chmod +x "$STAGE_DIR/dhewm3"

# Game shared libraries (.so) from the build directory
find "$BUILD_DIR" -maxdepth 1 -name "*.so" -exec cp {} "$STAGE_DIR/" \;

# Convenience launcher
cat > "$STAGE_DIR/run.sh" <<'LAUNCHER'
#!/usr/bin/env bash
# Convenience launcher — run from any directory.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/dhewm3" +set fs_basepath "${1:-}" "$@"
LAUNCHER
chmod +x "$STAGE_DIR/run.sh"

# Quick-start README
cat > "$STAGE_DIR/README.txt" <<'README'
dhewm3 — Linux build
====================

Requirements:
  - Doom 3 game data (version 1.3.1)
    Buy on Steam: https://store.steampowered.com/app/208200/DOOM_3/
    The folder must contain a "base/" subfolder with pak000.pk4 … pak008.pk4.
  - Runtime libraries: libSDL2, libopenal (openal-soft), libcurl
    Install via your package manager if you don't have them:
      Debian/Ubuntu:  sudo apt install libsdl2-2.0-0 libopenal1 libcurl4
      Fedora:         sudo dnf install SDL2 openal-soft libcurl
      Arch:           sudo pacman -S sdl2 openal libcurl-gnutls

Quick start:
  ./dhewm3 +set fs_basepath /path/to/doom3/

Or use the convenience launcher:
  ./run.sh /path/to/doom3/

See https://github.com/awest813/Dewm-3/blob/main/docs/LINUX.md for full docs.
README

# ── Create tarball ────────────────────────────────────────────────────────────
TARBALL_NAME="dhewm3-linux-${ARCH}.tar.gz"
TARBALL_PATH="$REPO_ROOT/$TARBALL_NAME"

echo "==> Creating $TARBALL_NAME…"
tar -czf "$TARBALL_PATH" -C "$STAGING" dhewm3
rm -rf "$STAGING"

echo ""
echo "==> Done."
echo "    Tarball: $TARBALL_PATH"
echo ""

# ── Optional: AppImage ────────────────────────────────────────────────────────
if command -v appimagetool &>/dev/null; then
  echo "==> appimagetool found — building AppImage…"

  APPDIR="$(mktemp -d)/dhewm3.AppDir"
  mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib"

  cp "$BINARY" "$APPDIR/usr/bin/dhewm3"
  find "$BUILD_DIR" -maxdepth 1 -name "*.so" -exec cp {} "$APPDIR/usr/lib/" \;

  # AppRun entrypoint
  cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "$0")" && pwd)"
export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/bin/dhewm3" "$@"
APPRUN
  chmod +x "$APPDIR/AppRun"

  # .desktop file (required by AppImage spec)
  cat > "$APPDIR/dhewm3.desktop" <<'DESKTOP'
[Desktop Entry]
Name=dhewm3
Comment=Doom 3 GPL source port
Exec=dhewm3
Icon=dhewm3
Type=Application
Categories=Game;Shooter;
DESKTOP

  # Icon — use upstream SVG if available, otherwise skip
  if [[ -f "$REPO_ROOT/dist/linux/share/icons/hicolor/scalable/apps/org.dhewm3.Dhewm3.svg" ]]; then
    cp "$REPO_ROOT/dist/linux/share/icons/hicolor/scalable/apps/org.dhewm3.Dhewm3.svg" \
       "$APPDIR/dhewm3.svg"
  fi

  APPIMAGE_PATH="$REPO_ROOT/dhewm3-linux-${ARCH}.AppImage"
  ARCH="$ARCH" appimagetool "$APPDIR" "$APPIMAGE_PATH"
  chmod +x "$APPIMAGE_PATH"
  rm -rf "$(dirname "$APPDIR")"

  echo "    AppImage: $APPIMAGE_PATH"
else
  echo "NOTE: appimagetool not found — skipping AppImage creation."
  echo "      Download from https://github.com/AppImage/AppImageKit/releases"
  echo "      to produce a self-contained AppImage alongside the tarball."
fi
