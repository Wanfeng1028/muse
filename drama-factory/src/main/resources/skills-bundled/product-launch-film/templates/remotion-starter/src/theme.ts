// Fonts + re-exported palette. Pick a real pairing (or the product's own fonts); these are placeholders.
import {loadFont as loadSans} from '@remotion/google-fonts/SchibstedGrotesk';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

export {c} from './palette';

const sans = loadSans('normal', {weights: ['400', '500', '600', '700'], subsets: ['latin']});
const mono = loadMono('normal', {weights: ['400', '500', '600'], subsets: ['latin']});

export const fonts = {
	sans: `${sans.fontFamily}, -apple-system, "Helvetica Neue", sans-serif`,
	mono: `${mono.fontFamily}, ui-monospace, SFMono-Regular, Menlo, monospace`,
};

/** Code text must render exactly as typed: no "->" arrows, no "!=" glyphs. */
export const NO_LIGATURES = {fontVariantLigatures: 'none', fontFeatureSettings: '"calt" 0, "liga" 0'} as const;

export const radius = {win: 14, card: 12};
export const VIDEO = {width: 1920, height: 1080, fps: 60};
