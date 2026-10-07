// Page script for cdp.mjs: loads archives, runs the frozen hangar fixture,
// posts its captures and samples frame cost. Arguments (key=value):
//   fixture=hangar      hangar (3 views, timing samples) or scenes (8 views)
//   label=<name>        capture prefix (default: build directory name)
//   compare=a,b         reference capture prefixes, e.g. native,baseline
//   frames=300          webperf / GPU sample length
//   histogram=1         also record WebGL calls per frame
//   width=640           canvas CSS width. The engine derives its projection
//                       from the window aspect, so parity captures need the
//                       native fixture's exact 640x480 (r_mode 3) buffer.
canvas.style.width = canvas.style.maxWidth = (ARGS.width || 640) + 'px';
await new Promise((resolve, reject) => {
  const s = document.createElement('script');
  s.src = '/bench/bench.js?' + Date.now();
  s.onload = resolve; s.onerror = reject;
  document.head.appendChild(s);
});
const B = __bench;
const label = ARGS.label || location.pathname.split('/').slice(-2, -1)[0] || 'web';
const frames = +(ARGS.frames || 300);
const pick = (text, re) => +(text.match(re) || [0, NaN])[1];
const summary = text => ({
  fps: pick(text, /: ([\d.]+) fps/), cpuMean: pick(text, /CPU mean ([\d.]+)/), cpuP95: pick(text, /p95 ([\d.]+)/),
  scene: pick(text, /begin, ([\d.]+) ms scene/), submit: pick(text, /scene generation, ([\d.]+) ms submit/),
});
await B.stage();
await B.launch();
const result = { label, canvas: [GLctx.drawingBufferWidth, GLctx.drawingBufferHeight] };
const fixture = ARGS.fixture || 'hangar';
result.state = await B.fixture(fixture);
await B.saveShots(label, B.views[fixture]);
if (ARGS.compare) result.compare = await B.compare(label, ARGS.compare.split(','), B.views[fixture]);
if (fixture !== 'hangar') {
  await B.upload(label + '-result.json', JSON.stringify(result, null, 1));
  return result;
}
// The fixture leaves the saved-rail view frozen with fixed ticks; sample the
// render workload with real-time ticks, then live simulation at the 60 cap.
const frozen = await B.perf(frames, 'set com_fixedTic 0; set r_webFrameLimit 0');
result.frozen = { ...summary(frozen.join('\n')), ...(await B.gpu(frames)), lines: frozen };
const live = await B.perf(frames, 'set g_stopTime 0; set r_webFrameLimit 60');
result.live = { ...summary(live.join('\n')), ...(await B.gpu(frames)) };
if (ARGS.histogram) result.calls = await B.callHistogram(3000);
await B.upload(label + '-result.json', JSON.stringify(result, null, 1));
return result;
