import { Easing } from 'remotion';
import { FILM } from '../film';

// ---- Canvas & timing (from scenes.json via src/film.ts) -------------------
export const FPS = FILM.fps;
export const W = FILM.width;
export const H = FILM.height;
export const BPM = FILM.bpm;
export const BEAT = (FPS * 60) / BPM; // frames per beat (15 at 30 fps / 120 BPM)
export const BAR = BEAT * 4;

/** seconds -> frames (rounded) */
export const sec = (s: number) => Math.round(s * FPS);
/** beats -> frames */
export const beats = (n: number) => Math.round(n * BEAT);

// ---- Palette ----------------------------------------------------------------
// REPLACE with the brand palette from public/site/brand.json (CSS custom properties). Keep the role names:
// scenes and primitives only ever reference roles, never raw hex.
export const C = {
  ink: '#0A0B09', // deepest background
  page: '#0E0F0C', // base page
  bg2: '#141512', // raised background / glow centre
  surface: '#1A1B17', // rebuilt-UI card fill
  surface2: '#252620',
  border: '#3A3D33',
  borderStrong: '#525646',
  text: '#FDFEFB', // primary type
  muted: '#A1A39A',
  faint: '#6B6E63',
  brand: '#2E4325', // primary brand colour (CTA fill, glows)
  brandDeep: '#1B2A15',
  accent: '#DDE5B6', // highlight: focus rings, "good" state, winners
  accent2: '#96B874', // secondary accent: logo tint, dots
  // product-UI and status colours (match the product's real UI)
  appBg: '#090909',
  link: '#2563EB',
  ok: '#3FB97A',
  warn: '#F5A524',
  bad: '#EF4444',
} as const;

// ---- Motion -----------------------------------------------------------------
export const EASE = {
  out: Easing.bezier(0.16, 1, 0.3, 1), // the house ease-out
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  in: Easing.bezier(0.7, 0, 0.84, 0),
  soft: Easing.bezier(0.33, 1, 0.68, 1),
  snap: Easing.bezier(0.2, 0.9, 0.1, 1),
};

// ---- Type scale (px at 1080p) -------------------------------------------------
export const TYPE = { hero: 112, h1: 84, h2: 64, h3: 46, caption: 56, body: 32, small: 24, label: 18 };
