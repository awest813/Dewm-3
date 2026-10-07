# Web renderer plan: native-accurate output, much lower frame cost

Status as of 2026-10-06, after the GPU depth-copy and submission audit in
[`WEB.md`](WEB.md) ("GPU depth copy, submission audit and repeatable bench").
Numbers below come from that audit's reference conditions: Chrome 154
headless, ANGLE D3D11, AMD Radeon integrated GPU, 1005x753, frozen Mars City
hangar, 761 draws per frame. They describe one scene on one device.

## Progress

| Item | Status |
| --- | --- |
| 0: fixed capture size | done: projection follows window aspect; bench pinned to native 640x480 |
| 0: per-pass GPU timers | done: `webgpu`, plus `websurfaces` and `webpixel` |
| 0: more scenes | done: 12 campaign views (`tests/render_scenes_parity.cfg`) with native references |
| 0: second browser | open |
| 1.1: skip unused `_currentDepth` | done (`r_webSkipUnusedDepthCopy`); the remaining copy costs 0.15–0.4 ms, so scissoring it is low value |
| 1.2, 1.3 | open; per-pass timing shows render copies and shadows are small next to interactions |
| 1.4: interaction `discard` | measured: removing it changes nothing, not pursued |
| 1.5: S3TC | blocked for parity: native High/Medium rely on driver-side DXT encoding, which WebGL cannot reproduce; web defaults to Ultra |
| 1.6: resolution policy | done as an opt-in: Full/75%/50% render resolution in Graphics options and the in-game menu (`r_webRenderScale`); default Full |
| 2.1: vertex array objects | done (`r_webVertexArrays`); buffers re-uploaded within three frames skip the cache, which had churned in live scenes |
| 2.2: uniform blocks | interaction parameters packed into one array (`r_webDeferInteractionEnv`); measured 0–0.1 ms, so full uniform blocks are low value |
| 2.3: transient index staging | tried as a shared index ring: neutral, dropped |
| 3.2: `-msimd128` build-wide | done (`WEB_SIMD`), every parity fixture unchanged |
| 3.1: explicit SIMD kernels | open |
| Accuracy | clamp and sky-selection fixes; all 15 views MAE ≤ 0.0113; UCRT-exact `sinf`/`cosf` make every scene seed match native |
| Not in the original plan | OpenAL call caching (0.4–0.8 ms/frame) |

Details and measurements: [`WEB.md`](WEB.md), sections dated 2026-10-06.
After this work the hangar at 640x480 measures frozen CPU mean 4.2–4.8 ms and
GPU p50 about 5.1 ms, with 5,166 WebGL calls per frame. The main thread is
about 60–66% idle in profiles. GPU time is now mostly interaction shading,
which is the stock per-light work rather than web overhead. Further large
wins need structural work (Phase 4) or Tier 2 options. The table below is the
starting point the plan was written against.

## Where the time goes now

| Budget | Now | Main consumers |
| --- | ---: | --- |
| GPU per frame | ~6.5–7.5 ms (was 13–19 ms) | interactions ~3 ms; shadows ~0.5–1 ms; remainder is ambient/translucent/post |
| CPU per frame, frozen | ~5–6 ms | backend submission 2–3 ms; scene generation 1.5–2.5 ms |
| CPU per frame, live sim | ~7–11 ms (noisy) | game simulation + the above; live frames are now usually CPU-bound |
| WebGL calls per frame | 9,046 | `vertexAttribPointer` 2,513; `bindBuffer` 1,599; `bindTexture` 930; `uniform4fv` 836; `activeTexture` 822; `drawElements` 757; `uniformMatrix4fv` 371 |
| Uploads per frame | 92 `bufferData` | 86 CPU-index draws (GUI/deform surfaces) + per-frame index allocations |

The pre-audit GPU cost was dominated by one ANGLE slow path (combined
depth/stencil blit). Expect more such cliffs: always measure GPU time, not only
CPU time, and test both Chrome/ANGLE-D3D11 and at least one non-ANGLE browser.

## Rules for every change

1. **Exactness tiers.** Each change declares one tier up front:
   - **Tier 0, output-identical.** Pure performance work: state caching, batching,
     fewer copies, equivalent SIMD. Gate: all hangar captures have maximum
     channel change 0 versus the previous web build at the same canvas size,
     and every `RENDER_STATE` matches.
   - **Tier 1, accuracy fix.** Gate: native MAE and pixels-over-16 do not rise on
     any reference view; the targeted view improves. Also needs a GPU-shader or
     extracted check that fails on the old code.
   - **Tier 2, visual trade-off** (e.g. resolution scale). Opt-in only, never
     default, and never used for parity captures.
2. **Interleave A/B.** GPU clocks on integrated parts drift between page loads.
   Prefer a runtime cvar plus same-page alternating samples (as
   `r_webDepthOnlyCopy` / `r_webBatchFrameTemp` did); otherwise use at least
   two interleaved page loads per build.
