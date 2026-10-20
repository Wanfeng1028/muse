/* ==========================================================================
   prompt_box — 输入框下指令卡
   A command is typed into a generic input bar character by character. Enter:
   three generated pieces (a video, a caption track, a sound track) materialise,
   then each flies (0.7 s) into an open box. The box holds one beat with
   everything inside, then the lid swings shut — unhurried — and a check tab
   appears on the lid.

   Look: a soft daylight studio. Pale cool greys, matte white objects, large
   soft shadows, one cobalt accent. No platform / product styling, no logos.
   The box is a lit 3-D object (perspective, hinged lid, interior shading).
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, spring, springKick, hash2, rgba, rrect, tokFont, mkCanvas, softDot, drawSprite } from '../engine/core.js';
import { layoutChars, inkBox } from '../engine/text.js';

export const id = 'prompt_box';
export const role = 'card';
export const desc = '输入框下指令卡：输入框里逐字打出指令，回车后生成三样东西（成片、字幕、音效），各自飞约 0.7 秒进盒子，停一拍后合盖、盖上出现勾。通用输入框，无平台样式。全屏不透明。';

export const params = {
  text: { default: '把这段口播剪成竖屏短视频', type: 'string', desc: '逐字打出的指令。' },
  hint: { default: '描述你想要的视频…', type: 'string', desc: '输入框占位提示。' },
  items: { default: [['成片', '00:58'], ['字幕', '83 条'], ['音效', '12 个']], type: 'any', desc: '三样生成物：[标签, 小字]。' },
  accent: { default: '#2F5BFF', type: 'color', desc: '强调色。' },
  t_type: { default: 0.3, type: 'number', desc: '开始打字。' },
  cps: { default: 10, type: 'number', desc: '打字速度（字/秒）。' },
  fly: { default: 0.7, type: 'number', desc: '每样东西飞进盒子的时长（秒）。' },
  beat: { default: 0.4, type: 'number', desc: '全部进盒后停一拍再合盖（秒）。' },
  close: { default: 0.55, type: 'number', desc: '合盖时长（秒）。' },
};

/* ------------------------------------------------------------------ timing */
export function timing(p) {
  const n = [...p.text].length;
  const keys = [];
  let t = p.t_type;
  for (let i = 0; i < n; i++) { keys.push(t); t += (1 / p.cps) * (0.8 + 0.4 * hash2(4, i)) + (i === 3 || i === 7 ? 0.06 : 0); }
  const enter = t + 0.16;
  const gen = [0, 1, 2].map(k => enter + 0.16 + 0.1 * k);
  const launch = [0, 1, 2].map(k => enter + 0.62 + 0.14 * k);
  const land = launch.map(x => x + p.fly);
  const close0 = land[2] + p.beat, closed = close0 + p.close;
  return { n, keys, enter, gen, launch, land, close0, closed, check: closed + 0.2 };
}

/* ------------------------------------------------------------------ 3-D box */
// look-at camera: world Y up, box centred on the origin, bottom on Y = 0
const BOX = { w: 600, d: 420, h: 250, yaw: -0.36, lidT: 16 };
const CAM3 = (() => {
  const tgt = [0, 150, 0], dist = 2150, elev = 0.40;
  const C = [0, tgt[1] + dist * Math.sin(elev), dist * Math.cos(elev)];
  const f = norm([tgt[0] - C[0], tgt[1] - C[1], tgt[2] - C[2]]);
  const r = norm(cross(f, [0, 1, 0])), u = cross(r, f);
  return { C, f, r, u, F: 2250, cx: 540, cy: 1360 };
})();
function norm(v) { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function yawed(v) { const c = Math.cos(BOX.yaw), s = Math.sin(BOX.yaw); return [v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c]; }
function P3(X, Y, Z) {                 // box-local coordinates -> screen [x, y, scale]
  const w = yawed([X, Y, Z]);
  const d = [w[0] - CAM3.C[0], w[1] - CAM3.C[1], w[2] - CAM3.C[2]];
  const z = dot(d, CAM3.f), k = CAM3.F / z;
  return [CAM3.cx + dot(d, CAM3.r) * k, CAM3.cy - dot(d, CAM3.u) * k, k];
}
const KEYL = norm([-0.55, 0.78, 0.35]);
function faceLight(nLocal, amb = 0.5) { const n = yawed(nLocal); return amb + (1 - amb) * Math.max(0, dot(n, KEYL)); }
function facing(nLocal, cLocal) { const n = yawed(nLocal), c = yawed(cLocal); return dot(n, [CAM3.C[0] - c[0], CAM3.C[1] - c[1], CAM3.C[2] - c[2]]) > 0; }
function quad(ctx, pts) { ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]); ctx.closePath(); }
function tone(hex, k) { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) * k); return `rgb(${Math.min(255, c[0]) | 0},${Math.min(255, c[1]) | 0},${Math.min(255, c[2]) | 0})`; }

