// Test browser game-data handling without loading paid assets or WebAssembly.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/shell.html'), 'utf8');
assert.equal((html.match(/\{\{\{ SCRIPT \}\}\}/g) || []).length, 1,
  'Emscripten replaces every loader marker, including markers inside comments');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
const files = new Map();
const documentListeners = new Map();
const elementListeners = new Map();
const windowListeners = new Map();
let pointerRequests = 0, now = 1000, pendingTimer;
let consoleFrames = [];
function flushConsoleFrames() {
  const frames = consoleFrames;
  consoleFrames = [];
  frames.forEach(handler => handler());
}
const engineCalls = [];
const context = {
  location: { href: 'http://localhost:8080/dhewm3.html', search: '' },
  document: {
    body: { className: '', appendChild() {} },
    createElement(tag) { return { click() { context.download = { tag, href: this.href, filename: this.download }; }, remove() { context.linkRemoved = true; } }; },
    addEventListener(name, handler) { documentListeners.set(name, handler); },
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, {
        style: {}, value: 0, textContent: '', attributes: {},
        options: id === 'graphics-filtering' ? [1,2,4,8,16].map(value => ({value:String(value)})) : [],
        appendChild(child) { this.options.push(child); },
        focus() { context.focusedElement = id; },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        getBoundingClientRect() { return { width: 667, height: 500 }; },
        requestPointerLock() { ++pointerRequests; return { catch(handler) { context.rejectCapture = handler; } }; },
        addEventListener(name, handler) { elementListeners.set(id + ':' + name, handler); },
      });
      return elements.get(id);
    },
  },
  window: { addEventListener(name, handler) { windowListeners.set(name, handler); } },
  Date: { now() { return now; } }, Uint8Array,
  setTimeout(handler) { pendingTimer = handler; return 1; }, clearTimeout() {}, setInterval() {},
  requestAnimationFrame(handler) { consoleFrames.push(handler); return consoleFrames.length; },
  FS: {
    mkdirTree() {},
    writeFile(name, bytes) { files.set(name, bytes); },
    stat(name) {
      if (!files.has(name)) throw Error('missing');
      return { size: files.get(name).length, mode: 1 };
    },
    isFile(mode) { return mode === 1; },
    readdir() { return [...files.keys()].map(name => name.split('/').pop()); },
    unlink(name) { files.delete(name); },
  },
};
vm.createContext(context);
vm.runInContext(source, context);
context.Module.ccall = (...args) => engineCalls.push(args);
let swallowed = false;
documentListeners.get('keydown')({
  target: { tagName: 'INPUT' }, stopPropagation() { swallowed = true; },
});
assert.equal(swallowed, true, 'page command typing must not reach game bindings');
swallowed = false;
documentListeners.get('keydown')({
  target: context.canvas, stopPropagation() { swallowed = true; },
});
assert.equal(swallowed, false, 'canvas keyboard input must reach SDL');
documentListeners.get('mousemove')({
  target: { tagName: 'BUTTON' }, stopPropagation() { swallowed = true; },
});
assert.equal(swallowed, true, 'page controls must not turn the game camera');
swallowed = false;
documentListeners.get('mousemove')({
  target: context.canvas, stopPropagation() { swallowed = true; },
});
assert.equal(swallowed, false, 'canvas mouse movement must reach SDL');
context.document.pointerLockElement = context.canvas;
documentListeners.get('pointerlockchange')();
assert.equal(elements.get('mouse-status').textContent, 'Mouse captured.');
context.document.pointerLockElement = null;
documentListeners.get('pointerlockchange')();
assert.match(elements.get('mouse-status').textContent, /Mouse is free/);
context.runtimeReady = context.started = true;
context.Module.onMouseModeChange(true);
documentListeners.get('pointerlockerror')();
assert.match(elements.get('mouse-status').textContent, /Hold the right mouse button/);
swallowed = false;
documentListeners.get('mousemove')({ target: context.canvas, stopPropagation() { swallowed = true; } });
assert.equal(swallowed, true, 'unlocked hover must not turn the camera during gameplay');
documentListeners.get('mousedown')({ target: context.canvas, button: 2, clientX: 100, clientY: 200,
  preventDefault() {}, stopPropagation() {} });
