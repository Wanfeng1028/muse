/* ==========================================================================
   timeline_cut — 时间线剪口卡（波纹删除）
   A macro view of an editing timeline: the playhead scrubs to a mark, a steel
   blade drops and slices the video + audio tracks (sparks), the playhead moves
   to the out-point, a second cut; the segment between the cuts lifts out and
   falls away, then everything to its right slides left and latches into the
   gap (ripple delete). The total-length readout rolls down to the new length.

   Look: a graphite editing bay at night. The timeline is a plane tilted away
   from the camera (drawn flat, then mapped strip by strip with perspective),
   with shallow depth of field toward its far edge; amber playhead and blade
   light, sparks and bloom. Generic editor styling, no product UI.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, springKick, hash2, rgba, rrect, tokFont, mkCanvas, softDot, drawSprite } from '../engine/core.js';
import { layoutChars } from '../engine/text.js';
import { sparks } from '../engine/particles.js';

export const id = 'timeline_cut';
export const role = 'card';
export const desc = '时间线剪口卡：刀片两次切开视频和音频轨，中间片段抬起掉落，右侧整体左移合拢并卡扣（波纹删除），总时长数字回落。全屏不透明。';

export const params = {
  clip: { default: '口播_A01.mov', type: 'string', desc: '视频片段名。' },
  audio: { default: '人声', type: 'string', desc: '音频轨名。' },
  title: { default: '标题', type: 'string', desc: '上层标题片段名。' },
  total0: { default: 48, type: 'number', desc: '剪前总长（秒）。' },
  removed: { default: 7, type: 'number', desc: '删掉的时长（秒），决定两刀的间距。' },
  label: { default: '波纹删除', type: 'string', desc: '顶部小标题。' },
  sub: { default: 'RIPPLE DELETE', type: 'string', desc: '顶部英文小字。' },
  amber: { default: '#FFB23E', type: 'color', desc: '播放头 / 刀光颜色。' },
};

export function timing() {
  return { cut1: 1.0, move: 1.28, cut2: 1.66, lift: 2.0, slide: 2.5, latch: 2.92, roll: 2.95, rollEnd: 3.45 };
}

/* ------------------------------------------------------------------ flat timeline (source space) */
const SW = 1600, SH = 820;          // source canvas
const PX_PER_S = 46;                // timeline scale
const ROW = { ruler: 80, v2: 150, v1: 250, a1: 500 };
const HGT = { v2: 70, v1: 220, a1: 150 };
const X0 = 150;                     // time 0 in source px

const CACHE = {};
function frameThumb(k, w, h) {      // abstract talking-head frames for the filmstrip
  const key = 'th' + k + w + h;
  if (CACHE[key]) return CACHE[key];
  const c = mkCanvas(w, h), x = c.getContext('2d');
  const hue = [205, 195, 215, 200, 190, 210][k % 6];
  const g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, `hsl(${hue},28%,${34 + 6 * hash2(k, 1)}%)`); g.addColorStop(1, `hsl(${hue + 10},24%,${18 + 4 * hash2(k, 2)}%)`);
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  x.fillStyle = 'rgba(255,220,180,0.10)'; x.fillRect(w * 0.08, 0, w * 0.18, h);           // window light
  const cx = w * (0.5 + (hash2(k, 3) - 0.5) * 0.08), hy = h * 0.42;
  x.fillStyle = `hsl(28,32%,${58 + 6 * hash2(k, 4)}%)`;                                        // face
  x.beginPath(); x.ellipse(cx, hy, w * 0.13, h * 0.2, 0, 0, TAU); x.fill();
  x.fillStyle = '#1C1C22'; x.beginPath(); x.ellipse(cx, hy - h * 0.12, w * 0.15, h * 0.12, 0, Math.PI, TAU); x.fill();   // hair
  x.fillStyle = '#E8E6E1'; x.beginPath(); x.ellipse(cx, h * 1.02, w * 0.36, h * 0.36, 0, Math.PI, TAU); x.fill();       // sweater
  CACHE[key] = c;
  return c;
}
function waveEnv(t) {               // speech-like envelope, deterministic
  const syl = Math.pow(Math.abs(Math.sin(t * 7.3) * Math.sin(t * 2.1 + 0.4)), 0.6);
  const phrase = 0.35 + 0.65 * smooth(clamp(Math.sin(t * 0.9 + 1.2) * 1.5 + 0.5));
  return clamp(syl * phrase * (0.75 + 0.25 * hash2(Math.floor(t * 40), 5)));
}

