# Web port (Emscripten / WebAssembly) — audit & plan

> **Status: experimental renderer implementation through phase 4d.**
> The WebGL2 compatibility layer and material shaders are implemented, but
> a successful build is not proof of visual correctness or playable gameplay.
> CI compiles and links the engine without game data with Emscripten 4.0.23.
> Browser validation of rendering, audio, input, and save persistence remains
> required before this target can be called supported.

Latest accuracy evidence (2026-10-05): explicit double precision in vector
angle conversion resolves the recorded native/browser AI random-state
divergence and mask-only campaign haze/background comparison. All 596 trace
checkpoints and three render-state checkpoints in that fixture now match.
See **Vector-angle precision correction** below for tests, PNG measurements
and limits. Broader campaign, physical pointer capture, browser recovery and
sustained performance coverage remain unfinished.

The explosive-weapon audit found a grenade rigid-body mismatch, now corrected
by preserving native precision in generated cylinder/cone collision vertices.
Its recorded trajectory, splash damage and knockback now match. The longer
fixture still exposes a rocket launch/flight mismatch; see **Collision-shape
precision correction** below. Passing the earlier movement and AI fixtures
does not establish general gameplay accuracy.

Local verification on 2026-10-03: Emscripten 4.0.23 compiled and linked the
engine without game data, producing `dhewm3.html`, `dhewm3.js`, and
`dhewm3.wasm`. The browser shell's data-validation regression tests passed.
Browser checks now reach textured Mars City gameplay with a health HUD,
restore a browser save after page reload, and accept Escape to skip the
cinematic. A browser W key moved the player from x=1267 to x=1263.77;
F5 created QuickSave, which restored successfully with the same position.
Physical movement/mouse look and audible sound still need user
confirmation; material fidelity is still under review. The WebGL layer now
recreates recycled buffers when their target changes, copies packed depth
through a framebuffer blit, and converts RGB screenshot reads from RGBA.

Additional runtime checks: Mars City Underground loads, objective camera
screenshots finish, pistol fire consumes ammunition, reloading and switching
to the shotgun work, a spawned maintenance zombie animates and attacks, and
the player-death menu restarts the level. Full `vid_restart` preserves gameplay;
renderer-owned buffers/framebuffers and emulated state reset on context init.
`webaudioinfo` reports a running WebAudio context with playing OpenAL sources.
This proves scheduled audio, not audibility at the user's speakers.

Known validation blocker: Codex's in-app browser reports a Chromium error
when SDL requests pointer lock. The shell no longer duplicates SDL's request,
and reports capture success/failure under Controls. Test physical mouse look
in a desktop browser at `http://localhost:8080/dhewm3.html` before declaring
the port fully playable. Desktop-browser automation was stopped because its
current URL could not be reliably identified by the computer-use policy check.

