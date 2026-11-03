/* ==========================================================================
   movable_type — 活字印刷标题卡
   Metal type sorts rise out of the dark, tumble, fall into a steel composing
   rail one by one in reading order and lock up; a light sweeps across the
   polished faces and a small caption focuses in underneath.

   Look: a letterpress bench at night — raking tungsten key from the upper
   left, cool rim from behind, dust in the beam, an out-of-focus type case in
   the background. Every sort is a lit 3-D block (perspective camera,
   back-face culling, Blinn-Phong on every face); the glyph sits on the FRONT
   face, drawn through the face's own projected corners, so it always reads
   left-to-right and upright (never mirrored), and the slots fill left to
   right in reading order.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, spring, springKick, hash2, rgba, softDot, drawSprite, tokFont, mkCanvas } from '../engine/core.js';
import { layoutChars, inkBox } from '../engine/text.js';
import { dust } from '../engine/particles.js';

export const id = 'movable_type';
export const role = 'card';
export const desc = '活字印刷标题卡：金属活字从暗处升起、翻转、按阅读顺序落进排字槽并锁版，光扫过字面，副标题聚焦出现。全屏不透明。';
export const sfx_hints = [{ id: 'type_clink', at: 'each landing' }, { id: 'type_lock', at: 'lock' }];

export const params = {
  text: { default: '开源镜头库', type: 'string', desc: '标题（2–7 字）。每个字一块活字，从左到右依次落位。' },
  sub: { default: 'OPEN SOURCE · MOTION LIBRARY', type: 'string', desc: '副标题（小字，锁版后出现）。' },
  label: { default: 'LETTERPRESS', type: 'string', desc: '左上角的小标签，留空不显示。' },
  y: { default: 0.45, type: 'number', desc: '活字字面中心的垂直位置（画面高比例）。' },
  t0: { default: 0.15, type: 'number', desc: '第一块活字起飞时间（秒）。' },
  stagger: { default: 0.12, type: 'number', desc: '相邻两块起飞间隔（秒）。' },
  rise: { default: 0.62, type: 'number', desc: '上升到最高点用时（秒）。' },
  fall: { default: 0.27, type: 'number', desc: '从最高点落进槽用时（秒）。' },
  lock_gap: { default: 0.34, type: 'number', desc: '最后一块落位到锁版的间隔（秒）。' },
  metal: { default: '#7A6F66', type: 'color', desc: '铅字金属本色。' },
  glyph: { default: '#F2E6D6', type: 'color', desc: '抛光字面高光色。' },
  key: { default: '#FFB870', type: 'color', desc: '主光（钨丝灯）颜色。' },
  rim: { default: '#7FA6C9', type: 'color', desc: '逆光轮廓色。' },
  bg: { default: '#0C0A08', type: 'color', desc: '背景底色。' },
};

/* ------------------------------------------------------------------ timing */
export function timing(p) {
  const n = [...p.text].length;
  const launch = [], land = [];
  for (let i = 0; i < n; i++) { launch.push(p.t0 + i * p.stagger); land.push(p.t0 + i * p.stagger + p.rise + p.fall); }
  const lock = land[n - 1] + p.lock_gap;
  return { n, launch, land, lock, sweep: lock + 0.22, sub: lock + 0.55 };
}

/* ------------------------------------------------------------------ 3-D */
const CAM = { F: 2600, D: 2600 };
function proj(P, cam) {
  const s = CAM.F / (CAM.D - P[2]);
  return [cam.cx + (P[0] - cam.x) * s * cam.z, cam.cy + (P[1] - cam.y) * s * cam.z, s];
}
function rotX(p, c, a) {            // rotate p about the X axis through c
  const y = p[1] - c[1], z = p[2] - c[2], ca = Math.cos(a), sa = Math.sin(a);
  return [p[0], c[1] + y * ca - z * sa, c[2] + y * sa + z * ca];
}
function rotZ(p, c, a) {
  const x = p[0] - c[0], y = p[1] - c[1], ca = Math.cos(a), sa = Math.sin(a);
  return [c[0] + x * ca - y * sa, c[1] + x * sa + y * ca, p[2]];
}
const norm3 = v => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
// light directions (from surface toward the light; screen y points down)
const KEY = norm3([-0.55, -0.75, 0.62]);
const RIM = norm3([0.35, -0.55, -0.75]);
const VIEW = [0, 0, 1];
const HALF = norm3([KEY[0] + VIEW[0], KEY[1] + VIEW[1], KEY[2] + VIEW[2]]);