assert.equal(context.dragLooking, true);
assert.equal(engineCalls.at(-1)[0], 'Web_SetDragLook');
assert.equal(engineCalls.at(-1)[3][0], 1, 'drag starts with fresh fractional-movement state');
swallowed = false;
documentListeners.get('mousemove')({ target: context.canvas, clientX: 107, clientY: 197,
  stopPropagation() { swallowed = true; } });
assert.equal(swallowed, true, 'drag does not also emit SDL absolute motion');
assert.equal(engineCalls.at(-1)[0], 'Web_DragMouse');
assert.deepEqual(Array.from(engineCalls.at(-1)[3]), [7, -3, 667, 500], 'first motion is measured from the drag origin');
documentListeners.get('mousemove')({ target: context.canvas, clientX: 112, clientY: 202,
  stopPropagation() {} });
assert.deepEqual(Array.from(engineCalls.at(-1)[3]), [5, 5, 667, 500], 'later motion uses the previous drag point');
documentListeners.get('mouseup')({ target: {}, button: 2, stopPropagation() {} });
assert.equal(context.dragLooking, false, 'releasing outside the canvas stops drag look');
documentListeners.get('mousedown')({ target: context.canvas, button: 2,
  preventDefault() {}, stopPropagation() {} });
windowListeners.get('blur')();
assert.equal(context.dragLooking, false, 'focus loss stops drag look');
documentListeners.get('mousedown')({ target: context.canvas, button: 2, clientX: 30, clientY: 40,
  preventDefault() {}, stopPropagation() {} });
elementListeners.get('canvas:mouseleave')();
assert.equal(context.dragLooking, false, 'leaving the canvas stops drag look');
documentListeners.get('mousedown')({ target: context.canvas, button: 2, clientX: 30, clientY: 40,
  preventDefault() {}, stopPropagation() {} });
context.Module.onMouseModeChange(false);
assert.equal(context.dragLooking, false, 'opening a menu stops drag look');
assert.match(elements.get('mouse-status').textContent, /Mouse is free/, 'menus do not advertise drag look');
swallowed = false;
documentListeners.get('mousemove')({ target: context.canvas, stopPropagation() { swallowed = true; } });
assert.equal(swallowed, false, 'menus retain normal absolute mouse motion');
context.Module.onMouseModeChange(true);
elementListeners.get('focus-game:click')();
context.canvas.requestPointerLock();
assert.equal(pointerRequests, 1, 'SDL and canvas requests share one pending capture');
context.rejectCapture({ name: 'UnknownError', message: 'host rejected capture' });
context.canvas.requestPointerLock();
assert.equal(pointerRequests, 1, 'same-gesture retry is suppressed after rejection');
now += 300;
context.canvas.requestPointerLock();
assert.equal(pointerRequests, 1, 'background SDL retries stay suppressed after rejection');
elementListeners.get('focus-game:click')();
assert.equal(pointerRequests, 2, 'a later click can retry capture');
assert.equal(context.captureFromGesture, false, 'retry permission ends with the gesture');
pendingTimer();
assert.equal(context.capturePending, false, 'missing browser events cannot leave capture stuck pending');
context.canvas.requestPointerLock();
assert.equal(pointerRequests, 2, 'a timed-out host also waits for an explicit retry');
context.document.pointerLockElement = context.canvas;
documentListeners.get('pointerlockchange')();
assert.equal(engineCalls.at(-1)[3][0], 1, 'confirmed capture reaches cursor visibility logic');
assert.equal(context.captureFailed, false);
context.Module.onMouseModeChange(true);
swallowed = false;
documentListeners.get('mousemove')({ target: context.canvas, stopPropagation() { swallowed = true; } });
assert.equal(swallowed, false, 'captured gameplay motion reaches SDL');
context.document.pointerLockElement = null;
documentListeners.get('pointerlockchange')();
assert.equal(engineCalls.at(-1)[3][0], 0);
context.captureFailure({ name: 'WrongDocumentError', message: 'The root document of this element is not valid for pointer lock.' });
assert.equal(elements.get('mouse-browser-help').hidden, false, 'document rejection offers a browser recovery path');
assert.equal(elements.get('mouse-game-link').value, context.location.href);
context.captureFailure();
assert.equal(elements.get('mouse-browser-help').hidden, false, 'generic error events do not erase a detailed rejection');
context.Module.onMouseModeChange(false);
assert.equal(elements.get('mouse-browser-help').hidden, true, 'menus do not show gameplay capture recovery');
context.Module.onMouseModeChange(true);
context.document.pointerLockElement = context.canvas;
documentListeners.get('pointerlockchange')();
assert.equal(elements.get('mouse-browser-help').hidden, true, 'successful capture removes recovery guidance');
assert.equal(context.captureDocumentRejected, false);
context.document.pointerLockElement = null;
context.captureFailure({ name: 'NotAllowedError', message: 'User gesture required' });
assert.equal(elements.get('mouse-browser-help').hidden, true, 'transient gesture failures retain the existing retry flow');
context.started = false;
console.log('Web mouse capture and drag-look regression tests passed.');

