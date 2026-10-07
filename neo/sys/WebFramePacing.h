// Browser render pacing; simulation continues to use the engine's fixed ticks.
#ifndef WEB_FRAME_PACING_H
#define WEB_FRAME_PACING_H

static inline bool Web_ValidFrameLimit(int limit) {
	return limit == 0 || limit == 30 || limit == 60;
}

/*
Rendered frames follow animation callbacks, which arrive once per display
refresh (or less often under browser power saving). A cap renders a callback
once its deadline is due; the deadline then advances one cap interval.

When the cap divides the display refresh (30 or 60 FPS at 60/120/240 Hz),
the cap is locked to refreshes: each rendered frame lasts exactly the same
number of refreshes. A cap equal to the refresh renders every callback.
Displays rarely run at exactly 60.000 Hz, so a deadline advancing by the
nominal interval slowly drifts against the callbacks and eventually drops or
doubles a frame. Locked pacing therefore nudges the deadline toward the
callbacks it renders (a small phase-locked loop) and accepts callbacks within
half a refresh of it, which tolerates the jitter of callback start times.
Other refresh rates (75, 144 Hz) keep the capped average rate; their frames
cannot be evenly spaced.
*/
struct webFramePacing_t {
	double nextFrame = 0;
	int previousLimit = -1;
	// Display refresh estimate (ms; 0 = unknown) over the last second of
	// callbacks: elapsed time divided by the refreshes it spans. The median
	// interval counts the refreshes in each interval, so a stalled frame
	// counts two or more and a delayed callback's long and short intervals
	// count one each (or two and none). Start-time delays then cancel across
	// the window instead of biasing the estimate.
	static const int PERIOD_SAMPLES = 63;
	double period = 0, lastCallback = 0;
	double intervals[PERIOD_SAMPLES] = {};
	int intervalCount = 0, intervalNext = 0;

	void ObserveCallback(double now) {
		const double dt = now - lastCallback;
		const bool first = lastCallback == 0;
		lastCallback = now;
		if (first || dt <= 0 || dt > 250) return;	// startup, clock reset, hidden tab
		intervals[intervalNext] = dt;
		intervalNext = (intervalNext + 1) % PERIOD_SAMPLES;
		if (intervalCount < PERIOD_SAMPLES) ++intervalCount;
		// Insertion sort: at most 63 values, and engine headers that redefine
		// C string functions rule out <algorithm> here.
		double sorted[PERIOD_SAMPLES];
		for (int i = 0; i < intervalCount; ++i) {
			int j = i;
			for (; j > 0 && sorted[j - 1] > intervals[i]; --j) sorted[j] = sorted[j - 1];
			sorted[j] = intervals[i];
		}
		const double median = sorted[intervalCount / 2];
		double elapsed = 0;
		int refreshes = 0;
		for (int i = 0; i < intervalCount; ++i) {
			elapsed += intervals[i];
			refreshes += (int)(intervals[i] / median + 0.5);
		}
		period = refreshes > 0 ? elapsed / refreshes : median;
	}

	// Refreshes per capped frame when the cap divides the refresh, else 0.
	int LockedRefreshes(int limit) const {
		if (!limit || period <= 0) return 0;
		const double interval = 1000.0 / limit;
		const int refreshes = (int)(interval / period + 0.5);
		if (refreshes < 1) return 0;
		const double error = refreshes * period - interval;
		return error > -0.03 * interval && error < 0.03 * interval ? refreshes : 0;
	}

	bool ShouldRender(double now, int limit) {
		if (!Web_ValidFrameLimit(limit)) limit = 60;
		ObserveCallback(now);
		if (limit != previousLimit) {
			previousLimit = limit;
			nextFrame = now;
		}
		if (!limit) return true;
		const double interval = 1000.0 / limit;
		const int refreshes = LockedRefreshes(limit);
		const bool locked = refreshes > 0;
		if (refreshes == 1) {
			// The cap equals the refresh: browsers deliver at most one callback
			// per refresh, so every callback renders, including one that
			// arrives early after a stalled frame.
			nextFrame = now + interval;
			return true;
		}
		// Callback start times jitter by milliseconds, and a "60 Hz" display
		// may run slightly fast. Unlocked caps accept a callback a quarter
		// interval early; the deadline still advances one interval per
		// rendered frame, so faster displays keep the capped average rate.
		const double early = locked ? period * 0.5 : interval * 0.25;
		if (now + early < nextFrame) return false;
		const double error = now - nextFrame;
		nextFrame += interval;
		if (locked && error < early) {
			nextFrame += error * 0.1;
		} else if (locked) {
			// A whole refresh late (the browser skipped one): restart the
			// schedule here so the next frame is a full interval later.
			nextFrame = now + interval;
		}
		// Skip missed deadlines after loading/backgrounding, without bursts.
		if (nextFrame <= now + 0.5) nextFrame = now + interval;
		return true;
	}
};

#endif