// the four walls: outward normal, the four corners (top-left, top-right, bottom-right, bottom-left as seen from outside)
function walls() {
  const { w, d, h } = BOX, x0 = -w / 2, x1 = w / 2, z0 = -d / 2, z1 = d / 2;
  return [
    { id: 'front', n: [0, 0, 1], c: [0, h / 2, z1], v: [[x0, h, z1], [x1, h, z1], [x1, 0, z1], [x0, 0, z1]] },
    { id: 'right', n: [1, 0, 0], c: [x1, h / 2, 0], v: [[x1, h, z1], [x1, h, z0], [x1, 0, z0], [x1, 0, z1]] },
    { id: 'back', n: [0, 0, -1], c: [0, h / 2, z0], v: [[x1, h, z0], [x0, h, z0], [x0, 0, z0], [x1, 0, z0]] },
    { id: 'left', n: [-1, 0, 0], c: [x0, h / 2, 0], v: [[x0, h, z0], [x0, h, z1], [x0, 0, z1], [x0, 0, z0]] },
  ];
}

function lidAngle(t, T) {
  const cl = seg(t, T.close0, T.closed);
  const ease = cl < 1 ? E.cubicIn(cl) * 0.55 + E.sineInOut(cl) * 0.45 : 1;       // unhurried, lands with weight
  return lerp(1.92, 0, ease) + (t >= T.closed ? Math.abs(springKick(t - T.closed, 6, 0.45)) * 0.04 : 0);
}
function lidBox(ang) {                   // 8 corners of the lid slab, hinged on the back top edge
  const { w, d, h, lidT } = BOX, x0 = -w / 2 - 8, x1 = w / 2 + 8, zb = -d / 2 - 8, L = d + 16;
  const rot = (y, z) => [h + y * Math.cos(ang) + z * Math.sin(ang), zb - y * Math.sin(ang) + z * Math.cos(ang)];   // (y, z) about hinge
  const pt = (x, y, z) => { const [yy, zz] = rot(y, z); return [x, yy, zz]; };
  return {
    top: [pt(x0, lidT, 0), pt(x1, lidT, 0), pt(x1, lidT, L), pt(x0, lidT, L)],
    bot: [pt(x0, 0, 0), pt(x1, 0, 0), pt(x1, 0, L), pt(x0, 0, L)],
    nTop: [0, Math.cos(ang), -Math.sin(ang)], ang, L,
  };
}

