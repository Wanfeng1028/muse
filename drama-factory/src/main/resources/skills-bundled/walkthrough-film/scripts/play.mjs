// Error sweep: play the whole film headless at high rate and collect every page / console /
// render-time error. The cheapest regression test in the pipeline — run it after every edit, and
// once per shipped theme before reporting a round done.
//
// INPUT   a page exposing window.seek/play/render, window.t and window.TOTAL
// OUTPUT  "TOTAL <secs> errors: <n>" plus the first 40 unique errors
//
//   node play.mjs [rate]                 # default rate 6; 14 is a fast full sweep
//   THEME=light node play.mjs 14         # must also end `errors: 0`
//
// env: FILM_ROOT (default cwd) · URL · THEME · W H · DSF
//
// It wraps window.render so an exception inside one frame is logged WITH ITS TIMESTAMP and the
// sweep keeps going — otherwise the first bad frame hides every later one.

import puppeteer from 'puppeteer-core';
import path from 'path';

const ROOT = process.env.FILM_ROOT || process.cwd();
const rate = parseFloat(process.argv[2] || '6');
const W = +(process.env.W || 2560), H = +(process.env.H || 1440), DSF = +(process.env.DSF || 0.5);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const URL = (process.env.URL || 'file://' + path.join(ROOT, 'index.html'))
          + '?render&nocap&rate=' + rate + (process.env.THEME ? '&theme=' + process.env.THEME : '');

const b = await puppeteer.launch({
  executablePath: CHROME, headless: true,
  args: ['--no-sandbox', '--allow-file-access-from-files', '--mute-audio', '--hide-scrollbars'],
});
const p = await b.newPage();
await p.setViewport({ width: W, height: H, deviceScaleFactor: DSF });

const errs = [];
p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });

await p.goto(URL, { waitUntil: 'networkidle0', timeout: 90000 });
await p.evaluate(() => document.fonts.ready);
await p.evaluate(() => {
  const _r = render;
  window.render = function (gt) {
    try { _r(gt); }
    catch (e) { console.error('RENDERERR@' + (+gt).toFixed(2) + ' ' + e.message); }
  };
});
await new Promise(r => setTimeout(r, 500));

const TOTAL = await p.evaluate(() => TOTAL);
await p.evaluate(() => { seek(0); play(); });

const t0 = Date.now();
while (Date.now() - t0 < (TOTAL / rate + 10) * 1000) {
  const tt = await p.evaluate(() => t);
  if (tt >= TOTAL - 0.05) break;
  await new Promise(r => setTimeout(r, 500));
}

const uniq = [...new Set(errs)];
console.log('TOTAL', TOTAL, 'errors:', uniq.length);
if (uniq.length) console.log(uniq.slice(0, 40).join('\n'));
await b.close();
process.exit(uniq.length ? 1 : 0);
