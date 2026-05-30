#!/usr/bin/env bash
# macos-run.sh — launch dhewm3, auto-discovering Doom 3 game data.
#
# Usage:
#   ./scripts/macos-run.sh                    # auto-discover game data
#   ./scripts/macos-run.sh --app              # open dhewm3.app (GUI / user testing)
#   ./scripts/macos-run.sh /path/to/doom3/    # use an explicit path

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
if [[ -f "$PREFS_FILE" ]]; then
  SAVED="$(cat "$PREFS_FILE")"
  SAVED="${SAVED%/}"
  if [[ -d "$SAVED/base" ]]; then
    echo "Using saved game data path: $SAVED"
    exec "$BINARY" +set fs_basepath "$SAVED"
  fi
fi

# ── Explicit path ─────────────────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
  GAME_DATA="$1"
  if [[ ! -d "$GAME_DATA/base" ]]; then
    echo "Warning: $GAME_DATA/base not found — game data may be missing or path is wrong."
    echo "Expected to find pak000.pk4 … pak008.pk4 inside $GAME_DATA/base/"
  fi
  exec "$BINARY" +set fs_basepath "$GAME_DATA"
fi

# ── Auto-discover common macOS Doom 3 install locations ──────────────────────
CANDIDATES=(
  # Steam default library
  "$HOME/Library/Application Support/Steam/steamapps/common/Doom 3"
  # GOG / manual installs
  "$HOME/Games/Doom 3"
  "/Applications/Doom 3"
  "$HOME/Library/Application Support/Doom 3"
)

# Parse Steam libraryfolders.vdf for additional Steam library roots
VDF="$HOME/Library/Application Support/Steam/steamapps/libraryfolders.vdf"
if [[ -f "$VDF" ]]; then
  while IFS= read -r LINE; do
    if [[ "$LINE" =~ \"path\"[[:space:]]*\"([^\"]+)\" ]]; then
      CANDIDATES+=("${BASH_REMATCH[1]}/steamapps/common/Doom 3")
    fi
  done < "$VDF"
fi

# External volumes — any mounted volume with a Steam library or bare Doom 3 folder
for VOL_PATH in /Volumes/*/steamapps/common/Doom\ 3 /Volumes/*/Doom\ 3; do
  [[ -d "$VOL_PATH" ]] && CANDIDATES+=("$VOL_PATH")
done

for CANDIDATE in "${CANDIDATES[@]}"; do
  if [[ -d "$CANDIDATE/base" ]]; then
    echo "Found Doom 3 data at: $CANDIDATE"
    exec "$BINARY" +set fs_basepath "$CANDIDATE"
  fi
done

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
