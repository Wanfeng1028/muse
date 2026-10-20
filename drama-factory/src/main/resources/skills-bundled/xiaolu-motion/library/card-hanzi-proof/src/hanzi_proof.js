/* ==========================================================================
   hanzi_proof — 汉字雨纠错卡
   Printed characters rain down a sheet of vermilion-ruled xuan paper in three
   depth layers. Time slows; one column settles into an idiom that contains a
   typo. A proofreader's red brush circles the wrong character, strikes it
   through, writes the correction in the margin; the wrong character drops
   away, the correction slides along the leader line into its slot and turns
   into print, and a small red "校" seal lands. Then the rain drifts on.

   Look: warm paper, fibre texture, ink with a hair of bleed, 朱丝栏 rules,
   brush strokes with pressure variation. Depth by size, tone and defocus.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, hash2, hash3, rgba, tokFont, mkCanvas, Noise } from '../engine/core.js';
import { inkBox } from '../engine/text.js';

export const id = 'hanzi_proof';
export const role = 'card';
export const desc = '汉字雨纠错卡：宣纸上的印刷汉字像雨一样落下，一列停成成语，红笔圈出错字、划掉、在页边写出正确字，正确字滑入原位变成铅字，盖“校”印。全屏不透明。';

export const params = {
  text: { default: '再接再励', type: 'string', desc: '停下来的那一列（含一个错字）。' },
  wrong: { default: 3, type: 'number', desc: '错字在 text 里的序号（从 0 起）。' },
  right: { default: '厉', type: 'string', desc: '正确的字。' },
  seal: { default: '校', type: 'string', desc: '印章里的字（1 字）。' },
  paper: { default: '#EDE4D3', type: 'color', desc: '纸色。' },
  ink: { default: '#1D1915', type: 'color', desc: '墨色。' },
  red: { default: '#C23A22', type: 'color', desc: '朱批红。' },
  t_settle: { default: 1.35, type: 'number', desc: '这一列停稳的时间（秒）。' },
};

export function timing(p) {
  const s = p.t_settle;
  return { settle: s, circle: s + 0.2, strike: s + 0.62, write: s + 0.86, drop: s + 1.3, fly: s + 1.42, land: s + 1.95, seal: s + 2.3, resume: s + 2.1 };
}

/* ---------------------------------------------------------------- characters */
let GB1 = null;
function gb1() {
  if (GB1) return GB1;
  const dec = new TextDecoder('gb18030'), out = [];
  for (let hi = 0xB0; hi <= 0xD7; hi++) for (let lo = 0xA1; lo <= 0xFE; lo++) {
    if (hi === 0xD7 && lo > 0xF9) continue;
    const s = dec.decode(new Uint8Array([hi, lo]));
    if (s && s.length === 1 && s !== '�') out.push(s);
  }
  GB1 = out;
  return out;
}

/* rain time: the rain slows to a near stop while the proofreader works, then drifts on */
const TT = {};
function rainClock(p) {
  const k = JSON.stringify([p.t_settle]);
  if (TT[k]) return TT[k];
  const T = timing(p), dt = 1 / 600, n = Math.ceil(8 / dt);
  const acc = new Float32Array(n + 1);
  let a = 0;
  for (let i = 0; i < n; i++) {
    const t = i * dt;
    const slow = E.cubicInOut(seg(t, T.settle - 0.55, T.settle + 0.1));
    const back = E.sineInOut(seg(t, T.resume, T.resume + 1.2));
    const f = lerp(1, 0.06, slow) + (0.3 - 0.06) * back;
    acc[i] = a; a += f * dt;
  }
  acc[n] = a;
  TT[k] = t => { const x = clamp(t / dt, 0, n - 1), i = Math.floor(x); return lerp(acc[i], acc[i + 1], x - i); };
  return TT[k];
}
function speedAt(p, t) { const c = rainClock(p); return (c(t + 0.005) - c(t - 0.005)) / 0.01; }

