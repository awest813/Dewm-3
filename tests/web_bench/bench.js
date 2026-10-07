// Page-side helpers for licensed-data browser measurements (docs/WEB.md).
// Loaded into dhewm3.html by run_fixture.js and run_console_fixture.js; uses
// the launcher's own staging functions, so no shell code is modified.
// Archives are fetched from /doom3base/ and captures are posted to the local
// capture server.
(function () {
  var B = window.__bench = {};
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  B.sleep = sleep;
  B.captureUrl = 'http://127.0.0.1:8091/';
  B.cmd = function (text) { Module.ccall('Web_QueueCommand', null, ['string'], [text]); };
  // The shell keeps only the last 200,000 characters of console text, so a
  // numeric position goes stale in long sessions. B.mark() echoes a unique
  // line before the commands of interest; waits and slices start after it.
  var marks = 0;
  B.mark = function () {
    var token = 'BENCH_MARK_' + (++marks) + '_' + Date.now();
    B.cmd('echo ' + token);
    return token;
  };
  function start(from) {
    if (typeof from !== 'string') return from;
    var at = consoleText.lastIndexOf(from);
    return at < 0 ? -1 : at + from.length;
  }
  // Console text after a mark (or position), up to an optional end index.
  B.after = function (from, end) {
    var at = start(from);
    if (at < 0) throw Error('console text before ' + from + ' was trimmed');
    return consoleText.slice(at, end);
  };
  B.waitFor = async function (marker, from, seconds) {
    for (var i = 0; i < seconds * 4; i++) {
      var base = start(from);
      var at = base < 0 ? -1 : consoleText.indexOf(marker, base);
      if (at >= 0) return at;
      await sleep(250);
    }
    throw Error('timed out waiting for ' + marker);
  };
  B.stage = async function () {
    for (var i = 0; i < 240 && !runtimeReady; i++) await sleep(250);
    setStaging(true);
    resetStaging();
    for (var p = 0; p < 9; p++) {
      var name = 'pak00' + p + '.pk4';
      var r = await fetch('/doom3base/' + name);
      if (!r.ok) throw Error('fetch ' + name + ' ' + r.status);
      stageFile('base/' + name, await r.arrayBuffer());
    }
    finishStaging();
    if (missingArchives().length) throw Error('missing archives: ' + missingArchives().join(' '));
  };
  B.launch = async function () {
    var from = consoleText.length;
    startBtn.click();
    await B.waitFor('in_grabKeyboard', from, 120);
    await sleep(1000);
  };
  // Runs the fixture as one command buffer so frame/tick counts are fixed.
  B.fixture = async function (name) {
    name = name || 'hangar';
    var r = await fetch('/bench/' + name + '-fixture.cfg');
    if (!r.ok) throw Error('missing /bench/' + name + '-fixture.cfg; run prepare.py');
    FS.writeFile('/doom3/base/webfixture.cfg', await r.text());
    var from = B.mark();
    B.cmd('exec webfixture.cfg');
    var end = await B.waitFor('FIXTURE_DONE', from, 900);
    return B.after(from, end).split('\n').filter(function (l) { return /RENDER_STATE/.test(l); });
  };
  B.upload = async function (name, data) {
    var r = await fetch(B.captureUrl + name, { method: 'POST', body: typeof data === 'string' ? new Blob([data]) : data });
    if (!r.ok) throw Error('upload ' + name + ' ' + r.status);
  };
  B.views = {
    hangar: ['rails', 'stairs', 'saved_rail'],
    scenes: ['mc_underground', 'alphalabs1', 'delta2a', 'enpro', 'recycling1', 'hell1', 'delta5',
      'heat_glass', 'heat_breaky', 'heat_mask', 'reflect_glass', 'imp'],
  };
  // Posts the fixture's screenshots, in order, as <label>-<view>.png.
  B.saveShots = async function (label, views) {
    views = views || B.views.hangar;
    var dir = '/home/web_user/.local/share/dhewm3/base/screenshots/';
    var names = FS.readdir(dir).filter(function (n) { return /^shot\d+\.png$/.test(n); }).sort().slice(-views.length);
    if (names.length !== views.length) throw Error('expected ' + views.length + ' screenshots, found ' + names.length);
    for (var i = 0; i < names.length; i++) {
      await B.upload(label + '-' + views[i] + '.png', FS.readFile(dir + names[i]));
      FS.unlink(dir + names[i]);
    }
  };
  B.decode = async function (url) {
    var bmp = await createImageBitmap(await (await fetch(url)).blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
    var c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext('2d');
    g.drawImage(bmp, 0, 0);
    return g.getImageData(0, 0, bmp.width, bmp.height).data;
  };
  // Same metrics as tests/render_image_compare.py.
  B.cmp = function (a, b) {
    var sum = 0, max = 0, over16 = 0, n = 0;
    for (var i = 0; i < a.length; i += 4) {
      var m = 0;
      for (var k = 0; k < 3; k++) { var d = Math.abs(a[i + k] - b[i + k]); sum += d; if (d > m) m = d; }
      if (m > max) max = m;
      if (m > 16) over16++;
      n++;
    }
    return { mae: +(sum / (n * 3)).toFixed(6), max: max, over16pct: +(100 * over16 / n).toFixed(4) };
  };
  // Compares <label> captures with each reference prefix under /bench/captures/.
  B.compare = async function (label, references, views) {
    var out = {};
    for (var v of (views || B.views.hangar)) {
      var mine = await B.decode('/bench/captures/' + label + '-' + v + '.png'), row = {};
      for (var ref of references) {
        try { row[ref] = B.cmp(mine, await B.decode('/bench/captures/' + ref + '-' + v + '.png')); }
        catch (e) { row[ref] = 'missing'; }
      }
      out[v] = row;
    }
    return out;
  };
  // GPU time per engine animation callback (EXT_disjoint_timer_query_webgl2).
  B.gpu = async function (frames) {
    var gl = GLctx, ext = gl.getExtension('EXT_disjoint_timer_query_webgl2');
    if (!ext) return { unavailable: true };
    var raf = B.realRaf || (B.realRaf = window.requestAnimationFrame.bind(window));
    var pending = [], times = [], wall = [], last = 0, n = 0;
    window.requestAnimationFrame = function (cb) {
      return raf(function (t) {
        if (n >= frames) return cb(t);
        var q = gl.createQuery();
        gl.beginQuery(ext.TIME_ELAPSED_EXT, q);
        try { cb(t); } finally {
          gl.endQuery(ext.TIME_ELAPSED_EXT);
          pending.push(q); n++;
          if (last) wall.push(t - last);
          last = t;
        }
      });
    };
    while (n < frames) await sleep(100);
    window.requestAnimationFrame = raf;
    for (var i = 0; i < 100 && pending.length; i++) {
      await sleep(50);
      pending = pending.filter(function (q) {
        if (!gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE)) return true;
        if (!gl.getParameter(ext.GPU_DISJOINT_EXT)) times.push(gl.getQueryParameter(q, gl.QUERY_RESULT) / 1e6);
        gl.deleteQuery(q);
        return false;
      });
    }
    var sort = function (a) { return a.slice().sort(function (x, y) { return x - y; }); };
    times = sort(times); wall = sort(wall);
    if (!times.length) return { frames: 0, unavailable: 'every GPU sample was disjoint or unavailable' };
    return { frames: times.length, gpuP50: +times[times.length >> 1].toFixed(2),
      gpuP95: +times[Math.floor(times.length * 0.95)].toFixed(2), callbackIntervalP50: +wall[wall.length >> 1].toFixed(2) };
  };
  B.perf = async function (frames, setup) {
    if (setup) { B.cmd(setup); await sleep(2500); }
    var from = B.mark();
    B.cmd('webperf ' + frames);
    await B.waitFor('Web perf: light triangles', from, 180);
    await sleep(500);
    return B.after(from).split('\n').filter(function (l) { return /^Web (perf|pacing):/.test(l); });
  };
  // WebGL calls per rendered frame, by method (adds wrapper overhead; do not
  // combine with timing samples).
  B.callHistogram = async function (ms) {
    var counts = {}, on = true, frames = 0, lastDraws = 0;
    var P = WebGL2RenderingContext.prototype, originals = {};
    Object.getOwnPropertyNames(P).forEach(function (name) {
      var d = Object.getOwnPropertyDescriptor(P, name);
      if (!d || typeof d.value !== 'function' || name === 'constructor') return;
      originals[name] = d.value;
      P[name] = function () { if (on) counts[name] = (counts[name] | 0) + 1; return originals[name].apply(this, arguments); };
    });
    var raf = window.requestAnimationFrame.bind(window);
    (function tick() {
      var draws = (counts.drawElements | 0) + (counts.drawArrays | 0);
      if (draws !== lastDraws) { frames++; lastDraws = draws; }
      if (on) raf(tick);
    })();
    await sleep(ms || 3000);
    on = false;
    Object.keys(originals).forEach(function (name) { P[name] = originals[name]; });
    var f = Math.max(1, frames), total = 0, rows = [];
    Object.keys(counts).forEach(function (k) { total += counts[k]; rows.push([k, +(counts[k] / f).toFixed(1)]); });
    rows.sort(function (a, b) { return b[1] - a[1]; });
    return { frames: frames, callsPerFrame: +(total / f).toFixed(1), top: rows.slice(0, 25) };
  };
})();
