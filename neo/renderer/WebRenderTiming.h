#ifndef __WEB_RENDER_TIMING_H__
#define __WEB_RENDER_TIMING_H__

#ifdef __EMSCRIPTEN__
enum { WEB_RENDER_PHASE_COUNT = 20 };
extern "C" double R_GLES_PerfTimestamp();
extern "C" void R_GLES_PerfPhase( int phase, double cpuMs );
extern "C" void R_GLES_PerfLightTriangles( int inputFaces, int keptFaces, bool fusedBounds );

// GPU pass categories for the webgpu command (tr_gles.cpp).
enum {
	WEB_GPU_DEPTH_FILL, WEB_GPU_DEPTH_COPY, WEB_GPU_SHADOWS, WEB_GPU_INTERACTIONS,
	WEB_GPU_SHADER_PASSES, WEB_GPU_FOG_BLEND, WEB_GPU_POST_PROCESS, WEB_GPU_OTHER, WEB_GPU_PASS_COUNT
};
void R_GLES_GpuPass( int pass );

// Clock reads are disabled outside an explicit webperf sample. Each scope has
// its own timer, including early returns and recursive camera/mirror views.
class webRenderPhase_t {
	int phase;
	double started;
public:
	explicit webRenderPhase_t(int initialPhase) : phase(initialPhase), started(R_GLES_PerfTimestamp()) {}
	void Next(int nextPhase) {
		if (!started) return;
		double now = R_GLES_PerfTimestamp();
		R_GLES_PerfPhase(phase, now - started);
		phase = nextPhase;
		started = now;
	}
	~webRenderPhase_t() { Next(-1); }
};
#endif

#endif
