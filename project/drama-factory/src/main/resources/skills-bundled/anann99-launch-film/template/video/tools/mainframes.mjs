#!/usr/bin/env node
// Render frames of the MASTER timeline (all scenes + hand-offs) and a 3-column sheet.
//   node tools/mainframes.mjs 205,210,215 [outDir=out/qa/main] [scale=0.5]
import { bundle } from '@remotion/bundler';
import { renderStill, selectComposition } from '@remotion/renderer';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const [framesArg, outArg, scaleArg] = process.argv.slice(2);
if (!framesArg) { console.error('usage: node tools/mainframes.mjs 205,210,215 [outDir] [scale]'); process.exit(1); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const out = path.resolve(outArg || path.join(root, 'out', 'qa', 'main'));
fs.mkdirSync(out, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(root, 'src', 'index.ts'), publicDir: path.join(root, 'public'), outDir: path.join(root, 'out', '.bundle-main') });
const composition = await selectComposition({ serveUrl, id: 'Main' });
const frames = framesArg.split(',').map(Number);
const files = [];
for (const f of frames) {
  const o = path.join(out, `m${String(f).padStart(4, '0')}.png`);
  await renderStill({ composition, serveUrl, output: o, frame: f, scale: scaleArg ? Number(scaleArg) : 0.5 });
  files.push(o);
}
const cols = 3, n = files.length, pad = (cols - (n % cols)) % cols;
let flt = files.map((_, i) => `[${i}:v]scale=640:360[v${i}]`).join(';') + ';';
let ch = files.map((_, i) => `[v${i}]`).join('');
for (let i = 0; i < pad; i++) { flt += `color=c=black:s=640x360:d=1[b${i}];`; ch += `[b${i}]`; }
const total = n + pad;
flt += total > 1
  ? `${ch}xstack=inputs=${total}:layout=${Array.from({ length: total }, (_, i) => `${(i % cols) * 640}_${Math.floor(i / cols) * 360}`).join('|')}[o]`
  : `${ch}null[o]`;
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...files.flatMap((f) => ['-i', f]), '-filter_complex', flt, '-map', '[o]', '-frames:v', '1', path.join(out, 'sheet.jpg')]);
console.log('sheet', path.join(out, 'sheet.jpg'));
