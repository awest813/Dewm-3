#ifndef __WEB_RENDER_TIMING_H__
#define __WEB_RENDER_TIMING_H__

#ifdef __EMSCRIPTEN__
enum { WEB_RENDER_PHASE_COUNT = 20 };
extern "C" double R_GLES_PerfTimestamp();
extern "C" void R_GLES_PerfPhase( int phase, double cpuMs );
extern "C" void R_GLES_PerfLightTriangles( int inputFaces, int keptFaces, bool fusedBounds );

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
