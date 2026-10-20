/* ==========================================================================
   xiaolu-motion · engine/core.js
   Deterministic utilities: math, easing, springs, hashing, gradient noise,
   colour helpers, glyph measurement, sprites.

   Ported from 《在我开口之前》 src/core.js (Claude 自由创作渲染器). Changes:
   ES module, no global canvas constants (W/H come from the runtime), no DOM
   access at import time (so Node can import components to dump their specs),
   palette removed (colours now come from style tokens).
   Rule: no clocks, no Math.random — every value is a pure function of inputs.
   ========================================================================== */
export const TAU = Math.PI * 2;
export const DEG = Math.PI / 180;

/* ---------- math ---------- */
export function clamp(x, a = 0, b = 1) { return x < a ? a : x > b ? b : x; }
export function lerp(a, b, t) { return a + (b - a) * t; }
export function seg(t, a, b) { return b === a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)); }
export function smooth(x) { x = clamp(x); return x * x * (3 - 2 * x); }
export function smoother(x) { x = clamp(x); return x * x * x * (x * (x * 6 - 15) + 10); }
export function fract(x) { return x - Math.floor(x); }
export function mod(a, n) { return ((a % n) + n) % n; }
export function dist(ax, ay, bx, by) { return Math.hypot(bx - ax, by - ay); }
/* 0 before a, rises a->b, holds, falls c->d */
export function bump(t, a, b, c, d) {
  if (t <= a || t >= d) return 0; if (t < b) return smooth((t - a) / (b - a)); if (t <= c) return 1; return 1 - smooth((t - c) / (d - c));
}

/* ---------- easing (names are part of the storyboard contract: timeline/SCHEMA.md) ---------- */
const _eN = 1 - Math.pow(2, -10);
export const E = {
  lin: x => clamp(x),
  linear: x => clamp(x),
  step: x => (x >= 1 ? 1 : 0),
  expoOut: x => { x = clamp(x); return (1 - Math.pow(2, -10 * x)) / _eN; },
  expoIn: x => { x = clamp(x); return x <= 0 ? 0 : (Math.pow(2, 10 * (x - 1)) - Math.pow(2, -10)) / _eN; },
  expoInOut: x => { x = clamp(x); if (x <= 0) return 0; if (x >= 1) return 1; return x < 0.5 ? Math.pow(2, 20 * x - 10) / 2 : (2 - Math.pow(2, -20 * x + 10)) / 2; },
  backOut: (x, s = 1.4) => { x = clamp(x); const y = x - 1; return 1 + (s + 1) * y * y * y + s * y * y; },
  cubicIn: x => { x = clamp(x); return x * x * x; },
  cubicOut: x => { x = clamp(x); const y = 1 - x; return 1 - y * y * y; },
  cubicInOut: x => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
  quartOut: x => { x = clamp(x); return 1 - Math.pow(1 - x, 4); },
  quintOut: x => { x = clamp(x); return 1 - Math.pow(1 - x, 5); },
  quintInOut: x => { x = clamp(x); return x < 0.5 ? 16 * x * x * x * x * x : 1 - Math.pow(-2 * x + 2, 5) / 2; },
  sineInOut: x => { x = clamp(x); return -(Math.cos(Math.PI * x) - 1) / 2; },
  sineIn: x => { x = clamp(x); return 1 - Math.cos(x * Math.PI / 2); },
  sineOut: x => { x = clamp(x); return Math.sin(x * Math.PI / 2); },
  quadIn: x => { x = clamp(x); return x * x; },
  quadOut: x => { x = clamp(x); return 1 - (1 - x) * (1 - x); },
  circOut: x => { x = clamp(x); return Math.sqrt(1 - Math.pow(x - 1, 2)); },
};
export function ease(name) { const f = E[name]; if (!f) throw new Error('unknown ease ' + name); return f; }

/* damped spring step response; s = seconds since release; 0 -> 1 (overshoots) */
export function spring(s, freq = 3.2, zeta = 0.42) {
  if (s <= 0) return 0;
  const w = TAU * freq, wd = w * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * w * s) * (Math.cos(wd * s) + (zeta * w / wd) * Math.sin(wd * s));
}
/* impulse that returns to 0 (press / wobble) */
export function springKick(s, freq = 3, zeta = 0.35) {
  if (s <= 0) return 0;
  const w = TAU * freq, wd = w * Math.sqrt(1 - zeta * zeta);
  return Math.exp(-zeta * w * s) * Math.sin(wd * s);
}