function clipBody(x, row, h, a, b, col, label, kind, tk, cut, seed) {
  // one clip spanning source px [a, b) on a row; cut = null | {sel: bool}
  if (b - a < 2) return;
  const y = ROW[row];
  x.save();
  rrect(x, a + 1, y, b - a - 2, h, 10); x.clip();
  x.fillStyle = col; x.fillRect(a, y, b - a, h);
  if (kind === 'video') {
    const tw = 132, th = h - 46;
    for (let k = Math.floor((a - X0) / tw) - 1; k * tw + X0 < b; k++) {
      const tx = X0 + k * tw + seed;
      x.drawImage(frameThumb(k + 12, tw - 4, th), tx + 2, y + 34);
    }
    x.fillStyle = 'rgba(0,0,0,0.25)'; x.fillRect(a, y + 34, b - a, th);
  } else if (kind === 'audio') {
    x.fillStyle = 'rgba(0,0,0,0.22)'; x.fillRect(a, y + 30, b - a, h - 30);
    x.fillStyle = 'rgba(190,255,215,0.85)';
    const mid = y + 30 + (h - 30) / 2;
    for (let px = a; px < b; px += 3) {
      const tt = (px - X0 - seed) / PX_PER_S;
      const v = waveEnv(tt) * (h - 42) / 2;
      x.fillRect(px, mid - v, 2, v * 2);
    }
  }
  // header strip + name
  x.fillStyle = 'rgba(255,255,255,0.10)'; x.fillRect(a, y, b - a, kind === 'title' ? h : 30);
  x.font = tokFont(tk, 'sans', 19, 500); x.fillStyle = 'rgba(255,255,255,0.88)'; x.textBaseline = 'alphabetic';
  x.fillText(label, Math.max(a, 0) + 14, y + 22 + (kind === 'title' ? 14 : 0));
  x.restore();
  rrect(x, a + 1, y, b - a - 2, h, 10);
  x.strokeStyle = cut && cut.sel ? 'rgba(255,96,64,0.95)' : 'rgba(255,255,255,0.16)'; x.lineWidth = cut && cut.sel ? 4 : 1.5; x.stroke();
}

