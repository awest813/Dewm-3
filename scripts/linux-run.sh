#!/usr/bin/env bash
# linux-run.sh — launch dhewm3, auto-discovering Doom 3 game data.
#
# Usage:
#   ./scripts/linux-run.sh                    # auto-discover game data
#   ./scripts/linux-run.sh /path/to/doom3/    # use an explicit path
#
# The script checks these locations in order:
#   1. Saved path (~/.local/share/dhewm3/gamepath, written by this script
#      the first time the user supplies a valid path)
#   2. Command-line argument (explicit path)
#   3. Steam default library (~/.local/share/Steam/steamapps/common/Doom 3)
#   4. Extra Steam libraries parsed from libraryfolders.vdf
#   5. GOG / manual install candidates

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Prefer build-release (portable / packaged binary) over dev build
BINARY=""
for candidate in \
    "$REPO_ROOT/build-release/dhewm3" \
    "$REPO_ROOT/build/dhewm3"; do
  if [[ -x "$candidate" ]]; then
    BINARY="$candidate"
    break
  fi
done

if [[ -z "$BINARY" ]]; then
  echo "Error: dhewm3 binary not found in build/ or build-release/."
  echo "Run ./scripts/linux-setup.sh first to build it."
  exit 1
fi

# ── Persistent saved path ─────────────────────────────────────────────────────
PREFS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dhewm3"
PREFS_FILE="$PREFS_DIR/gamepath"
mkdir -p "$PREFS_DIR"

has_doom3_data() {
  local dir="$1"
  [[ -d "$dir/base" && -f "$dir/base/pak000.pk4" ]]
}

# ── Load saved path ───────────────────────────────────────────────────────────
SAVED_PATH=""
if [[ -f "$PREFS_FILE" ]]; then
  SAVED_PATH="$(cat "$PREFS_FILE")"
  SAVED_PATH="${SAVED_PATH%/}"
fi

if [[ -n "$SAVED_PATH" ]] && has_doom3_data "$SAVED_PATH"; then
  echo "Using saved game data path: $SAVED_PATH"
  exec "$BINARY" +set fs_basepath "$SAVED_PATH"
fi

# ── Explicit path from command line ───────────────────────────────────────────
if [[ $# -ge 1 ]]; then
  GAME_DATA="${1%/}"
  if ! has_doom3_data "$GAME_DATA"; then
    echo "Warning: $GAME_DATA/base/pak000.pk4 not found — game data may be"
    echo "         missing or the path is wrong."
    echo "         Expected the top-level Doom 3 folder (the one containing base/)."
  fi
  echo "$GAME_DATA" > "$PREFS_FILE"
  exec "$BINARY" +set fs_basepath "$GAME_DATA"
fi

# ── Auto-discover ─────────────────────────────────────────────────────────────
STEAM_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/Steam"
STEAM_COMPAT="${HOME}/.steam/steam"   # legacy symlink location

CANDIDATES=(
  # Steam default library
  "$STEAM_ROOT/steamapps/common/Doom 3"
  "$STEAM_COMPAT/steamapps/common/Doom 3"
  # Flatpak Steam
  "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Doom 3"
  # GOG / manual installs
  "$HOME/Games/Doom 3"
  "$HOME/games/doom3"
  "/usr/local/games/doom3"
  "/opt/doom3"
)

# Parse extra Steam library roots from libraryfolders.vdf
for VDF in \
    "$STEAM_ROOT/steamapps/libraryfolders.vdf" \
    "$STEAM_COMPAT/steamapps/libraryfolders.vdf"; do
  if [[ -f "$VDF" ]]; then
    while IFS= read -r LINE; do
      if [[ "$LINE" =~ \"path\"[[:space:]]*\"([^\"]+)\" ]]; then
        CANDIDATES+=("${BASH_REMATCH[1]}/steamapps/common/Doom 3")
      fi
    done < "$VDF"
  fi
done

for CANDIDATE in "${CANDIDATES[@]}"; do
  if has_doom3_data "$CANDIDATE"; then
    echo "Found Doom 3 data at: $CANDIDATE"
    echo "$CANDIDATE" > "$PREFS_FILE"
    exec "$BINARY" +set fs_basepath "$CANDIDATE"
  fi
done

# ── Not found ─────────────────────────────────────────────────────────────────
cat <<'EOF'
Could not auto-discover Doom 3 game data.

Supply your Doom 3 installation path directly:
  ./scripts/linux-run.sh /path/to/doom3/

The directory you point at must contain a base/ subfolder with
pak000.pk4 through pak008.pk4 (patched to version 1.3.1).

Common locations:
  Steam:  ~/.local/share/Steam/steamapps/common/Doom 3/
  GOG:    wherever you installed it (look for a folder named "base/")

See docs/LINUX.md → "Game data" for more detail.
EOF
exit 1
