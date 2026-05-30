# User testing on MacBook Air M1 (Apple Silicon)

This guide is for **testers** validating dhewm3 on a **MacBook Air M1** (or any Apple
Silicon Mac). Maintainers: use [MACOS-RELEASE-CHECKLIST.md](./MACOS-RELEASE-CHECKLIST.md)
before shipping a release.

---

## What you need

| Item | Details |
|------|---------|
| Mac | MacBook Air M1 (or M2/M3), **macOS 11.0+** |
| Game data | [DOOM 3 on Steam](https://store.steampowered.com/app/208200/DOOM_3/) (1.3.1) — install through the Steam Mac client |
| Disk space | ~2 GB free for build; ~500 MB for the app + DMG |
| Time | First source build often **15–30 minutes** on an Air (8 GB RAM is fine; avoid heavy apps while compiling) |
| Optional | [Homebrew](https://brew.sh) — required only if building from source |

You do **not** need Rosetta for a native arm64 build.

---

## Path A — Pre-built DMG (fastest for testers)

Use this when a maintainer shared a DMG or you downloaded one from
[Releases](https://github.com/awest813/Dewm-3/releases/latest).

1. Download **`dhewm3-macos-arm64.dmg`** (not the Intel or universal file unless told otherwise).
2. Open the DMG and drag **`dhewm3`** to **Applications**.
3. **First launch security** (unsigned builds):  
   Right-click `dhewm3` in Applications → **Open** → **Open** once.  
   Do not only double-click if Gatekeeper blocks the app.
4. Launch `dhewm3`. A **folder picker** should appear.
5. Select your Doom 3 folder — for Steam on Mac, usually:  
   `~/Library/Application Support/Steam/steamapps/common/Doom 3`  
   (the folder that **contains** `base/`, not `base/` itself).
6. Confirm the main menu loads and you can start a new game.

---

## Path B — Build from source (developers & CI testers)

Use the **`master`** branch (or the branch your maintainer names). PR
[#12](https://github.com/awest813/Dewm-3/pull/12) and later include fixes for the
cmake app-bundle layout.

```sh
# 1. Clone
git clone https://github.com/awest813/Dewm-3.git
cd Dewm-3

# 2. Preflight (machine + Steam data)
./scripts/macos-preflight.sh

# 3. One-step build (auto-detects M1 → macos-arm64 preset)
./scripts/macos-setup.sh

# 4. Verify build
./scripts/macos-preflight.sh --build --verbose

# 5. Launch (pick one)
./scripts/macos-run.sh --app          # Finder / GUI — same as double-clicking dhewm3.app
./scripts/macos-run.sh                # Terminal, auto-finds Steam data
./scripts/macos-run.sh "/path/to/Doom 3"   # explicit path
```

Artifacts after setup:

- `dhewm3.app` — double-click to test the real user flow  
- `dhewm3-arm64.dmg` — optional; test install via DMG drag-to-Applications  

---

## What to test (checklist)

Copy this into your notes or a GitHub issue.

### Install & first launch

- [ ] App opens without crashing (unsigned: used **Right-click → Open** once if needed)
- [ ] Folder picker appears when game data is not configured
- [ ] Selecting the Steam `Doom 3` folder starts the game
- [ ] Second launch skips the picker (path saved under `~/Library/Application Support/dhewm3/gamepath`)

### Gameplay (smoke)

- [ ] Main menu appears, resolution looks correct on Retina display
- [ ] New game / load first map works
- [ ] Sound plays (OpenAL)
- [ ] Mouse look and keyboard work
- [ ] Quit and relaunch still finds game data

### Optional

- [ ] Install from `dhewm3-arm64.dmg` into Applications and repeat first-launch flow
- [ ] Move Doom 3 to an external drive (Steam library) and confirm rediscovery or picker

---

## Reporting feedback

Open a [GitHub issue](https://github.com/awest813/Dewm-3/issues/new) and include:

1. **Mac model** (e.g. MacBook Air M1, 8 GB RAM) and **macOS version** (`sw_vers`)
2. **How you ran dhewm3** (DMG vs source build; `dhewm3.app` vs Terminal)
3. **Doom 3 source** (Steam / GOG) and path you selected
4. **What happened** vs what you expected
5. **Logs** (if it failed from Terminal):
   ```sh
   ./scripts/macos-preflight.sh --build --verbose
   cat ~/Library/Application\ Support/dhewm3/gamepath
   ```
6. Output of:
   ```sh
   file build/dhewm3.app/Contents/MacOS/dhewm3
   ```

---

## Troubleshooting (M1-specific)

| Problem | What to try |
|---------|-------------|
| Gatekeeper blocks app | Right-click → **Open**, or use a signed DMG if provided |
| Build runs out of memory | Close other apps; rebuild with `cmake --build build -j 4` |
| `OpenAL not found` during build | `brew install openal-soft` then re-run `./scripts/macos-setup.sh` |
| Folder picker every launch | Delete bad saved path: `rm ~/Library/Application\ Support/dhewm3/gamepath` |
| Steam path not found | Install Doom 3 via Steam on this Mac, or pass path: `./scripts/macos-run.sh "/…/Doom 3"` |
| Black screen / instant quit | Run from Terminal: `./build/dhewm3.app/Contents/MacOS/dhewm3 -h` and paste output in your issue |

More detail: [MACOS.md](./MACOS.md).

---

## For maintainers before a test round

1. Merge macOS bundle-path fixes to `master` (PR #12+).
2. Confirm [macos.yml](../.github/workflows/macos.yml) **macOS arm64** job is green.
3. Optionally tag a pre-release and attach `dhewm3-macos-arm64.dmg` for Path A testers.
4. Send testers this file and the branch/tag to use.
