#!/usr/bin/env bash
# Help exits 1 intentionally (Common.cpp). Assert the output as well as status.
set -euo pipefail
binary="${1:?Usage: check-engine.sh /path/to/dhewm3}"
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
status=0
"$binary" --help > "$log" 2>&1 || status=$?
cat "$log"
if [[ "$status" -ne 1 ]] || ! grep -q 'Commandline arguments:' "$log" || ! grep -q 'fs_basepath' "$log"; then
  echo "Engine help check failed (exit $status)." >&2
  exit 1
fi
