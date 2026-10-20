'use strict';
/* ==========================================================================
   S5  04 ATTENTION  20.00 – 26.00   (24.5–26.0: the diagram becomes 3D plane L01)
   S6  05 LAYERS     26.00 – 32.00   (WebGL planes, motion blur, implosion + flash)
   ========================================================================== */
const NEXT_W = [0.06, 0.09, 0.14, 0.03, 0.21, 0.42, 0.05];   // 用 一个 字 ， 形容 秋天 。
const S5D = { arcs: [] };
const BEATS5 = [22.5, 23.0, 23.5, 24.0, 24.5, 25.0, 25.5];
const PC0 = mkCanvas(W, H), pc0x = PC0.getContext('2d');
const PG0 = mkCanvas(W / 2, H / 2), pg0x = PG0.getContext('2d');
let PT0 = null, PTG0 = null;

registerInit(() => {
  const rng = mulberry32(2020);
  const arcs = [];
  for (let b = 1; b <= 7; b++) {
    let ws;
    if (b === 7) ws = NEXT_W.slice();
    else {
      const raw = []; for (let a = 0; a < b; a++) raw.push(Math.exp(gaussR(rng) * 0.7 + 0.45 * (a - b)));
      const s = raw.reduce((x, y) => x + y, 0), keep = 0.55 + 0.3 * rng();
      ws = raw.map(v => v / s * keep);
    }
    for (let a = b - 1; a >= 0; a--) arcs.push({ a, b, w: ws[a] });
  }
  arcs.forEach((A, m) => { A.m = m; A.t0 = 20.25 + m * 0.043; });
  S5D.arcs = arcs;
  S5D.maxW = arcs.reduce((x, A) => Math.max(x, A.w), 0);
  PT0 = GLX.makePlaneTex(PC0); PTG0 = GLX.makePlaneTex(PG0);
});

function arcGeom(a, b) {
  const ya = S5L.y0 + S5L.dy * a, yb = S5L.y0 + S5L.dy * b;
  return { cx: S5L.spine, cy: (ya + yb) / 2, rx: 90 * (b - a), ry: (yb - ya) / 2, ya, yb };
}
function arcPt(G, th) { return [G.cx + G.rx * Math.cos(th), G.cy + G.ry * Math.sin(th)]; }

