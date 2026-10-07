/*
 * tr_gles.cpp — WebGL2 / OpenGL ES 3.0 backend for the dhewm3 web port.
 *
 * Built only for EMSCRIPTEN (see neo/CMakeLists.txt). What it does:
 *
 *  - R_GLES_LoadFunctions(): resolve every qgl* pointer — real GLES3
 *    functions where they exist, in-file replacements or no-op stubs
 *    otherwise. Never FatalErrors (the desktop loader does).
 *  - R_GLES_InitConfig(): fill glConfig with WebGL2-safe values.
 *  - Fixed-function emulation: matrix-stack mirror (modelview/projection/
 *    texture) with MVP uniform sync; client-state arrays reimplemented as
 *    vertex attributes; engine attrib indices 8..11 remapped onto the
 *    shader-visible locations below; alpha-func tracked as a shader uniform.
 *  - GLSL-ES 3.0 programs: a Blinn-Phong interaction shader (same maps,
 *    colors and falloff as the ARB original, not bit-identical), an MVP
 *    shadow-volume shader (shared GPU-extruded or private projected verts),
 *    environment / bumpy-environment reflection
 *    shaders, a glasswarp shader, and a flat program that also covers
 *    OBJECT_PLANE texgen draws (fog, blend lights, projected/screen textures).
 *    Env parameters are uploaded live (the engine writes them between bind
 *    and draw); draw calls re-select the flat program when texgen is active.
 *
 * Attribute convention (see draw_arb2.cpp RB_ARB2_CreateDrawInteractions):
 *    loc 0 = xyz (vec3 client ptr, vec4 shadow-cache ptr)
 *    loc 1 = st, loc 2 = color (ubyte, normalized), loc 3 = normal,
 *    loc 4 = tangent0, loc 5 = tangent1.
 * Engine ARB indices 8/9/10/11 (st/tan0/tan1/normal) are remapped to 1/4/5/3.
 *
 * Rendering parity remains under review (see docs/WEB.md).
 * Packed normal maps, the engine specular table, alpha comparisons and
 * old-style material/vertex color combinations are emulated in GLSL.
 *  - custom ARB programs outside the built-in ports use the flat fallback.
 */

#include <set>
#include <unordered_map>
#include <vector>
#include <algorithm>
#include "sys/platform.h"
#include "framework/Common.h"
#include "renderer/tr_local.h"
#include "renderer/WebRenderTiming.h"
#include "renderer/qgl.h"
static std::set<GLuint> g_depthTextures;
static GLuint g_scratchIndexBuffer = 0;
static GLuint g_depthCopyFramebuffer = 0;

#ifdef __EMSCRIPTEN__
#include <emscripten/html5.h>
#endif
#ifndef GL_TIME_ELAPSED_EXT
#define GL_TIME_ELAPSED_EXT 0x88BF
#endif
#ifndef GL_GPU_DISJOINT_EXT
#define GL_GPU_DISJOINT_EXT 0x8FBB
#endif

struct webPerf_t {
	int remaining, samples;
	bool warmup;
	double started, cpu[600];
	// Pacing: start-to-start interval of rendered frames and game tics each
	// rendered frame ran (index 3 counts three or more).
	double intervals[600], lastRendered;
	int intervalCount, frameTics, ticFrames[4];
	// Slowest sampled frame: CPU time, its top-level phases (events,
	// commands, session, draw, async) and game tics, to attribute hitches.
	double slowestMs, slowest[8], frameStartPhases[7], frameStartAsync;
	int slowestTics;
	double asyncMs;
	double phases[WEB_RENDER_PHASE_COUNT];
	unsigned int phaseCalls[WEB_RENDER_PHASE_COUNT];
	unsigned int draws, indexQueries, programBinds, uniformUploads, bufferCreates;
	unsigned int uniformWrites, bufferBinds, attribWrites, vertexArrayBinds, vertexArrayCreates;
	unsigned int callbacks, skippedCallbacks;
	double lightInputFaces, lightKeptFaces;
	unsigned int lightTriangleBuilds, fusedBoundBuilds;
	unsigned int bufferDataCalls, bufferSubDataCalls, cpuIndexDraws;
	unsigned int activeTextureCalls, stencilCalls;
	double uploadBytes;
};
static webPerf_t g_webPerf = {};
// Rendered browser frames (R_GLES_GpuFrame); dates buffer uploads.
static unsigned int g_glesFrame = 1;

extern "C" void R_GLES_PerfCallback( bool rendered ) {
	if (!g_webPerf.remaining) return;
	++g_webPerf.callbacks;
	if (!rendered) {
		++g_webPerf.skippedCallbacks;
		return;
	}
	const double now = emscripten_get_now();
	if (!g_webPerf.warmup && g_webPerf.lastRendered > 0 && g_webPerf.intervalCount < 600) {
		g_webPerf.intervals[g_webPerf.intervalCount++] = now - g_webPerf.lastRendered;
	}
	g_webPerf.lastRendered = now;
}

// Game tics run by the session this frame (idSessionLocal::Frame).
extern "C" void R_GLES_PerfTics( int tics ) {
	if (g_webPerf.remaining) g_webPerf.frameTics += tics;
}

extern "C" void R_GLES_PerfAsync( double cpuMs ) {
	if (g_webPerf.remaining) g_webPerf.asyncMs += cpuMs;
}
extern "C" void R_GLES_PerfPhase( int phase, double cpuMs ) {
	if (g_webPerf.remaining && phase >= 0 && phase < WEB_RENDER_PHASE_COUNT) {
		g_webPerf.phases[phase] += cpuMs;
		++g_webPerf.phaseCalls[phase];
	}
}
extern "C" double R_GLES_PerfTimestamp() {
	return g_webPerf.remaining ? emscripten_get_now() : 0;
}

extern "C" void R_GLES_PerfLightTriangles( int inputFaces, int keptFaces, bool fusedBounds ) {
	if (!g_webPerf.remaining) return;
	g_webPerf.lightInputFaces += inputFaces;
	g_webPerf.lightKeptFaces += keptFaces;
	++g_webPerf.lightTriangleBuilds;
	if (fusedBounds) ++g_webPerf.fusedBoundBuilds;
}

static void GLES_Perf_f( const idCmdArgs &args ) {
	g_webPerf = webPerf_t();
	g_webPerf.remaining = args.Argc() > 1 ? idMath::ClampInt(30, 600, atoi(args.Argv(1))) : 180;
	g_webPerf.warmup = true;
	common->Printf("Web perf: sampling %d frames; keep the camera and browser size fixed\n", g_webPerf.remaining);
}

void R_GLES_PerfFrame( double cpuMs ) {
	if (!g_webPerf.remaining) return;
	if (g_webPerf.warmup) {
		g_webPerf.warmup = false;
		g_webPerf.started = emscripten_get_now();
		g_webPerf.draws = g_webPerf.indexQueries = g_webPerf.programBinds = g_webPerf.uniformUploads = 0;
		g_webPerf.asyncMs = 0;
		g_webPerf.bufferCreates = 0;
		g_webPerf.uniformWrites = g_webPerf.bufferBinds = g_webPerf.attribWrites = 0;
		g_webPerf.vertexArrayBinds = g_webPerf.vertexArrayCreates = 0;
		g_webPerf.callbacks = g_webPerf.skippedCallbacks = 0;
		g_webPerf.lightInputFaces = g_webPerf.lightKeptFaces = 0;
		g_webPerf.lightTriangleBuilds = g_webPerf.fusedBoundBuilds = 0;
		g_webPerf.bufferDataCalls = g_webPerf.bufferSubDataCalls = g_webPerf.cpuIndexDraws = 0;
		g_webPerf.activeTextureCalls = g_webPerf.stencilCalls = 0;
		g_webPerf.uploadBytes = 0;
		g_webPerf.intervalCount = g_webPerf.frameTics = 0;
		g_webPerf.slowestMs = 0;
		memset(g_webPerf.frameStartPhases, 0, sizeof(g_webPerf.frameStartPhases));
		g_webPerf.frameStartAsync = 0;
		memset(g_webPerf.ticFrames, 0, sizeof(g_webPerf.ticFrames));
		memset(g_webPerf.phases, 0, sizeof(g_webPerf.phases));
		memset(g_webPerf.phaseCalls, 0, sizeof(g_webPerf.phaseCalls));
		return;
	}
	g_webPerf.cpu[g_webPerf.samples++] = cpuMs;
	++g_webPerf.ticFrames[g_webPerf.frameTics < 3 ? g_webPerf.frameTics : 3];
	if (cpuMs > g_webPerf.slowestMs) {
		g_webPerf.slowestMs = cpuMs;
		for (int i = 0; i < 7; ++i) g_webPerf.slowest[i] = g_webPerf.phases[i] - g_webPerf.frameStartPhases[i];
		g_webPerf.slowest[7] = g_webPerf.asyncMs - g_webPerf.frameStartAsync;
		g_webPerf.slowestTics = g_webPerf.frameTics;
	}
	for (int i = 0; i < 7; ++i) g_webPerf.frameStartPhases[i] = g_webPerf.phases[i];
	g_webPerf.frameStartAsync = g_webPerf.asyncMs;
	g_webPerf.frameTics = 0;
	if (--g_webPerf.remaining) return;
	double elapsed = emscripten_get_now() - g_webPerf.started, total = 0;
	for (int i = 0; i < g_webPerf.samples; ++i) total += g_webPerf.cpu[i];
	std::sort(g_webPerf.cpu, g_webPerf.cpu + g_webPerf.samples);
	double frames = g_webPerf.samples;
	common->Printf("Web perf: %.1f fps, CPU mean %.2f ms, p95 %.2f ms; per frame %.1f draws, %.1f index queries, %.1f program binds, %.1f full uniform uploads\n",
		frames * 1000.0 / elapsed, total / frames, g_webPerf.cpu[(g_webPerf.samples * 95 - 1) / 100],
		g_webPerf.draws / frames, g_webPerf.indexQueries / frames, g_webPerf.programBinds / frames, g_webPerf.uniformUploads / frames);
	common->Printf("Web perf: %.1f animation callbacks/s, %u cap skips (%.1f%%)\n",
		g_webPerf.callbacks * 1000.0 / elapsed, g_webPerf.skippedCallbacks,
		g_webPerf.callbacks ? 100.0 * g_webPerf.skippedCallbacks / g_webPerf.callbacks : 0.0);
	common->Printf("Web perf: CPU breakdown %.2f ms async input/audio, %.2f ms game/render\n",
		g_webPerf.asyncMs / frames, (total - g_webPerf.asyncMs) / frames);
	common->Printf("Web perf: %.2f ms events, %.2f ms commands/network, %.2f ms session, %.2f ms draw\n",
		g_webPerf.phases[0] / frames, g_webPerf.phases[1] / frames, g_webPerf.phases[2] / frames, g_webPerf.phases[3] / frames);
	common->Printf("Web perf: %.1f new GPU buffers per frame\n", g_webPerf.bufferCreates / frames);
	common->Printf("Web perf: %.1f uniform writes, %.1f buffer binds, %.1f attribute writes per frame\n",
		g_webPerf.uniformWrites / frames, g_webPerf.bufferBinds / frames, g_webPerf.attribWrites / frames);
	common->Printf("Web perf: %.1f vertex array binds, %.1f vertex arrays created per frame\n",
		g_webPerf.vertexArrayBinds / frames, g_webPerf.vertexArrayCreates / frames);
	common->Printf("Web perf: draw %.2f ms begin, %.2f ms scene generation, %.2f ms submit/cleanup\n",
		g_webPerf.phases[4] / frames, g_webPerf.phases[5] / frames, g_webPerf.phases[6] / frames);
	common->Printf("Web perf: %.2f ms backend, %.2f ms triangle cleanup, %.2f ms vertex-cache cleanup\n",
		g_webPerf.phases[7] / frames, g_webPerf.phases[8] / frames, g_webPerf.phases[9] / frames);
	common->Printf("Web perf: views %.2f ms setup, %.2f ms visibility, %.2f ms lights\n",
		g_webPerf.phases[10] / frames, g_webPerf.phases[11] / frames, g_webPerf.phases[12] / frames);
	common->Printf("Web perf: views %.2f ms models/interactions, %.2f ms prune/sort, %.2f ms subviews/demo/queue (nested subview time overlaps)\n",
		g_webPerf.phases[13] / frames, g_webPerf.phases[14] / frames, g_webPerf.phases[15] / frames);
	common->Printf("Web perf: model detail %.2f ms resolve/animate (%.1f calls), %.2f ms ambient surfaces (%.1f calls), %.2f ms active interactions (%.1f calls) per frame\n",
		g_webPerf.phases[16] / frames, g_webPerf.phaseCalls[16] / frames,
		g_webPerf.phases[17] / frames, g_webPerf.phaseCalls[17] / frames,
		g_webPerf.phases[18] / frames, g_webPerf.phaseCalls[18] / frames);
	common->Printf("Web perf: interaction builds %.2f ms (%.1f calls) per frame; active time includes builds and shadow-only model resolution\n",
		g_webPerf.phases[19] / frames, g_webPerf.phaseCalls[19] / frames);
	common->Printf("Web perf: light triangles %.1f input / %.1f kept per frame; %.1f builds (%.1f fused bounds)\n",
		g_webPerf.lightInputFaces / frames, g_webPerf.lightKeptFaces / frames,
		g_webPerf.lightTriangleBuilds / frames, g_webPerf.fusedBoundBuilds / frames);
	if (g_webPerf.intervalCount > 0) {
		// A locked cap should hold one interval; report how many frames did.
		const int limit = cvarSystem->GetCVarInteger("r_webFrameLimit");
		double *iv = g_webPerf.intervals;
		const int n = g_webPerf.intervalCount;
		std::sort(iv, iv + n);
		int onCadence = 0;
		if (limit > 0) {
			const double target = 1000.0 / limit;
			for (int i = 0; i < n; ++i) onCadence += iv[i] > target - 2.5 && iv[i] < target + 2.5;
		}
		common->Printf("Web pacing: frame interval p50 %.2f ms, p95 %.2f ms, max %.2f ms; %s\n",
			iv[n / 2], iv[(n * 95 - 1) / 100], iv[n - 1],
			limit > 0 ? va("%.1f%% within 2.5 ms of the %d FPS interval", 100.0 * onCadence / n, limit) : "unlocked");
		common->Printf("Web pacing: game tics per frame 0:%d 1:%d 2:%d 3+:%d\n",
			g_webPerf.ticFrames[0], g_webPerf.ticFrames[1], g_webPerf.ticFrames[2], g_webPerf.ticFrames[3]);
		common->Printf("Web pacing: slowest frame %.2f ms CPU: %.2f events, %.2f async, %.2f commands, %.2f session (%d tics), %.2f draw (%.2f scene generation, %.2f submit)\n",
			g_webPerf.slowestMs, g_webPerf.slowest[0], g_webPerf.slowest[7], g_webPerf.slowest[1], g_webPerf.slowest[2],
			g_webPerf.slowestTics, g_webPerf.slowest[3], g_webPerf.slowest[5], g_webPerf.slowest[6]);
	}
	common->Printf("Web perf: uploads %.1f bufferData + %.1f bufferSubData calls, %.1f KB per frame; %.1f CPU-index draws\n",
		g_webPerf.bufferDataCalls / frames, g_webPerf.bufferSubDataCalls / frames,
		g_webPerf.uploadBytes / 1024.0 / frames, g_webPerf.cpuIndexDraws / frames);
	common->Printf("Web perf: %.1f texture-unit selects, %.1f stencil state calls per frame\n",
		g_webPerf.activeTextureCalls / frames, g_webPerf.stencilCalls / frames);
}

static int g_dumpSurfaces = 0;	// websurfaces: 1 armed, 2 dumping this frame
// webpixel: 1 armed, 2 probing this frame; an optional draw range is always reported.
static int g_pixelProbe = 0, g_pixelX = 0, g_pixelY = 0, g_pixelDraw = 0, g_pixelFirst = 0, g_pixelLastDraw = -1;
static byte g_pixelLastColor[4];

// webgpu [frames]: GPU time per render pass from timer queries
// (EXT_disjoint_timer_query_webgl2). Queries run one at a time; a pass ends
// when the next begins, and "other" covers GUI, 2D and frame work outside 3D
// views. Results are read frames later, so sampling never waits on the GPU.
static const char *g_gpuPassNames[WEB_GPU_PASS_COUNT] = {
	"depth fill", "depth copy", "shadows", "interactions", "ambient/translucent", "fog/blend lights", "post-process", "other"
};
struct webGpuQuery_t { GLuint query; int pass; };
static struct {
	bool available;
	int remaining, frames, active, pass;
	idList<webGpuQuery_t> pending;
	idList<GLuint> pool;
	double ms[WEB_GPU_PASS_COUNT];
	unsigned int disjoint;
} g_webGpu;

static void GLES_GpuEnd( void ) {
	if ( g_webGpu.pass < 0 ) return;
	glEndQuery( GL_TIME_ELAPSED_EXT );
	g_webGpu.pass = -1;
}

void R_GLES_GpuPass( int pass ) {
	if ( !g_webGpu.remaining || pass == g_webGpu.pass ) return;
	GLES_GpuEnd();
	webGpuQuery_t q;
	if ( g_webGpu.pool.Num() ) {
		q.query = g_webGpu.pool[g_webGpu.pool.Num() - 1];
		g_webGpu.pool.RemoveIndex( g_webGpu.pool.Num() - 1 );
	} else {
		glGenQueries( 1, &q.query );
	}
	q.pass = pass;
	glBeginQuery( GL_TIME_ELAPSED_EXT, q.query );
	g_webGpu.pending.Append( q );
	g_webGpu.pass = pass;
}

static void GLES_GpuCollect( void ) {
	GLint disjoint = 0;
	glGetIntegerv( GL_GPU_DISJOINT_EXT, &disjoint );
	if ( disjoint ) ++g_webGpu.disjoint;
	while ( g_webGpu.pending.Num() ) {
		webGpuQuery_t &q = g_webGpu.pending[0];
		if ( q.pass == g_webGpu.pass && g_webGpu.pending.Num() == 1 ) break;	// still open
		GLuint ready = 0;
		glGetQueryObjectuiv( q.query, GL_QUERY_RESULT_AVAILABLE, &ready );
		if ( !ready ) break;
		GLuint ns = 0;
		glGetQueryObjectuiv( q.query, GL_QUERY_RESULT, &ns );
		if ( !disjoint ) g_webGpu.ms[q.pass] += ns / 1.0e6;
		g_webGpu.pool.Append( q.query );
		g_webGpu.pending.RemoveIndex( 0 );
	}
}

// Called once per rendered browser frame.
void R_GLES_GpuFrame( void ) {
	++g_glesFrame;
	// websurfaces arms on one frame boundary and dumps the whole next frame.
	if ( g_dumpSurfaces ) g_dumpSurfaces = g_dumpSurfaces == 1 ? 2 : 0;
	if ( g_pixelProbe ) {
		g_pixelProbe = g_pixelProbe == 1 ? 2 : 0;
		g_pixelDraw = 0;
		memset( g_pixelLastColor, 0xff, sizeof( g_pixelLastColor ) );
	}
	if ( !g_webGpu.active ) return;
	if ( g_webGpu.remaining ) {
		R_GLES_GpuPass( WEB_GPU_OTHER );
		if ( --g_webGpu.remaining == 0 ) GLES_GpuEnd();
		++g_webGpu.frames;
	}
	GLES_GpuCollect();
	if ( g_webGpu.remaining || g_webGpu.pending.Num() ) return;
	g_webGpu.active = 0;
	double total = 0;
	for ( int i = 0; i < WEB_GPU_PASS_COUNT; i++ ) total += g_webGpu.ms[i];
	common->Printf( "Web GPU: %d frames, %.2f ms per frame%s\n", g_webGpu.frames, total / g_webGpu.frames,
		g_webGpu.disjoint ? " (GPU timing was disjoint: some passes were discarded, averages are low)" : "" );
	for ( int i = 0; i < WEB_GPU_PASS_COUNT; i++ ) {
		common->Printf( "Web GPU: %-20s %6.2f ms\n", g_gpuPassNames[i], g_webGpu.ms[i] / g_webGpu.frames );
	}
}

