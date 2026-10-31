// Checks the web build's OpenAL EFX (web/openal_efx.js, web/openal_reverb.js)
// against native OpenAL Soft reverb responses (tests/openal_native_reverb.js).
//   node tests/web_openal_efx_check.js
//
// The post-js files run on a minimal Emscripten-like AL object and a small
// WebAudio model: gain, highshelf biquad (Chromium's coefficients), channel
// merger and splitter, and AudioWorkletNode running the worklet's own
// processor. Each native case is rebuilt through the EFX API and rendered at
// 44.1 kHz, then the loudest early samples and the 10 ms energy envelope are
// compared. The API checks cover errors and copy semantics Doom 3 relies on.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const native = require('./openal_native_reverb.js');

const RATE = native.rate, BLOCK = 128;
let failures = 0, checks = 0;
function check(ok, label) { checks++; if (!ok) { failures++; console.error('FAIL ' + label); } }

// --- WebAudio model ---------------------------------------------------------
let blockIndex = 0;
class AudioParam { constructor(v) { this.value = v; } }
class AudioNode {
  constructor(ctx, inputs, outputs) {
    this.context = ctx; this.numberOfInputs = inputs; this.numberOfOutputs = outputs;
    this.sources = [];  // [node, output, input]
    this.channelCount = 2; this.channelCountMode = 'max'; this.channelInterpretation = 'speakers';
    this.cacheBlock = -1;
  }
  connect(dest, output = 0, input = 0) {
    if (!dest.sources.some(s => s[0] === this && s[1] === output && s[2] === input)) dest.sources.push([this, output, input]);
    return dest;
  }
  disconnect() { for (const n of this.context.nodes) n.sources = n.sources.filter(s => s[0] !== this); }
  // Sum of the connections into one input, mixed to its channel count.
  input(index, n) {
    const parts = this.sources.filter(s => s[2] === index).map(s => s[0].pull(n)[s[1]]);
    let channels = parts.reduce((m, p) => Math.max(m, p.length), 0);
    if (this.channelCountMode === 'explicit') channels = this.channelCount;
    else if (this.channelCountMode === 'clamped-max') channels = Math.min(channels, this.channelCount);
    const out = [];
    for (let c = 0; c < channels; c++) out.push(new Float32Array(n));
    for (const p of parts) {
      if (p.length === channels || this.channelInterpretation === 'discrete') {
        for (let c = 0; c < Math.min(channels, p.length); c++) for (let i = 0; i < n; i++) out[c][i] += p[c][i];
      } else if (p.length === 1) {  // mono up-mix
        for (let c = 0; c < channels; c++) for (let i = 0; i < n; i++) out[c][i] += p[0][i];
      } else if (channels === 1 && p.length === 2) {  // stereo down-mix
        for (let i = 0; i < n; i++) out[0][i] += 0.5 * (p[0][i] + p[1][i]);
      } else throw Error('unsupported channel mix');
    }
    return out;
  }
  pull(n) {
    if (this.cacheBlock !== blockIndex) { this.cache = this.process(n); this.cacheBlock = blockIndex; }
    return this.cache;
  }
}
class GainNode extends AudioNode {
  constructor(ctx) { super(ctx, 1, 1); this.gain = new AudioParam(1); }
  process(n) {
    const x = this.input(0, n), g = this.gain.value;
    return [x.map(ch => ch.map(v => v * g))];
  }
}
class BiquadFilterNode extends AudioNode {
  constructor(ctx) { super(ctx, 1, 1); this.type = 'lowpass'; this.frequency = new AudioParam(350); this.gain = new AudioParam(0); this.Q = new AudioParam(1); this.state = []; }
  // Chromium's Biquad::SetHighShelfParams (A = 10^(gain/40), slope 1), in double.
  coefficients() {
    if (this.type !== 'highshelf') throw Error('only highshelf is modeled');
    const a = Math.pow(10, this.gain.value / 40), w0 = Math.PI * 2 * this.frequency.value / this.context.sampleRate;
    const alpha = 0.5 * Math.sin(w0) * Math.sqrt((a + 1 / a) * (1 / 1 - 1) + 2), k = Math.cos(w0), k2 = 2 * Math.sqrt(a) * alpha;
    const b0 = a * ((a + 1) + (a - 1) * k + k2), b1 = -2 * a * ((a - 1) + (a + 1) * k), b2 = a * ((a + 1) + (a - 1) * k - k2);
    const a0 = (a + 1) - (a - 1) * k + k2, a1 = 2 * ((a - 1) - (a + 1) * k), a2 = (a + 1) - (a - 1) * k - k2;
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0];
  }
  process(n) {
    const x = this.input(0, n), [b0, b1, b2, a1, a2] = this.coefficients();
    return [x.map((ch, c) => {
      const s = this.state[c] || (this.state[c] = [0, 0, 0, 0]), y = new Float32Array(n);
      for (let i = 0; i < n; i++) {  // direct form I, as Chromium
        const v = b0 * ch[i] + b1 * s[0] + b2 * s[1] - a1 * s[2] - a2 * s[3];
        s[1] = s[0]; s[0] = ch[i]; s[3] = s[2]; s[2] = v; y[i] = v;
      }
      return y;
    })];
  }
}
class ChannelMergerNode extends AudioNode {
  constructor(ctx, inputs) { super(ctx, inputs, 1); this.channelCount = 1; this.channelCountMode = 'explicit'; }
  process(n) { const out = []; for (let i = 0; i < this.numberOfInputs; i++) out.push(this.input(i, n)[0]); return [out]; }
}
class ChannelSplitterNode extends AudioNode {
  constructor(ctx, outputs) { super(ctx, 1, outputs); this.channelCount = outputs; this.channelCountMode = 'explicit'; this.channelInterpretation = 'discrete'; }
  process(n) { const x = this.input(0, n); return x.map(ch => [ch]); }
}
class BufferSource extends AudioNode {
  constructor(ctx, channels) { super(ctx, 0, 1); this.channels = channels; this.pos = 0; }
  process(n) { const out = this.channels.map(ch => ch.subarray(this.pos, this.pos + n)); this.pos += n; return [out]; }
}
// The worklet module text runs in its own context with registerProcessor.
let processors = {};
class AudioWorkletProcessorModel { constructor() { this.port = { onmessage: null }; } }
function loadWorkletModule(code) {
  const scope = { Math, Float32Array, Array, Object, Reflect, sampleRate: RATE, AudioWorkletProcessor: AudioWorkletProcessorModel,
    registerProcessor: (name, cls) => { processors[name] = cls; } };
  vm.runInNewContext(code, scope);
}
class AudioWorkletNodeModel extends AudioNode {
  constructor(ctx, name, options) {
    super(ctx, 1, 1);
    this.channelCount = options.channelCount; this.channelCountMode = options.channelCountMode; this.channelInterpretation = options.channelInterpretation;
    this.processor = new processors[name](options);
    this.port = { postMessage: (m) => this.processor.port.onmessage({ data: JSON.parse(JSON.stringify(m)) }) };
  }
  process(n) {
    const inputs = [this.sources.length ? this.input(0, n) : []], out = [new Float32Array(n), new Float32Array(n)];
    this.processor.process(inputs, [out]);
    return [out];
  }
}
class AudioContextModel {
  constructor() {
    this.sampleRate = RATE; this.nodes = [];
    const track = (node) => { this.nodes.push(node); return node; };
    this.track = track;
    this.destination = track(new GainNode(this));
    this.audioWorklet = { addModule: (url) => { loadWorkletModule(blobs[url]); return Promise.resolve(); } };
  }
  createGain() { return this.track(new GainNode(this)); }
  createBiquadFilter() { return this.track(new BiquadFilterNode(this)); }
  createChannelMerger(n) { return this.track(new ChannelMergerNode(this, n)); }
  createChannelSplitter(n) { return this.track(new ChannelSplitterNode(this, n)); }
  render(blocks, onBlock) {
    const L = new Float32Array(blocks * BLOCK), R = new Float32Array(blocks * BLOCK);
    for (let b = 0; b < blocks; b++) {
      blockIndex++;
      if (onBlock) onBlock(b);
      const out = this.destination.pull(BLOCK)[0];
      if (out.length) { L.set(out[0], b * BLOCK); R.set(out[out.length > 1 ? 1 : 0], b * BLOCK); }
    }
    return [L, R];
  }
}
const blobs = {};
let blobCount = 0;

