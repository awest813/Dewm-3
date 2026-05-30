#!/usr/bin/env bash
# macos-preflight.sh — environment checks before M1 / Apple Silicon user testing.
#
# Usage (from repo root):
#   ./scripts/macos-preflight.sh              # machine + game-data checks
#   ./scripts/macos-preflight.sh --build      # also verify a local build
#   ./scripts/macos-preflight.sh --build --verbose

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=macos-lib.sh
source "$REPO_ROOT/scripts/macos-lib.sh"

CHECK_BUILD=0
VERBOSE=0
FAILURES=0
WARNINGS=0

for arg in "$@"; do
  case "$arg" in
    --build) CHECK_BUILD=1 ;;
    --verbose|-v) VERBOSE=1 ;;
    -h|--help)
      echo "Usage: $0 [--build] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

pass() { echo "  OK   $*"; }
warn() { echo "  WARN $*"; WARNINGS=$((WARNINGS + 1)); }
fail() { echo "  FAIL $*"; FAILURES=$((FAILURES + 1)); }

echo "==> dhewm3 macOS preflight (Apple Silicon user testing)"
echo ""

# ── Host ──────────────────────────────────────────────────────────────────────
echo "-- Machine"
ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  pass "CPU architecture is arm64 (Apple Silicon — M1/M2/M3)"
else
  warn "CPU is '$ARCH', not arm64 — this guide targets M1 MacBook Air; use docs/MACOS.md for Intel"
fi

OS_VER="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
pass "macOS version: $OS_VER"

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "Not running on macOS — run this script on the test Mac"
fi

# ── Build tools ───────────────────────────────────────────────────────────────
echo ""
echo "-- Build prerequisites (for source builds)"

if xcode-select -p &>/dev/null; then
  pass "Xcode Command Line Tools installed"
else
  fail "Xcode Command Line Tools missing — run: xcode-select --install"
fi

if command -v brew &>/dev/null; then
  pass "Homebrew found ($(brew --prefix))"
else
  fail "Homebrew not installed — https://brew.sh"
fi

for tool in cmake git; do
  if command -v "$tool" &>/dev/null; then
    pass "$tool $(command "$tool" --version 2>/dev/null | head -n1)"
  else
    warn "$tool not in PATH (macos-setup.sh will install cmake via brew)"
  fi
done

for pkg in openal-soft sdl2 curl dylibbundler; do
  if brew list "$pkg" &>/dev/null 2>&1; then
    pass "brew package: $pkg"
  else
    warn "brew package '$pkg' not installed — macos-setup.sh will install it"
  fi
done

# ── Game data ─────────────────────────────────────────────────────────────────
echo ""
echo "-- Doom 3 game data"

STEAM_D3="$HOME/Library/Application Support/Steam/steamapps/common/Doom 3"
PREFS_FILE="$HOME/Library/Application Support/dhewm3/gamepath"

if [[ -f "$PREFS_FILE" ]]; then
  SAVED="$(tr -d '\n' < "$PREFS_FILE")"
  SAVED="${SAVED%/}"
  pass "Saved game path: $SAVED"
  if [[ -d "$SAVED/base/pak000.pk4" ]]; then
    pass "Saved path contains base/pak000.pk4"
  else
    warn "Saved path missing base/pak000.pk4 — picker will run again"
  fi
fi

FOUND_DATA=""
if [[ -d "$STEAM_D3/base/pak000.pk4" ]]; then
  FOUND_DATA="$STEAM_D3"
  pass "Steam Doom 3 install found: $STEAM_D3"
else
  warn "Steam default Doom 3 path not found (install via Steam or set path manually)"
fi

# ── Local build / app bundle ─────────────────────────────────────────────────
if [[ "$CHECK_BUILD" -eq 1 ]]; then
  echo ""
  echo "-- Local build"

  APP="$REPO_ROOT/dhewm3.app"
  if [[ -d "$APP" ]]; then
    pass "dhewm3.app exists at $APP"
    if [[ -x "$APP/Contents/MacOS/dhewm3-launcher" ]]; then
      pass "CFBundleExecutable launcher present"
    else
      fail "Missing dhewm3-launcher inside .app"
    fi
    if plutil -lint "$APP/Contents/Info.plist" &>/dev/null; then
      pass "Info.plist is valid"
    else
      fail "Info.plist failed plutil -lint"
    fi
  else
    fail "dhewm3.app not found — run: ./scripts/macos-setup.sh"
  fi

  ENGINE=""
  for BUILD_DIR in "$REPO_ROOT/build" "$REPO_ROOT/build-release"; do
    if ENGINE="$(macos_engine_binary "$BUILD_DIR" 2>/dev/null)"; then
      pass "Engine binary: $ENGINE"
      break
    fi
  done
  if [[ -z "$ENGINE" ]]; then
    fail "No engine binary under build/ or build-release/"
  else
    FILE_INFO="$(file "$ENGINE")"
    if echo "$FILE_INFO" | grep -q "arm64"; then
      pass "Engine is arm64: $FILE_INFO"
    elif echo "$FILE_INFO" | grep -q "universal"; then
      pass "Engine is universal: $FILE_INFO"
    else
      warn "Engine may not be arm64: $FILE_INFO"
    fi

    if [[ "$VERBOSE" -eq 1 ]]; then
      echo ""
      echo "    Linked libraries (should use Homebrew paths, not /usr/lib):"
      otool -L "$ENGINE" | grep -E 'openal|SDL|curl' | sed 's/^/      /' || true
    fi

    if "$ENGINE" -h > /tmp/dhewm3-preflight-smoke.log 2>&1; then
      pass "Engine smoke test (dhewm3 -h) exited 0"
    else
      if grep -qi 'usage\|help\|dhewm3' /tmp/dhewm3-preflight-smoke.log 2>/dev/null; then
        pass "Engine smoke test printed help (non-zero exit is normal)"
      else
        warn "Engine smoke test produced unexpected output — see /tmp/dhewm3-preflight-smoke.log"
      fi
    fi
  fi

  DMG_COUNT="$(find "$REPO_ROOT" -maxdepth 1 -name 'dhewm3-*.dmg' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$DMG_COUNT" -gt 0 ]]; then
    pass "DMG present in repo root ($(find "$REPO_ROOT" -maxdepth 1 -name 'dhewm3-*.dmg' -print | tr '\n' ' '))"
  else
    warn "No dhewm3-*.dmg in repo root (created by macos-setup.sh)"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "==> Summary: $FAILURES failure(s), $WARNINGS warning(s)"
if [[ "$FAILURES" -gt 0 ]]; then
  echo "Fix failures above before user testing. See docs/MACOS-USER-TEST-M1.md"
  exit 1
fi

echo ""
if [[ "$CHECK_BUILD" -eq 0 ]]; then
  echo "Ready to build. Next steps:"
  echo "  ./scripts/macos-setup.sh"
  echo "  ./scripts/macos-preflight.sh --build"
  echo "  ./scripts/macos-run.sh --app    # or: open dhewm3.app"
elif [[ -n "$FOUND_DATA" || -f "$PREFS_FILE" ]]; then
  echo "Ready for user testing. Launch with:"
  echo "  ./scripts/macos-run.sh --app"
  echo "  ./scripts/macos-run.sh"
else
  echo "Build looks good. Install Doom 3 via Steam, then launch:"
  echo "  ./scripts/macos-run.sh --app"
fi
echo "Full tester guide: docs/MACOS-USER-TEST-M1.md"
