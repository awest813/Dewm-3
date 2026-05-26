#!/usr/bin/env bash
# macos-firstrun.sh — CFBundleExecutable for dhewm3.app
#
# On first launch (or when game data can't be found automatically) this script
# presents a macOS folder-picker dialog via osascript, saves the chosen path,
# and launches the dhewm3 engine.  On subsequent launches it reads the saved
# path so the user never sees the picker again unless the data moves.
#
# This file is copied into dhewm3.app/Contents/MacOS/dhewm3-launcher by
# scripts/macos-bundle.sh.  It should not be invoked directly by end-users.

set -euo pipefail

# ── Locate the real engine binary (next to this launcher inside the .app) ─────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$SCRIPT_DIR/dhewm3"

if [[ ! -x "$ENGINE" ]]; then
  osascript -e 'display alert "dhewm3 is damaged" message "Could not find the dhewm3 engine binary inside the app bundle.\nTry re-downloading dhewm3." as critical'
  exit 1
fi

# ── Persistent config path ────────────────────────────────────────────────────
PREFS_DIR="$HOME/Library/Application Support/dhewm3"
PREFS_FILE="$PREFS_DIR/gamepath"
mkdir -p "$PREFS_DIR"

# ── Helper: verify a candidate directory looks like Doom 3 data ───────────────
has_doom3_data() {
  local dir="$1"
  [[ -d "$dir/base" && -f "$dir/base/pak000.pk4" ]]
}

# ── Helper: pick a folder via Finder dialog ───────────────────────────────────
pick_folder() {
  osascript <<'APPLESCRIPT'
tell application "Finder"
  activate
end tell
set chosen to choose folder with prompt ¬
  "Select your Doom 3 installation folder." & return & ¬
  "The folder must contain a \"base\" subfolder with pak000.pk4 … pak008.pk4."
return POSIX path of chosen
APPLESCRIPT
}

# ── Load saved path (if any) ─────────────────────────────────────────────────
SAVED_PATH=""
if [[ -f "$PREFS_FILE" ]]; then
  SAVED_PATH="$(cat "$PREFS_FILE")"
  # Strip trailing slash
  SAVED_PATH="${SAVED_PATH%/}"
fi

# ── Auto-discover known Doom 3 locations ──────────────────────────────────────
# Returns the first valid path or an empty string.
auto_discover() {
  local candidates=()

  # 1. Steam default library (Apple Silicon path)
  candidates+=("$HOME/Library/Application Support/Steam/steamapps/common/Doom 3")

  # 2. Parse Steam libraryfolders.vdf for extra library roots
  local vdf="$HOME/Library/Application Support/Steam/steamapps/libraryfolders.vdf"
  if [[ -f "$vdf" ]]; then
    # Extract quoted paths from the VDF file (works for Steam's JSON-like format)
    while IFS= read -r line; do
      if [[ "$line" =~ \"path\"[[:space:]]*\"([^\"]+)\" ]]; then
        local steam_root="${BASH_REMATCH[1]}"
        candidates+=("$steam_root/steamapps/common/Doom 3")
      fi
    done < "$vdf"
  fi

  # 3. External volumes — glob common Steam library patterns
  for vol_dir in /Volumes/*/steamapps/common/Doom\ 3; do
    [[ -d "$vol_dir" ]] && candidates+=("$vol_dir")
  done

  # 4. GOG / manual installs
  candidates+=(
    "$HOME/Games/Doom 3"
    "/Applications/Doom 3"
    "$HOME/Library/Application Support/Doom 3"
  )

  for c in "${candidates[@]}"; do
    if has_doom3_data "$c"; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

# ── Resolve game data path ────────────────────────────────────────────────────
GAME_DATA=""

# Priority 1: saved path is still valid
if [[ -n "$SAVED_PATH" ]] && has_doom3_data "$SAVED_PATH"; then
  GAME_DATA="$SAVED_PATH"
fi

# Priority 2: auto-discovery
if [[ -z "$GAME_DATA" ]]; then
  GAME_DATA="$(auto_discover)" || true
fi

# Priority 3: show picker
if [[ -z "$GAME_DATA" ]]; then
  osascript -e 'display notification "dhewm3 needs your Doom 3 game data to run." with title "dhewm3 Setup"' || true

  while true; do
    CHOSEN="$(pick_folder 2>/dev/null)" || {
      # User cancelled
      osascript -e 'display alert "dhewm3 needs game data" message "Doom 3 game data is required to play.\n\nYou can buy Doom 3 on Steam or GOG, then re-launch dhewm3 to set the path." as warning'
      exit 1
    }
    # Strip trailing slash that Finder sometimes adds
    CHOSEN="${CHOSEN%/}"

    if has_doom3_data "$CHOSEN"; then
      GAME_DATA="$CHOSEN"
      break
    else
      osascript -e "display alert \"Wrong folder\" message \"The folder you selected does not contain a \\\"base\\\" subfolder with pak000.pk4.\\n\\nSelected: $CHOSEN\\n\\nPlease choose the top-level Doom 3 installation folder (the one that contains the \\\"base\\\" folder).\" as warning"
    fi
  done
fi

# ── Save chosen path for future launches ─────────────────────────────────────
echo "$GAME_DATA" > "$PREFS_FILE"

# ── Launch engine ─────────────────────────────────────────────────────────────
exec "$ENGINE" +set fs_basepath "$GAME_DATA" "$@"