function drawFlat(x, t, p, tk, T) {
  x.setTransform(1, 0, 0, 1, 0, 0);
  x.clearRect(0, 0, SW, SH);
  // panel
  const g = x.createLinearGradient(0, 0, 0, SH);
  g.addColorStop(0, '#1D1E22'); g.addColorStop(1, '#141518');
  x.fillStyle = g; x.fillRect(0, 0, SW, SH);
  for (const r of ['v2', 'v1', 'a1']) { x.fillStyle = 'rgba(255,255,255,0.025)'; x.fillRect(0, ROW[r] - 6, SW, HGT[r] + 12); }
  // cut geometry (source px)
  const c1 = X0 + 13.2 * PX_PER_S, c2 = c1 + p.removed * PX_PER_S, end0 = X0 + p.total0 * PX_PER_S;
  const slideU = E.cubicOut(seg(t, T.slide, T.latch));
  const snap = t >= T.latch ? springKick(t - T.latch, 9, 0.35) * 7 : 0;
  const shift = -(c2 - c1) * slideU + snap * (slideU > 0.99 ? 1 : 0);
  // ruler
  x.fillStyle = 'rgba(255,255,255,0.35)';
  x.font = tokFont(tk, 'sans', 17, 500);
  for (let s = 0; s <= 30; s++) {
    const px = X0 + s * PX_PER_S;
    if (px > SW) break;
    const major = s % 5 === 0;
    x.fillRect(px, ROW.ruler + (major ? 12 : 28), 1.5, major ? 36 : 20);
    if (major) x.fillText(`00:${String(s).padStart(2, '0')}`, px + 6, ROW.ruler + 26);
  }
  // tracks: left part, removed part (lifts out), right part (ripples left)
  const lift = seg(t, T.lift, T.lift + 0.5);
  const selected = t >= T.cut2 + 0.08;
  const parts = [
    { a: -400, b: c1, dx: 0 },
    { a: c2, b: end0, dx: shift },
  ];
  const tracks = [
    ['v2', HGT.v2, '#5E4A9C', p.title, 'title', X0 + 3 * PX_PER_S, X0 + 21 * PX_PER_S],
    ['v1', HGT.v1, '#2B6A88', p.clip, 'video', -400, end0],
    ['a1', HGT.a1, '#2C7552', p.audio, 'audio', -400, end0],
  ];
  for (const [row, h, col, label, kind, ta, tb] of tracks) {
    for (const part of parts) {
      const a = Math.max(ta, part.a), b = Math.min(tb, part.b);
      if (b <= a) continue;
      x.save(); x.translate(part.dx, 0);
      clipBody(x, row, h, a, b, col, a <= ta + 1 || part.a === c2 ? label : '', kind, tk, null, part.dx);
      x.restore();
    }
  }
  // the removed segment: selected (red outline), then lifts, tilts and falls away
  if (lift < 1) {
    const e = E.cubicIn(lift);
    x.save();
    x.globalAlpha = 1 - E.cubicIn(clamp(lift * 1.4 - 0.3));
    const cx = (c1 + c2) / 2, cy = (ROW.v1 + ROW.a1 + HGT.a1) / 2;
    x.translate(cx, cy - 60 * E.cubicOut(clamp(lift * 3)) + 520 * e * e);
    x.rotate(0.22 * e); x.scale(1 - 0.08 * e, 1 - 0.08 * e);
    x.translate(-cx, -cy);
    for (const [row, h, col, label, kind, ta, tb] of tracks) {
      const a = Math.max(ta, c1), b = Math.min(tb, c2);
      if (b > a) clipBody(x, row, h, a, b, col, '', kind, tk, { sel: selected }, 0);
    }
    x.restore(); x.globalAlpha = 1;
  }
  // cut slits (bright) — visible from each cut until the lift
  const slit = (cx, t0) => {
    const u = t - t0;
    if (u < 0) return;
    const a = u < 0.08 ? u / 0.08 : Math.exp(-(u - 0.08) / 0.5);
    x.fillStyle = rgba(p.amber, a);
    x.fillRect(cx - 2, ROW.v1 - 8, 4, ROW.a1 + HGT.a1 - ROW.v1 + 16);
  };
  if (t < T.lift + 0.1) { slit(c1, T.cut1); slit(c2, T.cut2); }
  // the join flash after the latch
  const j = t - T.latch;
  if (j > 0 && j < 0.6) { x.fillStyle = rgba(p.amber, 0.9 * Math.exp(-j / 0.15)); x.fillRect(c1 - 3, ROW.v1 - 10, 6, ROW.a1 + HGT.a1 - ROW.v1 + 20); }
  // playhead: scrubs to the in-point, jumps to the out-point, rides back to the join
  let ph;
  if (t < T.cut1 - 0.1) ph = lerp(X0 + 4 * PX_PER_S, c1, E.cubicInOut(seg(t, 0.15, T.cut1 - 0.12)));
  else if (t < T.move) ph = c1;
  else if (t < T.cut2 + 0.2) ph = lerp(c1, c2, E.cubicInOut(seg(t, T.move, T.move + 0.28)));
  else ph = lerp(c2, c1, E.cubicInOut(seg(t, T.slide, T.latch)));
  x.fillStyle = p.amber; x.fillRect(ph - 1.5, ROW.ruler, 3, SH - ROW.ruler - 30);
  x.beginPath(); x.moveTo(ph - 14, ROW.ruler); x.lineTo(ph + 14, ROW.ruler); x.lineTo(ph + 14, ROW.ruler + 16); x.lineTo(ph, ROW.ruler + 30); x.lineTo(ph - 14, ROW.ruler + 16); x.closePath(); x.fill();
  return { c1, c2, ph, shift };
}

/* ------------------------------------------------------------------ perspective mapping */
const VIEW = { top: 690, bottom: 1400, sTop: 1.0, sBot: 1.42, cx: 540, srcCx: 0 };
function mapY(sy) {                         // source y -> screen y (foreshortened toward the top)
  const u = sy / SH, k = lerp(VIEW.sTop, VIEW.sBot, u);
  const acc = (u * (VIEW.sTop + (VIEW.sBot - VIEW.sTop) * u / 2)) / ((VIEW.sTop + VIEW.sBot) / 2);
  return { y: lerp(VIEW.top, VIEW.bottom, acc), k };
}
function mapPt(sx, sy, cam) { const m = mapY(sy); return [VIEW.cx + (sx - cam.focusX) * m.k * cam.z, m.y + (cam.z - 1) * (m.y - 1000)]; }