/* ---------------------------------------------------------------- paper */
const CACHE = {};
function paperSprite(W, H, col, red) {
  const k = 'paper' + W + H + col + red;
  if (CACHE[k]) return CACHE[k];
  const c = mkCanvas(W, H), x = c.getContext('2d');
  x.fillStyle = col; x.fillRect(0, 0, W, H);
  // cloudy formation of the sheet (large low-contrast fbm blotches)
  const hw = W >> 1, hh = H >> 1, nc = mkCanvas(hw, hh), nx = nc.getContext('2d');   // formation noise at half res
  const img = nx.createImageData(hw, hh), d = img.data;
  for (let y = 0; y < hh; y++) for (let xx = 0; xx < hw; xx++) {
    const n = Noise.fbm(xx * 0.008, y * 0.008, 4) * 0.9 + Noise.fbm(xx * 0.06, y * 0.06, 2) * 0.25;
    const i = (y * hw + xx) * 4, v = n * 2;
    d[i] = v > 0 ? 255 : 90; d[i + 1] = v > 0 ? 250 : 70; d[i + 2] = v > 0 ? 235 : 40; d[i + 3] = Math.min(255, Math.abs(v) * 255 * 0.14);
  }
  nx.putImageData(img, 0, 0);
  x.imageSmoothingQuality = 'high'; x.drawImage(nc, 0, 0, W, H);
  // fibres
  for (let i = 0; i < 2600; i++) {
    const px = hash2(1, i) * W, py = hash2(2, i) * H, a = hash2(3, i) * TAU, l = 6 + 26 * hash2(4, i);
    x.strokeStyle = hash2(5, i) < 0.5 ? `rgba(120,96,64,${0.05 + 0.07 * hash2(6, i)})` : `rgba(255,252,240,${0.15 + 0.2 * hash2(6, i)})`;
    x.lineWidth = 0.6 + 0.8 * hash2(7, i);
    x.beginPath(); x.moveTo(px, py); x.quadraticCurveTo(px + Math.cos(a + 0.6) * l * 0.5, py + Math.sin(a + 0.6) * l * 0.5, px + Math.cos(a) * l, py + Math.sin(a) * l); x.stroke();
  }
  // 朱丝栏: pale vermilion column rules
  const cols = 9, cw = W / cols;
  for (let q = 1; q < cols; q++) {
    const xx = q * cw;
    x.fillStyle = rgba(red, 0.16); x.fillRect(xx - 1, H * 0.035, 2, H * 0.93);
    x.fillStyle = rgba(red, 0.06); x.fillRect(xx - 3, H * 0.035, 6, H * 0.93);
  }
  x.strokeStyle = rgba(red, 0.22); x.lineWidth = 3; x.strokeRect(cw * 0.25, H * 0.035, W - cw * 0.5, H * 0.93);
  x.strokeStyle = rgba(red, 0.12); x.lineWidth = 1.2; x.strokeRect(cw * 0.25 + 9, H * 0.035 + 9, W - cw * 0.5 - 18, H * 0.93 - 18);
  CACHE[k] = c;
  return c;
}

/* glyph sprite: ink + a hair of bleed, cached per (char, size, blur) */
function inkGlyph(ch, font, px, ink, blur) {
  blur = Math.round(blur * 4) / 4;                         // quantised: the cache must stay small
  const k = ch + font + ink + blur;
  if (CACHE[k]) return CACHE[k];
  const S = Math.ceil(px * 1.5 + blur * 4), c = mkCanvas(S, S), x = c.getContext('2d');
  const ib = inkBox(ch, font);
  const gx = S / 2 - (ib.l + ib.r) / 2, gy = S / 2 - (ib.t + ib.b) / 2;
  x.font = font; x.textBaseline = 'alphabetic';
  x.filter = `blur(${(0.9 + blur).toFixed(2)}px)`; x.fillStyle = rgba(ink, 0.35); x.fillText(ch, gx, gy);
  x.filter = blur > 0.2 ? `blur(${blur.toFixed(2)}px)` : 'none'; x.fillStyle = ink; x.fillText(ch, gx, gy);
  CACHE[k] = { c, S };
  return CACHE[k];
}