/* ---------- deterministic randomness ---------- */
export function mulberry32(a) {
  a = a >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function hashU(n) {
  n = (n | 0) >>> 0;
  n = Math.imul(n ^ (n >>> 16), 0x7feb352d);
  n = Math.imul(n ^ (n >>> 15), 0x846ca68b);
  n = (n ^ (n >>> 16)) >>> 0;
  return n;
}
export function hash1(n) { return hashU(n) / 4294967296; }
export function hash2(a, b) { return hashU(hashU(a) ^ Math.imul(b | 0, 0x9E3779B1)) / 4294967296; }
export function hash3(a, b, c) { return hashU(hashU(hashU(a) ^ Math.imul(b | 0, 0x9E3779B1)) ^ Math.imul(c | 0, 0x85EBCA77)) / 4294967296; }
export function hashStr(s) { let h = 2166136261 >>> 0; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h; }
export function gaussR(rng) { let u = 0, v = 0; while (u === 0) u = rng(); v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v); }

/* ---------- gradient noise (fixed permutation, seed 90210 as in the original) ---------- */
export const Noise = (() => {
  const rng = mulberry32(90210);
  const p = new Uint8Array(512);
  const perm = [...Array(256).keys()];
  for (let i = 255; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
  for (let i = 0; i < 512; i++) p[i] = perm[i & 255];
  const g2 = [[1, 1], [-1, 1], [1, -1], [-1, -1], [1, 0], [-1, 0], [0, 1], [0, -1]];
  const fade = t => t * t * t * (t * (t * 6 - 15) + 10);
  function n2(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const X = xi & 255, Y = yi & 255;
    const g = (ix, iy, dx, dy) => { const gg = g2[p[ix + p[iy]] & 7]; return gg[0] * dx + gg[1] * dy; };
    const u = fade(xf), v = fade(yf);
    const a = g(X, Y, xf, yf), b = g(X + 1, Y, xf - 1, yf), c = g(X, Y + 1, xf, yf - 1), d = g(X + 1, Y + 1, xf - 1, yf - 1);
    return lerp(lerp(a, b, u), lerp(c, d, u), v) * 0.7071 * 1.4; // ~[-1,1]
  }
  function n1(x, seed = 0) { return n2(x, seed * 17.13 + 3.7); }
  function fbm(x, y, oct = 4) { let s = 0, a = 0.5, f = 1, n = 0; for (let i = 0; i < oct; i++) { s += a * n2(x * f, y * f); n += a; a *= 0.5; f *= 2.03; } return s / n; }
  return { n2, n1, fbm };
})();
/* 1-2 px breathing drift for otherwise static elements */
export function drift(t, seed, amp = 1.5, speed = 0.35) { return [Noise.n1(t * speed, seed) * amp, Noise.n1(t * speed, seed + 50) * amp]; }

/* ---------- colour ---------- */
const _rgbCache = new Map();
export function hexRgb(h) {
  let c = _rgbCache.get(h);
  if (!c) {
    if (typeof h !== 'string') throw new Error('bad colour ' + h);
    if (h[0] === '#') {
      let s = h.slice(1);
      if (s.length === 3) s = s.split('').map(ch => ch + ch).join('');
      c = [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
    } else { const m = h.match(/-?[\d.]+/g); if (!m || m.length < 3) throw new Error('bad colour ' + h); c = [+m[0], +m[1], +m[2]]; }
    if (c.some(v => !Number.isFinite(v))) throw new Error('bad colour ' + h);
    _rgbCache.set(h, c);
  }
  return c;
}
export function rgba(h, a = 1) { const c = hexRgb(h); return `rgba(${c[0]},${c[1]},${c[2]},${clamp(a)})`; }
export function mixRgb(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
export function mixHex(h1, h2, t, a = 1) { const c = mixRgb(hexRgb(h1), hexRgb(h2), clamp(t)); return `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${clamp(a)})`; }
export function rgbStr(c, a = 1) { return `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${clamp(a)})`; }
export function gl3(h) { const c = hexRgb(h); return [c[0] / 255, c[1] / 255, c[2] / 255]; }

/* ---------- canvas helpers (DOM only when called) ---------- */
export function mkCanvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
export function rrect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2))); }
export function resetCtx(ctx, w, h) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ctx.filter = 'none'; ctx.clearRect(0, 0, w, h); ctx.lineCap = 'butt'; ctx.lineJoin = 'miter'; ctx.setLineDash([]);
  ctx.shadowBlur = 0; ctx.shadowColor = 'transparent'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.letterSpacing = '0px';
}
export function setFilter(ctx, blur) { ctx.filter = blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : 'none'; }

