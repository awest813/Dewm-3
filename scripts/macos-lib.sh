# macos-lib.sh — shared helpers for macOS build scripts.
# Source from other scripts:  source "$(dirname "$0")/macos-lib.sh"

# Print the path to the dhewm3 engine binary inside BUILD_DIR.
# Prefers the cmake MACOSX_BUNDLE layout; falls back to a flat binary.
macos_engine_binary() {
  local build_dir="$1"
  if [[ -x "$build_dir/dhewm3.app/Contents/MacOS/dhewm3" ]]; then
    echo "$build_dir/dhewm3.app/Contents/MacOS/dhewm3"
  elif [[ -x "$build_dir/dhewm3" ]]; then
    echo "$build_dir/dhewm3"
  else
    return 1
  fi
}

# Copy game .dylib modules (base.dylib, d3xp.dylib, …) into DEST_DIR.
macos_copy_game_dylibs() {
  local build_dir="$1"
  local dest_dir="$2"
  local dir
  for dir in "$build_dir" "$build_dir/dhewm3.app/Contents/MacOS"; do
    [[ -d "$dir" ]] || continue
    find "$dir" -maxdepth 1 -name "*.dylib" -exec cp -f {} "$dest_dir/" \;
  done
}

# Stage engine binary (as dhewm3) and game dylibs into OUT_DIR (for CI artifacts).
macos_stage_engine_artifacts() {
  local build_dir="$1"
  local out_dir="$2"
  local engine
  engine="$(macos_engine_binary "$build_dir")" || return 1
  mkdir -p "$out_dir"
  cp -f "$engine" "$out_dir/dhewm3"
  chmod +x "$out_dir/dhewm3"
  macos_copy_game_dylibs "$build_dir" "$out_dir"
}
