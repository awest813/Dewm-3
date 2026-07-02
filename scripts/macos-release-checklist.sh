#!/usr/bin/env bash
# macos-release-checklist.sh — automate verifiable items from docs/MACOS-RELEASE-CHECKLIST.md
#
# Run on a Mac after ./scripts/macos-setup.sh (and optionally universal / signed builds).
#
# Usage (from repo root):
#   ./scripts/macos-release-checklist.sh              # §1–3, §8 (default build/)
#   ./scripts/macos-release-checklist.sh --universal  # also §6 (build-release/)
#   ./scripts/macos-release-checklist.sh --discovery  # §5 Steam / GOG path probes
#   ./scripts/macos-release-checklist.sh --dmg        # §3 mount + Applications symlink
#   ./scripts/macos-release-checklist.sh --signed APP # §7 spctl on signed .app
#   ./scripts/macos-release-checklist.sh --all        # every automatable check
#
# Sections §4 (first-run GUI) and parts of §7 (notarization) remain manual — see the doc.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=macos-lib.sh
source "$REPO_ROOT/scripts/macos-lib.sh"

BUILD_DIR="$REPO_ROOT/build"
CHECK_UNIVERSAL=0
CHECK_DISCOVERY=0
CHECK_DMG_MOUNT=0
SIGNED_APP=""

FAILURES=0
PASSES=0
SKIPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --universal) CHECK_UNIVERSAL=1 ;;
    --discovery) CHECK_DISCOVERY=1 ;;
    --dmg) CHECK_DMG_MOUNT=1 ;;
    --all)
      CHECK_UNIVERSAL=1
      CHECK_DISCOVERY=1
      CHECK_DMG_MOUNT=1
      ;;
    --signed)
      shift
      SIGNED_APP="${1:-}"
      [[ -n "$SIGNED_APP" ]] || { echo "Error: --signed requires a path to dhewm3.app"; exit 1; }
      ;;
    --signed=*)
      SIGNED_APP="${1#--signed=}"
      ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      echo "Unexpected argument: $1"
      exit 1
      ;;
  esac
  shift
done

pass() { echo "  [PASS] $*"; PASSES=$((PASSES + 1)); }
fail() { echo "  [FAIL] $*"; FAILURES=$((FAILURES + 1)); }
skip() { echo "  [SKIP] $*"; SKIPS=$((SKIPS + 1)); }
manual() { echo "  [MANUAL] $*"; }

section() {
  echo ""
  echo "── $1 ──"
}

# ── Host guard ────────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: this script must run on macOS."
  exit 1
fi

echo "==> macOS release checklist (automated checks)"
echo "    Doc: docs/MACOS-RELEASE-CHECKLIST.md"

# ── §1 Build verification ───────────────────────────────────────────────────
section "§1 — Build verification"

ENGINE=""
if ENGINE="$(macos_engine_binary "$BUILD_DIR" 2>/dev/null)"; then
  pass "Engine binary found: $ENGINE"
else
  fail "No engine under $BUILD_DIR — run: ./scripts/macos-setup.sh"
  ENGINE=""
fi

