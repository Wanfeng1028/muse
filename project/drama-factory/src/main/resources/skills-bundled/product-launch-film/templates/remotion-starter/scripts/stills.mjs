// Review stills: node scripts/stills.mjs [--named] [--audit] [--frames=100,200]
//   --named   out/stills/<name>.png at full size (key frames you will show the user)
//   --audit   out/audit/f<frame>.jpg at half size: every 15 frames + mid-animation EXTRA frames
//   --frames  out/stills/check-<frame>.png for spot checks
// Tile the audit into contact sheets and LOOK at every one:
//   ffmpeg -pattern_type glob -i 'out/audit/*.jpg' -vf "scale=384:-1,tile=6x8:padding=4" out/sheet-%02d.jpg
import path from 'node:path';
import {mkdirSync} from 'node:fs';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const COMPOSITION = 'FilmPicture';
/** [name, absolute frame]: one or two per scene, at the moment the scene "lands". */
const NAMED = [
	['01-s1-typed', 120],
	['01-s1-landed', 300],
];
/** Mid-animation frames worth checking (slides, crossfades, highlights growing). */
const EXTRA = [30, 60, 90, 200];

const args = process.argv.slice(2);
const only = args.find((a) => a.startsWith('--frames='));
const doNamed = args.includes('--named') || (!args.includes('--audit') && !only);
const doAudit = args.includes('--audit');
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const comp = await selectComposition({serveUrl, id: COMPOSITION});
const jobs = [];
if (doNamed) for (const [n, f] of NAMED) jobs.push({out: `out/stills/${n}.png`, frame: f, scale: 1, fmt: 'png'});
if (doAudit) {
	const set = new Set([...Array.from({length: Math.ceil(comp.durationInFrames / 15)}, (_, i) => i * 15), ...EXTRA]);
	for (const f of [...set].filter((f) => f < comp.durationInFrames).sort((a, b) => a - b))
		jobs.push({out: `out/audit/f${String(f).padStart(4, '0')}.jpg`, frame: f, scale: 0.5, fmt: 'jpeg'});
}
if (only) for (const f of only.split('=')[1].split(',').map(Number)) jobs.push({out: `out/stills/check-${f}.png`, frame: f, scale: 1, fmt: 'png'});
mkdirSync('out/stills', {recursive: true});
mkdirSync('out/audit', {recursive: true});
const t0 = Date.now();
for (const j of jobs)
	await renderStill({composition: comp, serveUrl, output: j.out, frame: j.frame, scale: j.scale, imageFormat: j.fmt, ...(j.fmt === 'jpeg' ? {jpegQuality: 82} : {})});
console.log(`${jobs.length} stills in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
