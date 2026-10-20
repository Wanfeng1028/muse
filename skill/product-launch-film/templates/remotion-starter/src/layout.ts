// Every positioned block, per scene (no imports: read by scripts/check-layout.ts under plain Node).
// check-layout asserts: inside SAFE, no two blocks of a scene closer than MIN_GAP, mono lines fit, titles fit.
export type Block = {id: string; x: number; y: number; w: number; h: number; pad?: number; mono?: number};

export const SAFE = {x: 96, y: 72, w: 1920 - 192, h: 1080 - 144};
export const MIN_GAP = 32;
export const WIN_HEADER = 52;
/** Advance width of the monospace font in em (JetBrains Mono = 0.6). */
export const MONO_ADV = 0.6;

export const L = {
	s1: {
		title: {id: 'title', x: 240, y: 250, w: 1440, h: 80},
		term: {id: 'term', x: 240, y: 380, w: 1440, h: 330, pad: 40, mono: 26},
	},
} satisfies Record<string, Record<string, Block>>;

export const innerW = (b: Block) => b.w - 2 * (b.pad ?? 0);
export const innerH = (b: Block, header = WIN_HEADER) => b.h - header - 2 * (b.pad ?? 0);
