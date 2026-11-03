'use strict';
/* ==========================================================================
   S7  06 SCORE    32.00 – 36.00
   S8  07 SAMPLE   36.00 – 40.60 (fades out under the warm front)
   ========================================================================== */
const TOP8 = [['凉', 0.31], ['爽', 0.17], ['黄', 0.12], ['静', 0.08], ['落', 0.06], ['远', 0.04], ['金', 0.03], ['思', 0.02]];
const REST_P = 0.17;
const TOP8_CELL = [[22, 36], [12, 41], [31, 33], [17, 46], [28, 43], [9, 34], [35, 39], [20, 30]];
const MID_CH = '冷寒秋风叶月霜雨枫桂清淡空高念愁萧瑟飒丰收暖香';
const GCOLS = 46, GROWS = 80, GCELL = 30, GOX = -150, GOY = -240;
const S7D = {};
const GRIDC = mkCanvas(GCOLS * GCELL, GROWS * GCELL);
const MASKD = mkCanvas(GCOLS, GROWS), MASKB = mkCanvas(GCOLS, GROWS);
const LAYA = mkCanvas(GCOLS * GCELL, GROWS * GCELL), LAYB = mkCanvas(GCOLS * GCELL, GROWS * GCELL);

registerInit(() => {
  const rng = mulberry32(3755);
  const cells = new Array(GCOLS * GROWS);
  const special = new Map();
  TOP8_CELL.forEach(([c, r], k) => special.set(r * GCOLS + c, { ch: TOP8[k][0], p: TOP8[k][1], top: k }));
  const nearTop = (c, r) => TOP8_CELL.some(([cc, rr]) => Math.abs(cc - c) <= 1 && Math.abs(rr - r) <= 1);
  [...MID_CH].forEach(ch => {
    let c, r; do { c = 6 + Math.floor(rng() * 34); r = 12 + Math.floor(rng() * 56); } while (special.has(r * GCOLS + c) || nearTop(c, r));
    special.set(r * GCOLS + c, { ch, p: 0.002 + rng() * 0.01, top: -1 });
  });
  for (let r = 0; r < GROWS; r++) for (let c = 0; c < GCOLS; c++) {
    const i = r * GCOLS + c;
    const s = special.get(i);
    const x = GOX + GCELL * c + GCELL / 2, y = GOY + GCELL * r + GCELL / 2;
    const d = Math.hypot(x - CX, y - CY);
    if (s) cells[i] = { ch: s.ch, p: s.p, top: s.top, x, y, d };
    else cells[i] = { ch: GB1[Math.floor(rng() * GB1.length)], p: Math.pow(10, -6 + rng() * 2.4), top: -1, x, y, d };
    cells[i].b = Math.pow(cells[i].p, 0.35);
  }
  S7D.cells = cells;
  const x = GRIDC.getContext('2d');
  x.font = FNT.pf(22, 400); x.fillStyle = '#FFFFFF'; x.textAlign = 'center'; x.textBaseline = 'alphabetic';
  const mid = cjkMid(FNT.pf(22, 400));
  for (let r = 0; r < GROWS; r++) for (let c = 0; c < GCOLS; c++) {
    const cl = cells[r * GCOLS + c];
    if (cl.top >= 0) continue;                 // top-8 are drawn separately (they fly away later)
    x.fillText(cl.ch, GCELL * c + GCELL / 2, GCELL * r + GCELL / 2 + mid);
  }
  S7D.mid = mid;
  S7D.mdx = MASKD.getContext('2d'); S7D.mbx = MASKB.getContext('2d');
  S7D.imgD = S7D.mdx.createImageData(GCOLS, GROWS); S7D.imgB = S7D.mbx.createImageData(GCOLS, GROWS);
  S7D.lax = LAYA.getContext('2d'); S7D.lbx = LAYB.getContext('2d');
  // cumulative column
  let cum = 0;
  S7D.segs = TOP8.map(([ch, p], k) => { const s = { ch, p, c0: cum, c1: cum + p, k }; cum += p; return s; });
  S7D.segs.push({ ch: '其余', p: REST_P, c0: cum, c1: 1, k: 8 });
  // label positions (spread to avoid overlap)
  let prev = -1e9;
  S7D.segs.forEach(s => { s.yc = COLY(s.c0 + s.p / 2); s.ly = Math.max(s.yc, prev + 50); prev = s.ly; });
  // r sequence
  const rr = mulberry32(8128);
  S7D.rt = CUES.roulette.filter(x => x < 39.5).map(x => ({ t: x, r: rr() }));   // roulette ticks from the cue sheet
  const tail = [0.47, 0.36, 0.58, 0.41];            // the last few throws land outside 凉, then the lock snaps into it
  for (let i = 0; i < tail.length; i++) S7D.rt[S7D.rt.length - tail.length + i].r = tail[i] + (rr() - 0.5) * 0.04;
});
const COLY = c => 560 + 840 * c;
function scanY(t) { return 1920 * E.sineInOut(seg(t, 32.4, 33.9)); }
function scanTime(y) { const u = clamp(y / 1920); return 32.4 + 1.5 * Math.acos(1 - 2 * u) / Math.PI; }

