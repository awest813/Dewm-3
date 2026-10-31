// OpenAL EFX for Emscripten's OpenAL (linked with --post-js after
// openal_stereo.js and openal_reverb.js).
//
// Emscripten's OpenAL has no EFX, so the web build used to run without the
// per-area reverb the native build gets from OpenAL Soft. This adds what
// Doom 3 uses: effects (EAX reverb), low-pass filters, auxiliary effect slots
// and per-source direct filters and sends, and reports ALC_EXT_EFX when the
// browser has AudioWorklet. neo/sound/snd_efx_web.cpp provides the C entry
// points, which call AL.efx here.
//
// The source graph follows OpenAL Soft 1.23.1 (alc/alu.cpp):
//  - direct filter: gain, then a high shelf at 5 kHz whose gain at the
//    reference frequency is GAINHF. That is WebAudio's 'highshelf' with
//    A = GAINHF (gain 40 log10 GAINHF dB); both use slope 1.
//  - send: the source is panned into the slot's first-order B-Format input
//    (W, Y, Z, X, N3D) with the direct path's widened direction, scaled by
//    the send filter's gain (its GAINHF shelf in front) and the room rolloff.
//  - slot: openal_reverb.js in an AudioWorklet, mixed into the listener gain.
// docs/WEB.md ("EFX reverb", 2026-10-31) has the native comparison.
(function () {
  if (typeof AL === 'undefined' || !AL.updateSourceSpace || typeof openalEaxReverb !== 'function') return;
  if (typeof AudioWorkletNode !== 'function') return;  // insecure context or old browser: no EFX

  AL.ALC_EXTENSIONS['ALC_EXT_EFX'] = true;

  var INVALID_NAME = 0xA001, INVALID_ENUM = 0xA002, INVALID_VALUE = 0xA003, INVALID_OPERATION = 0xA004;
  var EFFECT = 0, FILTER = 1, SLOT = 2;
  var FRONT_SCALE = 1.5, SQRT3 = Math.sqrt(3), SPEED_OF_SOUND = 343.3, HF_REFERENCE = 5000;
  var f = Math.fround;

  // AL_EAXREVERB_* parameter: [field, min, max] (al/effects/reverb.cpp).
  var REVERB_PARAMS = {
    0x0001: ['density', 0, 1], 0x0002: ['diffusion', 0, 1], 0x0003: ['gain', 0, 1],
    0x0004: ['gainHF', 0, 1], 0x0005: ['gainLF', 0, 1], 0x0006: ['decayTime', 0.1, 20],
    0x0007: ['decayHFRatio', 0.1, 2], 0x0008: ['decayLFRatio', 0.1, 2], 0x0009: ['reflectionsGain', 0, 3.16],
    0x000A: ['reflectionsDelay', 0, 0.3], 0x000C: ['lateReverbGain', 0, 10], 0x000D: ['lateReverbDelay', 0, 0.1],
    0x000F: ['echoTime', 0.075, 0.25], 0x0010: ['echoDepth', 0, 1], 0x0011: ['modulationTime', 0.04, 4],
    0x0012: ['modulationDepth', 0, 1], 0x0013: ['airAbsorptionGainHF', 0.892, 1], 0x0014: ['hfReference', 1000, 20000],
    0x0015: ['lfReference', 20, 1000], 0x0016: ['roomRolloffFactor', 0, 10]
  };
  var REVERB_PAN = { 0x000B: 'reflectionsPan', 0x000E: 'lateReverbPan' };
  function reverbDefaults() {
    return {
      density: 1, diffusion: 1, gain: f(0.32), gainHF: f(0.89), gainLF: 1, decayTime: f(1.49),
      decayHFRatio: f(0.83), decayLFRatio: 1, reflectionsGain: f(0.05), reflectionsDelay: f(0.007),
      reflectionsPan: [0, 0, 0], lateReverbGain: f(1.26), lateReverbDelay: f(0.011), lateReverbPan: [0, 0, 0],
      echoTime: 0.25, echoDepth: 0, modulationTime: 0.25, modulationDepth: 0, airAbsorptionGainHF: f(0.994),
      hfReference: 5000, lfReference: 250, roomRolloffFactor: 0, decayHFLimit: true
    };
  }
  function copyProps(p) {
    var c = {};
    for (var k in p) c[k] = Array.isArray(p[k]) ? p[k].slice() : p[k];
    return c;
  }

  var efx = AL.efx = { effects: {}, filters: {}, slots: {}, nextId: [1, 1, 1], workletUrl: null };

  function setError(err) { if (AL.currentCtx) AL.currentCtx.err = err; }
  function table(kind) { return kind === EFFECT ? efx.effects : kind === FILTER ? efx.filters : efx.slots; }

  efx.gen = function (kind) {
    var id = efx.nextId[kind]++;
    if (kind === EFFECT) efx.effects[id] = { type: 0, props: null };
    else if (kind === FILTER) efx.filters[id] = { type: 0, gain: 1, gainHF: 1 };
    else {
      if (!AL.currentCtx) { setError(INVALID_OPERATION); return 0; }
      efx.slots[id] = createSlot(AL.currentCtx, id);
    }
    return id;
  };

  efx.remove = function (kind, ids) {
    var t = table(kind), i;
    for (i = 0; i < ids.length; i++) {
      if (ids[i] !== 0 && !t[ids[i]]) { setError(INVALID_NAME); return; }
      if (kind === SLOT && ids[i] !== 0 && t[ids[i]].sources.size) { setError(INVALID_OPERATION); return; }
    }
    for (i = 0; i < ids.length; i++) {
      if (ids[i] === 0) continue;
      if (kind === SLOT) destroySlot(t[ids[i]]);
      delete t[ids[i]];
    }
  };

  efx.is = function (kind, id) { return !!table(kind)[id]; };

  // alEffecti/f/fv, alFilteri/f, alAuxiliaryEffectSloti/f. value is a number
  // or, for vectors, an array of three.
  efx.set = function (kind, id, param, isInt, value) {
    var obj = table(kind)[id];
    if (!obj) { setError(INVALID_NAME); return; }
    if (kind === EFFECT) setEffectParam(obj, param, isInt, value);
    else if (kind === FILTER) setFilterParam(obj, param, isInt, value);
    else setSlotParam(obj, param, isInt, value);
  };

  function setEffectParam(effect, param, isInt, value) {
    if (param === 0x8001 /* AL_EFFECT_TYPE */) {
      if (!isInt) { setError(INVALID_ENUM); return; }
      if (value === 0 /* AL_EFFECT_NULL */) { effect.type = 0; effect.props = null; }
      else if (value === 0x8000 /* AL_EFFECT_EAXREVERB */) { effect.type = value; effect.props = reverbDefaults(); }
      else setError(INVALID_VALUE);
      return;
    }
    if (effect.type !== 0x8000) { setError(INVALID_ENUM); return; }
    var p = effect.props;
    if (param === 0x0017 /* AL_EAXREVERB_DECAY_HFLIMIT */) {
      if (!isInt) { setError(INVALID_ENUM); return; }
      if (value !== 0 && value !== 1) { setError(INVALID_VALUE); return; }
      p.decayHFLimit = value === 1;
      return;
    }
    if (isInt) { setError(INVALID_ENUM); return; }
    if (REVERB_PAN[param]) {
      if (!Array.isArray(value)) { setError(INVALID_ENUM); return; }
      if (!value.every(isFinite)) { setError(INVALID_VALUE); return; }
      p[REVERB_PAN[param]] = value.map(f);
      return;
    }
    var def = REVERB_PARAMS[param];
    if (!def) { setError(INVALID_ENUM); return; }
    if (Array.isArray(value)) value = value[0];
    if (!(value >= def[1] && value <= def[2])) { setError(INVALID_VALUE); return; }
    p[def[0]] = f(value);
  }

  function setFilterParam(filter, param, isInt, value) {
    if (param === 0x8001 /* AL_FILTER_TYPE */) {
      if (!isInt) { setError(INVALID_ENUM); return; }
      if (value === 0 || value === 1 /* AL_FILTER_NULL, AL_FILTER_LOWPASS */) {
        filter.type = value; filter.gain = 1; filter.gainHF = 1;
      } else setError(INVALID_VALUE);
      return;
    }
    if (filter.type !== 1 || isInt) { setError(INVALID_ENUM); return; }
    if (param !== 0x0001 && param !== 0x0002 /* AL_LOWPASS_GAIN, AL_LOWPASS_GAINHF */) { setError(INVALID_ENUM); return; }
    if (!(value >= 0 && value <= 1)) { setError(INVALID_VALUE); return; }
    if (param === 1) filter.gain = f(value); else filter.gainHF = f(value);
  }

  function setSlotParam(slot, param, isInt, value) {
    if (param === 0x0001 /* AL_EFFECTSLOT_EFFECT */) {
      if (!isInt) { setError(INVALID_ENUM); return; }
      var effect = value ? efx.effects[value] : null;
      if (value && !effect) { setError(INVALID_VALUE); return; }
      var had = !!slot.props;
      // The slot keeps a copy, as OpenAL Soft does: later effect changes
      // need the effect attached again.
      slot.props = effect && effect.props ? copyProps(effect.props) : null;
      postSlot(slot);
      if (had !== !!slot.props) slot.sources.forEach(route);
      else slot.sources.forEach(updateSend);
    } else if (param === 0x0002 /* AL_EFFECTSLOT_GAIN */) {
      if (isInt) { setError(INVALID_ENUM); return; }
      if (!(value >= 0 && value <= 1)) { setError(INVALID_VALUE); return; }
      slot.gain = f(value);
      postSlot(slot);
    } else if (param === 0x0003 /* AL_EFFECTSLOT_AUXILIARY_SEND_AUTO */) {
      if (!isInt) { setError(INVALID_ENUM); return; }
      if (value !== 0 && value !== 1) { setError(INVALID_VALUE); return; }
      slot.auxSendAuto = value === 1;
      slot.sources.forEach(updateSend);
    } else setError(INVALID_ENUM);
  }

  // Effect slots: a 4-input ChannelMerger collects the B-Format sends and
  // feeds the reverb worklet once its module has loaded.
  function createSlot(ctx, id) {
    var slot = { id: id, ctx: ctx, gain: 1, auxSendAuto: true, props: null, sources: new Set(), node: null };
    slot.input = ctx.audioCtx.createChannelMerger(4);
    loadWorklet(ctx).then(function () {
      if (!efx.slots[id]) return;
      slot.node = new AudioWorkletNode(ctx.audioCtx, 'openal-eaxreverb', {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [2],
        channelCount: 4, channelCountMode: 'explicit', channelInterpretation: 'discrete',
        processorOptions: { props: slot.props, gain: slot.gain }
      });
      slot.input.connect(slot.node);
      slot.node.connect(ctx.gain);
    }, function (e) { err('OpenAL EFX: reverb worklet failed to load: ' + e); });
    return slot;
  }

  function destroySlot(slot) {
    slot.input.disconnect();
    if (slot.node) { slot.node.port.postMessage({ props: null }); slot.node.disconnect(); slot.node = null; }
  }

  function postSlot(slot) {
    if (slot.node) slot.node.port.postMessage({ props: slot.props, gain: slot.gain });
  }

  function loadWorklet(ctx) {
    if (!ctx.efxWorklet) {
      if (!efx.workletUrl) {
        efx.workletUrl = URL.createObjectURL(new Blob(['(' + openalEaxReverb.toString() + ')();'],
          { type: 'application/javascript' }));
      }
      ctx.efxWorklet = ctx.audioCtx.audioWorklet.addModule(efx.workletUrl);
    }
    return ctx.efxWorklet;
  }

  // alSourcei(AL_DIRECT_FILTER) and alSource3i(AL_AUXILIARY_SEND_FILTER).
  // Filter values are copied when attached, as in OpenAL Soft.
  function filterValues(id) {
    if (id === 0) return null;
    var filter = efx.filters[id];
    if (!filter) return undefined;
    return filter.type === 1 ? { gain: filter.gain, gainHF: filter.gainHF } : null;
  }
  function sourceState(id) {
    var src = AL.currentCtx && AL.currentCtx.sources[id];
    if (!src) { setError(INVALID_NAME); return null; }
    if (!src.efx) src.efx = { direct: null, slot: null, send: null, dryIn: null, wetIn: null };
    return src;
  }

  efx.sourceDirectFilter = function (sourceId, filterId) {
    var src = sourceState(sourceId);
    if (!src) return;
    var values = filterValues(filterId);
    if (values === undefined) { setError(INVALID_VALUE); return; }
    var e = src.efx, old = e.direct;
    if (old === values || (old && values && old.gain === values.gain && old.gainHF === values.gainHF)) return;
    e.direct = values;
    route(src);
  };

  efx.sourceSend = function (sourceId, slotId, sendIndex, filterId) {
    var src = sourceState(sourceId);
    if (!src) return;
    var slot = slotId ? efx.slots[slotId] : null, values = filterValues(filterId);
    if ((slotId && !slot) || sendIndex !== 0 || values === undefined) { setError(INVALID_VALUE); return; }
    var e = src.efx, old = e.send;
    var sameFilter = old === values || (old && values && old.gain === values.gain && old.gainHF === values.gainHF);
    if (e.slot === slot && sameFilter) return;
    if (e.slot !== slot) {
      if (e.slot) e.slot.sources.delete(src);
      if (slot) slot.sources.add(src);
      e.slot = slot;
    }
    e.send = values;
    route(src);
  };

  function shelfDb(gainHF) { return 40 * Math.log10(Math.max(gainHF, 0.001)); }

  // Connects src.gain to the dry destination (the stereo panner or the
  // listener gain), through the direct filter when one is set, and to the
  // send when the source has a slot with an effect.
  function route(src) {
    var e = src.efx, ac = src.context.audioCtx, dest = src.panner || src.context.gain, dryIn = dest;
    if (e.direct && (e.direct.gain !== 1 || e.direct.gainHF !== 1)) {
      if (!e.dryGain) {
        e.dryGain = ac.createGain();
        e.dryShelf = ac.createBiquadFilter();
        e.dryShelf.type = 'highshelf';
        e.dryShelf.frequency.value = HF_REFERENCE;
        e.dryGain.connect(e.dryShelf);
      }
      e.dryGain.gain.value = e.direct.gain;
      e.dryShelf.gain.value = e.direct.gainHF !== 1 ? shelfDb(e.direct.gainHF) : 0;
      if (e.shelfDest !== dest) { e.dryShelf.disconnect(); e.dryShelf.connect(dest); e.shelfDest = dest; }
      dryIn = e.dryGain;
    }
    var wetIn = e.slot && e.slot.props ? sendInput(src) : null;
    if (e.dryIn !== dryIn || e.wetIn !== wetIn) {
      src.gain.disconnect();
      src.gain.connect(dryIn);
      if (wetIn) [].concat(wetIn).forEach(function (node) { src.gain.connect(node); });
      e.dryIn = dryIn;
      e.wetIn = wetIn;
    }
    if (!wetIn && e.wet && e.wet.slot) { e.wet.out.forEach(function (g) { g.disconnect(); }); e.wet.slot = null; }
  }

  // The send chain: [high shelf] -> [splitter for stereo] -> four gains into
  // the slot's merger inputs. Returns the node src.gain feeds.
  function sendInput(src) {
    var e = src.efx, ac = src.context.audioCtx, w = e.wet, i;
    var stereo = !src.panner && sourceChannels(src) === 2;
    if (!w) {
      w = e.wet = { shelf: null, splitter: null, out: [], gains: [NaN, NaN, NaN, NaN], stereo: null, slot: null, input: null };
      for (i = 0; i < 4; i++) w.out.push(ac.createGain());
    }
    var hf = e.send ? e.send.gainHF : 1, input;
    if (hf !== 1) {
      if (!w.shelf) { w.shelf = ac.createBiquadFilter(); w.shelf.type = 'highshelf'; w.shelf.frequency.value = HF_REFERENCE; }
      w.shelf.gain.value = shelfDb(hf);
    }
    if (w.stereo !== stereo || w.slot !== e.slot || (hf !== 1) !== !!w.shelfUsed) {
      // Mono: one input into W, Y, Z and X. Stereo: left and right each into W and Y.
      var head = hf !== 1 ? w.shelf : null;
      if (w.shelf) w.shelf.disconnect();
      if (w.splitter) w.splitter.disconnect();
      for (i = 0; i < 4; i++) w.out[i].disconnect();
      if (stereo) {
        if (!w.splitter) w.splitter = ac.createChannelSplitter(2);
        if (head) head.connect(w.splitter);
        for (i = 0; i < 4; i++) {
          w.splitter.connect(w.out[i], i >> 1);
          w.out[i].connect(e.slot.input, 0, i & 1);
        }
        input = head || w.splitter;
      } else {
        for (i = 0; i < 4; i++) {
          if (head) head.connect(w.out[i]);
          w.out[i].connect(e.slot.input, 0, i);
        }
        input = head || null;
      }
      w.stereo = stereo;
      w.slot = e.slot;
      w.shelfUsed = hf !== 1;
      w.input = input;
      w.gains = [NaN, NaN, NaN, NaN];
    }
    updateSend(src);
    // Without a shelf or splitter, src.gain fans out to the four gains itself.
    return w.input || w.out;
  }

  function sourceChannels(src) {
    for (var i = 0; i < src.bufQueue.length; i++) if (src.bufQueue[i].id !== 0) return src.bufQueue[i].channels;
    return 1;
  }

  // Listener-space direction and distance of a source (x right, y up, z back),
  // with the listener basis OpenAL Soft builds, as in openal_stereo.js.
  function listenerSpace(src, out) {
    var listener = src.context.listener, lp = listener.position, at = listener.direction, up = listener.up, p = src.position;
    if (src.relative) { out[0] = p[0]; out[1] = p[1]; out[2] = p[2]; }
    else {
      var nl = Math.hypot(at[0], at[1], at[2]) || 1, nx = at[0] / nl, ny = at[1] / nl, nz = at[2] / nl;
      var vl = Math.hypot(up[0], up[1], up[2]) || 1, vx = up[0] / vl, vy = up[1] / vl, vz = up[2] / vl;
      var ux = ny * vz - nz * vy, uy = nz * vx - nx * vz, uz = nx * vy - ny * vx;
      var ul = Math.hypot(ux, uy, uz) || 1; ux /= ul; uy /= ul; uz /= ul;
      vx = uy * nz - uz * ny; vy = uz * nx - ux * nz; vz = ux * ny - uy * nx;
      var dx = p[0] - lp[0], dy = p[1] - lp[1], dz = p[2] - lp[2];
      out[0] = dx * ux + dy * uy + dz * uz;
      out[1] = dx * vx + dy * vy + dz * vz;
      out[2] = -(dx * nx + dy * ny + dz * nz);
    }
    out[3] = Math.hypot(out[0], out[1], out[2]);
    return out;
  }

  // Wet gain beyond the source gain: send filter gain, the reverb's room
  // rolloff and the automatic initial decay (alu.cpp CalcAttnSourceParams).
  // With Doom 3's rolloff 0 only the filter gain and room rolloff remain.
  function sendGain(src, slot, filterGain, dist) {
    var g = filterGain, ref = src.refDistance, rolloff = src.rolloffFactor, props = slot.props;
    if (src.panner && dist > ref && props.decayTime > 0) {
      var atten = function (r) { var d = ref + r * (dist - ref); return d > ref ? ref / d : 1; };
      g *= atten(props.roomRolloffFactor);
      if (slot.auxSendAuto) {
        var base = atten(rolloff), fact = (dist - ref) * rolloff / (props.decayTime * SPEED_OF_SOUND);
        g *= Math.pow(0.001, fact) * (1 - base) + base;
      }
    }
    return g;
  }

  var pos = [0, 0, 0, 0], coeffs = [0, 0, 0, 0];
  // B-Format send gains (W, Y, Z, X; stereo: left W, left Y, right W, right Y).
  function updateSend(src) {
    var e = src.efx, w = e && e.wet;
    if (!w || !w.slot || !e.slot || !e.slot.props) return;
    var g = e.send ? e.send.gain : 1;
    if (w.stereo) {
      // Stereo channels sit at +/-30 degrees, widened by 3 to +/-90.
      coeffs[0] = g; coeffs[1] = SQRT3 * g; coeffs[2] = g; coeffs[3] = -SQRT3 * g;
    } else {
      var x = 0, y = 0, z = -1;
      if (src.panner) {
        listenerSpace(src, pos);
        g = sendGain(src, e.slot, g, pos[3]);
        if (pos[3] > 0) { x = pos[0] / pos[3]; y = pos[1] / pos[3]; z = pos[2] / pos[3]; }
      }
      var az = Math.atan2(x, -z), el = Math.asin(Math.max(-1, Math.min(1, y))), absAz = Math.abs(az);
      if (absAz < Math.PI / 2) az = (az < 0 ? -1 : 1) * Math.min(absAz * FRONT_SCALE, Math.PI / 2);
      var c = Math.cos(el);
      coeffs[0] = g;
      coeffs[1] = -SQRT3 * Math.sin(az) * c * g;
      coeffs[2] = SQRT3 * Math.sin(el) * g;
      coeffs[3] = SQRT3 * Math.cos(az) * c * g;
    }
    for (var i = 0; i < 4; i++) {
      if (w.gains[i] !== coeffs[i]) { w.out[i].gain.value = coeffs[i]; w.gains[i] = coeffs[i]; }
    }
  }

  // Emscripten rewires src.gain when a buffer change switches the panner on
  // or off; route the source again afterwards.
  var initSourcePanner = AL.initSourcePanner;
  AL.initSourcePanner = function (src) {
    var panner = src.panner;
    initSourcePanner(src);
    if (src.efx && src.panner !== panner) { src.efx.dryIn = src.efx.wetIn = null; route(src); }
  };
  var updateSourceSpace = AL.updateSourceSpace;
  AL.updateSourceSpace = function (src) {
    updateSourceSpace(src);
    if (src.efx) updateSend(src);
  };
})();