if [[ -n "$ENGINE" ]]; then
  FILE_INFO="$(file "$ENGINE")"
  pass "file: $FILE_INFO"

  HOST_ARCH="$(uname -m)"
  if echo "$FILE_INFO" | grep -q "universal binary"; then
    pass "Architecture: universal binary"
  elif [[ "$HOST_ARCH" == "arm64" ]] && echo "$FILE_INFO" | grep -q "arm64"; then
    pass "Architecture matches host (arm64)"
  elif [[ "$HOST_ARCH" == "x86_64" ]] && echo "$FILE_INFO" | grep -q "x86_64"; then
    pass "Architecture matches host (x86_64)"
  else
    warn_arch="Binary arch may not match host ($HOST_ARCH): $FILE_INFO"
    if [[ "$CHECK_UNIVERSAL" -eq 1 ]]; then
      pass "$warn_arch (universal build expected)"
    else
      fail "$warn_arch"
    fi
  fi

  OTOOL_OUT="$(otool -L "$ENGINE" 2>/dev/null || true)"
  if echo "$OTOOL_OUT" | grep -E 'openal|SDL2|curl' | grep -q '/opt/homebrew\|/usr/local'; then
    pass "Linked libs use Homebrew paths (openal / SDL2 / curl)"
  elif echo "$OTOOL_OUT" | grep -E 'openal|SDL2|curl' | grep -q '@executable_path'; then
    pass "Linked libs bundled under @executable_path (post-dylibbundler)"
  elif echo "$OTOOL_OUT" | grep -E 'openal|SDL2|curl' | grep -q '/System/Library'; then
    fail "openal/SDL2/curl link to /System/Library — use Homebrew openal-soft"
  else
    fail "Could not confirm Homebrew/bundled paths for openal/SDL2/curl"
  fi

  if "$ENGINE" -h > /tmp/dhewm3-release-checklist-smoke.log 2>&1; then
    pass "dhewm3 -h exited 0"
  elif grep -qiE 'usage|help|dhewm3|fs_basepath' /tmp/dhewm3-release-checklist-smoke.log 2>/dev/null; then
    pass "dhewm3 -h printed help (non-zero exit is normal)"
  else
    fail "dhewm3 -h produced unexpected output — see /tmp/dhewm3-release-checklist-smoke.log"
  fi
fi

skip "macos-setup.sh on Apple Silicon — run on host or rely on macos-14 CI"
skip "macos-setup.sh on Intel — run on host or rely on macos-13 CI"

# ── §2 App bundle ─────────────────────────────────────────────────────────────
section "§2 — App bundle"

APP="$REPO_ROOT/dhewm3.app"
if [[ -d "$APP" ]]; then
  pass "dhewm3.app in repo root"
else
  fail "dhewm3.app missing — run: ./scripts/macos-bundle.sh $BUILD_DIR"
fi

if [[ -x "$APP/Contents/MacOS/dhewm3-launcher" ]]; then
  pass "dhewm3-launcher executable"
else
  fail "Missing or non-executable dhewm3-launcher"
fi

if [[ -x "$APP/Contents/MacOS/dhewm3" ]]; then
  pass "dhewm3 engine executable"
else
  fail "Missing or non-executable engine in .app"
fi

if plutil -lint "$APP/Contents/Info.plist" &>/dev/null; then
  pass "Info.plist valid (plutil -lint)"
else
  fail "Info.plist failed plutil -lint"
fi

if compgen -G "$APP/Contents/MacOS/"*.dylib >/dev/null; then
  pass "Game .dylib modules present (base.dylib, …)"
else
  fail "No *.dylib in .app/Contents/MacOS/"
fi

if [[ -f "$APP/Contents/Resources/dhewm3.icns" ]]; then
  pass "App icon present (dhewm3.icns)"
else
  skip "No app icon — Finder shows generic icon"
fi

FRAMEWORKS="$APP/Contents/Frameworks"
if [[ -d "$FRAMEWORKS" ]]; then
  FW_LIST="$(find "$FRAMEWORKS" -maxdepth 1 -name '*.dylib' -print 2>/dev/null || true)"
  if echo "$FW_LIST" | grep -qi openal && echo "$FW_LIST" | grep -qi SDL2; then
    pass "Bundled Frameworks include openal + SDL2 (dylibbundler single-pass)"
  else
    fail "Frameworks missing openal or SDL2 — dylibbundler may have wiped deps"
  fi
else
  skip "No Contents/Frameworks — dylibbundler not run or Homebrew-only build"
fi

# Every Mach-O must carry a valid signature (ad-hoc is fine) or Apple Silicon
# kills it on launch.  dylibbundler invalidates the linker's signature, so
# macos-bundle.sh re-signs — verify that here to catch regressions.
if [[ -x "$APP/Contents/MacOS/dhewm3" ]]; then
  if codesign --verify --strict "$APP/Contents/MacOS/dhewm3" &>/dev/null; then
    pass "Engine binary has a valid code signature (ad-hoc or better)"
  else
    fail "Engine binary lacks a valid signature — will be killed on Apple Silicon"
  fi
fi

# ── §3 DMG ────────────────────────────────────────────────────────────────────
section "§3 — DMG"

