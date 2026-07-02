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
#
# Homebrew dylibs (openal-soft, SDL2, curl) are bundled into
# dhewm3.app/Contents/Frameworks/ so the .app is fully self-contained and
# works on Macs that do not have Homebrew installed.  Requires dylibbundler:
#   brew install dylibbundler

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=macos-lib.sh
source "$REPO_ROOT/scripts/macos-lib.sh"

BUILD_DIR="${1:-$REPO_ROOT/build}"
BINARY="$(macos_engine_binary "$BUILD_DIR")" || BINARY=""
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
if [[ -z "$APP_DIR" || "$APP_DIR" == "/" ]]; then
  echo "Error: APP_DIR is empty or root — refusing to rm -rf."
  exit 1
fi
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist — inject version and correct minimum macOS version from git tag if available
cp "$PLIST_SRC" "$APP_DIR/Contents/Info.plist"
GIT_VERSION="$(git -C "$REPO_ROOT" describe --tags --abbrev=0 2>/dev/null || true)"
GIT_VERSION="${GIT_VERSION#v}"  # strip leading 'v' if present

# Determine the correct LSMinimumSystemVersion for this binary:
#   x86_64-only builds support macOS 10.15 (Catalina); all others use 11.0 (Big Sur).
MIN_MACOS="11.0"
if [[ "$ARCH_SUFFIX" == "x86_64" ]]; then
  MIN_MACOS="10.15"
fi

# Edit the plist with PlistBuddy, which ships with every macOS (unlike python3,
# which on a clean install is only a stub that prompts for the Command Line
# Tools).  All three keys already exist in dist/macosx/Info.plist.
PLIST_BUDDY="/usr/libexec/PlistBuddy"
PLIST_OUT="$APP_DIR/Contents/Info.plist"
plist_set() { "$PLIST_BUDDY" -c "Set :$1 $2" "$PLIST_OUT" 2>/dev/null; }

if [[ -x "$PLIST_BUDDY" ]]; then
  if [[ -n "$GIT_VERSION" ]]; then
    plist_set CFBundleVersion "$GIT_VERSION"
    plist_set CFBundleShortVersionString "$GIT_VERSION"
  fi
  plist_set LSMinimumSystemVersion "$MIN_MACOS"
else
  echo "    WARNING: PlistBuddy not found — Info.plist version/min-version left unchanged."
fi

if [[ -n "$GIT_VERSION" ]]; then
  echo "    Version set to: $GIT_VERSION  (min macOS: $MIN_MACOS)"
else
  echo "    No git tag found — bundle version unchanged  (min macOS: $MIN_MACOS)"
fi

# dhewm3 engine binary (renamed so the launcher can call it)
cp "$BINARY" "$APP_DIR/Contents/MacOS/dhewm3"

# Game library .dylibs (base.dylib, d3xp.dylib, etc.) — cmake places them inside
# build/dhewm3.app/Contents/MacOS/ as well as the build root on some setups.
macos_copy_game_dylibs "$BUILD_DIR" "$APP_DIR/Contents/MacOS"

# Launcher script (the CFBundleExecutable that macOS actually runs)
cp "$LAUNCHER_SRC" "$APP_DIR/Contents/MacOS/dhewm3-launcher"
cp "$REPO_ROOT/scripts/macos-lib.sh" "$APP_DIR/Contents/MacOS/macos-lib.sh"
chmod +x "$APP_DIR/Contents/MacOS/dhewm3-launcher"
chmod +x "$APP_DIR/Contents/MacOS/dhewm3"

# App icon — dist/macosx/dhewm3.icns is preferred; fall back to the upstream
# Doom3.icns shipped with the engine sources so Finder shows a real icon.
ICON_SRC=""
for candidate in \
  "$REPO_ROOT/dist/macosx/dhewm3.icns" \
  "$REPO_ROOT/neo/sys/osx/Doom3.icns"; do
  if [[ -f "$candidate" ]]; then
    ICON_SRC="$candidate"
    break
  fi
done
if [[ -n "$ICON_SRC" ]]; then
  cp "$ICON_SRC" "$APP_DIR/Contents/Resources/dhewm3.icns"
else
  echo "    WARNING: No .icns found — app will use the generic macOS icon."
fi

echo "    $APP_DIR assembled."

# ── Bundle Homebrew dylibs ────────────────────────────────────────────────────
# Copy openal-soft, SDL2, and curl dylibs (and their transitive deps) into
# Contents/Frameworks/ and rewrite LC_LOAD_DYLIB paths so the .app works on
# any Mac without Homebrew installed.
FRAMEWORKS_DIR="$APP_DIR/Contents/Frameworks"
mkdir -p "$FRAMEWORKS_DIR"

if command -v dylibbundler &>/dev/null; then
  echo "==> Bundling Homebrew dylibs with dylibbundler…"
  # Bundle deps for the engine binary
  dylibbundler \
    --fix-file "$APP_DIR/Contents/MacOS/dhewm3" \
    --bundle-deps \
    --dest-dir "$FRAMEWORKS_DIR" \
    --install-path "@executable_path/../Frameworks" \
    --overwrite-dir

  # Bundle deps for any game .dylibs (base.dylib, d3xp.dylib, …)
  for GAME_LIB in "$APP_DIR/Contents/MacOS/"*.dylib; do
    [[ -f "$GAME_LIB" ]] || continue
    dylibbundler \
      --fix-file "$GAME_LIB" \
      --bundle-deps \
      --dest-dir "$FRAMEWORKS_DIR" \
      --install-path "@executable_path/../Frameworks" \
      --overwrite-dir
  done

  echo "    Homebrew dylibs bundled into $FRAMEWORKS_DIR"
else
  echo "WARNING: dylibbundler not found — Homebrew dylibs will NOT be bundled."
  echo "         Install it with:  brew install dylibbundler"
  echo "         The .app will only work on Macs that have the same Homebrew"
  echo "         libraries installed (openal-soft, sdl2, curl)."
fi

# ── Ad-hoc code-sign ──────────────────────────────────────────────────────────
# dylibbundler rewrites the binaries' load commands, which invalidates the
# linker's ad-hoc signature.  Without a valid signature the .app is killed on
# launch on Apple Silicon, so re-sign every Mach-O before packaging.
echo "==> Ad-hoc code-signing the .app…"
macos_adhoc_sign_app "$APP_DIR"
echo "    Ad-hoc signatures applied."

# ── Create DMG ────────────────────────────────────────────────────────────────
DMG_NAME="dhewm3-macos-${ARCH_SUFFIX}.dmg"
DMG_PATH="$REPO_ROOT/$DMG_NAME"

echo "==> Creating $DMG_NAME…"

# Temporary staging folder for the DMG contents
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
cp -R "$APP_DIR" "$STAGING/"
# Symlink /Applications so users can drag-and-drop
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "dhewm3" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo ""
echo "==> Done."
echo "    App bundle : $APP_DIR"
echo "    Disk image : $DMG_PATH"
echo ""
echo "To distribute to users: share $DMG_NAME."
echo "Users open the DMG, drag dhewm3 to Applications, and double-click to play."