static void GLES_Pixel_f( const idCmdArgs &args ) {
	if ( args.Argc() != 3 && args.Argc() != 5 ) {
		common->Printf( "usage: webpixel <x> <y> [first last]  (framebuffer pixels, origin bottom-left)\n" );
		return;
	}
	g_pixelX = atoi( args.Argv(1) );
	g_pixelY = atoi( args.Argv(2) );
	// Optional draw range: report every draw in it, changed or not.
	g_pixelFirst = args.Argc() == 5 ? atoi( args.Argv(3) ) : 0;
	g_pixelLastDraw = args.Argc() == 5 ? atoi( args.Argv(4) ) : -1;
	g_pixelProbe = 1;
}

static void GLES_Gpu_f( const idCmdArgs &args ) {
	if ( !g_webGpu.available ) {
		common->Printf( "Web GPU: EXT_disjoint_timer_query_webgl2 unavailable\n" );
		return;
	}
	if ( g_webGpu.active ) {
		common->Printf( "Web GPU: a sample is already running\n" );
		return;
	}
	g_webGpu.remaining = args.Argc() > 1 ? idMath::ClampInt( 10, 600, atoi( args.Argv(1) ) ) : 120;
	g_webGpu.active = 1;
	g_webGpu.frames = 0;
	g_webGpu.pass = -1;
	g_webGpu.disjoint = 0;
	memset( g_webGpu.ms, 0, sizeof( g_webGpu.ms ) );
	common->Printf( "Web GPU: sampling %d frames\n", g_webGpu.remaining );
}

// websurfaces [x1 y1 x2 y2]: for every view of the next rendered frame, list
// the draw surfaces whose scissor overlaps the region (view pixels, origin
// bottom-left; default everything). Diagnostic only; identifies the materials
// behind native/web image differences.
static idScreenRect g_dumpRegion;
static void GLES_Surfaces_f( const idCmdArgs &args ) {
	g_dumpRegion.Clear();
	if ( args.Argc() == 5 ) {
		g_dumpRegion.x1 = atoi( args.Argv(1) ); g_dumpRegion.y1 = atoi( args.Argv(2) );
		g_dumpRegion.x2 = atoi( args.Argv(3) ); g_dumpRegion.y2 = atoi( args.Argv(4) );
	} else {
		g_dumpRegion.x1 = g_dumpRegion.y1 = -32768;
		g_dumpRegion.x2 = g_dumpRegion.y2 = 32767;
	}
	g_dumpSurfaces = 1;
}

void R_GLES_DumpDrawSurfs( const viewDef_t *view ) {
	if ( g_dumpSurfaces != 2 || view == NULL ) return;
	common->Printf( "WEB_SURFACES view %d%s, %d surfaces\n", view->renderView.viewID,
		view->isSubview ? " (subview)" : "", view->numDrawSurfs );
	for ( int i = 0; i < view->numDrawSurfs; i++ ) {
		const drawSurf_t *surf = view->drawSurfs[i];
		const idScreenRect &r = surf->scissorRect;
		if ( r.x2 < g_dumpRegion.x1 || r.x1 > g_dumpRegion.x2 || r.y2 < g_dumpRegion.y1 || r.y1 > g_dumpRegion.y2 ) continue;
		const idRenderEntityLocal *def = surf->space ? surf->space->entityDef : NULL;
		common->Printf( "WEB_SURFACE %d sort %g stages %d coverage %d entity %d model %s material %s scissor %d %d %d %d indexes %d\n",
			i, surf->sort, surf->material ? surf->material->GetNumStages() : 0,
			surf->material ? (int)surf->material->Coverage() : -1, def ? def->index : -1,
			def && def->parms.hModel ? def->parms.hModel->Name() : "-",
			surf->material ? surf->material->GetName() : "-", r.x1, r.y1, r.x2, r.y2,
			surf->geo ? surf->geo->numIndexes : 0 );
	}
}

static GLuint g_boundProgram = 0;
static GLuint g_boundIndexBuffer = 0, g_boundArrayBuffer = 0;
static idCVar r_webDepthOnlyCopy("r_webDepthOnlyCopy", "1", CVAR_RENDERER | CVAR_BOOL,
	"copy only depth (not stencil) for the soft-particle _currentDepth image");
static idCVar r_webStateCache("r_webStateCache", "1", CVAR_RENDERER | CVAR_BOOL,
	"avoid redundant WebGL uniforms, buffer bindings and vertex array state");

// Uniforms belong to a linked program, not to the current ARB id pair.
// A bounded direct-mapped cache needs no allocation or browser query. A
// collision merely causes another upload; all writes pass through here.
struct glesUniformState_t {
	GLuint program;
	GLint location;
	int kind, bytes;
	byte value[256];
};
static glesUniformState_t g_uniformState[512] = {};

static bool GLES_UniformChanged(GLint location, int kind, int bytes, const void *value) {
	if (location < 0) return false;
	if (bytes <= 0 || bytes > 256) return true;
	glesUniformState_t &state = g_uniformState[((unsigned)location + g_boundProgram * 31u) & 511u];
	bool same = state.program == g_boundProgram && state.location == location &&
		state.kind == kind && state.bytes == bytes && !memcmp(state.value, value, bytes);
	if (r_webStateCache.GetBool() && same) return false;
	state.program = g_boundProgram;
	state.location = location;
	state.kind = kind;
	state.bytes = bytes;
	memcpy(state.value, value, bytes);
	if (g_webPerf.remaining) ++g_webPerf.uniformWrites;
	return true;
}

static void GLES_Uniform1i(GLint location, GLint value) {
	if (GLES_UniformChanged(location, 1, sizeof(value), &value)) glUniform1i(location, value);
}
static void GLES_Uniform1f(GLint location, GLfloat value) {
	if (GLES_UniformChanged(location, 2, sizeof(value), &value)) glUniform1f(location, value);
}
static void GLES_Uniform3fv(GLint location, GLsizei count, const GLfloat *value) {
	if (GLES_UniformChanged(location, 3, count * 3 * sizeof(float), value)) glUniform3fv(location, count, value);
}
static void GLES_Uniform4fv(GLint location, GLsizei count, const GLfloat *value) {
	if (GLES_UniformChanged(location, 4, count * 4 * sizeof(float), value)) glUniform4fv(location, count, value);
}
static void GLES_UniformMatrix4fv(GLint location, GLsizei count, GLboolean transpose, const GLfloat *value) {
	if (GLES_UniformChanged(location, 5 + transpose, count * 16 * sizeof(float), value))
		glUniformMatrix4fv(location, count, transpose, value);
}

// Vertex input state. The engine sets client arrays per surface; WebGL
// calls are made at draw time (GLES_SyncVertexState). Static geometry draws
// with a cached vertex array object keyed by its complete layout and element
// buffer, so a draw needs one bindVertexArray instead of a buffer bind and
// five or six attribute writes. Streamed data (frame-temp vertices, CPU
// indices), buffers re-uploaded within the last few frames and
// r_webVertexArrays 0 use the default vertex array, where each attribute is
// written only when it changes.
struct glesAttribState_t {
	bool valid, enabled;
	GLuint buffer;
	GLint size;
	GLenum type;
	GLboolean normalized;
	GLsizei stride;
	const void *pointer;
};
static glesAttribState_t g_attribState[6] = {};		// requested by the engine
static glesAttribState_t g_defaultAttribs[6] = {};	// actual, default vertex array
static GLuint g_defaultElement = 0;					// actual, default vertex array
static GLuint g_actualArrayBuffer = 0;
static GLuint g_currentVao = 0;
static idCVar r_webVertexArrays("r_webVertexArrays", "1", CVAR_RENDERER | CVAR_BOOL,
	"draw static geometry with cached WebGL vertex array objects");

enum { GLES_VAO_KEY_WORDS = 2 + 6 * 4 };
struct glesVaoKey_t {
	GLuint words[GLES_VAO_KEY_WORDS];	// element buffer, enabled mask, then per attribute
	bool operator==( const glesVaoKey_t &other ) const { return !memcmp( words, other.words, sizeof( words ) ); }
};
struct glesVaoKeyHash_t {
	size_t operator()( const glesVaoKey_t &key ) const {
		unsigned int hash = 2166136261u;
		for ( int i = 0; i < GLES_VAO_KEY_WORDS; i++ ) {
			hash = ( hash ^ key.words[i] ) * 16777619u;
		}
		return hash;
	}
};
static std::unordered_map<glesVaoKey_t, GLuint, glesVaoKeyHash_t> g_vaoCache;
// Bumped whenever requested vertex state or a buffer's streaming class
// changes; a draw with an unchanged serial reuses the previous resolution.
static unsigned int g_vertexStateSerial = 1, g_vertexSyncSerial = 0;
static bool g_vertexSyncCpu = false, g_vertexSyncArrays = false;
// Volatile buffers become stable with time alone; re-resolve once per frame.
static unsigned int g_vertexSyncFrame = 0;
static GLuint g_vertexSyncVao = ~0u;
// Per buffer name: last specified with GL_STREAM_DRAW, and the frame of its
// last glBufferData (+1; 0 = never). Live scenes re-specify dynamic buffers
// (shadow volumes, deformed and moving models) every frame at new offsets;
// a vertex array for such data is never drawn again, so creating one per
// draw cost more than it saved (Enpro, live: 27 creates per frame, 22 ms
// CPU, against 11 ms without vertex arrays). Buffers specified within the
// last GLES_STABLE_FRAMES frames use the default vertex array instead.
struct glesBufferInfo_t {
	unsigned char stream;
	unsigned int specifiedFrame;
};
static std::vector<glesBufferInfo_t> g_bufferInfo;
static const unsigned int GLES_STABLE_FRAMES = 3;
static bool GLES_IsVolatileBuffer( GLuint buffer ) {
	if ( buffer >= g_bufferInfo.size() ) return false;
	const glesBufferInfo_t &info = g_bufferInfo[buffer];
	return info.stream || ( info.specifiedFrame && g_glesFrame + 1 - info.specifiedFrame < GLES_STABLE_FRAMES );
}
// Records a glBufferData; a deleted buffer forgets its history.
static void GLES_NoteBufferData( GLuint buffer, bool stream, bool deleted = false ) {
	if ( buffer >= g_bufferInfo.size() ) {
		if ( deleted ) return;
		g_bufferInfo.resize( buffer + 64, glesBufferInfo_t() );
	}
	glesBufferInfo_t &info = g_bufferInfo[buffer];
	if ( info.stream != ( stream ? 1 : 0 ) ) ++g_vertexStateSerial;
	info.stream = stream ? 1 : 0;
	info.specifiedFrame = deleted ? 0 : g_glesFrame + 1;
}
static const size_t GLES_MAX_VAOS = 16384;


static void GLES_AttribEnabled(GLuint index, bool enabled) {
	if (index < 6 && g_attribState[index].enabled != enabled) {
		g_attribState[index].enabled = enabled;
		++g_vertexStateSerial;
	}
}

static void GLES_AttribPointer(GLuint index, GLint size, GLenum type, GLboolean normalized,
	GLsizei stride, const GLvoid *pointer) {
	if (index >= 6) return;
	glesAttribState_t &state = g_attribState[index];
	if (state.valid && state.buffer == g_boundArrayBuffer && state.size == size && state.type == type &&
		state.normalized == normalized && state.stride == stride && state.pointer == pointer) {
		return;
	}
	state.valid = true;
	state.buffer = g_boundArrayBuffer;
	state.size = size;
	state.type = type;
	state.normalized = normalized;
	state.stride = stride;
	state.pointer = pointer;
	++g_vertexStateSerial;
}

static void GLES_UseProgram( GLuint program ) {
	if (g_boundProgram == program) return;
	if (g_webPerf.remaining) ++g_webPerf.programBinds;
	glUseProgram(program);
	g_boundProgram = program;
}

static void GLES_BindArrayBufferNow( GLuint buffer ) {
	if (r_webStateCache.GetBool() && g_actualArrayBuffer == buffer) return;
	glBindBuffer(GL_ARRAY_BUFFER, buffer);
	g_actualArrayBuffer = buffer;
	if (g_webPerf.remaining) ++g_webPerf.bufferBinds;
}

static void GLES_BindVertexArrayNow( GLuint vao ) {
	if (g_currentVao == vao) return;
	glBindVertexArray(vao);
	g_currentVao = vao;
	if (g_webPerf.remaining) ++g_webPerf.vertexArrayBinds;
}

// The element binding belongs to the bound vertex array. Uploads and CPU-index
// draws use the default array, so cached arrays keep the binding in their key.
static void GLES_BindDefaultElementNow( GLuint buffer ) {
	GLES_BindVertexArrayNow(0);
	if (r_webStateCache.GetBool() && g_defaultElement == buffer) return;
	glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, buffer);
	g_defaultElement = buffer;
	if (g_webPerf.remaining) ++g_webPerf.bufferBinds;
}

// Array and element bindings are recorded and applied when an upload or draw
// needs them.
static void APIENTRY GLES_BindBuffer( GLenum target, GLuint buffer ) {
	if (target == GL_ELEMENT_ARRAY_BUFFER) {
		if (g_boundIndexBuffer != buffer) ++g_vertexStateSerial;
		g_boundIndexBuffer = buffer;
	} else if (target == GL_ARRAY_BUFFER) {
		g_boundArrayBuffer = buffer;
	} else {
		glBindBuffer(target, buffer);
		if (g_webPerf.remaining) ++g_webPerf.bufferBinds;
	}
}

static void GLES_SyncUploadTarget( GLenum target ) {
	if (target == GL_ARRAY_BUFFER) GLES_BindArrayBufferNow(g_boundArrayBuffer);
	else if (target == GL_ELEMENT_ARRAY_BUFFER) GLES_BindDefaultElementNow(g_boundIndexBuffer);
}

static void GLES_DeleteVertexArray( GLuint vao ) {
	if (g_currentVao == vao) GLES_BindVertexArrayNow(0);
	glDeleteVertexArrays(1, &vao);
}

static void GLES_ClearVertexArrays( void ) {
	++g_vertexStateSerial;
	for (auto &entry : g_vaoCache) GLES_DeleteVertexArray(entry.second);
	g_vaoCache.clear();
}

static void APIENTRY GLES_DeleteBuffers( GLsizei count, const GLuint *buffers ) {
	++g_vertexStateSerial;
	for (GLsizei i = 0; i < count; ++i) {
		const GLuint buffer = buffers[i];
		if (buffer == g_boundIndexBuffer) g_boundIndexBuffer = 0;
		if (buffer == g_boundArrayBuffer) g_boundArrayBuffer = 0;
		if (buffer == g_actualArrayBuffer) g_actualArrayBuffer = 0;
		// A deleted buffer can stay attached to a vertex array that is not
		// bound; rewrite those bindings before the default array is used.
		if (buffer == g_defaultElement) g_defaultElement = ~0u;
		for (unsigned int j = 0; j < 6; ++j) {
			if (g_attribState[j].buffer == buffer) g_attribState[j].valid = false;
			if (g_defaultAttribs[j].buffer == buffer) g_defaultAttribs[j].valid = false;
		}
		for (auto it = g_vaoCache.begin(); it != g_vaoCache.end();) {
			bool uses = it->first.words[0] == buffer;
			for (int j = 0; j < 6 && !uses; ++j) {
				uses = ( it->first.words[1] & (1u << j) ) && it->first.words[2 + j * 4] == buffer;
			}
			if (uses) {
				GLES_DeleteVertexArray(it->second);
				it = g_vaoCache.erase(it);
			} else {
				++it;
			}
		}
		GLES_NoteBufferData(buffer, false, true);
	}
	glDeleteBuffers(count, buffers);
}

static void APIENTRY GLES_GenBuffers( GLsizei count, GLuint *buffers ) {
	if (g_webPerf.remaining) g_webPerf.bufferCreates += count;
	glGenBuffers(count, buffers);
}

static void APIENTRY GLES_BufferData( GLenum target, GLsizeiptrARB size, const GLvoid *data, GLenum usage ) {
	if (g_webPerf.remaining) {
		++g_webPerf.bufferDataCalls;
		g_webPerf.uploadBytes += (double)size;
	}
	GLES_SyncUploadTarget(target);
	GLuint buffer = target == GL_ELEMENT_ARRAY_BUFFER ? g_boundIndexBuffer : g_boundArrayBuffer;
	GLES_NoteBufferData(buffer, usage == GL_STREAM_DRAW);
	glBufferData(target, (GLsizeiptr)size, data, usage);
}

static void APIENTRY GLES_BufferSubData( GLenum target, GLintptrARB offset, GLsizeiptrARB size, const GLvoid *data ) {
	if (g_webPerf.remaining) {
		++g_webPerf.bufferSubDataCalls;
		g_webPerf.uploadBytes += (double)size;
	}
	GLES_SyncUploadTarget(target);
	glBufferSubData(target, (GLintptr)offset, (GLsizeiptr)size, data);
}

// Apply the requested vertex state before a draw. CPU-index draws bind the
// scratch element buffer themselves through the default vertex array.
static void GLES_SyncVertexState( bool cpuIndices ) {
	const bool cache = r_webStateCache.GetBool();
	// Uploads may have bound the default vertex array since the last draw;
	// only a vertex array this function selected is known to be current.
	const GLuint vao = g_currentVao;
	if (cache && g_vertexSyncSerial == g_vertexStateSerial && g_vertexSyncFrame == g_glesFrame && g_vertexSyncCpu == cpuIndices && vao == g_vertexSyncVao
		&& g_vertexSyncArrays == r_webVertexArrays.GetBool()) {
		if (vao == 0 && !cpuIndices) GLES_BindDefaultElementNow(g_boundIndexBuffer);
		return;
	}
	g_vertexSyncSerial = g_vertexStateSerial;
	g_vertexSyncFrame = g_glesFrame;
	g_vertexSyncCpu = cpuIndices;
	g_vertexSyncArrays = r_webVertexArrays.GetBool();
	bool cached = cache && r_webVertexArrays.GetBool() && !cpuIndices
		&& !GLES_IsVolatileBuffer(g_boundIndexBuffer);
	glesVaoKey_t key;
	if (cached) {
		memset(&key, 0, sizeof(key));
		key.words[0] = g_boundIndexBuffer;
		for (int i = 0; i < 6; ++i) {
			const glesAttribState_t &want = g_attribState[i];
			if (!want.enabled) continue;
			if (!want.valid || !want.buffer || GLES_IsVolatileBuffer(want.buffer)) {
				cached = false;
				break;
			}
			key.words[1] |= 1u << i;
			key.words[2 + i * 4] = want.buffer;
			key.words[3 + i * 4] = (GLuint)want.size | ( (GLuint)want.normalized << 4 ) | ( (GLuint)want.type << 8 );
			key.words[4 + i * 4] = (GLuint)want.stride;
			key.words[5 + i * 4] = (GLuint)(uintptr_t)want.pointer;
		}
	}
	if (cached) {
		auto found = g_vaoCache.find(key);
		if (found != g_vaoCache.end()) {
			GLES_BindVertexArrayNow(found->second);
			g_vertexSyncVao = g_currentVao;
			return;
		}
		if (g_vaoCache.size() >= GLES_MAX_VAOS) GLES_ClearVertexArrays();
		GLuint vao = 0;
		glGenVertexArrays(1, &vao);
		GLES_BindVertexArrayNow(vao);
		for (int i = 0; i < 6; ++i) {
			if (!( key.words[1] & (1u << i) )) continue;
			const glesAttribState_t &want = g_attribState[i];
			GLES_BindArrayBufferNow(want.buffer);
			glVertexAttribPointer(i, want.size, want.type, want.normalized, want.stride, want.pointer);
			glEnableVertexAttribArray(i);
			if (g_webPerf.remaining) g_webPerf.attribWrites += 2;
		}
		if (g_boundIndexBuffer) glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, g_boundIndexBuffer);
		g_vaoCache[key] = vao;
		if (g_webPerf.remaining) ++g_webPerf.vertexArrayCreates;
		g_vertexSyncVao = g_currentVao;
		return;
	}
	GLES_BindVertexArrayNow(0);
	for (int i = 0; i < 6; ++i) {
		const glesAttribState_t &want = g_attribState[i];
		glesAttribState_t &have = g_defaultAttribs[i];
		if (want.enabled && want.valid) {
			bool same = have.valid && have.buffer == want.buffer && have.size == want.size && have.type == want.type &&
				have.normalized == want.normalized && have.stride == want.stride && have.pointer == want.pointer;
			if (!cache || !same) {
				GLES_BindArrayBufferNow(want.buffer);
				glVertexAttribPointer(i, want.size, want.type, want.normalized, want.stride, want.pointer);
				bool enabled = have.enabled;
				have = want;
				have.enabled = enabled;
				if (g_webPerf.remaining) ++g_webPerf.attribWrites;
			}
		}
		if (!cache || have.enabled != want.enabled) {
			if (want.enabled) glEnableVertexAttribArray(i);
			else glDisableVertexAttribArray(i);
			have.enabled = want.enabled;
			if (g_webPerf.remaining) ++g_webPerf.attribWrites;
		}
	}
	if (!cpuIndices) GLES_BindDefaultElementNow(g_boundIndexBuffer);
	g_vertexSyncVao = g_currentVao;
}

