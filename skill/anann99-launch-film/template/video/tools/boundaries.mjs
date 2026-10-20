#!/usr/bin/env node
// Extract frames just before/after every scene boundary of a RENDERED film and tile them (4 per row):
//   node tools/boundaries.mjs out/film.mp4 [before=0.1] [after=0.2]
// Use it to catch double-exposed text, flash/blank frames and brightness collapses at hand-offs.
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const [mp4, beforeArg, afterArg] = process.argv.slice(2);
if (!mp4) { console.error('usage: node tools/boundaries.mjs out/film.mp4 [before] [after]'); process.exit(1); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'scenes.json'), 'utf8'));
const before = Number(beforeArg ?? 0.1), after = Number(afterArg ?? 0.2);
const cuts = cfg.scenes.slice(1).map((s) => s.start);
const out = path.join(root, 'out', 'qa', 'boundaries');
fs.mkdirSync(out, { recursive: true });
const files = [];
for (const t of cuts) {
  for (const [tag, at] of [['a', t - before], ['b', t + after]]) {
    const f = path.join(out, `t${t.toFixed(2)}_${tag}.png`);
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(Math.max(0, at)), '-i', mp4, '-frames:v', '1', '-vf', 'scale=480:270', f]);
    files.push(f);
  }
}
const cols = 4, n = files.length, pad = (cols - (n % cols)) % cols;
let flt = files.map((_, i) => `[${i}:v]null[v${i}]`).join(';') + ';';
let ch = files.map((_, i) => `[v${i}]`).join('');
for (let i = 0; i < pad; i++) { flt += `color=c=black:s=480x270:d=1[b${i}];`; ch += `[b${i}]`; }
const total = n + pad;
flt += `${ch}xstack=inputs=${total}:layout=${Array.from({ length: total }, (_, i) => `${(i % cols) * 480}_${Math.floor(i / cols) * 270}`).join('|')}[o]`;
const sheet = path.join(out, 'sheet.jpg');
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...files.flatMap((f) => ['-i', f]), '-filter_complex', flt, '-map', '[o]', '-frames:v', '1', sheet]);
console.log(`boundaries ${cuts.join(', ')} → ${sheet} (each pair: ${before}s before | ${after}s after)`);