function drawLid(ctx, lid, p, t, T) {
  const P = v => P3(v[0], v[1], v[2]);
  const T4 = lid.top.map(P), B4 = lid.bot.map(P);
  const cTop = lid.top.reduce((a, v) => [a[0] + v[0] / 4, a[1] + v[1] / 4, a[2] + v[2] / 4], [0, 0, 0]);
  const showTop = facing(lid.nTop, cTop);
  // front lip (the free edge) and the side lip facing the camera
  const lip = [T4[3], T4[2], B4[2], B4[3]];
  quad(ctx, lip); ctx.fillStyle = tone('#EDEFF1', faceLight([0, -Math.sin(lid.ang), -Math.cos(lid.ang)].map(x => -x), 0.62)); ctx.fill();
  const side = [T4[0], T4[3], B4[3], B4[0]];
  quad(ctx, side); ctx.fillStyle = tone('#E7EAED', faceLight([-1, 0, 0], 0.6)); ctx.fill();
  const face = showTop ? T4 : B4;
  quad(ctx, face);
  const g = ctx.createLinearGradient(face[0][0], face[0][1], face[2][0], face[2][1]);
  if (showTop) { const k = faceLight(lid.nTop, 0.62); g.addColorStop(0, tone('#FFFFFF', k)); g.addColorStop(1, tone('#F1F3F5', k)); }
  else { g.addColorStop(0, '#C7CDD5'); g.addColorStop(1, '#DCE1E6'); }
  ctx.fillStyle = g; ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(face[3][0], face[3][1]); ctx.lineTo(face[2][0], face[2][1]); ctx.stroke();
  if (showTop) {
    // cobalt band over the lid + the check tab once closed
    const at = (u, v) => P([lerp(lid.top[0][0], lid.top[1][0], u), lerp(lid.top[0][1], lid.top[3][1], v), lerp(lid.top[0][2], lid.top[3][2], v)]);
    quad(ctx, [at(0.47, 0), at(0.53, 0), at(0.53, 1), at(0.47, 1)]); ctx.fillStyle = rgba(p.accent, 0.92); ctx.fill();
    const k = clamp((t - T.check) / 0.35);
    if (k > 0) {
      const e = E.backOut(k, 1.6), c = at(0.5, 0.55), rx = 52 * c[2] * e;
      ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.ellipse(c[0], c[1], rx * 1.12, rx * 0.72, -0.2, 0, TAU); ctx.fill();
      ctx.fillStyle = p.accent; ctx.beginPath(); ctx.ellipse(c[0], c[1], rx, rx * 0.62, -0.2, 0, TAU); ctx.fill();
      const dk = E.cubicOut(clamp((t - T.check - 0.12) / 0.25));
      if (dk > 0) {
        const sc = c[2], pts = [[c[0] - 20 * sc, c[1] + 2 * sc], [c[0] - 6 * sc, c[1] + 12 * sc], [c[0] + 22 * sc, c[1] - 12 * sc]];
        const l1 = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]), l2 = Math.hypot(pts[2][0] - pts[1][0], pts[2][1] - pts[1][1]);
        const L = (l1 + l2) * dk;
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 7 * sc; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
        if (L <= l1) ctx.lineTo(lerp(pts[0][0], pts[1][0], L / l1), lerp(pts[0][1], pts[1][1], L / l1));
        else { ctx.lineTo(pts[1][0], pts[1][1]); ctx.lineTo(lerp(pts[1][0], pts[2][0], (L - l1) / l2), lerp(pts[1][1], pts[2][1], (L - l1) / l2)); }
        ctx.stroke(); ctx.lineCap = 'butt';
      }
    }
  }
}