function s7CellState(cl, t) {
  // returns [dimAlpha, iceAlpha]
  const tr = 32.0 + cl.d / 2750;
  if (t < tr) return [0, 0];
  const rv = E.expoOut((t - tr) / 0.18);
  const wave = Math.exp(-(t - tr) / 0.07) * 0.55;
  let ts = scanTime(cl.y);
  if (cl.y < 0 || cl.y > 1920) ts = 33.0 + (cl.y < 0 ? 0 : 0.9);
  let dim = rv, ice = wave * rv;
  if (t >= ts) {
    const k = E.expoOut((t - ts) / 0.3);
    const fl = Math.exp(-(t - ts) / 0.07);
    dim = rv * (1 - k);
    ice = Math.max(ice, fl * 0.95) + cl.b * k * (1 - fl * 0.5);
  }
  const dark = E.expoOut(seg(t, 34.0, 34.75));
  if (cl.top < 0) { ice *= 1 - 0.88 * dark; dim *= 1 - 0.9 * dark; }
  const out = 1 - E.cubicInOut(seg(t, 35.25, 35.75));
  return [dim * out, clamp(ice) * out];
}

function drawS7(t, R) {
  const w = R.w, g = R.g;
  if (t < 35.8) {
    // ---- per-cell masks
    const D = S7D.imgD.data, B = S7D.imgB.data;
    const cells = S7D.cells;
    for (let i = 0; i < cells.length; i++) {
      const [d, b] = s7CellState(cells[i], t);
      D[i * 4 + 3] = Math.round(d * 255); B[i * 4 + 3] = Math.round(b * 255);
    }
    S7D.mdx.putImageData(S7D.imgD, 0, 0); S7D.mbx.putImageData(S7D.imgB, 0, 0);
    for (const [lx, mask, col] of [[S7D.lax, MASKD, COL.dim], [S7D.lbx, MASKB, COL.iceX]]) {
      lx.globalCompositeOperation = 'copy'; lx.drawImage(GRIDC, 0, 0);
      lx.globalCompositeOperation = 'destination-in'; lx.imageSmoothingEnabled = false; lx.drawImage(mask, 0, 0, GRIDC.width, GRIDC.height);
      lx.globalCompositeOperation = 'source-in'; lx.fillStyle = col; lx.fillRect(0, 0, GRIDC.width, GRIDC.height);
      lx.globalCompositeOperation = 'source-over';
    }
    w.drawImage(LAYA, GOX, GOY); w.drawImage(LAYB, GOX, GOY);
    // ---- top 8 (still in the grid)
    w.font = FNT.pf(22, 400); w.textAlign = 'center';
    TOP8_CELL.forEach(([c, r], k) => {
      if (t >= CUES.flyout[k]) return;
      const cl = S7D.cells[r * GCOLS + c];
      const [d, b] = s7CellState(cl, t);
      const bb = Math.max(b, 0);
      if (d > 0.01) { w.globalAlpha = d; w.fillStyle = COL.dim; w.fillText(cl.ch, cl.x, cl.y + S7D.mid); }
      if (bb > 0.01) {
        w.globalAlpha = clamp(bb * 1.1); w.fillStyle = COL.iceX; w.fillText(cl.ch, cl.x, cl.y + S7D.mid);
        const ts = scanTime(cl.y);
        if (t > ts) drawSprite(g, softDot('c', COL.cyan), cl.x, cl.y, 20 + 30 * cl.b, cl.b * 1.2 * E.expoOut((t - ts) / 0.5));
      }
      w.globalAlpha = 1;
    });
    w.textAlign = 'left';
    // ---- scan line
    if (t >= 32.4 && t <= 33.95) {
      const y = scanY(t);
      const a = bump(t, 32.4, 32.45, 33.85, 33.95);
      w.fillStyle = rgba(COL.iceX, a); w.fillRect(-200, y - 1, W + 400, 2);
      const gr = w.createLinearGradient(0, y - 90, 0, y);
      gr.addColorStop(0, rgba(COL.cyan, 0)); gr.addColorStop(1, rgba(COL.cyan, 0.10 * a));
      w.fillStyle = gr; w.fillRect(-200, y - 90, W + 400, 90);
      g.fillStyle = rgba(COL.cyan, 0.8 * a); g.fillRect(-200, y - 3, W + 400, 6);
    }
    // ---- radial wavefront ring
    if (t < 32.5) {
      const rr = (t - 32.0) * 2750;
      const a = 0.5 * (1 - seg(t, 32.0, 32.45));
      blurRing(w, CX, CY, rr, 2750, 2, COL.cyan, a);
      blurRing(g, CX, CY, rr, 2750, 6, COL.cyan, a * 0.8);
    }
  }
  // ---- leaderboard (screen space)
  if (t >= 35.0) { R.screenOn(w); R.screenOn(g); drawLeaderboard(w, g, t, R); }
}
function gridScreenPos(cl, t) { const c = camera(t); return [c.cx + (cl.x - c.cx) * c.zoom + c.sx, c.cy + (cl.y - c.cy) * c.zoom + c.sy]; }