3. **Report GPU p50/p95 and submit/scene time,** not only FPS. FPS saturates at
   the 60 Hz display and hides headroom.
4. **Keep a kill switch** for each optimization until it has survived a broad
   campaign sweep.

## Phase 0 — measurement coverage (do first, small)

- **Fixed capture size.** Captures currently vary with the canvas size (MAE
  0.14–0.21 between 629x471 and 1005x753 for one build). Find the cause:
  likely candidates are `_currentRender`/`_currentDepth` power-of-two sizing,
  tiled screenshots when the canvas is smaller than the capture, and
  post-process scale. Then either make captures size-independent or pin the
  bench canvas. Tier 1 if the cause is a renderer bug.
- **Per-pass GPU timers in the engine.** A `webperf gpu` mode that brackets
  depth prefill, `_currentDepth` copy, each light's shadow and interaction
  passes, translucent, post-process and GUI with timer queries. Read results
  one frame late; no queries outside a sample. This replaces whole-frame
  cvar toggling.
- **More scenes.** Add native/web fixture pairs for: a dense multi-light room
  (Alpha Labs), a combat encounter with skinned monsters, a heat-haze/glass
  heavy view, and a GUI-heavy view (PDA or in-world screens). Record native
  references on the same machine.
- **Second browser.** Run the bench in Firefox (no ANGLE on its default
  Windows path) to separate engine cost from ANGLE cost.

Exit: one command produces captures, native MAE, CPU/GPU per pass and a WebGL
call histogram for at least four scenes.

## Phase 1 — GPU cost (largest effect on weak/integrated GPUs)

1. **Skip `_currentDepth` when nothing samples it** (Tier 0). The copy runs
   for every view whenever `r_useSoftParticles` is on, even if no soft
   particle is visible. Have the frontend flag views that contain a
   soft-particle stage; copy only then. Also clip the blit to the union of
   those surfaces' scissor rectangles.
2. **Same rule for `_currentRender`** (heat haze, glass, color process): copy
   only the scissored region that is actually sampled (Tier 0 if every sampled
   texel is still copied).
3. **Shadow-volume fill** (Tier 0). Shadow draws already use per-surface
   scissors. What WebGL lacks is the depth-bounds test (native
   `r_useDepthBoundsTest`). That test rejects volume fragments where the
   *stored* scene depth lies outside the light's range; those pixels cannot
   receive that light, so their stencil values never matter. The only
   emulation is sampling `_currentDepth` in the shadow shader and discarding,
   which costs a texture read per fragment. Measure stencil-pass GPU time per
   light with the Phase 0 timers first; act only if it is material, and
   confirm lit pixels are unchanged.
4. **Interaction cost (~3 ms)** (Tier 0 candidates only):
   - Confirm early depth rejection survives `discard` in the interaction
     shader. The shader discards only on alpha test, so a variant without
     `discard` for the common case lets the GPU keep early-Z.
   - Remove dead work for `u_alphaTest.x == 0` with a compile-time variant.
   - Do **not** replace the normalization cube map or the specular table:
     their quantization is part of native output.
5. **Texture formats** (Tier 1, needs Phase 0 references at High spec):
   - Fix S3TC detection (`WEBGL_compressed_texture_s3tc`). The current probe
     never matches.
   - Then verify High/Medium specs against native DXT output. This cuts
     texture memory roughly 4–8x at those specs, which matters for the 2 GB
     wasm heap ceiling and for lower-memory machines.
   - Audit other storage-hint promotions (RGB5/RGBA4/L8A8 → RGBA8) against
     native at those specs.
6. **Resolution policy** (Tier 2, opt-in): a render-scale option and a
   documented devicePixelRatio policy for HiDPI screens. Fill cost scales with
   pixels, but this is never a parity setting.

Exit: GPU p50 ≤ 6 ms in all Phase 0 scenes on the reference iGPU at
1005x753, every capture unchanged.

## Phase 2 — WebGL submission (CPU, ~2–3 ms and 9k calls)

1. **Vertex array objects** (Tier 0, biggest remaining call reduction).
   - Cache one VAO per (array buffer, attribute layout, enabled mask).
   - Most surfaces own a VBO, so every draw rewrites five or six attribute
     pointers and rebinds buffers (~2,500 + ~1,600 calls per frame).
   - Resolve at draw time from the shim's existing shadow state, not by
     editing engine call sites. Keep the element-buffer binding explicit
     (it is VAO state).
   - Fall back to the current path for frame-temp data, whose offsets change
     every frame. Kill switch: `r_webVertexArrays`.