function drawS5Content(w, g, t) {
  const focus = E.expoInOut(seg(t, 22.25, 22.85));
  const drop = bump(t, 22.0, 22.03, 22.08, 22.5);
  const x0 = S5L.spine;
  const yTop = S5L.y0 - 36, yBot = S5L.y0 + S5L.dy * 7 + 36;
  // spine
  w.fillStyle = rgba(COL.text2, 0.55); w.fillRect(x0 - 0.75, yTop, 1.5, yBot - yTop);
  // arcs
  w.lineCap = 'round';
  for (const A of S5D.arcs) {
    const p = E.expoOut(seg(t, A.t0, A.t0 + 0.32));
    if (p <= 0) continue;
    const G = arcGeom(A.a, A.b);
    const isNext = A.b === 7;
    const wn = A.w / S5D.maxW;
    let lw = 1.2 + 4.8 * wn, al = 0.25 + 0.7 * wn;
    if (isNext) { lw = lerp(lw, 1.6 + 13 * A.w, focus); al = lerp(al, 0.55 + 0.45 * wn, focus); }
    else al *= lerp(1, 0.15, focus);
    al = clamp(al * (1 + 0.8 * drop));
    const gr = w.createLinearGradient(0, G.ya, 0, G.yb);
    gr.addColorStop(0, rgba(COL.violet, al)); gr.addColorStop(1, rgba(COL.cyan, al));
    w.strokeStyle = gr; w.lineWidth = lw;
    w.beginPath(); w.ellipse(G.cx, G.cy, G.rx, G.ry, 0, Math.PI / 2, Math.PI / 2 - Math.PI * p, true); w.stroke();
    // growing head
    if (p < 1) { const [hx, hy] = arcPt(G, Math.PI / 2 - Math.PI * p); drawSprite(g, softDot('c', COL.ice), hx, hy, 14, 0.9 * (1 - p)); }
    // glow for strong arcs
    const ga = (isNext ? lerp(0.25, 0.7, focus) : 0.2 * (1 - focus)) * wn + 0.5 * drop * wn;
    if (ga > 0.02) {
      g.strokeStyle = rgba(isNext ? COL.cyan : COL.violet, clamp(ga)); g.lineWidth = lw + 3;
      g.beginPath(); g.ellipse(G.cx, G.cy, G.rx, G.ry, 0, Math.PI / 2, Math.PI / 2 - Math.PI * p, true); g.stroke();
    }
  }
  w.lineCap = 'butt';
  // pulses along NEXT arcs (every beat from 22.5)
  const arrive = new Array(8).fill(0);
  for (const tb of BEATS5) {
    const tau = t - tb;
    if (tau < 0 || tau > 0.62) continue;
    for (let a = 0; a < 7; a++) {
      const wgt = NEXT_W[a], G = arcGeom(a, 7);
      const I = 0.35 + 0.65 * wgt / 0.42;
      const u = E.cubicInOut(clamp(tau / 0.42));
      const th = Math.PI / 2 - Math.PI * u;
      const fadeOut = 1 - seg(tau, 0.42, 0.62);
      for (let s = 0; s < 10; s++) {
        const th1 = th + s * 0.045, th2 = th + (s + 1) * 0.045;
        if (th1 > Math.PI / 2) break;
        const aa = I * (1 - s / 10) * fadeOut;
        w.strokeStyle = rgba(COL.iceX, aa); w.lineWidth = 2 + 4 * wgt / 0.42 * (1 - s / 10);
        w.beginPath(); w.ellipse(G.cx, G.cy, G.rx, G.ry, 0, Math.min(Math.PI / 2, th2), th1, true); w.stroke();
      }
      const [hx, hy] = arcPt(G, th);
      drawSprite(w, softDot('c', COL.iceX), hx, hy, 8 + 10 * wgt / 0.42, I * fadeOut);
      drawSprite(g, softDot('c', COL.cyan), hx, hy, 26 + 30 * wgt / 0.42, I * fadeOut);
      if (tau > 0.34) arrive[a] = Math.max(arrive[a], wgt / 0.42 * bump(tau, 0.36, 0.42, 0.44, 0.62));
    }
  }
  // weight labels at arc apexes
  if (t >= 22.4) {
    const order = [5, 4, 2, 1, 0, 6, 3];
    order.forEach((a, n) => {
      const la = E.expoOut(seg(t, 22.45 + n * 0.06, 22.75 + n * 0.06));
      if (la <= 0) return;
      const G = arcGeom(a, 7);
      const x = G.cx + G.rx, y = G.cy;
      const str = NEXT_W[a].toFixed(2);
      const f = FNT.mono(20, 500), tw = textW(str, f);
      w.globalAlpha = la;
      rrect(w, x - tw / 2 - 8, y - 15, tw + 16, 30, 8); w.fillStyle = 'rgba(5,7,12,0.88)'; w.fill();
      w.lineWidth = 1.5; w.strokeStyle = rgba(COL.cyan, 0.35 + 0.5 * NEXT_W[a] / 0.42); w.stroke();
      w.font = f; w.fillStyle = COL.iceX; w.textAlign = 'center'; w.fillText(str, x, y + 7); w.textAlign = 'left';
      w.globalAlpha = 1;
    });
  }
  // leaders, cards, anchors
  for (let i = 0; i < 8; i++) {
    const r = S5L.rows[i];
    let lx0 = S5L.x + r.cw + 12;
    if (i === 7) {
      w.font = FNT.mono(18); w.fillStyle = COL.text2; w.fillText('NEXT', lx0 + 2, r.yc + 6);
      lx0 += textW('NEXT', FNT.mono(18)) + 14;
    }
    w.save(); w.setLineDash([2, 5]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.text2, 0.5);
    w.beginPath(); w.moveTo(lx0, r.yc); w.lineTo(x0 - 10, r.yc); w.stroke(); w.restore();
    let hl = i === 5 ? focus : 0;
    hl = Math.max(hl, arrive[i] * 0.9);
    drawS5Card(w, g, i, 1, 1, clamp(hl));
    if (i < 7) {
      w.font = S5L.font; w.fillStyle = mixHex(COL.text, COL.iceX, arrive[i]); w.textAlign = 'left'; w.fillText(r.tk, r.tx, r.tb);
      if (i === 5 && focus > 0) { g.font = S5L.font; g.globalAlpha = 0.35 * focus + 0.4 * arrive[i]; g.fillStyle = COL.cyan; g.fillText(r.tk, r.tx, r.tb); g.globalAlpha = 1; }
    } else {
      const ca = clamp(1.8 * (0.5 + 0.5 * Math.cos(TAU * (t - 20.0))) - 0.4);
      w.fillStyle = rgba(COL.cyan, ca); w.fillRect(S5L.x + 26, r.yc - 18, 2, 36);
    }
    const anc = i < 7 ? COL.iceX : COL.cyan;
    w.fillStyle = anc; w.beginPath(); w.arc(x0, r.yc, 4 + 2 * arrive[i], 0, TAU); w.fill();
    drawSprite(g, softDot('c', COL.cyan), x0, r.yc, 18 + 20 * arrive[i], 0.5 + 0.5 * arrive[i]);
  }
}