/* ------------------------------------------------------------------ sprites (built once per font/size) */
const CACHE = {};
function glyphSprite(ch, font, px, col) {
  const k = ch + '|' + font + '|' + px + '|' + col;
  if (CACHE[k]) return CACHE[k];
  const S = Math.ceil(px), c = mkCanvas(S, S), x = c.getContext('2d');
  const ib = inkBox(ch, font);
  const gx = S / 2 - (ib.l + ib.r) / 2, gy = S / 2 - (ib.t + ib.b) / 2;   // centre the INK, not the advance box
  x.font = font; x.textBaseline = 'alphabetic';
  const lay = (dx, dy, fill, op = 'source-over', blur = 0) => {
    x.globalCompositeOperation = op; x.filter = blur ? `blur(${blur}px)` : 'none';
    x.fillStyle = fill; x.fillText(ch, gx + dx, gy + dy);
  };
  // 1) relief shadow cast down-right onto the recessed field
  lay(S * 0.012, S * 0.02, 'rgba(0,0,0,0.85)', 'source-over', S * 0.008);
  // 2) glyph shoulder (darker metal, 1 px larger feel)
  lay(0, 0, '#5B524A');
  // 3) polished face: vertical gradient, warm top
  const g = x.createLinearGradient(0, gy + ib.t, 0, gy + ib.b);
  g.addColorStop(0, col); g.addColorStop(0.55, '#C9BBAA'); g.addColorStop(1, '#8E8174');
  x.globalCompositeOperation = 'source-over'; x.filter = 'none'; x.fillStyle = g;
  x.fillText(ch, gx - S * 0.004, gy - S * 0.006);
  // 4) bevel: bright rim on the up-left edges, dark rim on the down-right edges (clipped to the glyph)
  const rimC = mkCanvas(S, S), r = rimC.getContext('2d');
  r.font = font; r.textBaseline = 'alphabetic';
  r.fillStyle = '#FFF6E8'; r.fillText(ch, gx - S * 0.004, gy - S * 0.006);
  r.globalCompositeOperation = 'destination-out'; r.fillText(ch, gx + S * 0.006, gy + S * 0.008);
  x.globalCompositeOperation = 'source-over'; x.globalAlpha = 0.9; x.drawImage(rimC, 0, 0); x.globalAlpha = 1;
  const shC = mkCanvas(S, S), s2 = shC.getContext('2d');
  s2.font = font; s2.textBaseline = 'alphabetic';
  s2.fillStyle = '#2A231D'; s2.fillText(ch, gx - S * 0.004, gy - S * 0.006);
  s2.globalCompositeOperation = 'destination-out'; s2.fillText(ch, gx - S * 0.012, gy - S * 0.016);
  x.globalAlpha = 0.75; x.drawImage(shC, 0, 0); x.globalAlpha = 1;
  // 5) glyph-only mask (for the specular sweep)
  const m = mkCanvas(S, S), mx = m.getContext('2d');
  mx.font = font; mx.textBaseline = 'alphabetic'; mx.fillStyle = '#fff'; mx.fillText(ch, gx - S * 0.004, gy - S * 0.006);
  CACHE[k] = { c, m, S };
  return CACHE[k];
}
/* face field texture: dark oxidised metal with fine machining lines */
function fieldSprite(S, seed) {
  const k = 'field|' + S + '|' + seed;
  if (CACHE[k]) return CACHE[k];
  const c = mkCanvas(S, S), x = c.getContext('2d');
  const g = x.createLinearGradient(0, 0, S, S);
  g.addColorStop(0, '#3A332D'); g.addColorStop(1, '#1E1A17');
  x.fillStyle = g; x.fillRect(0, 0, S, S);
  for (let i = 0; i < S; i += 2) {
    const a = 0.035 + 0.05 * hash2(seed, i);
    x.fillStyle = `rgba(255,236,210,${a})`; x.fillRect(0, i, S, 1);
  }
  for (let i = 0; i < 60; i++) {           // pits
    const px = hash2(seed + 7, i) * S, py = hash2(seed + 9, i) * S;
    x.fillStyle = `rgba(0,0,0,${0.18 + 0.2 * hash2(seed + 11, i)})`; x.fillRect(px, py, 1.5, 1.5);
  }
  CACHE[k] = c;
  return c;
}
/* out-of-focus type case: a tray of compartments receding away from camera, heavily defocused */
function caseSprite(W, H) {
  const k = 'case|' + W + '|' + H;
  if (CACHE[k]) return CACHE[k];
  const c = mkCanvas(W, H), x = c.getContext('2d');
  x.filter = 'blur(16px)';
  const rows = 7, vy = H * 0.60;                       // horizon of the tray
  for (let r = rows - 1; r >= 0; r--) {
    const z0 = r / rows, z1 = (r + 1) / rows;          // 0 = near (bottom), 1 = far
    const y0 = lerp(H * 1.05, vy, Math.pow(z0, 0.7)), y1 = lerp(H * 1.05, vy, Math.pow(z1, 0.7));
    const sc0 = lerp(1.9, 0.9, z0), sc1 = lerp(1.9, 0.9, z1);
    const cols = 6;
    for (let q = 0; q < cols; q++) {
      const u0 = (q / cols - 0.5), u1 = ((q + 1) / cols - 0.5);
      const xa = W / 2 + u0 * W * sc0, xb = W / 2 + u1 * W * sc0, xc = W / 2 + u1 * W * sc1, xd = W / 2 + u0 * W * sc1;
      const fade = 0.35 + 0.65 * (1 - z0);
      x.fillStyle = `rgba(70,44,26,${0.5 * fade})`;
      x.beginPath(); x.moveTo(xa, y0); x.lineTo(xb, y0); x.lineTo(xc, y1); x.lineTo(xd, y1); x.closePath(); x.fill();
      x.fillStyle = `rgba(10,7,5,${0.92})`;
      const ix = (a, b2, t2) => a + (b2 - a) * t2;
      x.beginPath(); x.moveTo(ix(xa, xb, 0.06), ix(y0, y1, 0.08)); x.lineTo(ix(xb, xa, 0.06), ix(y0, y1, 0.08));
      x.lineTo(ix(xc, xd, 0.06), ix(y1, y0, 0.1)); x.lineTo(ix(xd, xc, 0.06), ix(y1, y0, 0.1)); x.closePath(); x.fill();
      for (let s2 = 0; s2 < 7; s2++) {                 // glints of sorts lying in the compartment
        const a = hash2(r * 31 + q, s2), b2 = hash2(r * 17 + q, s2 + 40);
        const gx = ix(ix(xa, xb, 0.15 + 0.7 * a), ix(xd, xc, 0.15 + 0.7 * a), 0.2 + 0.6 * b2), gy = ix(y0, y1, 0.2 + 0.6 * b2);
        x.fillStyle = `rgba(255,196,128,${(0.10 + 0.30 * hash2(q, r * 9 + s2)) * fade})`;
        x.beginPath(); x.arc(gx, gy, 6 + 10 * (1 - z0), 0, TAU); x.fill();
      }
    }
  }
  CACHE[k] = c;
  return c;
}