DMG=""
for candidate in "$REPO_ROOT"/dhewm3-macos-*.dmg "$REPO_ROOT"/dhewm3-*.dmg; do
  [[ -f "$candidate" ]] || continue
  DMG="$candidate"
  break
done

if [[ -n "$DMG" ]]; then
  pass "DMG found: $(basename "$DMG")"
else
  fail "No dhewm3-macos-*.dmg in repo root"
fi

if [[ "$CHECK_DMG_MOUNT" -eq 1 && -n "$DMG" ]]; then
  MOUNT_OUT="$(hdiutil attach "$DMG" -nobrowse -readonly 2>&1)" || MOUNT_OUT=""
  MOUNT_POINT="$(echo "$MOUNT_OUT" | awk '/\/Volumes\// {print $NF; exit}')"
  if [[ -n "$MOUNT_POINT" && -d "$MOUNT_POINT" ]]; then
    pass "DMG mounts cleanly"
    if [[ -d "$MOUNT_POINT/dhewm3.app" ]]; then
      pass "DMG contains dhewm3.app"
    else
      fail "DMG missing dhewm3.app at mount root"
    fi
    if [[ -L "$MOUNT_POINT/Applications" ]]; then
      pass "DMG has /Applications symlink"
    else
      fail "DMG missing Applications symlink for drag-and-drop install"
    fi
    hdiutil detach "$MOUNT_POINT" -quiet && pass "DMG unmounts cleanly" || fail "hdiutil detach failed"
  else
    fail "Could not mount DMG: $DMG"
  fi
else
  skip "DMG mount test — re-run with --dmg"
fi

# ── §4 First-run (manual) ─────────────────────────────────────────────────────
section "§4 — First-run / game data"
manual "Clean machine: remove ~/Library/Application Support/dhewm3/gamepath, launch .app, pick folder"
manual "Re-launch: game starts without picker"
manual "Bad path: echo /nonexistent > gamepath, re-launch — picker or auto-discovery"
manual "Explicit path: ./scripts/macos-run.sh /path/to/doom3/"

# ── §5 Path discovery ─────────────────────────────────────────────────────────
if [[ "$CHECK_DISCOVERY" -eq 1 ]]; then
  section "§5 — Expanded path discovery"

  STEAM_DEFAULT="$HOME/Library/Application Support/Steam/steamapps/common/Doom 3"
  if macos_has_doom3_data "$STEAM_DEFAULT"; then
    pass "Steam default library has Doom 3 data"
  else
    skip "Steam default path has no base/pak000.pk4 (install Doom 3 or skip)"
  fi

  VDF="$HOME/Library/Application Support/Steam/steamapps/libraryfolders.vdf"
  ALT_FOUND=0
  if [[ -f "$VDF" ]]; then
    while IFS= read -r candidate; do
      [[ -z "$candidate" ]] && continue
      if macos_has_doom3_data "$candidate"; then
        pass "libraryfolders.vdf candidate: $candidate"
        ALT_FOUND=1
      fi
    done < <(macos_game_data_candidates | tail -n +2)
    if [[ "$ALT_FOUND" -eq 0 ]]; then
      skip "No extra libraryfolders.vdf paths with Doom 3 data (OK if single-library install)"
    fi
  else
    skip "libraryfolders.vdf not found"
  fi

  EXT_FOUND=0
  for vol_path in /Volumes/*/steamapps/common/Doom\ 3 /Volumes/*/Doom\ 3; do
    [[ -d "$vol_path" ]] || continue
    if macos_has_doom3_data "$vol_path"; then
      pass "External volume: $vol_path"
      EXT_FOUND=1
    fi
  done
  if [[ "$EXT_FOUND" -eq 0 ]]; then
    skip "No external-volume Steam library with Doom 3 (mount drive to test)"
  fi

  if macos_discover_game_data &>/dev/null; then
    pass "macos_discover_game_data finds: $(macos_discover_game_data)"
  else
    skip "macos_discover_game_data found nothing (install game data to test)"
  fi
else
  section "§5 — Expanded path discovery"
  skip "Steam / external discovery — re-run with --discovery"
fi

