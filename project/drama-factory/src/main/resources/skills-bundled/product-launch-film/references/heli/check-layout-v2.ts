// v2 layout audit (pure geometry): node --no-warnings scripts/check-layout-v2.ts
// safe area · min gap between blocks · monospace fit (JetBrains Mono 0.6 em) · title fit (Schibsted
// Grotesk 600, conservative 0.56 em) · no pane scrolls (content height <= view height) · rail fits.
import {L, SAFE, MIN_GAP, WIN_HEADER, innerW, cols, type Block} from '../src/v2/layout.ts';
import * as K from '../src/v2/content.ts';
import {wrappedLines} from '../src/v2/reason.ts';
import {chipW} from '../src/v2/rail-metrics.ts';

let fails = 0;
const fail = (m: string) => (fails++, console.log('  ✗ ' + m));
const gapBetween = (a: Block, b: Block) => Math.max(Math.max(b.x - (a.x + a.w), a.x - (b.x + b.w)), Math.max(b.y - (a.y + a.h), a.y - (b.y + b.h)));
const ADV = 0.6;
const monoFit = (name: string, b: Block, lines: string[], font = b.mono!, inset = 0) => {
	const w = innerW(b) - inset;
	let worst = 0;
	for (const l of lines) {
		const px = l.length * font * ADV;
		worst = Math.max(worst, px);
		if (px > w) fail(`${name}: "${l.slice(0, 40)}…" ${px.toFixed(0)}px > ${w}px`);
	}
	console.log(`  ${name.padEnd(24)} widest ${worst.toFixed(0)} / ${w} px`);
};
const fitsV = (name: string, b: Block, rowsH: number, chrome = WIN_HEADER) => {
	const view = b.h - chrome - 2 * (b.pad ?? 0);
	console.log(`  ${name.padEnd(24)} height ${rowsH.toFixed(0)} / ${view} px`);
	if (rowsH > view) fail(`${name} content ${rowsH}px > view ${view}px (would scroll)`);
};
const titleH = (text: string, size: number, w: number) => {
	const per = size * 0.56;
	let lines = 1, cur = 0;
	for (const word of text.split(' ')) {
		const ww = (word.length + 1) * per;
		if (cur + ww > w) (lines++, (cur = ww));
		else cur += ww;
	}
	return lines * size * 1.06;
};
const TITLES: Record<string, [string, number][]> = {
	problem: [['New tool. Blank slate.', 60]],
	record: [['One task. One record.', 76], ['Written as the agent works. Read by whichever agent comes next.', 30]],
	switch: [['The next agent starts with the record.', 60], ['Switch tools. Keep the thread.', 60]],
	skills: [['Agents don’t guess.', 60]],
	done: [['Done means verified.', 60]],
	rules: [['One rulebook. You hold the keys.', 60]],
};
for (const [scene, blocks] of Object.entries(L)) {
	const list = Object.values(blocks) as Block[];
	const before = fails;
	for (const b of list) if (b.x < SAFE.x || b.y < SAFE.y || b.x + b.w > SAFE.x + SAFE.w || b.y + b.h > SAFE.y + SAFE.h) fail(`${scene}.${b.id} outside safe area`);
	let minGap = Infinity;
	for (let i = 0; i < list.length; i++)
		for (let j = i + 1; j < list.length; j++) {
			const g = gapBetween(list[i], list[j]);
			minGap = Math.min(minGap, g);
			if (g < MIN_GAP) fail(`${scene}: ${list[i].id} ↔ ${list[j].id} gap ${g}px < ${MIN_GAP}`);
		}
	const tb = (blocks as Record<string, Block>).title;
	const ts = TITLES[scene];
	if (tb && ts) {
		// record: main + sub stacked; switch: two alternative titles
		const h = scene === 'record' ? titleH(ts[0][0], ts[0][1], tb.w) + 18 + titleH(ts[1][0], ts[1][1], tb.w) * 1.32 : Math.max(...ts.map(([t, s]) => titleH(t, s, tb.w)));
		if (h > tb.h + 1) fail(`${scene}.title ~${h.toFixed(0)}px > block ${tb.h}px`);
	}
	console.log(`${fails === before ? '✓' : '✗'} ${scene.padEnd(8)} blocks ${list.length}, min gap ${minGap}px`);
}