// Interaction setup selects each of five texture units per surface, but many
// selections are followed by a bind the engine skips as redundant. Only
// texture-object calls depend on the selected unit, so record the request
// and send it before the next such call (GLES_SyncActiveTexture).
static GLenum g_activeTexture = GL_TEXTURE0, g_wantedActiveTexture = GL_TEXTURE0;
static void GLES_SyncActiveTexture( void ) {
	if (g_activeTexture == g_wantedActiveTexture) return;
	g_activeTexture = g_wantedActiveTexture;
	if (g_webPerf.remaining) ++g_webPerf.activeTextureCalls;
	glActiveTexture(g_activeTexture);
}
static void APIENTRY GLES_ActiveTexture( GLenum texture ) {
	g_wantedActiveTexture = texture;
	if (!r_webStateCache.GetBool()) {
		// Comparison mode: select immediately, as the desktop path does.
		g_activeTexture = 0;
		GLES_SyncActiveTexture();
	}
}
static void APIENTRY GLES_TexParameteri( GLenum target, GLenum pname, GLint param ) {
	GLES_SyncActiveTexture();
	glTexParameteri(target, pname, param);
}
static void APIENTRY GLES_TexSubImage2D( GLenum target, GLint level, GLint x, GLint y, GLsizei width, GLsizei height,
	GLenum format, GLenum type, const GLvoid *pixels ) {
	GLES_SyncActiveTexture();
	glTexSubImage2D(target, level, x, y, width, height, format, type, pixels);
}
static void APIENTRY GLES_TexImage3D( GLenum target, GLint level, GLint internalFormat, GLsizei width, GLsizei height,
	GLsizei depth, GLint border, GLenum format, GLenum type, const GLvoid *pixels ) {
	GLES_SyncActiveTexture();
	glTexImage3D(target, level, internalFormat, width, height, depth, border, format, type, pixels);
}
static void APIENTRY GLES_CompressedTexImage2D( GLenum target, GLint level, GLenum internalFormat, GLsizei width,
	GLsizei height, GLint border, GLsizei imageSize, const GLvoid *data ) {
	GLES_SyncActiveTexture();
	glCompressedTexImage2D(target, level, internalFormat, width, height, border, imageSize, data);
}
static void APIENTRY GLES_CopyTexImage2D( GLenum target, GLint level, GLenum internalFormat, GLint x, GLint y,
	GLsizei width, GLsizei height, GLint border ) {
	GLES_SyncActiveTexture();
	glCopyTexImage2D(target, level, internalFormat, x, y, width, height, border);
}
// State queries may read the active unit or its bindings.
static void APIENTRY GLES_GetIntegerv( GLenum pname, GLint *params ) {
	GLES_SyncActiveTexture();
	glGetIntegerv(pname, params);
}
static void APIENTRY GLES_GetFloatv( GLenum pname, GLfloat *params ) {
	GLES_SyncActiveTexture();
	glGetFloatv(pname, params);
}
static void APIENTRY GLES_GetBooleanv( GLenum pname, GLboolean *params ) {
	GLES_SyncActiveTexture();
	glGetBooleanv(pname, params);
}

// Shadow volumes set both stencil faces before every draw; consecutive
// volumes usually repeat them. Index 0 is GL_FRONT, 1 is GL_BACK. The
// cache starts from a new context's documented defaults.
static GLenum g_stencilOps[2][3];
static GLint g_stencilRef;
static GLenum g_stencilFuncState;
static GLuint g_stencilMaskState;
static void GLES_ResetStencilState( void ) {
	for (int face = 0; face < 2; ++face)
		g_stencilOps[face][0] = g_stencilOps[face][1] = g_stencilOps[face][2] = GL_KEEP;
	g_stencilFuncState = GL_ALWAYS;
	g_stencilRef = 0;
	g_stencilMaskState = ~0u;
}
static bool GLES_StencilOpsChanged( int first, int last, GLenum fail, GLenum zfail, GLenum zpass ) {
	bool same = true;
	for (int face = first; face <= last; ++face) {
		same = same && g_stencilOps[face][0] == fail && g_stencilOps[face][1] == zfail && g_stencilOps[face][2] == zpass;
		g_stencilOps[face][0] = fail;
		g_stencilOps[face][1] = zfail;
		g_stencilOps[face][2] = zpass;
	}
	if (r_webStateCache.GetBool() && same) return false;
	if (g_webPerf.remaining) ++g_webPerf.stencilCalls;
	return true;
}
static void APIENTRY GLES_StencilOp( GLenum fail, GLenum zfail, GLenum zpass ) {
	if (GLES_StencilOpsChanged(0, 1, fail, zfail, zpass)) glStencilOp(fail, zfail, zpass);
}
static void APIENTRY GLES_StencilOpSeparate( GLenum face, GLenum fail, GLenum zfail, GLenum zpass ) {
	int first = face == GL_BACK ? 1 : 0, last = face == GL_FRONT ? 0 : 1;
	if (GLES_StencilOpsChanged(first, last, fail, zfail, zpass)) glStencilOpSeparate(face, fail, zfail, zpass);
}
static void APIENTRY GLES_StencilFunc( GLenum func, GLint ref, GLuint mask ) {
	bool same = g_stencilFuncState == func && g_stencilRef == ref && g_stencilMaskState == mask;
	g_stencilFuncState = func;
	g_stencilRef = ref;
	g_stencilMaskState = mask;
	if (r_webStateCache.GetBool() && same) return;
	if (g_webPerf.remaining) ++g_webPerf.stencilCalls;
	glStencilFunc(func, ref, mask);
}

// WebAssembly checks indirect-call signatures. Casting one void(void) stub
// to every GL signature traps; assignment deduces a matching callback here.
template<typename Return, typename... Args>
static Return APIENTRY GLES_NopTyped(Args...) { return Return(); }

// ---------------------------------------------------------------------------
// Cached ARB env parameters (slots mirror program.env[] indices, see
// tr_local.h PP_* — e.g. PP_LIGHT_ORIGIN=4 .. PP_COLOR_ADD=17, GAMMA=21).
// ---------------------------------------------------------------------------
static float g_glesEnvVertex[32][4];
static float g_glesEnvFragment[32][4];

// ---------------------------------------------------------------------------
// Texgen mirror (OBJECT_PLANE only — the only mode Doom 3 uses; see
// RB_PrepareStageTexturing, RB_T_BlendLight, RB_T_BasicFog). Fixed-function
// texgen doesn't exist in GLES3, so the flat program computes the same
// dot-products in-shader. Enables apply to the current texture unit at call
// time, exactly like fixed-function state.
// ---------------------------------------------------------------------------
#define GLES_MAX_TEXGEN_UNITS 8
static float g_genPlane[GLES_MAX_TEXGEN_UNITS][4][4]; // unit, coord S/T/R/Q, plane
static bool g_genEn[GLES_MAX_TEXGEN_UNITS][4];

// Per-unit texture target tracking (via qglBindTexture override): lets
// draw-time sync spot cube-map draws (skybox, diffuse cubes) while the flat
// program is bound.
static GLenum g_unitTarget[GLES_MAX_TEXGEN_UNITS] = { GL_TEXTURE_2D, GL_TEXTURE_2D,
	GL_TEXTURE_2D, GL_TEXTURE_2D, GL_TEXTURE_2D, GL_TEXTURE_2D, GL_TEXTURE_2D, GL_TEXTURE_2D };
static GLuint g_unitId[GLES_MAX_TEXGEN_UNITS] = { 0, 0, 0, 0, 0, 0, 0, 0 };

// Set while inside RB_ARB2_CreateDrawInteractions (draw_arb2.cpp) so draws
// with a stale interaction binding elsewhere can be demoted to flat.
// The caller owns this scope. Binding the two ARB programs is not atomic:
// the first bind may briefly pair an interaction vertex program with the
// preceding particle/ambient fragment program. That intermediate selection
// must not clear the mark before the matching fragment program is bound.
static int g_inInteraction = 0;

void R_GLES_MarkInteraction( int on ) {
	g_inInteraction = on ? 1 : 0;
}

static int GLES_TexgenCoordIndex( GLenum coord ) {
	if ( coord == (GLenum)GL_S ) return 0;
	if ( coord == (GLenum)GL_T ) return 1;
	if ( coord == (GLenum)GL_R ) return 2;
	if ( coord == (GLenum)GL_Q ) return 3;
	return -1;
}

static int GLES_TexgenCapIndex( GLenum cap ) {
	if ( cap == (GLenum)GL_TEXTURE_GEN_S ) return 0;
	if ( cap == (GLenum)GL_TEXTURE_GEN_T ) return 1;
	if ( cap == (GLenum)GL_TEXTURE_GEN_R ) return 2;
	if ( cap == (GLenum)GL_TEXTURE_GEN_Q ) return 3;
	return -1;
}

static bool GLES_TexgenActive( void ) {
	for ( int u = 0; u < GLES_MAX_TEXGEN_UNITS; u++ ) {
		for ( int c = 0; c < 4; c++ ) {
			if ( g_genEn[u][c] ) {
				return true;
			}
		}
	}
	return false;
}

// ---------------------------------------------------------------------------
// Matrix-stack mirror (column-major, like GL). The engine drives the world
// through qglLoadMatrixf per surface (tr_render.cpp) and ortho projections
// for 2D; mirroring gives every shader a correct u_mvp without touching the
// shared frontend code.
// ---------------------------------------------------------------------------
#define GLES_MSTACK_DEPTH 8
static GLenum g_glesMode = GL_MODELVIEW;
static float g_mProj[16], g_mMV[16], g_mTex[16];
static float g_mProjStack[GLES_MSTACK_DEPTH][16];
static float g_mMVStack[GLES_MSTACK_DEPTH][16];
static float g_mTexStack[GLES_MSTACK_DEPTH][16];
static int g_mProjDepth = 0, g_mMVDepth = 0, g_mTexDepth = 0;

static float *GLES_CurMatrix( void ) {
	if ( g_glesMode == GL_PROJECTION ) {
		return g_mProj;
	} else if ( g_glesMode == GL_TEXTURE ) {
		return g_mTex;
	}
	return g_mMV;
}

static void GLES_MatIdentity( float *m ) {
	for ( int i = 0; i < 16; i++ ) {
		m[i] = ( i % 5 == 0 ) ? 1.0f : 0.0f;
	}
}

// out = a * b (column-major)
static void GLES_MatMul( float *out, const float *a, const float *b ) {
	float t[16];
	for ( int c = 0; c < 4; c++ ) {
		for ( int r = 0; r < 4; r++ ) {
			t[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1]
			             + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
		}
	}
	for ( int i = 0; i < 16; i++ ) {
		out[i] = t[i];
	}
}

// ---------------------------------------------------------------------------
// GLSL programs
// ---------------------------------------------------------------------------
typedef struct {
	GLuint prog;
	GLint mvp, shadowExtrude;
	GLint lOrigin, vOrigin;
	GLint interEnv; // interaction: vertex program.env[4..17] as one array
	GLint diffCol, specCol;
	GLint gamma, alphaTest, flatColor, useVtx, inverseVtx, textureMatrix, secondTexgen;
	GLint tex[7]; // sampler locations for units 0..6 (interaction)
	GLint tex0;   // flat/shadow diffuse sampler
	GLint tex1;   // flat texgen second sampler (unit 1)
	GLint texgenMode; // flat: 0 off, 1 two-unit, 2 projective
	GLint genP0, genM0, genP1, genM1; // flat texgen planes/masks
	GLint eyeLocal, modelR0, modelR1, modelR2; // environment programs
	GLint cubeMap, bumpMap; // environment programs
	GLint stageTex, scratchTex, scratchTex2; // glasswarp program
	GLint depthRecip, partRadius, chanMask; // soft-particle program (env 22/23/24)
	GLint softDiff, softDepth; // soft-particle samplers (units 0/1)
	GLint skyCube; // sky program sampler (unit 0)
	GLint heat[7]; // modelview, projection, scroll, deform, screen scale/reciprocal, mode
	GLint colorFraction, colorTarget, screenScale, screenRecip;
} glesProg_t;

static glesProg_t g_progInteraction = {};
static glesProg_t g_progShadow = {};
static glesProg_t g_progFlat = {};
static glesProg_t g_progEnv = {};
static glesProg_t g_progBumpyEnv = {};
static glesProg_t g_progGlass = {};
static glesProg_t g_progSoft = {};
static glesProg_t g_progSky = {};
static glesProg_t g_progHeat = {};
static glesProg_t g_progColorProcess = {};
static int g_heatModes[1024] = {};
// Image name for a texture object (diagnostics only; linear search).
static const char *GLES_ImageName( GLuint texnum ) {
	for ( int i = 0; i < globalImages->images.Num(); i++ ) {
		if ( globalImages->images[i]->texnum == texnum ) return globalImages->images[i]->imgName.c_str();
	}
	return "?";
}

static bool g_colorProcessIds[1024] = {};
static float g_vertexLocal[32][4] = {};
static glesProg_t *g_curProg = NULL;
static bool g_vertexProgramEnabled = false, g_fragmentProgramEnabled = false;
static bool g_cpuShadowVertices = false;
static bool g_shadowExtrude = false;
static int g_lastVid = -1, g_lastFid = -1;

// fixed-function state mirrored into uniforms
static float g_flatColor[4] = { 1, 1, 1, 1 };
static float g_useVtxColor = 0.0f;
static float g_inverseVtxColor = 0.0f;
static bool g_alphaEnabled = false;
static float g_alphaRef = 0.5f;
static GLenum g_alphaFunc = GL_ALWAYS;

// vertex-shader header shared by all programs
static const char *GLES_VS_HEAD =
	"#version 300 es\n"
	"layout(location=0) in vec4 a_pos;\n"
	"layout(location=1) in vec3 a_tc;\n"
	"layout(location=2) in vec4 a_col;\n"
	"layout(location=3) in vec3 a_nrm;\n"
	"layout(location=4) in vec3 a_tan0;\n"
	"layout(location=5) in vec3 a_tan1;\n"
	"uniform mat4 u_mvp;\n";

static const char *GLES_FS_HEAD =
	"#version 300 es\n"
	"precision highp float;\n"
	// Match the desktop ARB gamma injection's MUL_SAT before POW.
	"vec3 gammaCorrect(vec3 color, vec4 gamma) {\n"
	"  return pow(clamp(color * gamma.rgb, 0.0, 1.0), vec3(gamma.a));\n"
	"}\n"
	"uniform vec3 u_alphaTest;\n"
	"bool alphaPass(float a) {\n"
	"  if(u_alphaTest.x < 0.5) return true; int f=int(u_alphaTest.z); float r=u_alphaTest.y;\n"
	"  if(f==512) return false; if(f==513) return a<r; if(f==514) return a==r;\n"
	"  if(f==515) return a<=r; if(f==516) return a>r; if(f==517) return a!=r;\n"
	"  if(f==518) return a>=r; return true; }\n";

static GLuint GLES_CompileShader( GLenum type, const char *src ) {
	GLuint sh = glCreateShader( type );
	glShaderSource( sh, 1, &src, NULL );
	glCompileShader( sh );
	GLint ok = 0;
	glGetShaderiv( sh, GL_COMPILE_STATUS, &ok );
	if ( !ok ) {
		char log[1024];
		glGetShaderInfoLog( sh, sizeof( log ), NULL, log );
		common->Printf( "WebGL: shader compile failed: %s\n", log );
		glDeleteShader( sh );
		return 0;
	}
	return sh;
}

static GLuint GLES_LinkProgram( const char *vsSrc, const char *fsSrc ) {
	GLuint vsh = GLES_CompileShader( GL_VERTEX_SHADER, vsSrc );
	GLuint fsh = GLES_CompileShader( GL_FRAGMENT_SHADER, fsSrc );
	if ( vsh == 0 || fsh == 0 ) {
		if ( vsh ) glDeleteShader( vsh );
		if ( fsh ) glDeleteShader( fsh );
		return 0;
	}
	GLuint prog = glCreateProgram();
	glAttachShader( prog, vsh );
	glAttachShader( prog, fsh );
	glLinkProgram( prog );
	glDeleteShader( vsh );
	glDeleteShader( fsh );
	GLint ok = 0;
	glGetProgramiv( prog, GL_LINK_STATUS, &ok );
	if ( !ok ) {
		char log[1024];
		glGetProgramInfoLog( prog, sizeof( log ), NULL, log );
		common->Printf( "WebGL: program link failed: %s\n", log );
		glDeleteProgram( prog );
		return 0;
	}
	return prog;
}

static void GLES_FetchCommon( glesProg_t *p ) {
	p->mvp = glGetUniformLocation( p->prog, "u_mvp" );
	p->gamma = glGetUniformLocation( p->prog, "u_gamma" );
	p->alphaTest = glGetUniformLocation( p->prog, "u_alphaTest" );
	p->flatColor = glGetUniformLocation( p->prog, "u_flatColor" );
	p->useVtx = glGetUniformLocation( p->prog, "u_useVtx" );
	p->inverseVtx = glGetUniformLocation( p->prog, "u_inverseVtx" );
	p->textureMatrix = glGetUniformLocation( p->prog, "u_textureMatrix" );
	p->secondTexgen = glGetUniformLocation( p->prog, "u_secondTexgen" );
}