/* ==========================================================================
   S6 — centred "frame tunnel": 9:16 hairline frames facing the camera,
   one smooth accelerating camera path zc(t); plane k sits where the camera
   will be at its pass time, so each frame reaches the screen edge exactly on T_k.
   ========================================================================== */
const S6 = { f: 1400, K: 0.2746, V0: 1600, dExit: 700, HW: 270, HH: 480, N: 26, rollRate: 4 * DEG / 900 };
function zcam(t) { return (S6.V0 / S6.K) * (Math.exp(S6.K * (t - 26)) - 1); }
registerInit(() => {
  S6.T = PASS_T.slice(); S6.T.push(31.5, 31.625);                 // two more planes ahead, never passed (they implode)
  S6.Z = S6.T.map(T => zcam(T) + S6.dExit);
  S6.layers = [];
  for (let k = 0; k < S6.N; k++) {
    const rng = mulberry32(7000 + 31 * k);
    const raw = []; for (let i = 0; i < 7; i++) raw.push(Math.exp(gaussR(rng) * 0.95 + 0.22 * i));
    const sm = raw.reduce((a, b) => a + b, 0), w = raw.map(v => v / sm);
    const faint = [];
    for (let n = 0; n < 3; n++) { const a = Math.floor(rng() * 5); faint.push([a, a + 1 + Math.floor(rng() * (6 - a))]); }
    S6.layers.push({ w, wmax: Math.max(...w), faint, off: [12 * Math.cos(k * 0.9 + 0.5), 12 * Math.sin(k * 0.9 + 0.5)] });
  }
  const rng = mulberry32(606);
  S6.stars = [];
  for (let n = 0; n < 620; n++) { const a = rng() * TAU, r = 380 + Math.pow(rng(), 0.7) * 2400; S6.stars.push({ x: Math.cos(a) * r, y: Math.sin(a) * r * 1.3, z: rng() * 24000, d: rng(), c: rng() }); }
});
const S6_VIOLET = hexRgb('#8E7DFF'), S6_CYAN = hexRgb('#6EE7F5'), S6_ICE = hexRgb('#CFF6FF');
function s6Color(k) {
  const n = LAYER_NUM[k];
  if (n <= 6) return S6_VIOLET;
  if (n <= 16) return mixRgb(S6_VIOLET, S6_CYAN, smooth((n - 6) / 10));
  return mixRgb(S6_CYAN, S6_ICE, smooth(clamp((n - 16) / 64)));
}
function s6Implode(t) { return E.cubicInOut(seg(t, 31.4, 31.88)); }
const S6_ANCH = [0, 1, 2, 3, 4, 5, 6].map(i => [-186, -404 + i * 44]);