const P = L.problem.left;
monoFit('problem.left', P, ['Edit  ' + K.PATCH_FILE, 'Bash  npm test -- auth', '  ✕ login › slow network (10002 ms)']);
fitsV('problem.left', P, 7.8 * Math.round(P.mono! * 1.6));
const R = L.record;
monoFit('record.term', R.term, ['$ ' + K.CREATE_CMD[0], '> ' + K.CREATE_CMD[1], ...K.CREATE_OUT]);
fitsV('record.term', R.term, (2 + K.CREATE_OUT.length) * 32);
monoFit('record.file', R.file, K.RECORD.map((l) => l.t), R.file.mono, 4);
fitsV('record.file', R.file, K.RECORD.length * 34);
const S = L.switch.pane;
monoFit('switch.pane context', S, [...K.CONTEXT, 'SessionStart · Heli-Harness    additionalContext'], S.mono, 18);
fitsV('switch.pane', S, 1.3 * 38 + 0.35 * 38 + K.CONTEXT.length * 38);
const railW = (hosts: string[], b: Block) => {
	const w = hosts.reduce((a, h) => a + chipW(h), 0);
	const gap = (b.w - w) / (hosts.length - 1);
	console.log(`  ${'rail'.padEnd(24)} chips ${w} px, gap ${gap.toFixed(0)} px`);
	if (gap < 40) fail(`rail gap ${gap.toFixed(0)}px < 40`);
};
railW(K.SWITCH_HOSTS, L.switch.rail);
railW(K.RULE_HOSTS, L.rules.rail);
const A = L.skills.agent;
const strike = wrappedLines(K.STRIKE_REASON, cols(A) - 2);
monoFit('skills.agent', A, ['apply_patch ' + K.PATCH_FILE, ' '.repeat(12) + K.PATCH[0], 'Bound task state from tasks/fix-login-timeout/current-task.md']);
monoFit('skills.agent reason', A, [...strike, 'PreToolUse · Heli-Harness    permissionDecision: deny'], A.mono, 18);
fitsV('skills.agent', A, (1.3 + 1 + 0.6 + 1 + 2 + 0.4 + 1.3 + strike.length) * 35);
const D = L.done.term;
const err = wrappedLines(K.COMPLETE_BLOCKED[0], cols(D));
monoFit('done.term', D, ['$ ' + K.COMPLETE_CMD, ...err, K.COMPLETE_BLOCKED[1], '$ ' + K.RECORD_CMD[0], '> ' + K.RECORD_CMD[1], K.RECORD_OUT_FOLDED, ...K.COMPLETE_OK]);
fitsV('done.term', D, (1 + err.length + 1 + 0.6 + 2 + 1 + 1 + 2) * 40);
for (const [n, b, r] of [['rules.rowA', L.rules.rowA, K.PUSH_REASON], ['rules.rowB', L.rules.rowB, K.RM_REASON]] as const) {
	const lines = wrappedLines(r, cols(b) - 2);
	monoFit(n + ' reason', b, lines, b.mono, 18);
	const head = 92 + K.PUSH_CMD.length * 30 * ADV + 40 + 'permissionDecision: deny'.length * 22 * ADV;
	if (head > innerW(b)) fail(`${n} header ${head}px > ${innerW(b)}`);
	fitsV(n, b, 70 + lines.length * 36, 0);
}
monoFit('close.cmd', L.close.cmd, ['$ npm install -g heli-harness']);
console.log(fails ? `\n${fails} layout problem(s)` : '\nlayout ok');
process.exit(fails ? 1 : 0);
