// REPLACE with the brand's fonts. Google Fonts: import from '@remotion/google-fonts/<Family>'.
// Local fonts: put files in public/fonts and use loadFont from '@remotion/fonts' (or an @font-face style tag).
import { loadFont as loadSans } from '@remotion/google-fonts/Geist';
import { loadFont as loadMono } from '@remotion/google-fonts/GeistMono';
import { loadFont as loadPixel } from '@remotion/google-fonts/GeistPixel';
import { loadFont as loadSerif } from '@remotion/google-fonts/InstrumentSerif';

const sans = loadSans('normal', { weights: ['300', '400', '500', '600', '700'], subsets: ['latin'] });
const mono = loadMono('normal', { weights: ['400', '500', '600'], subsets: ['latin'] });
const pixel = loadPixel('normal', { weights: ['400'], subsets: ['latin'] });
const serif = loadSerif('normal', { weights: ['400'], subsets: ['latin'] });

export const FONT = {
  sans: `${sans.fontFamily}, system-ui, sans-serif`,
  mono: `${mono.fontFamily}, ui-monospace, monospace`,
  pixel: `${pixel.fontFamily}, ${mono.fontFamily}, monospace`, // dot-matrix numerals / motifs
  serif: `${serif.fontFamily}, Georgia, serif`,
};