/* ---------------------------------------------------------------- rain */
const LAYERS = [
  { name: 'far', cols: 13, size: 34, spd: 280, tone: 0.28, blur: 1.6, len: [7, 15], gap: 1.45, seed: 11 },
  { name: 'mid', cols: 9, size: 62, spd: 470, tone: 0.62, blur: 0.0, len: [5, 10], gap: 1.35, seed: 23 },
  { name: 'near', cols: 3, size: 150, spd: 900, tone: 0.20, blur: 9, len: [2, 4], gap: 1.5, seed: 37 },
];
function drawRain(ctx, t, p, tk, env, L, tr, fade, clear) {
  const G = gb1(), s = env.s, W = env.W, H = env.H;
  for (const ly of LAYERS) {
    const sz = ly.size * s, sp = sz * ly.gap;
    const font = tokFont(tk, 'serif', sz, 700);
    for (let c = 0; c < ly.cols; c++) {
      const cw = W / ly.cols;
      let x = (c + 0.5) * cw + (hash2(ly.seed, c) - 0.5) * cw * 0.2;
      if (ly.name === 'near' && Math.abs(x - W / 2) < 300 * s) x = x < W / 2 ? 150 * s : W - 150 * s;
      if (ly.name === 'mid' && Math.abs(x - L.cx) < cw * 0.6) continue;            // the proof column
      const v = ly.spd * s * (0.7 + 0.6 * hash2(ly.seed + 1, c));
      const m = ly.len[0] + Math.floor(hash2(ly.seed + 2, c) * (ly.len[1] - ly.len[0] + 1));
      const period = H + sz + 2 * m * sp;               // long enough that a stream never pops on wrap
      const y0 = hash2(ly.seed + 3, c) * period;
      const yh = y0 + v * tr;                              // head position in "rain time"
      const cycle = Math.floor(yh / period);
      const head = yh - cycle * period - m * sp;
      for (let j = 0; j < m; j++) {
        const y = head - j * sp;
        if (y < -sz || y > H + sz) continue;
        const zone = (x > L.cx + 120 * s && x < L.cx + 440 * s) ? 1 - 0.9 * clear : 1;
        const a = Math.pow(1 - j / m, 1.3) * (j === 0 ? 1 : 0.9) * fade * zone;
        if (a < 0.02) continue;
        const ch = G[Math.floor(hash3(ly.seed + c, cycle, j) * G.length)];
        const gs = inkGlyph(ch, font, sz, p.ink, ly.blur * s);
        ctx.globalAlpha = a * ly.tone;
        ctx.drawImage(gs.c, x - gs.S / 2, y - gs.S / 2);
      }
    }
  }
  ctx.globalAlpha = 1;
}

/* ---------------------------------------------------------------- brush */
function brushPath(ctx, pts, w0, w1, col, a, prog) {
  // variable-width stroke: overlapping round dabs along the polyline up to prog (0..1 of length)
  let len = 0; const segs = [];
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); segs.push(l); len += l; }
  const end = len * clamp(prog);
  ctx.fillStyle = rgba(col, a);
  let acc = 0;
  for (let i = 1; i < pts.length && acc < end; i++) {
    const l = segs[i - 1], n = Math.max(1, Math.ceil(l / 1.6));
    for (let k = 0; k < n; k++) {
      const d = acc + l * k / n;
      if (d > end) break;
      const u = d / len;
      const w = lerp(w0, w1, u) * (0.82 + 0.18 * Math.sin(u * 17.0)) * (u < 0.06 ? 0.55 + 7.5 * u : 1);
      const x = lerp(pts[i - 1][0], pts[i][0], k / n), y = lerp(pts[i - 1][1], pts[i][1], k / n);
      ctx.beginPath(); ctx.arc(x, y, w / 2, 0, TAU); ctx.fill();
    }
    acc += l;
  }
}
function circlePts(cx, cy, rx, ry, seed) {
  const pts = [];
  for (let i = 0; i <= 90; i++) {
    const u = i / 90, a = -2.2 + u * TAU * 1.08;       // a bit more than a full turn, like a quick hand
    const r = 1 + 0.05 * Math.sin(u * 7 + seed) + 0.03 * Math.sin(u * 17 + seed * 2) + 0.06 * u;
    pts.push([cx + Math.cos(a) * rx * r, cy + Math.sin(a) * ry * r]);
  }
  return pts;
}

/* ---------------------------------------------------------------- layout */
function layout(p, env, tk) {
  const s = env.s, chars = [...p.text], n = chars.length;
  const sz = 150 * s, step = 188 * s;
  const cx = env.W * 0.44, cy = env.H * 0.47;
  const ys = chars.map((_, i) => cy + (i - (n - 1) / 2) * step);
  return { s, chars, n, sz, step, cx, cy, ys, font: tokFont(tk, 'serif', sz, 900), kfont: tokFont(tk, 'kai', 132 * s, 500) };
}

function camera(t, env) {
  const z = 1 + 0.06 * E.sineInOut(seg(t, 0, env.dur));
  return { z, cx: env.W * 0.46, cy: env.H * 0.5 };
}