/* ------------------------------------------------------------------ layout */
function layout(p, env) {
  const s = env.s, chars = [...p.text], n = chars.length;
  const S = Math.min(186, 900 / (n + (n - 1) * 0.07)) * s;          // face size
  const gap = S * 0.07, depth = S * 0.95;
  const total = n * S + (n - 1) * gap;
  const x0 = env.W / 2 - total / 2, yc = p.y * env.H;
  const spx = Math.round(S * 1.6);                                  // glyph sprite size (drawn down to S)
  const font = tokFont(env.tokens, 'serif', spx * 0.74 / 1.6, 900);
  const sfont = tokFont(env.tokens, 'serif', spx * 0.74, 900);
  return { chars, n, S, gap, depth, x0, yc, font, sfont, spx, total, s };
}

/* block pose at time t: centre (x,y,z) of the FRONT face, rotation angles */
function pose(i, t, p, L, T) {
  const xs = L.x0 + i * (L.S + L.gap) + L.S / 2;
  const ta = T.launch[i], tl = T.land[i];
  const lockShift = -6 * L.s * E.expoOut(seg(t, T.lock, T.lock + 0.12));
  if (t < ta) return null;
  if (t >= tl) {                                   // landed: tiny bounce, then locked up
    const b = springKick(t - tl, 7.5, 0.34) * 7 * L.s;
    return { x: xs + lockShift, y: L.yc - Math.max(0, b), z: 0, ax: 0, az: 0, v: 0, landed: true, air: 0 };
  }
  const apex = L.yc - (250 + 60 * hash2(i, 3)) * L.s;
  const y0 = L.yc + 1250 * L.s;
  const tp = ta + p.rise;
  let y, vy;
  if (t < tp) { const u = (t - ta) / p.rise, e = 1 - (1 - u) * (1 - u); y = lerp(y0, apex, e); vy = (apex - y0) * 2 * (1 - u) / p.rise; }
  else { const u = (t - tp) / p.fall; y = lerp(apex, L.yc, u * u); vy = (L.yc - apex) * 2 * u / p.fall; }
  const u = (t - ta) / (tl - ta);                  // 0..1 over the whole flight
  const turns = 1 + (i % 2);                       // full turns about X, always ending face-front
  const ax = -TAU * turns * E.cubicOut(u);
  const az = (hash2(i, 5) - 0.5) * 0.5 * (1 - E.cubicOut(u));
  const x = lerp(xs + (hash2(i, 9) - 0.5) * 260 * L.s, xs, E.cubicOut(u));
  const zs = (i % 2 ? 300 : -560) * L.s;             // odd sorts come from near the lens, even ones from deep
  const z = zs * (1 - E.cubicOut(Math.min(1, u * 1.25)));
  return { x, y, z, ax, az, v: Math.abs(vy), landed: false, air: 1 - u };
}