// Page focus must not retain movement or attack when releases occur outside SDL.
context.started = true;
elementListeners.get('canvas:blur')();
assert.equal(engineCalls.at(-1)[0], 'Web_ReleaseInput');
context.document.hidden = true;
documentListeners.get('visibilitychange')();
assert.equal(engineCalls.at(-1)[0], 'Web_ReleaseInput');
for (const tagName of ['SELECT', 'SUMMARY']) {
  swallowed = false;
  documentListeners.get('keydown')({ target: { tagName }, stopPropagation() { swallowed = true; } });
  assert.equal(swallowed, true, 'graphics controls must not send game bindings');
}
context.savesReady = true;
context.document.getElementById('graphics-controls').disabled = false;
let graphicsValues = [1, 0, 0, 1, 1.5, 1.2, 60, 8], graphicsWrites = [], filteringLimit = 16;
context.Module.ccall = (name, result, types, args) => {
  if (name === 'Web_GetTextureFilteringLimit') return filteringLimit;
  if (name === 'Web_GetGraphicsOption') return graphicsValues[args[0]];
  if (name === 'Web_SetGraphicsOption') {
    graphicsWrites.push([...args]); graphicsValues[args[0]] = args[1]; return 1;
  }
  engineCalls.push([name, result, types, args]);
};
context.readGraphics();
assert.equal(elements.get('graphics-bump').checked, true, 'normal-map control inverts skipBump');
assert.equal(elements.get('graphics-specular').checked, true);
assert.equal(elements.get('graphics-gamma').value, 1.5, 'read current engine values');
elements.get('graphics-gamma').value = 'invalid';
context.applyGraphics(false);
assert.equal(graphicsWrites.length, 0, 'validate all options before any write');
assert.equal(context.focusedElement, 'graphics-gamma', 'invalid setting receives focus');
assert.equal(elements.get('graphics-gamma').attributes['aria-invalid'], 'true');
elements.get('graphics-gamma').value = '';
context.applyGraphics(false);
assert.equal(graphicsWrites.length, 0, 'blank gamma rejected');
elements.get('graphics-gamma').value = '1.75';
elements.get('graphics-bump').checked = false;
context.applyGraphics(false);
assert.equal(graphicsValues[1], 1);
assert.equal(graphicsValues[4], 1.75);
assert.equal(elements.get('graphics-gamma').attributes['aria-invalid'], undefined, 'successful correction clears invalid state');
assert.match(elements.get('graphics-status').textContent, /Graphics applied/);
for (const limit of [30, 60, 0]) {
  elements.get('graphics-fps').value = String(limit);
  context.applyGraphics(false);
  assert.equal(graphicsValues[6], limit, 'each frame-limit choice reaches the engine');
}
graphicsWrites = [];
elements.get('graphics-fps').value = '45';
context.applyGraphics(false);
assert.equal(graphicsWrites.length, 0, 'invalid frame rates cannot partially apply graphics');
assert.equal(context.focusedElement, 'graphics-fps');
context.applyGraphics(true);
assert.deepEqual(graphicsValues, [1, 0, 0, 1, 1, 1, 60, 8], 'restore only graphics defaults with 60 FPS and 8x filtering');
for (const level of [1, 2, 4, 8, 16]) {
  elements.get('graphics-filtering').value = String(level);
  context.applyGraphics(false);
  assert.equal(graphicsValues[7], level, 'filtering choice reaches engine');
}
filteringLimit = 4;
context.readGraphics();
assert.equal(elements.get('graphics-filtering').value, 4, 'unsupported saved level shows effective GPU limit');
assert.equal(elements.get('graphics-filtering').options[3].disabled, true);
graphicsWrites = [];
elements.get('graphics-filtering').value = '8';
context.applyGraphics(false);
assert.equal(graphicsWrites.length, 0, 'unsupported filtering cannot partially apply other options');
assert.equal(context.focusedElement, 'graphics-filtering');
context.applyGraphics(true);
assert.equal(graphicsValues[7], 4, 'defaults respect device filtering limit');
graphicsValues[7] = 3;
context.readGraphics();
assert.equal(elements.get('graphics-filtering').value, 3, 'native intermediate filtering survives readback');
assert.equal(elements.get('graphics-filtering').options.length, 6);
context.applyGraphics(false);
assert.equal(graphicsValues[7], 3, 'unrelated Apply preserves intermediate filtering');
assert.equal(elements.get('graphics-filtering').options.length, 6, 'refresh replaces custom option');
filteringLimit = 1;
context.applyGraphics(true);
assert.equal(graphicsValues[7], 1, 'unsupported extension keeps standard filtering');
assert.match(elements.get('filtering-help').textContent, /standard texture filtering/);
filteringLimit = 16;
context.savesReady = false;
context.applyGraphics(true);
assert.match(elements.get('graphics-status').textContent, /saving is unavailable/);
elements.get('graphics-controls').disabled = true;
graphicsWrites = [];
context.applyGraphics(true);
assert.equal(graphicsWrites.length, 0, 'prestart controls guarded');
context.started = false;
context.Module.ccall = (...args) => engineCalls.push(args);
console.log('Web graphics and focus-release regression tests passed.');
context.runtimeReady = true;
assert.equal(context.missingArchives().length, 9);
assert.equal(context.stageFile('Doom 3/base/pak000.pk4', new Uint8Array([1]).buffer), true);
assert.equal(context.stageFile('Doom 3/d3xp/pak000.pk4', new Uint8Array([9]).buffer), false);
assert.equal(files.get('/doom3/base/pak000.pk4')[0], 1);
context.finishStaging();
assert.equal(context.dataReady, false, 'incomplete install must not enable Start');
for (let i = 1; i < 9; i++) {
  context.stageFile(`pak00${i}.pk4`, new Uint8Array([1]).buffer);
}
context.finishStaging();
assert.equal(context.dataReady, true);
assert.equal(context.focusedElement, 'start', 'complete loading leads keyboard users to Start');
assert.equal(elements.get('launcher-state').textContent, 'Ready to play');
assert.match(elements.get('datastatus').textContent, /9 of 9/);
const loadedFiles = files.size;
context.stageFileList([{ name: 'unrelated.txt' }]);
assert.equal(files.size, loadedFiles, 'unrecognized selection preserves already loaded archives');
assert.equal(context.dataReady, true);
assert.match(elements.get('status').textContent, /No original Doom 3/);
assert.equal(context.missingArchives().length, 0);
context.stageFile('pak008.pk4', new Uint8Array().buffer);
context.finishStaging();
assert.equal(context.dataReady, false, 'empty archives must not enable Start');
context.resetStaging();
assert.equal(files.size, 0, 'new selection must discard previous data');
assert.equal(context.dataReady, false);
assert.equal(context.archiveName('Doom 3/base/PAK000.PK4'), 'pak000.pk4');
assert.equal(context.archiveName('Doom 3/d3xp/pak000.pk4'), null);
assert.equal(context.archiveName('Doom 3/base/mod.pk4'), null);
const reads = [];
const pendingReads = [];
context.FileReader = class {
  readAsArrayBuffer(file) { reads.push(file.name); pendingReads.push(this); }
};
context.stageFileList([
  { name: 'doom3.exe' }, { name: 'pak000.pk4', webkitRelativePath: 'd3xp/pak000.pk4' },
  { name: 'PAK000.PK4', webkitRelativePath: 'base/PAK000.PK4' },
]);
assert.deepEqual(reads, ['PAK000.PK4'], 'filter unrelated files before allocating their buffers');
assert.equal(elements.get('pickfilesbtn').disabled, true);
context.stageFileList([{ name: 'pak001.pk4' }]);
assert.equal(reads.length, 1, 'an overlapping selection must not replace an active load');
pendingReads[0].result = new Uint8Array([1]).buffer;
pendingReads[0].onload();
context.finishStaging();
assert.equal(elements.get('pickfilesbtn').disabled, false);
assert.equal(elements.get('datastatus').className, 'note', 'incomplete archives must not display success');
assert.equal(elements.get('setup').attributes['aria-busy'], 'false');
context.runtimeReady = false;
context.stageFileList([{ name: 'pak001.pk4' }]);
assert.equal(reads.length, 1, 'picker cannot stage files before filesystem initialization');
context.runtimeReady = true;

