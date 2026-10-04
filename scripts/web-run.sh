#!/usr/bin/env bash
# web-run.sh — serve the dhewm3 web build locally and print the URL.
#
# Usage:
#   ./scripts/web-run.sh                   # serve build-web on port 8080
#   ./scripts/web-run.sh --port 9000       # custom port
#   ./scripts/web-run.sh --dir build-web   # custom build directory
#   ./scripts/web-run.sh --no-coop         # skip COOP/COEP headers
#
# Open the printed URL, load your Doom 3 data in the page, press Start.
# See docs/WEB.md for the full web guide.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PORT="8080"
DIR="$REPO_ROOT/build-web"
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --dir)  DIR="$2";  shift 2 ;;
    --no-coop) EXTRA+=(--no-coop); shift ;;
    -h|--help)
      sed -n '2,/^set -/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--port N] [--dir DIR] [--no-coop]"
      exit 1
      ;;
  esac
done

if [[ ! -f "$DIR/dhewm3.html" ]]; then
  echo "error: $DIR/dhewm3.html not found."
  echo "Build it first (see docs/WEB.md):"
  echo "  emcmake cmake -S neo --preset web-wasm -B build-web"
  echo "  cmake --build build-web --parallel"
  exit 1
fi

exec python3 "$REPO_ROOT/web/serve.py" --dir "$DIR" --port "$PORT" "${EXTRA[@]}"