function drawBox(ctx, glow, t, T, p, env, inside) {
  const { w, d, h } = BOX;
  const P = v => P3(v[0], v[1], v[2]);
  // floor: contact shadow + soft penumbra toward the lower right (key from the upper left)
  const fc = [[-w / 2, 0, -d / 2], [w / 2, 0, -d / 2], [w / 2, 0, d / 2], [-w / 2, 0, d / 2]].map(P);
  ctx.save(); ctx.filter = 'blur(34px)'; ctx.fillStyle = 'rgba(38,50,70,0.30)';
  quad(ctx, fc.map(q => [q[0] + 60, q[1] + 30])); ctx.fill(); ctx.restore();
  ctx.save(); ctx.filter = 'blur(7px)'; ctx.fillStyle = 'rgba(30,40,56,0.42)'; quad(ctx, fc); ctx.fill(); ctx.restore();
  const ang = lidAngle(t, T), lid = lidBox(ang);
  const lidOpen = ang > Math.PI / 2;
  if (lidOpen) drawLid(ctx, lid, p, t, T);
  const W4 = walls();
  const rim = [[-w / 2, h, -d / 2], [w / 2, h, -d / 2], [w / 2, h, d / 2], [-w / 2, h, d / 2]].map(P);
  // interior through the opening: floor + inner faces of the walls that face away from the camera
  ctx.save(); quad(ctx, rim); ctx.clip();
  quad(ctx, [[-w / 2, 6, -d / 2], [w / 2, 6, -d / 2], [w / 2, 6, d / 2], [-w / 2, 6, d / 2]].map(P)); ctx.fillStyle = '#CDD3DA'; ctx.fill();
  for (const wl of W4) {
    if (facing(wl.n, wl.c)) continue;                                   // its inner face is the one we see
    const k = 0.84 + 0.14 * faceLight(wl.n.map(x => -x), 0);
    const q = wl.v.map(P);
    quad(ctx, q);
    const g = ctx.createLinearGradient(0, Math.min(q[0][1], q[1][1]), 0, Math.max(q[2][1], q[3][1]));
    g.addColorStop(0, tone('#F2F4F6', k)); g.addColorStop(1, tone('#B8C0CA', k));
    ctx.fillStyle = g; ctx.fill();
  }
  ctx.restore();
  if (inside) inside(ctx);                                               // pieces going in; the front walls hide them
  // outer faces toward the camera
  for (const wl of W4) {
    if (!facing(wl.n, wl.c)) continue;
    const k = 0.80 + 0.24 * (faceLight(wl.n, 0) );
    const q = wl.v.map(P);
    quad(ctx, q);
    const g = ctx.createLinearGradient(0, Math.min(q[0][1], q[1][1]), 0, Math.max(q[2][1], q[3][1]));
    g.addColorStop(0, tone('#FFFFFF', k * 1.02)); g.addColorStop(0.8, tone('#F1F3F5', k)); g.addColorStop(1, tone('#DDE2E8', k));
    ctx.fillStyle = g; ctx.fill();
    // cobalt band around the box
    const band = (y0, y1) => [[wl.v[0][0], y1, wl.v[0][2]], [wl.v[1][0], y1, wl.v[1][2]], [wl.v[1][0], y0, wl.v[1][2]], [wl.v[0][0], y0, wl.v[0][2]]].map(P);
    quad(ctx, band(h * 0.30, h * 0.36)); ctx.fillStyle = tone(p.accent, 0.72 + 0.36 * k); ctx.fill();
    // top edge catches the light
    ctx.strokeStyle = `rgba(255,255,255,${(0.5 + 0.5 * k).toFixed(3)})`; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); ctx.lineTo(q[1][0], q[1][1]); ctx.stroke();
  }
  // vertical corner edges
  ctx.strokeStyle = 'rgba(90,100,118,0.18)'; ctx.lineWidth = 1.2;
  for (const wl of W4) if (facing(wl.n, wl.c)) { const q = wl.v.map(P); ctx.beginPath(); ctx.moveTo(q[1][0], q[1][1]); ctx.lineTo(q[2][0], q[2][1]); ctx.stroke(); }
  if (!lidOpen) drawLid(ctx, lid, p, t, T);
  // the closing puff of air
  const s = t - T.closed;
  if (s > 0 && s < 0.55) {
    for (let k = 0; k < 16; k++) {
      const a = hash2(3, k), side = k % 2 ? 1 : -1;
      const q = P([side * (w / 2 + 30 + 220 * E.cubicOut(s / 0.55) * (0.4 + a)), h * (0.75 + 0.4 * a), (a - 0.5) * d * 1.2]);
      drawSprite(ctx, softDot('puff', '#FFFFFF'), q[0], q[1], (16 + 46 * s) * (0.6 + a), 0.38 * (1 - s / 0.55));
    }
  }
}