// A mount failure permits session-only play, but never promises persistent saves.
context.IDBFS = {};
context.FS.mount = () => { throw Error('storage blocked'); };
context.runtimeReady = false;
context.Module.onRuntimeInitialized();
assert.equal(context.runtimeReady, true);
assert.equal(context.savesReady, false);
assert.match(elements.get('storage-status').textContent, /Progress may be lost/);
assert.equal(elements.get('pickfilesbtn').disabled, false);

context.FS.mount = () => {};
context.FS.syncfs = (populate, done) => done(null);
context.Module.onRuntimeInitialized();
assert.equal(context.savesReady, true);
assert.equal(elements.get('storage-status').textContent, 'Browser saves enabled.');

// Visibility must be established before SDL reads the canvas's CSS dimensions.
context.dataReady = true;
context.Module.callMain = () => { assert.equal(context.document.body.className, 'playing'); };
context.Module.ccall = (name) => name === 'Web_GetGraphicsOption' ? 1 : undefined;
elementListeners.get('start:click')();
assert.equal(elements.get('setup').className, 'done');
assert.equal(elements.get('focus-game').disabled, false);
assert.equal(elements.get('run-command').disabled, false);
assert.equal(elements.get('screenshot').disabled, false);
context.Blob = class { constructor(parts, options) { context.screenshotBlob = { parts, options }; } };
context.URL = { createObjectURL() { return 'blob:test-image'; }, revokeObjectURL(url) { context.revokedURL = url; } };
context.Module.ccall = (...args) => engineCalls.push(args);
elementListeners.get('screenshot:click')();
assert.equal(engineCalls.at(-1)[3][0], 'webscreenshot', 'screenshot is queued through the engine');
assert.equal(elements.get('screenshot').disabled, true, 'capture cannot overlap through the toolbar');
const screenshotCalls = engineCalls.length;
elementListeners.get('screenshot:click')();
assert.equal(engineCalls.length, screenshotCalls);
context.Module.onScreenshotReady(new Uint8Array([137,80,78,71]));
assert.equal(elements.get('screenshot-download').href, 'blob:test-image');
assert.match(elements.get('screenshot-download').download, /^doom3-\d+\.png$/);
assert.equal(elements.get('screenshot-download').hidden, false, 'capture offers a direct download gesture');
assert.equal(elements.get('screenshot-image').src, 'blob:test-image', 'preview uses the captured engine PNG');
assert.equal(elements.get('screenshot-preview').hidden, false, 'capture can be inspected without a download');
assert.equal(context.screenshotBlob.options.type, 'image/png');
assert.equal(context.revokedURL, undefined, 'the current image stays available for retry');
context.URL.createObjectURL = () => 'blob:second-image';
context.Module.onScreenshotReady(new Uint8Array([137,80,78,71]));
assert.equal(context.revokedURL, 'blob:test-image', 'replacement releases the previous image');
assert.equal(elements.get('screenshot-download').href, 'blob:second-image');
assert.equal(elements.get('screenshot-image').src, 'blob:second-image', 'preview follows the replacement before the old URL is released');
assert.equal(elements.get('screenshot').disabled, false);
context.Module.onScreenshotReady(null, 'Capture unavailable');
assert.equal(elements.get('screenshot-status').textContent, 'Capture unavailable');
assert.equal(elements.get('screenshot-download').href, 'blob:second-image', 'capture failure retains the last successful image');
assert.equal(elements.get('screenshot-image').src, 'blob:second-image', 'capture failure retains the last successful preview');
context.URL.createObjectURL = () => { throw Error('download unavailable'); };
context.Module.onScreenshotReady(new Uint8Array([137,80,78,71]));
assert.match(elements.get('screenshot-status').textContent, /Could not download/);
context.wantsMouse = false;
elementListeners.get('focus-game:click')();
assert.equal(context.focusedElement, 'canvas');
context.started = false;
context.dataReady = true;
context.Module.callMain = () => { throw Error('startup failure'); };
elementListeners.get('start:click')();
assert.equal(elements.get('setup').className, '', 'startup errors must leave recovery instructions visible');
assert.match(elements.get('status').textContent, /Reload this page/);
assert.equal(elements.get('developer-console').hidden, false);
assert.equal(elements.get('start').disabled, true, 'a failed engine cannot safely be initialized twice');
assert.equal(context.document.body.className, '');
assert.equal(elements.get('retry').hidden, false, 'startup failure offers a visible reload action');
assert.equal(elements.get('graphics-controls').disabled, true);
assert.equal(elements.get('run-command').disabled, true);
assert.equal(elements.get('screenshot').disabled, true);
assert.equal(elements.get('launcher-state').textContent, 'Engine unavailable');
assert.equal(context.focusedElement, 'retry', 'startup failure leads keyboard users to the recovery action');
let reloads = 0;
context.location = { reload() { reloads++; } };
elementListeners.get('retry:click')();
assert.equal(reloads, 1);
console.log('Web shell game-data regression tests passed.');