/* soft round sprite (radial falloff) used for glows, dust and bokeh */
const SPRITES = {};
export function softDot(key, colorHex, hard = 0.0) {
  const k = key + colorHex + hard;
  if (SPRITES[k]) return SPRITES[k];
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  const rgb = hexRgb(colorHex);
  const st = (o, a) => g.addColorStop(o, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`);
  if (hard > 0) { st(0, 1); st(hard, 1); st(Math.min(1, hard + 0.12), 0.35); st(1, 0); }
  else { st(0, 1); st(0.18, 0.62); st(0.42, 0.2); st(0.7, 0.05); st(1, 0); }
  x.fillStyle = g; x.fillRect(0, 0, s, s);
  SPRITES[k] = c; return c;
}
export function drawSprite(ctx, spr, x, y, r, a = 1) {
  if (!ctx || a <= 0.002 || r <= 0) return;
  const ga = ctx.globalAlpha;
  ctx.globalAlpha = clamp(a) * ga;
  ctx.drawImage(spr, x - r, y - r, r * 2, r * 2);
  ctx.globalAlpha = ga;
}
/* ring with analytic motion blur: stroke widens by the distance travelled during one sub-frame */
export function blurRing(ctx, cx, cy, r, v, lw, col, a, subdt = 0) {
  if (!ctx || a <= 0.002 || r <= 0) return;
  const smear = Math.abs(v) * subdt;
  const w = Math.max(lw, smear);
  ctx.lineWidth = w; ctx.strokeStyle = rgba(col, a * lw / w);
  ctx.beginPath(); ctx.arc(cx, cy, Math.max(0.5, r), 0, TAU); ctx.stroke();
}

/* ---------- monotone cubic interpolation (camera paths through exact key times) ---------- */
export function makePchip(xs, ys) {
  const n = xs.length;
  if (n === 1) return () => ys[0];
  const d = new Array(n), m = new Array(n - 1), h = new Array(n - 1);
  for (let i = 0; i < n - 1; i++) { h[i] = xs[i + 1] - xs[i]; m[i] = (ys[i + 1] - ys[i]) / h[i]; }
  d[0] = m[0]; d[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) {
    if (m[i - 1] * m[i] <= 0) d[i] = 0;
    else { const w1 = 2 * h[i] + h[i - 1], w2 = h[i] + 2 * h[i - 1]; d[i] = (w1 + w2) / (w1 / m[i - 1] + w2 / m[i]); }
  }
  return function (x) {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0; while (i < n - 2 && x > xs[i + 1]) i++;
    const t = (x - xs[i]) / h[i], t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * d[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * d[i + 1];
  };
}

/* ---------- style-token helpers ---------- */
/* colour param: '#hex', 'rgba(...)', '@name' (tokens.colors.name) or '@colors.name' */
export function tokColor(tokens, v, fallback = '#ffffff') {
  if (v === undefined || v === null || v === '') return fallback;
  if (typeof v !== 'string') return fallback;
  if (v[0] !== '@') return v;
  const key = v.slice(1).replace(/^colors\./, '');
  const c = tokens && tokens.colors && tokens.colors[key];
  if (!c) throw new Error('unknown colour token ' + v);
  return c;
}
/* font role -> CSS font string. role: tokens.fonts[role].family; weight number */
export function tokFont(tokens, role, size, weight) {
  const f = tokens && tokens.fonts && tokens.fonts[role];
  if (!f) throw new Error('unknown font role ' + role);
  const fam = `"${f.family}"` + (f.fallback ? ', ' + f.fallback : '');
  return `${weight || f.default_weight || 400} ${Math.round(size * 100) / 100}px ${fam}`;
}
