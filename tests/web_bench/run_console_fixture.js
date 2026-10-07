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
FS.writeFile('/doom3/base/webfixture.cfg', lines.join(NL) + NL + 'echo FIXTURE_DONE' + NL);
const from = B.mark();
B.cmd('exec webfixture.cfg');
const end = await B.waitFor('FIXTURE_DONE', from, +(ARGS.timeout || 900));
// Throws if the fixture's log outgrew the shell's console buffer.
const log = B.after(from, end);
const label = ARGS.label || ARGS.cfg;
await B.upload(label + '-console.txt', log);
return { label, lines: log.split(NL).length };