/* ------------------------------------------------------------------ drawing */
function camera(t, T, env) {
  const push = 1 + 0.045 * E.sineInOut(seg(t, 0, env.dur));
  let sx = 0, sy = 0;
  const hits = [...T.land.map(x => [x, 2.2]), [T.lock, 4]];
  for (const [t0, a] of hits) {
    const s = t - t0;
    if (s >= 0 && s < 0.3) { const e = a * Math.exp(-s / 0.06); sx += e * Math.sin(TAU * 19 * s + t0); sy += e * Math.sin(TAU * 23 * s + 1.3 + t0); }
  }
  return { x: env.W / 2, y: env.H * 0.39, cx: env.W / 2 + sx, cy: env.H * 0.39 + sy, z: push };
}

function shade(n, base, amb = 0.16) {
  const d = Math.max(0, dot3(n, KEY)), sp = Math.pow(Math.max(0, dot3(n, HALF)), 38), rm = Math.pow(Math.max(0, dot3(n, RIM)), 3);
  return { d, sp, rm, k: amb + 0.95 * d };
}

function drawBlock(ctx, glow, b, L, p, cam, sweepX, t) {
  const S = L.S, dp = L.depth;
  const c = [b.x, b.y, b.z - dp / 2];
  const hx = S / 2, hy = S / 2;
  // cuboid corners: front face z = b.z, back face z = b.z - dp
  const raw = [
    [b.x - hx, b.y - hy, b.z], [b.x + hx, b.y - hy, b.z], [b.x + hx, b.y + hy, b.z], [b.x - hx, b.y + hy, b.z],
    [b.x - hx, b.y - hy, b.z - dp], [b.x + hx, b.y - hy, b.z - dp], [b.x + hx, b.y + hy, b.z - dp], [b.x - hx, b.y + hy, b.z - dp],
  ].map(P => rotZ(rotX(P, c, b.ax), c, b.az));
  const pr = raw.map(P => proj(P, cam));
  const faces = [
    { id: 'front', v: [0, 1, 2, 3] }, { id: 'back', v: [5, 4, 7, 6] }, { id: 'top', v: [4, 5, 1, 0] },
    { id: 'bottom', v: [3, 2, 6, 7] }, { id: 'left', v: [4, 0, 3, 7] }, { id: 'right', v: [1, 5, 6, 2] },
  ];
  const camP = [cam.x, cam.y, CAM.D];
  const vis = [];
  for (const f of faces) {
    const A = raw[f.v[0]], B = raw[f.v[1]], C = raw[f.v[3]];
    const nrm = norm3(cross(sub3(B, A), sub3(C, A)));
    const ctr = f.v.reduce((a, k) => [a[0] + raw[k][0] / 4, a[1] + raw[k][1] / 4, a[2] + raw[k][2] / 4], [0, 0, 0]);
    const out = nrm;                                // the face windings above give outward normals
    if (dot3(out, sub3(camP, ctr)) <= 0) continue;
    vis.push({ ...f, n: out, ctr });
  }
  vis.sort((a, b2) => a.ctr[2] - b2.ctr[2]);
  for (const f of vis) {
    const q = f.v.map(k => pr[k]);
    const sh = shade(f.n);
    ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); for (let k = 1; k < 4; k++) ctx.lineTo(q[k][0], q[k][1]); ctx.closePath();
    if (f.id === 'front') {
      // field texture through the face's projected corners (affine: TL, TR, BL)
      const [tl, tr, , bl] = q;
      const fs = fieldSprite(128, 7);
      ctx.save(); ctx.clip();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.transform((tr[0] - tl[0]) / 128, (tr[1] - tl[1]) / 128, (bl[0] - tl[0]) / 128, (bl[1] - tl[1]) / 128, tl[0], tl[1]);
      ctx.drawImage(fs, 0, 0);
      ctx.restore();
      ctx.fillStyle = `rgba(0,0,0,${clamp(0.55 - sh.k * 0.5)})`; ctx.fill();
      ctx.fillStyle = rgba(p.key, 0.10 * sh.d); ctx.fill();
      // glyph (upright, left-to-right: mapped through TL->TR and TL->BL)
      const gs = glyphSprite(b.ch, L.sfont, L.spx, p.glyph);
      ctx.save();
      ctx.transform((tr[0] - tl[0]) / gs.S, (tr[1] - tl[1]) / gs.S, (bl[0] - tl[0]) / gs.S, (bl[1] - tl[1]) / gs.S, tl[0], tl[1]);
      ctx.globalAlpha = clamp(0.35 + 0.75 * sh.k);
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(gs.c, 0, 0);
      // specular sweep over the polished glyph only
      if (sweepX !== null) {
        const faceX0 = (tl[0] + bl[0]) / 2, faceX1 = (tr[0] + (q[2][0])) / 2;
        const u = (sweepX - faceX0) / Math.max(1, faceX1 - faceX0);
        if (u > -0.6 && u < 1.6) {
          const band = mkBand(gs, u);
          ctx.globalAlpha = 0.95; ctx.globalCompositeOperation = 'lighter'; ctx.drawImage(band, 0, 0);
          ctx.globalCompositeOperation = 'source-over';
          if (glow) {
            glow.save(); glow.transform((tr[0] - tl[0]) / gs.S, (tr[1] - tl[1]) / gs.S, (bl[0] - tl[0]) / gs.S, (bl[1] - tl[1]) / gs.S, tl[0], tl[1]);
            glow.globalAlpha = 0.8; glow.drawImage(band, 0, 0); glow.restore();
          }
        }
      }
      ctx.restore();
      // chamfer highlight on the top edge, dark on the bottom edge
      ctx.lineWidth = 1.6 * L.s;
      ctx.strokeStyle = rgba('#FFE7C8', 0.25 + 0.5 * sh.sp + 0.25 * sh.d);
      ctx.beginPath(); ctx.moveTo(tl[0], tl[1]); ctx.lineTo(tr[0], tr[1]); ctx.stroke();
      ctx.strokeStyle = rgba('#FFE7C8', 0.12 + 0.3 * sh.d);
      ctx.beginPath(); ctx.moveTo(tl[0], tl[1]); ctx.lineTo(bl[0], bl[1]); ctx.stroke();
      ctx.strokeStyle = 'rgba(0,0,0,0.55)';
      ctx.beginPath(); ctx.moveTo(bl[0], bl[1]); ctx.lineTo(q[2][0], q[2][1]); ctx.lineTo(tr[0], tr[1]); ctx.stroke();
    } else {
      // body faces: dark lead alloy; brightness from the key, a soft-box reflection stripe that slides with
      // the face normal, a hot specular, a cool rim from behind
      const base = hexMul(p.metal, 0.10 + 0.62 * sh.k);
      const g = ctx.createLinearGradient(q[0][0], q[0][1], q[2][0], q[2][1]);
      g.addColorStop(0, rgbS(base, 1.18)); g.addColorStop(1, rgbS(base, 0.62));
      ctx.fillStyle = g; ctx.fill();
      const env = clamp(0.5 + 0.5 * (-f.n[1] * 0.8 - f.n[0] * 0.4));            // faces turned up/left see the soft box
      const sp0 = clamp(env * 1.4 - 0.25), sx = lerp(0.15, 0.85, env);
      if (sp0 > 0.02) {
        const eg = ctx.createLinearGradient(lerp(q[0][0], q[1][0], sx - 0.22), lerp(q[0][1], q[1][1], sx - 0.22), lerp(q[0][0], q[1][0], sx + 0.22), lerp(q[0][1], q[1][1], sx + 0.22));
        eg.addColorStop(0, 'rgba(255,226,190,0)'); eg.addColorStop(0.5, rgba('#FFE6C6', 0.38 * sp0)); eg.addColorStop(1, 'rgba(255,226,190,0)');
        ctx.fillStyle = eg; ctx.fill();
      }
      if (sh.sp > 0.02) { ctx.fillStyle = rgba('#FFE9CF', 0.85 * sh.sp); ctx.fill(); }
      if (sh.rm > 0.02) { ctx.fillStyle = rgba(p.rim, 0.45 * sh.rm); ctx.fill(); }
      ctx.lineWidth = 1.4 * L.s;
      ctx.strokeStyle = rgba('#FFE3C2', 0.12 + 0.55 * sh.d * env);
      ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); ctx.lineTo(q[1][0], q[1][1]); ctx.stroke();
      if (f.id === 'bottom' || f.id === 'left' || f.id === 'right') {       // the nick (groove) on the body
        const m0 = [(q[0][0] + q[3][0]) / 2, (q[0][1] + q[3][1]) / 2], m1 = [(q[1][0] + q[2][0]) / 2, (q[1][1] + q[2][1]) / 2];
        ctx.strokeStyle = 'rgba(0,0,0,0.35)'; ctx.lineWidth = 3 * L.s;
        ctx.beginPath(); ctx.moveTo(lerp(m0[0], q[0][0], 0.35), lerp(m0[1], q[0][1], 0.35)); ctx.lineTo(lerp(m1[0], q[1][0], 0.35), lerp(m1[1], q[1][1], 0.35)); ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(255,230,200,0.10)'; ctx.lineWidth = 1; ctx.stroke();
    }
  }
  return pr;
}
const _band = {};
function mkBand(gs, u) {
  const k = gs.S;
  if (!_band[k]) _band[k] = { c: mkCanvas(gs.S, gs.S) };
  const c = _band[k].c, x = c.getContext('2d');
  x.globalCompositeOperation = 'source-over'; x.clearRect(0, 0, gs.S, gs.S);
  const cx = u * gs.S, w = gs.S * 0.28;
  const g = x.createLinearGradient(cx - w, 0, cx + w, gs.S * 0.25);
  g.addColorStop(0, 'rgba(255,240,215,0)'); g.addColorStop(0.5, 'rgba(255,244,226,0.95)'); g.addColorStop(1, 'rgba(255,240,215,0)');
  x.fillStyle = g; x.fillRect(0, 0, gs.S, gs.S);
  x.globalCompositeOperation = 'destination-in'; x.drawImage(gs.m, 0, 0);
  return c;
}
function hexMul(h, k) { const c = [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; return c.map(v => v * k); }
function rgbS(c, k) { return `rgb(${Math.min(255, c[0] * k) | 0},${Math.min(255, c[1] * k) | 0},${Math.min(255, c[2] * k) | 0})`; }

function drawRail(ctx, glow, L, cam, t, T, p) {
  // steel composing rail under the row: top face (depth) + front face
  const y = L.yc + L.S / 2, pad = 70 * L.s, x0 = L.x0 - pad, x1 = L.x0 + L.total + pad;
  const zF = 30 * L.s, zB = -L.depth - 40 * L.s, hF = 26 * L.s;
  const P = (x, yy, z) => proj([x, yy, z], cam);
  const a = P(x0, y, zB), b = P(x1, y, zB), c = P(x1, y, zF), d = P(x0, y, zF);
  ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.lineTo(d[0], d[1]); ctx.closePath();
  const g = ctx.createLinearGradient(0, a[1], 0, c[1]);
  g.addColorStop(0, '#15110E'); g.addColorStop(0.7, '#3B332C'); g.addColorStop(1, '#6B5F54');
  ctx.fillStyle = g; ctx.fill();
  const e = P(x1, y + hF, zF), f = P(x0, y + hF, zF);
  ctx.beginPath(); ctx.moveTo(d[0], d[1]); ctx.lineTo(c[0], c[1]); ctx.lineTo(e[0], e[1]); ctx.lineTo(f[0], f[1]); ctx.closePath();
  const g2 = ctx.createLinearGradient(d[0], 0, c[0], 0);
  g2.addColorStop(0, '#5E534A'); g2.addColorStop(0.3, '#A29384'); g2.addColorStop(0.42, '#E9D8C3'); g2.addColorStop(0.55, '#8A7C6F'); g2.addColorStop(1, '#3A322C');
  ctx.fillStyle = g2; ctx.fill();
  ctx.strokeStyle = 'rgba(255,226,190,0.55)'; ctx.lineWidth = 1.2 * L.s;
  ctx.beginPath(); ctx.moveTo(d[0], d[1]); ctx.lineTo(c[0], c[1]); ctx.stroke();
  if (glow) { glow.strokeStyle = 'rgba(255,200,140,0.35)'; glow.lineWidth = 3 * L.s; glow.beginPath(); glow.moveTo(lerp(d[0], c[0], 0.3), d[1]); glow.lineTo(lerp(d[0], c[0], 0.55), c[1]); glow.stroke(); }
  // left head stop + the quoin (steel wedge) that locks the row from the right
  const hs0 = P(x0 - 26 * L.s, y - L.S * 0.55, 0), hs1 = P(x0 + 4 * L.s, y, 0);
  ctx.fillStyle = '#4A4038'; ctx.fillRect(hs0[0], hs0[1], hs1[0] - hs0[0], hs1[1] - hs0[1]);
  ctx.fillStyle = 'rgba(255,220,180,0.35)'; ctx.fillRect(hs0[0], hs0[1], hs1[0] - hs0[0], 2 * L.s);
  const qin = E.expoOut(seg(t, T.lock - 0.16, T.lock));
  const qx = lerp(x1 + 120 * L.s, L.x0 + L.total + 2 * L.s - 6 * L.s * E.expoOut(seg(t, T.lock, T.lock + 0.12)), qin);
  const q0 = P(qx, y - L.S * 0.62, 0), q1 = P(qx + 40 * L.s, y, 0);
  const gq = ctx.createLinearGradient(q0[0], 0, q1[0], 0);
  gq.addColorStop(0, '#6E6257'); gq.addColorStop(0.35, '#3E3630'); gq.addColorStop(1, '#1C1815');
  ctx.fillStyle = gq;
  ctx.beginPath(); ctx.moveTo(q0[0], q0[1] + 14 * L.s); ctx.lineTo(q1[0], q0[1]); ctx.lineTo(q1[0], q1[1]); ctx.lineTo(q0[0], q1[1]); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = 'rgba(255,222,184,0.45)'; ctx.lineWidth = 1.2 * L.s;
  ctx.beginPath(); ctx.moveTo(q0[0], q0[1] + 14 * L.s); ctx.lineTo(q1[0], q0[1]); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,222,184,0.18)';
  ctx.beginPath(); ctx.moveTo(q0[0] + 1, q0[1] + 14 * L.s); ctx.lineTo(q0[0] + 1, q1[1]); ctx.stroke();
  return { y, x0, x1 };
}