// Blinn-Phong interaction vertex shader. Same inputs as interaction.vfp:
// local-space position/normal/tangents, per-stage texgen matrices in u_*S/T
// (uv' = dot(vec4(uv,0,1), row)), tangent-space light/view vectors.
// The engine's vertex program.env[4..17] arrive as one array, uploaded with a
// single call per draw that changed any of them (GLES_FlushInteractionEnv).
static const char *GLES_VS_INTERACTION =
	"uniform vec4 u_ienv[14];\n"
	"#define u_lOrigin u_ienv[0]\n"    // PP_LIGHT_ORIGIN (4), .w unused
	"#define u_vOrigin u_ienv[1]\n"    // PP_VIEW_ORIGIN (5)
	"#define u_projS u_ienv[2]\n"      // PP_LIGHT_PROJECT_S (6)
	"#define u_projT u_ienv[3]\n"      // (7)
	"#define u_projQ u_ienv[4]\n"      // (8)
	"#define u_fallS u_ienv[5]\n"      // PP_LIGHT_FALLOFF_S (9)
	"#define u_bumpS u_ienv[6]\n"      // (10)
	"#define u_bumpT u_ienv[7]\n"      // (11)
	"#define u_diffS u_ienv[8]\n"      // (12)
	"#define u_diffT u_ienv[9]\n"      // (13)
	"#define u_specS u_ienv[10]\n"     // (14)
	"#define u_specT u_ienv[11]\n"     // (15)
	"#define u_colorMod u_ienv[12]\n"  // PP_COLOR_MODULATE (16)
	"#define u_colorAdd u_ienv[13]\n"  // PP_COLOR_ADD (17)
	"out vec2 v_bump;\n"
	"out vec2 v_diff;\n"
	"out vec2 v_spec;\n"
	"out vec4 v_lproj;\n" // xyz = projected stq, w = falloff coord
	"out vec3 v_L;\n"
	"out vec3 v_H;\n"
	"out vec4 v_col;\n"
	"void main() {\n"
	"  vec3 pos = a_pos.xyz;\n"
	"  vec4 tc4 = vec4( a_tc.xy, 0.0, 1.0 );\n"
	"  v_bump = vec2( dot( tc4, u_bumpS ), dot( tc4, u_bumpT ) );\n"
	"  v_diff = vec2( dot( tc4, u_diffS ), dot( tc4, u_diffT ) );\n"
	"  v_spec = vec2( dot( tc4, u_specS ), dot( tc4, u_specT ) );\n"
	"  vec4 p4 = vec4( pos, 1.0 );\n"
	"  v_lproj = vec4( dot( p4, u_projS ), dot( p4, u_projT ), dot( p4, u_projQ ), dot( p4, u_fallS ) );\n"
	"  vec3 L = u_lOrigin.xyz - pos;\n"
	"  vec3 V = u_vOrigin.xyz - pos;\n"
	"  v_L = vec3( dot( L, a_tan0 ), dot( L, a_tan1 ), dot( L, a_nrm ) );\n"
	"  vec3 H = normalize(L) + normalize(V);\n"
	"  v_H = vec3( dot( H, a_tan0 ), dot( H, a_tan1 ), dot( H, a_nrm ) );\n"
	"  v_col = a_col * u_colorMod + u_colorAdd;\n"
	"  gl_Position = u_mvp * vec4( pos, 1.0 );\n"
	"}\n";

// Blinn-Phong interaction fragment shader. Texture units match the engine
// bindings in RB_ARB2_DrawInteraction: 1 bump, 2 falloff, 3 projection,
// 4 diffuse, 5 specular, 6 specular table; unit 0 normalizes light vectors.
static const char *GLES_FS_INTERACTION =
	"uniform samplerCube u_cube;\n"   // unit 0: native normalization lookup
	"uniform sampler2D u_bump;\n"   // unit 1
	"uniform sampler2D u_fall;\n"   // unit 2
	"uniform sampler2D u_proj;\n"   // unit 3
	"uniform sampler2D u_diff;\n"   // unit 4
	"uniform sampler2D u_spec;\n"   // unit 5
	"uniform sampler2D u_spectab;\n" // unit 6, engine-generated specular response
	"uniform vec4 u_diffCol;\n"  // fragment program.env[0]
	"uniform vec4 u_specCol;\n"  // fragment program.env[1]
	"uniform vec4 u_gamma;\n"    // rgb = brightness, a = 1/gamma
	"in vec2 v_bump;\n"
	"in vec2 v_diff;\n"
	"in vec2 v_spec;\n"
	"in vec4 v_lproj;\n"
	"in vec3 v_L;\n"
	"in vec3 v_H;\n"
	"in vec4 v_col;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec3 N = texture( u_bump, v_bump ).agb * 2.0 - 1.0;\n"
	"  vec3 L = texture( u_cube, v_L ).rgb * 2.0 - 1.0;\n"
	"  vec3 H = normalize( v_H );\n"
	// interaction.vfp multiplies by the whole falloff texel, not only red.
	"  vec3 fall = texture( u_fall, vec2( v_lproj.w, 0.5 ) ).rgb;\n"
	"  vec3 light = textureProj( u_proj, vec3( v_lproj.xyz ) ).rgb * fall;\n"
	"  vec4 diff = texture( u_diff, v_diff );\n"
	"  vec4 spec = texture( u_spec, v_spec );\n"
	"  float ndl = max( dot( N, L ), 0.0 );\n"
	"  float ndh = max( dot( N, H ), 0.0 );\n"
	"  float response = texture( u_spectab, vec2(ndh, 0.5) ).r;\n"
	"  vec3 col = (diff.rgb * u_diffCol.rgb\n"
	"           + 2.0 * spec.rgb * u_specCol.rgb * response) * ndl * light;\n"
	"  col *= v_col.rgb;\n"
	"  col = gammaCorrect(col, u_gamma);\n"
	"  if (!alphaPass(diff.a)) { discard; }\n"
	"  o_col = vec4( col, diff.a );\n"
	"}\n";

// Shared shadow vertices store both near (w=1) and infinite (w=0) copies
// of the surface position. Match shadow.vp's projection away from the light.
// Private/precomputed volumes already contain projected positions.
static const char *GLES_VS_SHADOW =
	"uniform vec4 u_lOrigin;\n"
	"uniform float u_shadowExtrude;\n"
	"void main() {\n"
	"  vec4 pos = a_pos;\n"
	"  pos.xyz -= u_shadowExtrude * (1.0 - pos.w) * u_lOrigin.xyz;\n"
	"  gl_Position = u_mvp * pos;\n"
	"}\n";
static const char *GLES_FS_SHADOW =
	"out vec4 o_col;\n"
	"void main() { o_col = vec4( 0.0 ); }\n";

// Flat program: old-style ambient stages, 2D, and any fixed-function draws.
// Doubles as the texgen program (fog, blend lights, projected/screen
// textures): when texgen is enabled the same OBJECT_PLANE dot-products the
// fixed pipeline would compute are evaluated in-shader (see g_genPlane).
static const char *GLES_VS_FLAT =
	"uniform mat4 u_textureMatrix;\n"
	"uniform vec4 u_genP0[4];\n" // unit 0 texgen planes S/T/R/Q
	"uniform vec4 u_genM0;\n"   // unit 0 enable mask
	"uniform vec4 u_genP1[4];\n" // unit 1 texgen planes
	"uniform vec4 u_genM1;\n"   // unit 1 enable mask
	"out vec2 v_tc;\n"
	"out vec4 v_col;\n"
	"out vec4 v_gen0;\n"
	"out vec4 v_gen1;\n"
	"void main() {\n"
	"  v_tc = (u_textureMatrix * vec4(a_tc.xy, 0.0, 1.0)).xy; v_col = a_col;\n"
	"  vec4 p4 = vec4( a_pos.xyz, 1.0 );\n"
	"  vec4 g0 = vec4( dot( p4, u_genP0[0] ), dot( p4, u_genP0[1] ),\n"
	"                    dot( p4, u_genP0[2] ), dot( p4, u_genP0[3] ) );\n"
	"  vec4 g1 = vec4( dot( p4, u_genP1[0] ), dot( p4, u_genP1[1] ),\n"
	"                    dot( p4, u_genP1[2] ), dot( p4, u_genP1[3] ) );\n"
	"  v_gen0 = u_textureMatrix * mix( vec4( 0.0, 0.0, 0.0, 1.0 ), g0, u_genM0 );\n"
	"  v_gen1 = mix( vec4( 0.0, 0.0, 0.0, 1.0 ), g1, u_genM1 );\n"
	"  gl_Position = u_mvp * a_pos;\n"
	"}\n";
static const char *GLES_FS_FLAT =
	"uniform float u_secondTexgen;\n"
	"uniform sampler2D u_tex0;\n"  // unit 0
	"uniform sampler2D u_tex1;\n"  // unit 1 (texgen second stage)
	"uniform vec4 u_gamma;\n"
	"uniform vec4 u_flatColor;\n"
	"uniform float u_useVtx;\n"
	"uniform float u_inverseVtx;\n"
	"uniform float u_texgenMode;\n" // 0 off, 1 two-unit, 2 projective
	"in vec2 v_tc;\n"
	"in vec4 v_col;\n"
	"in vec4 v_gen0;\n"
	"in vec4 v_gen1;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec4 vertexColor = vec4(mix(v_col.rgb, 1.0-v_col.rgb, u_inverseVtx), v_col.a);\n"
	// Fixed-function current and texture-environment colors are clamped to
	// [0,1]; overbright material stages (rgb 5) rely on that saturation.
	"  vec4 vc = mix( vec4( 1.0 ), vertexColor, u_useVtx ) * clamp( u_flatColor, 0.0, 1.0 );\n"
	"  vec4 c;\n"
	"  if ( u_texgenMode < 0.5 ) {\n"
	"    c = texture( u_tex0, v_tc ) * vc;\n"
	"  } else if ( u_texgenMode < 1.5 ) {\n"
	"    c = texture( u_tex0, v_gen0.st ) * texture( u_tex1, v_gen1.st ) * vc;\n"
	"  } else {\n"
	// Fixed-function MODULATE on both units: blend lights keep projected
	// and falloff alpha as well as their color (RB_BlendLight).
	"    vec4 proj = textureProj( u_tex0, vec3(v_gen0.xy, v_gen0.w) );\n"
	"    vec4 fall = u_secondTexgen > 0.5 ? texture( u_tex1, vec2( v_gen1.s, 0.5 ) ) : vec4( 1.0 );\n"
	"    c = proj * fall * vc;\n"
	"  }\n"
	"  c.rgb = gammaCorrect(c.rgb, u_gamma);\n"
	"  if (!alphaPass(c.a)) { discard; }\n"
	"  o_col = c;\n"
	"}\n";

// Stock environment.vfp interpolates the unnormalized local normal and
// eye vector, then computes reflection per fragment. Reflecting at vertices
// changes the sampled cube face across large triangles and moving views.
static const char *GLES_VS_ENV =
	"uniform vec4 u_eyeLocal;\n"  // vertex program.env[5]
	"out vec3 v_normal, v_eye;\n"
	"out vec4 v_col;\n"
	"void main() {\n"
	"  v_normal = a_nrm; v_eye = u_eyeLocal.xyz - a_pos.xyz;\n"
	"  v_col = a_col;\n"
	"  gl_Position = u_mvp * a_pos;\n"
	"}\n";
static const char *GLES_FS_ENV =
	"uniform samplerCube u_cube;\n" // unit 0
	"uniform vec4 u_gamma;\n"
	"uniform vec4 u_flatColor; uniform float u_useVtx;\n"
	"in vec3 v_normal, v_eye;\n"
	"in vec4 v_col;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	// ARB vertex.color is the current GL color when the color array is off.
	// A disabled WebGL attribute otherwise defaults to black, hiding glass.
	"  vec4 color = mix(clamp(u_flatColor, 0.0, 1.0), v_col, u_useVtx);\n"
	"  vec4 sampleColor = texture( u_cube, reflect(-normalize(v_eye), normalize(v_normal)) ) * color;\n"
	"  vec3 c = sampleColor.rgb;\n"
	"  c = gammaCorrect(c, u_gamma);\n"
	"  if (!alphaPass(sampleColor.a)) { discard; }\n"
	"  o_col = vec4( c, sampleColor.a );\n"
	"}\n";

// Stock colorProcess.vfp blends the captured screen toward a tinted mean
// intensity. Screen coordinates include the padded render texture scale;
// stage UVs and vertex colors do not participate in this effect.
static const char *GLES_VS_COLORPROCESS =
	"void main() { gl_Position = u_mvp * a_pos; }\n";
static const char *GLES_FS_COLORPROCESS =
	"uniform sampler2D u_screen;\n"
	"uniform vec4 u_colorFraction, u_colorTarget, u_screenScale, u_screenRecip, u_gamma;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec3 src = texture(u_screen, gl_FragCoord.xy * u_screenRecip.xy * u_screenScale.xy).rgb;\n"
	"  float grey = (src.r + src.g + src.b) * 0.33;\n"
	"  vec3 c = src * (vec3(1.0) - u_colorFraction.rgb) + grey * u_colorTarget.rgb * u_colorFraction.rgb;\n"
	"  c = gammaCorrect(c, u_gamma);\n"
	"  if (!alphaPass(1.0)) discard;\n"
	"  o_col = vec4(c, 1.0);\n"
	"}\n";

// Bumpy environment (TG_REFLECT_CUBE with bump map on unit 1): perturb the
// local normal with the bump texel per-pixel, then reflect in world space.
static const char *GLES_VS_BUMPYENV =
	"out vec3 v_posL;\n"
	"out vec3 v_nrmL;\n"
	"out vec3 v_t0L;\n"
	"out vec3 v_t1L;\n"
	"out vec2 v_bumpTC;\n"
	"out vec4 v_col;\n"
	"void main() {\n"
	"  v_posL = a_pos.xyz; v_nrmL = a_nrm;\n"
	"  v_t0L = a_tan0; v_t1L = a_tan1;\n"
	"  v_bumpTC = a_tc.xy; v_col = a_col;\n"
	"  gl_Position = u_mvp * a_pos;\n"
	"}\n";
static const char *GLES_FS_BUMPYENV =
	"uniform samplerCube u_cube;\n" // unit 0
	"uniform sampler2D u_bump;\n"   // unit 1
	"uniform vec4 u_eyeLocal;\n"
	"uniform vec4 u_modelR0;\n"
	"uniform vec4 u_modelR1;\n"
	"uniform vec4 u_modelR2;\n"
	"uniform vec4 u_gamma;\n"
	"in vec3 v_posL;\n"
	"in vec3 v_nrmL;\n"
	"in vec3 v_t0L;\n"
	"in vec3 v_t1L;\n"
	"in vec2 v_bumpTC;\n"
	"in vec4 v_col;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec3 b = normalize(texture( u_bump, v_bumpTC ).agb * 2.0 - 1.0);\n"
	// Stock bumpyEnvironment normalizes the sampled bump vector, but does
	// not renormalize its interpolated tangent/model transform afterward.
	"  vec3 nL = b.z * v_nrmL + b.x * v_t0L + b.y * v_t1L;\n"
	"  vec3 nW = vec3( dot( nL, u_modelR0.xyz ),\n"
	"                                 dot( nL, u_modelR1.xyz ),\n"
	"                                 dot( nL, u_modelR2.xyz ) );\n"
	"  vec3 vL = u_eyeLocal.xyz - v_posL;\n"
	"  vec3 vW = normalize( vec3( dot( vL, u_modelR0.xyz ),\n"
	"                                 dot( vL, u_modelR1.xyz ),\n"
	"                                 dot( vL, u_modelR2.xyz ) ) );\n"
	"  vec3 c = texture( u_cube, reflect( -vW, nW ) ).rgb;\n"
	"  c = gammaCorrect(c, u_gamma);\n"
	"  if (!alphaPass(v_col.a)) { discard; }\n"
	"  o_col = vec4( c, v_col.a );\n"
	"}\n";

// Soft particles: faithful GLSL port of the engine-embedded ARB programs
// (draw_arb2.cpp softpartVShader/softpartFShader, from TheDarkMod 2.04).
// Depth recovery constants are Doom 3 projection-specific (see the ARB
// comments); like the original, no gamma is applied (nodhewm3gammahack).
static const char *GLES_VS_SOFT =
	"out vec2 v_tc;\n"
	"out vec4 v_col;\n"
	"void main() {\n"
	"  v_tc = a_tc.xy; v_col = a_col;\n"
	"  gl_Position = u_mvp * a_pos;\n"
	"}\n";
static const char *GLES_FS_SOFT =
	"uniform sampler2D u_diff;\n"   // unit 0: particle image
	"uniform sampler2D u_depth;\n"  // unit 1: _currentDepth
	"uniform vec4 u_depthRecip;\n"  // fragment program.env[22]
	"uniform vec4 u_partRadius;\n"  // fragment program.env[23]
	"uniform vec4 u_chanMask;\n"    // fragment program.env[24]
	"in vec2 v_tc;\n"
	"in vec4 v_col;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	// Map the fragment to a texcoord on the depth image, sample scene depth.
	// 0.9994 cap + Doom-unit recovery identical to the ARB original.
	"  vec2 depthTC = gl_FragCoord.xy * u_depthRecip.xy;\n"
	"  float scene_depth = min( texture( u_depth, depthTC ).r, 0.9994 );\n"
	"  float sceneD = 1.0 / ( scene_depth * 0.33333333 - 0.33316667 );\n"
	"  float particleD = 1.0 / ( gl_FragCoord.z * 0.33333333 - 0.33316667 );\n"
	// NB depth is negative: 0 at the eye, -100 at 100 units into the screen.
	"  float d = -sceneD + particleD;\n"
	"  d += u_partRadius.x;\n"
	"  float fade = clamp( d * u_partRadius.y, 0.0, 1.0 );\n"
	"  float nearFade = clamp( particleD * -u_partRadius.z, 0.0, 1.0 );\n"
	"  fade *= nearFade;\n"
	"  vec4 fade4 = clamp( vec4( fade ) + u_chanMask, 0.0, 1.0 );\n"
	"  vec4 oColor = texture( u_diff, v_tc );\n"
	"  oColor *= fade4;\n"
	"  vec4 res = oColor * v_col;\n"
	"  if (!alphaPass(res.a)) { discard; }\n"
	"  o_col = res;\n"
	"}\n";
// Glass warp (TG_GLASSWARP): stage texture on unit 0 carries the distortion
// pattern; scratch copies of the framebuffer on units 1/2 are sampled with
// a screen-space UV wobbled by it. Subtle effect; approximated.
static const char *GLES_VS_GLASS =
	"out vec2 v_tc;\n"
	"out vec4 v_col;\n"
	"out vec2 v_suv;\n"
	"void main() {\n"
	"  v_tc = a_tc.xy; v_col = a_col;\n"
	"  vec4 clip = u_mvp * a_pos;\n"
	"  v_suv = ( clip.xy / max( clip.w, 0.0001 ) ) * 0.5 + 0.5;\n"
	"  gl_Position = clip;\n"
	"}\n";
static const char *GLES_FS_GLASS =
	"uniform sampler2D u_stageTex;\n"   // unit 0
	"uniform sampler2D u_scratchTex;\n" // unit 1
	"uniform sampler2D u_scratchTex2;\n"// unit 2
	"uniform vec4 u_gamma;\n"
	"in vec2 v_tc;\n"
	"in vec4 v_col;\n"
	"in vec2 v_suv;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec2 off = ( texture( u_stageTex, v_tc ).rg - 0.5 ) * 0.08;\n"
	"  vec3 c = texture( u_scratchTex, v_suv + off ).rgb * v_col.rgb;\n"
	"  c = gammaCorrect(c, u_gamma);\n"
	"  if (!alphaPass(v_col.a)) { discard; }\n"
	"  o_col = vec4( c, v_col.a );\n"
	"}\n";

// Retail heat-haze variants share distance-limited deformation. The fragment
// variant controls mask/vertex attenuation; the stock assets also mix the
// vertex-color vertex program with the mask-only fragment program.
static const char *GLES_VS_HEAT =
	"uniform mat4 u_mv, u_proj; uniform vec4 u_scroll, u_deform;\n"
	"out vec2 v_tc, v_scroll, v_deform; out vec4 v_col;\n"
	"void main(){ gl_Position=u_mvp*a_pos; v_tc=a_tc.xy; v_scroll=a_tc.xy+u_scroll.xy; v_col=a_col;\n"
	"vec4 p=vec4(1.0,0.0,(u_mv*a_pos).z,1.0); vec4 q=u_proj*p;\n"
	"v_deform=min(vec2(q.x/max(q.w,1.0)),vec2(0.02))*u_deform.xy; }\n";
static const char *GLES_FS_HEAT =
	"uniform sampler2D u_screen, u_normal, u_mask; uniform vec4 u_screenScale, u_screenRecip; uniform int u_mode;\n"
	"in vec2 v_tc, v_scroll, v_deform; in vec4 v_col; out vec4 o_col;\n"
	"void main(){ vec2 mask=vec2(1.0); if(u_mode>1){ mask=texture(u_mask,v_tc).xy;\n"
	"if(u_mode==3) mask*=v_col.xy; mask-=vec2(0.01); if(any(lessThan(mask,vec2(0.0)))) discard; }\n"
	"vec4 n=texture(u_normal,v_scroll); vec2 offset=(vec2(n.a,n.g)*2.0-1.0)*mask*v_deform;\n"
	"vec2 uv=clamp(gl_FragCoord.xy*u_screenRecip.xy+offset,vec2(0.0),vec2(1.0))*u_screenScale.xy;\n"
	"o_col=vec4(texture(u_screen,uv).rgb,1.0); }\n";