let FLAT = null, BLUR = null;
function blit(ctx, cam) {
  const strip = 4;
  for (let sy = 0; sy < SH; sy += strip) {
    const m0 = mapY(sy), m1 = mapY(sy + strip);
    const k = m0.k * cam.z, y0 = m0.y + (cam.z - 1) * (m0.y - 1000), y1 = m1.y + (cam.z - 1) * (m1.y - 1000);
    const x0 = VIEW.cx - cam.focusX * k;
    const dof = clamp((1 - sy / SH) * 1.4 - 0.25);                      // far edge (top) defocused
    ctx.globalAlpha = 1; ctx.drawImage(FLAT, 0, sy, SW, strip, x0, y0, SW * k, y1 - y0 + 0.6);
    if (dof > 0.02) { ctx.globalAlpha = dof; ctx.drawImage(BLUR, 0, sy, SW, strip, x0, y0, SW * k, y1 - y0 + 0.6); }
  }
  ctx.globalAlpha = 1;
}

/* ------------------------------------------------------------------ blade */
function drawBlade(ctx, glow, t, t0, cx, cam, p) {
  // steel utility blade: drops 0.12 s before the cut, lifts after
  const u = t - (t0 - 0.12);
  if (u < 0 || u > 0.55) return;
  const down = u < 0.12 ? E.cubicIn(u / 0.12) : 1 - E.cubicInOut(clamp((u - 0.16) / 0.3));
  const topPt = mapPt(cx, ROW.v1 - 10, cam), botPt = mapPt(cx, ROW.a1 + HGT.a1 + 10, cam);
  const lean = (botPt[0] - topPt[0]) / (botPt[1] - topPt[1]);
  const tipY = lerp(topPt[1] - 520, botPt[1] + 18, down), tipX = topPt[0] + lean * (tipY - topPt[1]);
  const bh = 620;
  ctx.save(); ctx.translate(tipX, tipY); ctx.transform(1, 0, lean, 1, 0, 0);
  // craft-knife blade: straight spine on the right, long ground edge sweeping down to the tip on the left
  const body = [[0, 0], [-34, -80], [-86, -230], [-104, -bh], [58, -bh], [58, -150], [16, -26]];
  ctx.beginPath(); body.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath();
  const g = ctx.createLinearGradient(-104, 0, 58, 0);
  g.addColorStop(0, '#6A6F78'); g.addColorStop(0.3, '#C9CED6'); g.addColorStop(0.55, '#F4F6F8'); g.addColorStop(0.75, '#9CA3AD'); g.addColorStop(1, '#50555D');
  ctx.fillStyle = g; ctx.fill();
  // moving specular band down the blade
  const sy = -bh * (1 - clamp(u / 0.3));
  const sg = ctx.createLinearGradient(0, sy - 120, 0, sy + 120);
  sg.addColorStop(0, 'rgba(255,255,255,0)'); sg.addColorStop(0.5, 'rgba(255,255,255,0.35)'); sg.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = sg; ctx.fill();
  // ground bevel along the cutting edge
  const bev = [[0, 0], [-34, -80], [-86, -230], [-104, -bh * 0.5], [-78, -bh * 0.5], [-62, -226], [-14, -76], [8, -12]];
  ctx.beginPath(); bev.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath();
  ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.fill();
  ctx.strokeStyle = rgba(p.amber, 0.95); ctx.lineWidth = 2.2;
  ctx.beginPath(); ctx.moveTo(-104, -bh * 0.5); ctx.lineTo(-86, -230); ctx.lineTo(-34, -80); ctx.lineTo(0, 0); ctx.stroke();
  ctx.strokeStyle = 'rgba(20,22,26,0.5)'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(58, -bh); ctx.lineTo(58, -150); ctx.lineTo(16, -26); ctx.lineTo(0, 0); ctx.stroke();
  ctx.restore();
  if (glow) {
    glow.save(); glow.translate(tipX, tipY); glow.transform(1, 0, lean, 1, 0, 0);
    glow.strokeStyle = rgba(p.amber, 0.85); glow.lineWidth = 7; glow.beginPath(); glow.moveTo(-86, -230); glow.lineTo(-34, -80); glow.lineTo(0, 0); glow.stroke();
    glow.restore();
  }
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t) {
  const T = timing();
  for (const c of [T.cut1, T.cut2]) if (t > c - 0.15 && t < c + 0.4) return 10;
  if (t > T.lift - 0.05 && t < T.latch + 0.3) return 8;
  if (t > T.move - 0.05 && t < T.move + 0.35) return 6;
  return 3;
}
export function post(t) {
  const T = timing();
  let ca = 0;
  for (const c of [T.cut1, T.cut2, T.latch]) { const s = t - c; if (s >= 0 && s < 0.07) ca = Math.max(ca, 0.004 * (1 - s / 0.07)); }
  return { fade: smooth(seg(t, 0, 0.25)), ca };
}

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, T = timing(), glow = env.glow;
  if (!FLAT) { FLAT = mkCanvas(SW, SH); BLUR = mkCanvas(SW, SH); }
  const fx = FLAT.getContext('2d');
  const G = drawFlat(fx, t, p, tk, T);
  const bx = BLUR.getContext('2d');
  bx.setTransform(1, 0, 0, 1, 0, 0); bx.clearRect(0, 0, SW, SH); bx.filter = 'blur(7px)'; bx.drawImage(FLAT, 0, 0); bx.filter = 'none';
  // room: graphite, warm spill from above, faint UI grid
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#0C0D10'); g.addColorStop(0.45, '#15161A'); g.addColorStop(1, '#08090B');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const rg = ctx.createRadialGradient(W * 0.55, 620, 30, W * 0.55, 900, 900);
  rg.addColorStop(0, rgba(p.amber, 0.10)); rg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
  // camera: follows the edit point, pushes in a little
  const focusX = lerp(G.c1 - 60, G.c1 + (G.c2 - G.c1) * 0.4, E.sineInOut(seg(t, 0.2, T.cut2))) - lerp(0, (G.c2 - G.c1) * 0.4, E.sineInOut(seg(t, T.slide, T.latch + 0.2)));
  let sx = 0, sy = 0;
  for (const [c, a] of [[T.cut1, 5], [T.cut2, 5], [T.latch, 7]]) { const s = t - c; if (s >= 0 && s < 0.25) { const e = a * Math.exp(-s / 0.05); sx += e * Math.sin(97 * s + c); sy += e * Math.sin(71 * s + 2 * c); } }
  const cam = { z: 1 + 0.05 * E.sineInOut(seg(t, 0, env.dur)), focusX };
  ctx.save(); ctx.translate(sx, sy);
  if (glow) { glow.save(); glow.translate(sx, sy); }
  // soft shadow under the tilted panel, then the panel
  ctx.save(); ctx.filter = 'blur(40px)'; ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(-100, VIEW.top + 40, W + 200, VIEW.bottom - VIEW.top); ctx.restore();
  blit(ctx, cam);
  // glass sheen across the panel
  const sh = ctx.createLinearGradient(0, VIEW.top, 0, VIEW.bottom);
  sh.addColorStop(0, 'rgba(255,255,255,0.05)'); sh.addColorStop(0.2, 'rgba(255,255,255,0)'); sh.addColorStop(1, 'rgba(0,0,0,0.25)');
  ctx.fillStyle = sh; ctx.fillRect(0, VIEW.top, W, VIEW.bottom - VIEW.top);
  // blades, sparks, glow of the slits and playhead
  drawBlade(ctx, glow, t, T.cut1, G.c1, cam, p);
  drawBlade(ctx, glow, t, T.cut2, G.c2, cam, p);
  for (const [c, cx] of [[T.cut1, G.c1], [T.cut2, G.c2]]) {
    const pts = [mapPt(cx, ROW.v1 + HGT.v1 * 0.5, cam), mapPt(cx, ROW.a1 + HGT.a1 * 0.5, cam)];
    pts.forEach((q, k) => sparks(ctx, glow, t - c, { x: q[0], y: q[1], seed: 7 + k + (cx | 0), count: 14, spreadY: 120, speed: [260, 820], life: [0.25, 0.55], gravity: 900, colorHot: '#FFFFFF', colorCool: p.amber, glowColor: p.amber, width: 2 }));
  }
  if (glow) {
    const ph = mapPt(G.ph, ROW.ruler, cam), pb = mapPt(G.ph, SH - 30, cam);
    glow.strokeStyle = rgba(p.amber, 0.55); glow.lineWidth = 8; glow.beginPath(); glow.moveTo(ph[0], ph[1]); glow.lineTo(pb[0], pb[1]); glow.stroke();
    const j = t - T.latch;
    if (j > 0 && j < 0.6) { const a = mapPt(G.c1, ROW.v1, cam), b = mapPt(G.c1, ROW.a1 + HGT.a1, cam); glow.strokeStyle = rgba(p.amber, Math.exp(-j / 0.18)); glow.lineWidth = 26; glow.beginPath(); glow.moveTo(a[0], a[1]); glow.lineTo(b[0], b[1]); glow.stroke(); }
  }
  ctx.restore(); if (glow) glow.restore();
  // headline: label + total-length readout that rolls down after the latch
  const la = smooth(seg(t, 0.15, 0.6));
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  ctx.font = tokFont(tk, 'sans', 30, 500); ctx.letterSpacing = '10px'; ctx.fillStyle = rgba('#8E949E', 0.9 * la);
  ctx.fillText(p.sub, W / 2 + 5, 250);
  ctx.letterSpacing = '6px'; ctx.font = tokFont(tk, 'sans', 44, 700); ctx.fillStyle = rgba('#E9E6DF', la);
  ctx.fillText(p.label, W / 2 + 3, 322); ctx.letterSpacing = '0px';
  const r = E.cubicInOut(seg(t, T.roll, T.rollEnd));
  const secs = p.total0 - p.removed * r;
  drawReadout(ctx, glow, W / 2, 484, secs, r, t, T, p, tk);
  // bottom caption
  ctx.font = tokFont(tk, 'sans', 26, 500); ctx.fillStyle = rgba('#7D838D', 0.85 * la); ctx.textAlign = 'center';
  ctx.font = tokFont(tk, 'sans', 28, 500);
  ctx.fillText('空隙自动合拢，后面的片段整体前移', W / 2, 590);
  ctx.textAlign = 'left';
}

