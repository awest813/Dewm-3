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

# Return 0 when DIR looks like a Doom 3 installation (base/ with pak000.pk4).
macos_has_doom3_data() {
  local dir="$1"
  [[ -d "$dir/base" && -f "$dir/base/pak000.pk4" ]]
}

# Print candidate Doom 3 install paths (one per line), in search priority order.
# Used by macos-run.sh and macos-firstrun.sh.
macos_game_data_candidates() {
  # Steam default library
  printf '%s\n' "$HOME/Library/Application Support/Steam/steamapps/common/Doom 3"

  # Extra Steam library roots from libraryfolders.vdf
  local vdf="$HOME/Library/Application Support/Steam/steamapps/libraryfolders.vdf"
  if [[ -f "$vdf" ]]; then
    local line steam_root
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" =~ \"path\"[[:space:]]*\"([^\"]+)\" ]]; then
        steam_root="${BASH_REMATCH[1]}"
        printf '%s\n' "$steam_root/steamapps/common/Doom 3"
      fi
    done < "$vdf"
  fi

  # Legacy Steam config (older installs)
  local legacy_vdf="$HOME/Library/Application Support/Steam/config/libraryfolders.vdf"
  if [[ -f "$legacy_vdf" ]]; then
    local line steam_root
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" =~ \"path\"[[:space:]]*\"([^\"]+)\" ]]; then
        steam_root="${BASH_REMATCH[1]}"
        printf '%s\n' "$steam_root/steamapps/common/Doom 3"
      fi
    done < "$legacy_vdf"
  fi

  # External volumes — Steam libraries and bare Doom 3 folders
  local vol_path
  for vol_path in /Volumes/*/steamapps/common/Doom\ 3 /Volumes/*/Doom\ 3; do
    [[ -d "$vol_path" ]] && printf '%s\n' "$vol_path"
  done

  # GOG / manual installs
  printf '%s\n' \
    "$HOME/Games/Doom 3" \
    "/Applications/Doom 3" \
    "$HOME/Library/Application Support/Doom 3"
}

# Print the first valid Doom 3 path, or return 1 if none found.
macos_discover_game_data() {
  local candidate
  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    if macos_has_doom3_data "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done < <(macos_game_data_candidates)
  return 1
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