Prior art: upstream dhewm3 1.5.1 notes Doom 3 demo support based on
[Gabriel Cuvillier's D3Wasm](http://www.continuation-labs.com/projects/d3wasm/)
(see `Changelog.md`). That proves Doom 3 *can* run in a browser, but this fork
has since diverged (ImGui `F10` menu, soft particles, EFX/HRTF audio, 64-bit
cleanups) and now has an experimental WebGL2 backend.

---

## 1. How the engine is structured today

- Entry points (blocking `while(1) common->Frame()` loop):
  `neo/sys/linux/main.cpp:410`, `neo/sys/win32/win_main.cpp:1006`,
  `neo/sys/aros/aros_main.cpp:931`. Framework: `neo/framework/Common.cpp`
  (`Init`/`Frame`/`Shutdown`), `neo/framework/EventLoop.cpp`,
  `neo/framework/Session.cpp`.
- Platform layer: `neo/sys/{cpu,threads,events,sys_local,glimp}.cpp`,
  OS backends `neo/sys/{posix,linux,win32,osx,aros}/`. There is **no**
  `neo/sys/sdl/` directory — SDL2 calls live directly in the shared files.
- Build: `neo/CMakeLists.txt` (deps: OpenAL **REQUIRED**, SDL2 **REQUIRED**
  when `SDL2=ON`, CURL optional, vendored miniz/minizip/stb/imgui — no system
  zlib). Options include `HARDLINK_GAME`, `DEDICATED`, `IMGUI`, `SDL2`, `TOOLS`.
- Presets today (`neo/CMakePresets.json`): `linux-x86_64`, `linux-arm64`,
  `linux-release`, `macos-arm64`, `macos-intel`, `macos-universal`. New in this
  prep: `web-wasm` (see §6).
- Game logic: `neo/game/` (base) + `neo/d3xp/` built as **shared libraries**
  (`base.so`/`d3xp.so`, `GAME_DLL`) loaded via `dlopen`/`LoadLibrary`
  (`neo/sys/posix/posix_main.cpp:290`, `neo/sys/win32/win_main.cpp:627`,
  `neo/framework/Common.cpp:2696`).

## 2. Portability constraints (original audit)

The table records the initial porting constraints, not a list of current
failures. The cooperative loop, hardlinked base game, WebAudio defaults,
browser filesystem, and WebGL compatibility layer are implemented. Use the
runtime evidence and remaining validation blocker above for current status.

| # | Blocker | Where | Web fix |
|---|---------|-------|---------|
| 1 | **Renderer is legacy GL compat, not GLES/WebGL2.** Fixed-function calls (`glBegin`, `GL_QUADS`, matrix stack, `GL_COMBINE_ARB`, client arrays in `draw_common.cpp`), `GL_VERTEX/FRAGMENT_PROGRAM_ARB` assembly shaders (`draw_arb2.cpp`, `glprogs/*.vfp`) | `neo/renderer/qgl.h`, `qgl_proc.h`, `RenderSystem_init.cpp`, `draw_common.cpp`, `draw_arb2.cpp`, `VertexCache.cpp`, `neo/sys/glimp.cpp` | **Rewrite required.** Request GLES3 context (`SDL_GL_CONTEXT_PROFILE_ES`), port interactions/ambient/shadow/soft-particle/megaTexture shaders to GLSL-ES 3.0, replace VBO/VAO paths, force `r_gammaInShaders 1`, `r_useDepthBoundsTest 0`, stencil-separate path only, handle S3TC → ETC2/ASTC or decompress |
| 2 | **Blocking main loop.** `while(1)` + `SDL_Delay` | `sys/*/main.cpp`, `framework/EventLoop.cpp` | `emscripten_set_main_loop(common->Frame)` / `emscripten_sleep`; canvas resize handling |
| 3 | **Game DLLs via `dlopen`.** Browsers can't `dlopen` host `.so`s | `sys/posix/posix_main.cpp`, `framework/Common.cpp`, `config.h.in` | **Mandatory `HARDLINK_GAME=ON`**, base **or** d3xp only (pick base first) |
| 4 | **Filesystem is POSIX sync I/O.** `fopen`/`opendir`/`stat`, `fs_basepath`/`fs_savepath`, 2 GB+ `.pk4` streaming | `framework/FileSystem.cpp`, `sys/posix/posix_main.cpp:Sys_Mkdir/ListFiles`, `sys/linux/main.cpp:187` `Sys_GetPath` | `--preload-file` for demo/shareware paks + IDBFS mount (`/home/web_user/.config/dhewm3`) + `FS.syncfs()` for saves/configs; stub `Sys_GetDriveFreeSpace`; never load whole pak into heap |
| 5 | **x86 asm / SSE intrinsics / `cpuid` / FPU control.** Won't compile for `wasm32` | `sys/cpu.cpp`, `idlib/math/Math.h`, `idlib/math/Simd_SSE*.cpp`, `Simd_MMX/3DNow.cpp`, `Simd.cpp` dispatch | Build `Simd_Generic.cpp` only; stub `Sys_GetProcessorId()` → `GENERIC`, skip `STREFLOP_FSTCW/MXCSR` under `__EMSCRIPTEN__` |
| 6 | **OpenAL EFX/HRTF/limiter assumptions.** Emscripten OpenAL is a WebAudio subset | `sound/snd_system.cpp`, `snd_efxfile.cpp`, `snd_world.cpp`, `snd_local.h` | Force `s_useEAXReverb 0`, `s_alHRTF 0`, `s_alOutputLimiter 0`; expect no `alcResetDeviceSOFT`/EFX; handle autoplay-policy resume on first gesture; `s_noSound` fallback must keep working |
| 7 | **ImGui `opengl2` backend.** Immediate-mode, fixed-function | `libs/imgui/backends/imgui_impl_opengl2.cpp`, `sys/sys_imgui.cpp` (plus `dlopen(libX11)` DPI hack) | Switch to existing `imgui_impl_opengl3` + `imgui_impl_sdl2`, or `IMGUI=OFF` for first bring-up (preset does the latter) |
| 8 | **Threads (SDL mutex/cond/thread).** Needs SharedArrayBuffer + COOP/COEP or single-thread stubs | `sys/threads.cpp`, `framework/BuildDefines.h` (`MAX_THREADS 10`) | Either `-pthread -sSHARED_MEMORY -sPTHREAD_POOL_SIZE` + proper headers, or DEDICATED-style single-thread stubs (pattern: `sys/stub/openal_stub.cpp`, `stub_gl.cpp`) |
| 9 | **Sockets + libcurl.** Multiplayer UDP/TCP + HTTP pak downloads don't map to the web | `sys/posix/posix_net.cpp`, `sys/win32/win_net.cpp`, `framework/async/*`, `framework/FileSystem.cpp` curl block, `config.h.in` `ID_ENABLE_CURL` | `ID_ENABLE_CURL OFF` on web; disable server scan/multiplayer, keep loopback/demo playback; downloads via `fetch` shim later |
| 10 | **Stack/memory sizing.** 8 MB stack assumption, unbounded heap growth | `CMakeLists.txt` ldflags, `sys/platform.h:43`, `renderer/Cinematic.cpp`, `MegaTexture.cpp` | `-sSTACK_SIZE=8MB -sALLOW_MEMORY_GROWTH=1 -sMAXIMUM_MEMORY=2GB` (tune after profiling) |

Endianness is fine (`wasm32` is LE; `idlib/Lib.cpp` already handles it via
`SDL_BYTEORDER`). `stb_image`/`stb_vorbis`/miniz/minizip are pure C and
Emscripten-friendly. `D3_ARCH`/`D3_SIZEOFPTR` plumbing already handles 32-bit
(`wasm32` = 4-byte pointers; expect savegames to be incompatible with x64
builds — same as the existing macOS universal note).

## 3. Port strategy (phases)

1. **Prep (done).** Docs + preset + shell + setup script + CI smoke.
2. **Minimal configure (done).** `if(EMSCRIPTEN)` guards in `neo/CMakeLists.txt`
   (ports, `HARDLINK_GAME=ON`, `IMGUI/CURL/backtrace/X11` off, `Simd_Generic`
   only, `.html` shell output); `sys/platform.h` Emscripten section;
   `sys/cpu.cpp` + `idlib/math/Simd.cpp` generic-only; `sys/linux/main.cpp`
   `emscripten_set_main_loop` + IDBFS-friendly save path; `sound/snd_system.cpp`
   WebAudio-safe defaults; `sys/sys_imgui.cpp` X11 `dlopen` guard.
   Goal: `emcmake` configure succeeds; renderer compilation is covered by
   the compile job, while browser correctness requires a separate check.
3. **GL-stub hello-canvas (done, phase 3a).** `sys/stub/stub_gl.cpp`-style
   tolerance + `web/shell.html` canvas: `R_GLES_LoadFunctions()` resolves real
   GLES3 entry points and no-ops the rest, `R_GLES_InitConfig()` reports a
   WebGL2-safe `glConfig` (VBO/S3TC/depth-bounds off, ARB-program emulation on),
   `R_LoadARBProgram` maps every `.vfp` to one shared passthrough GLSL-ES
   program. Milestone: link + boot + cleared canvas + engine console output.
4. **Renderer port (in progress — phase 4, the big one).**
   - Heat-haze variants now have a dedicated GLSL shader with scroll,
     distance-scaled distortion, mask discard, and vertex fading. Browser
     testing removed the black rectangles produced by the generic fallback.
   - DONE (phase 4a, `renderer/tr_gles.cpp`): real VBO submission (vertex-cache
     design maps 1:1 onto core `BufferData/SubData`, `Position()` offsets);
     Blinn-Phong GLSL-ES interaction shader (same maps/colors/falloff as
     `interaction.vfp`, packed RXGB normals and engine specular-table lookup);
     MVP shadow-volume shader with CPU-extruded volumes
     (`r_useShadowVertexProgram 0`, `r_useIndexBuffers 1` forced on web);
     matrix-stack mirror with per-draw MVP sync (incl. per-surface
     `modelViewMatrix` and ortho 2D); client arrays reimplemented as attribs;
     all alpha comparisons as shader discard; legacy texture formats translated
     (luminance via R8/RG8 + swizzle, BGR(A) swizzled on CPU).
   - DONE (phase 4b, `renderer/tr_gles.cpp`): fog + blend lights + projected/
     screen textures via OBJECT_PLANE texgen emulation in the flat program
     (draw-time program sync, since those paths bind no ARB program);
     environment / bumpy-environment reflection shaders; glasswarp shader;
     live env-param uniform upload (engine writes params between bind and
     draw); vertex-color/white-material tracking (`u_useVtx`); gamma from
     cached env slot 21 (post-process single-application preserved).
   - DONE (phase 4c, `renderer/tr_gles.cpp`): faithful soft-particle port
     (ARB source transliterated incl. Doom-3 depth constants, no-gamma like
     the original) + packed depth/stencil textures and framebuffer-blit
     depth capture; sky / diffuse-irradiance cubes
     via unit-0-cube detection at draw time (`samplerCube` direction lookup);
     stale-interaction demotion (explicit `R_GLES_MarkInteraction` window
     around `RB_ARB2_CreateDrawInteractions` + self-healing on rebind).
   - DONE (phase 4d): S3TC detected at runtime (`WEBGL_compressed_texture_s3tc`
     enable + `glCompressedTexImage2D` mapping; uncompressed fallback where
     absent); `reloadARBprograms` relinks compiled-in GLSL; opt-in
     `-DWEB_THREADS=ON` pthreads experiment (serve.py sends COOP/COEP;
     single-threaded stays the default).
   - TODO: MegaTexture (compiles; stock maps don't use it), render-target
     compressed paths, Emscripten perf pass, `-pthread` validation,
     multiplayer/WebSockets, touch controls.
5. **Audio + input + saves.** WebAudio OpenAL subset, pointer-lock/mouse,
   touch/gamepad mapping, `FS.syncfs()` on save/config write + page hide.
6. **Packaging.** `emcc` flags, `--preload-file` vs. remote pak streaming,
   COOP/COEP headers if pthreads, demo-data legal check (game data is **not**
   GPL — same rule as desktop: user supplies `base/pak*.pk4`).

## 4. Game-data / legal note

This source release contains **no game data** (see `README.md`). The web port
must do the same: ship engine `.js`/`.wasm` only; at runtime load user-supplied
`base/pak*.pk4` (Steam/GOG/1.3.1/demo where permitted). Do not commit pak files.

## 5. Quick start (current state)

```sh
# 1. Install Emscripten SDK (emsdk) and activate it:
#    https://emscripten.org/docs/compiling/Building-Projects.html
#    emsdk install 4.0.23 && emsdk activate 4.0.23 && source ./emsdk_env.sh

# 2. Environment check:
./scripts/web-setup.sh --check-only

# 3. Configure + build:
emcmake cmake -S neo --preset web-wasm -B build-web
cmake --build build-web --parallel

# 4. Serve locally (correct .wasm MIME + COOP/COEP headers):
./scripts/web-run.sh                  # -> http://localhost:8080/dhewm3.html
```

### Game data (your Doom 3 install — never committed)

Two flows, same engine path (`+set fs_basepath /doom3`):

- **In-page picker (default, shareable builds):** open `dhewm3.html`, choose
  *Select Doom 3 folder…* (File System Access API where available, with
  `<input webkitdirectory>` / multi-`.pk4` fallback). Files are staged to
  `/doom3/base` in MEMFS; only the nine original `pak000.pk4` through
  `pak008.pk4` files are read. Expansion/mod archives and unrelated files
  are skipped before allocating their buffers. Then press Launch Doom 3.
- **Preloaded at build time (local testing only):**
  `emcmake cmake -S neo --preset web-wasm -B build-web -DWEB_PRELOAD_DIR=/path/to/doom3`
  bakes `<dir>/base` to `/doom3/base` in the `.data` bundle; the page detects
  all nine required archives and skips the picker. Do not distribute the bundle (game data
  is not GPL).

### Saves, input, audio

- Saves/configs live at `/home/web_user/.local/share/dhewm3` (same layout as
  desktop `PATH_SAVE`), backed by IDBFS: loaded at startup and automatically
  persisted when files close. Wait for writes to finish before closing the tab.
  Saves belong to this browser and origin. The toolbar reports whether
  browser save storage initialized successfully.
- Click the canvas once for pointer lock (drives SDL relative-mouse mode);
  <kbd>Esc</kbd> releases. Audio resumes on first click (autoplay policy).
- <kbd>Esc</kbd> opens the game menu; <kbd>Shift</kbd>+<kbd>Esc</kbd> opens
  the engine console. The optional page console also accepts engine commands.

### Shell audit and polish

The picker now excludes unrelated files before reading, normalizes archive
name casing, prevents overlapping loads, and marks incomplete data as a
warning. Failed startup or runtime abort keeps recovery instructions and
the console visible; the engine cannot be initialized twice. Console visibility
can be changed during play. The layout has responsive spacing, visible keyboard
focus, an accessible game-canvas label, and loading/storage/mouse status text.
Regression checks cover loader filtering, overlapping selections, incomplete
data, startup failure, input isolation, and pointer-lock status.

The launcher now presents a two-step setup card instead of an empty game canvas.
It explains Steam file selection, the nine required archives, and which data
survives a page reload. File selection is disabled until runtime initialization
finishes. Loading reports archive counts; completion focuses Launch Doom 3 for
keyboard users. An unrelated flat-file selection preserves staged archives.
Folder-picker failures expose the direct-file alternative; canceling the picker
keeps the existing state. Failed startup/abort disables unusable controls and
offers Reload launcher beside the diagnostic console. Persistent-storage mount
failure permits session-only play with a visible warning, provided MEMFS works.

Folder imports discover matching archive entries before replacing loaded data.
Empty folders and failed directory scans retain the existing selection. A read
failure for one archive is logged while the remaining archives continue loading;
the final missing-file list keeps launch disabled until the set is complete.
Both import paths display the number of nonempty archives loaded during staging.
After an engine failure, keyboard focus moves to Reload launcher. Picker and
launch buttons describe their status through accessible labels. Play controls
and graphics actions wrap at narrow widths without requiring horizontal scrolling.

After launch, the canvas fits the desktop viewport while preserving its 4:3
aspect ratio. Focus game returns keyboard focus and requests capture when the
engine wants mouse input. Mouse/save status remains visible next to play controls;
graphics, key-binding help and diagnostics are secondary panels. Invalid gamma
or brightness focuses the offending field and sets `aria-invalid` before any
engine writes. The setup stacks into a single column at narrow widths.

Graphics options exposes the same three Frame rate choices through Apply
graphics. The archived `r_webFrameLimit` setting uses `30`, `60`, or `0`
(Unlocked). A deadline gate on browser animation callbacks limits rendered
frames independently of the fixed game ticks. Late callbacks skip missed
render deadlines instead of bursting; changing limits takes effect on the next
callback. This sets a maximum, not a guarantee of performance in complex scenes.

Frame-limit validation on 2026-10-04 passed the Release WebAssembly and Windows
builds, shell regressions, 97 gameplay/input/graphics checks and 98 menu checks.
The timing harness exercises caps at 30, 60, 90, 120, 144 and 240 Hz display
callbacks, preserving native fixed-tick counts, handling jitter, live switching,
and avoiding bursts after a long gap. In the loaded Mars City hangar, 60-frame
samples measured 30.1 FPS with the 30 cap, 57.5 FPS with the 60 cap, and 59.3 FPS
unlocked in the embedded browser. The stock Advanced menu cycles the same values
with arrow keys, and its former Yes/No field is widened for the full Unlocked
label. The setting was restored to 60 and player position remained
`(1263.77 -1501 68.25) 180`. These measurements reflect one scene and device.
The final build visually verified the full Unlocked label. Opening launcher
Graphics options read back Unlocked after it was selected in-game; the expanded
panel still had no horizontal overflow at a 320-pixel viewport. The default
60 FPS choice persisted across the rebuild/page reload.

Screenshot captures a PNG through the engine and exposes a Download PNG link.
Capture runs through the command queue and disables the toolbar button until
the engine reports success or failure. The web-only `webscreenshot [width height]`
command accepts sizes from 1 to 4096 per dimension; omitting a size captures the
current render dimensions. Capture does not change the screenshot-format option
or scissor setting. Download uses a direct user click to accommodate browser
download policy. The current PNG remains available for retry until replaced by
another successful capture or the page is reloaded; replacement releases its
temporary object URL. The toolbar does not claim the file was saved.

Local validation: Release WebAssembly linked successfully, and the expanded
shell regressions passed (including storage fallback, folder cancellation/error,
ready-button focus, failure recovery and graphics error focus). Browser checks
covered desktop and 390-pixel setup, an empty archive's disabled launch state,
all nine Steam archives, QuickSave restoration, console visibility, Focus game,
and invalid/corrected gamma. No horizontal overflow was observed at the narrow
viewport. Physical captured mouse input, audible output and lower-memory device
behavior remain separate checks.

The 2026-10-04 launcher follow-up passed Release WebAssembly linking and the
expanded shell regressions, including empty/failed folder scans, continued
loading after an unreadable archive, recovery focus, and screenshot replacement.
Browser checks imported all nine Steam archives, launched, and restored QuickSave.
Setup with installation help open and play with graphics controls open both
had equal client/scroll widths at a 320-pixel viewport (305 CSS pixels after
the scrollbar). Direct Download PNG clicks saved valid 866×648 and 640×480
captures. Invalid dimensions were rejected, `r_screenshotFormat` remained `0`,
an intentionally disabled scissor remained `0` after capture, and player
position stayed `(1263.77 -1501 68.25) 180`. Scissor was restored to `1` afterward.
Embedded-browser pointer lock still failed; the visible fallback instructions
remain appropriate. These launcher checks do not establish full game fidelity.

Remaining priorities:

1. Confirm captured physical mouse look and audible output in a desktop
   browser; the embedded browser cannot currently complete this check.
2. Compare representative campaign scenes with the Windows build, especially
   specular lighting, alpha-tested materials, and custom ARB-program fallback.
3. Profile memory and load times on lower-memory machines. Staging the nine
   retail archives still keeps their data in browser memory; filtering and
   ownership transfer reduce extra allocations but do not provide streaming.

See `scripts/web-setup.sh --help` and `web/shell.html` for the canvas shell.

### Rendering audit and polish

The interaction shader previously read normal-map X from red, although the
image loader packs it into alpha. Interaction and bumpy-reflection shaders now
decode `.agb`. Interaction lighting uses the engine-generated specular table,
its factor of two, diffuse light attenuation on specular, and the original
vertex half-vector calculation. Bumpy reflections use the original tangent
basis ordering and no longer apply an extra vertex-color multiplier.

Old-style ambient stages retain material tint when vertex colors are enabled,
including inverse RGB modulation. Alpha testing implements all eight OpenGL
comparisons and updates the active uniform immediately when comparison or
enable state changes. Fragment calculations use high precision for depth
effects. Heat-haze uniform locations are cached when programs link, and a
failed shader pair releases any successfully compiled partner.

Validation: Windows and WebAssembly builds passed. The browser restored
Mars City gameplay from QuickSave and compiled all nine engine shader programs.
`tests/render_shader_check.py` extracts the actual renderer GLSL into a local,
asset-free WebGL2 fixture. Its 41 checks passed: eight shader pairs compile and
link, alpha comparisons accept/reject pixels correctly, packed-normal lighting,
specular-table response, rejection of red specular highlights from back-facing
lights, material tint, inverse RGB modulation, and no GL errors.
The engine's heat-haze program is additionally compiled during game startup.

To repeat the GPU checks:

```sh
python tests/render_shader_check.py build-web/render-check.html
python web/serve.py --dir build-web --port 8080
```

Open `http://localhost:8080/render-check.html` and inspect the visible results.
These controlled pixel checks do not establish whole-campaign visual parity.
Next compare matching Windows/browser camera positions for glass, particles,
reflections, and masked materials, then port any remaining custom ARB programs
that still use the flat fallback. Browser pointer-lock failure is a separate
input limitation in the embedded browser.

A user reported solid red planes and rails while moving in the starting
hangar. The symptom persisted after the interaction shader corrections and
was reproduced at `setviewpos 1279.37 -1739.38 68.25 300`. Toggling soft
particles off removed it at that same viewpoint; toggling them on restored
it. Disabling state caching did not resolve it.

The cause was program-pair selection clearing the caller's interaction scope.
Vertex and fragment ARB programs are bound separately. Following particles
or heat haze, the first lighting bind temporarily formed a mismatched pair
and selected the flat program, which cleared the scope marker. Even after the
second bind selected the correct lighting pair, draw-time synchronization
demoted it to the flat shader. Lighting geometry could then sample a stale
2D texture left by another pass.

Program selection now preserves the scope owned by
`RB_ARB2_CreateDrawInteractions`; context initialization resets it. The
temporary particle fallback was removed. The rebuilt browser showed normal
rails at both the reproduction viewpoint and the nearby stair viewpoint
(`1267 -1550 68.25 180`) with `r_useSoftParticles 1`.

`tests/render_program_state_check.py` extracts the actual C++ state functions
into an asset-free harness. Its 34 checks cover both binding orders after
particles, heat haze, reflections, and the fixed pipeline, plus scope exit,
disabled programs, shadows, and texgen. Reintroducing the old scope reset
makes the first transition check fail. Generate the harness, compile it with
`em++ -sENVIRONMENT=node`, and run the generated JavaScript with Node; the web
build workflow also runs it. The separate 41 GPU shader checks still pass.
Broader shadow/lighting parity remains unfinished.

## 6. Mouse capture and frame profiling

Gameplay ignores unlocked hover, while menus retain absolute cursor movement.
The engine also rejects internally generated SDL motion while capture is
unavailable; only the fallback's marked relative events can turn the camera.
Pointer-lock requests from SDL and the canvas share one pending request; failed
Promises and missing completion events leave a visible cursor and permit a
later click to retry. The embedded Chromium host still returns `UnknownError`
on capture. When this happens, hold the right mouse button over the canvas to
look. Releasing the button, leaving the canvas, losing focus, or opening a menu
ends drag-look. The fallback measures movement from the right-click position
and sends relative SDL events with CSS-to-window scaling and fractional carry;
it does not depend on SDL's stale absolute cursor position.

The renderer tracks index-buffer bindings and deletions, including its scratch
buffer for CPU indices, instead of querying GL before each indexed draw. It
also skips redundant `glUseProgram` calls and repeated full uniform uploads
for consecutive CPU shadow draws. Unchanged ARB environment parameters skip
per-surface uniform uploads; shader activation refreshes the cached environment.
Matrix changes still update the active MVP.
`r_webStateCache 1` also caches actual per-program uniform values, vertex array
layouts/enables, and array/index buffer bindings. Attribute layouts include
the captured buffer object; deleting it invalidates the layout. Uniform cache
collisions cause an upload, and shader reload clears the cache. Setting the
option to `0` allows an in-game comparison while continuing to track writes.

The shadow shader now implements `shadow.vp`'s light-relative homogeneous
projection for shared vertices (`r_useShadowVertexProgram` defaults to `1`).
Private volumes retain their precomputed positions; each surface selects the
appropriate mode before drawing. The shadow vertex program also takes priority
over a stale heat-haze fragment binding. Transform-feedback GPU checks compare
near vertices, vertices at infinity, and private projected vertices against
the CPU result through a non-identity MVP matrix.
Recycled cache headers prefer a buffer with the same vertex/index
classification, avoiding GPU object replacement merely to change its type.
`r_webBufferReuse 0` restores the previous selection for comparison; the
default is `1`. A type mismatch still creates a fresh GPU object when no
compatible free header is available, preserving WebGL's binding rules.
All caches reset when a new context is created, and shader reload unbinds the
old program before deleting it.

Use `webperf 180` in the Engine command field to sample 180 frames (30–600
allowed). It reports average FPS, mean and 95th-percentile CPU frame time,
draws, index queries, program binds, full uniform uploads, GPU buffer creation, and CPU phase
timings. These are browser wall-clock/CPU submission measurements, not GPU
timer-query results. Keep the camera, window size, and game options fixed for
comparisons, and avoid compiling during a sample.
It also counts actual uniform writes, buffer binds and attribute writes, and
separates frame setup, scene generation and submission/cleanup.

The `web-wasm` preset now uses `Release`, with `-O3 -flto` for the hardlinked
engine/game and final WebAssembly optimisation. `web-wasm-debug` builds
`RelWithDebInfo` in `build-web-debug` for debugging without replacing the
release output. DWARF debug information limits the final Binaryen passes.

At the hangar viewpoint `1150 -1550 68.25 180`, with an 833×625 drawing buffer
and soft particles enabled, the initial 180-frame baseline was 36.0 FPS and
26.98 ms mean CPU time. The state optimizations removed approximately 902
index queries per frame, reduced program binds from 328 to 37, and reduced
full uniform uploads from 466 to 223. Follow-up FPS samples varied between
32.4 and 36.7; those state changes alone did not establish an FPS improvement.
After skipping unchanged environment uploads, a further sample was 37.1 FPS.

A separate 180-frame comparison in the same live game then isolated buffer
reuse. With `r_webBufferReuse 0`, the renderer created 195.2 GPU buffers per
frame and measured 33.8 FPS, 28.87 ms mean CPU time, and 37.41 ms p95. With
reuse enabled, creation dropped to 0.0 per frame and the sample measured
43.1 FPS, 22.49 ms mean CPU time, and 27.40 ms p95. Both samples had about
900 draws per frame; WebAudio had not yet resumed in either sample.
This local comparison shows roughly 28% more FPS and
22% less CPU time from compatible buffer reuse; it does not predict other
maps or hardware. Shader reload and runtime draw-error checks passed with
reuse enabled, and the rails still rendered normally.
An additional audio-enabled run reported a running context with ten playing
sources and 53.4 FPS, but only 753 draws per frame; that changed workload is
not a direct comparison with the earlier samples.

Validation includes the web shell input/data tests, 78 extracted renderer
state checks, 44 GPU shader checks, and 14 extracted drag-input bridge checks. The web workflow
runs the shell tests and both C++ harnesses without proprietary assets; the
GPU fixture runs in a local WebGL2 browser. Windows and WebAssembly builds
passed; normal pointer lock still needs a host that accepts it.

### 60 FPS performance audit (2026-10-04)

`GL_CheckErrors()` previously called `glGetError()` every frame even with
`r_ignoreGLErrors 1`, merely suppressing the resulting messages. On WebGL this
query can synchronize with the browser's GPU process. The web build now skips
the query when reporting is disabled. Set `r_ignoreGLErrors 0` to retain the
bounded error-draining/reporting diagnostic path; desktop behavior is unchanged.

A controlled 600-frame comparison used a frozen hangar rail view, a 708x531
drawing buffer, the 60 FPS cap, shadows and soft particles enabled. Each run
submitted exactly 940 draws, 64 program binds and 253 full uniform uploads per
frame, with no new GPU buffers:

| WebGL error polling | FPS | CPU mean | CPU p95 |
|--------------------|----:|---------:|--------:|
| Enabled, first control | 57.8 | 9.89 ms | 20.33 ms |
| Disabled, optimized path | 60.1 | 4.89 ms | 6.73 ms |
| Enabled again | 57.5 | 7.92 ms | 15.95 ms |

This isolates reduced CPU submission stalls for this frozen workload. It does
**not** establish sustained 60 FPS during live gameplay. With simulation running
and WebAudio confirmed running with 9–10 sources, the busy rail view still
measured roughly 51–57 FPS across samples, about 898–906 draws per frame, and
CPU p95 around 20–27 ms. Scene generation and backend submission remain the
largest phases. A quieter pre-audit view measured 59.8 FPS at about 413 draws.
Different actor states, cold caches and frame scheduling affect these live
samples, so they are not interchangeable before/after measurements.

Temporary-buffer storage orphaning was also tested with audio and simulation
running. It measured 51.9 FPS versus 55.7/55.5 FPS in the surrounding controls,
with similar draw counts, and was removed. Disabling soft particles did not
establish 60 FPS either; all original visual options remain enabled.

Both builds pass, and 98 extracted renderer-state checks cover the retained
change, including no queries in normal web frames, diagnostic error draining,
clean termination and the ten-error bound. Evidence is under ignored
`build-web/performance-query-ab-console.txt`,
`performance-stream-ab-console.txt` and `performance-audit-baseline.txt`;
final build logs are `performance-final-build.log` in both build directories.

Next performance work should separately measure dynamic-geometry upload and
scene-generation cost, add GPU timing where supported, and compare warm live
samples at the rails and representative later maps. A 60 FPS cap supplies a
target, not a guarantee: CPU p95 must fit the 16.67 ms budget and browser frame
delivery must also stay regular. These measurements preserve game timing and
do not justify reducing simulation ticks or skipping visual effects.

At the user's stopping point, the final rebuilt browser was loaded and QuickSave
restored without writing over it. The pre-audit playing position
`(64.99 -1311.67 196.25) 180` was restored. Readbacks confirm the 60 FPS cap,
`g_stopTime 0`, `com_fixedTic 0`, shadows and soft particles enabled, and
WebAudio running (15 sources). The console is hidden. Restoration evidence is
`build-web/performance-restored-console.txt`. Sustained 60 FPS in the busy rail
view remains unfinished; the retained improvement is the verified stopping point.

## 7. Gameplay timing and graphics options

The single-threaded browser loop generates async user commands **after**
`RunEventLoop()` fills SDL's keyboard and mouse poll queues, before advancing
the session. With `com_asyncInput 1`, it previously generated commands before
processing events, adding one rendered frame of delay to movement, attacks,
reload and weapon switches. The native default `com_asyncInput 0` continues
to use synchronous input from the current event queue.
The original integer `USERCMD_MSEC` (16 ms), timescale handling and ten-tick
hitch limit remain unchanged. Rendering at a different frame rate does not
change the simulation step. Physics, weapon definitions and weapon scripts are
unchanged.

Canvas/window focus loss and hiding the page discard queued and held input.
Releasing a mouse button outside the canvas also clears input, since page mouse
events are withheld from SDL. This prevents movement or attack from remaining
held when its release happens in a page control. The embedded browser's
pointer-lock limitation described above still applies.

Open **Graphics options** below the game. It reads current engine settings,
including changes made through the game menu or console. **Apply graphics**
updates dynamic shadows, normal maps, specular highlights, soft particles,
gamma (0.5–3), brightness (0.5–2), frame rate (30/60/Unlocked) and texture
filtering without a renderer restart. Settings use
the engine's archived configuration and existing IDBFS persistence. Restoring
defaults affects only these eight graphics settings. Controls remain disabled
until startup succeeds, and invalid numeric fields apply no changes.

The native bridge accepts only eight setting indices and validates booleans,
ranges and non-finite numbers. Boundary validation disables optimization because
the engine's finite-math compiler flags otherwise elide NaN checks. Graphics
controls cannot set simulation speed, movement or weapon cvars. Texture quality
is available through the stock in-game menu described below. Antialiasing and
resolution are managed by the browser context and are not runtime switches.

**Texture filtering** offers Standard, 2×, 4×, 8× and 16× anisotropic filtering.
Higher levels retain sharper floor and wall textures at oblique viewing angles.
Unsupported levels are disabled using the renderer's actual capability and
maximum. Without the extension, Standard remains available. The panel shows
effective filtering when a saved request exceeds the GPU's limit, and preserves
valid intermediate values made through the native menu or console as a current
custom choice. Restoring graphics defaults requests 8×, bounded by the device's
limit. These changes retune the existing images through the native engine's
filtering update path; no texture assets are replaced.

The October 4 graphics audit passes all six launcher regression groups, 108
timing/input/graphics checks, and 81 real WebGL2 checks for shader compilation,
lighting, alpha tests, reflections, gamma, heat haze and filtering. These are
scoped checks; mask-only campaign haze/background differences and broader
campaign rendering remain unverified. Local GPU evidence is
`build-web/graphics-audit-gpu-report.txt`.
The Release web build passes (`build-web/graphics-audit-build.log`). In the
rebuilt game, applying 16× filtering read back `image_anisotropy 16`; a console
value of 3.5× appeared as a current custom choice and survived Apply. Original
8× filtering, the 60 FPS cap and playing position
`(64.99 -1311.67 196.25) 180` were restored, with simulation running and audio
enabled. Live evidence is `build-web/graphics-audit-live-console.txt`.

`tests/web_gameplay_check.py` extracts actual scheduling, movement/button,
weapon impulse, input clearing and graphics bridge functions. Its 46 checks
cover equal tick counts at 30/60/90/144 render callbacks per second, tick
boundaries, hitch/timescale behavior, opposing movement, jump, attack repeats,
multiple attack bindings, weapon/reload impulse sequences, menu inhibition,
focus clearing and graphics validation. It also checks the integration order
in `Common::Frame`. Compile with `em++ -O3 -ffinite-math-only -sENVIRONMENT=node`
and run with Node; the web workflow runs this harness and the shell regressions.
These checks validate input/timing plumbing, not full playthrough or weapon
balance parity. The bounded native/web simulation comparison below adds direct
movement, selected weapons and save/load evidence. Render-rate scheduling,
physical input, remaining weapons and cinematic timing still require broader comparisons.

Local validation: Windows and Release WebAssembly builds passed. The saved
Mars City hangar loaded with all nine original Steam archives. Each graphics
control was checked against engine cvar output, persisted across a page reload,
and restored to its default. A temporary pistol grant showed weapon selection
and ammunition consumption; the original QuickSave was reloaded afterward.
Full reload-animation/fire-rate parity and physical mouse behavior remain
unverified; the embedded host continues to report pointer-lock `UnknownError`.

### Native/web simulation comparison

`testUsercmd <ticks> <forward> <right> <up> <buttons> [impulse]` is an opt-in
cheat/developer command shared by the Windows and web base-game builds. It
advances the real `gameLocal.RunFrame` with fixed input and prints position,
velocity, view angles, ground/crouch state, health, weapon identity, readiness
and ammunition. Each
invocation accepts at most 300 ticks; zero ticks only samples state. Invalid
integer/range arguments are rejected before advancing. Cinematics, paused game
time and multiplayer are excluded. An impulse is sent once at the start.

This check advances the loaded world and does not generate a valid recording
of ordinary user input. Use an isolated native save/config directory, or reload
the original save afterward in the browser. It does not replace browser input,
frame-pacing or campaign tests. Stock command-demo `consistencyHash` is always
zero in `Game_local.cpp`, so a successful command-demo replay alone cannot prove
simulation parity.

`tests/gameplay_parity.cfg` provides a reproducible Mars City 2 sequence: walking,
strafe collision, jump/landing, crouch/standing, pistol selection, two attack
windows and reload after recovery. Run it from an isolated native `base/`
directory. In the browser, submit the same `devmap`, `wait` and `testUsercmd`
commands through Engine command; omit `condump`/`quit` and restore the original
timing/developer settings and save afterward. Compare the native console dump
with exported browser Console text:

```text
python tests/gameplay_parity_check.py native-console.txt web-console.txt
```

Local validation: Windows and Release WebAssembly builds passed. All 17
checkpoints matched game-time advance, ground/crouch state, health, clip/ammo
and readiness. The maximum position difference was `0.000244` game units;
the comparison allows `0.001` units for position/velocity rounding. Pistol
attack windows consumed five rounds (12 → 9 → 7), and reload restored the clip
to 12. Three invalid argument cases were rejected on both platforms without
changing the initial checkpoint. Fifteen asset-free verifier regressions cover
wrapped console output, rounding, divergent movement/ammo, missing evidence,
interrupted playback, incorrect timing and noclip. These regressions run in CI;
the actual Steam campaign comparison is a local licensed-data check.

`tests/save_weapon_parity.cfg` adds a grounded save/load round trip with a
nonzero camera yaw and selected pistol. Position and ammunition change before
loading the temporary `CodexParityAudit_20261003` save. Shotgun, machinegun,
chaingun and plasma each exercise selection, fire, recovery and reload. Each
platform writes and reads its own save; cross-platform binary save compatibility
is not tested. Compare the logs with:

```text
python tests/gameplay_parity_check.py native-console.txt web-console.txt --scenario save-weapons
```

Local validation: all 24 Windows/web checkpoints matched exactly, including
view angles, weapon identity, position/velocity, health, ammunition and elapsed
game time. Save/load restored the saved yaw, pistol and clip after movement and
firing. All four additional weapons consumed ammunition and completed reload.
The original browser QuickSave and timing/developer settings were restored.
The fixture creates a clearly named temporary test save in the browser; it
does not overwrite QuickSave. Camera pitch, damage/death, late-game saves,
explosive/melee weapons and real input cadence remain unverified.

## 8. In-game options audit and polish

The original licensed main menu remains the in-game interface. The web build
adapts known stock controls during GUI parsing; it does not distribute a copy
of the commercial GUI. Matching requires the stock GUI path, window name and
original cvar binding, so unfamiliar mod controls keep their own behavior.

- **System:** render size and display mode show a muted `Browser` state;
  speakers show `Stereo`, and unsupported EAX shows `Off`. The legacy audio
  backend control, when present, shows `WebAudio`. These display-only controls
  do not accept input or overwrite engine values during Apply.
- **Advanced:** Frame rate offers **30 FPS**, **60 FPS** (default), and
  **Unlocked**, updating immediately without a restart. Unlocked follows the
  browser/display refresh rate. The unsupported multisampling
  row becomes **Soft particles**, with a live On/Off toggle. Shadows, normal
  maps, specular highlights, brightness, volume and gameplay controls continue
  to use their original engine bindings.
- **Texture quality:** Low/Medium/High/Ultra retain the engine's presets but use
  `execMachineSpec nores` to preserve browser render size. Apply uses
  `reloadImages reload` to force quality changes without recreating WebGL or
  restarting audio. The confirmation explains the reload. Texture reload can
  briefly pause the game, especially with large archives.
  The desktop hardware-scan button becomes **Use balanced texture quality**
  (Medium), because browser RAM/VRAM probes do not identify optimal settings.
  Stock GUI revisions with a lone OK button regain the missing Apply action;
  their existing close animation is preserved. Older Apply/Cancel variants
  retain their original action handlers.
- **Preset scope:** the row explicitly says **Texture quality**. Browser texture
  presets retain the player's decals, projectile lights, double vision, muzzle
  flash and sound limits; changing texture quality no longer resets these options.
- **Defaults:** the confirmation explains that controls, gameplay, graphics and
  volume reset. Medium is the browser's default texture preset; display mode,
  custom render dimensions, language and saved games are retained. Current menu
  values refresh without restarting WebGL or WebAudio. Texture changes still use
  the System panel's Apply flow.
- **Keyboard:** Tab and Shift+Tab navigate visible controls, skip off-screen/collapsed
  panels and disabled choices, and stay inside open modal dialogs. Enter
  activates stock buttons; choice widgets keep Left/Right navigation. A cyan
  outline identifies the focused control. Stock menu sliders clamp keyboard steps
  before writing their engine values, including fractional steps at either end.

Desktop behavior is retained, except that the High preset's accidental empty
cvar assignment is corrected to `r_mode 4` (800×600). Browser sound commands
normalize output to stereo/EAX off without invoking blocking desktop dialogs
or restarting WebAudio.

`tests/web_menu_check.py` compiles extracted menu command branches, preset
execution, choice read/write and focus traversal alongside the actual policy.
Its 98 checks cover mod isolation, disabled setting writes, latched Apply,
all quality levels, preserved browser size, the desktop High preset, correct
image reload syntax, audio normalization, focus wrapping, modal boundaries,
slider endpoints, preset scope, browser-safe Restore Defaults and frame-rate
choice/value mappings.
The web workflow runs it without proprietary game assets.

Local validation: Windows and Release WebAssembly builds passed, along with
66 menu checks, 46 gameplay/input/graphics checks and the web shell regressions.
The original Steam GUI showed browser-managed rows and the live soft-particles
toggle. A Medium preset was selected from the loaded hangar's menu; forced
texture reload retained position `(1263.77 -1501 68.25) 180`, render mode `5`,
one OpenGL initialization and the same running WebAudio context. Ultra and soft
particles were restored afterward. Reloading the hangar textures paused the
browser for roughly eight seconds locally. The final build also completed the
stock menu's Use balanced → Apply Changes → Apply flow using Tab/Enter;
render mode remained `5` and WebAudio context `2` remained running. The visible
focus outline and final System labels were verified in the browser.
Demo and custom menu layouts still
need separate visual verification.

The follow-up options audit passed Windows and Release WebAssembly builds,
96 menu checks and the web shell regressions. In the rebuilt Steam-supplied
menu, the Texture quality label and full defaults confirmation were visible;
the confirmation was canceled after inspection. Repeated keyboard steps kept
the brightness cvar within `[0.5, 2.0]`; brightness was restored to `1`.
Restore Defaults behavior is covered by the extracted command harness, including
custom browser dimensions, Medium selection, audio normalization and language.

## 9. Rendering accuracy verification

The stock `environment.vfp` reflection path now interpolates the unnormalized
local surface normal and eye vector, then normalizes and reflects per pixel.
The previous implementation reflected at vertices and interpolated the result,
which could sample a different cube face as the camera moved. Cube-map alpha
now participates in output alpha and alpha testing, as in the stock program.

`colorProcess.vfp` now has a dedicated shader instead of the flat fallback.
It samples the captured screen using both viewport reciprocal and padded
texture scale, then blends toward the target tint using the stock `0.33`
mean-intensity factor and independent RGB fractions. Vertex local parameters
and fragment environment parameters update after binding. The shader is
included in startup, program reload and context-reset paths.

Local WebGL2 pixel checks generated by `tests/render_shader_check.py` passed
81 assertions on the tested browser (80 without the optional anisotropy
extension), including reflection cube-face selection, cube alpha/discard,
current material color with color arrays disabled, normalization-cube diffuse
response, bumpy-reflection transforms, heat-haze variants, color-processing
blend boundaries and padded screen coordinates. The extracted
renderer-state harness passed 94 assertions, including extension fallback and
restoration, effect selection,
parameter updates and mismatched program pairs. These checks use generated
textures, without distributing licensed assets. Run the generator against
`build-web/render-check.html` and visit that page on the local server.

The Release web build passed and restored QuickSave in the Mars City hangar.
The stock `textures/decals/bloodyfilmred` material registered both color-process
programs through `g_testPostProcess` and produced tinted output; the temporary
effect was then removed. This exercises registration and drawing, rather than
proving the campaign's screen-capture context matches native. Player position
remained `(1263.77 -1501 68.25) 180`, and WebAudio context `2` was running with
nine playing sources after the check.

Full accuracy remains unproven. Completion requires evidence across the base
Doom 3 campaign, not just the opening room or synthetic tests:

| Area | Evidence needed before completion |
|------|-----------------------------------|
| Movement, weapons and timing | Native/web comparisons of equivalent input or command-demo sequences, including jump/crouch, collisions, weapon cadence/reload and low/high render rates |
| Materials and lighting | Matched native/web campaign views exercising reflections, shadows, fog, heat haze, alpha materials, screen effects and every stock material program used by the campaign |
| Campaign behavior | Level transitions, cinematics, scripted encounters, objectives, damage/death and save/load across representative late-game maps |
| Audio and input | Audible/spatial sound and captured physical mouse look in a desktop browser, plus focus loss, menus and fallback input |
| Browser polish | Data-loading recovery, persistent saves/settings, responsive controls, stable context recovery, and measured memory/frame behavior |

The current backend still has unported ARB-program fallback and an approximate
glass-warp implementation. Bumpy-reflection basis and model transforms have GPU
coverage, but campaign coverage of that effect and other ambient programs is
still incomplete. Existing tests do not prove the full campaign correct.

### Matched Windows/web scene captures (2026-10-04)

`tests/render_parity.cfg` captures a fixed Mars City Underground view and a
refrigerator view at 640x480 using an isolated native save/config directory.
Use the same licensed Steam assets locally; the fixture includes no game data.
For browser captures, use `webscreenshot 640 480`, omit `condump`/`quit`, and
download each PNG before requesting another. Send unfreeze/teleport separately
from freeze/capture: `wait` counts command-buffer passes and did not reliably
allow a rendered browser frame to update the cached camera. Verify `getviewpos`
before comparing. Restore the user's save and temporary cvars afterward.

The interaction shader now samples the stock normalization cube for diffuse
lighting, instead of mathematically normalizing the interpolated light vector.
The matched elevator capture's RGB mean absolute error fell from 4.006 to 3.889
byte levels. Coordinates, orientation and the fixture's gameplay checkpoints
matched; animated monitor content still differed. The web image remains
brighter in parts of this scene, so this is improvement rather than parity.

The refrigerator model in this fixture uses `textures/sfx/fridgeglass1`, which
is masked cube reflection, **not heat haze**. `g_testPostProcess` also does not
provide a valid native heat-haze oracle: a 2D overlay does not trigger the 3D
framebuffer capture. Real campaign heat-haze comparison remains outstanding.

The reflection shader previously multiplied its cube sample by a disabled
WebGL color attribute (black), hiding the frost reflection. It now uses the
current material color when the array is disabled, matching ARB `vertex.color`,
and uses the vertex color when enabled without applying an extra tint. GPU
checks cover both sources and their alpha tests. The corrected refrigerator
capture restores visible frost. Against native, left-fridge region
`(165,240)-(270,475)` RGB mean absolute error fell from 27.423 to 21.625 byte
levels; pixels whose maximum channel error exceeds 10 fell from 79.64% to
45.33%. The region excludes differing weapon animations. Remaining lighting,
filtering and scene-time differences are not explained by this fix.

`tests/render_image_compare.py` (Pillow required) measures equal-sized PNGs,
records source hashes and optional region, and can save a difference image.
It performs no resizing or alignment and defines no fidelity pass threshold:

```sh
python tests/render_image_compare.py native.png web.png \
  --region 165 240 270 475 --difference difference.png
```

Local evidence is under ignored `build-web/render-parity/` and
`build-windows/render-parity-v3-native/`: before/after PNGs and JSON measurements,
GPU report, and console state. `build-web/reflection-color-build.log` records
the successful Release web build. This evidence is scoped to these scenes.

### Filtering and controlled lighting comparison (2026-10-04)

The web backend now probes `EXT_texture_filter_anisotropic` and reads the GPU's
actual limit. It previously forced the capability off and clamped all presets
to 1x, despite the High/Ultra preset requesting 8x. The existing image upload
and live-filtering code now applies those preset values on supported GPUs.
Unsupported or invalid contexts retain the 1x fallback; capability state resets
and is queried again after context restoration. The tested browser GPU reports
a 16x limit, and a real GPU parameter check accepts the requested 8x value.

`tests/render_lighting_parity.cfg` captures six lighting variants at 1x and a
seventh normal view at 8x: normal, no bump, no specular, neither, no ambient and
no interactions. Both builds use the same map, camera and bounded input replay.
The initial browser fixture idled between map load and replay, allowing the
elevator door to open while it stayed closed in the native captures. The final
browser fixture submits map load, replay and freeze as one command, and the
native fixture likewise omits the initial `wait`. This corrects the comparison
setup rather than introducing a brightness adjustment in the renderer.

The matched 1x static wall region `(0,0)-(120,420)` has RGB mean absolute error
0.678 byte levels; without specular it is 0.369, without bump/specular 0.350,
and without interactions both captures are black. The final normal capture's
full-image mean absolute error is 0.953 at 1x and 1.127 at 8x, with average
channel bias below 0.11 and 0.05 respectively. Animated monitor details and GPU
sampling/rounding still differ; these results establish close agreement for
this controlled view and do not prove all campaign lighting correct.

The Release web build passed (`build-web/anisotropy-build.log`), as did 94
renderer-state checks and 81 WebGL2 checks. Evidence: ignored
`build-windows/render-lighting-v2-native/` and `build-web/render-parity/`
(`lighting-matrix-report.json`, `anisotropy-final-report.json`, matched PNGs,
console logs and the GPU report).

At the user's requested stopping point, the next work remains real 3D campaign
heat haze, additional material-program paths, campaign transitions/encounters,
broader weapons and timing cases, physical captured mouse/spatial audio, and
browser context recovery and memory behavior. The broad accuracy goal remains
unfinished; the current renderer/preset change is the verified stopping point.

The final stopping-point check confirms the launcher offers 30 FPS, 60 FPS and
Unlocked, with 60 FPS selected. The engine readback reports `r_webFrameLimit 60`,
`com_fixedTic 0` and `g_stopTime 0`. QuickSave was reloaded at
`(1263.77 -1501 68.25) 180`, with HUD and weapon display enabled and diagnostic
ambient skipping disabled. All 97 gameplay timing/input/graphics checks, 98
in-game menu checks and the launcher regression groups pass. The new
`tests/render_heat_parity.cfg` has native captures only; matched browser
heat-haze validation remains unfinished and is not a parity claim.

### Campaign heat-haze diagnostics and capture preview (2026-10-04)

`tests/render_heat_parity.cfg` now targets two real Mars City Underground
surfaces: `textures/glass/glass2` on `func_static_53006` (plain heat haze), and
`textures/glass/breakyglass3` on `func_fracture_2` (vertex-masked heat haze).
Each view is captured with programmed ambient stages enabled and disabled.
One bounded simulation tick after each teleport updates the cached render
view; `wait` alone did not reliably do so. The fixture sets `com_wipeSeconds 0`
to exclude the wall-clock loading-screen fade from material comparisons.
The reported views are `(-3200 -2884 269.5) 0` and `(-1908 -304 274.5) 0` in
both builds. Noclip is used only to position these renderer diagnostics.

The launcher now offers **View screenshot** after a successful capture, using
the same engine PNG as the download link. Replacing a capture updates both
before releasing the previous object URL; a failed capture preserves the last
successful preview. This also permits inspection when an embedded host does
not save a download. Failed mouse capture now waits for an explicit canvas or
Focus game click instead of accepting repeated background SDL grab requests.
Menu mouse status and right-drag fallback continue to follow gameplay state.

Local evidence is in ignored `build-windows/render-heat-v4-native/` and
`build-web/render-parity/heat-campaign-report.json`, with paired captures and
`heat-web-console.txt`. The browser captures are screenshots of the PNG preview
at its natural 640x480 size, **encoded as JPEG by the browser tool**. They were
not resized or registered. This limits pixel precision and does not replace
a raw PNG parity check. In the selected plain-glass region, native/web on/off
mean absolute changes are 2.338/2.899 byte levels; for the vertex-masked region
they are 0.501/0.857. The respective on/off-delta differences are 2.001 and
0.805. Refraction is visible and measurable in both builds, but exact agreement
remains unproven. Animated actors are also not a matched timing oracle here.

The launcher regression groups and Release build pass for the preview and
capture-retry changes (`build-web/heat-input-polish-build.log`).
In the rebuilt browser, one explicit Focus game attempt produced one host
capture error; subsequent console, screenshot and preview interactions left
that count at one. The preview was verified on restored QuickSave. Readbacks
confirm `com_wipeSeconds 1`, `com_fixedTic 0`, `g_stopTime 0`, `developer 0`,
`ui_showGun 1`, `r_skipNewAmbient 0` and `r_webFrameLimit 60` at the original
hangar position. Evidence: `heat-restored-console.txt` in the capture directory.
The following checkpoint extends these diagnostics; full accuracy remains
unfinished.

### Raw PNG export and stopping checkpoint (2026-10-04)

The screenshot preview now offers **Copy image** when PNG clipboard writes are
supported. It copies the captured engine PNG without canvas recompression.
Unavailable clipboard access leaves the preview and Download PNG link usable;
a pending copy cannot overlap another copy or replace a newer capture's status.
All six launcher regression groups pass, including unsupported clipboard,
permission rejection, retry and replacement during a pending copy. Live copying
also succeeded in the embedded browser, where downloads had not saved a file.
Native and web builds pass (`render-state-build.log` in each build directory).

`tests/retail_material_inventory.py` reads the user's local PK4 archives without
extracting game assets. It reports 42 materials naming six stock programs and
11 such materials referenced by compiled map geometry. This inventory excludes
dynamic models, skins and engine-selected programs; it is not complete campaign
coverage. Run it against the original Doom 3 `base` directory:

```sh
python tests/retail_material_inventory.py /path/to/Doom3/base \
  --output build-web/retail-material-inventory.json
```

The heat fixture additionally exercises mask-only haze on `textures/sfx/vp1`,
`func_static_53020`, at `(-1724 -2341 247.5) 0`. Raw PNG on/off comparisons replace
the earlier JPEG preview measurements: selected plain and vertex-masked regions
have native/web effect-delta mean absolute errors of 0.343 and 0.029 byte levels.
The mask-only region differs by 0.889, and its background also differs with heat
disabled. Shadow, fog, ambient and soft-particle controls have not isolated the
cause. These regional measurements establish no general fidelity threshold.
Evidence is in ignored `build-web/render-parity/raw-heat-campaign-report.json`
and `heat-mask-background-report.json`, with the raw PNG pairs.

Optional `getviewpos state` now prints game/render time, frame number and random
seed without changing state. At the three fixture views, native and browser
both report times 176/192/208 ms and frames 11/12/13. Their random seeds differ:
native -471451794/-2008849762/-787973119 versus browser
1286920474/-392712374/630802013. Matching clocks alone therefore does not prove
equivalent simulation state. The next investigation should explain this
divergence before attributing the remaining background difference to lighting.
Evidence: `build-windows/render-heat-v7-native/base/render-heat-console.txt`
and `build-web/render-parity/heat-state-web-console.txt`.

At the requested stopping point, frame-rate choices remain **30 FPS**, **60 FPS**
and **Unlocked**, with 60 FPS selected. Unlocked follows browser/display refresh;
changing the render limit does not change the fixed game simulation tick.
QuickSave was restored at `(1263.77 -1501 68.25) 180`; readbacks confirm
`com_fixedTic 0`, `g_stopTime 0`, `com_wipeSeconds 1`, fog and programmed ambient
rendering enabled, soft particles/HUD/weapon display enabled, and developer mode
off. The console is hidden and normal play is running. Restoration evidence is
`build-web/render-parity/stopping-checkpoint-console.txt`.
Remaining work includes the simulation-state divergence, mask-only haze and
background lighting, other campaign materials, broader gameplay/campaign cases,
captured physical mouse input and browser recovery/performance coverage.

### Random-state investigation (2026-10-05)

The three recorded heat-fixture browser seeds are exactly **four random draws
ahead** of their native counterparts in the stock 32-bit `idRandom` sequence.
The offset stays constant across these views; this narrows the investigation
but does not establish the point or cause of divergence. A fresh isolated
native run with OpenAL initialized (`s_noSound 0`, output attenuated with
`s_volume_dB -60`) reproduces all three earlier native seeds. Disabling native
audio therefore does not explain this particular mismatch. The new run's
console and PNGs are under ignored `build-windows/render-heat-sound-native`.

`tests/render_state_parity_check.py` now compares recorded game/render clocks,
frame numbers and random seeds before pixel analysis. It rejects missing,
truncated or unequal state records and diagnoses random draw offsets within
4096 draws in either direction. It does not accept a seed mismatch merely
because the offset is constant. Seven regression cases include native console
wrapping inside labels and seed digits. The checker passes the old/native-audio
pair and rejects the current native/browser pair at checkpoint 1:

```sh
python tests/render_state_parity_check.py native-console.txt web-console.txt
# State comparison failed: render checkpoint 1 random_seed:
# -471451794 / 1286920474 (web 4 random draws ahead)
```

Matching these four fields alone would still not prove matching entity state,
camera, settings or campaign fidelity. The next investigation must locate the
first differing draw during map setup or early simulation before attributing
the remaining mask-only background difference to the renderer.

The subsequent optional `g_debugRandomSeed 1` trace narrows this further:
native and browser agree through map spawning and startup events, with seeds
472315226 after spawning and 2063731475 after startup events. The first
divergence occurs inside tick 1 entity thinking, where the browser advances
one extra draw. That offset grows to two, three and four after thinking in
ticks 2, 3 and 4, then stays four through the captured views. The initial
2505-record comparison is preserved in ignored
`build-windows/random-trace-native/full-console.txt` and
`build-web/random-trace-console.txt`. The trace does not reset or advance the
generator, and is disabled by default. To avoid overflowing the browser's
bounded console, detailed output is restricted to spawns and early entity
updates that change the seed; entity names accompany the early updates.

The checker also accepts `--trace` to identify the first unequal trace
checkpoint, checking phase, entity/map index and frame before seed values.
Nine regression cases cover both forms of evidence. For long native runs,
use the full engine log: the in-game `condump` history can lose early records.

The sparse rerun produces 596 trace records on each platform. Their first
unequal checkpoint is `think_entity`, entity 1954, frame 1:
`monster_zsec_machinegun_7` (`idAI`). Native's seed after its update is
697712057; browser's is 741003814, exactly one draw ahead. The preceding
updates of player1, monster_zombie_jumpsuit_2 and monster_zsec_machinegun_9
match. Evidence is in ignored
`build-windows/random-trace-native/sparse-console.txt` and
`build-web/random-sparse-console.txt`. This identifies the first divergent
entity update, not the cause; its animation/script/head-alignment paths still
need branch-level comparison. The final native and Release web trace builds
pass (`random-sparse-build.log` in each build directory).

### Vector-angle precision correction (2026-10-05)

Branch tracing with optional `ai_debugRandomEntity 1954` finds the extra draw
in eye/head alignment. Before correction, browser orientation yaw is 45 degrees
and its focus direction is 45.0000076; native obtains 44.9999962 for both. The
browser therefore enters the exact eye-angle-change branch in each of the
first four ticks, while native does not. This changes random scheduling even
though the visible angular difference is tiny.

The cause is C++ `<math.h>` overload selection: the current MSVC native
toolchain selects double `atan2` for float arguments, whereas the Emscripten
headers select the float overload. `idVec3` yaw, pitch, angle and polar
conversions now explicitly pass doubles to `atan2`, retaining double radians
until conversion to degrees. The native precision and AI comparison rules
are preserved; no tolerance, extra random draw or forced seed is introduced.

`tests/web_angle_check.py` extracts the real `ToYaw` code and tests ten measured
native Windows fixtures, including cardinal directions, all four quadrants,
zero and the campaign's equal-coordinate focus vector. Native and optimized
Emscripten runs pass; the old implicit-overload implementation fails the same
test. CI runs this check alongside the existing timing/input checks.

Fresh native and browser campaign runs now match all **596 random trace
checkpoints**, all three recorded game/render clock/frame/seed states, and
all 40 selected AI phase records plus four yaw and four head-alignment records.
Evidence: ignored `build-windows/angle-fixed-native/full-console.txt` and
`build-web/angle-fixed-console.txt`. Native and Release web builds pass
(`angle-precision-build.log`). This closes the recorded seed divergence for
this fixture; it does not establish complete campaign or rendering parity.

Fresh 640×480 browser engine PNGs, exported through Copy image without JPEG
conversion, also resolve the previously unexplained mask-only haze comparison.
At the fixture's matching camera/time/frame/seed, the `(240,130)-(400,350)`
region has on/off mean absolute errors of 0.000672/0.000038 byte levels and an
effect-delta error of 0.000634, versus the earlier 0.889 effect-delta error.
The larger background region `(190,150)-(430,465)` now differs by 0.0143 byte
levels. Original PNGs and metrics are in ignored
`build-web/render-parity/angle-fixed-mask-{on,off}.png` and
`angle-fixed-mask-report.json`; camera/state capture evidence is in
`build-web/angle-fixed-capture-console.txt`. The shader was not changed for
this correction. These measurements apply to the captured fixture and remain
evidence rather than a general fidelity threshold.

### Matrix-angle precision correction (2026-10-05)

The same overload audit finds early float rounding in `idMat3::ToAngles`:
`asin(sp)` is rounded before assignment to its double `theta`, and float
`atan2` results are rounded before degree conversion. Identical inputs produce
browser pitch/roll of 30 degrees where native reports 29.9999981, and browser
yaw of 45 where native reports 44.9999962. Near-vertical pitch also differs.
The conversion now explicitly passes doubles to `asin` and all three `atan2`
calls. Its existing sin clamp and gimbal-lock threshold are preserved.

The extracted-code test now covers **20 vector/matrix-angle fixtures**, with
native measurements for identity, yaw quadrants, pitch and roll, near gimbal
lock and drift beyond the sin bounds. Both native and optimized Emscripten
pass; reverting just the matrix calls to implicit overloads makes it fail.
Both native and Release web engine builds pass (`matrix-precision-build.log`
in their respective build directories). Fresh native and browser gameplay
runs also match all 17 movement, jump, crouch, pistol-fire and reload
checkpoints, with position/velocity tolerance of 0.001 units and no collision
bypass. Evidence is in ignored
`build-windows/matrix-gameplay-native/full-console.txt` and
`build-web/matrix-gameplay-console.txt`. These fixtures do not establish
complete campaign or rendering parity.

A subsequent matrix-build campaign replay also preserves all 596 random
trace checkpoints and all three recorded render clock/frame/seed states.
Evidence: ignored `build-windows/matrix-heat-native/full-console.txt` and
`build-web/matrix-heat-console.txt`.

### Field-of-view precision correction (2026-10-05)

The remaining camera projection calculation had the same implicit-overload
problem in its three `tan` and three `atan2` calls. At a 60-degree base FOV,
the original browser calculation returns 46.8264465 degrees vertically while
native MSVC returns 46.8264503. Explicit double arguments now preserve native
transcendental precision before the existing float assignments. The aspect
ratio choices, portrait-screen horizontal minimum, and unavailable-screen
fallback retain their original behavior.

`tests/web_fov_check.py` extracts the actual `idGameLocal::CalcFov` method and
checks 72 native values saved in asset-free `tests/fov_native.txt`. Coverage
includes base FOVs of 60/90/110, auto/4:3/16:9/16:10, standard/wide/portrait
dimensions and a zero-sized screen. Native and optimized Emscripten runs
pass exactly; the original implicit-overload browser code fails. CI runs
this check. These fixtures verify projection calculations, not complete
campaign image parity.

Both full engine builds pass (`fov-precision-build.log` in each build
directory). A fresh native/browser campaign replay retains all 596 random
trace checkpoints and all three recorded clock/frame/seed states. Evidence:
ignored `build-windows/fov-heat-native/full-console.txt` and
`build-web/fov-heat-console.txt`.

### Explosive-weapon trajectory audit (2026-10-05, before shape correction)

`testUsercmd` now also reports read-only snapshots of all player-owned
projectiles: entity index/definition, hidden state, physical position and
velocity, plus checkpoint frame/time/count. It does not advance time beyond
the requested input ticks, create projectiles or modify their physics.
Normal gameplay does not call this developer-only command.

`tests/explosive_weapon_parity.cfg` exercises grenade hold/release, flight,
bounce, detonation and removal; rocket and charged BFG fire, recovery/reload
and removal; and chainsaw selection/attack/recovery input. Both full builds
pass (`projectile-replay-build.log`). The fixture's 22 native checkpoints
exercise real projectile motion and ammunition consumption. Grenade splash
damage leaves native health at 63 and moves the player from
`(-224,-2236,16.249998)` to `(-226.470337,-2254.741943,16.250038)`.

The browser run before correction **fails parity**: grenade splash leaves
health at 60 and position `(-228.025497,-2254.683838,16.250196)`. The grenade
rests at different positions before exploding, so later rocket/BFG results
cannot be treated as isolated weapon mismatches. Evidence is in ignored
`build-windows/explosive-v2-native/full-console.txt` and
`build-web/explosive-console.txt`.

A denser follow-up records 265 projectile checkpoints. The first recorded
exact difference is at frame 182 (2912 ms): matching position but native
vertical velocity 407.628021 versus browser 407.628113. By frame 186, horizontal
velocity differs by 0.001419 units. This locates the earliest observed
divergence visible in these projectile snapshots after a collision. A later
arithmetic trace locates an earlier launch-state discrepancy, described below.
Evidence: ignored
`build-windows/grenade-trace-native/full-console.txt` and
`build-web/grenade-trace-console.txt`.

`tests/projectile_parity_check.py` rejects divergent frame/time/count,
entity identity, position/velocity and incomplete flight/removal evidence,
alongside exact weapon/ammo/health/tick comparisons. Six asset-free projectile
verifier regressions and three additional explosive-weapon coverage checks
pass and run in CI. The real licensed-data fixture still fails at rocket flight
after the grenade correction. This audit does not prove BFG targeting,
chainsaw hit damage, death behavior or the complete campaign.

### Collision-shape precision correction (2026-10-05)

Optional `rb_debugEntityDef`, `rb_debugStartFrame` and `rb_debugEndFrame`
enable read-only state and collision arithmetic tracing. Empty entity definition
disables it by default. The 742-record first run finds angular momentum already
different before the grenade's first integration at frame 160, rather than
originating at the later bounce. Expanded launch tracing shows identical spin
velocity but different off-diagonal inertia tensor values. Evidence: ignored
`build-windows/rigid-launch-native/full-console.txt` and
`build-web/rigid-launch-console.txt`. The original native trajectory is unchanged
with diagnostics enabled. `tests/rigid_body_trace_check.py` compares exact
ordered records; four verifier regressions cover wrapping, exponents, missing
evidence and identity/value/order/count differences.

The grenade uses a generated six-sided cylinder. `SetupCylinder` and
`SetupCone` previously passed float angles to global `sin`/`cos`: native MSVC
uses double results through vertex scaling, while Emscripten rounds them early
using float overloads. For example, cylinder vertex 2's x coordinate becomes
-1.50000024 on web instead of native -1.50000012. This changes mass properties,
initial angular momentum and later collision behavior. Both shape generators
now explicitly pass doubles, preserving native rounding at the vertex assignment.
No inertia values, random seeds or physical tolerances are forced to agree.

`tests/web_trace_shape_check.py` extracts the real vertex-generation prefixes
and compares 66 cylinder/cone vertices with measured original native fixtures
in asset-free `tests/trace_shape_native.txt`. Synthetic symmetric and shifted,
nonuniform bounds cover 5/6/10-sided shapes. Native and optimized Emscripten
pass exactly; the original implicit-overload code fails. CI runs this check.
Polygon/mass/collision behavior is tested separately in the actual engine.

Both full builds pass (`trace-shape-precision-build.log`). Fresh native and
browser explosive-weapon runs now match **all seven grenade snapshots** and
**all 747 recorded rigid-body arithmetic values**. Splash damage leaves health
at 63 on both, with matching knockback and final grenade position. Evidence:
ignored `build-windows/shape-fixed-explosive-native/full-console.txt` and
`build-web/shape-fixed-explosive-console.txt`.

Fresh post-fix movement/pistol runs match all 17 checkpoints. The earlier
campaign fixture also retains all 596 random-state checkpoints and three render
clock/frame/seed states. Logs are in ignored `shape-fixed-gameplay-native` and
`shape-fixed-heat-native` directories under `build-windows`, with corresponding
`shape-fixed-{gameplay,heat}-console.txt` browser logs under `build-web`.
All 44 Python verifier/launcher regressions and six browser shell regression
groups pass.

The longer fixture remains incomplete: at `rocket_fire`, frame 672, projectile
origin differs by 0.063454 units and launch velocity differs. The cause of this
remaining spread/flight mismatch is not yet fully established. It must remain a failing
comparison rather than being hidden with a wider tolerance. BFG targeting,
melee hits, death and full campaign behavior remain unverified.

A subsequent seed audit locates the first extra browser random draw at frame
148, during `env_gibs_torso_1` (entity 245, `idAFEntity_Generic`) thinking.
Player and AI seed changes before that entity match native. An explicit native
generic-SIMD control also matches the original native trace. This narrows the
remaining investigation to the articulated-body entity; it does not establish
the responsible physics or sound branch. Optional `g_debugRandomEntityFrame`
and `ai_debugRandomFrame` enable selected-frame tracing and default to -1.
Evidence is in ignored `build-windows/entity148-native/full-console.txt`,
`build-windows/entity148-generic-native/full-console.txt` and
`build-web/entity148-console.txt`. The explosive fixture now records clock and
seed state after every checkpoint and freezes at the end for comparison.

### Rotational collision precision correction (2026-10-05)

Optional `af_debugEntity`/`af_debugEndFrame` capture articulated-body origin,
velocity and orientation. `af_debugRotationEntity`/`af_debugRotationFrame`
capture selected-frame integration rotation inputs and matrices. Entity selectors
default to -1, disabling the read-only diagnostics.

The torso begins with identical state and matches native for nine frames. The
first recorded difference is in body 1's post-collision orientation at frame 10.
Integration rotation inputs and matrices match; isolated native/web matrix
multiplication, normalization and inverse-square-root seed tables also match.
By frame 148, browser collision speed is 94.3485413, versus native 7.15470839.
Only the browser crosses the 80-unit bounce-sound threshold, drawing a sound
diversity value from the shared game random generator. Evidence: ignored
`build-windows/af-state-native/full-console.txt`,
`build-windows/af-rotation-native/full-console.txt`,
`build-web/af-state-console.txt`, `build-web/af-first10-console.txt` and
`build-web/af-rotation-console.txt`.

Rotational collision handling now explicitly passes doubles to its initial
`tan` and both collision-fraction `atan` calls, preserving the native rounding
through fraction scaling and division. `tests/web_collision_fraction_check.py`
extracts all three actual formulas and checks 66 synthetic cases against
original MSVC measurements in `tests/collision_fraction_native.txt`.
Native and optimized web pass exactly; original web arithmetic fails (for
example, fraction 0.75 instead of native 0.74999994). Native results are
unchanged with the correction. CI runs the asset-free check.

Both full engine builds pass. The corrected browser matches all 241 early
articulated-body records and 64 random trace records, eliminating the extra
frame-148 sound draw. Evidence: ignored `build-web/af-collision-fixed-console.txt`.
Native control runs preserve all 22 original clock/frame/seed checkpoints and
weapon/projectile comparisons. All 44 Python regressions pass.

The complete explosive replay still fails: another seed mismatch appears
between frame 171 and frame 471, and rocket launch origin differs by 0.08931
units. All 22 player/weapon/ammo/health/timing checkpoints pass, which does not
prove projectile or full scene fidelity. Evidence: ignored
`build-windows/collision-fixed-native/full-console.txt` and
`build-web/collision-fixed-explosive-console.txt`. No random draws are forced or
skipped, and comparison tolerances remain unchanged.

A bounded follow-up identifies the next seed difference precisely: frame 214
matches through `think_complete`, then native queued events consume one draw
that web does not. The responsible event and scheduling difference remain
unresolved. Evidence: ignored
`build-windows/collision-next-seed-native/full-console.txt` and
`build-web/collision-next-seed-console.txt`. This is the next fidelity target.

### Speaker script and browser sound-clock audit (2026-10-05)

Optional `g_debugEventStartFrame`/`g_debugEventEndFrame` trace queued event
identity, due time and seeds before/after callbacks. Both default to -1.
`g_debugScriptThread` selects a named script thread for execution/wait tracing
and defaults to empty. These diagnostics never schedule events or draw random
values. Event traces read object identity before callbacks, since callbacks can
delete their objects.

The frame-214 native draw comes from
`map_marscity2::video_request_speaker`. Its stock script plays a sound, waits
for the returned duration, then waits one second. Native reports 2.39500022
seconds (2395 ms) at frame 1, queues a callback due at 2411 ms, waits one second
at frame 151 and plays again at frame 214. Web instead reports zero seconds at
frame 1 and leaves `waitingUntil` equal to the current time (16 ms), so no later
callback is queued. Both report the same 52819 samples for the speaker sound.
Evidence: ignored `build-windows/event214-native/full-console.txt`,
`build-windows/event-wide-native/full-console.txt`,
`build-windows/thread-wait-native/full-console.txt` and corresponding
`build-web/{event214,event-wide,thread-wait}-console.txt` logs.

Existing `s_showStartSound` diagnostics identify the zero result as duplicate
suppression: the browser's spawn sound and subsequent script sound share a
stale cached audio timestamp during synchronous map initialization. Evidence:
ignored `build-web/sound-start-console.txt`. The single-thread Emscripten sound
query now calculates the current wall-clock sample timestamp using the same
double conversion, eight-sample alignment and overflow mask as
`AsyncUpdateWrite`, without mixing audio recursively. Native and browser
pthread builds retain their existing async clock query. Both full builds pass.
The corrected browser matches every recorded speaker wait and execution state,
including frames 1, 151, 214, 364 and 427, and all six recorded clock/frame/seed
checkpoints through frame 471. Evidence: ignored
`build-web/sound-clock-fixed-console.txt`, compared with
`build-windows/thread-wait-native/full-console.txt`. All 44 Python regressions
and six browser shell groups pass. The complete explosive replay now passes all
22 player/weapon/ammo/health, projectile, and game/render clock/frame/seed
checkpoints with the existing 0.001-unit comparison tolerance. Evidence: ignored
`build-web/sound-clock-full-console.txt`, compared with
`build-windows/collision-fixed-native/full-console.txt`. This supersedes the
rocket and frame-214 failures recorded above. These fixtures do not establish
full campaign fidelity, BFG targeting, melee hit/death behavior, or sustained
60 FPS; those still require separate verification.

### Chainsaw hit and target death audit (2026-10-05)

`testEntityState <name>` is a cheat-only, single-player, read-only snapshot of
named entity presence, health, damageability, origin, velocity and game clock.
It does not advance time, change targets or consume random values. Missing
entities are reported explicitly. `tests/melee_hit_parity.cfg` exercises a
stock maintenance zombie with actual chainsaw attacks, followed by recovery
and ragdoll settling. `notarget` isolates weapon damage; enemy pursuit and
attacks are outside this fixture's scope. No licensed assets are included.

The initial comparison failed: player timing matched but the browser ragdoll
moved differently and received an extra hit. Random traces located the first
seed difference at frame 32, before any damage. Browser `ui_showGun` was 0 from
the preceding scene fixture; native was 1. View-model chainsaw smoke consumes
the game random stream only when visible. The fixture now explicitly sets
`ui_showGun 1` and `g_showHud 1` on both platforms, instead of depending on saved
settings. No engine random calls or damage rules were changed to hide the
failed comparison.

With matching settings, all six player/weapon/timing checkpoints, all five
target damage/death and ragdoll snapshots, and all five clock/frame/seed
checkpoints pass. Every serialized target value also matches exactly, without
the usual 0.001-unit tolerance. The zombie starts at 50 health, reaches zero
after the first attack window, and settles at -100 after subsequent hits.
Evidence: ignored `build-windows/melee-hit-native/full-console.txt` and
`build-web/melee-matched-settings-console.txt`. The negative comparison remains
in `build-web/melee-hit-console.txt`; bounded follow-up traces are in
`build-windows/melee-trace-native/full-console.txt` and
`build-web/melee-trace-console.txt`.

Both full builds pass. All 48 Python regressions pass, including four verifier
checks that reject missing target records, unchanged health, mismatched damage
and ragdoll drift. Fresh browser checks after the sound-clock correction also
preserve 17 movement checkpoints, 596 scene random-state records and three
scene clock/frame checkpoints against their native baselines. Evidence:
ignored `build-web/sound-clock-{movement,heat}-console.txt` and
`build-windows/shape-fixed-{gameplay,heat}-native/full-console.txt`.
BFG enemy targeting, player death, full combat encounters, campaign coverage,
physical pointer capture and sustained 60 FPS remain unverified.

### Charged BFG damage and occlusion audit (2026-10-05)

`tests/bfg_damage_parity.cfg` exercises a charged stock BFG shot in a disposable
Mars City 2 scene, with two exposed stock maintenance zombies and a third
behind the railing. Actual physical collisions, stock damage definitions,
player splash damage, gib/removal events and game random calls remain enabled.
`notarget` isolates damage from enemy pursuit. Gun display settings are explicit
on both platforms, as in the chainsaw fixture. No licensed assets are included.

Initial target placements failed to exercise the intended coverage: the shot
hit the railing without damaging targets, and a subsequent lateral placement
left the second zombie outside the walkable platform. Those runs are not treated
as successful damage/targeting evidence. The accepted setup puts both exposed
zombies on the platform while retaining the blocked control.

Native and web now match all seven player/weapon/ammo/timing checkpoints, all
18 target snapshots, and all six recorded game/render clock/frame/seed
checkpoints. Every serialized target value also matches exactly with zero
comparison tolerance. Exposed target health reaches -750 and -532; both are
removed by the final checkpoint. The blocked target remains at 50 health.
Player splash damage reduces health from 100 to 40 identically. Evidence:
ignored `build-windows/bfg-damage-native/full-console.txt` and
`build-web/bfg-damage-console.txt`. Earlier inadequate runs remain in the
`bfg-target-native`, `bfg-visible-native`, `bfg-multi-native` and corresponding
browser log artifacts for investigation.

`entity_parity_check.py --scenario bfg-damage` validates target presence,
removal timing, initial health, exposed-target death, blocked-target health,
and target physics/clock parity. Missing entities have explicit presence
records without invented health or position. Three new verifier tests reject
blocked-target damage, unchanged exposed-target health and premature removal,
and check missing-entity parsing. All 51 Python regressions pass. The existing
chainsaw comparison still passes after adding removal support.

This fixture establishes close-impact BFG direct/splash damage and the blocked
control's preservation. It does not establish long-flight beam acquisition,
periodic beam damage, moving-target tracking or all occlusion geometries.
Those remain fidelity targets alongside player death, full combat encounters,
campaign coverage, physical pointer capture and sustained 60 FPS.

### Periodic BFG beam and cleanup audit (2026-10-05)

`tests/bfg_beam_parity.cfg` retains the stock Mars City 2 map and door timing,
advances 100 additional settling ticks before charging, and positions a stock
maintenance zombie beside the flight path. Enemy pursuit is disabled with
`notarget`; physics, weapon scripts, periodic damage and random calls are not
bypassed. Rejected exploratory positions either collided immediately or lacked
a supporting floor; those do not count as beam coverage. The accepted fixture
contains no exploratory script calls or forced door commands.

Both platforms observe target health 50 before periodic damage, then 40 and 30
at two pre-impact snapshots while the BFG is still travelling at 350 units/sec.
The second snapshot also records the target's pain-driven movement. Impact
reduces health to -370; the ragdoll settles, and both target and projectile are
removed by frame 828 (13248 ms), beyond the stock seven-second projectile removal
delay. All 12 player/weapon/timing checkpoints, 12 projectile snapshots, 10
target snapshots and 10 clock/frame/seed checkpoints match. Every serialized
target value also matches with zero tolerance. Evidence: ignored
`build-windows/bfg-periodic-cleanup-native/full-console.txt` and
`build-web/bfg-periodic-cleanup-console.txt`.

The verifier requires two nonfatal pulses before impact, continued actual
projectile flight at both damage snapshots, impact, weapon recovery, settled
ragdoll motion and final target/projectile removal. New negative tests reject
missing second pulses, early impact, changed pulse timing, absent cleanup and
stopped projectiles even when both supplied logs agree. All 54 Python
regressions and six browser shell groups pass. Both full builds pass.

`testTrace <solid|shot> <start x y z> <end x y z>` is a cheat-only, single-player,
read-only collision probe using the engine's point trace and excluding the
local player. It reports fraction, contact point/normal and entity identity;
coordinates must be finite and within +/-32768. A point trace does not prove
clearance for a projectile's full volume. Six native/browser floor, wall,
door and clear-path probes match exactly, including a zero normal on a miss.
Three invalid-coordinate cases and invalid argument count return the same
errors on both platforms. Frozen game/render clock, frame and random seed remain
unchanged before and after the probes. Evidence: ignored
`build-windows/beam-probe-full-native/full-console.txt` and
`build-web/beam-probe-full-console.txt`.

This extends the preceding close-impact audit to single-target beam acquisition,
two periodic pulses, pain-driven target movement and cleanup. Multi-target beam
scheduling, acquisition/removal edge cases, changing occlusion and real combat
pursuit remain unverified. Player death, broad campaign/material coverage,
physical pointer capture and sustained 60 FPS still require evidence.

Browser replay cleanup must also reset `in_nograb 0`; loading a save alone does
not reset this non-archived engine test setting. The current restore confirms
`in_nograb 0`, `com_fixedTic 0`, `g_stopTime 0`, a 60 FPS cap and a running
WebAudio context. Focus game still reports mouse capture unavailable in the
in-app browser, so successful physical capture remains unproven after correcting
the test setting. The launcher presents its existing right-button fallback.
Evidence: ignored `build-web/beam-restored-console.txt` and
`C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/beam-audit-restored.jpg`.

### Live mouse recovery and frame pacing audit (2026-10-05)

The rebuilt launcher was tested with all nine original Steam game archives and
the user's existing QuickSave at the Mars City security checkpoint. Readback
confirmed `in_nograb 0`, `com_fixedTic 0`, `g_stopTime 0`, the 60 FPS cap,
an 820 x 615 framebuffer, and a running WebAudio context with 16 playing sources.
No save was overwritten.

A `webperf 600` sample with a fixed camera and browser size averaged **59.4 FPS**.
Mean CPU work was 4.21 ms per frame, with a 6.15 ms p95: 0.57 ms input/audio,
3.64 ms game/render and 2.64 ms draw. The renderer averaged 410.9 draws and zero
new GPU buffers per frame. No browser automation ran during the sample. Evidence:
ignored `build-web/mouse-recovery-performance-console.txt`.
This establishes near-60 FPS for this stationary scene only; moving views,
combat, heavier scenes, GPU frame time and campaign-wide sustained performance
remain unverified. The selected cap alone is not a performance result.

Focus game still encounters the in-app browser's root-document pointer-lock
rejection. The launcher now displays **Try another browser** for that specific
error, while keeping right-button drag-to-look available. Its game-address field
and **Copy game link** button were checked live: the visible status reported
“Link copied. Paste it into your browser.” The help explains that another browser
requires choosing the game archives again and has separate saves. It does not
promise that changing browsers will enable capture. Successful physical pointer
capture remains unverified.

Seven browser regression groups cover this recovery, including unavailable and
rejected clipboard access, duplicate-copy prevention, and hiding the help after
successful capture or when the game releases the mouse. All 54 Python tests pass;
the full web build passes. Visual evidence:
`C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/mouse-recovery-restored.jpg`.

### Player splash death and ragdoll audit (2026-10-05)

`tests/player_death_parity.cfg` uses the stock Mars City Underground map,
rocket launcher, ammunition and damage rules. Three rockets are fired at a fixed
wall, returning the living player to the same firing position between shots.
There is no health assignment, forced death, corpse teleport or physics override.
The replay runs in a disposable native save directory and never overwrites the
user's QuickSave. Browser cleanup reloads that save with ordinary simulation,
input and audio settings restored.

All **nine player checkpoints match exactly at the serialized precision**,
including position, velocity, view, health, weapon identity, ammo, clip and
readiness. Health progresses 100 -> 59 -> 18 -> -23. The death checkpoints show
the weapon released (`object`, zero clip, ammo -1, not ready), ragdoll motion at
frames 383 and 473, and zero velocity at frame 773. All nine projectile snapshots
also match exactly, including three real launches, impacts and final cleanup.
All nine recorded game/render clocks, frame numbers and random seeds match.
This samples the death sequence at fixed checkpoints; it does not establish the
exact intervening death-event frame or compare death rendering pixel by pixel.

Evidence: ignored `build-windows/player-death-clean-native/full-console.txt`
and `build-web/player-death-clean-console.txt`. Earlier rejected probes either
left the player alive after the lift door opened or teleported the dead body;
neither is used as accepted death coverage. The clean fixture aims at a fixed
wall and allows the dead body to fall and settle without repositioning it.

The gameplay and projectile verifiers accept `--scenario player-death`.
Five new asset-free regression tests reject incomplete phases, absent stock
splash damage, changed timing, retained weapons, missing ragdoll motion,
unfinished settling, missing launches/impacts/cleanup and platform view drift.
All **59 Python tests pass**. CI includes the new tests and fixture path filters.
The engine implementation did not change during this audit.

This verifies one genuine self-inflicted player death, weapon release, ragdoll
settling and projectile cleanup. Enemy-caused death, restart/load UI after death, interrupted
death animations, broad campaign coverage and graphics fidelity remain open.

### Death-screen keyboard recovery audit (2026-10-05)

The genuine three-rocket death replay was allowed to continue with
`com_fixedTic 0` and `g_stopTime 0`. The normal session reached the stock
Restart / Load / Main Menu screen. Tab followed by Enter activated Restart,
which loaded the map's autosave and returned to a living player with 100 health.
This verifies the existing browser restart action through real keyboard input;
it does not establish native/browser autosave state parity.

The restart GUI was outside the browser's main-menu keyboard policy, so it had
no visible focus outline. `Web_IsKeyboardMenu` now includes the licensed stock
`guis/restart.gui` along with the two main menus. The restart screen uses the
same visible-control traversal, modal focus ownership, Enter activation and
focus outline. Graphics-choice overrides remain limited to the main menus.
Unknown/mod GUI behavior and native engine behavior are unchanged.

The compiled menu harness passes 111 checks, including restart-menu policy,
case-insensitive matching, unknown-source exclusion and the absence of graphics
overrides on the death menu. All 59 Python tests pass.

The first live Load-panel test also exposed focus escaping to Main Menu behind
the overlay: the stock panel omits its modal flag. The web policy now marks only
`guis/restart.gui`'s `LoadGame` container modal. Its closed zero-size rectangle
continues to be skipped. The additional harness checks guard this exact source
and window match, null arguments and exclusion of other stock/mod windows.

Both web builds pass. Live verification of the final build shows the focus
outline on Restart and Load. Opening Load then pressing Tab enters the save
list; forward wrap and Shift+Tab stay within the list, Load Game and Cancel.
QuickSave was selected with arrow keys, and the focused Load Game button was
activated with Enter. Visual evidence:
`C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/death-load-focus.jpg`.
The game loaded Mars City and returned to the actual saved view
`(1263.77 -1501 68.25)`, yaw 180, without a positioning command. Normal input,
simulation and audio were restored (`in_nograb 0`, `com_fixedTic 0`,
`g_stopTime 0`, `s_noSound 0`); WebAudio reported a running context with nine
playing sources. Evidence: ignored `build-web/death-load-restored-console.txt`
and `C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/death-load-restored.jpg`.

The death fixture now explicitly selects stock normal difficulty and default
damage protection (`g_skill 1`, `g_damageScale 1`, `g_useDynamicProtection 1`,
`g_testDeath 0`). A fresh native run and the final rebuilt web run still match
all nine player/projectile/clock checkpoints. Evidence: ignored
`build-windows/player-death-defaults-native/full-console.txt` and
`build-web/player-death-defaults-console.txt`.

### Hangar material capture and clipboard feedback audit (2026-10-05)

`tests/render_hangar_parity.cfg` captures the reported red-rail viewpoint and
two nearby stair/floor views in stock Mars City, with soft particles, shadows,
bump mapping and specular enabled. Both builds use Ultra texture quality,
8x anisotropy and neutral gamma/brightness. The fixture uses noclip for a fixed
camera and excludes HUD, weapon and player-view effects. The latter exclusion
is necessary here: the initial native captures were entirely black because the
opening player-view fade covered the world. Those black captures are not accepted
as visual parity evidence. This fixture does not test that fade or normal movement.

Native 640x480 PNGs are under ignored
`build-windows/render-hangar-world-native/base/screenshots/`. Three browser
captures were generated at 640x480, and their camera readbacks match native.
All three recorded game/render clocks, frames and random seeds match exactly:
frames 11/12/13, times 176/192/208 ms, seeds 51639948/2023847007/-395835503.
Evidence: ignored `build-windows/render-hangar-world-native/full-console.txt`
and `build-web/render-hangar/console.txt`.

The displayed browser preview shows normal rails and floor at the saved-rail
view. Browser proof is JPEG UI capture, not the engine's raw PNG. The embedded
browser's Download PNG action did not produce an observable export through the
browser automation, and Copy image remained pending. Accordingly no pixel-error
metric or native/web rendering parity claim is made for these captures.
Raw browser PNG acquisition and moving-camera coverage remain open.
Visual evidence:
`C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/hangar-saved-rail-visible.jpg`.

The live pending clipboard operation exposed missing feedback: Copy image
disabled itself while the status continued to say the screenshot was ready.
The launcher now reports copying immediately and, after five seconds, reports
that the browser is still waiting and suggests checking for a clipboard prompt
or trying Download PNG. It keeps one clipboard write pending at a time and
does not report success until the browser resolves it. The timer is cleared
when the operation settles and cannot overwrite a newer screenshot's status.
All seven browser regression groups pass, including pending-write feedback,
replacement-image protection and stale-timer checks.

A replacement capture also explains when an earlier clipboard write keeps Copy
disabled. The web build completes successfully with both feedback changes.
These feedback states are regression-tested; live browser verification of the
updated feedback remains open.

### Raw hangar PNG comparison (2026-10-05)

The rebuilt launcher now completes Copy image in the embedded browser. Its
successful clipboard result supplied real PNG bytes for all three frozen
hangar views. Captures explicitly use `webscreenshot 640 480`; the launcher
Screenshot button otherwise follows the physical canvas size (813x610 here).
An initial comparison with the FPS overlay enabled was rejected and repeated
with `com_showFPS 0` and `com_asyncInput 0`, matching the native fixture.

All three camera readbacks and recorded clocks/frames/seeds match the native
fixture. RGB mean absolute errors on the 0–255 scale are 0.160769 (rails),
0.932836 (stairs) and 1.048218 (saved rail). Pixels whose largest channel
difference exceeds 16 comprise 0.132487%, 0.646159% and 0.905273%, respectively.
These are measurements, not acceptance thresholds. Visual inspection shows
different shadow coverage around the stairs and floor despite the small global
averages; graphics parity remains incomplete. Next isolate the shadow pass
with matched shadows-on/off captures before changing renderer code.

Evidence is ignored `build-web/render-hangar/{rails-raw,stairs-raw,saved-rail-raw}.png`,
`raw-console.txt` and `raw-metrics.json`, compared with the native world PNGs
listed above. Screenshot copy success was verified live; the pending-feedback
branch remains covered by regression tests rather than this successful copy.
QuickSave and normal timing, HUD, weapon, input and audio settings were restored.
Physical pointer capture still reports WrongDocumentError in the embedded
browser. Moving-camera fidelity and sustained combat performance remain open.

### Stencil-shadow initialization diagnosis (2026-10-05)

Matched shadows-on/off native captures were taken at the same three frozen
hangar checkpoints. The pre-fix browser PNGs are byte-for-byte identical in
pixel data with shadows enabled and disabled. Against native shadows-off,
their RGB mean errors fall to 0.101566, 0.196066 and 0.271367; native shadows-on
retains the larger errors above. Thus the missing shadow coverage is not merely
a PNG export or screenshot overlay problem.

The WebGL branch of `R_CheckPortableExtensions` returns after
`R_GLES_InitConfig`, bypassing desktop initialization of `tr.stencilIncr` and
`tr.stencilDecr`. Both remain zero (`GL_ZERO`), erasing stencil values instead
of counting volume crossings. The WebGL configuration now explicitly assigns
core WebGL2 `GL_INCR_WRAP` and `GL_DECR_WRAP` on every initialization.
The hangar fixture explicitly selects normal shadow/debug controls.

The actual GPU regression page reads those assignments from renderer source
and exercises depth-failing crossings in an eight-bit stencil buffer. All
86 GPU checks pass, including increment, decrement, overflow and underflow.
A negative page using the old zero operations fails the first crossing test.
The existing compiled renderer-state harness also passes all 98 checks.
Evidence: ignored `build-web/stencil-gpu-checks.txt`,
`build-web/stencil-zero-negative-checks.txt`,
`build-windows/render-shadow-isolation/full-console.txt` and
`build-web/render-hangar/shadows-off-console.txt`.

The rebuilt engine passes the same licensed-data three-view audit. Native/web
clocks, frames and seeds still match exactly. Shadows now change all three
browser images, restoring the missing stair/floor coverage. RGB mean errors
against native shadows-on fall from 0.160769/0.932836/1.048218 to
0.100183/0.185637/0.250479. Pixels with any channel difference above 16 fall
to 0.013997%/0.060872%/0.073242%. The native and browser mean shadow effects
(on versus off) are 0.060560/0.060586, 0.753503/0.755038 and 0.795219/0.810457.
Remaining differences are not declared acceptable merely because the global
mean is small; broader material, moving-camera and campaign audits remain open.

Evidence: ignored `build-web/stencil-init-build.log` (successful compile/link),
`build-web/render-hangar/stencil-fixed/{rails,stairs,saved-rail}-{on,off}.png`,
`console.txt`, `metrics.json` and reproducible `compare-stencil.py` in its parent
directory. The native comparison uses the paired isolation captures above.

QuickSave was restored without a positioning command (saved view
1263.77/-1501/68.25, yaw 180), with normal simulation, input, view effects,
HUD/weapon and audio. A 180-frame stationary sample with the 60 FPS cap, Ultra
textures, 8x filtering and shadows enabled measures 50.9 FPS, CPU mean 17.51 ms
and p95 24.72 ms. Draw work averages 13.59 ms (8.01 ms scene generation,
5.57 ms submission/cleanup); session work averages 2.79 ms. This is a short
stationary sample, not proof of sustained movement/combat performance. The
restored shadow rendering must be preserved during subsequent optimization.
Evidence: ignored `build-web/render-hangar/stencil-fixed/restored-perf-console.txt`
and `C:/Users/allen/.codex/visualizations/2026/10/05/doom3-accuracy/stencil-shadow-fix-restored.jpg`.

### Scene-generation profiling expansion (2026-10-05)

A second 300-frame stationary sample with working shadows measures 51.7 FPS,
CPU mean 17.70 ms and p95 24.15 ms. Scene generation averages 7.88 ms and
backend work 6.17 ms. Evidence: ignored `build-web/view-perf-before-console.txt`.
These measurements reflect this machine's current workload; during the next
build only about 500 MB of 16 GB physical memory was free. The game tab was
temporarily replaced with the small GPU-check page to release game-data memory
during linking. No unrelated process was stopped.

`webperf` now splits view generation into matrix/frustum setup, portal
visibility, light surfaces, models/interactions, prune/sort and subviews/demo
recording/draw-queue work. Each recursive view owns its timer, including early
returns. Nested subview time overlaps the parent's subview measurement and
must not be summed as mutually exclusive categories. Clock reads occur only
during an explicit sample. The instrumentation is web-only and changes no
rendering or simulation policy; it is diagnostic work, not a performance gain.

The instrumented web build compiles and links successfully. Its frozen 640x480
saved-rail PNG is pixel-identical to the prior fixed-shadow build (largest
channel change zero), and all three native game/render clocks, frames and
seeds still match. Evidence: ignored `build-web/view-perf-build.log`,
`build-web/view-perf/saved-rail.png`, `image-check.txt` and `frozen-console.txt`.

The instrumented 300-frame sample measures 35.2 FPS, CPU mean 19.10 ms and
p95 29.76 ms. View work averages 0.01 ms setup, 0.15 ms visibility, 0.67 ms
lights, 6.78 ms models/interactions, 0.12 ms prune/sort and 0.01 ms
subviews/demo/queue. Models/interactions are the largest measured frontend
cost and the next optimization target. These samples were taken under varying
machine load and do not establish a performance change from instrumentation.
Sustained 60 FPS remains unverified. Evidence: ignored
`build-web/view-perf/profile-console.txt`.

## 10. Files added for web

- `web/shell.html` — Emscripten shell (`{{{ SCRIPT }}}`, canvas + console,
  game-data picker → MEMFS `/doom3/base`, IDBFS saves, pointer-lock/audio,
  `noInitialRun` + `callMain('+set fs_basepath /doom3')`).
- `web/serve.py` + `scripts/web-run.sh` — local server (wasm MIME, COOP/COEP).
- `scripts/web-setup.sh` — emsdk/env check, preset validation, configure
  guidance.
- `neo/CMakePresets.json` → `web-wasm` preset (`HARDLINK_GAME=ON`,
  `BASE=ON`, `D3XP=OFF`, `IMGUI=OFF`, `DEDICATED=OFF`, `TOOLS=OFF`,
  Emscripten toolchain via `$env{EMSDK}`); `-DWEB_PRELOAD_DIR=` for testing.
- `.github/workflows/web.yml` — validates the shell and builds the engine with
  pinned Emscripten 4.0.23, without game data.