// Sky / diffuse-irradiance cubes (TG_SKYBOX_CUBE, TG_WOBBLESKY_CUBE,
// TG_DIFFUSE_CUBE): the engine feeds precomputed vec3 directions through the
// texcoord array (dynamicTexCoords or normals). Same lookup the fixed
// pipeline would do, as a samplerCube program.
static const char *GLES_VS_SKY =
	"out vec3 v_dir;\n"
	"out vec4 v_col;\n"
	"void main() {\n"
	"  v_dir = a_tc; v_col = a_col;\n"
	"  gl_Position = u_mvp * a_pos;\n"
	"}\n";
static const char *GLES_FS_SKY =
	"uniform samplerCube u_cube;\n" // unit 0
	"uniform vec4 u_gamma;\n"
	"uniform vec4 u_flatColor;\n"
	"uniform float u_useVtx;\n"
	"in vec3 v_dir;\n"
	"in vec4 v_col;\n"
	"out vec4 o_col;\n"
	"void main() {\n"
	"  vec4 vc = mix( vec4( 1.0 ), v_col, u_useVtx ) * clamp( u_flatColor, 0.0, 1.0 );\n"
	"  vec3 c = texture( u_cube, normalize( v_dir ) ).rgb * vc.rgb;\n"
	"  c = gammaCorrect(c, u_gamma);\n"
	"  if (!alphaPass(vc.a)) { discard; }\n"
	"  o_col = vec4( c, vc.a );\n"
	"}\n";

static idStr GLES_Concat( const char *a, const char *b ) {
	idStr s = a;
	s += b;
	return s;
}

static void GLES_BuildInteraction( void ) {
	if ( g_progInteraction.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_INTERACTION );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_INTERACTION );
	g_progInteraction.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progInteraction.prog == 0 ) {
		common->Printf( "WebGL: interaction program failed, world lighting will use flat fallback\n" );
		return;
	}
	glesProg_t *p = &g_progInteraction;
	GLES_FetchCommon( p );
	p->lOrigin = p->vOrigin = -1;
	p->interEnv = glGetUniformLocation( p->prog, "u_ienv" );
	p->diffCol = glGetUniformLocation( p->prog, "u_diffCol" );
	p->specCol = glGetUniformLocation( p->prog, "u_specCol" );
	const char *names[7] = { "u_cube", "u_bump", "u_fall", "u_proj", "u_diff", "u_spec", "u_spectab" };
	// Retain the stock diffuse-light normalization cube's quantized response.
	GLES_UseProgram( p->prog );
	for ( int i = 0; i < 7; i++ ) {
		p->tex[i] = glGetUniformLocation( p->prog, names[i] );
		if ( p->tex[i] >= 0 ) {
			GLES_Uniform1i( p->tex[i], i );
		}
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: interaction GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildShadow( void ) {
	if ( g_progShadow.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_SHADOW );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_SHADOW );
	g_progShadow.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progShadow.prog == 0 ) {
		return;
	}
	GLES_FetchCommon( &g_progShadow );
	g_progShadow.lOrigin = glGetUniformLocation(g_progShadow.prog, "u_lOrigin");
	g_progShadow.shadowExtrude = glGetUniformLocation(g_progShadow.prog, "u_shadowExtrude");
	g_progShadow.tex0 = -1;
	common->Printf( "WebGL: shadow GLSL-ES program ready (id %u)\n", (unsigned)g_progShadow.prog );
}

