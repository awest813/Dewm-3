#!/usr/bin/env bash
# macos-run.sh — launch dhewm3, auto-discovering Doom 3 game data.
#
# Usage:
#   ./scripts/macos-run.sh                              # auto-discover game data
#   ./scripts/macos-run.sh --app                        # open dhewm3.app (GUI / user testing)
#   ./scripts/macos-run.sh /path/to/doom3/              # use an explicit path
#   ./scripts/macos-run.sh /path/to/doom3/ [engine args…]  # pass extra engine args
#   ./scripts/macos-run.sh --show-path                  # print saved path, if any
#   ./scripts/macos-run.sh --clear-path                 # remove saved path
#   ./scripts/macos-run.sh --help                       # show this help
#
# Any arguments after the (optional) game-data path are forwarded directly to
# the dhewm3 engine.  When no path is supplied, all arguments are forwarded.
# Examples:
#   ./scripts/macos-run.sh +set r_fullscreen 0
#   ./scripts/macos-run.sh /path/to/doom3/ +set r_fullscreen 0 +set com_allowConsole 1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=macos-lib.sh
source "$REPO_ROOT/scripts/macos-lib.sh"

# Launch dhewm3.app via Finder (GUI / first-run picker) — preferred for user testing.
if [[ "${1:-}" == "--app" || "${1:-}" == "-a" ]]; then
  APP="$REPO_ROOT/dhewm3.app"
  if [[ ! -d "$APP" ]]; then
    echo "Error: $APP not found."
    echo "Run ./scripts/macos-setup.sh first, or install from a DMG."
    exit 1
  fi
  echo "Opening $APP …"
  exec open "$APP"
fi

show_help() {
  cat <<'EOF'
Usage:
  ./scripts/macos-run.sh [path/to/doom3] [engine args...]
  ./scripts/macos-run.sh --app
  ./scripts/macos-run.sh --show-path
  ./scripts/macos-run.sh --clear-path
  ./scripts/macos-run.sh --help

Tips:
  - If the first argument starts with '+' or '-', it is treated as an engine arg.
  - Supply the Doom 3 folder (contains base/) as the first argument to override saved path.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

BINARY=""
for BUILD_DIR in "$REPO_ROOT/build" "$REPO_ROOT/build-release"; do
  if BINARY="$(macos_engine_binary "$BUILD_DIR")"; then
    [[ "$BUILD_DIR" == *build-release* ]] && echo "Using release build: $BINARY"
    break
  fi
done

if [[ -z "$BINARY" ]]; then
  echo "Error: dhewm3 binary not found under build/ or build-release/"
  echo "Run ./scripts/macos-setup.sh first to build it."
  exit 1
fi

# ── Saved path from first-run launcher (dhewm3.app) ──────────────────────────
PREFS_FILE="$HOME/Library/Application Support/dhewm3/gamepath"

if [[ "${1:-}" == "--show-path" ]]; then
  if [[ -f "$PREFS_FILE" ]]; then
    SAVED="$(cat "$PREFS_FILE")"
    SAVED="${SAVED%/}"
    if macos_has_doom3_data "$SAVED"; then
      echo "Saved game data path: $SAVED"
    else
      echo "Saved game data path is invalid: $SAVED"
    fi
  else
    echo "No saved game data path."
  fi
  exit 0
fi

if [[ "${1:-}" == "--clear-path" ]]; then
  rm -f "$PREFS_FILE"
  echo "Cleared saved game data path."
  exit 0
fi

is_explicit_path_arg=false
if [[ $# -ge 1 ]]; then
  case "$1" in
    +*|-*) is_explicit_path_arg=false ;;
    *)     is_explicit_path_arg=true ;;
  esac
fi

# ── Explicit path ─────────────────────────────────────────────────────────────
if [[ "$is_explicit_path_arg" == "true" ]]; then
  GAME_DATA="${1%/}"
  if ! macos_has_doom3_data "$GAME_DATA"; then
    echo "Warning: $GAME_DATA does not contain base/pak000.pk4 — game data may be missing or path is wrong."
    echo "Expected to find pak000.pk4 … pak008.pk4 inside $GAME_DATA/base/"
  fi
  # Save the explicit path for future launches (matches linux-run.sh behaviour).
  mkdir -p "$(dirname "$PREFS_FILE")"
  echo "$GAME_DATA" > "$PREFS_FILE"
  exec "$BINARY" +set fs_basepath "$GAME_DATA" "${@:2}"
fi

if [[ -f "$PREFS_FILE" ]]; then
  SAVED="$(cat "$PREFS_FILE")"
  SAVED="${SAVED%/}"
  if macos_has_doom3_data "$SAVED"; then
    echo "Using saved game data path: $SAVED"
    exec "$BINARY" +set fs_basepath "$SAVED" "$@"
  fi
fi

# ── Auto-discover ─────────────────────────────────────────────────────────────
if DISCOVERED="$(macos_discover_game_data)"; then
  echo "Found Doom 3 data at: $DISCOVERED"
  exec "$BINARY" +set fs_basepath "$DISCOVERED" "$@"
fi

# ── Not found ─────────────────────────────────────────────────────────────────
cat <<'EOF'
Could not auto-discover Doom 3 game data.

Supply your Doom 3 installation path directly:
  ./scripts/macos-run.sh /path/to/doom3/

Or use the GUI launcher (folder picker on first run):
  ./scripts/macos-run.sh --app

The directory you point at must contain a base/ subfolder with
pak000.pk4 through pak008.pk4 (patched to version 1.3.1).

Common locations:
  Steam:  ~/Library/Application Support/Steam/steamapps/common/Doom 3/
  GOG:    wherever you installed it (look for a folder named "base/")

See docs/MACOS-USER-TEST-M1.md for the M1 tester guide.
EOF
exit 1