function drawBackground(ctx, glow, t, env, L, p, cam) {
  const { W, H } = env;
  ctx.fillStyle = p.bg; ctx.fillRect(0, 0, W, H);
  // deep case, parallax 0.4 of the camera push
  const cs = caseSprite(W, H);
  const k = 1 + (cam.z - 1) * 0.4;
  ctx.save(); ctx.globalAlpha = 0.75;
  ctx.translate(W / 2, H * 0.5); ctx.scale(k, k); ctx.translate(-W / 2, -H * 0.5);
  ctx.drawImage(cs, 0, 0); ctx.restore();
  // warm key-light pool around the title, cool floor fall-off
  const g = ctx.createRadialGradient(W * 0.42, L.yc - 160 * L.s, 40, W * 0.5, L.yc, H * 0.62);
  g.addColorStop(0, rgba(p.key, 0.30)); g.addColorStop(0.35, rgba(p.key, 0.10)); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const v = ctx.createLinearGradient(0, 0, 0, H);
  v.addColorStop(0, 'rgba(0,0,0,0.55)'); v.addColorStop(0.3, 'rgba(0,0,0,0)'); v.addColorStop(0.75, 'rgba(0,0,0,0.1)'); v.addColorStop(1, 'rgba(0,0,0,0.7)');
  ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
  // volumetric beam from the upper left
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  const bx = -W * 0.2, by = -H * 0.05;
  const bg2 = ctx.createLinearGradient(bx, by, W * 0.62, L.yc);
  bg2.addColorStop(0, rgba(p.key, 0.0)); bg2.addColorStop(0.55, rgba(p.key, 0.07)); bg2.addColorStop(1, rgba(p.key, 0.0));
  ctx.fillStyle = bg2;
  ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + W * 0.42, by); ctx.lineTo(W * 0.98, L.yc + 60 * L.s); ctx.lineTo(W * 0.18, L.yc + 60 * L.s); ctx.closePath(); ctx.fill();
  ctx.restore();
  dust(ctx, glow, t, { x: 0, y: H * 0.08, w: W, h: H * 0.62, count: 70, seed: 11, color: '#FFD9A8', glowColor: p.key, r: [0.8, 2.4], speed: 10, alpha: 0.55, fadeIn: smooth(seg(t, 0, 0.8)) });
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  const T = timing(p);
  if (t < T.land[T.n - 1] + 0.05) return 10;
  if (t < T.lock + 0.2) return 6;
  if (t < T.sweep + 0.8) return 3;
  return 2;
}
export function post(t) { return { fade: smooth(seg(t, 0, 0.3)) }; }

