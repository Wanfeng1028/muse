/* ==========================================================================
   number_impact — 数字冲击卡
   A small counter races up from zero, growing as it goes, speed lines
   converging on it; then it slams to the target at full size: white flash,
   chromatic split, a shockwave ring, embers thrown out, camera shake, a hot
   glow that cools to a steady ember. A label settles in.

   Look: black stage, white-hot to vermilion numerals (heavy sans), bloom
   carried by a dedicated glow pass, smoke haze. Digits sit in fixed cells so
   nothing jitters while counting; the ones digit rolls like a wheel.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, spring, springKick, hash2, rgba, tokFont, mkCanvas, softDot, drawSprite, Noise } from '../engine/core.js';
import { inkBox } from '../engine/text.js';

export const id = 'number_impact';
export const role = 'card';
export const desc = '数字冲击卡：小号数字从 0 飞速计数、边数边变大，速度线向中心汇聚；到目标值时重重砸下：闪白、色散、冲击波环、火星四溅、镜头抖动、辉光由炽白冷却成余烬，标签落定。全屏不透明。';

export const params = {
  value: { default: 90, type: 'number', desc: '目标值（整数）。' },
  unit: { default: '%', type: 'string', desc: '单位（小一号，跟在数字后）。' },
  label: { default: '剪辑时间省下', type: 'string', desc: '数字上方的标签。' },
  sub: { default: 'TIME SAVED ON EDITING', type: 'string', desc: '数字下方的小字。' },
  t_count: { default: 0.35, type: 'number', desc: '开始计数。' },
  t_hit: { default: 1.6, type: 'number', desc: '砸到目标值的时刻。' },
  hot: { default: '#FF5A1F', type: 'color', desc: '主色（炽热橙红）。' },
};

export function timing(p) {
  // one tick per change of the displayed value, at most one per frame
  const ticks = [];
  let last = -1, lastT = -1;
  for (let f = Math.ceil(p.t_count * 30); f < Math.round(p.t_hit * 30); f++) {
    const t = f / 30, v = countValue(t, p);
    if (v !== last && t - lastT > 1 / 30 - 1e-6) { ticks.push(+t.toFixed(4)); last = v; lastT = t; }
  }
  return { count: p.t_count, hit: p.t_hit, ticks, label: p.t_hit + 0.3 };
}
function countU(t, p) { return seg(t, p.t_count, p.t_hit - 0.06); }
function countValue(t, p) {
  if (t >= p.t_hit) return p.value;
  const u = countU(t, p);
  return Math.min(p.value - 1, Math.floor(p.value * E.quadIn(u) * 0.985 + (u > 0 ? 1 : 0) - 1 + 1e-9));
}

/* ------------------------------------------------------------------ digits */
function numeralFill(ctx, y0, y1, heat, p) {
  const g = ctx.createLinearGradient(0, y0, 0, y1);
  g.addColorStop(0, mix('#FFF4DF', '#FFFFFF', heat));
  g.addColorStop(0.45, mix('#FF9A4A', '#FFE2B0', heat));
  g.addColorStop(1, mix(p.hot, '#FF8A3D', heat));
  return g;
}
function mix(a, b, t) {
  const A = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16)), B = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], clamp(t)))).join(',')})`;
}

function drawNumber(ctx, glow, t, p, tk, env, sc, heat, glowA) {
  const T = timing(p);
  const hitDone = t >= p.t_hit;
  const tq = Math.floor(t * env.fps + 1e-6) / env.fps;     // value held for the whole frame: crisp digits, no ghosting
  const v = countValue(tq, p);
  const str = String(v);
  const size = 420;
  const font = tokFont(tk, 'sans', size, 900), ufont = tokFont(tk, 'sans', size * 0.42, 900);
  const cell = size * 0.6;
  const n = str.length, uw = p.unit ? size * 0.36 : 0;
  const total = n * cell + uw;
  ctx.save(); ctx.scale(sc, sc);
  ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  const ib = inkBox('0', font);
  const base = -(ib.t + ib.b) / 2;
  ctx.fillStyle = numeralFill(ctx, base + ib.t, base + ib.b, heat, p);
  for (let i = 0; i < n; i++) ctx.fillText(str[i], -total / 2 + cell * (i + 0.5), base);
  if (p.unit) {
    ctx.font = ufont; ctx.fillStyle = numeralFill(ctx, base - size * 0.72, base, heat, p);
    ctx.fillText(p.unit, total / 2 - uw / 2 + size * 0.02, base - size * 0.02);
  }
  ctx.restore();
  // glow pass: the same numerals, hot orange, into the half-res glow layer
  if (glow && glowA > 0.01) {
    glow.save(); glow.scale(sc, sc); glow.font = font; glow.textAlign = 'center'; glow.textBaseline = 'alphabetic';
    glow.fillStyle = rgba('#FF7A2E', glowA);
    for (let i = 0; i < n; i++) glow.fillText(str[i], -total / 2 + cell * (i + 0.5), base);
    if (p.unit) { glow.font = ufont; glow.fillText(p.unit, total / 2 - uw / 2, base); }
    glow.restore();
  }
  return { total: total * sc, h: (ib.b - ib.t) * sc };
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  if (t > p.t_count && t < p.t_hit + 0.5) return 10;
  if (t < p.t_hit + 1.2) return 4;
  return 2;
}
export function post(t, p) {
  const s = t - p.t_hit;
  const flash = s >= 0 && s < 0.3 ? 0.55 * Math.exp(-s / 0.05) : 0;
  const ca = s >= 0 && s < 0.12 ? 0.012 * (1 - s / 0.12) : 0;
  return { flash, flashTint: [1, 0.86, 0.72], ca, fade: smooth(seg(t, 0, 0.2)) };
}

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, glow = env.glow, T = timing(p);
  const s = t - p.t_hit;
  // stage
  ctx.fillStyle = '#050304'; ctx.fillRect(0, 0, W, H);
  const heatBg = s >= 0 ? Math.exp(-s / 0.8) : 0;
  const rg = ctx.createRadialGradient(W / 2, H * 0.47, 10, W / 2, H * 0.47, H * 0.6);
  rg.addColorStop(0, rgba(p.hot, 0.16 + 0.35 * heatBg)); rg.addColorStop(0.5, rgba('#5A0E08', 0.18 + 0.2 * heatBg)); rg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
  // camera shake after the hit
  let sx = 0, sy = 0, rot = 0;
  if (s >= 0 && s < 0.6) {
    const a = 22 * Math.exp(-s / 0.09);
    sx = a * Math.sin(TAU * 21 * s + 1.3); sy = a * Math.sin(TAU * 17 * s + 0.2) * 0.8; rot = 0.012 * Math.exp(-s / 0.08) * Math.sin(TAU * 13 * s);
  }
  const cx = W / 2, cy = H * 0.47;
  ctx.save(); ctx.translate(cx + sx, cy + sy); ctx.rotate(rot);
  if (glow) { glow.save(); glow.translate(cx + sx, cy + sy); glow.rotate(rot); }
  // speed lines converging on the counter (accelerate with the count)
  const u = countU(t, p);
  if (u > 0 && s < 0.25) {
    const k = E.quadIn(u) * (s > 0 ? Math.exp(-s / 0.06) : 1);
    for (let i = 0; i < 70; i++) {
      const a = hash2(3, i) * TAU, r0 = 260 + 700 * hash2(4, i);
      const ph = (t * (1.5 + 3.5 * k) * (0.6 + hash2(5, i)) + hash2(6, i)) % 1;
      const r1 = r0 * (1 - ph), len = 60 + 380 * k * hash2(7, i);
      const x1 = Math.cos(a) * (r1 + 240), y1 = Math.sin(a) * (r1 + 240);
      const x2 = Math.cos(a) * (r1 + 240 + len), y2 = Math.sin(a) * (r1 + 240 + len);
      ctx.strokeStyle = rgba(i % 5 ? '#FF7A3A' : '#FFE6C8', (0.12 + 0.4 * k) * Math.sin(Math.PI * ph)); ctx.lineWidth = 1.5 + 2 * hash2(8, i);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
  }
  // shockwave rings + embers
  if (s >= 0) {
    for (const [d, w, a] of [[0, 26, 0.9], [0.06, 10, 0.5]]) {
      const ss = s - d;
      if (ss < 0 || ss > 0.9) continue;
      const r = 120 + 1500 * E.expoOut(ss / 0.9);
      const al = a * Math.pow(1 - ss / 0.9, 1.6);
      ctx.strokeStyle = rgba('#FFD2A0', al); ctx.lineWidth = w * (1 - ss / 0.9) + 2;
      ctx.beginPath(); ctx.ellipse(0, 0, r, r * 0.9, 0, 0, TAU); ctx.stroke();
      if (glow) { glow.strokeStyle = rgba(p.hot, al); glow.lineWidth = w * 2; glow.beginPath(); glow.ellipse(0, 0, r, r * 0.9, 0, 0, TAU); glow.stroke(); }
    }
    // radial spark burst: streaks along their velocity, drag + a little gravity
    for (let i = 0; i < 90; i++) {
      const life = 0.35 + 0.75 * hash2(31, i);
      if (s > life) continue;
      const a = hash2(32, i) * TAU, v = 700 + 1900 * hash2(33, i), td = 0.16;
      const kk = 1 - Math.exp(-s / td), vv = v * Math.exp(-s / td);
      const r0 = 150 + 60 * hash2(34, i);
      const x = Math.cos(a) * (r0 + v * td * kk), y = Math.sin(a) * (r0 + v * td * kk) * 0.9 + 420 * s * s;
      const lx = Math.cos(a) * vv * 0.028, ly = Math.sin(a) * vv * 0.028 * 0.9;
      const al = Math.pow(1 - s / life, 1.4);
      ctx.strokeStyle = mix('#FFFFFF', p.hot, s / life).replace('rgb', 'rgba').replace(')', `,${al.toFixed(3)})`);
      ctx.lineWidth = 1.5 + 2 * hash2(35, i); ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x - lx, y - ly); ctx.lineTo(x, y); ctx.stroke();
      if (glow) drawSprite(glow, softDot('spk', '#FF7A2E'), x, y, 9, al * 0.9);
    }
    ctx.lineCap = 'butt';
    // floating embers after the hit
    for (let i = 0; i < 40; i++) {
      const life = 1.2 + 1.5 * hash2(21, i), ss = s - 0.05 * hash2(22, i);
      if (ss < 0 || ss > life) continue;
      const a = hash2(23, i) * TAU, v = 120 + 380 * hash2(24, i);
      const x = Math.cos(a) * v * (1 - Math.exp(-ss / 0.5)) * 1.4 + Noise.n1(ss + i, 3) * 30, y = Math.sin(a) * v * (1 - Math.exp(-ss / 0.5)) - 60 * ss * ss;
      const al = Math.sin(Math.PI * ss / life) * 0.9;
      drawSprite(ctx, softDot('em', '#FFC08A'), x, y, 3 + 3 * hash2(25, i), al);
      if (glow) drawSprite(glow, softDot('emg', '#FF6A20'), x, y, 12, al * 0.8);
    }
  }
  // the numeral: small and growing while counting, slams in over-scaled, springs to rest
  let sc, heat, gA;
  if (s < 0) { sc = lerp(0.36, 0.62, E.quadIn(u)); heat = 0.2 + 0.4 * E.quadIn(u); gA = 0.25 + 0.35 * E.quadIn(u); }
  else { sc = 1 + 0.28 * Math.exp(-s / 0.06) * Math.cos(TAU * 3.2 * s) * (s < 0.5 ? 1 : 0) - 0.0; heat = Math.exp(-s / 0.35); gA = 0.35 + 0.65 * Math.exp(-s / 0.5); }
  const appear = smooth(seg(t, p.t_count - 0.2, p.t_count + 0.05));
  ctx.globalAlpha = appear;
  // smoky haze behind the numeral
  if (s >= 0) drawSprite(ctx, softDot('haze', '#3A0C06'), 0, 0, 700, 0.7 * Math.exp(-s / 2));
  drawNumber(ctx, glow, t, p, tk, env, sc, heat, gA * appear);
  ctx.globalAlpha = 1;
  ctx.restore(); if (glow) glow.restore();
  // label above, small caps below
  const la = E.expoOut(seg(t, T.label, T.label + 0.6));
  if (la > 0.001) {
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.font = tokFont(tk, 'sans', 58, 700); ctx.letterSpacing = '8px';
    ctx.filter = `blur(${(8 * (1 - la)).toFixed(2)}px)`;
    ctx.fillStyle = rgba('#F3E7DA', la); ctx.fillText(p.label, W / 2 + 4, cy - 250 - 20 * (1 - la));
    ctx.font = tokFont(tk, 'sans', 26, 500); ctx.letterSpacing = '9px';
    ctx.fillStyle = rgba('#B7806A', 0.9 * la); ctx.fillText(p.sub, W / 2 + 4, cy + 300 + 16 * (1 - la));
    ctx.filter = 'none'; ctx.letterSpacing = '0px';
    const w = 240 * la;
    ctx.fillStyle = rgba(p.hot, 0.8 * la); ctx.fillRect(W / 2 - w / 2, cy + 240, w, 4);
  }
}

export function bbox(t, p, tk, env) {
  return [{ kind: 'text', label: String(p.value), x: env.W * 0.15, y: env.H * 0.35, w: env.W * 0.7, h: env.H * 0.25, font_px: 420 }];
}