/* ---------------------------------------------------------------- component API */
export function mbSamples(t, p) {
  const v = speedAt(p, t), T = timing(p);
  if (t >= T.drop && t < T.land + 0.1) return 8;
  return v > 0.5 ? 8 : v > 0.2 ? 5 : 3;
}
export function post(t) { return { fade: smooth(seg(t, 0, 0.25)) }; }

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, T = timing(p), L = layout(p, env, tk);
  const cam = camera(t, env);
  const clock = rainClock(p), tr = clock(t);
  ctx.drawImage(paperSprite(W, H, p.paper, p.red), 0, 0);
  ctx.save();
  ctx.translate(cam.cx, cam.cy); ctx.scale(cam.z, cam.z); ctx.translate(-cam.cx, -cam.cy);
  // the rain (drawn under a slight paper-coloured haze while time is slowed, so the column pops)
  drawRain(ctx, t, p, tk, env, L, tr, 1, E.cubicInOut(seg(t, T.settle - 0.2, T.circle + 0.3)));
  const hush = E.cubicInOut(seg(t, T.settle - 0.4, T.settle + 0.3)) * (1 - 0.6 * E.sineInOut(seg(t, T.resume, T.resume + 1.2)));
  if (hush > 0.001) { ctx.fillStyle = rgba(p.paper, 0.55 * hush); ctx.fillRect(-W, -H, 3 * W, 3 * H); }

  // the proof column: falls with the rain, decelerates into place
  // it falls with the rain (same rain clock), so it slows exactly as the rain slows, then locks
  const ts = T.settle + 0.1, V = 1350 * L.s;
  const raw = Math.max(0, V * (clock(ts) - tr));
  const fallOff = raw * (1 - 0.5 * E.sineInOut(seg(t, ts - 0.35, ts)));  // soft final approach
  const colBlur = 1.5 * (1 - E.cubicOut(seg(t, T.settle - 0.5, T.settle)));
  for (let i = 0; i < L.n; i++) {
    let y = L.ys[i] - fallOff, x = L.cx, a = 1, rot = 0, ch = L.chars[i];
    if (i === p.wrong && t >= T.drop) {                   // the wrong one drops away
      const u = t - T.drop;
      y += 900 * L.s * u * u + 40 * L.s * u; x += 60 * L.s * u; rot = 0.9 * u * u + 0.2 * u; a = clamp(1 - u / 0.55);
    }
    if (a <= 0.01) continue;
    const gs = inkGlyph(ch, L.font, L.sz, p.ink, colBlur);
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.globalAlpha = a;
    ctx.drawImage(gs.c, -gs.S / 2, -gs.S / 2); ctx.restore();
  }
  ctx.globalAlpha = 1;
  const wy = L.ys[p.wrong], wx = L.cx;
  const rx = 104 * L.s, ry = 100 * L.s;
  const redA = 1 - E.cubicIn(seg(t, T.land + 0.25, T.land + 0.7)) * 0.0;
  // red circle around the typo
  const cp = E.cubicInOut(seg(t, T.circle, T.circle + 0.38));
  if (cp > 0) {
    const pts = circlePts(wx, wy, rx, ry, 1.3);
    brushPath(ctx, pts, 9 * L.s, 4 * L.s, p.red, 0.9 * redA, cp);
  }
  // strike-through (the proofreader's delete stroke) while the wrong character is still there
  const sp2 = E.cubicOut(seg(t, T.strike, T.strike + 0.16));
  if (sp2 > 0 && t < T.drop + 0.35) {
    const k = t < T.drop ? 1 : clamp(1 - (t - T.drop) / 0.35);
    const pts = [[wx - 78 * L.s, wy + 60 * L.s], [wx - 20 * L.s, wy + 12 * L.s], [wx + 30 * L.s, wy - 28 * L.s], [wx + 84 * L.s, wy - 66 * L.s]];
    brushPath(ctx, pts, 11 * L.s, 5 * L.s, p.red, 0.92 * k, sp2);
  }
  // leader line to the margin + the correction written by hand (kai, red)
  const mx = L.cx + 300 * L.s, my = wy - 36 * L.s;
  const lp = E.cubicOut(seg(t, T.write - 0.12, T.write + 0.12));
  if (lp > 0) {
    const pts = [[wx + rx * 0.9, wy - ry * 0.35], [wx + rx * 1.35, wy - ry * 0.55], [mx - 70 * L.s, my + 6 * L.s]];
    const fadeL = 1 - E.cubicIn(seg(t, T.fly, T.fly + 0.3));
    brushPath(ctx, pts, 4 * L.s, 2.5 * L.s, p.red, 0.85 * fadeL, lp);
  }
  const wp = seg(t, T.write, T.write + 0.4);
  const fly = E.cubicInOut(seg(t, T.fly, T.land));
  if (wp > 0) {
    // hand-written glyph revealed top-left -> bottom-right, then carried to the slot and set in print
    const gx = lerp(mx, wx, fly), gy = lerp(my, wy, fly) - Math.sin(Math.PI * fly) * 60 * L.s;
    const kg = inkGlyph(p.right, L.kfont, 132 * L.s, p.red, 0);
    const pg = inkGlyph(p.right, L.font, L.sz, p.ink, 0);
    const toPrint = E.cubicInOut(seg(t, T.land - 0.28, T.land + 0.05));
    ctx.save();
    ctx.translate(gx, gy);
    const sc = lerp(0.86, 1, fly);
    ctx.scale(sc, sc);
    if (t < T.fly) {                                        // stroke-order-ish reveal
      const r = E.cubicOut(wp);
      ctx.beginPath(); ctx.moveTo(-kg.S, -kg.S); ctx.lineTo(-kg.S / 2 + kg.S * 1.9 * r, -kg.S); ctx.lineTo(-kg.S / 2 + kg.S * 1.9 * r - kg.S, kg.S); ctx.lineTo(-kg.S, kg.S); ctx.closePath(); ctx.clip();
    }
    ctx.globalAlpha = 1 - toPrint; ctx.drawImage(kg.c, -kg.S / 2, -kg.S / 2);
    ctx.globalAlpha = toPrint; ctx.drawImage(pg.c, -pg.S / 2, -pg.S / 2);
    ctx.restore(); ctx.globalAlpha = 1;
    // the ink settling: one soft ring on the paper when it lands
    const ls = t - T.land;
    if (ls > 0 && ls < 0.6) {
      ctx.strokeStyle = rgba(p.ink, 0.18 * (1 - ls / 0.6)); ctx.lineWidth = 2 * L.s;
      ctx.beginPath(); ctx.arc(wx, wy, (70 + 90 * E.cubicOut(ls / 0.6)) * L.s, 0, TAU); ctx.stroke();
    }
  }
  // tick mark next to the corrected character, then the seal
  const tp = E.cubicOut(seg(t, T.land + 0.12, T.land + 0.3));
  if (tp > 0) brushPath(ctx, [[wx + 128 * L.s, wy + 6 * L.s], [wx + 146 * L.s, wy + 28 * L.s], [wx + 196 * L.s, wy - 36 * L.s]], 8 * L.s, 3.5 * L.s, p.red, 0.9, tp);
  drawSeal(ctx, t, p, tk, L, T, env);
  ctx.restore();
}

