# macOS Release Checklist

This is the **release gate** for all Mac-friendly dhewm3 builds.
Complete every item before tagging a release or uploading a distributable DMG.

---

## 1 — Build verification

- [ ] `./scripts/macos-setup.sh` completes without errors on Apple Silicon.
- [ ] `./scripts/macos-setup.sh` completes without errors on Intel (or `macos-13` CI runner).
- [ ] `file build/dhewm3` confirms the expected architecture (`arm64` / `x86_64`).
- [ ] `otool -L build/dhewm3 | grep -E 'openal|SDL2|curl'` shows Homebrew paths (not `/System/Library/…`).
- [ ] `./build/dhewm3 -h` runs and prints a usage message (exit code may be non-zero — normal).

## 2 — App bundle

- [ ] `dhewm3.app` is created in the repo root after setup.
- [ ] `dhewm3.app/Contents/MacOS/dhewm3-launcher` exists and is executable.
- [ ] `dhewm3.app/Contents/MacOS/dhewm3` (engine) exists and is executable.
- [ ] `dhewm3.app/Contents/Info.plist` is present and valid (`plutil -lint dhewm3.app/Contents/Info.plist`).
- [ ] Game `.dylib` files (base.dylib, d3xp.dylib, …) are present in `dhewm3.app/Contents/MacOS/`.

## 3 — DMG

- [ ] `dhewm3-<arch>.dmg` (or `dhewm3-universal.dmg`) is created in the repo root.
- [ ] The DMG mounts cleanly when double-clicked (no corruption warnings).
- [ ] The DMG contains `dhewm3.app` and an `/Applications` symlink for drag-and-drop install.
- [ ] The DMG unmounts cleanly.

## 4 — First-run / game data

**Clean machine test** (no prior dhewm3 config):

- [ ] Remove `~/Library/Application Support/dhewm3/gamepath` if it exists.
- [ ] Launch `dhewm3.app` — the folder-picker dialog appears.
- [ ] Select a valid Doom 3 folder → game launches.
- [ ] Quit and re-launch → game launches immediately (no picker shown).

**Bad path test:**

- [ ] Corrupt the saved path: `echo "/nonexistent" > ~/Library/Application\ Support/dhewm3/gamepath`.
- [ ] Re-launch `dhewm3.app` — auto-discovery kicks in; if it fails the picker appears again.

**Explicit path test:**

- [ ] `./scripts/macos-run.sh /path/to/doom3/` launches the game correctly.

## 5 — Expanded path discovery

- [ ] Steam default library path detected automatically (if Steam is installed with Doom 3).
- [ ] At least one alternative library from `libraryfolders.vdf` is detected (if applicable).
- [ ] An external volume Steam library is detected when mounted (if applicable).

## 6 — Universal binary (release-only)

- [ ] `./scripts/macos-setup.sh universal` completes without errors.
- [ ] `file build-release/dhewm3.app/Contents/MacOS/dhewm3` shows `Mach-O universal binary with 2 architectures`.
- [ ] `lipo -info build-release/dhewm3.app/Contents/MacOS/dhewm3` lists both `x86_64` and `arm64`.
- [ ] `dhewm3-universal.dmg` is created and mounts cleanly.

## 7 — Code signing & notarization (signed release only)

- [ ] Trigger the `release-sign` workflow job (workflow_dispatch → sign=true).
- [ ] CI signs the bundle without errors.
- [ ] CI notarizes the DMG without errors (`xcrun notarytool` returns `Accepted`).
- [ ] CI staples the ticket (`xcrun stapler staple`).
- [ ] On a clean Mac: open the DMG → drag to Applications → launch → **no Gatekeeper warning**.
- [ ] `spctl --assess --type exec dhewm3.app` exits 0 ("accepted") on the signed build.

## 8 — Documentation

- [ ] `docs/MACOS.md` "Fastest way to run on Mac" section matches the actual steps.
- [ ] `README.md` Mac section links to `docs/MACOS.md` and mentions the `.app` download.

---

_Check all boxes before tagging a release. Any unchecked item is a release blocker._
