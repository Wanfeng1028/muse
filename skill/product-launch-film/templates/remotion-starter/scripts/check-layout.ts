// Layout audit by pure geometry (no rendering): node --no-warnings scripts/check-layout.ts
// For every scene in src/layout.ts: blocks inside the safe area, no two blocks closer than MIN_GAP,
// every monospace line fits its block, titles fit their block, pane content does not overflow (no scrolling).
// Extend the per-scene section at the bottom whenever you add a scene. For moving layouts, also check the
// in-between positions (sample the animation every few frames) as well as the end states.
import {L, SAFE, MIN_GAP, MONO_ADV, WIN_HEADER, innerW, innerH, type Block} from '../src/layout.ts';
import * as K from '../src/copy.ts';

let fails = 0;
const fail = (m: string) => {
	fails++;
	console.log('  ✗ ' + m);
};
const gap = (a: Block, b: Block) => Math.max(b.x - (a.x + a.w), a.x - (b.x + b.w), b.y - (a.y + a.h), a.y - (b.y + b.h));

/** Width check for monospace lines (advance = MONO_ADV em). */
export const monoFit = (name: string, b: Block, lines: string[], font = b.mono ?? 20) => {
	const w = innerW(b);
	let worst = 0;
	for (const l of lines) {
		const px = l.length * font * MONO_ADV;
		worst = Math.max(worst, px);
		if (px > w) fail(`${name}: "${l.slice(0, 40)}…" ${px.toFixed(0)}px > ${w}px`);
	}
	console.log(`  ${name.padEnd(22)} widest ${worst.toFixed(0)} / ${w} px`);
};
/** Height check: rows × line height must fit the pane's view (header + padding removed). */
export const fitsV = (name: string, b: Block, rows: number, lineH: number, header = WIN_HEADER) => {
	const view = innerH(b, header);
	const h = rows * lineH;
	console.log(`  ${name.padEnd(22)} height ${h.toFixed(0)} / ${view} px`);
	if (h > view) fail(`${name}: content ${h}px > view ${view}px (would scroll)`);
};
/** Conservative title height: ~0.56 em per character for a grotesk at weight 600, line-height 1.06. */
export const titleFit = (name: string, b: Block, text: string, size: number) => {
	const per = size * 0.56;
	let lines = 1;
	let cur = 0;
	for (const word of text.split(' ')) {
		const ww = (word.length + 1) * per;
		if (cur + ww > b.w) {
			lines++;
			cur = ww;
		} else cur += ww;
	}
	const h = lines * size * 1.06;
	if (h > b.h + 1) fail(`${name}: ~${h.toFixed(0)}px (${lines} lines) > block ${b.h}px`);
};

for (const [scene, blocks] of Object.entries(L)) {
	const list = Object.values(blocks) as Block[];
	const before = fails;
	for (const b of list) if (b.x < SAFE.x || b.y < SAFE.y || b.x + b.w > SAFE.x + SAFE.w || b.y + b.h > SAFE.y + SAFE.h) fail(`${scene}.${b.id} outside safe area`);
	let minGap = Infinity;
	for (let i = 0; i < list.length; i++)
		for (let j = i + 1; j < list.length; j++) {
			const g = gap(list[i], list[j]);
			minGap = Math.min(minGap, g);
			if (g < MIN_GAP) fail(`${scene}: ${list[i].id} ↔ ${list[j].id} gap ${g}px < ${MIN_GAP}`);
		}
	console.log(`${fails === before ? '✓' : '✗'} ${scene.padEnd(8)} blocks ${list.length}, min gap ${minGap === Infinity ? '-' : minGap + 'px'}`);
}

// --- per-scene content checks -------------------------------------------------------------
titleFit('s1.title', L.s1.title, K.S1.title, 60);
monoFit('s1.term', L.s1.term, ['$ ' + K.S1.cmd, ...K.S1.out]);
fitsV('s1.term', L.s1.term, 1 + K.S1.out.length, L.s1.term.mono! * 1.6);

console.log(fails ? `\n${fails} layout problem(s)` : '\nlayout ok');
process.exit(fails ? 1 : 0);