/* draw one tunnel frame in plane-local units (frame = ±270 × ±480, NEXT point at the origin) */
function drawTunnelPlane(w, g, k, d, t, aFrame, aContent, sc, aLabel) {
  const s = S6.f / d * sc;
  const L = S6.layers[k];
  const phi = S6.rollRate * (d - S6.dExit);
  const cs = Math.cos(phi), sn = Math.sin(phi);
  const ox = L.off[0] * sc, oy = L.off[1] * sc;
  const ex = CX + s * (cs * ox - sn * oy), ey = CY + s * (sn * ox + cs * oy);
  const col = s6Color(k);
  const setT = (c, m) => c.setTransform(s * cs * m, s * sn * m, -s * sn * m, s * cs * m, ex * m, ey * m);
  // ---- frame (constant hairline on screen)
  if (aFrame > 0.004) {
    setT(w, 1);
    w.lineWidth = 1.5 / s; w.strokeStyle = rgbStr(col, 0.62 * aFrame);
    w.beginPath(); w.roundRect(-S6.HW, -S6.HH, 2 * S6.HW, 2 * S6.HH, 34); w.stroke();
    w.lineWidth = 2 / s; w.strokeStyle = rgbStr(col, 0.9 * aFrame);
    w.beginPath();
    for (const [x, y, sx, sy] of [[-S6.HW + 16, -S6.HH + 16, 1, 1], [S6.HW - 16, -S6.HH + 16, -1, 1], [-S6.HW + 16, S6.HH - 16, 1, -1], [S6.HW - 16, S6.HH - 16, -1, -1]]) {
      w.moveTo(x + 26 * sx, y); w.lineTo(x, y); w.lineTo(x, y + 26 * sy);
    }
    w.stroke();
    const lsz = 17 * s;
    if (lsz > 7) {
      w.font = FNT.mono(17, 500); w.textAlign = 'left'; w.fillStyle = rgbStr(col, 0.85 * aFrame * smooth((lsz - 7) / 5));
      w.fillText('L' + String(LAYER_NUM[k]).padStart(2, '0'), -S6.HW + 26, -S6.HH + 50);
    }
  }
  if (aContent <= 0.004) return;
  setT(w, 1);
  // ---- faint token-to-token arcs (left of the list)
  w.lineWidth = Math.min(3, Math.max(0.8, 1.2 * s)) / s;
  for (const [a, b] of L.faint) {
    const ya = S6_ANCH[a][1], yb = S6_ANCH[b][1];
    w.strokeStyle = rgbStr(col, 0.16 * aContent);
    w.beginPath(); w.ellipse(-186, (ya + yb) / 2, 14 * (b - a), (yb - ya) / 2, 0, Math.PI / 2, 3 * Math.PI / 2); w.stroke();
  }
  // ---- 7 arcs converging on the NEXT point (width ∝ weight, capped at 3 px on screen)
  for (let i = 0; i < 7; i++) {
    const [x0, y0] = S6_ANCH[i];
    const wn = L.w[i] / L.wmax;
    const px = Math.min(3, Math.max(0.8, (0.7 + 3.4 * wn) * s * 0.9));
    w.lineWidth = px / s;
    w.strokeStyle = rgbStr(mixRgb(col, S6_ICE, 0.25 * wn), (0.22 + 0.7 * wn) * aContent);
    w.beginPath(); w.moveTo(x0, y0); w.bezierCurveTo(x0 + 120, y0, -34, y0 * 0.36, 0, 0); w.stroke();
  }
  // ---- anchors + small token labels (fade out before they could grow large)
  const fs = 20 * s;
  const la = aLabel * smooth((fs - 7) / 5) * (1 - smooth((fs - 26) / 10));
  for (let i = 0; i < 7; i++) {
    const [x0, y0] = S6_ANCH[i];
    w.fillStyle = rgbStr(mixRgb(col, S6_ICE, 0.5), 0.9 * aContent);
    w.beginPath(); w.arc(x0, y0, clamp(3.5 * s, 1.2, 5) / s, 0, TAU); w.fill();
    if (la > 0.01) { w.font = FNT.pf(20, 500); w.textAlign = 'right'; w.fillStyle = rgbStr(mixRgb(col, hexRgb(COL.text), 0.45), 0.85 * la); w.fillText(TOK[i], x0 - 14, y0 + 7); }
  }
  w.textAlign = 'left';
  // ---- NEXT point (on the camera axis), brighter with depth of the stack
  const deepB = 0.55 + 0.45 * k / (S6.N - 1);
  const pr = clamp(6 * s, 1.6, 9) / s;
  w.fillStyle = rgbStr(mixRgb(S6_ICE, [255, 255, 255], 0.5), Math.min(1, 1.1 * aContent));
  w.beginPath(); w.arc(0, 0, pr, 0, TAU); w.fill();
  w.lineWidth = 1.2 / s; w.strokeStyle = rgbStr(col, 0.5 * aContent); w.beginPath(); w.arc(0, 0, 16, 0, TAU); w.stroke();
  // glow (screen space)
  w.setTransform(1, 0, 0, 1, 0, 0);
  const gr = Math.min(70, 30 * s + 10) * (0.8 + 0.4 * deepB);
  drawSprite(g, softDot('c', rgbHex(mixRgb(col, S6_ICE, 0.4))), ex / 1, ey / 1, gr, 0.55 * deepB * aContent);
}
function rgbHex(c) { return '#' + c.map(v => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join(''); }

function drawTunnelStars(w, t, zc, alpha, imp) {
  const zp = zcam(t - 0.025);
  const dens = t < 30 ? 0.4 : 0.4 + 0.6 * smooth(seg(t, 30.0, 30.4));
  const len = t < 30 ? 1 : 1 + 2.2 * smooth(seg(t, 30.0, 30.6));   // speed lines after 30 s
  w.setTransform(1, 0, 0, 1, 0, 0); w.lineCap = 'round';
  for (const st of S6.stars) {
    if (st.d > dens) continue;
    const zz = st.z + Math.ceil((zc - 400 - st.z) / 24000) * 24000;
    const d1 = zz - zc, d0 = zz - (zc - (zc - zp) * len);
    if (d1 < 60) continue;
    const k1 = S6.f / d1 * (1 - imp), k0 = S6.f / Math.max(60, d0) * (1 - imp);
    const x1 = CX + st.x * k1, y1 = CY + st.y * k1, x0 = CX + st.x * k0, y0 = CY + st.y * k0;
    const a = alpha * clamp((d1 - 60) / 500) * (1 - smooth((d1 - 9000) / 7000)) * (0.25 + 0.55 * st.c) * (t < 30 ? 0.65 : 1);
    if (a < 0.01) continue;
    const col = st.c < 0.33 ? COL.violet : st.c < 0.7 ? COL.cyan : COL.ice;
    w.strokeStyle = rgba(col, a); w.lineWidth = 1.2 + 1.3 * clamp(1 - d1 / 6000);
    w.beginPath(); w.moveTo(x0, y0); w.lineTo(x1 + 0.01, y1); w.stroke();
  }
  w.lineCap = 'butt';
}
function drawTunnel(t, R, transition) {
  const w = R.w, g = R.g;
  R.screenOn(w); R.screenOn(g);
  const zc = zcam(t);
  const imp = s6Implode(t);
  const sc = 1 - imp;
  const intro = transition ? E.expoOut(seg(t, 24.8, 25.6)) : 1;
  drawTunnelStars(w, t, zc, intro, imp);
  // vanishing-point core: the stack's NEXT points line up here ("we keep flying toward it")
  const core = (transition ? 0.35 * intro : 0.45 + 0.25 * seg(t, 26, 31.4));
  drawSprite(g, softDot('c', COL.ice), CX, CY, 46 + 20 * seg(t, 26, 31.4), core);
  // frames far -> near (k = 0 is L01, handled by the transition while t < 26)
  for (let k = S6.N - 1; k >= (transition ? 1 : 0); k--) {
    const d = S6.Z[k] - zc;
    if (d < S6.dExit * 0.9) continue;
    const fog = 1 - smooth((d - 3400) / 4800);
    if (fog <= 0.004) continue;
    const nearF = 0.45 + 0.55 * smooth((d - S6.dExit) / 420);             // frame reaches the edge half-bright, then is gone
    const nearC = smooth((d - S6.dExit * 1.02) / 430);                    // content fades before it can get large
    const fin = transition ? E.expoOut(seg(t, 24.85 + 0.03 * k, 25.55 + 0.03 * k)) : 1;
    const bright = 1 + 0.6 * imp;
    const nearL = smooth((d - 1350) / 500);                                // labels leave early: no smeared text at speed
    drawTunnelPlane(w, g, k, d, t, fog * nearF * fin * bright * (d < S6.dExit ? 0 : 1), fog * nearC * fin * bright, sc, fog * nearL * fin);
  }
  w.setTransform(1, 0, 0, 1, 0, 0);
  // pass pulses: a small soft bloom at the centre on every pass time
  for (let k = 0; k < PASS_T.length; k++) {
    const u = t - PASS_T[k];
    if (u >= 0 && u < 0.25) drawSprite(g, softDot('c', COL.ice), CX, CY, 70 + 60 * u / 0.25, 0.32 * Math.exp(-u / 0.07));
  }
  // 31.40–31.90 everything collapses into the white point, 31.90 radial bloom bursts
  const pre = E.cubicIn(seg(t, 31.4, 31.9));
  if (pre > 0.002) {
    drawSprite(g, softDot('c', COL.ice), CX, CY, 40 + 170 * pre, pre);
    drawSprite(w, softDot('c', COL.iceX), CX, CY, 8 + 36 * pre, pre);
    w.fillStyle = rgba('#FFFFFF', pre); w.beginPath(); w.arc(CX, CY, 2 + 11 * pre, 0, TAU); w.fill();
  }
  if (t >= 31.9) {
    // radial bloom burst: bright core, expanding ring and fine light rays (no flat fill)
    const q = seg(t, 31.9, 32.0);
    const e = E.expoOut(q);
    drawSprite(g, softDot('c', '#E6FBFF'), CX, CY, 60 + 520 * e, 0.95);
    drawSprite(w, softDot('c', '#FFFFFF'), CX, CY, 26 + 90 * e, 1);
    const rr = 20 + 1150 * e;
    blurRing(w, CX, CY, rr, 11500 * Math.exp(-q * 4), 2.5, COL.iceX, 0.85 * (1 - 0.6 * q));
    blurRing(g, CX, CY, rr, 11500 * Math.exp(-q * 4), 7, COL.ice, 0.6 * (1 - 0.6 * q));
    w.lineCap = 'round';
    for (let i = 0; i < 28; i++) {
      const a = i / 28 * TAU + hash1(i + 77) * 0.2, r0 = 60 + 200 * e * hash1(i + 11), r1 = r0 + (260 + 900 * hash1(i + 5)) * e;
      w.lineWidth = 1.5 + 1.5 * hash1(i + 3); w.strokeStyle = rgba(COL.iceX, 0.55 * (1 - 0.5 * q));
      w.beginPath(); w.moveTo(CX + Math.cos(a) * r0, CY + Math.sin(a) * r0); w.lineTo(CX + Math.cos(a) * r1, CY + Math.sin(a) * r1); w.stroke();
    }
    w.lineCap = 'butt';
  }
}

/* ---------- S5 -> S6 transition: the diagram becomes frame L01 ---------- */
function l01State(t) {
  const d0 = S6.Z[0] - zcam(t);
  const q0 = (S6.Z[0] - zcam(24.5)) / S6.dExit;
  const e = E.cubicInOut(seg(t, 24.5, 25.3));
  const Q = Math.exp(Math.log(q0) * (1 - e));
  const th = 15 * DEG * (e - E.cubicInOut(seg(t, 25.45, 25.95)));
  return { d0, Q, th };
}
function projL01(u, v, st) {       // plane-local (u, v; v down) -> camera space (X, Y, Z)
  return [u, v * Math.cos(st.th), st.d0 - v * Math.sin(st.th)];
}
function drawS5(t, R) {
  if (t < 24.5) { drawS5Content(R.w, R.g, t); return; }
  // the diagram keeps living in its own texture (pulses continue), camera frozen as it was at 24.5
  const cam = camera(24.5);
  resetCtx(pc0x, W, H); resetCtx(pg0x, W / 2, H / 2);
  const z = cam.zoom;
  pc0x.setTransform(z, 0, 0, z, 540 - 540 * z, 960 - 960 * z);
  pg0x.setTransform(z * 0.5, 0, 0, z * 0.5, (540 - 540 * z) * 0.5, (960 - 960 * z) * 0.5);
  drawS5Content(pc0x, pg0x, t);
  GLX.updatePlaneTex(PT0, PC0); GLX.updatePlaneTex(PTG0, PG0);
  drawTunnel(t, R, true);
  const st = l01State(t);
  // content quad (tilted ~15°, shrinks to ~40% and sits in the centre, fades before it grows large)
  const hw = S6.HW * st.Q, hh = S6.HH * st.Q;
  const corners = [projL01(-hw, -hh, st), projL01(hw, -hh, st), projL01(-hw, hh, st), projL01(hw, hh, st)];
  const aC = smooth((st.d0 - 760) / 420);
  if (aC > 0.003) R.planes.push({ tex: PT0, glowTex: PTG0, corners, alpha: aC, tint: [1, 1, 1], glow: 1, d: st.d0 });
  R.focal = S6.f;
  // L01's hairline frame, projected with the same tilt; it appears as the diagram settles into it
  const aF = E.expoOut(seg(t, 25.05, 25.4)) * (0.45 + 0.55 * smooth((st.d0 - S6.dExit) / 420));
  if (aF > 0.003 && st.d0 > S6.dExit * 0.9) {
    const w = R.w; R.screenOn(w);
    const pts = [];
    const HW = S6.HW, HH = S6.HH, r = 34;
    const push = (u, v) => { const c = projL01(u, v, st); pts.push([CX + S6.f * c[0] / c[2], CY + S6.f * c[1] / c[2]]); };
    for (const [cx, cy, a0] of [[HW - r, -HH + r, -Math.PI / 2], [HW - r, HH - r, 0], [-HW + r, HH - r, Math.PI / 2], [-HW + r, -HH + r, Math.PI]]) {
      for (let i = 0; i <= 8; i++) { const a = a0 + (i / 8) * Math.PI / 2; push(cx + r * Math.cos(a), cy + r * Math.sin(a)); }
    }
    w.lineWidth = 1.5; w.strokeStyle = rgbStr(s6Color(0), 0.62 * aF);
    w.beginPath(); pts.forEach((p, i) => i ? w.lineTo(p[0], p[1]) : w.moveTo(p[0], p[1])); w.closePath(); w.stroke();
  }
}
registerScene({ name: 'S5', t0: 20.0, t1: 26.0, draw: drawS5 });

function drawS6(t, R) { drawTunnel(t, R, false); }
registerScene({ name: 'S6', t0: 26.0, t1: 32.0, draw: drawS6 });
