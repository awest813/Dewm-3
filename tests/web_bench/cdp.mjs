// Minimal Chrome DevTools driver for the licensed-data browser bench.
//
//   node tests/web_bench/cdp.mjs <page-url|-> <page-script.js> [key=value ...]
//
// Connects to Chrome on 127.0.0.1:9222 (--remote-debugging-port=9222),
// optionally navigates its first page, then runs the script's body inside an
// async function with `ARGS` bound to the key=value pairs. The script's
// return value is printed as JSON. Uses Node's built-in WebSocket (Node 22+).
import { readFileSync } from 'node:fs';

const [, , url, scriptFile, ...pairs] = process.argv;
if (!scriptFile) {
  console.error('usage: node cdp.mjs <page-url|-> <page-script.js> [key=value ...]');
  process.exit(2);
}
const args = Object.fromEntries(pairs.map(p => [p.slice(0, p.indexOf('=')), p.slice(p.indexOf('=') + 1)]));
const targets = await (await fetch('http://127.0.0.1:9222/json')).json();
const page = targets.find(t => t.type === 'page');
if (!page) {
  console.error('Chrome on port 9222 has no open page; start it with about:blank');
  process.exit(2);
}
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener('message', ev => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const send = (method, params = {}) => new Promise(r => {
  const i = ++id;
  pending.set(i, r);
  ws.send(JSON.stringify({ id: i, method, params }));
});

if (url && url !== '-') {
  await send('Page.enable');
  await send('Page.navigate', { url });
  await new Promise(r => setTimeout(r, 3000));
}
const body = readFileSync(scriptFile, 'utf8');
const res = await send('Runtime.evaluate', {
  expression: `(async () => { const ARGS = ${JSON.stringify(args)};\n${body}\n})()`,
  awaitPromise: true, returnByValue: true, timeout: 1800000,
});
ws.close();
if (res.result?.exceptionDetails) {
  console.error(JSON.stringify(res.result.exceptionDetails, null, 1).slice(0, 4000));
  process.exit(1);
}
console.log(JSON.stringify(res.result?.result?.value, null, 1));