# ── §6 Universal binary ─────────────────────────────────────────────────────────
if [[ "$CHECK_UNIVERSAL" -eq 1 ]]; then
  section "§6 — Universal binary (release)"

  UNI_BUILD="$REPO_ROOT/build-release"
  UNI_ENGINE=""
  if UNI_ENGINE="$(macos_engine_binary "$UNI_BUILD" 2>/dev/null)"; then
    pass "Universal engine: $UNI_ENGINE"
    UNI_FILE="$(file "$UNI_ENGINE")"
    if echo "$UNI_FILE" | grep -q "universal binary"; then
      pass "file reports universal binary"
    else
      fail "Expected universal binary: $UNI_FILE"
    fi
    LIPO_INFO="$(lipo -info "$UNI_ENGINE" 2>&1)" || LIPO_INFO=""
    if echo "$LIPO_INFO" | grep -q "x86_64" && echo "$LIPO_INFO" | grep -q "arm64"; then
      pass "lipo lists x86_64 and arm64"
    else
      fail "lipo -info missing a slice: $LIPO_INFO"
    fi
  else
    fail "No build-release engine — run: ./scripts/macos-setup.sh universal"
  fi

  UNI_DMG="$REPO_ROOT/dhewm3-macos-universal.dmg"
  if [[ -f "$UNI_DMG" ]]; then
    pass "dhewm3-macos-universal.dmg present"
  else
    fail "dhewm3-macos-universal.dmg missing"
  fi
else
  section "§6 — Universal binary (release)"
  skip "Universal checks — re-run with --universal after: ./scripts/macos-setup.sh universal"
fi

# ── §7 Signing (partial auto) ─────────────────────────────────────────────────
section "§7 — Code signing & notarization"
manual "Trigger release-sign workflow (workflow_dispatch, sign=true)"
manual "CI notarization Accepted + stapler staple"
manual "Clean Mac: DMG → Applications → launch with no Gatekeeper warning"

if [[ -n "$SIGNED_APP" ]]; then
  if [[ -d "$SIGNED_APP" ]]; then
    if spctl --assess --type execute "$SIGNED_APP" 2>/dev/null; then
      pass "spctl --assess accepted: $SIGNED_APP"
    else
      fail "spctl --assess rejected: $SIGNED_APP"
    fi
    if codesign -dv "$SIGNED_APP" &>/tmp/dhewm3-codesign.log; then
      pass "codesign -dv succeeded"
    else
      fail "codesign -dv failed — see /tmp/dhewm3-codesign.log"
    fi
  else
    fail "Signed app path not found: $SIGNED_APP"
  fi
else
  skip "Local spctl check — re-run with: --signed /Applications/dhewm3.app"
fi

# ── §8 Documentation ──────────────────────────────────────────────────────────
section "§8 — Documentation"

README="$REPO_ROOT/README.md"
MACOS_DOC="$REPO_ROOT/docs/MACOS.md"

if grep -q 'docs/MACOS.md' "$README"; then
  pass "README.md links to docs/MACOS.md"
else
  fail "README.md missing link to docs/MACOS.md"
fi

if grep -qE '\.app|DMG|dhewm3-macos' "$README"; then
  pass "README.md mentions .app / DMG download"
else
  fail "README.md Mac section should mention .app or DMG download"
fi

if grep -q 'Fastest way to run on Mac' "$MACOS_DOC"; then
  pass 'MACOS.md has "Fastest way to run on Mac" section'
else
  fail 'MACOS.md missing "Fastest way to run on Mac" section'
fi

if grep -q 'dhewm3-macos-arm64.dmg' "$MACOS_DOC"; then
  pass "MACOS.md lists release DMG filenames"
else
  fail "MACOS.md should list dhewm3-macos-*.dmg filenames"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "==> Summary: $PASSES passed, $FAILURES failed, $SKIPS skipped (manual items listed above)"
echo ""
if [[ "$FAILURES" -gt 0 ]]; then
  echo "Release blocked — fix failures or complete manual §4/§7 steps in docs/MACOS-RELEASE-CHECKLIST.md"
  exit 1
fi

echo "Automated checks passed. Complete any [MANUAL] / [SKIP] items before tagging a release."
exit 0
