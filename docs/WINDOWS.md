# Windows build and Steam game data

Install CMake 3.21 or newer, Visual Studio 2022 or newer with the **Desktop
development with C++** workload, and a Windows SDK. Visual Studio 2026 needs
a CMake version that supports its generator (4.2 or newer).

From PowerShell in the repository root:

```powershell
./scripts/windows-run.ps1 -CheckOnly
./scripts/windows-setup.ps1
./scripts/windows-run.ps1
```

Setup downloads the upstream `dhewm3-libs` at a fixed revision into `.deps/`,
configures the `windows-x64` preset, builds engine and game DLLs, and copies
dependency DLLs beside the executable. It does not download paid game data.
To use an existing dependency checkout, supply `-DependenciesPath` pointing
to its `x86_64-w64-mingw32` directory. Supply
`-Generator 'Visual Studio 17 2022'` to choose VS 2022 explicitly.

The launcher discovers Steam through its registry entry, reads extra libraries
from `libraryfolders.vdf`, and uses app **9050**'s manifest install directory.
Install **original DOOM 3** in Steam. BFG Edition's data is incompatible.
The store's combined DOOM 3 purchase page and the original game's install
app ID are different; see [upstream installation instructions](https://dhewm3.org/#how-to-install).

All nine nonempty `base/pak000.pk4` through `pak008.pk4` archives are required.
`-CheckOnly` reports discovery without launching or saving a preference.
When launching, a valid path is saved under `%APPDATA%/dhewm3/gamepath`.

```powershell
./scripts/windows-run.ps1 -GameData 'D:/SteamLibrary/steamapps/common/Doom 3' -CheckOnly
./scripts/windows-run.ps1 -EngineArgs @('+set', 'r_fullscreen', '0')
./scripts/windows-run.ps1 -EngineArgs @('+set', 'fs_game', 'd3xp')
```

Resurrection of Evil additionally needs its own installed data, including
`d3xp/pak000.pk4`; a folder containing only expansion patch archives is
incomplete. Steam's **Properties → Installed Files → Verify integrity** can
repair the selected game's files. Install the expansion separately if owned.

To launch this fork from Steam, use **Games → Add a Non-Steam Game** and add
`build-windows/RelWithDebInfo/dhewm3.exe`. Set its launch options to
`+set fs_basepath "C:/Program Files (x86)/Steam/steamapps/common/Doom 3"`
(adjust for your library). Keep the original game's executable in place.

## Validation

```powershell
./tests/windows-launchers.ps1
cmake -S neo --list-presets
```

The launcher checks presence and size, not archive CRCs. Gameplay validation
requires starting a level, checking sound and input, and saving/reloading.
The non-Steam shortcut runs this fork; launching app 9050 normally runs the
original Steam executable.

Local verification on 2026-10-03: Visual Studio 2026 and CMake 4.3.1 built
`dhewm3.exe`, `base.dll`, and `d3xp.dll`. A startup check loaded
`game/mars_city1` from the original Steam installation, initialized OpenGL
and OpenAL, and exited normally. Textured gameplay and the HUD were observed;
the user confirmed physical keyboard/mouse controls and F5 quicksave.
The resulting QuickSave was restored by the rebuilt engine and exited normally.
