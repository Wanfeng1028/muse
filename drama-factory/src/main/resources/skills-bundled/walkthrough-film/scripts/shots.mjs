// Frame shots from a logical-clock film page — the review tool.
//
// INPUT   a page exposing window.seek(t); a list of times
// OUTPUT  <outdir>/t<time>.jpg per time, plus any page/console errors on stdout
//
//   node shots.mjs <outdir> <t> [t …]            # e.g. node shots.mjs /tmp/shotsA 63.0 66.9 86.5
//   THEME=light node shots.mjs /tmp/shotsL 63.0  # ALWAYS pass the theme you are reviewing
//
// env: FILM_ROOT (default cwd) · URL · THEME · W H (default 2560 1440) · DSF (device scale, default 0.5
//      so review JPEGs are cheap to look at) · JQ (82) · CHROME
//
// Rules of use:
//  - LOOK at every JPEG. "no page errors" proves the code ran, not that the frame is correct.
//  - Filenames carry ONE decimal by default; for 1/30 s smoothness checks pass a THREE-decimal
//    name (set NAME_DP=3) or shoot into a separate directory per burst.
//  - Max ~8 times per call, and run it with `nohup … > log 2>&1 &` then poll: browser.close() can
//    hang for minutes on some machines.
//  - A single page seeking from scene A to scene Z is NOT the same as a per-scene render: earlier
//    layers can stay visible. If a frame looks wrong here, render the scene before believing it.

import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const ROOT = process.env.FILM_ROOT || process.cwd();
const out = process.argv[2];
const times = process.argv.slice(3).map(Number).filter(n => !isNaN(n));
if (!out || !times.length) { console.error('usage: shots.mjs <outdir> <t> [t …]'); process.exit(1); }
fs.mkdirSync(out, { recursive: true });

const W = +(process.env.W || 2560), H = +(process.env.H || 1440);
const DSF = +(process.env.DSF || 0.5), JQ = +(process.env.JQ || 82), DP = +(process.env.NAME_DP || 1);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const URL = (process.env.URL || 'file://' + path.join(ROOT, 'index.html'))
          + '?render&t=0' + (process.env.THEME ? '&theme=' + process.env.THEME : '');

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
await new Promise(r => setTimeout(r, 600));

for (const tt of times) {
  await p.evaluate(x => { seek(x); }, tt);
  await new Promise(r => setTimeout(r, 120));
  const name = `t${tt.toFixed(DP).padStart(6 + (DP > 1 ? DP - 1 : 0), '0')}.jpg`;
  await p.screenshot({ path: path.join(out, name), type: 'jpeg', quality: JQ });
  console.log('shot', name);
}
console.log(errs.length ? [...new Set(errs)].join('\n') : 'no page errors');
await b.close();