static void GLES_BuildFlat( void ) {
	if ( g_progFlat.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_FLAT );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_FLAT );
	g_progFlat.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progFlat.prog == 0 ) {
		common->Printf( "WebGL: flat program failed — nothing will render\n" );
		return;
	}
	glesProg_t *p = &g_progFlat;
	GLES_FetchCommon( p );
	p->tex0 = glGetUniformLocation( p->prog, "u_tex0" );
	p->tex1 = glGetUniformLocation( p->prog, "u_tex1" );
	p->texgenMode = glGetUniformLocation( p->prog, "u_texgenMode" );
	p->genP0 = glGetUniformLocation( p->prog, "u_genP0" );
	p->genM0 = glGetUniformLocation( p->prog, "u_genM0" );
	p->genP1 = glGetUniformLocation( p->prog, "u_genP1" );
	p->genM1 = glGetUniformLocation( p->prog, "u_genM1" );
	p->useVtx = glGetUniformLocation( p->prog, "u_useVtx" );
	GLES_UseProgram( p->prog );
	if ( p->tex0 >= 0 ) {
		GLES_Uniform1i( p->tex0, 0 );
	}
	if ( p->tex1 >= 0 ) {
		GLES_Uniform1i( p->tex1, 1 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: flat GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_FetchEnvCommon( glesProg_t *p ) {
	GLES_FetchCommon( p );
	p->eyeLocal = glGetUniformLocation( p->prog, "u_eyeLocal" );
	p->modelR0 = glGetUniformLocation( p->prog, "u_modelR0" );
	p->modelR1 = glGetUniformLocation( p->prog, "u_modelR1" );
	p->modelR2 = glGetUniformLocation( p->prog, "u_modelR2" );
}

static void GLES_BuildEnv( void ) {
	if ( g_progEnv.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_ENV );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_ENV );
	g_progEnv.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progEnv.prog == 0 ) {
		return;
	}
	glesProg_t *p = &g_progEnv;
	GLES_FetchEnvCommon( p );
	p->cubeMap = glGetUniformLocation( p->prog, "u_cube" );
	GLES_UseProgram( p->prog );
	if ( p->cubeMap >= 0 ) {
		GLES_Uniform1i( p->cubeMap, 0 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: environment GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildBumpyEnv( void ) {
	if ( g_progBumpyEnv.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_BUMPYENV );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_BUMPYENV );
	g_progBumpyEnv.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progBumpyEnv.prog == 0 ) {
		return;
	}
	glesProg_t *p = &g_progBumpyEnv;
	GLES_FetchEnvCommon( p );
	p->cubeMap = glGetUniformLocation( p->prog, "u_cube" );
	p->bumpMap = glGetUniformLocation( p->prog, "u_bump" );
	GLES_UseProgram( p->prog );
	if ( p->cubeMap >= 0 ) {
		GLES_Uniform1i( p->cubeMap, 0 );
	}
	if ( p->bumpMap >= 0 ) {
		GLES_Uniform1i( p->bumpMap, 1 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: bumpy-environment GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildGlass( void ) {
	if ( g_progGlass.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_GLASS );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_GLASS );
	g_progGlass.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progGlass.prog == 0 ) {
		return;
	}
	glesProg_t *p = &g_progGlass;
	GLES_FetchCommon( p );
	p->stageTex = glGetUniformLocation( p->prog, "u_stageTex" );
	p->scratchTex = glGetUniformLocation( p->prog, "u_scratchTex" );
	p->scratchTex2 = glGetUniformLocation( p->prog, "u_scratchTex2" );
	GLES_UseProgram( p->prog );
	if ( p->stageTex >= 0 ) {
		GLES_Uniform1i( p->stageTex, 0 );
	}
	if ( p->scratchTex >= 0 ) {
		GLES_Uniform1i( p->scratchTex, 1 );
	}
	if ( p->scratchTex2 >= 0 ) {
		GLES_Uniform1i( p->scratchTex2, 2 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: glasswarp GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildSoft( void ) {
	if ( g_progSoft.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_SOFT );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_SOFT );
	g_progSoft.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progSoft.prog == 0 ) {
		return;
	}
	glesProg_t *p = &g_progSoft;
	GLES_FetchCommon( p );
	p->depthRecip = glGetUniformLocation( p->prog, "u_depthRecip" );
	p->partRadius = glGetUniformLocation( p->prog, "u_partRadius" );
	p->chanMask = glGetUniformLocation( p->prog, "u_chanMask" );
	p->softDiff = glGetUniformLocation( p->prog, "u_diff" );
	p->softDepth = glGetUniformLocation( p->prog, "u_depth" );
	GLES_UseProgram( p->prog );
	if ( p->softDiff >= 0 ) {
		GLES_Uniform1i( p->softDiff, 0 );
	}
	if ( p->softDepth >= 0 ) {
		GLES_Uniform1i( p->softDepth, 1 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: soft-particle GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildSky( void ) {
	if ( g_progSky.prog != 0 ) {
		return;
	}
	idStr vs = GLES_Concat( GLES_VS_HEAD, GLES_VS_SKY );
	idStr fs = GLES_Concat( GLES_FS_HEAD, GLES_FS_SKY );
	g_progSky.prog = GLES_LinkProgram( vs.c_str(), fs.c_str() );
	if ( g_progSky.prog == 0 ) {
		return;
	}
	glesProg_t *p = &g_progSky;
	GLES_FetchCommon( p );
	p->useVtx = glGetUniformLocation( p->prog, "u_useVtx" );
	p->flatColor = glGetUniformLocation( p->prog, "u_flatColor" );
	p->skyCube = glGetUniformLocation( p->prog, "u_cube" );
	GLES_UseProgram( p->prog );
	if ( p->skyCube >= 0 ) {
		GLES_Uniform1i( p->skyCube, 0 );
	}
	GLES_UseProgram( 0 );
	common->Printf( "WebGL: sky GLSL-ES program ready (id %u)\n", (unsigned)p->prog );
}

static void GLES_BuildColorProcess( void ) {
	if (g_progColorProcess.prog) return;
	idStr vs = GLES_Concat(GLES_VS_HEAD, GLES_VS_COLORPROCESS);
	idStr fs = GLES_Concat(GLES_FS_HEAD, GLES_FS_COLORPROCESS);
	glesProg_t *p = &g_progColorProcess;
	p->prog = GLES_LinkProgram(vs.c_str(), fs.c_str());
	if (!p->prog) return;
	GLES_FetchCommon(p);
	p->colorFraction = glGetUniformLocation(p->prog, "u_colorFraction");
	p->colorTarget = glGetUniformLocation(p->prog, "u_colorTarget");
	p->screenScale = glGetUniformLocation(p->prog, "u_screenScale");
	p->screenRecip = glGetUniformLocation(p->prog, "u_screenRecip");
	GLES_UseProgram(p->prog);
	GLES_Uniform1i(glGetUniformLocation(p->prog, "u_screen"), 0);
	GLES_UseProgram(0);
	common->Printf("WebGL: color-process GLSL-ES program ready (id %u)\n", (unsigned)p->prog);
}

static void GLES_BuildHeat( void ) {
	if ( g_progHeat.prog ) return;
	idStr vs=GLES_Concat(GLES_VS_HEAD,GLES_VS_HEAT), fs=GLES_Concat(GLES_FS_HEAD,GLES_FS_HEAT);
	g_progHeat.prog=GLES_LinkProgram(vs.c_str(),fs.c_str());
	if ( !g_progHeat.prog ) return;
	GLES_FetchCommon(&g_progHeat);
	const char *names[7] = { "u_mv", "u_proj", "u_scroll", "u_deform", "u_screenScale", "u_screenRecip", "u_mode" };
	for ( int i = 0; i < 7; ++i ) g_progHeat.heat[i] = glGetUniformLocation(g_progHeat.prog,names[i]);
	GLES_UseProgram(g_progHeat.prog);
	GLES_Uniform1i(glGetUniformLocation(g_progHeat.prog,"u_screen"),0);
	GLES_Uniform1i(glGetUniformLocation(g_progHeat.prog,"u_normal"),1);
	GLES_Uniform1i(glGetUniformLocation(g_progHeat.prog,"u_mask"),2);
	GLES_UseProgram(0);
	common->Printf("WebGL: heat-haze GLSL-ES program ready (id %u)\n", (unsigned)g_progHeat.prog);
}

void R_GLES_ReloadPrograms( void ) {
	memset(g_uniformState, 0, sizeof(g_uniformState));
	GLES_UseProgram(0);
	// Desktop reloadARBprograms re-parses .vfp files from disk; our GLSL is
	// compiled in, so "reload" deletes and re-links every program (exercises
	// the same console path and recovers leaked/failed programs).
	glesProg_t *all[] = {
		&g_progInteraction, &g_progShadow, &g_progFlat, &g_progEnv,
		&g_progBumpyEnv, &g_progGlass, &g_progSoft, &g_progSky, &g_progHeat, &g_progColorProcess
	};
	for ( size_t i = 0; i < sizeof( all ) / sizeof( all[0] ); i++ ) {
		if ( all[i]->prog != 0 ) {
			glDeleteProgram( all[i]->prog );
			all[i]->prog = 0;
		}
	}
	g_curProg = NULL;
	g_lastVid = -1;
	g_lastFid = -1;
	R_GLES_NoteProgram( NULL );
	common->Printf( "WebGL: GLSL programs relinked\n" );
}

unsigned int R_GLES_NoteProgram( const char *name, int ident ) {
	// Compile all programs up front so the first bind never stalls.
	GLES_BuildInteraction();
	GLES_BuildShadow();
	GLES_BuildFlat();
	GLES_BuildEnv();
	GLES_BuildBumpyEnv();
	GLES_BuildGlass();
	GLES_BuildSoft();
	GLES_BuildSky();
	GLES_BuildHeat();
	GLES_BuildColorProcess();
	if ( name && ident > 0 && ident < 1024 ) {
		if ( !idStr::Icmp(name,"heatHaze.vfp") ) g_heatModes[ident]=1;
		else if ( !idStr::Icmp(name,"heatHazeWithMask.vfp") ) g_heatModes[ident]=2;
		else if ( !idStr::Icmp(name,"heatHazeWithMaskAndVertex.vfp") ) g_heatModes[ident]=3;
		g_colorProcessIds[ident] = !idStr::Icmp(name, "colorProcess.vfp");
	}
	if ( name ) {
		common->Printf( "WebGL: ARB program '%s' registered (real GLSL in use where ported)\n", name );
	}
	if ( g_progFlat.prog != 0 ) {
		return g_progFlat.prog;
	}
	return 0;
}

// Upload MVP + shared uniforms to the current program.
static void GLES_SyncMVP( void ) {
	if ( g_curProg == NULL || g_curProg->prog == 0 ) {
		return;
	}
	float mvp[16];
	GLES_MatMul( mvp, g_mProj, g_mMV );
	if ( g_curProg->mvp >= 0 ) {
		GLES_UniformMatrix4fv( g_curProg->mvp, 1, GL_FALSE, mvp );
	}
	if ( g_curProg->textureMatrix >= 0 ) {
		GLES_UniformMatrix4fv( g_curProg->textureMatrix, 1, GL_FALSE, g_mTex );
	}
}

static void GLES_UploadAlphaTest( glesProg_t *p ) {
	if ( p != NULL && p->alphaTest >= 0 ) {
		float at[3] = { g_alphaEnabled ? 1.0f : 0.0f, g_alphaRef, (float)g_alphaFunc };
		GLES_Uniform3fv( p->alphaTest, 1, at );
	}
}

// Interaction vertex environment (program.env[4..17]). Per-surface setup
// changes several slots between draws; one array upload before the draw
// replaces a call per slot. r_webDeferInteractionEnv 0 uploads on every
// change instead (same values, more calls) for A/B timing.
static idCVar r_webDeferInteractionEnv("r_webDeferInteractionEnv", "1", CVAR_RENDERER | CVAR_BOOL,
	"upload the interaction vertex environment once per draw instead of per parameter");
static bool g_interactionEnvDirty = true;

static void GLES_FlushInteractionEnv( void ) {
	if ( g_interactionEnvDirty && g_curProg == &g_progInteraction && g_progInteraction.interEnv >= 0 ) {
		GLES_Uniform4fv( g_progInteraction.interEnv, 14, g_glesEnvVertex[4] );
		g_interactionEnvDirty = false;
	}
}

static void GLES_UploadProgramUniforms( glesProg_t *p ) {
	if (g_webPerf.remaining) ++g_webPerf.uniformUploads;
	// Gamma comes from the cached fragment env slot 21 (RB_SetProgramEnvironment
	// writes 1s for post-process passes so gamma isn't applied twice — reading
	// the cvars directly would double-apply it there).
	if ( p->gamma >= 0 ) {
		GLES_Uniform4fv( p->gamma, 1, g_glesEnvFragment[21] );
	}
	GLES_UploadAlphaTest( p );
	if ( p->flatColor >= 0 ) {
		GLES_Uniform4fv( p->flatColor, 1, g_flatColor );
	}
	if ( p->useVtx >= 0 ) {
		GLES_Uniform1f( p->useVtx, g_useVtxColor );
	}
	if ( p->inverseVtx >= 0 ) GLES_Uniform1f( p->inverseVtx, g_inverseVtxColor );
	if ( p == &g_progInteraction && p->prog != 0 ) {
		g_interactionEnvDirty = true;
		GLES_FlushInteractionEnv();
		if ( p->diffCol >= 0 ) GLES_Uniform4fv( p->diffCol, 1, g_glesEnvFragment[0] );
		if ( p->specCol >= 0 ) GLES_Uniform4fv( p->specCol, 1, g_glesEnvFragment[1] );
	} else if ( p == &g_progShadow && p->prog != 0 ) {
		GLES_Uniform4fv(p->lOrigin, 1, g_glesEnvVertex[4]);
		GLES_Uniform1f(p->shadowExtrude, g_shadowExtrude ? 1.0f : 0.0f);
	} else if ( ( p == &g_progEnv || p == &g_progBumpyEnv ) && p->prog != 0 ) {
		// Environment programs read vertex env 5 (local eye) and 6/7/8
		// (model rows); see RB_SetProgramEnvironmentSpace.
		if ( p->eyeLocal >= 0 ) GLES_Uniform4fv( p->eyeLocal, 1, g_glesEnvVertex[5] );
		if ( p->modelR0 >= 0 ) GLES_Uniform4fv( p->modelR0, 1, g_glesEnvVertex[6] );
		if ( p->modelR1 >= 0 ) GLES_Uniform4fv( p->modelR1, 1, g_glesEnvVertex[7] );
		if ( p->modelR2 >= 0 ) GLES_Uniform4fv( p->modelR2, 1, g_glesEnvVertex[8] );
	} else if ( p == &g_progSoft && p->prog != 0 ) {
		// Soft particles read fragment env 22/23/24 (depth recip, particle
		// radius, channel mask); see draw_common.cpp.
		if ( p->depthRecip >= 0 ) GLES_Uniform4fv( p->depthRecip, 1, g_glesEnvFragment[22] );
		if ( p->partRadius >= 0 ) GLES_Uniform4fv( p->partRadius, 1, g_glesEnvFragment[23] );
		if ( p->chanMask >= 0 ) GLES_Uniform4fv( p->chanMask, 1, g_glesEnvFragment[24] );
	}
	GLES_SyncMVP();
	if ( p == &g_progHeat ) {
		GLES_UniformMatrix4fv(p->heat[0],1,GL_FALSE,g_mMV);
		GLES_UniformMatrix4fv(p->heat[1],1,GL_FALSE,g_mProj);
		GLES_Uniform4fv(p->heat[2],1,g_vertexLocal[0]);
		GLES_Uniform4fv(p->heat[3],1,g_vertexLocal[1]);
		GLES_Uniform4fv(p->heat[4],1,g_glesEnvFragment[0]);
		GLES_Uniform4fv(p->heat[5],1,g_glesEnvFragment[1]);
		GLES_Uniform1i(p->heat[6],g_heatModes[g_lastFid]);
	}
	if (p == &g_progColorProcess) {
		GLES_Uniform4fv(p->colorFraction, 1, g_vertexLocal[0]);
		GLES_Uniform4fv(p->colorTarget, 1, g_vertexLocal[1]);
		GLES_Uniform4fv(p->screenScale, 1, g_glesEnvFragment[0]);
		GLES_Uniform4fv(p->screenRecip, 1, g_glesEnvFragment[1]);
	}
}

// Select a real program from the ARB (vertex, fragment) id pair the engine
// bound. VPROG/FPROG_INTERACTION get the Blinn-Phong shader, the stencil
// shadow vertex program gets the MVP shader, environment pairs get reflection
// shaders, FPROG_GLASSWARP (bound without a vertex program) gets the warp
// shader, everything else gets flat.
static void GLES_UseSelectedProgram( void ) {
	glesProg_t *p = &g_progFlat;
	if ( g_lastVid == VPROG_STENCIL_SHADOW && g_progShadow.prog != 0 ) {
		p = &g_progShadow;
	} else if (g_lastVid > 0 && g_lastVid < 1024 && g_colorProcessIds[g_lastVid]
	           && g_lastFid > 0 && g_lastFid < 1024 && g_colorProcessIds[g_lastFid]
	           && g_progColorProcess.prog != 0) {
		p = &g_progColorProcess;
	} else if ( g_lastVid > 0 && g_lastVid < 1024 && g_heatModes[g_lastVid]
	            && g_lastFid > 0 && g_lastFid < 1024 && g_heatModes[g_lastFid]
	            && g_progHeat.prog != 0 ) {
		p = &g_progHeat;
	} else
	if ( g_lastVid == VPROG_INTERACTION && g_lastFid == FPROG_INTERACTION
	     && g_progInteraction.prog != 0 ) {
		p = &g_progInteraction;
	} else if ( g_lastVid == VPROG_ENVIRONMENT && g_lastFid == FPROG_ENVIRONMENT
	            && g_progEnv.prog != 0 ) {
		p = &g_progEnv;
	} else if ( g_lastVid == VPROG_BUMPY_ENVIRONMENT && g_lastFid == FPROG_BUMPY_ENVIRONMENT
	            && g_progBumpyEnv.prog != 0 ) {
		p = &g_progBumpyEnv;
	} else if ( g_lastFid == FPROG_GLASSWARP && g_progGlass.prog != 0 ) {
		p = &g_progGlass;
	} else if ( g_lastVid == VPROG_SOFT_PARTICLE && g_lastFid == FPROG_SOFT_PARTICLE
	            && g_progSoft.prog != 0 ) {
		p = &g_progSoft;
	} else if ( g_progFlat.prog == 0 ) {
		return;
	}
	g_curProg = p;
	GLES_UseProgram( p->prog );
	// Binding a program must preserve vertex arrays, just as desktop GL
	// does: ambient and GUI paths may bind after setting their pointers.
	GLES_UploadProgramUniforms( p );
}

// ---------------------------------------------------------------------------
// ARB program entry points (signatures match qgl_gles.h; assigned to the
// qgl* pointers by R_GLES_LoadFunctions)
// ---------------------------------------------------------------------------
static void APIENTRY GLES_ProgramStringARB( GLenum target, GLenum format, GLsizei len, const GLvoid *string ) {
	(void)target; (void)format; (void)len; (void)string;
	GLES_BuildInteraction();
	GLES_BuildShadow();
	GLES_BuildFlat();
	GLES_BuildEnv();
	GLES_BuildBumpyEnv();
	GLES_BuildGlass();
	GLES_BuildSoft();
	GLES_BuildSky();
}

static void APIENTRY GLES_BindProgramARB( GLenum target, GLuint id ) {
	if ( target == GL_VERTEX_PROGRAM_ARB ) {
		g_lastVid = (int)id;
	} else if ( target == GL_FRAGMENT_PROGRAM_ARB ) {
		g_lastFid = (int)id;
	} else {
		return;
	}
	GLES_UseSelectedProgram();
}

static void APIENTRY GLES_GenProgramsARB( GLsizei n, GLuint *programs ) {
	static GLuint next = 1;
	for ( GLsizei i = 0; i < n; i++ ) {
		programs[i] = next++;
	}
}

static void APIENTRY GLES_ProgramEnvParameter4fvARB( GLenum target, GLuint index, const GLfloat *params ) {
	float (*slot)[4] = ( target == GL_VERTEX_PROGRAM_ARB ) ? g_glesEnvVertex : g_glesEnvFragment;
	if ( index < 32 ) {
		// Program activation uploads the cached environment to that shader.
		// Repeated per-surface defaults (matrix rows, colors, gamma) therefore
		// need no additional upload until their values actually change.
		if (!memcmp(slot[index], params, 4 * sizeof(float))) return;
		slot[index][0] = params[0];
		slot[index][1] = params[1];
		slot[index][2] = params[2];
		slot[index][3] = params[3];
	}
	// The engine writes env parameters between binding a program and drawing
	// with it (e.g. per-interaction colors in RB_ARB2_DrawInteraction), so
	// push the ones the current program consumes straight into uniforms.
	// Anything unmapped stays cached for the next program switch.
	if ( g_curProg != NULL && g_curProg->prog != 0 && index < 32 ) {
		GLint loc = -1;
		if ( g_curProg == &g_progInteraction ) {
			if ( target == GL_VERTEX_PROGRAM_ARB ) {
				if ( index >= 4 && index <= 17 ) {
					g_interactionEnvDirty = true;
					if ( !r_webDeferInteractionEnv.GetBool() ) {
						GLES_FlushInteractionEnv();
					}
				}
			} else {
				if ( index == 0 ) loc = g_curProg->diffCol;
				else if ( index == 1 ) loc = g_curProg->specCol;
				else if ( index == 21 ) loc = g_curProg->gamma;
			}
		} else if (g_curProg == &g_progHeat && target == GL_FRAGMENT_PROGRAM_ARB) {
			if (index == 0) loc = g_curProg->heat[4];
			else if (index == 1) loc = g_curProg->heat[5];
		} else if (g_curProg == &g_progColorProcess && target == GL_FRAGMENT_PROGRAM_ARB) {
			if (index == 0) loc = g_curProg->screenScale;
			else if (index == 1) loc = g_curProg->screenRecip;
			else if (index == 21) loc = g_curProg->gamma;
		} else if ( g_curProg == &g_progShadow ) {
			if (target == GL_VERTEX_PROGRAM_ARB && index == 4) loc = g_curProg->lOrigin;
		} else if ( g_curProg == &g_progEnv || g_curProg == &g_progBumpyEnv ) {
			if ( target == GL_VERTEX_PROGRAM_ARB ) {
				if ( index == 5 ) loc = g_curProg->eyeLocal;
				else if ( index == 6 ) loc = g_curProg->modelR0;
				else if ( index == 7 ) loc = g_curProg->modelR1;
				else if ( index == 8 ) loc = g_curProg->modelR2;
			} else if ( index == 21 ) {
				loc = g_curProg->gamma;
			}
		} else if ( g_curProg == &g_progSoft ) {
			// Soft-particle fragment env (draw_common.cpp): 22 depth recip,
			// 23 particle radius, 24 channel mask, 21 gamma (unused by the
			// shader but harmless to keep current).
			if ( target == GL_FRAGMENT_PROGRAM_ARB ) {
				if ( index == 22 ) loc = g_curProg->depthRecip;
				else if ( index == 23 ) loc = g_curProg->partRadius;
				else if ( index == 24 ) loc = g_curProg->chanMask;
				else if ( index == 21 ) loc = g_curProg->gamma;
			}
		} else {
			// flat / shadow / glass: only gamma is shared.
			if ( target == GL_FRAGMENT_PROGRAM_ARB && index == 21 ) {
				loc = g_curProg->gamma;
			}
		}
		if ( loc >= 0 ) {
			GLES_Uniform4fv( loc, 1, params );
		}
	}
}

static void APIENTRY GLES_ProgramLocalParameter4fvARB( GLenum target, GLuint index, const GLfloat *params ) {
	if ( target == GL_VERTEX_PROGRAM_ARB && index < 32 ) memcpy(g_vertexLocal[index],params,4*sizeof(float));
	if (g_curProg == &g_progColorProcess && target == GL_VERTEX_PROGRAM_ARB && index < 2) {
		GLES_Uniform4fv(index == 0 ? g_curProg->colorFraction : g_curProg->colorTarget, 1, params);
	}
	if ( g_curProg ) GLES_UploadProgramUniforms(g_curProg);
}

// Engine ARB attrib indices 8..11 (st/tangent0/tangent1/normal) are remapped
// onto the shader-visible locations 1/4/5/3 (see file header).
static GLuint GLES_RemapAttrib( GLuint index ) {
	switch ( index ) {
	case 8: return 1;
	case 9: return 4;
	case 10: return 5;
	case 11: return 3;
	default: return index;
	}
}

static void APIENTRY GLES_VertexAttribPointerARB( GLuint index, GLint size, GLenum type, GLboolean normalized, GLsizei stride, const GLvoid *pointer ) {
	GLES_AttribPointer( GLES_RemapAttrib( index ), size, type, normalized, stride, pointer );
}

static void APIENTRY GLES_EnableVertexAttribArrayARB( GLuint index ) {
	GLES_AttribEnabled( GLES_RemapAttrib( index ), true );
}

static void APIENTRY GLES_DisableVertexAttribArrayARB( GLuint index ) {
	GLES_AttribEnabled( GLES_RemapAttrib( index ), false );
}

static GLvoid *APIENTRY GLES_MapBufferARB( GLenum target, GLenum access ) {
	(void)target; (void)access;
	// No MapBuffer in GLES3 core and VertexCache never maps (uploads go
	// through BufferData/SubData, see VertexCache.cpp) — never called.
	return NULL;
}

// ---------------------------------------------------------------------------
// Fixed-function replacements (signatures match the QGLPROC declarations)
// ---------------------------------------------------------------------------
static void APIENTRY GLES_Enable( GLenum cap ) {
	if ( cap == GL_LIGHTING || cap == GL_LINE_STIPPLE ) return;
	if ( cap == GL_TEXTURE_2D || cap == GL_TEXTURE_CUBE_MAP || cap == GL_TEXTURE_3D ) return;
	if ( cap == (GLenum)GL_VERTEX_PROGRAM_ARB || cap == (GLenum)GL_FRAGMENT_PROGRAM_ARB ) {
		if ( cap == (GLenum)GL_VERTEX_PROGRAM_ARB ) g_vertexProgramEnabled = true;
		else g_fragmentProgramEnabled = true;
		return;
	}
	if ( cap == (GLenum)GL_ALPHA_TEST ) {
		g_alphaEnabled = true;
		GLES_UploadAlphaTest( g_curProg );
		return;
	}
	int gen = GLES_TexgenCapIndex( cap );
	if ( gen >= 0 ) {
		int unit = backEnd.glState.currenttmu;
		if ( unit >= 0 && unit < GLES_MAX_TEXGEN_UNITS ) {
			g_genEn[unit][gen] = true;
		}
		return;
	}
	glEnable( cap );
}

static void APIENTRY GLES_Disable( GLenum cap ) {
	if ( cap == GL_LIGHTING || cap == GL_LINE_STIPPLE ) return;
	if ( cap == GL_TEXTURE_2D || cap == GL_TEXTURE_CUBE_MAP || cap == GL_TEXTURE_3D ) return;
	if ( cap == (GLenum)GL_VERTEX_PROGRAM_ARB || cap == (GLenum)GL_FRAGMENT_PROGRAM_ARB ) {
		if ( cap == (GLenum)GL_VERTEX_PROGRAM_ARB ) g_vertexProgramEnabled = false;
		else g_fragmentProgramEnabled = false;
		return;
	}
	if ( cap == (GLenum)GL_ALPHA_TEST ) {
		g_alphaEnabled = false;
		GLES_UploadAlphaTest( g_curProg );
		return;
	}
	int gen = GLES_TexgenCapIndex( cap );
	if ( gen >= 0 ) {
		int unit = backEnd.glState.currenttmu;
		if ( unit >= 0 && unit < GLES_MAX_TEXGEN_UNITS ) {
			g_genEn[unit][gen] = false;
		}
		return;
	}
	glDisable( cap );
}

static void APIENTRY GLES_ClearDepth( GLclampd depth ) {
	glClearDepthf( (GLfloat)depth );
}

static void APIENTRY GLES_DepthRange( GLclampd zNear, GLclampd zFar ) {
	glDepthRangef( (GLfloat)zNear, (GLfloat)zFar );
}

static void APIENTRY GLES_AlphaFunc( GLenum func, GLclampf ref ) {
	// AlphaFunc configures the comparison; Enable/Disable owns its state.
	g_alphaRef = idMath::ClampFloat(0.0f, 1.0f, ref);
	g_alphaFunc = func;
	GLES_UploadAlphaTest( g_curProg );
}

static void APIENTRY GLES_Color3f( GLfloat r, GLfloat g, GLfloat b ) {
	g_flatColor[0] = r; g_flatColor[1] = g; g_flatColor[2] = b; g_flatColor[3] = 1.0f;
	if ( g_curProg != NULL && g_curProg->flatColor >= 0 ) {
		GLES_Uniform4fv( g_curProg->flatColor, 1, g_flatColor );
	}
}

static void APIENTRY GLES_Color4f( GLfloat r, GLfloat g, GLfloat b, GLfloat a ) {
	g_flatColor[0] = r; g_flatColor[1] = g; g_flatColor[2] = b; g_flatColor[3] = a;
	if ( g_curProg != NULL && g_curProg->flatColor >= 0 ) {
		GLES_Uniform4fv( g_curProg->flatColor, 1, g_flatColor );
	}
}

static void APIENTRY GLES_Color3fv( const GLfloat *v ) {
	GLES_Color3f( v[0], v[1], v[2] );
}

static void APIENTRY GLES_Color4fv( const GLfloat *v ) {
	GLES_Color4f( v[0], v[1], v[2], v[3] );
}

void R_GLES_SetStageColor( const float *color, int vertexColor ) {
	// Desktop combines material tint on a second white-texture stage.
	// Preserve that tint explicitly instead of dropping it on WebGL.
	GLES_Color4fv( color );
	g_useVtxColor = vertexColor == SVC_IGNORE ? 0.0f : 1.0f;
	g_inverseVtxColor = vertexColor == SVC_INVERSE_MODULATE ? 1.0f : 0.0f;
	if ( g_curProg ) GLES_UploadProgramUniforms( g_curProg );
}

void R_GLES_SetShadowMode( bool sharedVertices ) {
	g_shadowExtrude = sharedVertices;
	if (g_curProg == &g_progShadow)
		GLES_Uniform1f(g_progShadow.shadowExtrude, sharedVertices ? 1.0f : 0.0f);
}

// Legacy client arrays -> vertex attributes on the live VBO (Position() has
// already bound it; see idVertexCache::Position).
static void GLES_UploadUseVtx( void ) {
	if ( g_curProg != NULL && g_curProg->useVtx >= 0 ) {
		GLES_Uniform1f( g_curProg->useVtx, g_useVtxColor );
	}
	if ( g_curProg && g_curProg->inverseVtx >= 0 ) GLES_Uniform1f( g_curProg->inverseVtx, g_inverseVtxColor );
}

static void APIENTRY GLES_VertexPointer( GLint size, GLenum type, GLsizei stride, const GLvoid *pointer ) {
	g_cpuShadowVertices = size == 4;
	GLES_AttribPointer( 0, size, type, GL_FALSE, stride, pointer );
	GLES_AttribEnabled( 0, true );
}

static void APIENTRY GLES_ColorPointer( GLint size, GLenum type, GLsizei stride, const GLvoid *pointer ) {
	g_inverseVtxColor = 0.0f;
	GLES_AttribPointer( 2, size, type, type == GL_UNSIGNED_BYTE ? GL_TRUE : GL_FALSE, stride, pointer );
	GLES_AttribEnabled( 2, true );
	// A vertex-color array takes over color modulation from the flat uniform;
	// reset it to white so the two don't multiply (the fixed pipeline's
	// second texture stage handled non-white material colors there).
	g_flatColor[0] = g_flatColor[1] = g_flatColor[2] = g_flatColor[3] = 1.0f;
	if ( g_curProg != NULL && g_curProg->flatColor >= 0 ) {
		GLES_Uniform4fv( g_curProg->flatColor, 1, g_flatColor );
	}
}

static void APIENTRY GLES_TexCoordPointer( GLint size, GLenum type, GLsizei stride, const GLvoid *pointer ) {
	GLES_AttribPointer( 1, size, type, GL_FALSE, stride, pointer );
	GLES_AttribEnabled( 1, true );
}

static void APIENTRY GLES_NormalPointer( GLenum type, GLsizei stride, const GLvoid *pointer ) {
	GLES_AttribPointer( 3, 3, type, GL_FALSE, stride, pointer );
	GLES_AttribEnabled( 3, true );
}

static void APIENTRY GLES_TexGenfv( GLenum coord, GLenum pname, const GLfloat *params ) {
	if ( pname != (GLenum)GL_OBJECT_PLANE ) {
		return; // only OBJECT_PLANE is used (see RB_PrepareStageTexturing)
	}
	int ci = GLES_TexgenCoordIndex( coord );
	if ( ci < 0 ) {
		return;
	}
	int unit = backEnd.glState.currenttmu;
	if ( unit < 0 || unit >= GLES_MAX_TEXGEN_UNITS ) {
		return;
	}
	g_genPlane[unit][ci][0] = params[0];
	g_genPlane[unit][ci][1] = params[1];
	g_genPlane[unit][ci][2] = params[2];
	g_genPlane[unit][ci][3] = params[3];
}

// Upload texgen planes + mode to the flat program. Mode 2 (projective) when
// unit 0 has Q enabled (blend lights, TG_PROJECTED), mode 1 for plain
// two-unit texgen (fog), 0 when nothing is enabled.
static void GLES_SyncTexgenUniforms( void ) {
	if ( g_curProg != &g_progFlat || g_progFlat.prog == 0 ) {
		return;
	}
	float mode = 0.0f;
	if ( g_genEn[0][3] ) {
		mode = 2.0f;
	} else if ( GLES_TexgenActive() ) {
		mode = 1.0f;
	}
	if ( g_progFlat.texgenMode >= 0 ) {
		GLES_Uniform1f( g_progFlat.texgenMode, mode );
	}
	if ( g_progFlat.secondTexgen >= 0 ) {
		bool second = g_genEn[1][0] || g_genEn[1][1] || g_genEn[1][2] || g_genEn[1][3];
		GLES_Uniform1f( g_progFlat.secondTexgen, second ? 1.0f : 0.0f );
	}
	if ( mode == 0.0f ) {
		return;
	}
	float m0[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
	float m1[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
	float p0[16], p1[16];
	for ( int c = 0; c < 4; c++ ) {
		m0[c] = g_genEn[0][c] ? 1.0f : 0.0f;
		m1[c] = g_genEn[1][c] ? 1.0f : 0.0f;
		for ( int k = 0; k < 4; k++ ) {
			p0[c * 4 + k] = g_genPlane[0][c][k];
			p1[c * 4 + k] = g_genPlane[1][c][k];
		}
	}
	if ( g_progFlat.genP0 >= 0 ) GLES_Uniform4fv( g_progFlat.genP0, 4, p0 );
	if ( g_progFlat.genM0 >= 0 ) GLES_Uniform4fv( g_progFlat.genM0, 1, m0 );
	if ( g_progFlat.genP1 >= 0 ) GLES_Uniform4fv( g_progFlat.genP1, 4, p1 );
	if ( g_progFlat.genM1 >= 0 ) GLES_Uniform4fv( g_progFlat.genM1, 1, m1 );
}

// Draw calls are the synchronization point the fixed pipeline never had:
// fog, blend lights and TG_* stages enable texgen without binding any ARB
// program, so select the texgen-capable flat program here when needed.
// The texgen mode uniform is refreshed on every flat draw (texgen state can
// change between draws without any program bind, e.g. fog cleanup -> 2D).
// Two more draw-time rules keep stale bindings honest:
//  - a stale interaction program (bound by an earlier light, reused by a
//    fixed-path draw outside RB_ARB2_CreateDrawInteractions) is demoted to
//    flat, which is what the fixed pipeline would have executed;
//  - a cube map on unit 0 with nothing texture-like on unit 1 selects the
//    sky program (skybox / diffuse-irradiance cubes feed vec3 directions).
static void GLES_SyncProgramForDraw( void ) {
	// CPU-extruded shadow volumes use homogeneous xyz/w vertices with
	// ARB programs disabled. They still need the shadow shader in WebGL.
	if ( g_cpuShadowVertices && !g_vertexProgramEnabled && g_progShadow.prog != 0 ) {
		if (g_curProg != &g_progShadow) {
			g_curProg = &g_progShadow;
			GLES_UseProgram( g_progShadow.prog );
			GLES_UploadProgramUniforms( &g_progShadow );
		}
		return;
	}
	// Main-menu GUI draws use the fixed pipeline and never bind an ARB
	// program. WebGL still requires a shader for the very first draw.
	if ( (g_curProg == NULL || (!g_vertexProgramEnabled && !g_fragmentProgramEnabled))
	     && g_curProg != &g_progFlat && g_progFlat.prog != 0 ) {
		g_curProg = &g_progFlat;
		GLES_UseProgram( g_progFlat.prog );
		GLES_UploadProgramUniforms( &g_progFlat );
	}
	if ( GLES_TexgenActive() ) {
		if ( g_curProg != &g_progFlat && g_progFlat.prog != 0 ) {
			g_curProg = &g_progFlat;
			GLES_UseProgram( g_progFlat.prog );
			GLES_UploadProgramUniforms( &g_progFlat );
		}
	} else if ( g_curProg == &g_progInteraction && !g_inInteraction ) {
		if ( g_progFlat.prog != 0 ) {
			g_curProg = &g_progFlat;
			GLES_UseProgram( g_progFlat.prog );
			GLES_UploadProgramUniforms( &g_progFlat );
		}
	} else if ( ( g_curProg == &g_progFlat || g_curProg == &g_progSky )
	            && g_progSky.prog != 0 && g_progFlat.prog != 0 ) {
		// Fixed-function texturing samples the target the engine enabled on
		// each unit. A unit keeps its 2D and cube bindings independently, and
		// a disabled unit (BindNull) can still hold a stale binding, so the
		// most recently bound target does not identify the sampled texture.
		const textureType_t unit0 = backEnd.glState.tmu[0].textureType;
		const textureType_t unit1 = backEnd.glState.tmu[1].textureType;
		bool wantSky = unit0 == TT_CUBIC && ( unit1 == TT_DISABLED || unit1 == TT_CUBIC );
		if ( wantSky && g_curProg != &g_progSky ) {
			g_curProg = &g_progSky;
			GLES_UseProgram( g_progSky.prog );
			GLES_UploadProgramUniforms( &g_progSky );
		} else if ( !wantSky && g_curProg != &g_progFlat ) {
			g_curProg = &g_progFlat;
			GLES_UseProgram( g_progFlat.prog );
			GLES_UploadProgramUniforms( &g_progFlat );
		}
	}
	if ( g_curProg == &g_progFlat ) {
		GLES_SyncTexgenUniforms();
	}
}

static void APIENTRY GLES_BindTexture( GLenum target, GLuint texture ) {
	GLES_SyncActiveTexture();
	int unit = backEnd.glState.currenttmu;
	if ( unit >= 0 && unit < GLES_MAX_TEXGEN_UNITS ) {
		g_unitTarget[unit] = target;
		g_unitId[unit] = texture;
	}
	glBindTexture( target, texture );
}

static void (APIENTRYP RealDrawElements)( GLenum mode, GLsizei count, GLenum type, const GLvoid *indices ) = NULL;
static void (APIENTRYP RealDrawArrays)( GLenum mode, GLint first, GLsizei count ) = NULL;

static const char *GLES_ProgramName( const glesProg_t *p ) {
	if ( p == &g_progInteraction ) return "interaction";
	if ( p == &g_progShadow ) return "shadow";
	if ( p == &g_progFlat ) return "flat";
	if ( p == &g_progEnv ) return "environment";
	if ( p == &g_progBumpyEnv ) return "bumpyEnvironment";
	if ( p == &g_progGlass ) return "glass";
	if ( p == &g_progSoft ) return "softParticle";
	if ( p == &g_progSky ) return "sky";
	if ( p == &g_progHeat ) return "heatHaze";
	if ( p == &g_progColorProcess ) return "colorProcess";
	return "none";
}

// webpixel x y: after every draw of the next frame, read one pixel of the
// default framebuffer and print each draw that changes it, with the program
// and bound texture names. Diagnostic only (synchronous reads).
static void GLES_ProbePixel( void ) {
	if ( g_pixelProbe != 2 ) return;
	++g_pixelDraw;
	GLint fb = 0;
	glGetIntegerv( GL_DRAW_FRAMEBUFFER_BINDING, &fb );
	if ( fb != 0 ) return;
	byte rgba[4];
	glReadPixels( g_pixelX, g_pixelY, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, rgba );
	const bool inRange = g_pixelDraw >= g_pixelFirst && g_pixelDraw <= g_pixelLastDraw;
	if ( !inRange && !memcmp( rgba, g_pixelLastColor, 4 ) ) return;
	memcpy( g_pixelLastColor, rgba, 4 );
	common->Printf( "WEB_PIXEL draw %d -> %d %d %d %d state 0x%llx program %s texgen %d useVtx %g inverse %g color %g %g %g %g colorArray %d tex0 %s tex1 %s tex2 %s tex3 %s tex4 %s\n",
		g_pixelDraw, rgba[0], rgba[1], rgba[2], rgba[3], (unsigned long long)backEnd.glState.glStateBits,
		GLES_ProgramName( g_curProg ), GLES_TexgenActive() ? 1 : 0,
		g_useVtxColor, g_inverseVtxColor, g_flatColor[0], g_flatColor[1], g_flatColor[2], g_flatColor[3],
		g_attribState[2].enabled ? 1 : 0, GLES_ImageName( g_unitId[0] ), GLES_ImageName( g_unitId[1] ),
		GLES_ImageName( g_unitId[2] ), GLES_ImageName( g_unitId[3] ), GLES_ImageName( g_unitId[4] ) );
	if ( g_curProg == &g_progInteraction ) {
		common->Printf( "WEB_PIXEL   light origin %g %g %g diffuse %g %g %g\n", g_glesEnvVertex[4][0], g_glesEnvVertex[4][1],
			g_glesEnvVertex[4][2], g_glesEnvFragment[0][0], g_glesEnvFragment[0][1], g_glesEnvFragment[0][2] );
	}
}

static void APIENTRY GLES_DrawElements( GLenum mode, GLsizei count, GLenum type, const GLvoid *indices ) {
	if (g_webPerf.remaining) ++g_webPerf.draws;
	GLES_SyncProgramForDraw();
	GLES_FlushInteractionEnv();
	static int diagnostics = 0;
	bool diagnose = !r_ignoreGLErrors.GetBool() && diagnostics < 12;
	if ( diagnose ) {
		GLenum err;
		while ( (err = glGetError()) != GL_NO_ERROR ) common->Printf("WebGL: before draw error 0x%x\n", err);
	}
	if ( RealDrawElements != NULL ) {
		const bool cpuIndices = g_boundIndexBuffer == 0 && indices != NULL;
		GLES_SyncVertexState( cpuIndices );
		if ( cpuIndices ) {
			// Dynamic GUI surfaces do not have an index cache. WebGL forbids
			// drawing directly from CPU memory, so upload these indices.
			if (g_webPerf.remaining) ++g_webPerf.cpuIndexDraws;
			if ( !g_scratchIndexBuffer ) GLES_GenBuffers( 1, &g_scratchIndexBuffer );
			GLES_BindBuffer( GL_ELEMENT_ARRAY_BUFFER, g_scratchIndexBuffer );
			int bytes = type == GL_UNSIGNED_INT ? 4 : type == GL_UNSIGNED_SHORT ? 2 : 1;
			GLES_BufferData( GL_ELEMENT_ARRAY_BUFFER, count * bytes, indices, GL_STREAM_DRAW );
			RealDrawElements( mode, count, type, NULL );
			GLES_ProbePixel();
			if ( diagnose ) { common->Printf("WebGL: CPU-index draw error 0x%x (%d indices)\n", glGetError(), count); ++diagnostics; }
			GLES_BindBuffer( GL_ELEMENT_ARRAY_BUFFER, 0 );
			return;
		}
		RealDrawElements( mode, count, type, indices );
		if ( diagnose ) { common->Printf("WebGL: VBO-index draw error 0x%x (%d indices)\n", glGetError(), count); ++diagnostics; }
		GLES_ProbePixel();
	}
}

static void APIENTRY GLES_DrawArrays( GLenum mode, GLint first, GLsizei count ) {
	if (g_webPerf.remaining) ++g_webPerf.draws;
	GLES_SyncProgramForDraw();
	GLES_FlushInteractionEnv();
	if ( RealDrawArrays != NULL ) {
		GLES_SyncVertexState( false );
		RealDrawArrays( mode, first, count );
		GLES_ProbePixel();
	}
}

static void APIENTRY GLES_TexParameterf( GLenum target, GLenum pname, GLfloat value ) {
	GLES_SyncActiveTexture();
	if ( pname == GL_TEXTURE_BORDER_COLOR ) return;
	if ( pname == GL_TEXTURE_LOD_BIAS_EXT ) return;
	if ( (pname == GL_TEXTURE_WRAP_S || pname == GL_TEXTURE_WRAP_T || pname == GL_TEXTURE_WRAP_R)
	     && (value == GL_CLAMP || value == GL_CLAMP_TO_BORDER) ) value = GL_CLAMP_TO_EDGE;
	glTexParameterf( target, pname, value );
}
static void APIENTRY GLES_TexParameterfv( GLenum target, GLenum pname, const GLfloat *values ) {
	if ( pname != GL_TEXTURE_BORDER_COLOR ) GLES_TexParameterf(target, pname, values[0]);
}

static void APIENTRY GLES_EnableClientState( GLenum cap ) {
	if ( cap == (GLenum)GL_VERTEX_ARRAY ) {
		GLES_AttribEnabled( 0, true );
	} else if ( cap == (GLenum)GL_COLOR_ARRAY ) {
		GLES_AttribEnabled( 2, true );
		g_useVtxColor = 1.0f;
		GLES_UploadUseVtx();
	} else if ( cap == (GLenum)GL_TEXTURE_COORD_ARRAY ) {
		GLES_AttribEnabled( 1, true );
	} else if ( cap == (GLenum)GL_NORMAL_ARRAY ) {
		GLES_AttribEnabled( 3, true );
	}
}

static void APIENTRY GLES_DisableClientState( GLenum cap ) {
	if ( cap == (GLenum)GL_VERTEX_ARRAY ) {
		GLES_AttribEnabled( 0, false );
	} else if ( cap == (GLenum)GL_COLOR_ARRAY ) {
		GLES_AttribEnabled( 2, false );
		g_useVtxColor = 0.0f;
		g_inverseVtxColor = 0.0f;
		GLES_UploadUseVtx();
	} else if ( cap == (GLenum)GL_TEXTURE_COORD_ARRAY ) {
		GLES_AttribEnabled( 1, false );
	} else if ( cap == (GLenum)GL_NORMAL_ARRAY ) {
		GLES_AttribEnabled( 3, false );
	}
}

// Matrix mirror
static void APIENTRY GLES_MatrixMode( GLenum mode ) {
	g_glesMode = mode;
}

static void APIENTRY GLES_LoadMatrixf( const GLfloat *m ) {
	float *d = GLES_CurMatrix();
	for ( int i = 0; i < 16; i++ ) {
		d[i] = m[i];
	}
	GLES_SyncMVP();
}

static void APIENTRY GLES_LoadIdentity( void ) {
	GLES_MatIdentity( GLES_CurMatrix() );
	GLES_SyncMVP();
}

static void APIENTRY GLES_PushMatrix( void ) {
	if ( g_glesMode == GL_PROJECTION ) {
		if ( g_mProjDepth < GLES_MSTACK_DEPTH ) {
			for ( int i = 0; i < 16; i++ ) {
				g_mProjStack[g_mProjDepth][i] = g_mProj[i];
			}
			g_mProjDepth++;
		}
	} else if ( g_glesMode == GL_TEXTURE ) {
		if ( g_mTexDepth < GLES_MSTACK_DEPTH ) {
			for ( int i = 0; i < 16; i++ ) {
				g_mTexStack[g_mTexDepth][i] = g_mTex[i];
			}
			g_mTexDepth++;
		}
	} else {
		if ( g_mMVDepth < GLES_MSTACK_DEPTH ) {
			for ( int i = 0; i < 16; i++ ) {
				g_mMVStack[g_mMVDepth][i] = g_mMV[i];
			}
			g_mMVDepth++;
		}
	}
}

static void APIENTRY GLES_PopMatrix( void ) {
	if ( g_glesMode == GL_PROJECTION ) {
		if ( g_mProjDepth > 0 ) {
			g_mProjDepth--;
			for ( int i = 0; i < 16; i++ ) {
				g_mProj[i] = g_mProjStack[g_mProjDepth][i];
			}
		}
	} else if ( g_glesMode == GL_TEXTURE ) {
		if ( g_mTexDepth > 0 ) {
			g_mTexDepth--;
			for ( int i = 0; i < 16; i++ ) {
				g_mTex[i] = g_mTexStack[g_mTexDepth][i];
			}
		}
	} else {
		if ( g_mMVDepth > 0 ) {
			g_mMVDepth--;
			for ( int i = 0; i < 16; i++ ) {
				g_mMV[i] = g_mMVStack[g_mMVDepth][i];
			}
		}
	}
	GLES_SyncMVP();
}

static void APIENTRY GLES_Ortho( GLdouble left, GLdouble right, GLdouble bottom, GLdouble top, GLdouble zNear, GLdouble zFar ) {
	float *m = GLES_CurMatrix();
	float tx = (float)( -( right + left ) / ( right - left ) );
	float ty = (float)( -( top + bottom ) / ( top - bottom ) );
	float tz = (float)( -( zFar + zNear ) / ( zFar - zNear ) );
	for ( int i = 0; i < 16; i++ ) {
		m[i] = 0.0f;
	}
	m[0] = (float)( 2.0 / ( right - left ) );
	m[5] = (float)( 2.0 / ( top - bottom ) );
	m[10] = (float)( -2.0 / ( zFar - zNear ) );
	m[12] = tx; m[13] = ty; m[14] = tz; m[15] = 1.0f;
	GLES_SyncMVP();
}

static void APIENTRY GLES_Frustum( GLdouble left, GLdouble right, GLdouble bottom, GLdouble top, GLdouble zNear, GLdouble zFar ) {
	float *m = GLES_CurMatrix();
	for ( int i = 0; i < 16; i++ ) {
		m[i] = 0.0f;
	}
	m[0] = (float)( 2.0 * zNear / ( right - left ) );
	m[5] = (float)( 2.0 * zNear / ( top - bottom ) );
	m[8] = (float)( ( right + left ) / ( right - left ) );
	m[9] = (float)( ( top + bottom ) / ( top - bottom ) );
	m[10] = (float)( -( zFar + zNear ) / ( zFar - zNear ) );
	m[11] = -1.0f;
	m[14] = (float)( -( 2.0 * zFar * zNear ) / ( zFar - zNear ) );
	GLES_SyncMVP();
}

// Legacy texture uploads -> sized GLES3 internal formats. Luminance maps
// are uploaded as R8/RG8 with texture swizzle (replicates luma into RGB);
// BGR(A) pixel data (desktop GL accepts it, GLES3 doesn't) is swizzled on
// the CPU. Compressed (S3TC) uploads have no WebGL2 guarantee and stay
// no-ops (glConfig.textureCompressionAvailable=false keeps the engine from
// requesting them for normal images).
static void APIENTRY GLES_TexImage2D( GLenum target, GLint level, GLint internalFormat, GLsizei width, GLsizei height, GLint border, GLenum format, GLenum type, const GLvoid *pixels ) {
	GLES_SyncActiveTexture();
	GLenum internal = (GLenum)internalFormat;
	GLenum fmt = format;
	GLenum typ = type;
	bool swizzleL = false, swizzleLA = false;
	const GLvoid *data = pixels;
	byte *converted = NULL;

	// WebGL2 requires UNSIGNED_INT (not UNSIGNED_BYTE) with 24-bit depth
	// textures (see idImage::CopyDepthbuffer for _currentDepth).
	if ( fmt == (GLenum)GL_DEPTH_COMPONENT ) {
		// Match the window's packed depth/stencil attachment for WebGL blits.
		internal = GL_DEPTH24_STENCIL8;
		fmt = GL_DEPTH_STENCIL;
		typ = GL_UNSIGNED_INT_24_8;
		GLint texture = 0;
		glGetIntegerv( GL_TEXTURE_BINDING_2D, &texture );
		g_depthTextures.insert( (GLuint)texture );
	}

	switch ( internalFormat ) {
	case GL_LUMINANCE8:
	case GL_INTENSITY8:
	case GL_LUMINANCE:
		internal = GL_R8; fmt = GL_RED; swizzleL = true;
		break;
	case GL_LUMINANCE8_ALPHA8:
	case GL_LUMINANCE_ALPHA:
		internal = GL_RG8; fmt = GL_RG; swizzleLA = true;
		break;
	case GL_RGBA:
		internal = GL_RGBA8;
		break;
	case GL_RGB:
		internal = GL_RGB8;
		break;
	case GL_BGR_EXT:
		internal = GL_RGB8; fmt = GL_RGB;
		break;
	case GL_BGRA_EXT:
		internal = GL_RGBA8; fmt = GL_RGBA;
		break;
	default:
		break;
	}

	if ( pixels != NULL && type == GL_UNSIGNED_BYTE
	     && ( format == (GLenum)GL_BGR_EXT || format == (GLenum)GL_BGRA_EXT ) ) {
		int bpp = ( format == (GLenum)GL_BGR_EXT ) ? 3 : 4;
		size_t n = (size_t)width * (size_t)height * bpp;
		converted = (byte *)malloc( n );
		if ( converted != NULL ) {
			const byte *s = (const byte *)pixels;
			for ( size_t i = 0; i < n; i += bpp ) {
				converted[i] = s[i + 2];
				converted[i + 1] = s[i + 1];
				converted[i + 2] = s[i];
				if ( bpp == 4 ) {
					converted[i + 3] = s[i + 3];
				}
			}
			data = converted;
			fmt = ( bpp == 3 ) ? (GLenum)GL_RGB : (GLenum)GL_RGBA;
		}
	}

	// Desktop storage hints (RGB5, RGBA4, luminance) may be combined
	// with RGBA source pixels. WebGL requires matching sized formats.
	if ( format == GL_RGBA ) {
		internal = GL_RGBA8; fmt = GL_RGBA; swizzleL = swizzleLA = false;
	} else if ( format == GL_RGB ) {
		internal = GL_RGB8; fmt = GL_RGB; swizzleL = swizzleLA = false;
	}
	glTexImage2D( target, level, (GLint)internal, width, height, 0, fmt, typ, data );

	if ( swizzleL ) {
		GLint sw[4] = { GL_RED, GL_RED, GL_RED, GL_ONE };
		glTexParameteriv( target, GL_TEXTURE_SWIZZLE_RGBA, sw );
	} else if ( swizzleLA ) {
		GLint sw[4] = { GL_RED, GL_RED, GL_RED, GL_GREEN };
		glTexParameteriv( target, GL_TEXTURE_SWIZZLE_RGBA, sw );
	}

	if ( converted != NULL ) {
		free( converted );
	}
}

static void APIENTRY GLES_CopyTexSubImage2D( GLenum target, GLint level, GLint xoffset, GLint yoffset,
                                           GLint x, GLint y, GLsizei width, GLsizei height ) {
	GLES_SyncActiveTexture();
	GLint texture = 0;
	glGetIntegerv( GL_TEXTURE_BINDING_2D, &texture );
	if ( target != GL_TEXTURE_2D || g_depthTextures.count((GLuint)texture) == 0 ) {
		glCopyTexSubImage2D( target, level, xoffset, yoffset, x, y, width, height );
		return;
	}
	// WebGL does not support copying depth through CopyTexSubImage2D.
	// Blit the packed depth/stencil attachment into the sampled texture.
	GLint readFB = 0, drawFB = 0;
	glGetIntegerv( GL_READ_FRAMEBUFFER_BINDING, &readFB );
	glGetIntegerv( GL_DRAW_FRAMEBUFFER_BINDING, &drawFB );
	if ( !g_depthCopyFramebuffer ) glGenFramebuffers(1, &g_depthCopyFramebuffer);
	glBindFramebuffer( GL_DRAW_FRAMEBUFFER, g_depthCopyFramebuffer );
	glFramebufferTexture2D( GL_DRAW_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, target, texture, level );
	GLenum none = GL_NONE;
	glDrawBuffers(1, &none);
	GLboolean scissor = glIsEnabled(GL_SCISSOR_TEST);
	glDisable(GL_SCISSOR_TEST);
	// Only depth is sampled (_currentDepth). ANGLE's D3D11 backend copies a
	// combined depth/stencil blit through CPU staging memory; depth alone
	// takes its GPU path and yields the same depth texels.
	glBlitFramebuffer( x, y, x + width, y + height,
	                   xoffset, yoffset, xoffset + width, yoffset + height,
	                   r_webDepthOnlyCopy.GetBool() ? GL_DEPTH_BUFFER_BIT : GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT, GL_NEAREST );
	if (scissor) glEnable(GL_SCISSOR_TEST);
	glBindFramebuffer( GL_READ_FRAMEBUFFER, readFB );
	glBindFramebuffer( GL_DRAW_FRAMEBUFFER, drawFB );
}

// ---------------------------------------------------------------------------
// qgl* resolution: real GLES3 functions where they exist, replacements above
// for removed fixed-function entry points, no-op stubs for the rest.
// Never FatalErrors (the desktop loader does).
// ---------------------------------------------------------------------------
static void GLES_Info_f( const idCmdArgs & ) {
	GLint viewport[4], scissor[4], framebuffer = 0, program = 0;
	glGetIntegerv(GL_VIEWPORT, viewport);
	glGetIntegerv(GL_SCISSOR_BOX, scissor);
	glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &framebuffer);
	glGetIntegerv(GL_CURRENT_PROGRAM, &program);
	common->Printf("WebGL state: viewport %d %d %d %d, scissor %d %d %d %d, framebuffer %d, program %d\n",
	               viewport[0], viewport[1], viewport[2], viewport[3],
	               scissor[0], scissor[1], scissor[2], scissor[3], framebuffer, program);
}

static void APIENTRY GLES_ReadPixels( GLint x, GLint y, GLsizei width, GLsizei height,
                                     GLenum format, GLenum type, void *pixels ) {
	if ( format != GL_RGB || type != GL_UNSIGNED_BYTE ) {
		glReadPixels( x, y, width, height, format, type, pixels );
		return;
	}
	// WebGL guarantees RGBA/UNSIGNED_BYTE readback, while the engine's
	// objective screenshots request RGB with the current pack alignment.
	GLint alignment = 4;
	glGetIntegerv( GL_PACK_ALIGNMENT, &alignment );
	const int stride = ( width * 3 + alignment - 1 ) & ~( alignment - 1 );
	byte *rgba = (byte *)R_StaticAlloc( width * height * 4 );
	glReadPixels( x, y, width, height, GL_RGBA, GL_UNSIGNED_BYTE, rgba );
	byte *rgb = (byte *)pixels;
	for ( int row = 0; row < height; ++row ) {
		for ( int col = 0; col < width; ++col ) {
			memcpy( rgb + row * stride + col * 3, rgba + ( row * width + col ) * 4, 3 );
		}
	}
	R_StaticFree( rgba );
}

void R_GLES_LoadFunctions( void ) {
	// GLimp_Init created a context. Cached names and emulated state belong
	// to the previous context and must not survive a full vid_restart.
	g_scratchIndexBuffer = 0;
	g_boundIndexBuffer = g_boundArrayBuffer = 0;
	memset(g_uniformState, 0, sizeof(g_uniformState));
	memset(g_attribState, 0, sizeof(g_attribState));
	memset(g_defaultAttribs, 0, sizeof(g_defaultAttribs));
	g_defaultElement = g_actualArrayBuffer = g_currentVao = 0;
	++g_vertexStateSerial;
	g_vertexSyncVao = ~0u;
	g_vaoCache.clear();	// names belong to the previous context
	g_bufferInfo.clear();
	g_boundProgram = 0;
	g_activeTexture = g_wantedActiveTexture = GL_TEXTURE0;
	g_interactionEnvDirty = true;
	// Query names belong to the previous context.
	g_webGpu.pending.Clear();
	g_webGpu.pool.Clear();
	g_webGpu.active = g_webGpu.remaining = 0;
	g_webGpu.pass = -1;
	GLES_ResetStencilState();
	g_depthCopyFramebuffer = 0;
	g_depthTextures.clear();
	memset( g_genEn, 0, sizeof(g_genEn) );
	memset( g_genPlane, 0, sizeof(g_genPlane) );
	memset( g_unitId, 0, sizeof(g_unitId) );
	for ( int unit = 0; unit < GLES_MAX_TEXGEN_UNITS; ++unit ) g_unitTarget[unit] = GL_TEXTURE_2D;
	memset( g_glesEnvVertex, 0, sizeof(g_glesEnvVertex) );
	memset( g_glesEnvFragment, 0, sizeof(g_glesEnvFragment) );
	memset( g_vertexLocal, 0, sizeof(g_vertexLocal) );
	g_mProjDepth = g_mMVDepth = g_mTexDepth = 0;
	g_vertexProgramEnabled = g_fragmentProgramEnabled = g_cpuShadowVertices = false;
	g_shadowExtrude = false;
	g_alphaEnabled = false;
	g_alphaRef = 0.5f;
	g_alphaFunc = GL_ALWAYS;
	g_useVtxColor = 0.0f;
	g_inverseVtxColor = 0.0f;
	for ( int chan = 0; chan < 4; ++chan ) g_flatColor[chan] = 1.0f;
	glesProg_t *programs[] = { &g_progInteraction, &g_progShadow, &g_progFlat, &g_progEnv,
		&g_progBumpyEnv, &g_progGlass, &g_progSoft, &g_progSky, &g_progHeat, &g_progColorProcess };
	for ( size_t i = 0; i < sizeof(programs)/sizeof(programs[0]); ++i ) programs[i]->prog = 0;
	g_curProg = NULL;
	g_lastVid = g_lastFid = -1;
	g_inInteraction = 0;
	cmdSystem->AddCommand("webglinfo", GLES_Info_f, CMD_FL_RENDERER, "prints browser GL viewport and framebuffer state");
	cmdSystem->AddCommand("webgpu", GLES_Gpu_f, CMD_FL_RENDERER, "GPU time per render pass from timer queries (optional 10..600 frames)");
	cmdSystem->AddCommand("webpixel", GLES_Pixel_f, CMD_FL_RENDERER, "trace which draws change one framebuffer pixel in the next frame");
	cmdSystem->AddCommand("websurfaces", GLES_Surfaces_f, CMD_FL_RENDERER, "list the next view's draw surfaces overlapping an optional x1 y1 x2 y2 region");
	cmdSystem->AddCommand("webperf", GLES_Perf_f, CMD_FL_RENDERER, "sample browser frame timing and rendering calls (optional 30..600 frames)");
#define QGLPROC( name, rettype, args ) \
	q##name = ( rettype( APIENTRYP ) args )GLimp_ExtensionPointer( #name ); \
	if ( !q##name ) { \
		q##name = GLES_NopTyped; \
	}
#include "renderer/qgl_proc.h"
#undef QGLPROC

	// Replaced fixed-function entry points (declared via QGLPROC above).
	qglEnable = GLES_Enable;
	qglDisable = GLES_Disable;
	qglClearDepth = GLES_ClearDepth;
	qglDepthRange = GLES_DepthRange;
	qglAlphaFunc = GLES_AlphaFunc;
	qglColor3f = GLES_Color3f;
	qglColor4f = GLES_Color4f;
	qglColor3fv = GLES_Color3fv;
	qglColor4fv = GLES_Color4fv;
	qglVertexPointer = GLES_VertexPointer;
	qglColorPointer = GLES_ColorPointer;
	qglTexCoordPointer = GLES_TexCoordPointer;
	qglNormalPointer = GLES_NormalPointer;
	qglEnableClientState = GLES_EnableClientState;
	qglDisableClientState = GLES_DisableClientState;
	qglMatrixMode = GLES_MatrixMode;
	qglLoadMatrixf = GLES_LoadMatrixf;
	qglLoadIdentity = GLES_LoadIdentity;
	qglPushMatrix = GLES_PushMatrix;
	qglPopMatrix = GLES_PopMatrix;
	qglOrtho = GLES_Ortho;
	qglFrustum = GLES_Frustum;
	qglTexImage2D = GLES_TexImage2D;
	qglCopyTexSubImage2D = GLES_CopyTexSubImage2D;
	qglReadPixels = GLES_ReadPixels;
	qglReadBuffer = GLES_NopTyped; // default WebGL framebuffer already reads BACK
	qglTexParameterf = GLES_TexParameterf;
	qglTexParameterfv = GLES_TexParameterfv;
	qglTexGenfv = GLES_TexGenfv;
	// Emscripten may resolve removed desktop symbols to error-producing
	// compatibility entry points rather than NULL. Never call those.
	qglTexGenf = GLES_NopTyped;
	qglTexEnvi = GLES_NopTyped;
	qglTexEnvf = GLES_NopTyped;
	qglShadeModel = GLES_NopTyped;
	qglPolygonMode = GLES_NopTyped;
	qglDrawBuffer = GLES_NopTyped;
	qglBindTexture = GLES_BindTexture;
	// Everything that depends on the selected texture unit first sends a
	// deferred GLES_ActiveTexture selection.
	qglTexParameteri = GLES_TexParameteri;
	qglTexSubImage2D = GLES_TexSubImage2D;
	qglTexImage3D = GLES_TexImage3D;
	qglCopyTexImage2D = GLES_CopyTexImage2D;
	qglGetIntegerv = GLES_GetIntegerv;
	qglGetFloatv = GLES_GetFloatv;
	qglGetBooleanv = GLES_GetBooleanv;
	// qglTexGenf modes are ignored (planes carry the data); keep the loader
	// result (real function if it exists, no-op otherwise).
	RealDrawElements = qglDrawElements;
	RealDrawArrays = qglDrawArrays;
	qglDrawElements = GLES_DrawElements;
	qglDrawArrays = GLES_DrawArrays;

	// Core GLES3 equivalents for the multitexture / VBO / stencil entry
	// points the engine actually uses (resolved by core name, not ARB name).
	qglActiveTextureARB = GLES_ActiveTexture;
	qglStencilOp = GLES_StencilOp;
	qglStencilFunc = GLES_StencilFunc;
	qglBindBufferARB = GLES_BindBuffer;
	qglDeleteBuffersARB = GLES_DeleteBuffers;
	qglGenBuffersARB = GLES_GenBuffers;
	qglIsBufferARB = (PFNGLISBUFFERARBPROC)GLimp_ExtensionPointer( "glIsBuffer" );
	qglBufferDataARB = GLES_BufferData;
	qglBufferSubDataARB = GLES_BufferSubData;
	qglGetBufferParameterivARB = (PFNGLGETBUFFERPARAMETERIVARBPROC)GLimp_ExtensionPointer( "glGetBufferParameteriv" );
	qglGetBufferPointervARB = (PFNGLGETBUFFERPOINTERVARBPROC)GLimp_ExtensionPointer( "glGetBufferPointerv" );
	if ( !qglBindBufferARB ) qglBindBufferARB = GLES_NopTyped;
	if ( !qglDeleteBuffersARB ) qglDeleteBuffersARB = GLES_NopTyped;
	if ( !qglGenBuffersARB ) qglGenBuffersARB = GLES_NopTyped;
	if ( !qglIsBufferARB ) qglIsBufferARB = GLES_NopTyped;
	if ( !qglBufferDataARB ) qglBufferDataARB = GLES_NopTyped;
	if ( !qglBufferSubDataARB ) qglBufferSubDataARB = GLES_NopTyped;
	if ( !qglGetBufferParameterivARB ) qglGetBufferParameterivARB = GLES_NopTyped;
	if ( !qglGetBufferPointervARB ) qglGetBufferPointervARB = GLES_NopTyped;
	// No glGetBufferSubData / glMapBuffer in GLES3 core: custom stubs.
	qglGetBufferSubDataARB = GLES_NopTyped;
	qglMapBufferARB = GLES_MapBufferARB;
	qglUnmapBufferARB = GLES_NopTyped;

	// Stencil-separate is core in WebGL2; two-sided ATI ext does not exist.
	qglStencilOpSeparate = GLES_StencilOpSeparate;
	qglActiveStencilFaceEXT = GLES_NopTyped;
	qglDepthBoundsEXT = GLES_NopTyped;
	qglDebugMessageCallbackARB = GLES_NopTyped;

	// Fixed-function multitexture client state: no-ops (ARB2 path only).
	qglClientActiveTextureARB = GLES_NopTyped;
	qglMultiTexCoord2fARB = GLES_NopTyped;
	qglMultiTexCoord2fvARB = GLES_NopTyped;
	qglColorTableEXT = GLES_NopTyped;

	// Compressed uploads resolve to core functions when the S3TC extension
	// is present (see R_GLES_InitConfig); readback has no GLES equivalent.
	qglCompressedTexImage2DARB = GLES_CompressedTexImage2D;
	qglGetCompressedTexImageARB = GLES_NopTyped;

	// ARB program emulation (real GLSL programs, selected by id pair).
	qglProgramStringARB = GLES_ProgramStringARB;
	qglBindProgramARB = GLES_BindProgramARB;
	qglGenProgramsARB = GLES_GenProgramsARB;
	qglProgramEnvParameter4fvARB = GLES_ProgramEnvParameter4fvARB;
	qglProgramLocalParameter4fvARB = GLES_ProgramLocalParameter4fvARB;
	qglVertexAttribPointerARB = GLES_VertexAttribPointerARB;
	qglEnableVertexAttribArrayARB = GLES_EnableVertexAttribArrayARB;
	qglDisableVertexAttribArrayARB = GLES_DisableVertexAttribArrayARB;

	// Matrix mirror starts at identity (matches a fresh GL context).
	GLES_MatIdentity( g_mProj );
	GLES_MatIdentity( g_mMV );
	GLES_MatIdentity( g_mTex );

	// Gamma-neutral default for fragment env slot 21 until
	// RB_SetProgramEnvironment() writes the real values.
	g_glesEnvFragment[21][0] = g_glesEnvFragment[21][1] = g_glesEnvFragment[21][2]
		= g_glesEnvFragment[21][3] = 1.0f;

	common->Printf( "WebGL: GLES function pointers resolved (fixed-function reimplemented, rest stubbed)\n" );
}

static void GLES_InitAnisotropy( EMSCRIPTEN_WEBGL_CONTEXT_HANDLE context ) {
	glConfig.anisotropicAvailable = false;
	glConfig.maxTextureAnisotropy = 1.0f;
	if ( context <= 0 || !emscripten_webgl_enable_extension(context, "EXT_texture_filter_anisotropic") ) return;
	GLfloat maximum = 1.0f;
	glGetFloatv( GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT, &maximum );
	if ( maximum >= 1.0f ) {
		glConfig.anisotropicAvailable = true;
		glConfig.maxTextureAnisotropy = maximum;
	}
}

void R_GLES_InitConfig( void ) {
	// WebGL2 guarantees: 8+ texture image units, cube maps, NPOT, stencil8.
	// Depth-bounds and debug output are absent.
	// The desktop extension path is skipped, including its stencil setup.
	// GL_ZERO would erase the volume count instead of tracking crossings.
	tr.stencilIncr = GL_INCR_WRAP;
	tr.stencilDecr = GL_DECR_WRAP;
	glConfig.multitextureAvailable = true;
	glConfig.maxTextureUnits = 8;
	glConfig.maxTextureCoords = 8;
	glConfig.maxTextureImageUnits = 8;
	glConfig.textureEnvCombineAvailable = true; // passes the minimum-set check; TexEnv calls are stubbed
	glConfig.cubeMapAvailable = true;
	glConfig.envDot3Available = true;
	glConfig.textureNonPowerOfTwoAvailable = true;
	glConfig.anisotropicAvailable = false;
	glConfig.maxTextureAnisotropy = 1.0f;

	// S3TC is optional on the web (desktop browsers ~always expose
	// WEBGL_compressed_texture_s3tc, mobile ~never). Enable the extension
	// and probe for it; the engine's existing compressed paths (and the
	// qglCompressedTexImage2DARB mapping in R_GLES_LoadFunctions) just work
	// when present, and the engine transparently uses uncompressed images
	// when absent (same flag desktop drivers use).
	glConfig.textureCompressionAvailable = false;
#ifdef __EMSCRIPTEN__
	EMSCRIPTEN_WEBGL_CONTEXT_HANDLE webglCtx = emscripten_webgl_get_current_context();
	GLES_InitAnisotropy( webglCtx );
	g_webGpu.available = webglCtx > 0 && emscripten_webgl_enable_extension( webglCtx, "EXT_disjoint_timer_query_webgl2" );
	if ( webglCtx > 0 ) {
		emscripten_webgl_enable_extension( webglCtx, "WEBGL_compressed_texture_s3tc" );
	}
#endif
	{
		GLint numExt = 0;
		glGetIntegerv( GL_NUM_EXTENSIONS, &numExt );
		for ( GLint i = 0; i < numExt; i++ ) {
			const char *e = (const char *)glGetStringi( GL_EXTENSIONS, (GLuint)i );
			if ( e != NULL && strcmp( e, "GL_EXT_texture_compression_s3tc" ) == 0 ) {
				glConfig.textureCompressionAvailable = true;
				break;
			}
		}
	}
	common->Printf( "WebGL: S3TC texture compression %s\n",
		glConfig.textureCompressionAvailable ? "available" : "unavailable (using uncompressed images)" );
	common->Printf( "WebGL: anisotropic filtering %s (maximum %gx)\n",
		glConfig.anisotropicAvailable ? "available" : "unavailable",
		glConfig.maxTextureAnisotropy );
	// Real VBOs: uploads already go through BufferData/SubData (core) and
	// Position() binds + returns offsets (see idVertexCache::Position), so
	// the vertex-cache design works unmodified once this flag is on.
	glConfig.ARBVertexBufferObjectAvailable = true;
	glConfig.ARBVertexProgramAvailable = true; // emulated via GLSL programs
	glConfig.ARBFragmentProgramAvailable = true;
	glConfig.depthBoundsTestAvailable = false;
	glConfig.glDebugOutputAvailable = false;

	// WebGL2-safe submission defaults (applied every vid_restart; the
	// desktop presets are meaningless for the GLES backend).
	extern idCVar r_useIndexBuffers;
	r_useIndexBuffers.SetInteger( 1 ); // indexCache VBO offsets (client indexes are invalid in GLES3)

	// Synthetic extension string so any stray R_CheckExtension() calls find
	// the tokens this backend claims instead of dereferencing NULL
	// (glGetString(GL_EXTENSIONS) returns NULL on core profiles).
	static const char *s_glesExtensions =
		"GL_ARB_multitexture GL_ARB_texture_env_combine GL_ARB_texture_cube_map "
		"GL_ARB_texture_env_dot3 GL_ARB_texture_non_power_of_two "
		"GL_ARB_vertex_program GL_ARB_fragment_program WebGL2 GLES3 dhewm3-gles";
	glConfig.extensions_string = s_glesExtensions;

	common->Printf( "WebGL: GLES config initialized (VBO/index buffers on, shared GPU/private projected shadows)\n" );
}