function drawLeaderboard(w, g, t, R) {
  TOP8.forEach(([ch, p], k) => {
    const t0 = CUES.flyout[k];
    if (t < t0) return;
    const y = 640 + 92 * k;
    const cl = S7D.cells[TOP8_CELL[k][1] * GCOLS + TOP8_CELL[k][0]];
    const [gx, gy] = gridScreenPos(cl, Math.min(t, t0));
    const e = E.expoInOut(seg(t, t0, t0 + 0.34));
    const sF = FNT.song(64, 700);
    const tx = 150, tb = y + cjkMid(sF);
    // flying glyph: PingFang 22 -> Songti 64
    const x = lerp(gx - 11, tx, e), b = lerp(gy + S7D.mid, tb, e) - 40 * Math.sin(Math.PI * e);
    const s = lerp(22 / 64, 1, e);
    w.save(); w.translate(x, b); w.scale(s, s);
    w.globalAlpha = 1 - e; w.font = FNT.pf(64, 400); w.fillStyle = COL.iceX; w.fillText(ch, 0, 0);
    w.globalAlpha = e; w.font = sF; w.fillStyle = k === 0 ? COL.iceX : COL.text; w.fillText(ch, 0, 0);
    w.restore(); w.globalAlpha = 1;
    if (e < 1) drawSprite(g, softDot('c', COL.cyan), x + 32 * s, b - 24 * s, 40, 0.6 * (1 - e));
    // bar + percentage
    const bp = E.expoOut(seg(t, t0 + 0.18, Math.min(t0 + 0.5, 35.98)));
    if (bp > 0) {
      const bw = 2000 * p * bp;
      w.fillStyle = k === 0 ? COL.cyan : rgba(COL.cyan, 0.78); w.fillRect(260, y - 5, bw, 10);
      if (k === 0) { g.fillStyle = rgba(COL.cyan, 0.6); g.fillRect(260, y - 7, bw, 14); }
      w.font = FNT.mono(30); w.fillStyle = k === 0 ? COL.iceX : COL.text; w.globalAlpha = bp;
      w.fillText(Math.round(p * 100 * bp) + '%', 260 + bw + 16, y + 11); w.globalAlpha = 1;
    }
  });
  // "其余"
  const ra = E.expoOut(seg(t, 35.75, 36.05));
  if (ra > 0) {
    const y = 640 + 92 * 8;
    w.globalAlpha = ra;
    w.font = FNT.pf(28, 400); w.fillStyle = COL.text2; w.textAlign = 'right'; w.fillText('其余', 214, y + cjkMid(FNT.pf(28, 400))); w.textAlign = 'left';
    const bw = 2000 * REST_P * E.expoOut(seg(t, 35.8, 36.1));
    hatchRect(w, 260, y - 5, bw, 10, COL.text2, 0.7);
    w.font = FNT.mono(30); w.fillStyle = COL.text2; w.fillText('17%', 260 + bw + 16, y + 11);
    w.globalAlpha = 1;
  }
}
function hatchRect(w, x, y, ww, hh, col, a) {
  if (ww <= 0 || hh <= 0) return;
  w.save(); w.beginPath(); w.rect(x, y, ww, hh); w.clip();
  w.strokeStyle = rgba(col, a); w.lineWidth = 1.5;
  w.beginPath();
  for (let s = -hh; s < ww + hh; s += 6) { w.moveTo(x + s, y + hh); w.lineTo(x + s + hh, y); }
  w.stroke();
  w.strokeStyle = rgba(col, a * 0.8); w.lineWidth = 1.5; w.strokeRect(x + 0.75, y + 0.75, ww - 1.5, hh - 1.5);
  w.restore();
}
registerScene({ name: 'S7', t0: 32.0, t1: 36.0, draw: drawS7 });

