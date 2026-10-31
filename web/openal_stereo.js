// OpenAL Soft stereo panning for Emscripten's OpenAL (linked with --post-js).
//
// Emscripten spatializes mono sources with a WebAudio PannerNode
// ('equalpower'): front sources play at 0.707 per channel, sources behind as
// loudly as in front, and a reference distance of 0 silences the source even
// with rolloff 0. The native build uses OpenAL Soft, whose stereo output
// encodes the source direction as first-order ambisonics (after widening
// frontal azimuths by 1.5) and decodes it with fixed gains:
//   left/right = 0.5 W +/- 0.288675135 Y + 0.0552305643 X
// so front sources play at 0.596, sources behind at 0.404, and rolloff 0
// leaves the level alone at any reference distance. Measured from the native
// OpenAL32.dll (wave output), this model matches 144 directions within 0.009.
// Doom 3 sets rolloff 0 and applies distance falloff itself, so only panning
// remains; other distance models follow the OpenAL formulas. Stereo buffers
// are not spatialized by either library. docs/WEB.md (2026-10-31) has the data.
(function () {
  if (typeof AL === 'undefined' || !AL.initSourcePanner || typeof AudioNode === 'undefined') return;

  var FRONT_SCALE = 1.5, Y_GAIN = 0.288675135, X_GAIN = 0.0552305643, SQRT3 = Math.sqrt(3);

  // Gains for a direction in listener space (x right, y up, z back), unit length.
  function stereoGains(x, y, z, out) {
    var az = Math.atan2(x, -z);
    var el = Math.asin(Math.max(-1, Math.min(1, y)));
    var absAz = Math.abs(az);
    if (absAz < Math.PI / 2) az = (az < 0 ? -1 : 1) * Math.min(absAz * FRONT_SCALE, Math.PI / 2);
    var c = Math.cos(el);
    var ambiY = -SQRT3 * Math.sin(az) * c;  // left positive
    var ambiX = SQRT3 * Math.cos(az) * c;   // front positive
    // Not clamped: just past 90 degrees the far channel is slightly negative
    // (phase-inverted), as in OpenAL Soft's decoder.
    out[0] = 0.5 + Y_GAIN * ambiY + X_GAIN * ambiX;
    out[1] = 0.5 - Y_GAIN * ambiY + X_GAIN * ambiX;
  }

  // OpenAL distance attenuation (AL_*_DISTANCE[_CLAMPED]).
  function distanceGain(src, dist) {
    var model = src.context.sourceDistanceModel ? src.distanceModel : src.context.distanceModel;
    var ref = src.refDistance, max = src.maxDistance, rolloff = src.rolloffFactor;
    if (model === 0 /* AL_NONE */ || rolloff === 0) return 1;
    if (model === 0xd002 || model === 0xd004 || model === 0xd006) {
      if (max < ref) return 1;
      dist = Math.min(Math.max(dist, ref), max);
    }
    switch (model) {
    case 0xd001: case 0xd002: {
      var denom = ref + rolloff * (dist - ref);
      return denom > 0 ? Math.min(1, ref / denom) : 1;
    }
    case 0xd003: case 0xd004:
      return max !== ref ? Math.max(0, 1 - rolloff * (dist - ref) / (max - ref)) : 1;
    case 0xd005: case 0xd006:
      return dist > 0 && ref > 0 ? Math.pow(dist / ref, -rolloff) : 1;
    }
    return 1;
  }

  var connectNode = AudioNode.prototype.connect, disconnectNode = AudioNode.prototype.disconnect;
  // A mono input node fanned out to left/right gains and merged to stereo. The
  // input node stands in for the PannerNode Emscripten connects to.
  function createStereoPanner(ctx) {
    var input = ctx.createGain();
    input.channelCount = 1;
    input.channelCountMode = 'explicit';
    var left = ctx.createGain(), right = ctx.createGain(), merger = ctx.createChannelMerger(2);
    connectNode.call(input, left);
    connectNode.call(input, right);
    connectNode.call(left, merger, 0, 0);
    connectNode.call(right, merger, 0, 1);
    input.connect = function (dest) { return connectNode.call(merger, dest); };
    input.disconnect = function () { disconnectNode.call(merger); };
    input.openalStereo = { left: left, right: right, gains: [0, 0] };
    return input;
  }

  AL.initSourcePanner = function (src) {
    if (src.type === 0x1030 /* AL_UNDETERMINED */) return;
    var templateBuf = AL.buffers[0];
    for (var i = 0; i < src.bufQueue.length; i++) {
      if (src.bufQueue[i].id !== 0) { templateBuf = src.bufQueue[i]; break; }
    }
    if (src.spatialize === 1 /* AL_TRUE */ || (src.spatialize === 2 /* AL_AUTO_SOFT */ && templateBuf.channels === 1)) {
      if (src.panner) return;
      src.panner = createStereoPanner(src.context.audioCtx);
      AL.updateSourceSpace(src);
      src.panner.connect(src.context.gain);
      src.gain.disconnect();
      src.gain.connect(src.panner);
    } else {
      if (!src.panner) return;
      src.panner.disconnect();
      src.gain.disconnect();
      src.gain.connect(src.context.gain);
      src.panner = null;
    }
  };

  // Distance parameters feed the gains computed in updateSourceSpace.
  AL.updateSourceGlobal = function (src) {
    if (src.panner) AL.updateSourceSpace(src);
  };

  var gains = [0, 0];
  AL.updateSourceSpace = function (src) {
    var panner = src.panner;
    if (!panner || !panner.openalStereo) return;
    var listener = src.context.listener;
    var lp = listener.position, at = listener.direction, up = listener.up;
    // Listener basis as OpenAL Soft builds it: N forward, V up, U right.
    var nl = Math.hypot(at[0], at[1], at[2]) || 1, nx = at[0] / nl, ny = at[1] / nl, nz = at[2] / nl;
    var vl = Math.hypot(up[0], up[1], up[2]) || 1, vx = up[0] / vl, vy = up[1] / vl, vz = up[2] / vl;
    var ux = ny * vz - nz * vy, uy = nz * vx - nx * vz, uz = nx * vy - ny * vx;
    var ul = Math.hypot(ux, uy, uz) || 1; ux /= ul; uy /= ul; uz /= ul;
    vx = uy * nz - uz * ny; vy = uz * nx - ux * nz; vz = ux * ny - uy * nx;
    var p = src.position, x, y, z, wx, wy, wz;
    if (src.relative) {
      x = p[0]; y = p[1]; z = p[2];
      wx = lp[0] + ux * x + vx * y - nx * z;
      wy = lp[1] + uy * x + vy * y - ny * z;
      wz = lp[2] + uz * x + vz * y - nz * z;
    } else {
      var dx = p[0] - lp[0], dy = p[1] - lp[1], dz = p[2] - lp[2];
      x = dx * ux + dy * uy + dz * uz;
      y = dx * vx + dy * vy + dz * vz;
      z = -(dx * nx + dy * ny + dz * nz);
      wx = p[0]; wy = p[1]; wz = p[2];
    }
    var dist = Math.hypot(x, y, z);
    if (dist > 0) stereoGains(x / dist, y / dist, z / dist, gains);
    else stereoGains(0, 0, -1, gains);  // at the listener: OpenAL Soft pans to the front
    var g = distanceGain(src, dist), state = panner.openalStereo;
    var gl = gains[0] * g, gr = gains[1] * g;
    if (gl !== state.gains[0]) { state.left.gain.value = gl; state.gains[0] = gl; }
    if (gr !== state.gains[1]) { state.right.gain.value = gr; state.gains[1] = gr; }

    // Doppler, as Emscripten computes it (Doom 3 sets no velocities).
    var oldShift = src.dopplerShift, v = src.velocity, lv = listener.velocity;
    if ((wx === lp[0] && wy === lp[1] && wz === lp[2]) || (v[0] === lv[0] && v[1] === lv[1] && v[2] === lv[2])) {
      src.dopplerShift = 1.0;
    } else {
      var c = src.context.speedOfSound, f = src.context.dopplerFactor;
      var sx = lp[0] - wx, sy = lp[1] - wy, sz = lp[2] - wz, ms = Math.hypot(sx, sy, sz);
      var vls = Math.min((sx * lv[0] + sy * lv[1] + sz * lv[2]) / ms, c / f);
      var vss = Math.min((sx * v[0] + sy * v[1] + sz * v[2]) / ms, c / f);
      src.dopplerShift = (c - f * vls) / (c - f * vss);
    }
    if (src.dopplerShift !== oldShift) AL.updateSourceRate(src);
  };

  // For tests (tests/test_web_shell.js and the browser bench).
  AL.openalStereoGains = function (x, y, z) {
    var out = [0, 0], d = Math.hypot(x, y, z);
    if (d > 0) stereoGains(x / d, y / d, z / d, out); else stereoGains(0, 0, -1, out);
    return out;
  };
})();
