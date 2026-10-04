// Browser render pacing; simulation continues to use the engine's fixed ticks.
#ifndef WEB_FRAME_PACING_H
#define WEB_FRAME_PACING_H

static inline bool Web_ValidFrameLimit(int limit) {
	return limit == 0 || limit == 30 || limit == 60;
}

struct webFramePacing_t {
	double nextFrame = 0;
	int previousLimit = -1;

	bool ShouldRender(double now, int limit) {
		if (!Web_ValidFrameLimit(limit)) limit = 60;
		if (limit != previousLimit) {
			previousLimit = limit;
			nextFrame = now;
		}
		if (!limit) return true;
		// Small rAF timestamp jitter must not halve a 60 Hz display's rate.
		if (now + 0.5 < nextFrame) return false;
		const double interval = 1000.0 / limit;
		nextFrame += interval;
		// Skip missed deadlines after loading/backgrounding, without bursts.
		if (nextFrame <= now + 0.5) nextFrame = now + interval;
		return true;
	}
};

#endif