function drawReadout(ctx, glow, cx, y, secs, r, t, T, p, tk) {
  // mm:ss with rolling seconds digits (fixed cells so nothing jitters)
  const whole = Math.floor(secs + 1e-6), frac = secs - whole;
  const str = `00:${String(whole).padStart(2, '0')}`;
  const font = tokFont(tk, 'sans', 128, 700);
  ctx.font = font; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'center';
  const cell = 80, n = str.length, x0 = cx - (n * cell) / 2 + cell / 2;
  const hot = (r > 0 && r < 1) ? 1 : Math.exp(-Math.max(0, t - T.rollEnd) / 0.3) * (t > T.rollEnd ? 1 : 0);
  for (let i = 0; i < n; i++) {
    const ch = str[i], x = x0 + i * cell + (ch === ':' ? 0 : 0);
    const rolling = (i === n - 1) && r > 0 && r < 1;
    ctx.save(); ctx.beginPath(); ctx.rect(x - cell / 2, y - 120, cell, 150); ctx.clip();
    if (rolling) {                                        // odometer: as the value falls the wheel turns upward
      const Hc = 124;
      ctx.fillStyle = mixA('#FFFFFF', p.amber, hot);
      ctx.fillText(String(whole % 10), x, y + frac * Hc);
      ctx.fillText(String((whole + 1) % 10), x, y + (frac - 1) * Hc);
    } else {
      ctx.fillStyle = ch === ':' ? '#6B717B' : mixA('#F2EFE8', p.amber, i >= n - 2 ? hot : 0);
      ctx.fillText(ch, x, y);
    }
    ctx.restore();
  }
  ctx.textAlign = 'left';
  if (glow && hot > 0.02) { glow.fillStyle = rgba(p.amber, 0.25 * hot); glow.fillRect(cx + 20, y - 110, 180, 120); }
}
function mixA(a, b, t) {
  const A = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16)), B = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], clamp(t)))).join(',')})`;
}

export function bbox(t, p, tk, env) {
  return [{ kind: 'text', label: p.label, x: env.W / 2 - 240, y: 220, w: 480, h: 390, font_px: 44 }];
}