2. **Uniform blocks for interaction parameters** (Tier 0). Pack one block per
   light (origin, projection, falloff, colors) and a small per-surface block,
   replacing most of the ~836 `uniform4fv` + 371 matrix calls. Keep the
   existing value cache as the change detector.
3. **Transient index data** (Tier 0). Give frame-lifetime surfaces (GUI,
   deforms, per-frame light/shadow triangles) frame-temp index storage, staged
   and uploaded once like frame-temp vertices.
   - Keep long-lived indices in their own buffers. Browsers cache index-range
     validation per buffer, so mixing static and per-frame data in one buffer
     would re-validate static draws every frame.
   - Removes ~90 `bufferData` calls per frame.
4. **Texture-bind ordering inside a light** (needs proof before Tier 0). Light
   interactions blend with ONE,ONE into an 8-bit target. Unsigned saturating
   adds commute, so reordering surfaces within one light/stencil state by
   material could cut binds. Prove it exact with a pixel check across the
   scene set before enabling; drop it if any capture changes.
5. **Multi-draw** (later). `WEBGL_multi_draw` with `gl_DrawID`-indexed
   matrices could batch shadow volumes per light once Phase 2.1 removes
   per-draw attribute rebinding.

Exit: ≤ 4,000 WebGL calls and ≤ 1.5 ms submit per frame in the hangar, captures
unchanged.

## Phase 3 — frontend and simulation CPU (live frames)

1. **SIMD128 for `Simd_Generic` kernels** (Tier 0). The native Windows x64
   parity build also runs the generic C++ kernels: MSVC x64 compiles none of
   the inline SSE. Lane-wise wasm SIMD that keeps each lane's operation order
   is therefore bit-identical.
   - Order: skinning (`TransformJoints`/`TransformVerts`), `DeriveTangents`,
     `CreateShadowCache`/`CreateVertexProgramShadowCache`, `MinMax`, `Dot`.
   - Validate each kernel with the extracted-harness pattern already used for
     culling, facing and light-triangle bounds.
   - Never use relaxed-SIMD FMA.
2. **`-msimd128` auto-vectorization** (Tier 0 candidate). Try it build-wide
   only behind the full parity suite: combat, BFG, ranged, rotation and
   collision fixtures plus the hangar captures. Keep it if every serialized
   checkpoint and capture still matches exactly.
3. **Profile live simulation** with the existing `webperf` phases, during
   combat, to split game-code cost from renderer frontend cost before
   choosing further targets.

Exit: live 60-cap CPU p95 ≤ 12 ms in the combat scenes, all parity fixtures
unchanged.

## Phase 4 — structural (research, after Phases 1–3)

- **Backend on a worker.** Use OffscreenCanvas plus pthreads (the existing
  `WEB_THREADS` experiment) to overlap frontend N+1 with backend N, like the
  engine's original SMP split. It needs COOP/COEP hosting and careful
  vertex-cache lifetime review. Measure the overhead of the existing
  single-threaded path first.
- **WebGPU backend** only if WebGL call overhead remains the limit after
  Phase 2. It would be a second renderer with its own parity burden.

## Accuracy track (runs alongside)

1. Fix the capture-size dependence (Phase 0).
2. Add native references for more campaign scenes and a moving camera.
   Today's evidence covers three frozen hangar views.
3. Check High/Medium texture formats against native once S3TC detection is
   fixed (Phase 1.5).
4. Port the remaining float libm functions only when a fixture diverges
   through them: `tanf`, `atan2f`, `atanf`, `expf` and `powf` nearly match
   UCRT when evaluated in double; `asinf`, `acosf` and `logf` need AMD ports.
5. Track remaining known approximations: glass warp is approximate (no
   retail material uses it); custom ARB programs outside the ported set use
   the flat fallback (the retail inventory needs none besides `pinch.cg`,
   Cg source that the native ARB loader cannot compile either; confirm the
   native result for its two materials with a capture).
6. Keep every Tier 1 change paired with a GPU check that fails on the old
   shader, as the 2026-10-06 falloff and blend-light checks do.

## Suggested order

| Step | Phase | Tier | Expected effect |
| --- | --- | --- | --- |
| 1 | 0: fixed capture size, per-pass GPU timers, three more scenes | — | makes every later step measurable |
| 2 | 1.1–1.2: skip/scissor depth and render copies | 0 | GPU savings in scenes without soft particles or haze |
| 3 | 2.1: vertex array objects | 0 | ~4,000 fewer calls per frame |
| 4 | 2.3: transient index staging | 0 | ~90 fewer uploads per frame |
| 5 | 3.1: SIMD skinning and shadow kernels | 0 | live-frame CPU |
| 6 | 2.2: uniform blocks | 0 | ~1,000 fewer calls per frame |
| 7 | 1.5: S3TC detection + High-spec parity | 1 | memory, High/Medium parity |
| 8 | 1.4, 2.4, 3.2 | 0 after proof | situational |
