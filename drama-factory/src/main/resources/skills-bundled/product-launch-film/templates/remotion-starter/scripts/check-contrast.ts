// WCAG 2.x contrast for every text colour on every surface: node --no-warnings scripts/check-contrast.ts
// Body/label text needs 4.5:1. Only display text >= 24 px (or >= 18.66 px bold) may use 3:1 (list it in LARGE_ONLY).
import {SURFACES, TEXT} from '../src/palette.ts';

const LARGE_ONLY = new Set<string>([]); // e.g. 'ink4' if a colour is used only for huge display type

const lum = (hex: string) => {
	const v = hex.replace('#', '');
	const rgb = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
	return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
};
const ratio = (a: string, b: string) => {
	const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
};

let fails = 0;
for (const [tn, tc] of Object.entries(TEXT)) {
	const need = LARGE_ONLY.has(tn) ? 3 : 4.5;
	const rows = Object.entries(SURFACES).map(([sn, sc]) => [sn, ratio(tc, sc)] as const);
	const worst = rows.reduce((a, b) => (b[1] < a[1] ? b : a));
	const ok = worst[1] >= need;
	if (!ok) fails++;
	console.log(`${ok ? '✓' : '✗'} ${tn.padEnd(8)} ${tc}  worst ${worst[1].toFixed(2)}:1 on ${worst[0]} (needs ${need}:1)`);
}
console.log(fails ? `\n${fails} colour(s) fail AA` : '\ncontrast ok');
process.exit(fails ? 1 : 0);
