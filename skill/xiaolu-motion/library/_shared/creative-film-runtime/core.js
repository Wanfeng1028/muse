'use strict';
/* ==========================================================================
   BEFORE I SPEAK — core utilities (deterministic: no clocks, no Math.random)
   ========================================================================== */
const W = 1080, H = 1920, CX = 540, CY = 960, FPS = 60;
const TAU = Math.PI * 2;
const DEG = Math.PI / 180;

/* ---------- scene registry (filled by scene files, consumed by main.js) ---------- */
const SCENES = [];          // {name, t0, t1, draw(t, R)}
const INITS = [];           // init functions (build deterministic data)
function registerScene(s) { SCENES.push(s); }
function registerInit(f) { INITS.push(f); }

/* ---------- palette ---------- */
const COL = {
  bg: '#05070C', bgGlow: '#0B1222', text: '#ECE9E2', text2: '#7C8698', hair: '#1B2230',
  cyan: '#6EE7F5', ice: '#CFF6FF', violet: '#8E7DFF', indigo: '#2E3FBF', iceX: '#E6FBFF',
  stroke: '#2A3346', card: '#0C121D', dim: '#1A2130',
  wbg: '#0E0805', wbgGlow: '#2A160B', wtext: '#F7ECDD', wtext2: '#9C8672',
  amber: '#F2A541', gold: '#FFD27A', persimmon: '#E8603C', maple: '#B8412C', seal: '#C43A2F',
};
const _rgbCache = new Map();
function hexRgb(h) {
  let c = _rgbCache.get(h);
  if (!c) {
    if (h[0] === '#') { const s = h.slice(1); c = [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)]; }
    else { const m = h.match(/-?[\d.]+/g); if (!m || m.length < 3) throw new Error('bad colour ' + h); c = [+m[0], +m[1], +m[2]]; }
    if (c.some(v => !Number.isFinite(v))) throw new Error('bad colour ' + h);
    _rgbCache.set(h, c);
  }
  return c;
}
function rgba(h, a = 1) { const c = hexRgb(h); return `rgba(${c[0]},${c[1]},${c[2]},${clamp(a)})`; }
function mixRgb(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
function mixHex(h1, h2, t, a = 1) { const c = mixRgb(hexRgb(h1), hexRgb(h2), clamp(t)); return `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${clamp(a)})`; }
function rgbStr(c, a = 1) { return `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${clamp(a)})`; }
function gl3(h) { const c = hexRgb(h); return [c[0] / 255, c[1] / 255, c[2] / 255]; }

/* ---------- math ---------- */
function clamp(x, a = 0, b = 1) { return x < a ? a : x > b ? b : x; }
function lerp(a, b, t) { return a + (b - a) * t; }
function seg(t, a, b) { return clamp((t - a) / (b - a)); }
function smooth(x) { x = clamp(x); return x * x * (3 - 2 * x); }
function smoother(x) { x = clamp(x); return x * x * x * (x * (x * 6 - 15) + 10); }
function fract(x) { return x - Math.floor(x); }
function mod(a, n) { return ((a % n) + n) % n; }
function dist(ax, ay, bx, by) { return Math.hypot(bx - ax, by - ay); }
function bump(t, a, b, c, d) { // 0 before a, rises a->b, holds, falls c->d
  if (t <= a || t >= d) return 0; if (t < b) return smooth((t - a) / (b - a)); if (t <= c) return 1; return 1 - smooth((t - c) / (d - c));
}

/* ---------- easing ---------- */
const _eN = 1 - Math.pow(2, -10);
const E = {
  lin: x => clamp(x),
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
/* damped spring step response; s = seconds since release; returns 0 -> 1 (overshoots) */
function spring(s, freq = 3.2, zeta = 0.42) {
  if (s <= 0) return 0;
  const w = TAU * freq, wd = w * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * w * s) * (Math.cos(wd * s) + (zeta * w / wd) * Math.sin(wd * s));
}
/* spring that starts moving with an impulse and returns to 0 (for press / wobble) */
function springKick(s, freq = 3, zeta = 0.35) {
  if (s <= 0) return 0;
  const w = TAU * freq, wd = w * Math.sqrt(1 - zeta * zeta);
  return Math.exp(-zeta * w * s) * Math.sin(wd * s);
}

/* ---------- deterministic randomness ---------- */
function mulberry32(a) {
  a = a >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashU(n) {
  n = (n | 0) >>> 0;
  n = Math.imul(n ^ (n >>> 16), 0x7feb352d);
  n = Math.imul(n ^ (n >>> 15), 0x846ca68b);
  n = (n ^ (n >>> 16)) >>> 0;
  return n;
}
function hash1(n) { return hashU(n) / 4294967296; }
function hash2(a, b) { return hashU(hashU(a) ^ Math.imul(b | 0, 0x9E3779B1)) / 4294967296; }
function hash3(a, b, c) { return hashU(hashU(hashU(a) ^ Math.imul(b | 0, 0x9E3779B1)) ^ Math.imul(c | 0, 0x85EBCA77)) / 4294967296; }
function gaussR(rng) { let u = 0, v = 0; while (u === 0) u = rng(); v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v); }

/* ---------- gradient noise ---------- */
const Noise = (() => {
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
/* 1-2px breathing drift for otherwise static elements */
function drift(t, seed, amp = 1.5, speed = 0.35) { return [Noise.n1(t * speed, seed) * amp, Noise.n1(t * speed, seed + 50) * amp]; }

/* ---------- fonts ---------- */
const FAM = {
  SFPRO: '"SFProDisplay", "Helvetica Neue", sans-serif',
  PF: '"PingFang SC"',
  SONG: '"Songti SC"',
  MONO: '"SFMono", Menlo, monospace',
  AV: '"Avenir Next"',
};
function F(size, fam, weight = 400) { return `${weight} ${size}px ${fam}`; }
const FNT = {
  pf: (s, w = 400) => F(s, FAM.PF, w),
  song: (s, w = 700) => F(s, FAM.SONG, w),
  mono: (s, w = 400) => F(s, FAM.MONO, w),
  av: (s, w = 600) => F(s, FAM.AV, w),
  sfpro: (s, w = 250) => F(s, FAM.SFPRO, w),
};

/* ---------- music cue sheet (W/music/cues_used.json, read-only; defaults = shared timeline) ---------- */
const CUES = {
  version: 'default',
  typing: { yong: [4.47, 4.55, 4.63, 4.71], yige: [4.97, 5.05, 5.13, 5.21], zi: [5.29, 5.46],
    xingrong: [5.97, 6.0043, 6.0386, 6.0729, 6.1071, 6.1414, 6.1757, 6.21], qiutian: [6.47, 6.51, 6.55, 6.59, 6.63, 6.67, 6.71] },
  digitTicks: [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
  roulette: [36.75, 36.785, 36.8246, 36.8692, 36.9197, 36.9768, 37.0413, 37.1142, 37.1965, 37.2895, 37.3947, 37.5135, 37.6478, 37.7995, 37.9709, 38.1646, 38.3835, 38.6309, 38.9104, 39.2262],
  flyout: [35.0, 35.09, 35.18, 35.27, 35.36, 35.45, 35.54, 35.63],
  warnings: [],
};
async function loadCues() {
  try {
    const r = await fetch('/cues.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    const cs = d.cues;
    const ty = {};
    for (const c of cs) if (c.cat === 'typing') { const m = /^key \S+ \((\w+)\)$/.exec(c.name); if (m) (ty[m[1]] = ty[m[1]] || []).push(c.t); }
    for (const k of Object.keys(CUES.typing)) if (ty[k] && ty[k].length) CUES.typing[k] = ty[k].sort((a, b) => a - b);
    const pick = (re) => cs.filter(c => re.test(c.name)).map(c => c.t).sort((a, b) => a - b);
    const dt = pick(/^digit roll tick/); if (dt.length === 8) CUES.digitTicks = dt; else CUES.warnings.push('digit ticks ' + dt.length);
    const ro = pick(/^roulette tick/); if (ro.length >= 10) CUES.roulette = ro; else CUES.warnings.push('roulette ' + ro.length);
    const fo = pick(/^top-8 fly-out/); if (fo.length === 8) CUES.flyout = fo; else CUES.warnings.push('flyout ' + fo.length);
    CUES.tokenLand = pick(/^TOKEN lands/);
    CUES.planes = pick(/^PLANE through camera/);
    CUES.version = (d.meta && d.meta.version) || 'unknown';
  } catch (e) { CUES.warnings.push('cue sheet not loaded: ' + e); }
}

/* ---------- text helpers ---------- */
const _measureCtx = (() => { const c = document.createElement('canvas'); c.width = 8; c.height = 8; return c.getContext('2d'); })();
const _mCache = new Map();
function textW(str, font, ls = 0) {
  const key = font + '|' + ls + '|' + str;
  let w = _mCache.get(key);
  if (w === undefined) {
    _measureCtx.font = font;
    _measureCtx.letterSpacing = '0px';
    w = 0;
    for (const ch of str) w += _measureCtx.measureText(ch).width + ls;
    if (str.length) w -= ls;
    _mCache.set(key, w);
  }
  return w;
}
/* per-char layout: returns {chars:[{c,x,w}], width} (x relative to start, ls in px) */
const _lCache = new Map();
function layoutChars(str, font, ls = 0) {
  const key = font + '|' + ls + '|' + str;
  let L = _lCache.get(key);
  if (L) return L;
  _measureCtx.font = font;
  _measureCtx.letterSpacing = '0px';
  const chars = []; let x = 0;
  const arr = [...str];
  arr.forEach((ch, i) => {
    const w = _measureCtx.measureText(ch).width;
    chars.push({ c: ch, x, w, i });
    x += w + (i < arr.length - 1 ? ls : 0);
  });
  L = { chars, width: x };
  _lCache.set(key, L);
  return L;
}
function inkBox(ch, font) { // actual glyph ink bounds relative to (0, alphabetic baseline)
  _measureCtx.font = font;
  const m = _measureCtx.measureText(ch);
  return { l: -m.actualBoundingBoxLeft, r: m.actualBoundingBoxRight, t: -m.actualBoundingBoxAscent, b: m.actualBoundingBoxDescent, w: m.width };
}
function setFilter(ctx, blur) { ctx.filter = blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : 'none'; }

/* ---------- canvas helpers ---------- */
function mkCanvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
function rrect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, Math.max(0, Math.min(r, w / 2, h / 2))); }
/* soft round sprite (radial falloff) used for glows, dust and bokeh */
const SPRITES = {};
function softDot(key, colorHex, hard = 0.0) {
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
function drawSprite(ctx, spr, x, y, r, a = 1) {
  if (a <= 0.002 || r <= 0) return;
  ctx.globalAlpha = clamp(a);
  ctx.drawImage(spr, x - r, y - r, r * 2, r * 2);
  ctx.globalAlpha = 1;
}

/* ---------- cold diverging colormap: -1 indigo -> 0 near-black -> +1 cyan (extremes -> ice) ---------- */
const CMAP = (() => {
  const n = hexRgb('#2E3FBF'), z = hexRgb('#0A0E18'), p = hexRgb('#6EE7F5'), x = hexRgb('#E6FBFF');
  return function (v) {
    v = clamp(v, -1, 1);
    if (v >= 0) { const c = mixRgb(z, p, Math.min(1, v / 0.85)); return v > 0.85 ? mixRgb(p, x, (v - 0.85) / 0.15) : c; }
    const c = mixRgb(z, n, Math.min(1, -v / 0.9)); return -v > 0.9 ? mixRgb(n, mixRgb(n, x, 0.35), (-v - 0.9) / 0.1) : c;
  };
})();

/* ---------- monotone cubic interpolation (for camera paths through exact key times) ---------- */
function makePchip(xs, ys) {
  const n = xs.length, d = new Array(n), m = new Array(n - 1), h = new Array(n - 1);
  for (let i = 0; i < n - 1; i++) { h[i] = xs[i + 1] - xs[i]; m[i] = (ys[i + 1] - ys[i]) / h[i]; }
  d[0] = m[0]; d[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) {
    if (m[i - 1] * m[i] <= 0) d[i] = 0;
    else { const w1 = 2 * h[i] + h[i - 1], w2 = h[i] + 2 * h[i - 1]; d[i] = (w1 + w2) / (w1 / m[i - 1] + w2 / m[i]); }
  }
  return function (x) {
    if (x <= xs[0]) return ys[0] + d[0] * (x - xs[0]) * 0;
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0; while (i < n - 2 && x > xs[i + 1]) i++;
    const t = (x - xs[i]) / h[i], t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * d[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * d[i + 1];
  };
}

/* GB2312 level-1 hanzi (3755) */
const GB1 = (() => {
  const dec = new TextDecoder('gb18030');
  const out = [];
  for (let hi = 0xB0; hi <= 0xD7; hi++) for (let lo = 0xA1; lo <= 0xFE; lo++) {
    if (hi === 0xD7 && lo > 0xF9) continue;
    const s = dec.decode(new Uint8Array([hi, lo]));
    if (s && s.length === 1 && s !== '�') out.push(s);
  }
  return out;
})();

/* ring with analytic motion blur: the stroke widens by the distance travelled during one sub-frame
   (energy preserved), so fast rings stay continuous instead of stepping. v = radial speed px/s */
let SUBDT = 0;
function blurRing(ctx, cx, cy, r, v, lw, col, a) {
  if (a <= 0.002 || r <= 0) return;
  const smear = Math.abs(v) * SUBDT;
  const w = Math.max(lw, smear);
  ctx.lineWidth = w; ctx.strokeStyle = rgba(col, a * lw / w);
  ctx.beginPath(); ctx.arc(cx, cy, Math.max(0.5, r - Math.sign(v) * (w - lw) / 2 * 0), 0, TAU); ctx.stroke();
}
