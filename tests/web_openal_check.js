// Checks web/openal_stereo.js against native OpenAL Soft panning measurements.
//   node tests/web_openal_check.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const native = require('./openal_native_panning.js');

// Minimal globals: the post-js patches the Emscripten AL object.
function load() {
  const sandbox = { Math, AudioNode: function () {}, AL: { initSourcePanner() {}, buffers: [{}] } };
  sandbox.AudioNode.prototype.connect = function () {};
  sandbox.AudioNode.prototype.disconnect = function () {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/openal_stereo.js'), 'utf8'), sandbox);
  return sandbox.AL;
}
const AL = load();
let failures = 0;
for (const [name, pos, expected] of native) {
  const g = AL.openalStereoGains(pos[0], pos[1], pos[2]);
  const err = Math.max(Math.abs(Math.abs(g[0]) - expected[0]), Math.abs(Math.abs(g[1]) - expected[1]));
  if (!(err < 0.002)) {
    failures++;
    console.error(`FAIL ${name}: web ${g.map(v => v.toFixed(4))} native ${expected}`);
  }
}
// The patched source graph must also keep rolloff 0 at full level for any
// reference distance (a WebAudio PannerNode with refDistance 0 is silent).
if (Math.abs(AL.openalStereoGains(0, 0, 0)[0] - 0.5957) > 0.001) { failures++; console.error('FAIL source at the listener'); }
if (failures) { console.error(`${failures} OpenAL panning checks failed`); process.exit(1); }
console.log(`PASS: ${native.length} native OpenAL Soft panning directions`);