// Trace failures must never stringify pixel buffers: Emscripten passes
// a view of its large linear memory to readPixels.
class TraceGL {
  readPixels() {}
  getError() { return 0x502; }
}
context.location = { search: '?gl-debug=1' };
context.ArrayBuffer = ArrayBuffer;
context.window.WebGL2RenderingContext = TraceGL;
vm.runInContext(source, context);
const pixels = new Uint8Array(4);
pixels.toString = () => { throw Error('pixel buffer must not be stringified'); };
assert.doesNotThrow(() => new TraceGL().readPixels(0, 0, 1, 1, 0, 0, pixels));
flushConsoleFrames();
assert.match(elements.get('console').textContent, /Uint8Array\[4 bytes\]/);
console.log('WebGL trace buffer regression test passed.');

// Heavy diagnostic output must retain its ordered tail without per-line DOM
// writes/layout reads, and must not pull readers away from earlier messages.
const consoleElement = elements.get('console');
let consoleWrites = 0, consoleLayoutReads = 0, consoleContents = consoleElement.textContent;
Object.defineProperty(consoleElement, 'textContent', {
  configurable: true, get() { return consoleContents; },
  set(value) { ++consoleWrites; consoleContents = value; },
});
Object.defineProperty(consoleElement, 'scrollHeight', {
  configurable: true, get() { ++consoleLayoutReads; return 1000; },
});
consoleElement.clientHeight = 220;
consoleElement.scrollTop = 780;
context.consoleText = '';
for (let i = 0; i < 1000; i++) context.Module.print('line ' + i);
assert.equal(consoleFrames.length, 1, 'a burst schedules one console update');
assert.equal(consoleWrites, 0, 'logging does not mutate DOM per line');
assert.equal(consoleLayoutReads, 0, 'logging does not force layout per line');
flushConsoleFrames();
assert.equal(consoleWrites, 1);
assert.equal(consoleLayoutReads, 1);
assert.equal(consoleContents, Array.from({length: 1000}, (_, i) => 'line ' + i + '\n').join(''));
consoleElement.scrollTop = 100;
elementListeners.get('console:scroll')();
context.Module.printErr('reader stays here');
flushConsoleFrames();
assert.equal(consoleElement.scrollTop, 100, 'new output preserves a reader above the tail');
assert.match(consoleContents, /\[err\] reader stays here\n$/);
consoleElement.scrollTop = 780;
elementListeners.get('console:scroll')();
context.Module.print('x'.repeat(250000));
context.Module.print('last line');
flushConsoleFrames();
assert.equal(consoleContents.length, 200000, 'buffer and DOM keep a bounded tail');
assert.ok(consoleContents.endsWith('\nlast line\n'));
assert.equal(consoleElement.scrollTop, 1000, 'returning to the tail resumes following');
context.Module.printErr('immediate fatal detail');
context.showEngineFailure('failed');
assert.match(consoleContents, /\[err\] immediate fatal detail\n$/, 'fatal details flush before showing recovery');
flushConsoleFrames();
console.log('Web console batching and scroll regressions passed.');

