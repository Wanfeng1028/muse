// Deterministic frame-step render of ONE scene of a logical-clock film.
//
// Every output frame is seek(t) + screenshot, so the result never depends on the page's real-time
// performance: no dropped frames, no duplicated frames, identical output on every machine.
// (A real-time screencast duplicated ~50% of frames in heavy blur/glass chapters.)
//
// INPUT   a page exposing window.seek(t) and window.render(t), and a timing.json with
//         { total, scenes:[ { id, start, dur, cues:[…] } … ] }
// OUTPUT  one MP4 per scene at OUT (default renders_${VER}/NN_<id>.mp4), video + that scene's VO slice
//
//   node render_scene_step.mjs <sceneId|index> [out.mp4]
//
// env: FILM_ROOT  project root (default: cwd)
//      URL        page URL (default: file://$FILM_ROOT/index.html)
//      TIMING     timing.json path (default: $FILM_ROOT/audio/timing.json)
//      VO         voiceover file to slice (default: $FILM_ROOT/audio/voiceover.mp3; empty = silent)
//      THEME      appended as &theme=… — ALWAYS thread this through or you render the default skin
//      VER        version tag for the default output dir (default: v1)
//      W H FPS    frame size and rate (default 2560 1440 30)
//      JQ CRF     jpeg quality / x264 crf (default 92 / 16)
//      CHROME     Chrome executable path
//      TMPDIR_    scratch dir for the frame sequence (default: os.tmpdir())

import puppeteer from 'puppeteer-core';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { execSync } from 'child_process';

const ROOT   = process.env.FILM_ROOT || process.cwd();
const TIMING = process.env.TIMING || path.join(ROOT, 'audio/timing.json');
const VOFILE = process.env.VO === undefined ? path.join(ROOT, 'audio/voiceover.mp3') : process.env.VO;
const VER    = process.env.VER || 'v1';
const W = +(process.env.W || 2560), H = +(process.env.H || 1440), FPS = +(process.env.FPS || 30);
const JQ = +(process.env.JQ || 92), CRF = +(process.env.CRF || 16);
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const T = JSON.parse(fs.readFileSync(TIMING, 'utf8'));
const arg = process.argv[2];
if (!arg) { console.error('usage: render_scene_step.mjs <sceneId|index> [out.mp4]'); process.exit(1); }
const idx = isNaN(+arg) ? T.scenes.findIndex(s => s.id === arg) : +arg;
const sc = T.scenes[idx];
if (!sc) { console.error('no such scene:', arg); process.exit(1); }

const { start, dur } = sc;
const N = Math.round(dur * FPS);
const URL = (process.env.URL || 'file://' + path.join(ROOT, 'index.html'))
          + '?render&t=0' + (process.env.THEME ? '&theme=' + process.env.THEME : '');
const OUT = process.argv[3] || path.join(ROOT, `renders_${VER}`, `${String(idx).padStart(2, '0')}_${sc.id}.mp4`);
const TMP = path.join(process.env.TMPDIR_ || os.tmpdir(), `rstep_${VER}_${sc.id}`);

fs.rmSync(TMP, { recursive: true, force: true });
fs.mkdirSync(path.join(TMP, 'seq'), { recursive: true });
fs.mkdirSync(path.dirname(OUT), { recursive: true });
console.log(`scene ${idx} ${sc.id}  ${start} → ${(start + dur).toFixed(3)} (${dur}s)  ${N} frames`);

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--allow-file-access-from-files', '--mute-audio', '--hide-scrollbars',
         `--window-size=${W},${H}`, '--force-device-scale-factor=1',
         '--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--use-angle=metal'],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const errs = [];
page.on('pageerror', e => errs.push('PAGEERR ' + e.message));

await page.goto(URL, { waitUntil: 'networkidle0', timeout: 90000 });
await page.evaluate(() => document.fonts.ready);
await new Promise(r => setTimeout(r, 400));

// Warm the scene one frame BEFORE its start so enter() side effects, fonts and layout have settled;
// without this, frame 0 of a scene differs from every later render of the same scene.
await page.evaluate(s => seek(s), Math.max(0, start - 0.05));
await new Promise(r => setTimeout(r, 200));

const t0 = Date.now();
for (let k = 0; k < N; k++) {
  const tt = start + (k + 0.5) / FPS;                    // sample the middle of the frame interval
  await page.evaluate(x => new Promise(res => {
    seek(x);
    requestAnimationFrame(() => requestAnimationFrame(res));  // apply styles, then let the compositor settle
  }), tt);
  await page.screenshot({ path: path.join(TMP, 'seq', `s${String(k).padStart(5, '0')}.jpg`), type: 'jpeg', quality: JQ });
  if (k && k % 150 === 0) console.log(`  ${k}/${N} frames, ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
console.log(`captured ${N} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s`,
            errs.length ? errs.join(' | ') : 'no page errors');
try { browser.process().kill('SIGKILL'); } catch (e) {}   // close() can hang for minutes

const audio = VOFILE && fs.existsSync(VOFILE)
  ? `-ss ${start} -t ${dur} -i "${VOFILE}" -c:a aac -b:a 192k -shortest` : '-an';
execSync(`ffmpeg -y -v error -framerate ${FPS} -i "${path.join(TMP, 'seq')}/s%05d.jpg" ${audio} ` +
         `-c:v libx264 -crf ${CRF} -preset medium -pix_fmt yuv420p -g ${FPS} -movflags +faststart "${OUT}"`,
         { stdio: 'inherit' });
fs.rmSync(TMP, { recursive: true, force: true });
console.log('wrote', OUT);
process.exit(0);
