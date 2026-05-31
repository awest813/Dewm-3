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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/macos-lib.sh" ]]; then
  # shellcheck source=macos-lib.sh
  source "$SCRIPT_DIR/macos-lib.sh"
fi

# ── Locate the real engine binary (next to this launcher inside the .app) ─────
ENGINE="$SCRIPT_DIR/dhewm3"

if [[ ! -x "$ENGINE" ]]; then
  osascript -e 'display alert "dhewm3 is damaged" message "Could not find the dhewm3 engine binary inside the app bundle.\nTry re-downloading dhewm3." as critical'
  exit 1
fi

# ── Persistent config path ────────────────────────────────────────────────────
PREFS_DIR="$HOME/Library/Application Support/dhewm3"
PREFS_FILE="$PREFS_DIR/gamepath"
mkdir -p "$PREFS_DIR"

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
  SAVED_PATH="${SAVED_PATH%/}"
fi

# ── Resolve game data path ────────────────────────────────────────────────────
GAME_DATA=""

# Priority 1: saved path is still valid
if [[ -n "$SAVED_PATH" ]] && macos_has_doom3_data "$SAVED_PATH"; then
  GAME_DATA="$SAVED_PATH"
fi

# Priority 2: auto-discovery
if [[ -z "$GAME_DATA" ]]; then
  GAME_DATA="$(macos_discover_game_data)" || true
fi

# Priority 3: show picker
if [[ -z "$GAME_DATA" ]]; then
  osascript -e 'display notification "dhewm3 needs your Doom 3 game data to run." with title "dhewm3 Setup"' || true

  while true; do
    CHOSEN="$(pick_folder 2>/dev/null)" || {
      osascript -e 'display alert "dhewm3 needs game data" message "Doom 3 game data is required to play.\n\nYou can buy Doom 3 on Steam or GOG, then re-launch dhewm3 to set the path." as warning'
      exit 1
    }
    CHOSEN="${CHOSEN%/}"

    if macos_has_doom3_data "$CHOSEN"; then
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