function loadPostJs(withWorklet) {
  const AL = { ALC_EXTENSIONS: {}, buffers: [{ id: 0, channels: 1 }], currentCtx: null, initSourcePanner() {}, updateSourceSpace() {} };
  const sandbox = {
    AL, Math, Array, Object, Set, Float32Array, Promise, JSON, isFinite, console,
    AudioNode, err: (m) => { throw Error(m); },
    Blob: function (parts) { this.text = parts.join(''); },
    URL: { createObjectURL: (b) => { const u = 'blob:' + (++blobCount); blobs[u] = b.text; return u; } }
  };
  if (withWorklet) sandbox.AudioWorkletNode = function (ctx, name, options) { return ctx.track(new AudioWorkletNodeModel(ctx, name, options)); };
  vm.createContext(sandbox);
  for (const f of ['openal_stereo.js', 'openal_reverb.js', 'openal_efx.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web', f), 'utf8'), sandbox, { filename: f });
  }
  return AL;
}

// --- EFX availability and API -------------------------------------------------
check(!loadPostJs(false).ALC_EXTENSIONS.ALC_EXT_EFX, 'no ALC_EXT_EFX without AudioWorklet');
const AL = loadPostJs(true), efx = AL.efx;
check(AL.ALC_EXTENSIONS.ALC_EXT_EFX === true, 'ALC_EXT_EFX with AudioWorklet');