/* ------------------------------------------------------------------ generated pieces */
const CW = 300, CH = 190;
const CACHE = {};
function pieceSprite(k, p, tk) {
  const key = 'piece' + k + JSON.stringify(p.items[k]) + p.accent;
  if (CACHE[key]) return CACHE[key];
  const S = 2, c = mkCanvas(CW * S, CH * S), x = c.getContext('2d');
  x.scale(S, S);
  rrect(x, 0, 0, CW, CH, 26); x.fillStyle = '#FFFFFF'; x.fill();
  x.strokeStyle = 'rgba(20,30,50,0.08)'; x.lineWidth = 1.5; x.stroke();
  const [label, small] = p.items[k];
  if (k === 0) {                        // video: a small frame with a warm gradient scene + play mark
    x.save(); rrect(x, 16, 16, CW - 32, 112, 16); x.clip();
    const g = x.createLinearGradient(0, 16, 0, 128); g.addColorStop(0, '#FFB38A'); g.addColorStop(0.55, '#F28C6B'); g.addColorStop(1, '#5B4A9E');
    x.fillStyle = g; x.fillRect(16, 16, CW - 32, 112);
    x.fillStyle = 'rgba(255,240,210,0.95)'; x.beginPath(); x.arc(200, 70, 18, 0, TAU); x.fill();
    x.fillStyle = '#3E3470'; x.beginPath(); x.moveTo(16, 128); x.lineTo(90, 72); x.lineTo(140, 108); x.lineTo(190, 80); x.lineTo(CW - 16, 128); x.closePath(); x.fill();
    x.restore();
    x.fillStyle = 'rgba(255,255,255,0.92)'; x.beginPath(); x.arc(CW / 2, 72, 22, 0, TAU); x.fill();
    x.fillStyle = p.accent; x.beginPath(); x.moveTo(CW / 2 - 7, 60); x.lineTo(CW / 2 + 11, 72); x.lineTo(CW / 2 - 7, 84); x.closePath(); x.fill();
  } else if (k === 1) {                 // captions: three text lines with one highlighted word
    const rows = [[24, 196], [24, 150], [24, 212]];
    rows.forEach(([x0, w], r) => {
      rrect(x, x0, 30 + r * 30, w, 14, 7); x.fillStyle = r === 1 ? rgba(p.accent, 0.9) : '#D9DEE6'; x.fill();
      if (r === 1) { rrect(x, x0 + w + 10, 30 + r * 30, 70, 14, 7); x.fillStyle = '#D9DEE6'; x.fill(); }
    });
  } else {                              // sound: waveform bars
    for (let i = 0; i < 26; i++) {
      const hgt = 10 + 80 * Math.pow(Math.abs(Math.sin(i * 0.61) * Math.cos(i * 0.23)), 0.7) * (0.5 + 0.5 * hash2(8, i));
      rrect(x, 26 + i * 9.6, 76 - hgt / 2, 5.4, hgt, 2.7); x.fillStyle = i % 5 === 2 ? p.accent : rgba(p.accent, 0.45); x.fill();
    }
  }
  x.font = tokFont(tk, 'sans', 26, 700); x.fillStyle = '#1F2430'; x.textBaseline = 'alphabetic'; x.fillText(label, 22, CH - 22);
  x.font = tokFont(tk, 'sans', 20, 500); x.fillStyle = '#8A93A3';
  const lw = layoutChars(label, tokFont(tk, 'sans', 26, 700)).width;
  x.fillText(small, 22 + lw + 14, CH - 23);
  CACHE[key] = c;
  return c;
}
function pieceHome(k) { return [540 + (k - 1) * 318, 860]; }        // where they materialise

function piecePose(k, t, T, p) {
  const [hx, hy] = pieceHome(k);
  const tg = T.gen[k], tl = T.launch[k], td = T.land[k];
  if (t < tg) return null;
  if (t < tl) {
    const a = E.cubicOut(clamp((t - tg) / 0.3));
    return { x: hx, y: hy + 20 * (1 - a), s: 1, r: 0, a, reveal: a, inBox: false };
  }
  // flight: an arc up and over, down into the box; shrinks toward the box depth
  const u = clamp((t - tl) / (td - tl));
  const e = E.cubicInOut(u);
  const dst = P3((k - 1) * 165, BOX.h * 0.66 + (k === 1 ? 18 : 0), -BOX.d * 0.2 + (k - 1) * 12);   // standing inside, tops above the rim
  const x = lerp(hx, dst[0], e);
  const y = lerp(hy, dst[1], e) - Math.sin(Math.PI * Math.min(1, e * 1.15)) * 150;
  const s = lerp(1, 0.5 * dst[2], E.cubicIn(u) * 0.7 + e * 0.3);
  const r = (k - 1) * 0.25 * Math.sin(Math.PI * u) + (k - 1) * 0.12 * e;
  return { x, y, s, r, a: 1, reveal: 1, inBox: u > 0.55, u };      // switch while clear of the front wall
}