function drawSeal(ctx, t, p, tk, L, T, env) {
  const u = t - T.seal;
  if (u < 0) return;
  const k = E.backOut(clamp(u / 0.16), 1.2), sc = lerp(1.6, 1, clamp(u / 0.12)), a = clamp(u / 0.06);
  const x = L.cx + 300 * L.s, y = L.ys[L.n - 1] + 165 * L.s, S = 108 * L.s;
  ctx.save(); ctx.translate(x, y); ctx.rotate(-0.05); ctx.scale(sc, sc); ctx.globalAlpha = a * (0.9 + 0.1 * k);
  const key = 'seal' + p.seal + S + p.red;
  if (!CACHE[key]) {
    const c = mkCanvas(Math.ceil(S * 1.2), Math.ceil(S * 1.2)), x2 = c.getContext('2d'), o = S * 0.1;
    x2.fillStyle = p.red; x2.beginPath(); x2.roundRect(o, o, S, S, S * 0.08); x2.fill();
    x2.globalCompositeOperation = 'destination-out';
    x2.font = tokFont(tk, 'kai', S * 0.74, 500); x2.textAlign = 'center'; x2.textBaseline = 'alphabetic';
    const ib = inkBox(p.seal, x2.font);
    x2.fillText(p.seal, o + S / 2, o + S / 2 - (ib.t + ib.b) / 2);
    x2.lineWidth = S * 0.035; x2.strokeRect(o + S * 0.07, o + S * 0.07, S * 0.86, S * 0.86);
    for (let i = 0; i < 260; i++) {                       // uneven stamp pressure
      x2.globalAlpha = 0.25 + 0.5 * hash2(9, i);
      x2.beginPath(); x2.arc(o + hash2(10, i) * S, o + hash2(11, i) * S, 0.6 + 2.2 * hash2(12, i), 0, TAU); x2.fill();
    }
    CACHE[key] = c;
  }
  const c = CACHE[key];
  ctx.drawImage(c, -c.width / 2, -c.height / 2);
  ctx.restore(); ctx.globalAlpha = 1;
}

export function bbox(t, p, tk, env) {
  const L = layout(p, env, tk);
  return [{ kind: 'text', label: p.text, x: L.cx - L.sz / 2, y: L.ys[0] - L.sz / 2, w: L.sz, h: L.step * (L.n - 1) + L.sz, font_px: L.sz }];
}