const EFFECT = 0, FILTER = 1, SLOT = 2;
function newContext() {
  const ac = new AudioContextModel(), gain = ac.createGain();
  gain.connect(ac.destination);
  const ctx = { audioCtx: ac, gain, sources: {}, listener: { position: [0, 0, 0], velocity: [0, 0, 0], direction: [0, 0, -1], up: [0, 1, 0] },
    distanceModel: 0xd002, sourceDistanceModel: false, speedOfSound: 343.3, dopplerFactor: 1, _err: 0,
    get err() { return this._err; }, set err(v) { if (this._err === 0 || v === 0) this._err = v; } };
  AL.currentCtx = ctx;
  return ctx;
}
function takeError() { const e = AL.currentCtx.err; AL.currentCtx.err = 0; return e; }
function newSource(ctx, id, channels, pos) {
  const gain = ctx.audioCtx.createGain();
  gain.connect(ctx.gain);
  const src = { context: ctx, id, type: 0x1028, bufQueue: [{ id: 1, channels }], gain, panner: null, spatialize: 2, relative: true,
    refDistance: 1, maxDistance: 3.4e38, rolloffFactor: 0, position: pos.slice(), velocity: [0, 0, 0], dopplerShift: 1, distanceModel: 0xd002 };
  ctx.sources[id] = src;
  AL.initSourcePanner(src);
  return src;
}
function lowpass(gain, gainHF) {
  const id = efx.gen(FILTER);
  efx.set(FILTER, id, 0x8001, true, 1);
  efx.set(FILTER, id, 1, false, gain);
  efx.set(FILTER, id, 2, false, gainHF);
  return id;
}
const PARAM_IDS = { density: 1, diffusion: 2, gain: 3, gainHF: 4, gainLF: 5, decayTime: 6, decayHFRatio: 7, decayLFRatio: 8, reflectionsGain: 9,
  reflectionsDelay: 10, lateReverbGain: 12, lateReverbDelay: 13, echoTime: 15, echoDepth: 16, modulationTime: 17, modulationDepth: 18,
  airAbsorptionGainHF: 19, hfReference: 20, lfReference: 21, roomRolloffFactor: 22 };
