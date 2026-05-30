# ABOUT

This is a fork of [dhewm3](https://github.com/dhewm/dhewm3), a _Doom 3_ GPL source port,
focused on delivering easy, well-maintained builds for **macOS** and **Linux**. macOS with
**Apple Silicon (arm64) is the primary target**; Intel (x86_64) macOS and Linux x86_64/arm64
are fully supported secondary targets.

Upstream dhewm3 also supports Windows and FreeBSD. This fork does not break any of that,
but macOS and Linux are the focus of active development and testing here.

**Upstream dhewm3 homepage:** https://dhewm3.org  
**Upstream project:** https://github.com/dhewm/dhewm3  
**This fork:** https://github.com/awest813/Dewm-3  
**Upstream FAQ:** https://github.com/dhewm/dhewm3/wiki/FAQ  
**Upstream mods:** https://dhewm3.org/mods.html  


# WHAT THIS FORK ADDS

On top of everything in upstream dhewm3, this fork ships:

- **`scripts/macos-setup.sh`** — one-command build: installs Homebrew deps, auto-detects your
  CPU (arm64 or x86_64), configures with a named CMake preset, compiles, and creates a
  `dhewm3.app` bundle + DMG.
- **`scripts/macos-run.sh`** — launcher that auto-discovers Steam / GOG game data and launches
  dhewm3 without needing to type `+set fs_basepath …`.
- **`scripts/macos-bundle.sh`** — assembles `dhewm3.app` and packages it into a DMG.
- **`scripts/macos-firstrun.sh`** — the app's `CFBundleExecutable`; on first launch it shows a
  folder-picker (via `osascript`) and saves the chosen Doom 3 data path to
  `~/Library/Application Support/dhewm3/gamepath` for all future launches.
- **Named CMake presets** (`macos-arm64`, `macos-intel`, `macos-universal`, `linux-x86_64`,
  `linux-arm64`, `linux-release`) in `neo/CMakePresets.json`.
- **GitHub Actions CI** that builds macOS DMG and Linux tarball artifacts on every push/PR.
- **`docs/MACOS.md`** — comprehensive macOS documentation covering the support matrix,
  game-data setup, CMake presets, CI, signing, release procedure, and troubleshooting.
- **`scripts/linux-setup.sh`** — one-command Linux build: detects your distro's package
  manager, installs dependencies, configures with a named preset, compiles, and packages.
- **`scripts/linux-run.sh`** — launcher that auto-discovers Steam (including Flatpak Steam),
  GOG, and common install locations; saves the path for future launches.
- **`scripts/linux-package.sh`** — creates a portable tarball (and optionally an AppImage).
- **`docs/LINUX.md`** — comprehensive Linux documentation covering the support matrix,
  game-data discovery, CMake presets, AppImage packaging, CI, and troubleshooting.

Inherited from upstream dhewm3:

- 64-bit port
- SDL for low-level OS support, OpenGL and input handling
- OpenAL for audio output; OpenAL EFX for EAX-like reverb on all platforms
- Gamepad support
- Better support for widescreen and arbitrary display resolutions
- An advanced, mod-independent settings menu (open with `F10`)
- A portable CMake build system

See [Changelog.md](./Changelog.md) for a full upstream changelog.


# PLAYING ON macOS

## Fastest path (no Terminal needed)

1. **Get Doom 3 game data** — buy *DOOM 3* on [Steam](https://store.steampowered.com/app/208200/DOOM_3/)
   or GOG. The Steam version is already patched to 1.3.1.

2. **Download a pre-built DMG** from the [Releases page](../../releases/latest):
   - `dhewm3-macos-arm64.dmg` — Apple Silicon (M1/M2/M3)
   - `dhewm3-macos-x86_64.dmg` — Intel
   - `dhewm3-macos-universal-signed.dmg` — both architectures, signed (no security prompt)

3. **Open the DMG** and drag `dhewm3` to your Applications folder.

4. **Launch `dhewm3`** — a folder-picker appears on first launch. Select your Doom 3
   installation folder (the one that contains `base/`). The path is saved; future launches
   go straight to the game.

> **First-time macOS security note**  
> If macOS says *"dhewm3 cannot be opened because it is from an unidentified developer"*,
> right-click (or Control-click) `dhewm3` in Applications, choose **Open**, then click
> **Open** in the dialog. You only need to do this once. Use the signed DMG to avoid this
> entirely — see [docs/SIGNING.md](./docs/SIGNING.md) for how to enable signing.

## Building from source (macOS)

Install [Homebrew](https://brew.sh) if you haven't already, then run the one-step setup
script from the repository root:

```sh
./scripts/macos-setup.sh
```

This installs the required libraries, auto-detects your CPU (arm64 or x86_64), configures,
builds dhewm3, and produces a `dhewm3.app` bundle + DMG in one step. To launch:

```sh
./scripts/macos-run.sh              # auto-discovers Steam / GOG game data
./scripts/macos-run.sh /path/to/doom3/   # or supply the path explicitly
```

For manual CMake invocations using named presets:

```sh
brew install cmake openal-soft sdl2 curl
cmake -S neo --preset macos-arm64   # Apple Silicon (use macos-intel for Intel)
cmake --build build --parallel
```

See [docs/MACOS.md](./docs/MACOS.md) for the full support matrix, CMake preset reference,
CI details, signing/notarization, troubleshooting, and the release maintainer guide.

**Apple Silicon user testing (e.g. MacBook Air M1):** [docs/MACOS-USER-TEST-M1.md](./docs/MACOS-USER-TEST-M1.md) —
preflight script, test checklist, and feedback template.


# PLAYING ON LINUX

## Fastest path (no build required)

1. **Get Doom 3 game data** — buy *DOOM 3* on [Steam](https://store.steampowered.com/app/208200/DOOM_3/)
   or GOG. The Steam version is already patched to 1.3.1.

2. **Download a pre-built tarball** from the [Releases page](../../releases/latest):
   - `dhewm3-linux-x86_64.tar.gz` — 64-bit Intel/AMD
   - `dhewm3-linux-arm64.tar.gz` — 64-bit ARM (Raspberry Pi 4/5, etc.)

3. **Extract and run:**
   ```sh
   tar -xzf dhewm3-linux-x86_64.tar.gz
   cd dhewm3
   ./dhewm3 +set fs_basepath /path/to/doom3/
   ```

## Building from source (Linux)

Install dependencies and build with the one-step setup script:

```sh
./scripts/linux-setup.sh           # auto-detects distro and CPU
./scripts/linux-run.sh             # auto-discovers Steam / GOG game data
./scripts/linux-run.sh /path/to/doom3/   # or supply path explicitly
```

See [docs/LINUX.md](./docs/LINUX.md) for the full support matrix, CMake preset reference,
packaging, AppImage creation, CI details, and troubleshooting.


# GENERAL NOTES

## Game data and patching

This source release does not contain any game data. The game data is still covered by the
original EULA and must be obeyed as usual.

You must patch the game to version 1.3.1. See the [upstream FAQ](https://github.com/dhewm/dhewm3/wiki/FAQ)
for details, including how to get the game data from Steam on Linux or macOS.

*DOOM 3* and *Doom 3: Resurrection of Evil* are available on Steam:  
https://store.steampowered.com/app/208200/DOOM_3/

*DOOM 3: BFG Edition* is **not** supported by dhewm3.

## Configuration

See [Configuration.md](./Configuration.md) for dhewm3-specific configuration, especially
for using gamepads or the new settings menu.

## Compiling (Linux)

See **[docs/LINUX.md](./docs/LINUX.md)** for the full Linux guide, including the support
matrix, game-data auto-discovery, CMake presets, AppImage packaging, and troubleshooting.

### Quick start (Ubuntu / Debian)

```sh
sudo apt install cmake build-essential libsdl2-dev libopenal-dev libcurl4-openssl-dev
git clone https://github.com/awest813/Dewm-3.git && cd Dewm-3
./scripts/linux-setup.sh           # auto-detects x86_64 or arm64
./scripts/linux-run.sh             # auto-discovers Steam / GOG game data
./scripts/linux-run.sh /path/to/doom3/   # or supply path explicitly
```

Or using CMake presets directly:

```sh
cmake -S neo --preset linux-x86_64   # or linux-arm64
cmake --build build --parallel
./build/dhewm3 +set fs_basepath /path/to/doom3/
```

## Compiling (Windows)

The build system is CMake-based. Pre-built dependency binaries are available from the
upstream project at https://github.com/dhewm/dhewm3-libs. See the [upstream README](https://github.com/dhewm/dhewm3/blob/master/README.md)
for detailed Windows build instructions.

## Back End Rendering of Stencil Shadows

The Doom 3 GPL source code release did **not** include functionality enabling rendering of
stencil shadows via the "depth fail" method (commonly known as "Carmack's Reverse").  
It has been restored in dhewm3 1.5.1 after Creative Labs'
[patent](https://patents.google.com/patent/US6384822B1/en) finally expired.

This does not change the visual appearance of the game.

## MayaImport

The code for the Maya export plugin is included. If you are a Maya licensee you can obtain
the SDK from Autodesk.


# LICENSE

See COPYING.txt for the GNU GENERAL PUBLIC LICENSE

ADDITIONAL TERMS:  The Doom 3 GPL Source Code is also subject to certain additional terms. You should have received a copy of these additional terms immediately following the terms and conditions of the GNU GPL which accompanied the Doom 3 Source Code.  If not, please request a copy in writing from id Software at id Software LLC, c/o ZeniMax Media Inc., Suite 120, Rockville, Maryland 20850 USA.

EXCLUDED CODE:  The code described below and contained in the Doom 3 GPL Source Code release is not part of the Program covered by the GPL and is expressly excluded from its terms.  You are solely responsible for obtaining from the copyright holder a license for such code and complying with the applicable license terms.

## Dear ImGui

neo/libs/imgui/*

The MIT License (MIT)

Copyright (c) 2014-2024 Omar Cornut

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## PropTree

neo/tools/common/PropTree/*

Copyright (C) 1998-2001 Scott Ramsay

sramsay@gonavi.com

http://www.gonavi.com

This material is provided "as is", with absolutely no warranty expressed
or implied. Any use is at your own risk.

Permission to use or copy this software for any purpose is hereby granted
without fee, provided the above notices are retained on all copies.
Permission to modify the code and to distribute modified code is granted,
provided the above notices are retained, and a notice that the code was
modified is included with the above copyright notice.

If you use this code, drop me an email.  I'd like to know if you find the code
useful.

## Base64 implementation

neo/idlib/Base64.cpp

Copyright (c) 1996 Lars Wirzenius.  All rights reserved.

June 14 2003: TTimo <ttimo@idsoftware.com>

modified + endian bug fixes

http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=197039

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

## miniz

src/framework/miniz/*

The MIT License (MIT)

Copyright 2013-2014 RAD Game Tools and Valve Software
Copyright 2010-2014 Rich Geldreich and Tenacious Software LLC

All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

## IO on .zip files using minizip

src/framework/minizip/*

Copyright (C) 1998-2010 Gilles Vollant (minizip) ( http://www.winimage.com/zLibDll/minizip.html )

Modifications of Unzip for Zip64
Copyright (C) 2007-2008 Even Rouault

Modifications for Zip64 support
Copyright (C) 2009-2010 Mathias Svensson ( http://result42.com )

This software is provided 'as-is', without any express or implied
warranty.  In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.
2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.

## MD4 Message-Digest Algorithm

neo/idlib/hashing/MD4.cpp

Copyright (C) 1991-2, RSA Data Security, Inc. Created 1991. All
rights reserved.

License to copy and use this software is granted provided that it
is identified as the "RSA Data Security, Inc. MD4 Message-Digest
Algorithm" in all material mentioning or referencing this software
or this function.

License is also granted to make and use derivative works provided
that such works are identified as "derived from the RSA Data
Security, Inc. MD4 Message-Digest Algorithm" in all material
mentioning or referencing the derived work.

RSA Data Security, Inc. makes no representations concerning either
the merchantability of this software or the suitability of this
software for any particular purpose. It is provided "as is"
without express or implied warranty of any kind.

These notices must be retained in any copies of any part of this
documentation and/or software.

## MD5 Message-Digest Algorithm

neo/idlib/hashing/MD5.cpp

This code implements the MD5 message-digest algorithm.
The algorithm is due to Ron Rivest.  This code was
written by Colin Plumb in 1993, no copyright is claimed.
This code is in the public domain; do with it what you wish.

## CRC32 Checksum

neo/idlib/hashing/CRC32.cpp

Copyright (C) 1995-1998 Mark Adler

## stb_image and stb_vorbis

neo/renderer/stb_image.h
neo/sound/stb_vorbis.h

Used to decode JPEG and OGG Vorbis files.

from https://github.com/nothings/stb/

Copyright (c) 2017 Sean Barrett

Released under MIT License and Unlicense (Public Domain)

## Brandelf utility

neo/sys/linux/setup/brandelf.c

Copyright (c) 1996 Søren Schmidt
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer
   in this position and unchanged.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
3. The name of the author may not be used to endorse or promote products
   derived from this software withough specific prior written permission

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

`$FreeBSD: src/usr.bin/brandelf/brandelf.c,v 1.16 2000/07/02 03:34:08 imp Exp $`

## makeself - Make self-extractable archives on Unix

neo/sys/linux/setup/makeself/*, neo/sys/linux/setup/makeself/README
Copyright (c) Stéphane Peter
Licensing: GPL v2
