#!/usr/bin/env node
// Fast isolated scene stills.
//   node tools/stills.mjs S05 0,30,60,90 [scale=0.5]      # specific LOCAL frames
//   node tools/stills.mjs S05 auto                        # 8 evenly spaced frames
// Bundles ONLY src/entries/<id>.tsx (other scenes' work-in-progress can't break it), renders the frames to
// out/stills/<id>/f###.png and a 2-column contact sheet out/stills/<id>/sheet.jpg (needs ffmpeg).
import { bundle } from '@remotion/bundler';
import { renderStill, selectComposition } from '@remotion/renderer';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const [id, framesArg, scaleArg] = process.argv.slice(2);
if (!id || !framesArg) { console.error('usage: node tools/stills.mjs S05 0,30,60 [0.5] | auto'); process.exit(1); }
const scale = scaleArg ? Number(scaleArg) : 0.5;
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const outDir = path.join(root, 'out', 'stills', id);
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(root, 'src', 'entries', `${id}.tsx`), publicDir: path.join(root, 'public'), outDir: path.join(root, 'out', `.bundle-${id}`) });
const composition = await selectComposition({ serveUrl, id });
const frames = framesArg === 'auto'
  ? Array.from({ length: 8 }, (_, i) => Math.round((i * (composition.durationInFrames - 1)) / 7))
  : framesArg.split(',').map(Number);
const files = [];
for (const f of frames) {
  const output = path.join(outDir, `f${String(f).padStart(3, '0')}.png`);
  await renderStill({ composition, serveUrl, output, frame: f, scale, imageFormat: 'png' });
  files.push(output);
  console.log('rendered', output);
}
const sheet = path.join(outDir, 'sheet.jpg');
try {
  if (files.length === 1) {
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', files[0], '-vf', 'scale=960:-1', '-q:v', '3', sheet]);
  } else {
    const cols = 2, n = files.length, pad = (cols - (n % cols)) % cols;
    let flt = files.map((_, i) => `[${i}:v]scale=960:540[v${i}]`).join(';') + ';';
    let chain = files.map((_, i) => `[v${i}]`).join('');
    for (let i = 0; i < pad; i++) { flt += `color=c=black:s=960x540:d=1[b${i}];`; chain += `[b${i}]`; }
    const total = n + pad;
    flt += `${chain}xstack=inputs=${total}:layout=${Array.from({ length: total }, (_, i) => `${(i % cols) * 960}_${Math.floor(i / cols) * 540}`).join('|')}[out]`;
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...files.flatMap((f) => ['-i', f]), '-filter_complex', flt, '-map', '[out]', '-frames:v', '1', '-q:v', '3', sheet]);
  }
  console.log('sheet', sheet, 'frames', frames.join(','));
} catch (e) { console.log('sheet failed (frames still rendered):', e.message.split('\n')[0]); }
