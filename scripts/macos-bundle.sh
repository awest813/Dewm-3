#!/usr/bin/env bash
# macos-bundle.sh — assemble dhewm3.app from a completed build, then create a DMG.
#
# Usage (called automatically by macos-setup.sh, or manually):
#   ./scripts/macos-bundle.sh [BUILD_DIR]          # default: build/
#   ./scripts/macos-bundle.sh build-release/       # universal build
#
# Output:
#   dhewm3.app/           — Mac application bundle (in repo root)
#   dhewm3-<arch>.dmg     — drag-and-drop disk image for distribution

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${1:-$REPO_ROOT/build}"
BINARY="$BUILD_DIR/dhewm3"
PLIST_SRC="$REPO_ROOT/dist/macosx/Info.plist"
LAUNCHER_SRC="$REPO_ROOT/scripts/macos-firstrun.sh"
APP_DIR="$REPO_ROOT/dhewm3.app"

# ── Validate build ────────────────────────────────────────────────────────────
if [[ ! -x "$BINARY" ]]; then
  echo "Error: dhewm3 binary not found at $BINARY"
  echo "Run ./scripts/macos-setup.sh first to build it."
  exit 1
fi

# ── Determine arch suffix for the DMG name ────────────────────────────────────
ARCH_INFO="$(file "$BINARY")"
if echo "$ARCH_INFO" | grep -q "universal binary"; then
  ARCH_SUFFIX="universal"
elif echo "$ARCH_INFO" | grep -q "arm64"; then
  ARCH_SUFFIX="arm64"
else
  ARCH_SUFFIX="x86_64"
fi

echo "==> Assembling dhewm3.app (arch: $ARCH_SUFFIX)…"

# ── Build .app directory tree ─────────────────────────────────────────────────
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist
cp "$PLIST_SRC" "$APP_DIR/Contents/Info.plist"

# dhewm3 engine binary (renamed so the launcher can call it)
cp "$BINARY" "$APP_DIR/Contents/MacOS/dhewm3"

# Game library .dylibs (base.dylib, d3xp.dylib, etc.) if present
find "$BUILD_DIR" -maxdepth 1 -name "*.dylib" -exec cp {} "$APP_DIR/Contents/MacOS/" \;

# Launcher script (the CFBundleExecutable that macOS actually runs)
cp "$LAUNCHER_SRC" "$APP_DIR/Contents/MacOS/dhewm3-launcher"
chmod +x "$APP_DIR/Contents/MacOS/dhewm3-launcher"
chmod +x "$APP_DIR/Contents/MacOS/dhewm3"

# icns placeholder — use a simple copy from dist/ if it exists, otherwise skip
if [[ -f "$REPO_ROOT/dist/macosx/dhewm3.icns" ]]; then
  cp "$REPO_ROOT/dist/macosx/dhewm3.icns" "$APP_DIR/Contents/Resources/dhewm3.icns"
fi

echo "    $APP_DIR assembled."

# ── Create DMG ────────────────────────────────────────────────────────────────
DMG_NAME="dhewm3-${ARCH_SUFFIX}.dmg"
DMG_PATH="$REPO_ROOT/$DMG_NAME"

echo "==> Creating $DMG_NAME…"

# Temporary staging folder for the DMG contents
STAGING="$(mktemp -d)"
cp -R "$APP_DIR" "$STAGING/"
# Symlink /Applications so users can drag-and-drop
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "dhewm3" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGING"

echo ""
echo "==> Done."
echo "    App bundle : $APP_DIR"
echo "    Disk image : $DMG_PATH"
echo ""
echo "To distribute to users: share $DMG_NAME."
echo "Users open the DMG, drag dhewm3 to Applications, and double-click to play."
