#!/usr/bin/env bash
# web-setup.sh — environment check + configure guidance for the future
# Emscripten/WebAssembly port of dhewm3.
#
# Status: experimental WebGL2 renderer; visual/gameplay validation is pending.
# This script checks prerequisites. Configure and build separately below.
#
# Usage:
#   ./scripts/web-setup.sh --check-only   # validate emsdk + preset (default)
#   ./scripts/web-setup.sh --help         # show help
#
# Configure and build with:
#   emcmake cmake -S neo --preset web-wasm -B build-web
#   cmake --build build-web --parallel

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

show_help() {
  sed -n '2,/^set -/p' "$0" | sed 's/^# \{0,1\}//'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

echo "==> dhewm3 web port: environment check (experimental, see docs/WEB.md)"
echo ""

FAIL=0

# 1. emsdk / emcc
if command -v emcc &>/dev/null; then
  echo "OK: emcc found: $(emcc --version 2>/dev/null | head -n 1)"
else
  echo "MISSING: emcc not on PATH. Install emsdk and run:"
  echo "  emsdk install latest && emsdk activate latest && source ./emsdk_env.sh"
  FAIL=1
fi

if [[ -z "${EMSDK:-}" ]]; then
  echo "MISSING: EMSDK env var is not set (needed by the web-wasm CMake preset toolchainFile)."
  FAIL=1
else
  echo "OK: EMSDK=$EMSDK"
fi

# 2. Preset exists and is parseable
if command -v cmake &>/dev/null; then
  if cmake -S "$REPO_ROOT/neo" --list-presets 2>/dev/null | grep -q 'web-wasm'; then
    echo "OK: CMake preset 'web-wasm' found."
  else
    echo "FAIL: CMake preset 'web-wasm' not found in neo/CMakePresets.json."
    FAIL=1
  fi
else
  echo "MISSING: cmake not on PATH."
  FAIL=1
fi

# 3. Scaffolding files
for f in web/shell.html web/serve.py scripts/web-run.sh docs/WEB.md; do
  if [[ -f "$REPO_ROOT/$f" ]]; then
    echo "OK: $f present."
  else
    echo "FAIL: $f missing."
    FAIL=1
  fi
done

# 4. Shell hook (emcc replaces it with the engine loader)
if grep -q '{{{ SCRIPT }}}' "$REPO_ROOT/web/shell.html"; then
  echo "OK: web/shell.html has {{{ SCRIPT }}} hook."
else
  echo "FAIL: web/shell.html is missing the {{{ SCRIPT }}} hook."
  FAIL=1
fi

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "Environment NOT ready. Fix the MISSING items above, then re-run."
  exit 1
fi

echo "Environment looks ready to configure and build."
echo "NOTE: 'emcmake cmake -S neo --preset web-wasm -B build-web' should CONFIGURE;"
echo "the BUILD should now get through the renderer via the GLES compat layer"
echo "(renderer/qgl_gles.h + renderer/tr_gles.cpp). Expect runtime gaps, not"
echo "link errors — see docs/WEB.md phases 3a-4."