async function checkFolderRecovery() {
  context.setTimeout = handler => setImmediate(handler);
  context.runtimeReady = true;
  context.started = context.staging = false;
  const status = elements.get('status');
  status.textContent = 'Existing selection';
  context.window.showDirectoryPicker = async () => { throw { name: 'AbortError' }; };
  elementListeners.get('pickdir:click')();
  await new Promise(setImmediate);
  assert.equal(status.textContent, 'Existing selection', 'canceling the picker preserves the current state');
  context.window.showDirectoryPicker = async () => { throw { name: 'NotAllowedError' }; };
  elementListeners.get('pickdir:click')();
  await new Promise(setImmediate);
  assert.match(status.textContent, /Use Select .pk4 files instead/, 'folder permission errors expose an alternative');

  files.clear();
  for (let i = 0; i < 9; i++) context.stageFile(`pak00${i}.pk4`, new Uint8Array([1]).buffer);
  context.finishStaging();
  context.window.showDirectoryPicker = async () => ({ async *values() {} });
  elementListeners.get('pickdir:click')();
  await new Promise(setImmediate);
  assert.equal(files.size, 9, 'an empty folder preserves the previously loaded archives');
  assert.equal(context.dataReady, true);
  assert.equal(elements.get('start').disabled, false);
  assert.match(status.textContent, /No original Doom 3 archives/);
  assert.equal(elements.get('progress').style.display, 'none');

  context.window.showDirectoryPicker = async () => ({ async *values() { throw Error('folder disconnected'); } });
  elementListeners.get('pickdir:click')();
  await new Promise(setImmediate);
  assert.equal(files.size, 9, 'a failed folder scan preserves the loaded archives');
  assert.equal(context.dataReady, true);
  assert.equal(context.staging, false);
  assert.match(status.textContent, /Could not read that folder/);

  const handle = {
    async *values() {
      for (let i = 0; i < 9; i++) yield {
        kind: 'file', name: `pak00${i}.pk4`,
        async getFile() { return { async arrayBuffer() { return new Uint8Array([1]).buffer; } }; },
      };
    },
  };
  context.window.showDirectoryPicker = async () => handle;
  elementListeners.get('pickdir:click')();
  for (let i = 0; i < 12; i++) await new Promise(setImmediate);
  assert.equal(context.dataReady, true);
  assert.equal(elements.get('start').disabled, false);
  assert.equal(context.focusedElement, 'start');

  context.window.showDirectoryPicker = async () => ({
    async *values() {
      yield {kind: 'file', name: 'pak000.pk4', async getFile() { throw Error('archive unreadable'); }};
      yield {kind: 'file', name: 'pak001.pk4', async getFile() {
        return {async arrayBuffer() { return new Uint8Array([1]).buffer; }};
      }};
    },
  });
  elementListeners.get('pickdir:click')();
  for (let i = 0; i < 5; i++) await new Promise(setImmediate);
  assert.equal(context.staging, false, 'unreadable archives do not leave the importer busy');
  assert.equal(context.dataReady, false);
  assert.equal(files.has('/doom3/base/pak001.pk4'), true, 'later archives still load after one read fails');
  assert.match(elements.get('datastatus').textContent, /1 of 9.*pak000.pk4/);
  assert.equal(elements.get('pickdir').disabled, false, 'failed imports can be retried');
  console.log('Web launcher folder recovery regressions passed.');
}
async function checkScreenshotCopy() {
  let copyFeedback;
  context.setTimeout = (handler, delay) => { assert.equal(delay, 5000); copyFeedback = handler; return 1; };
  assert.equal(elements.get('screenshot-copy').hidden, true, 'unsupported image copy is hidden');
  const writes = [];
  context.ClipboardItem = class { constructor(data) { this.data = data; } };
  context.navigator = {clipboard:{async write(items) { writes.push(items); }}};
  context.URL.createObjectURL = () => 'blob:copy-image';
  context.Module.onScreenshotReady(new Uint8Array([137,80,78,71]));
  const image = context.lastScreenshotBlob;
  assert.equal(elements.get('screenshot-copy').hidden, false);
  await elementListeners.get('screenshot-copy:click')();
  assert.equal(writes[0][0].data['image/png'], image, 'copy exports the engine PNG without canvas recompression');
  assert.match(elements.get('screenshot-status').textContent, /Screenshot copied/);
  assert.equal(elements.get('screenshot-copy').disabled, false);
  context.navigator.clipboard.write = async () => { throw Error('permission denied'); };
  await elementListeners.get('screenshot-copy:click')();
  assert.match(elements.get('screenshot-status').textContent, /Choose Download PNG/);
  assert.equal(elements.get('screenshot-copy').disabled, false, 'rejection permits a later retry');
  assert.equal(context.lastScreenshotBlob, image, 'rejection retains the original capture');
  let finish;
  context.navigator.clipboard.write = () => new Promise(resolve => { finish = resolve; });
  const pending = elementListeners.get('screenshot-copy:click')();
  assert.equal(elements.get('screenshot-copy').disabled, true);
  assert.match(elements.get('screenshot-status').textContent, /Copying screenshot/);
  copyFeedback();
  assert.match(elements.get('screenshot-status').textContent, /still waiting for the browser/);
  assert.equal(elements.get('screenshot-copy').disabled, true, 'waiting feedback cannot overlap clipboard writes');
  context.Module.onScreenshotReady(new Uint8Array([137,80,78,71,2]));
  assert.equal(elements.get('screenshot-copy').disabled, true, 'replacement cannot overlap a pending copy');
  assert.match(elements.get('screenshot-status').textContent, /earlier image copy is still waiting/, 'replacement explains why Copy remains disabled');
  copyFeedback();
  assert.match(elements.get('screenshot-status').textContent, /Screenshot ready/, 'old waiting timer does not overwrite a replacement capture');
  finish();
  await pending;
  assert.match(elements.get('screenshot-status').textContent, /Screenshot ready/, 'old copy completion does not overwrite new capture status');
  assert.equal(elements.get('screenshot-copy').disabled, false);
  copyFeedback();
  assert.match(elements.get('screenshot-status').textContent, /Screenshot ready/, 'settled copy cannot display stale waiting feedback');
  context.ClipboardItem.supports = () => false;
  context.Module.onScreenshotReady(new Uint8Array([137,80,78,71]));
  assert.equal(elements.get('screenshot-copy').hidden, true, 'browsers without PNG clipboard support keep preview and download');
  console.log('Web screenshot copy regressions passed.');
}
async function checkMouseLinkCopy() {
  context.location = { href: 'http://localhost:8080/dhewm3.html', search: '' };
  const button = elements.get('mouse-copy-link');
  context.navigator = {};
  await elementListeners.get('mouse-copy-link:click')();
  assert.match(elements.get('mouse-copy-status').textContent, /Select the address/);
  assert.equal(context.focusedElement, 'mouse-game-link', 'unsupported clipboard leaves a selectable URL');
  let finish, writes = 0;
  context.navigator.clipboard = { writeText(value) {
    assert.equal(value, context.location.href, 'copy exports only the game address');
    ++writes;
    return new Promise(resolve => { finish = resolve; });
  } };
  const pending = elementListeners.get('mouse-copy-link:click')();
  assert.equal(button.disabled, true);
  await elementListeners.get('mouse-copy-link:click')();
  assert.equal(writes, 1, 'pending copies cannot overlap');
  finish();
  await pending;
  assert.match(elements.get('mouse-copy-status').textContent, /Link copied/);
  assert.equal(button.disabled, false);
  context.navigator.clipboard.writeText = async () => { throw Error('permission denied'); };
  await elementListeners.get('mouse-copy-link:click')();
  assert.match(elements.get('mouse-copy-status').textContent, /Select the address/);
  assert.equal(button.disabled, false, 'clipboard rejection permits retry and manual copy');
  console.log('Web mouse-link recovery regressions passed.');
}
checkMouseLinkCopy().then(checkScreenshotCopy).then(checkFolderRecovery).catch(error => { console.error(error); process.exitCode = 1; });