export function draw(ctx, t, p, tk, env) {
  const L = layout(p, { ...env, tokens: tk });
  const T = timing(p);
  const glow = env.glow;
  const cam = camera(t, T, env);
  drawBackground(ctx, glow, t, env, L, p, cam);
  const rail = drawRail(ctx, glow, L, cam, t, T, p);
  // contact shadows on the rail, sharper as a block comes down
  for (let i = 0; i < L.n; i++) {
    const b = pose(i, t, p, L, T);
    if (!b) continue;
    const hgt = clamp((L.yc - b.y) / (300 * L.s), 0, 1) + (b.landed ? 0 : 0.2);
    const sp = proj([b.x, rail.y, -L.depth / 2], cam);
    ctx.save(); ctx.filter = `blur(${(3 + 22 * hgt).toFixed(1)}px)`;
    ctx.fillStyle = `rgba(0,0,0,${(0.75 * (1 - 0.7 * hgt)).toFixed(3)})`;
    ctx.beginPath(); ctx.ellipse(sp[0], sp[1] - 4 * L.s, L.S * 0.55 * (1 + 0.4 * hgt), L.S * 0.12, 0, 0, TAU); ctx.fill();
    ctx.restore();
  }
  // blocks, far to near
  const sweepX = (t >= T.sweep && t < T.sweep + 0.9) ? lerp(L.x0 - 200 * L.s, L.x0 + L.total + 200 * L.s, E.sineInOut(seg(t, T.sweep, T.sweep + 0.9))) : null;
  const bs = [];
  for (let i = 0; i < L.n; i++) { const b = pose(i, t, p, L, T); if (b) bs.push({ ...b, i, ch: L.chars[i] }); }
  bs.sort((a, b) => (a.z - b.z) || (a.i - b.i));
  for (const b of bs) {
    const dof = Math.abs(b.z) / (60 * L.s);
    if (dof > 0.3) { ctx.save(); ctx.filter = `blur(${Math.min(9, dof).toFixed(2)}px)`; }
    const pr = drawBlock(ctx, glow, b, L, p, cam, b.landed ? sweepX : null, t);
    if (dof > 0.3) ctx.restore();
    // landing: glint + fine metal dust on the rail
    const s = t - T.land[b.i];
    if (s >= 0 && s < 0.35 && glow) {
      const c = proj([b.x, L.yc - L.S / 2, 0], cam);
      drawSprite(glow, softDot('g', '#FFD8A8'), c[0] - L.S * 0.3, c[1], 40 * L.s, 0.9 * Math.exp(-s / 0.08));
      for (let k = 0; k < 7; k++) {
        const a = (hash2(b.i, k) - 0.5) * 2.6 - Math.PI / 2, sp = (120 + 260 * hash2(b.i, k + 20)) * L.s;
        const px = c[0] + (hash2(b.i, k + 40) - 0.5) * L.S + Math.cos(a) * sp * s, py = rail.y + Math.sin(a) * sp * s + 500 * s * s;
        drawSprite(ctx, softDot('d', '#FFE4C0'), px, py, 2.2 * L.s, 0.8 * (1 - s / 0.35));
        drawSprite(glow, softDot('c', '#FFB870'), px, py, 7 * L.s, 0.6 * (1 - s / 0.35));
      }
    }
  }
  // caption + rule under the rail
  const su = E.expoOut(seg(t, T.sub, T.sub + 0.7));
  if (su > 0.001 && p.sub) {
    const f = tokFont(tk, 'sans', 26 * L.s, 500);
    ctx.font = f; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = `${(9 * L.s).toFixed(1)}px`;
    ctx.filter = `blur(${(6 * (1 - su)).toFixed(2)}px)`;
    ctx.fillStyle = rgba('#CDB89D', su * 0.95);
    ctx.fillText(p.sub, env.W / 2 + 4.5 * L.s, rail.y + 150 * L.s + 12 * (1 - su));
    ctx.filter = 'none'; ctx.letterSpacing = '0px';
    const w = 320 * L.s * E.expoOut(seg(t, T.sub - 0.1, T.sub + 0.6));
    ctx.fillStyle = rgba('#CDB89D', 0.5 * su);
    ctx.fillRect(env.W / 2 - w / 2, rail.y + 92 * L.s, w, 1.2 * L.s);
  }
  if (p.label) {
    const la = smooth(seg(t, 0.2, 0.9));
    ctx.font = tokFont(tk, 'sans', 20 * L.s, 500); ctx.textAlign = 'left'; ctx.letterSpacing = `${(6 * L.s).toFixed(1)}px`;
    ctx.fillStyle = rgba('#9C8A76', 0.8 * la);
    ctx.fillText(p.label, 108 * L.s, 262 * L.s);                       // below the top band (12 % H)
    ctx.fillStyle = rgba('#9C8A76', 0.45 * la); ctx.fillRect(108 * L.s, 278 * L.s, 60 * L.s, 1 * L.s);
    ctx.letterSpacing = '0px';
  }
}

export function bbox(t, p, tk, env) {
  const L = layout(p, { ...env, tokens: tk });
  return [{ kind: 'text', label: p.text, x: L.x0, y: L.yc - L.S / 2, w: L.total, h: L.S, font_px: L.S * 0.74 }];
}
