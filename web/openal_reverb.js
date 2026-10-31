// OpenAL Soft's EAX reverb for the web build (linked with --post-js, and run
// as an AudioWorklet by web/openal_efx.js).
//
// A port of alc/effects/reverb.cpp from OpenAL Soft 1.23.1 (the library the
// native build ships), with the stereo output stage of that version: the
// effect pans its eight lines into first-order ambisonics, which OpenAL Soft
// decodes to stereo with  left/right = 0.5 W +/- 0.288675135 Y + 0.0552305643 X.
// Here each line's pan gains are folded straight into left/right gains.
// docs/WEB.md ("EFX reverb", 2026-10-31) compares it with the native library.
//
// Ambisonic reverb engine for the OpenAL cross platform audio library
// Copyright (C) 2008-2017 by Chris Robinson and Christopher Fitzgerald.
// This library is free software; you can redistribute it and/or modify it
// under the terms of the GNU Library General Public License as published by
// the Free Software Foundation; either version 2 of the License, or (at your
// option) any later version. This port is distributed with dhewm3 under the
// GNU General Public License version 3, as LGPL section 3 permits.
//
// The whole factory is self-contained: openal_efx.js turns its source into
// the worklet module, where it also registers the 'openal-eaxreverb'
// processor. Elsewhere it just returns the Reverb class (tests/web_openal_check.js).
function openalEaxReverb() {
  'use strict';
  var f = Math.fround;
  var NUM_LINES = 4, MAX_UPDATE_SAMPLES = 256, BUFFER_LINE_SIZE = 1024;
  var MAX_MODULATION_TIME = 4.0, DEFAULT_MODULATION_TIME = 0.25;
  var MOD_FRACBITS = 24, MOD_FRACONE = 1 << MOD_FRACBITS, MOD_FRACMASK = MOD_FRACONE - 1;
  var MODULATION_DEPTH_COEFF = f(0.05);
  var DENSITY_SCALE = 125000.0;
  var DECAY_GAIN = f(0.001), MAX_REFLECTIONS_DELAY = f(0.3), MAX_LATE_REVERB_DELAY = f(0.1);
  var SPEED_OF_SOUND = f(343.3), GAIN_SILENCE = 0.00001, FLT_EPSILON = 1.1920929e-7;
  var INV_SQRT2 = f(1 / Math.SQRT2), SQRT3 = f(Math.sqrt(3));
  // OpenAL Soft's stereo decoder (alc/panning.cpp StereoConfig) for W, Y, X.
  var DECODE_W = f(0.5), DECODE_Y = f(0.288675135), DECODE_X = f(0.0552305643);

  var B2A = [[0.5, 0.5, 0.5, 0.5], [0.5, -0.5, -0.5, 0.5], [0.5, 0.5, -0.5, -0.5], [0.5, -0.5, 0.5, -0.5]];
  var EARLY_A2B = [[0.5, 0.5, 0.5, 0.5], [0.5, -0.5, 0.5, -0.5], [0.5, -0.5, -0.5, 0.5], [0.5, 0.5, -0.5, -0.5]];
  var LATE_A2B = [[0.5, 0.5, 0.5, 0.5], [INV_SQRT2, -INV_SQRT2, 0, 0], [0, 0, INV_SQRT2, -INV_SQRT2], [0.5, 0.5, -0.5, -0.5]];
  var EARLY_TAP_LENGTHS = [0.0, 2.0213520e-4, 4.2531060e-4, 6.7171600e-4].map(f);
  var EARLY_ALLPASS_LENGTHS = [9.7096800e-5, 1.0720356e-4, 1.1836234e-4, 1.3068260e-4].map(f);
  var EARLY_LINE_LENGTHS = [5.9850400e-4, 1.0913150e-3, 1.5376658e-3, 1.9419362e-3].map(f);
  var LATE_ALLPASS_LENGTHS = [1.6182800e-4, 2.0389060e-4, 2.8159360e-4, 3.2365600e-4].map(f);
  var LATE_LINE_LENGTHS = [1.9419362e-3, 2.4466860e-3, 3.3791220e-3, 3.8838720e-3].map(f);

  // Cubic spline resampler table, 256 steps between samples.
  var CUBIC = new Float32Array(513);
  for (var ci = 0; ci < 256; ci++) {
    var mu = ci / 256, mu2 = mu * mu, mu3 = mu2 * mu;
    CUBIC[ci] = 1.5 * mu3 - 2.5 * mu2 + 1.0;
    CUBIC[256 + ci] = -0.5 * mu3 + mu2 - 0.5 * mu;
  }

  function sumf(a) { var s = 0; for (var i = 0; i < a.length; i++) s = f(s + a[i]); return s; }
  function lerpf(a, b, t) { return f(a + f(t * f(b - a))); }
  function f2u(x) { return Math.trunc(x); }
  // fastf2u: SSE cvtss2si, rounding to nearest even.
  function fastf2u(x) { var r = Math.round(x); return r - x === 0.5 && r % 2 ? r - 1 : r; }
  function nextPow2(v) { var p = 1; while (p < v) p *= 2; return p; }

  // core/filters/biquad.cpp (transposed direct form II).
  var HIGH_SHELF = 0, LOW_SHELF = 1;
  function Biquad() { this.b0 = 1; this.b1 = 0; this.b2 = 0; this.a1 = 0; this.a2 = 0; this.z1 = 0; this.z2 = 0; }
  Biquad.prototype.clear = function () { this.z1 = this.z2 = 0; };
  Biquad.prototype.setParamsFromSlope = function (type, f0norm, gain) {
    gain = f(Math.max(gain, 0.001));
    var rcpQ = f(Math.sqrt(f(f(gain + f(1 / gain)) * 0) + 2));  // slope 1
    gain = Math.max(gain, 0.00001);
    var w0 = f(f(Math.PI * 2) * f0norm), sinW0 = f(Math.sin(w0)), cosW0 = f(Math.cos(w0));
    var alpha = f(f(sinW0 / 2) * rcpQ), sga2 = f(f(2 * f(Math.sqrt(gain))) * alpha);
    // Single-precision steps, as in the C++ (Real = float).
    var gp1 = f(gain + 1), gm1 = f(gain - 1), gm1c = f(gm1 * cosW0), gp1c = f(gp1 * cosW0);
    var b0, b1, b2, a0, a1, a2;
    if (type === HIGH_SHELF) {
      b0 = f(gain * f(f(gp1 + gm1c) + sga2));
      b1 = f(f(-2 * gain) * f(gm1 + gp1c));
      b2 = f(gain * f(f(gp1 + gm1c) - sga2));
      a0 = f(f(gp1 - gm1c) + sga2);
      a1 = f(2 * f(gm1 - gp1c));
      a2 = f(f(gp1 - gm1c) - sga2);
    } else {
      b0 = f(gain * f(f(gp1 - gm1c) + sga2));
      b1 = f(f(2 * gain) * f(gm1 - gp1c));
      b2 = f(gain * f(f(gp1 - gm1c) - sga2));
      a0 = f(f(gp1 + gm1c) + sga2);
      a1 = f(-2 * f(gm1 + gp1c));
      a2 = f(f(gp1 + gm1c) - sga2);
    }
    this.a1 = f(a1 / a0); this.a2 = f(a2 / a0);
    this.b0 = f(b0 / a0); this.b1 = f(b1 / a0); this.b2 = f(b2 / a0);
  };
  Biquad.prototype.copyParamsFrom = function (o) {
    this.b0 = o.b0; this.b1 = o.b1; this.b2 = o.b2; this.a1 = o.a1; this.a2 = o.a2;
  };
  // Two sections in series over buf[0..n), in place (DualBiquad).
  function dualProcess(p, q, buf, n) {
    var b00 = p.b0, b01 = p.b1, b02 = p.b2, a01 = p.a1, a02 = p.a2, z01 = p.z1, z02 = p.z2;
    var b10 = q.b0, b11 = q.b1, b12 = q.b2, a11 = q.a1, a12 = q.a2, z11 = q.z1, z12 = q.z2;
    for (var i = 0; i < n; i++) {
      var x = buf[i];
      var t = f(f(x * b00) + z01);
      z01 = f(f(f(x * b01) - f(t * a01)) + z02);
      z02 = f(f(x * b02) - f(t * a02));
      var y = f(f(t * b10) + z11);
      z11 = f(f(f(t * b11) - f(y * a11)) + z12);
      z12 = f(f(t * b12) - f(y * a12));
      buf[i] = y;
    }
    p.z1 = z01; p.z2 = z02; q.z1 = z11; q.z2 = z12;
  }

  // Four interleaved lines; lengths are powers of 2 so offsets wrap by masking.
  function DelayLine(length, frequency, extra) {
    var samples = nextPow2(f2u(Math.ceil(f(length * frequency))) + extra);
    this.mask = samples - 1;
    this.line = new Float32Array(samples * NUM_LINES);
  }
  DelayLine.prototype.write = function (offset, c, src, n) {
    var line = this.line, mask = this.mask;
    for (var i = 0; i < n; i++) line[((offset + i) & mask) * 4 + c] = src[i];
  };
  // Scatters reversed lines into the delay line (VectorScatterRevDelayIn).
  DelayLine.prototype.scatterRevIn = function (offset, x, y, src, n) {
    var line = this.line, mask = this.mask, s0 = src[0], s1 = src[1], s2 = src[2], s3 = src[3];
    for (var i = 0; i < n; i++) {
      var i0 = s3[i], i1 = s2[i], i2 = s1[i], i3 = s0[i], p = ((offset + i) & mask) * 4;
      line[p] = x * i0 + y * (i1 - i2 + i3);
      line[p + 1] = x * i1 + y * (-i0 + i2 + i3);
      line[p + 2] = x * i2 + y * (i0 - i1 + i3);
      line[p + 3] = x * i3 + y * (-i0 - i1 - i2);
    }
  };

  // Gerzon vector all-pass (VecAllpass::process), in place on four lines.
  function VecAllpass(length, frequency) {
    this.delay = new DelayLine(length, frequency, 0);
    this.coeff = 0;
    this.offset = [0, 0, 0, 0];
  }
  VecAllpass.prototype.process = function (s, offset, x, y, n) {
    var line = this.delay.line, mask = this.delay.mask, k = this.coeff, o = this.offset;
    var s0 = s[0], s1 = s[1], s2 = s[2], s3 = s[3];
    for (var i = 0; i < n; i++) {
      var off = offset + i;
      var in0 = s0[i], out0 = line[((off - o[0]) & mask) * 4] - k * in0, f0 = in0 + k * out0;
      var in1 = s1[i], out1 = line[((off - o[1]) & mask) * 4 + 1] - k * in1, f1 = in1 + k * out1;
      var in2 = s2[i], out2 = line[((off - o[2]) & mask) * 4 + 2] - k * in2, f2 = in2 + k * out2;
      var in3 = s3[i], out3 = line[((off - o[3]) & mask) * 4 + 3] - k * in3, f3 = in3 + k * out3;
      s0[i] = out0; s1[i] = out1; s2[i] = out2; s3[i] = out3;
      var p = (off & mask) * 4;
      line[p] = x * f0 + y * (f1 - f2 + f3);
      line[p + 1] = x * f1 + y * (-f0 + f2 + f3);
      line[p + 2] = x * f2 + y * (f0 - f1 + f3);
      line[p + 3] = x * f3 + y * (-f0 - f1 - f2);
    }
  };

  function calcDecayCoeff(length, decayTime) { return f(Math.pow(DECAY_GAIN, f(length / decayTime))); }
  function calcDecayLength(coeff, decayTime) { return f(f(f(Math.log10(coeff)) * decayTime) / -3); }
  function calcDelayLengthMult(density) { return Math.max(5, f(Math.cbrt(f(density * DENSITY_SCALE)))); }

  function T60Filter() { this.midGain = 0; this.hf = new Biquad(); this.lf = new Biquad(); }
  T60Filter.prototype.calcCoeffs = function (length, lfDecayTime, mfDecayTime, hfDecayTime, lf0norm, hf0norm) {
    var mfGain = calcDecayCoeff(length, mfDecayTime);
    var lfGain = f(calcDecayCoeff(length, lfDecayTime) / mfGain);
    var hfGain = f(calcDecayCoeff(length, hfDecayTime) / mfGain);
    this.midGain = mfGain;
    this.lf.setParamsFromSlope(LOW_SHELF, lf0norm, lfGain);
    this.hf.setParamsFromSlope(HIGH_SHELF, hf0norm, hfGain);
  };

  function zeros4(n) { return [new Float32Array(n), new Float32Array(n), new Float32Array(n), new Float32Array(n)]; }
  // Output gains per line: [left, right] current and target.
  function gains8() { var g = []; for (var i = 0; i < NUM_LINES; i++) g.push(new Float32Array(2)); return g; }

  // One of the two cross-faded reverb pipelines (ReverbPipeline).
  function Pipeline(frequency) {
    var multiplier = calcDelayLengthMult(1.0);
    var maxModDelay = f(MAX_MODULATION_TIME * MODULATION_DEPTH_COEFF / 2);
    this.filterLp = []; this.filterHp = [];
    for (var i = 0; i < NUM_LINES; i++) { this.filterLp.push(new Biquad()); this.filterHp.push(new Biquad()); }
    this.earlyDelayIn = new DelayLine(f(MAX_REFLECTIONS_DELAY + f(EARLY_TAP_LENGTHS[3] * multiplier)), frequency, BUFFER_LINE_SIZE);
    var lateLineDiffAvg = f(f(LATE_LINE_LENGTHS[3] - LATE_LINE_LENGTHS[0]) / NUM_LINES);
    this.lateDelayIn = new DelayLine(f(MAX_LATE_REVERB_DELAY + f(lateLineDiffAvg * multiplier)), frequency, BUFFER_LINE_SIZE);
    this.earlyDelayTap = [[0, 0], [0, 0], [0, 0], [0, 0]];
    this.earlyDelayCoeff = [0, 0, 0, 0];
    this.lateDelayTap = [[0, 0], [0, 0], [0, 0], [0, 0]];
    this.mixX = 0; this.mixY = 0;
    this.early = {
      vecAp: new VecAllpass(f(EARLY_ALLPASS_LENGTHS[3] * multiplier), frequency),
      delay: new DelayLine(f(EARLY_LINE_LENGTHS[3] * multiplier), frequency, MAX_UPDATE_SAMPLES),
      offset: [0, 0, 0, 0], coeff: [0, 0, 0, 0],
      currentGains: gains8(), targetGains: gains8()
    };
    this.late = {
      vecAp: new VecAllpass(f(LATE_ALLPASS_LENGTHS[3] * multiplier), frequency),
      delay: new DelayLine(f(f(LATE_LINE_LENGTHS[3] * multiplier) + maxModDelay), frequency, 4),
      offset: [0, 0, 0, 0], densityGain: 0,
      t60: [new T60Filter(), new T60Filter(), new T60Filter(), new T60Filter()],
      modIndex: 0, modStep: 1, modDepth: 0, modDelays: new Float32Array(MAX_UPDATE_SAMPLES),
      currentGains: gains8(), targetGains: gains8()
    };
    this.fadeSampleCount = 1;
  }
  Pipeline.prototype.clear = function () {
    for (var i = 0; i < NUM_LINES; i++) {
      this.filterLp[i].clear(); this.filterHp[i].clear();
      this.late.t60[i].hf.clear(); this.late.t60[i].lf.clear();
    }
  };
  Pipeline.prototype.clearLines = function () {
    this.earlyDelayIn.line.fill(0); this.lateDelayIn.line.fill(0);
    this.early.vecAp.delay.line.fill(0); this.early.delay.line.fill(0);
    this.late.vecAp.delay.line.fill(0); this.late.delay.line.fill(0);
  };

  Pipeline.prototype.updateDelayLine = function (earlyDelay, lateDelay, densityMult, decayTime, frequency) {
    for (var i = 0; i < NUM_LINES; i++) {
      var length = f(EARLY_TAP_LENGTHS[i] * densityMult);
      this.earlyDelayTap[i][1] = f2u(f(f(earlyDelay + length) * frequency));
      this.earlyDelayCoeff[i] = calcDecayCoeff(length, decayTime);
      length = f(f(f(f(LATE_LINE_LENGTHS[i] - LATE_LINE_LENGTHS[0]) / NUM_LINES) * densityMult) + lateDelay);
      this.lateDelayTap[i][1] = f2u(f(length * frequency));
    }
  };

  // B-Format transform that focuses the response toward a pan vector.
  function transformFromVector(vec) {
    var mag = Math.sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2]), n;
    if (mag > 1) { n = [vec[0] / mag * -SQRT3, vec[1] / mag * SQRT3, vec[2] / mag * SQRT3]; mag = 1; }
    else n = [vec[0] * -SQRT3, vec[1] * SQRT3, vec[2] * SQRT3];
    return [[1, 0, 0, 0], [n[0], 1 - mag, 0, 0], [n[1], 0, 1 - mag, 0], [n[2], 0, 0, 1 - mag]];
  }
  // A-Format line i to stereo: ambisonic coefficients through the decoder.
  function panLines(a2b, mat, gain, target) {
    for (var i = 0; i < NUM_LINES; i++) {
      var w = 0, y = 0, x = 0;
      for (var k = 0; k < NUM_LINES; k++) {
        var a = a2b[k][i];
        w += a * mat[0][k]; y += a * mat[1][k]; x += a * mat[3][k];
      }
      w = f(w * gain); y = f(y * gain); x = f(x * gain);
      target[i][0] = DECODE_W * w + DECODE_Y * y + DECODE_X * x;
      target[i][1] = DECODE_W * w - DECODE_Y * y + DECODE_X * x;
    }
  }
  Pipeline.prototype.update3DPanning = function (reflectionsPan, lateReverbPan, earlyGain, lateGain) {
    panLines(EARLY_A2B, transformFromVector(reflectionsPan), earlyGain, this.early.targetGains);
    panLines(LATE_A2B, transformFromVector(lateReverbPan), lateGain, this.late.targetGains);
  };

  Pipeline.prototype.updateEarlyLines = function (densityMult, diffusion, decayTime, frequency) {
    var e = this.early;
    e.vecAp.coeff = f(f(diffusion * diffusion) * INV_SQRT2);
    for (var i = 0; i < NUM_LINES; i++) {
      var length = f(EARLY_ALLPASS_LENGTHS[i] * densityMult);
      e.vecAp.offset[i] = f2u(f(length * frequency));
      length = f(EARLY_LINE_LENGTHS[i] * densityMult);
      e.offset[i] = f2u(f(length * frequency));
      e.coeff[i] = calcDecayCoeff(length, decayTime);
    }
  };

  Pipeline.prototype.updateModulator = function (modTime, modDepth, frequency) {
    var l = this.late;
    l.modStep = Math.max(fastf2u(f(MOD_FRACONE / f(frequency * modTime))), 1);
    var scale = modTime >= DEFAULT_MODULATION_TIME ? DEFAULT_MODULATION_TIME : modTime;
    l.modDepth = f(f(f(f(MODULATION_DEPTH_COEFF / 4) * scale) * modDepth) * frequency);
  };

  Pipeline.prototype.updateLateLines = function (densityMult, diffusion, lfDecayTime, mfDecayTime,
    hfDecayTime, lf0norm, hf0norm, frequency) {
    var l = this.late;
    var normWeightFactor = f(frequency / 20000);
    var lateAllpassAvg = f(sumf(LATE_ALLPASS_LENGTHS) / NUM_LINES);
    var length = f(f(f(sumf(LATE_LINE_LENGTHS) / NUM_LINES) + lateAllpassAvg) * densityMult);
    var decayTimeWeighted = f(f(f(f(lf0norm * normWeightFactor) * lfDecayTime) +
      f(f(f(hf0norm - lf0norm) * normWeightFactor) * mfDecayTime)) +
      f(f(1 - f(hf0norm * normWeightFactor)) * hfDecayTime));
    var a = calcDecayCoeff(length, decayTimeWeighted);
    l.densityGain = f(Math.sqrt(f(1 - f(a * a))));
    l.vecAp.coeff = f(f(diffusion * diffusion) * INV_SQRT2);
    for (var i = 0; i < NUM_LINES; i++) {
      length = f(LATE_ALLPASS_LENGTHS[i] * densityMult);
      l.vecAp.offset[i] = f2u(f(length * frequency));
      length = f(LATE_LINE_LENGTHS[i] * densityMult);
      l.offset[i] = Math.max(f2u(f(f(length * frequency) + 0.5)), 1) - 1;
      length = f(length + f(f(f(lerpf(LATE_ALLPASS_LENGTHS[i], lateAllpassAvg, diffusion) * densityMult) +
        f(l.modDepth / frequency))));
      l.t60[i].calcCoeffs(length, lfDecayTime, mfDecayTime, hfDecayTime, lf0norm, hf0norm);
    }
  };

  // Early reflections (ReverbPipeline::processEarly).
  Pipeline.prototype.processEarly = function (offset, samplesToDo, temp, out) {
    var inDelay = this.earlyDelayIn, inLine = inDelay.line, inMask = inDelay.mask;
    var e = this.early, eLine = e.delay.line, eMask = e.delay.mask;
    var mixX = this.mixX, mixY = this.mixY;
    for (var base = 0; base < samplesToDo;) {
      var todo = Math.min(samplesToDo - base, MAX_UPDATE_SAMPLES), fadeStep = f(1 / todo), i, j;
      for (j = 0; j < NUM_LINES; j++) {
        var tap0 = offset - this.earlyDelayTap[j][0], tap1 = offset - this.earlyDelayTap[j][1];
        var coeff = this.earlyDelayCoeff[j], coeffStep = tap0 !== tap1 ? f(coeff * fadeStep) : 0, t = temp[j];
        for (i = 0; i < todo; i++) {
          t[i] = inLine[((tap0 + i) & inMask) * 4 + j] * f(coeff - coeffStep * i) +
            inLine[((tap1 + i) & inMask) * 4 + j] * f(coeffStep * i);
        }
        this.earlyDelayTap[j][0] = this.earlyDelayTap[j][1];
      }
      e.vecAp.process(temp, offset, mixX, mixY, todo);
      for (j = 0; j < NUM_LINES; j++) e.delay.write(offset, NUM_LINES - 1 - j, temp[j], todo);
      for (j = 0; j < NUM_LINES; j++) {
        var feedbTap = offset - e.offset[j], feedbCoeff = e.coeff[j], tj = temp[j], o = out[j];
        for (i = 0; i < todo; i++) {
          tj[i] += eLine[((feedbTap + i) & eMask) * 4 + j] * feedbCoeff;
          o[base + i] = tj[i];
        }
      }
      this.lateDelayIn.scatterRevIn(offset, mixX, mixY, temp, todo);
      base += todo;
      offset += todo;
    }
  };

  // Late reverb feedback delay network (ReverbPipeline::processLate).
  Pipeline.prototype.processLate = function (offset, samplesToDo, temp, out) {
    var l = this.late, lateLine = l.delay.line, lateMask = l.delay.mask;
    var inLine = this.lateDelayIn.line, inMask = this.lateDelayIn.mask;
    var mixX = this.mixX, mixY = this.mixY, modDelays = l.modDelays;
    for (var base = 0; base < samplesToDo;) {
      var todo = Math.min(samplesToDo - base, Math.min(l.offset[0], MAX_UPDATE_SAMPLES)), i, j;
      // Modulated feedback delays (Modulation::calcDelays).
      var idx = l.modIndex, step = l.modStep, depth = l.modDepth, modScale = f(Math.PI * 2 / MOD_FRACONE);
      if (depth === 0) {
        // Depth 0 (most of Doom 3's presets) gives zero delays; skip the sines.
        modDelays.fill(0, 0, todo);
        idx = (idx + step * todo) >>> 0;
      } else {
        for (i = 0; i < todo; i++) {
          idx = (idx + step) >>> 0;
          modDelays[i] = f(f(f(Math.sin(f((idx & MOD_FRACMASK) * modScale))) + 1) * depth);
        }
      }
      l.modIndex = idx;
      var fadeStep = f(1 / todo);
      for (j = 0; j < NUM_LINES; j++) {
        var tap0 = offset - this.lateDelayTap[j][0], tap1 = offset - this.lateDelayTap[j][1];
        var feedbTap = offset - l.offset[j], midGain = l.t60[j].midGain;
        var densityGain = f(l.densityGain * midGain), densityStep = tap0 !== tap1 ? f(densityGain * fadeStep) : 0;
        var t = temp[j];
        for (i = 0; i < todo; i++) {
          var idelay = (modDelays[i] * 256) | 0, delay = feedbTap + i - (idelay >> 8), frac = idelay & 255;
          var fb = lateLine[(delay & lateMask) * 4 + j] * CUBIC[256 + frac] +
            lateLine[((delay - 1) & lateMask) * 4 + j] * CUBIC[frac] +
            lateLine[((delay - 2) & lateMask) * 4 + j] * CUBIC[256 - frac] +
            lateLine[((delay - 3) & lateMask) * 4 + j] * CUBIC[512 - frac];
          t[i] = fb * midGain + inLine[((tap0 + i) & inMask) * 4 + j] * f(densityGain - densityStep * i) +
            inLine[((tap1 + i) & inMask) * 4 + j] * f(densityStep * i);
        }
        this.lateDelayTap[j][0] = this.lateDelayTap[j][1];
        dualProcess(l.t60[j].hf, l.t60[j].lf, t, todo);
      }
      l.vecAp.process(temp, offset, mixX, mixY, todo);
      for (j = 0; j < NUM_LINES; j++) out[j].set(temp[j].subarray(0, todo), base);
      l.delay.scatterRevIn(offset, mixX, mixY, temp, todo);
      base += todo;
      offset += todo;
    }
  };

  // MixSamples for one line into left/right, ramping gains over the block.
  function mixLine(src, outL, outR, current, target, n) {
    var delta = n > 0 ? 1 / n : 0;
    for (var c = 0; c < 2; c++) {
      var dst = c ? outR : outL, gain = current[c], step = f((target[c] - gain) * delta), pos = 0;
      if (!(Math.abs(step) > FLT_EPSILON)) gain = target[c];
      else {
        for (; pos < n; pos++) dst[pos] += src[pos] * (gain + step * pos);
        gain = target[c];
      }
      current[c] = gain;
      if (!(Math.abs(gain) > GAIN_SILENCE)) continue;
      for (; pos < n; pos++) dst[pos] += src[pos] * gain;
    }
  }

  var DEVICE_CLEAR = 0, START_FADE = 1, FADING = 2, CLEANUP = 3, NORMAL = 4;

  function Reverb(frequency) {
    this.frequency = frequency;
    this.params = {
      density: 1, diffusion: 1, decayTime: 1.49, hfDecayTime: f(0.83 * 1.49), lfDecayTime: 1.49,
      modulationTime: 0.25, modulationDepth: 0, hfReference: 5000, lfReference: 250
    };
    this.state = DEVICE_CLEAR;
    this.current = 0;
    this.pipelines = [new Pipeline(frequency), new Pipeline(frequency)];
    this.offset = 0;
    this.temp = zeros4(MAX_UPDATE_SAMPLES);
    this.tempLine = new Float32Array(128);
    this.earlySamples = zeros4(128);
    this.lateSamples = zeros4(128);
  }

  // ReverbState::update. props uses OpenAL Soft's field names (lower camel case);
  // slotGain is AL_EFFECTSLOT_GAIN.
  Reverb.prototype.update = function (props, slotGain) {
    var frequency = this.frequency, p = this.params;
    var hfRatio = props.decayHFRatio;
    if (props.decayHFLimit && props.airAbsorptionGainHF < 1) {
      var limitRatio = f(f(1 / SPEED_OF_SOUND) / calcDecayLength(props.airAbsorptionGainHF, props.decayTime));
      hfRatio = Math.min(limitRatio, hfRatio);
    }
    var lfDecayTime = Math.min(Math.max(f(props.decayTime * props.decayLFRatio), 0.1), 20);
    var hfDecayTime = Math.min(Math.max(f(props.decayTime * hfRatio), 0.1), 20);
    var fullUpdate = this.state === DEVICE_CLEAR || p.density !== props.density ||
      p.diffusion !== props.diffusion || p.decayTime !== props.decayTime ||
      p.hfDecayTime !== hfDecayTime || p.lfDecayTime !== lfDecayTime ||
      p.modulationTime !== props.modulationTime || p.modulationDepth !== props.modulationDepth ||
      p.hfReference !== props.hfReference || p.lfReference !== props.lfReference;
    if (fullUpdate) {
      p.density = props.density; p.diffusion = props.diffusion; p.decayTime = props.decayTime;
      p.hfDecayTime = hfDecayTime; p.lfDecayTime = lfDecayTime;
      p.modulationTime = props.modulationTime; p.modulationDepth = props.modulationDepth;
      p.hfReference = props.hfReference; p.lfReference = props.lfReference;
      this.state = this.state !== DEVICE_CLEAR ? START_FADE : NORMAL;
      this.current ^= 1;
    }
    var pipeline = this.pipelines[this.current];
    var gain = f(props.gain * slotGain);
    pipeline.update3DPanning(props.reflectionsPan, props.lateReverbPan,
      f(props.reflectionsGain * gain), f(props.lateReverbGain * gain));

    var hf0norm = Math.min(f(props.hfReference / frequency), f(0.49));
    var lf0norm = Math.min(f(props.lfReference / frequency), f(0.49));
    pipeline.filterLp[0].setParamsFromSlope(HIGH_SHELF, hf0norm, props.gainHF);
    pipeline.filterHp[0].setParamsFromSlope(LOW_SHELF, lf0norm, props.gainLF);
    for (var i = 1; i < NUM_LINES; i++) {
      pipeline.filterLp[i].copyParamsFrom(pipeline.filterLp[0]);
      pipeline.filterHp[i].copyParamsFrom(pipeline.filterHp[0]);
    }

    var densityMult = calcDelayLengthMult(props.density);
    pipeline.updateDelayLine(props.reflectionsDelay, props.lateReverbDelay, densityMult, props.decayTime, frequency);
    if (fullUpdate) {
      pipeline.updateEarlyLines(densityMult, props.diffusion, props.decayTime, frequency);
      var t = f(props.diffusion * f(Math.atan(SQRT3)));
      pipeline.mixX = f(Math.cos(t));
      pipeline.mixY = f(f(Math.sin(t)) / SQRT3);
      pipeline.updateModulator(props.modulationTime, props.modulationDepth, frequency);
      pipeline.updateLateLines(densityMult, props.diffusion, lfDecayTime, props.decayTime, hfDecayTime,
        lf0norm, hf0norm, frequency);
    }
    var decaySamples = f(f(f(props.reflectionsDelay + props.lateReverbDelay) + props.decayTime) * frequency);
    pipeline.fadeSampleCount = f2u(Math.min(decaySamples, 1000000));
  };

  // Converts B-Format input to A-Format, filters it and feeds the early delay.
  // fade: 0 none, 1 fade in, -1 fade out.
  Reverb.prototype.feed = function (pipeline, input, n, fade) {
    var tmp = this.tempLine;
    for (var c = 0; c < NUM_LINES; c++) {
      tmp.fill(0, 0, n);
      if (input) {
        for (var k = 0; k < NUM_LINES && k < input.length; k++) {
          var g = B2A[c][k], src = input[k];
          for (var i = 0; i < n; i++) tmp[i] += src[i] * g;
        }
        if (fade) {
          var fadeStep = f(1 / n);
          for (i = 0; i < n; i++) tmp[i] *= fade > 0 ? f((i + 1) * fadeStep) : f(1 - f((i + 1) * fadeStep));
        }
      }
      dualProcess(pipeline.filterLp[c], pipeline.filterHp[c], tmp, n);
      pipeline.earlyDelayIn.write(this.offset, c, tmp, n);
    }
  };

  Reverb.prototype.mixOut = function (pipeline, outL, outR, n) {
    for (var c = 0; c < NUM_LINES; c++)
      mixLine(this.earlySamples[c], outL, outR, pipeline.early.currentGains[c], pipeline.early.targetGains[c], n);
    for (c = 0; c < NUM_LINES; c++)
      mixLine(this.lateSamples[c], outL, outR, pipeline.late.currentGains[c], pipeline.late.targetGains[c], n);
  };

  // ReverbState::process: input is four B-Format channels (W, Y, Z, X, N3D)
  // or null for silence; adds n (at most 128) samples to outL/outR.
  Reverb.prototype.process = function (input, outL, outR, n) {
    var oldPipeline = this.pipelines[this.current ^ 1], pipeline = this.pipelines[this.current];
    if (this.state >= FADING) {
      this.feed(pipeline, input, n, 0);
      if (this.state === FADING) this.feed(oldPipeline, null, n, 0);
    } else {
      this.feed(pipeline, input, n, 1);
      this.feed(oldPipeline, input, n, -1);
      this.state = FADING;
    }
    pipeline.processEarly(this.offset, n, this.temp, this.earlySamples);
    pipeline.processLate(this.offset, n, this.temp, this.lateSamples);
    this.mixOut(pipeline, outL, outR, n);
    if (this.state !== NORMAL) {
      if (this.state === CLEANUP) {
        oldPipeline.clearLines();
        oldPipeline.clear();
        this.state = NORMAL;
      } else {
        if (n >= oldPipeline.fadeSampleCount) {
          for (var c = 0; c < NUM_LINES; c++) {
            oldPipeline.early.targetGains[c].fill(0);
            oldPipeline.late.targetGains[c].fill(0);
          }
          oldPipeline.fadeSampleCount = 0;
          this.state = CLEANUP;
        } else oldPipeline.fadeSampleCount -= n;
        oldPipeline.processEarly(this.offset, n, this.temp, this.earlySamples);
        oldPipeline.processLate(this.offset, n, this.temp, this.lateSamples);
        this.mixOut(oldPipeline, outL, outR, n);
      }
    }
    // All line lengths divide 2^30, so wrapping keeps offsets in int range.
    this.offset = (this.offset + n) % 1073741824;
  };

  // True once a full update has set the effect and no cross-fade is running.
  Reverb.prototype.settled = function () { return this.state === NORMAL; };

  // Samples after which silent input has left the tail below -120 dB: the
  // current pipeline's -60 dB time doubled, and doubled again for an LF or
  // HF decay ratio of up to 2.
  Reverb.prototype.tailSamples = function () { return this.pipelines[this.current].fadeSampleCount * 4; };

  // Clears every line and filter, as a newly created effect state starts.
  Reverb.prototype.silence = function () {
    for (var i = 0; i < 2; i++) { this.pipelines[i].clearLines(); this.pipelines[i].clear(); }
  };

  if (typeof registerProcessor === 'function' && typeof AudioWorkletProcessor === 'function') {
    // One processor per auxiliary effect slot. Input: the four B-Format send
    // channels (a ChannelMerger). Output: stereo, added to the listener mix.
    // processorOptions and messages {props, gain} set the effect and slot
    // gain; props null clears the effect, as AL_EFFECTSLOT_EFFECT 0 does.
    class Processor extends AudioWorkletProcessor {
      constructor(options) {
        super();
        this.reverb = null;
        this.idle = 0;
        this.port.onmessage = (e) => this.set(e.data);
        if (options && options.processorOptions) this.set(options.processorOptions);
      }
      set(m) {
        if (!m.props) { this.reverb = null; return; }
        if (!this.reverb) this.reverb = new Reverb(sampleRate);
        this.reverb.update(m.props, m.gain);
        this.idle = 0;
      }
      process(inputs, outputs) {
        var reverb = this.reverb;
        if (!reverb) return true;
        var input = inputs[0], out = outputs[0], n = out[0].length, silent = true;
        for (var c = 0; c < input.length && silent; c++) {
          var ch = input[c];
          for (var i = 0; i < n; i++) if (ch[i] !== 0) { silent = false; break; }
        }
        // Native processes the slot on every update. Once the input has been
        // silent long enough for the tail to fall below -120 dB, the lines are
        // cleared and processing waits for the next send.
        if (silent && reverb.settled()) {
          if (this.idle > reverb.tailSamples()) return true;
          this.idle += n;
          if (this.idle > reverb.tailSamples()) { reverb.silence(); return true; }
        } else this.idle = 0;
        reverb.process(silent ? null : input, out[0], out[1], n);
        return true;
      }
    }
    registerProcessor('openal-eaxreverb', Processor);
  }
  // OpenAL Soft's shelf filter, for tests of the direct and send filters.
  Reverb.Biquad = Biquad;
  return Reverb;
}