/* ---------------- S8 ---------------- */
function rAt(t) {
  if (t >= 39.5) return 0.2317;
  let v = null, k = -1;
  for (let i = 0; i < S7D.rt.length; i++) if (t >= S7D.rt[i].t) { v = S7D.rt[i].r; k = i; }
  return v === null ? null : { r: v, k, t0: S7D.rt[k].t };
}
function drawS8(t, R) {
  const w = R.w, g = R.g;
  const lock = t >= 39.5;
  // at the impact the cold elements drop to a desaturated ghost and fade (no cyan under the gold light -> no green)
  const hit = t >= 40.0;
  const A = hit ? 0.38 * (1 - E.expoOut(seg(t, 40.0, 40.3))) : 1;
  if (A <= 0.002) return;
  const desat = hit ? 1 : 0;
  const segCol = (k) => k % 2 === 0 ? COL.cyan : '#3E8FB5';
  const x0 = 700, x1 = 760;
  const colA = (k) => lock ? (k === 0 ? 1 : 0.2 + 0.8 * Math.exp(-(t - 39.5) / 0.04)) : 1;
  if (t >= 40.0) {  // keep S8's final framing while it fades out under the warm front
    const c = camera(t), z = 1.04;
    w.setTransform(z, 0, 0, z, 540 - 540 * z + c.sx, 960 - 960 * z + c.sy);
    g.setTransform(z * 0.5, 0, 0, z * 0.5, (540 - 540 * z + c.sx) * 0.5, (960 - 960 * z + c.sy) * 0.5);
  }
  // ---- bars -> column
  S7D.segs.forEach((s, k) => {
    const e = E.expoInOut(seg(t, 36.0 + 0.035 * k, 36.45 + 0.035 * k));
    const yb = 640 + 92 * k, len0 = 2000 * s.p, len1 = 840 * s.p - 2;
    const cxA = 260 + len0 / 2, cyA = yb, cxB = (x0 + x1) / 2, cyB = COLY(s.c0) + 1 + len1 / 2;
    const cx = lerp(cxA, cxB, e), cy = lerp(cyA, cyB, e) - 30 * Math.sin(Math.PI * e);
    const ang = lerp(0, Math.PI / 2, e);
    const len = lerp(len0, len1, e), th = lerp(10, 60, e);
    w.save(); w.globalAlpha = A * colA(k); w.translate(cx, cy); w.rotate(ang);
    if (k === 8) hatchRect(w, -len / 2, -th / 2, len, th, COL.text2, 0.7);
    else {
      if (desat > 0) w.fillStyle = mixHex(segCol(k), '#8C8A88', desat);
      else if (k === 0 && lock) w.fillStyle = mixHex(COL.cyan, COL.iceX, 0.85);
      else { const m = smooth(e / 0.6); w.fillStyle = mixHex(COL.cyan, segCol(k), m, lerp(k === 0 ? 1 : 0.78, 1, m)); }
      w.fillRect(-len / 2, -th / 2, len, th);
    }
    w.restore(); w.globalAlpha = 1;
    // continuity with the S7 leaderboard: its glow and percentages hand over during the first part of the morph
    const hand = 1 - smooth(e / 0.3);
    if (hand > 0.004 && !lock) {
      if (k === 0) { g.save(); g.translate(cx, cy); g.rotate(ang); g.fillStyle = rgba(COL.cyan, 0.6 * hand); g.fillRect(-len / 2, -7, len, 14); g.restore(); }
      w.globalAlpha = hand; w.font = FNT.mono(30); w.fillStyle = k === 8 ? COL.text2 : k === 0 ? COL.iceX : COL.text;
      w.fillText(Math.round(s.p * 100) + '%', 260 + len0 + 16, yb + 11); w.globalAlpha = 1;
    }
    if (k === 0 && lock && !hit) { g.globalAlpha = A * (0.35 + 0.4 * Math.exp(-(t - 39.5) / 0.12)); g.fillStyle = COL.ice; g.fillRect(x0 - 4, COLY(0) - 2, 68, 840 * 0.31 + 4); g.globalAlpha = 1; }
    // label: Songti 64 @ (150, yb) -> 44 right-aligned at 660, spread y
    const lf0 = FNT.song(64, 700), lf1 = FNT.song(44, 700);
    let la = A * (lock ? (k === 0 ? 1 : 0.2) : 1);
    if (k === 0 && t >= 40.0) la = 0;                    // the S9 flight takes over this glyph
    if (k < 8) {
      const w1 = textW(s.ch, lf1);
      const lx = lerp(150, 660 - w1, e), lb = lerp(yb + cjkMid(lf0), s.ly + cjkMid(lf1), e);
      const sc = lerp(1, 44 / 64, e);
      w.save(); w.translate(lx, lb); w.scale(sc, sc); w.globalAlpha = la; w.font = lf0;
      w.fillStyle = hit ? '#8C8A88' : (k === 0 ? COL.iceX : COL.text); w.fillText(s.ch, 0, 0); w.restore(); w.globalAlpha = 1;
      if (k === 0 && lock && t < 40.0) { g.globalAlpha = 0.8; g.font = lf1; g.fillStyle = COL.ice; g.fillText('凉', 660 - w1, s.ly + cjkMid(lf1)); g.globalAlpha = 1; }
    } else {
      const lf = FNT.pf(28, 400);
      const lx = lerp(214 - textW('其余', lf), 660 - textW('其余', lf), e), lb = lerp(yb + cjkMid(lf), s.ly + cjkMid(lf), e);
      w.globalAlpha = la; w.font = lf; w.fillStyle = COL.text2; w.fillText('其余', lx, lb); w.globalAlpha = 1;
    }
    // leader from label to segment
    const le = seg(e, 0.8, 1);
    if (le > 0) {
      w.strokeStyle = rgba(COL.text2, 0.55 * le * A * (lock ? (k === 0 ? 1 : 0.3) : 1)); w.lineWidth = 1.5;
      w.beginPath(); w.moveTo(668, s.ly); w.lineTo(678, s.ly); w.lineTo(694, s.yc); w.stroke();
    }
    // percentage right of the column
    const pa = seg(e, 0.6, 1) * A * (lock ? (k === 0 ? 1 : 0.2) : 1);
    if (pa > 0) {
      w.globalAlpha = pa; w.font = FNT.mono(22); w.fillStyle = (k === 8 || hit) ? COL.text2 : (k === 0 ? COL.iceX : COL.text);
      w.fillText(Math.round(s.p * 100) + '%', 780, s.ly + 8); w.globalAlpha = 1;
      w.strokeStyle = rgba(COL.text2, 0.4 * pa); w.beginPath(); w.moveTo(764, s.yc); w.lineTo(772, s.ly); w.stroke();
    }
  });
  // ---- right scale
  const sa = E.expoOut(seg(t, 36.5, 36.9)) * A;
  if (sa > 0) {
    const sx = 900;
    w.fillStyle = rgba(COL.text2, 0.6 * sa); w.fillRect(sx - 0.75, COLY(0), 1.5, 840);
    w.font = FNT.mono(18); w.fillStyle = rgba(COL.text2, sa);
    [0, 0.25, 0.5, 0.75, 1].forEach(v => { const y = COLY(v); w.fillRect(sx - 0.75, y - 0.75, 12, 1.5); w.fillText(String(v), sx + 20, y + 6); });
  }
  // ---- random number r
  const ra = E.expoOut(seg(t, 36.4, 36.8)) * A;
  if (ra > 0) {
    w.globalAlpha = ra;
    w.font = FNT.pf(24, 400); w.fillStyle = COL.text2; w.fillText('随机数 r', 72, 980);
    const st = rAt(t);
    let str = '0.0000', flash = 0;
    if (st !== null) { str = (lock ? 0.2317 : st.r).toFixed(4); flash = lock ? Math.exp(-(t - 39.5) / 0.2) : Math.exp(-(t - st.t0) / 0.05); }
    w.font = FNT.mono(88, 400); w.fillStyle = hit ? '#8C8A88' : lock ? COL.iceX : mixHex(st === null ? COL.text2 : COL.text, COL.iceX, flash);
    w.fillText(str, 72, 1084);
    if (lock && !hit) { g.globalAlpha = 0.55 * ra; g.font = FNT.mono(88, 400); g.fillStyle = COL.cyan; g.fillText(str, 72, 1084); g.globalAlpha = 1; }
    w.globalAlpha = 1;
    // pointer
    if (st !== null) {
      const rv = lock ? 0.2317 : st.r;
      let py = COLY(rv);
      if (!lock && st.k > 0) { const prev = S7D.rt[st.k - 1].r; py = lerp(COLY(prev), py, E.expoOut((t - st.t0) / 0.05)); }
      if (lock) { const prev = S7D.rt[S7D.rt.length - 1].r; py = lerp(COLY(prev), COLY(0.2317), E.expoOut((t - 39.5) / 0.03)); }
      w.globalAlpha = ra;
      w.fillStyle = hit ? '#8C8A88' : COL.cyan; w.beginPath(); w.moveTo(696, py); w.lineTo(682, py - 8); w.lineTo(682, py + 8); w.closePath(); w.fill();
      if (!lock) { w.fillStyle = rgba(COL.cyan, 0.7); w.fillRect(560, py - 0.75, 120, 1.5); }
      else if (hit) { w.fillStyle = '#8C8A88'; w.fillRect(560, py - 1.5, 240, 3); }
      else {
        const le = E.expoOut((t - 39.5) / 0.06);
        const xr = lerp(680, 800, le);
        w.fillStyle = COL.iceX; w.fillRect(560, py - 1.5, xr - 560, 3);
        g.fillStyle = rgba(COL.cyan, 0.9); g.fillRect(560, py - 5, xr - 560, 10);
        const fl = Math.exp(-(t - 39.5) / 0.1);
        drawSprite(g, softDot('c', COL.iceX), 730, py, 90 + 60 * fl, 0.6 + 0.4 * fl);
        g.fillStyle = rgba(COL.ice, 0.5 * fl); g.fillRect(470, py - 12, 420, 24);
      }
      w.globalAlpha = 1;
    }
  }
}
registerScene({ name: 'S8', t0: 36.0, t1: 40.6, draw: drawS8 });
