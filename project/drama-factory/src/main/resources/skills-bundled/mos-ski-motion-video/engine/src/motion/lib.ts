// Motion primitives: every value is a pure function of time t (seconds), so any frame can be
// rendered on its own. No timers, no state carried between frames, no Math.random.

export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;

// Closed-form damped spring 0 -> 1. k = stiffness, d = damping.
export function spring(t: number, k = 170, d = 26): number {
  if (t <= 0) return 0;
  const w0 = Math.sqrt(k);
  const z = d / (2 * w0);
  if (z < 1) {
    const wd = w0 * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + ((z * w0) / wd) * Math.sin(wd * t));
  }
  return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
}

// Presets (stiffness, damping)
export const SPRING = {
  snappy: [320, 30] as const, // buttons, toggles, leading edges
  ui: [170, 26] as const, // cards, containers, camera (default)
  heavy: [110, 24] as const, // big type, logo lockups
  playful: [220, 14] as const, // stickers, mascots (visible overshoot)
};

// A value that changes target many times: sum one spring per change, so motion stays
// continuous and still seekable. keys = [[time, value], ...] sorted by time.
export function track(t: number, keys: [number, number][], k = 170, d = 26): number {
  let v = keys[0][1];
  for (let i = 1; i < keys.length; i++) v += (keys[i][1] - keys[i - 1][1]) * spring(t - keys[i][0], k, d);
  return v;
}

// Stretchy indicator: leading edge stiffer than trailing edge.
export function indicator(t: number, stops: [number, number][], width = 120) {
  const lead = track(t, stops, 320, 30);
  const trail = track(t, stops, 140, 22);
  return {left: Math.min(lead, trail), right: Math.max(lead, trail) + width};
}

// Content inside a morphing container: in just after the morph starts, out just before the next.
export function swapAlpha(t: number, tIn: number, tOut: number) {
  return Math.min(clamp((t - tIn - 0.08) / 0.12), clamp((tOut - 0.1 - t) / 0.1));
}

// Staggered entrance: item i of a group starts `gap` seconds after the previous.
export const stagger = (t: number, i: number, gap = 0.04, k = 260, d = 22) => spring(t - i * gap, k, d);

// Seeded PRNG (mulberry32). Use for any "random" layout so renders are identical every run.
export function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

export const loopT = (t: number, dur: number) => ((t % dur) + dur) % dur;

// Beat grid (from `motion.py beats` or a synthesized BPM). Snap any time to the nearest beat.
export type Beats = {bpm: number; beats: number[]; downbeats: number[]; hits: number[]};
export const gridFromBpm = (bpm: number, dur: number, offset = 0): Beats => {
  const beats: number[] = [];
  for (let t = offset; t < dur; t += 60 / bpm) beats.push(+t.toFixed(3));
  return {bpm, beats, downbeats: beats.filter((_, i) => i % 4 === 0), hits: []};
};
export const snap = (t: number, b: Beats) => b.beats.reduce((p, c) => (Math.abs(c - t) < Math.abs(p - t) ? c : p), b.beats[0]);

// Layout per format, so one timeline renders 9:16, 1:1 and 16:9 without cropping.
export type Format = 'vertical' | 'square' | 'wide';
export const FORMATS: Record<Format, {w: number; h: number}> = {
  vertical: {w: 1080, h: 1920},
  square: {w: 1080, h: 1080},
  wide: {w: 1920, h: 1080},
};
// Unit = 1% of the short side; type scales by it so text reads the same in every format.
export const unit = (f: Format) => Math.min(FORMATS[f].w, FORMATS[f].h) / 100;

// ---------------------------------------------------------------- jitter language
// Stepped time: hold each pose for `onN` frames at `fps` (on twos at 24fps = 12 drawings/s).
// Feed stepped(t) instead of t into any motion to get the stop-motion / "jitter" feel.
export const stepped = (t: number, fps = 24, onN = 2) => Math.floor((t * fps) / onN) * (onN / fps);

// Boil: seeded per-step offset (px) so static elements "live" like hand-redrawn frames.
export function boil(t: number, seed: number, amp = 2, fps = 12): {x: number; y: number; r: number} {
  const step = Math.floor(t * fps);
  const r = rng(seed * 9973 + step);
  return {x: (r() - 0.5) * 2 * amp, y: (r() - 0.5) * 2 * amp, r: (r() - 0.5) * amp * 0.5};
}

// Impact shake: decaying jitter after a hit at time `at` (camera or element).
export function shake(t: number, at: number, amp = 18, dur = 0.25, seed = 1) {
  const s = t - at;
  if (s < 0 || s > dur) return {x: 0, y: 0};
  const k = 1 - s / dur;
  const b = boil(s, seed, amp * k * k, 30);
  return {x: b.x, y: b.y};
}

// Snap-in with motion blur: element flies in from `from` px along an axis, blur ∝ speed.
export function snapIn(t: number, at: number, from = 220, k = 320, d = 30) {
  const p = spring(t - at, k, d);
  const v = spring(t - at + 1 / 60, k, d) - p; // per-frame velocity
  return {offset: (1 - p) * from, blur: Math.min(24, Math.abs(v) * from * 0.9), p};
}

// Line-mask text reveal: word i rises from below its own clip line. Wrap the word in an
// overflow:hidden span and translateY by (1 - p) * 110%.
export const riseWord = (t: number, i: number, start = 0, gap = 0.07) => spring(t - start - i * gap, 260, 26);

// Typed text: characters visible at time t (cps = chars/sec), plus a blinking caret.
export const typed = (text: string, t: number, start = 0, cps = 28) => text.slice(0, Math.max(0, Math.floor((t - start) * cps)));
export const caretOn = (t: number) => Math.floor(t * 2) % 2 === 0;

// Montage: pick which of N clips is visible for a burst of fast cuts (each `len` s).
export const montageIndex = (t: number, start: number, len = 0.18, n = 6) => Math.min(n - 1, Math.max(0, Math.floor((t - start) / len)));