function reverbEffect(props) {
  const id = efx.gen(EFFECT);
  efx.set(EFFECT, id, 0x8001, true, 0x8000);
  for (const k in PARAM_IDS) efx.set(EFFECT, id, PARAM_IDS[k], false, props[k]);
  efx.set(EFFECT, id, 0x000B, false, props.reflectionsPan);
  efx.set(EFFECT, id, 0x000E, false, props.lateReverbPan);
  efx.set(EFFECT, id, 0x0017, true, props.decayHFLimit ? 1 : 0);
  return id;
}

const settle = () => new Promise(r => setImmediate(r));  // worklet module load and node creation

async function apiChecks() {
  const ctx = newContext();
  const e = efx.gen(EFFECT), f = efx.gen(FILTER), s = efx.gen(SLOT);
  await settle();
  check(efx.is(EFFECT, e) && efx.is(FILTER, f) && efx.is(SLOT, s) && !efx.is(EFFECT, 999), 'objects exist once generated');
  efx.set(EFFECT, e, 0x0006, false, 2.0); check(takeError() === 0xA002, 'reverb parameter on a null effect is AL_INVALID_ENUM');
  efx.set(EFFECT, e, 0x8001, true, 0x8000); check(takeError() === 0 && efx.effects[e].props.decayTime === Math.fround(1.49), 'EAX reverb starts at defaults');
  efx.set(EFFECT, e, 0x0006, false, 25); check(takeError() === 0xA003 && efx.effects[e].props.decayTime === Math.fround(1.49), 'out-of-range decay time rejected');
  efx.set(EFFECT, e, 0x0006, false, 2.5); check(efx.effects[e].props.decayTime === 2.5, 'decay time set');
  efx.set(EFFECT, e, 0x0017, true, 0); check(efx.effects[e].props.decayHFLimit === false, 'decay HF limit set');
  efx.set(EFFECT, e, 0x0006, true, 2); check(takeError() === 0xA002, 'integer decay time is AL_INVALID_ENUM');
  efx.set(EFFECT, 999, 0x0006, false, 2); check(takeError() === 0xA001, 'unknown effect is AL_INVALID_NAME');
  efx.set(FILTER, f, 1, false, 0.5); check(takeError() === 0xA002, 'gain on a null filter is AL_INVALID_ENUM');
  efx.set(FILTER, f, 0x8001, true, 1); efx.set(FILTER, f, 2, false, 1.5); check(takeError() === 0xA003, 'GAINHF above 1 rejected');
  efx.set(SLOT, s, 1, true, e); efx.set(SLOT, s, 2, false, 0.5);
  check(takeError() === 0 && efx.slots[s].props.decayTime === 2.5 && efx.slots[s].gain === 0.5, 'slot takes the effect and gain');
  efx.set(EFFECT, e, 0x0006, false, 3); check(efx.slots[s].props.decayTime === 2.5, 'slot keeps its copy until the effect is attached again');
  efx.set(SLOT, s, 1, true, 999); check(takeError() === 0xA003, 'unknown effect for a slot is AL_INVALID_VALUE');
  const src = newSource(ctx, 7, 1, [0, 0, -1]);
  efx.sourceSend(7, s, 0, 0); check(takeError() === 0 && efx.slots[s].sources.has(src) && src.efx.wetIn, 'send attaches the source');
  efx.sourceSend(7, s, 1, 0); check(takeError() === 0xA003, 'only send 0 exists');
  efx.sourceSend(99, s, 0, 0); check(takeError() === 0xA001, 'unknown source is AL_INVALID_NAME');
  efx.remove(SLOT, [s]); check(takeError() === 0xA004 && efx.is(SLOT, s), 'slot in use is not deleted');
  efx.set(SLOT, s, 1, true, 0); check(!src.efx.wetIn && efx.slots[s].node.processor.reverb === null, 'slot without effect drops the send and idles the worklet');
  efx.set(SLOT, s, 1, true, e); check(src.efx.wetIn, 'reattached effect restores the send');
  efx.sourceSend(7, 0, 0, 0); efx.remove(SLOT, [s]); check(takeError() === 0 && !efx.is(SLOT, s), 'detached slot is deleted');
  efx.remove(EFFECT, [e, 999]); check(takeError() === 0xA001 && efx.is(EFFECT, e), 'delete with an unknown name deletes nothing');
  efx.remove(EFFECT, [e, 0]); check(!efx.is(EFFECT, e), 'delete ignores name 0');
}

