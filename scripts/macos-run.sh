#!/usr/bin/env bash
# macos-run.sh — launch dhewm3, auto-discovering Doom 3 game data.
#
# Usage:
#   ./scripts/macos-run.sh                    # auto-discover game data
#   ./scripts/macos-run.sh /path/to/doom3/    # use an explicit path

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINARY="$REPO_ROOT/build/dhewm3"

if [[ ! -x "$BINARY" ]]; then
  echo "Error: dhewm3 binary not found at $BINARY"
  echo "Run ./scripts/macos-setup.sh first to build it."
  exit 1
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
  # Steam (default library)
  "$HOME/Library/Application Support/Steam/steamapps/common/Doom 3"
  # Steam (alternate library on an external drive, etc.)
  "/Volumes/Steam/steamapps/common/Doom 3"
  # GOG / manual install convention
  "$HOME/Games/Doom 3"
  "/Applications/Doom 3"
)

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

The directory you point at must contain a base/ subfolder with
pak000.pk4 through pak008.pk4 (patched to version 1.3.1).

Common locations:
  Steam:  ~/Library/Application Support/Steam/steamapps/common/Doom 3/
  GOG:    wherever you installed it (look for a folder named "base/")

See docs/MACOS.md → "Game data" for more detail.
EOF
exit 1