/* ------------------------------------------------------------------ input bar */
function drawBar(ctx, glow, t, T, p, tk, env) {
  const s = env.s, W = env.W;
  const bw = 900 * s, bh = 150 * s, bx = (W - bw) / 2, by = 360 * s;
  const appear = E.cubicOut(seg(t, 0, 0.35));
  const press = t >= T.enter ? springKick(t - T.enter, 5, 0.5) * 0.02 : 0;
  ctx.save();
  ctx.translate(W / 2, by + bh / 2); ctx.scale(1 - press, 1 - press); ctx.translate(-W / 2, -(by + bh / 2) - 20 * (1 - appear));
  ctx.globalAlpha = appear;
  // soft shadow
  ctx.save(); ctx.filter = 'blur(30px)'; ctx.fillStyle = 'rgba(40,60,90,0.18)'; rrect(ctx, bx + 20, by + 34, bw - 40, bh, bh / 2); ctx.fill(); ctx.restore();
  rrect(ctx, bx, by, bw, bh, bh / 2); ctx.fillStyle = '#FFFFFF'; ctx.fill();
  const typedAll = t >= T.keys[T.n - 1];
  ctx.strokeStyle = t < T.enter && t > T.keys[0] - 0.2 ? rgba(p.accent, 0.35) : 'rgba(20,30,50,0.08)'; ctx.lineWidth = 2 * s; ctx.stroke();
  // left "+" glyph
  ctx.strokeStyle = '#9AA3B2'; ctx.lineWidth = 3.2 * s; ctx.lineCap = 'round';
  const px = bx + 70 * s, py = by + bh / 2;
  ctx.beginPath(); ctx.moveTo(px - 14 * s, py); ctx.lineTo(px + 14 * s, py); ctx.moveTo(px, py - 14 * s); ctx.lineTo(px, py + 14 * s); ctx.stroke();
  // typed text / hint
  const font = tokFont(tk, 'sans', 46 * s, 500);
  const chars = [...p.text];
  let shown = 0; for (let i = 0; i < T.n; i++) if (t >= T.keys[i]) shown = i + 1;
  const tx = bx + 124 * s, base = py + 16 * s;
  ctx.font = font; ctx.textBaseline = 'alphabetic';
  const sent = E.cubicInOut(seg(t, T.enter + 0.05, T.enter + 0.45));
  if (shown === 0) { ctx.fillStyle = '#A7AFBC'; ctx.fillText(p.hint, tx, base); }
  const Lc = layoutChars(p.text, font);
  for (let i = 0; i < shown; i++) {
    const age = t - T.keys[i], e = E.expoOut(clamp(age / 0.12));
    ctx.globalAlpha = appear * e * (1 - 0.55 * sent);
    ctx.fillStyle = '#1F2430';
    ctx.fillText(chars[i], tx + Lc.chars[i].x, base + 6 * s * (1 - e));
  }
  ctx.globalAlpha = appear;
  // caret
  const cx = tx + (shown ? Lc.chars[shown - 1].x + Lc.chars[shown - 1].w : 0) + 4 * s;
  const typing = t > T.keys[0] - 0.05 && t < T.keys[T.n - 1] + 0.05;
  const blink = typing ? 1 : (Math.floor((t + 0.05) / 0.5) % 2 === 0 ? 1 : 0);
  if (t < T.enter) { ctx.fillStyle = rgba(p.accent, blink); ctx.fillRect(cx, py - 30 * s, 4 * s, 60 * s); }
  // send button
  const sb = bx + bw - 76 * s, r = 50 * s;
  const act = typedAll ? 1 : 0;
  const bp = t >= T.enter ? 1 - 0.12 * Math.exp(-(t - T.enter) / 0.08) : 1;
  ctx.fillStyle = act ? p.accent : '#D5DAE2';
  ctx.beginPath(); ctx.arc(sb, py, r * bp, 0, TAU); ctx.fill();
  ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 6 * s; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(sb, py + 18 * s * bp); ctx.lineTo(sb, py - 18 * s * bp); ctx.moveTo(sb - 15 * s * bp, py - 4 * s * bp); ctx.lineTo(sb, py - 19 * s * bp); ctx.lineTo(sb + 15 * s * bp, py - 4 * s * bp); ctx.stroke();
  if (t >= T.enter && t < T.enter + 0.5 && glow) {       // press ring
    const u = (t - T.enter) / 0.5;
    ctx.strokeStyle = rgba(p.accent, 0.5 * (1 - u)); ctx.lineWidth = 3 * s;
    ctx.beginPath(); ctx.arc(sb, py, r * (1 + 0.9 * E.cubicOut(u)), 0, TAU); ctx.stroke();
  }
  // "working" shimmer along the bar after Enter
  const wk = seg(t, T.enter + 0.05, T.gen[2] + 0.3);
  if (wk > 0 && wk < 1) {
    ctx.save(); rrect(ctx, bx, by, bw, bh, bh / 2); ctx.clip();
    const sx = lerp(bx - 200 * s, bx + bw + 200 * s, E.sineInOut(wk));
    const g = ctx.createLinearGradient(sx - 160 * s, 0, sx + 160 * s, 0);
    g.addColorStop(0, rgba(p.accent, 0)); g.addColorStop(0.5, rgba(p.accent, 0.12)); g.addColorStop(1, rgba(p.accent, 0));
    ctx.fillStyle = g; ctx.fillRect(bx, by, bw, bh); ctx.restore();
  }
  ctx.restore(); ctx.globalAlpha = 1; ctx.lineCap = 'butt';
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  const T = timing(p);
  if (t >= T.launch[0] - 0.05 && t < T.land[2] + 0.05) return 10;
  if (t >= T.close0 - 0.02 && t < T.closed + 0.25) return 8;
  return 2;
}
export function post(t) { return { fade: smooth(seg(t, 0, 0.2)) }; }

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, T = timing(p), glow = env.glow;
  // studio: cool paper sweep, a soft top light, horizon where the floor meets the wall
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#EEF1F5'); g.addColorStop(0.55, '#E3E8EE'); g.addColorStop(0.62, '#DCE2E9'); g.addColorStop(1, '#CDD4DD');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const lg = ctx.createRadialGradient(W * 0.5, H * 0.18, 20, W * 0.5, H * 0.35, H * 0.7);
  lg.addColorStop(0, 'rgba(255,255,255,0.85)'); lg.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = lg; ctx.fillRect(0, 0, W, H);
  // camera: slow drift + a small settle when the lid shuts
  const z = 1 + 0.03 * E.sineInOut(seg(t, 0, env.dur)) + springKick(t - T.closed, 7, 0.4) * 0.006;
  ctx.save(); ctx.translate(W / 2, H * 0.5); ctx.scale(z, z); ctx.translate(-W / 2, -H * 0.5);
  if (glow) { glow.save(); glow.translate(W / 2, H * 0.5); glow.scale(z, z); glow.translate(-W / 2, -H * 0.5); }
  drawBar(ctx, glow, t, T, p, tk, env);
  // pieces: those in the air draw over the box; those inside are clipped by its opening
  const poses = [0, 1, 2].map(k => piecePose(k, t, T, p));
  const drawPiece = (c2, k, q) => {
    const sp = pieceSprite(k, p, tk);
    c2.save(); c2.translate(q.x, q.y); c2.rotate(q.r); c2.scale(q.s, q.s);
    c2.globalAlpha = q.a;
    if (!q.inBox) { c2.save(); c2.filter = 'blur(18px)'; c2.fillStyle = 'rgba(40,60,90,0.22)'; rrect(c2, -CW / 2 + 10, -CH / 2 + 26, CW - 20, CH, 26); c2.fill(); c2.restore(); }
    if (q.reveal < 1) { c2.beginPath(); c2.rect(-CW / 2 - 4, -CH / 2 - 4, CW + 8, (CH + 8) * q.reveal); c2.clip(); }
    c2.drawImage(sp, -CW / 2, -CH / 2, CW, CH);
    if (q.reveal < 1) { c2.fillStyle = rgba(p.accent, 0.8); c2.fillRect(-CW / 2, -CH / 2 + CH * q.reveal - 2, CW, 3); }
    c2.restore(); c2.globalAlpha = 1;
  };
  drawBox(ctx, glow, t, T, p, env, c2 => { poses.forEach((q, k) => { if (q && q.inBox) drawPiece(c2, k, q); }); });
  poses.forEach((q, k) => { if (q && !q.inBox) drawPiece(ctx, k, q); });
  // generation sparkle
  if (glow) for (let k = 0; k < 3; k++) {
    const s2 = t - T.gen[k];
    if (s2 > 0 && s2 < 0.45) { const [hx, hy] = pieceHome(k); drawSprite(glow, softDot('g', p.accent), hx, hy, 170, 0.35 * (1 - s2 / 0.45)); }
  }
  if (glow) glow.restore();
  ctx.restore();
}

export function bbox(t, p, tk, env) {
  return [{ kind: 'text', label: p.text, x: 90 * env.s, y: 360 * env.s, w: 900 * env.s, h: 150 * env.s, font_px: 46 * env.s }];
}