// --- Native responses ---------------------------------------------------------
const SETTLE = 16384, LEN = 120 * 441;
const worst = { tap: 0, env: 0 };
async function nativeChecks() {
 for (const c of native.cases) {
  const ctx = newContext(), ac = ctx.audioCtx, total = SETTLE + LEN;
  const src = newSource(ctx, 1, c.stereo ? 2 : 1, c.pos);
  if (!c.dry) efx.sourceDirectFilter(1, lowpass(0, 1));
  else if (c.directFilter) efx.sourceDirectFilter(1, lowpass(c.directFilter[0], c.directFilter[1]));
  let slot = 0, node = null;
  if (c.effect) {
    slot = efx.gen(SLOT);
    efx.set(SLOT, slot, 1, true, reverbEffect(native.effects[c.effect].props));
    efx.set(SLOT, slot, 2, false, c.slotGain);
  }
  efx.sourceSend(1, slot, 0, c.sendFilter ? lowpass(c.sendFilter[0], c.sendFilter[1]) : 0);
  check(takeError() === 0, c.name + ': no AL errors');
  await settle();
  const impulse = (c.stereo ? [0, 1] : [0]).map(k => { const a = new Float32Array(total + BLOCK); if (k === 0) a[SETTLE] = 1; return a; });
  const player = ac.track(new BufferSource(ac, impulse));
  player.connect(src.gain);
  const [L, R] = ac.render(Math.ceil(total / BLOCK), (b) => {
    // Native's LFO position when its impulse arrived (the modulation case).
    if (b === 0 && slot) node = efx.slots[slot].node;
    if (b === 0 && c.modIndex !== undefined) {
      const rv = node.processor.reverb;
      rv.pipelines[rv.current].late.modIndex = c.modIndex;
    }
  });
  const wl = L.subarray(SETTLE), wr = R.subarray(SETTLE);
  const peak = Math.max(...c.native.taps.map(t => Math.max(Math.abs(t[1]), Math.abs(t[2]))));
  let tapErr = 0;
  for (const [i, l, r] of c.native.taps) tapErr = Math.max(tapErr, Math.abs(wl[i] - l), Math.abs(wr[i] - r));
  tapErr /= peak;
  let envErr = 0;
  [wl, wr].forEach((w, ch) => {
    const ref = c.native.env[ch], top = Math.max(...ref.filter(v => v !== null));
    ref.forEach((db, b) => {
      if (db === null || db < top - 70) return;
      let e = 0;
      for (let i = b * 441; i < (b + 1) * 441; i++) e += w[i] * w[i];
      envErr = Math.max(envErr, Math.abs(10 * Math.log10(e) - db));
    });
  });
  worst.tap = Math.max(worst.tap, tapErr); worst.env = Math.max(worst.env, envErr);
  check(tapErr < 2e-5, `${c.name}: early samples within 2e-5 of peak (${tapErr.toExponential(2)})`);
  check(envErr < 0.01, `${c.name}: 10 ms energy within 0.01 dB (${envErr.toFixed(4)})`);
  if (slot) { efx.sourceSend(1, 0, 0, 0); efx.remove(SLOT, [slot]); }
 }
}

(async () => {
  await apiChecks();
  await nativeChecks();
  if (failures) { console.error(`${failures} of ${checks} OpenAL EFX checks failed`); process.exit(1); }
  console.log(`PASS: ${checks} OpenAL EFX checks; ${native.cases.length} native reverb cases, worst early sample ${worst.tap.toExponential(1)} of peak, envelope ${worst.env.toFixed(4)} dB`);
})();
