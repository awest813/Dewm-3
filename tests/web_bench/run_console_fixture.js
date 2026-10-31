// Page script for cdp.mjs: runs a native console fixture (tests/<name>.cfg,
// copied to /bench/ by prepare.py) in the browser and posts the console log
// as <label>-console.txt for the matching tests/*_parity_check.py verifier.
//   cfg=combat_pursuit_parity  label=<name>  timeout=900 (seconds)
canvas.style.width = canvas.style.maxWidth = (ARGS.width || 640) + 'px';
await new Promise((resolve, reject) => {
  const s = document.createElement('script');
  s.src = '/bench/bench.js?' + Date.now();
  s.onload = resolve; s.onerror = reject;
  document.head.appendChild(s);
});
const B = __bench;
const NL = String.fromCharCode(10);
const source = await (await fetch('/bench/' + ARGS.cfg + '.cfg')).text();
// Browser form: no window mode or quit; the shell owns those.
const lines = source.split(NL).filter(l => !/^(\/\/|set r_fullscreen|set r_mode|quit\s*$)/.test(l.trim()));
await B.stage();
await B.launch();
// A unique completion token: the shell keeps only the last 200,000 characters
// of console text, so long fixtures are read back from the engine's own log
// (dhewm3log.txt, like native) rather than relative to a console mark.
const token = 'FIXTURE_DONE_' + Date.now();
FS.writeFile('/doom3/base/webfixture.cfg', lines.join(NL) + NL + 'echo FIXTURE_DONE' + NL + 'echo ' + token + NL);
const from = B.mark();
B.cmd('exec webfixture.cfg');
const deadline = Date.now() + 1000 * +(ARGS.timeout || 900);
while (consoleText.indexOf(token) < 0) {
  if (Date.now() > deadline) throw Error('timed out waiting for ' + token);
  await B.sleep(250);
}
let log = null, from_ = 'console';
const logPath = '/home/web_user/.local/share/dhewm3/dhewm3log.txt';
try {
  // stdio buffers the log file: print enough to flush the fixture's tail.
  B.cmd('echo ' + 'x'.repeat(1000)); B.cmd('echo ' + 'x'.repeat(1000)); B.cmd('echo ' + 'x'.repeat(1000));
  await B.sleep(500);
  const text = new TextDecoder().decode(FS.readFile(logPath));
  const start = text.lastIndexOf(from), end = text.indexOf(token, start);
  if (start >= 0 && end > start) { log = text.slice(start + from.length, end); from_ = 'engine log'; }
} catch (e) { /* no engine log: fall back to console text */ }
if (log === null) log = B.after(from, consoleText.indexOf(token));  // throws if trimmed
const label = ARGS.label || ARGS.cfg;
await B.upload(label + '-console.txt', log);
return { label, lines: log.split(NL).length, source: from_ };
