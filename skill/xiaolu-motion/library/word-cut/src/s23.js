'use strict';
/* ==========================================================================
   S2  01 TOKENIZE   8.00 – 12.00
   S3  02 EMBED     12.00 – 15.50   (15.5–16.0 handled by the star-field module)
   ========================================================================== */
const TOK = ['用', '一个', '字', '，', '形容', '秋天', '。'];
const TOK_ID = ['44587', '48044', '19113', '3922', '104145', '86743', '1811'];
const TOK_START = [0, 1, 3, 4, 5, 7, 9];
const CUT_B = [1, 3, 4, 5, 7, 9];
const CUT_T = [8.50, 8.75, 9.00, 9.25, 9.50, 9.75];
const L2 = { x: 120, y0: 640, dy: 100, h: 84, r: 16, idX: 400, pad: 26 };
const CARD_FONT = FNT.pf(52, 500);
const SENT_FONT = FNT.pf(72, 400);
const ID_FONT = FNT.mono(40, 400);
const GAP = 24;
const S2D = {};            // derived layout

registerInit(() => {
  S2D.b72 = 960 + cjkMid(SENT_FONT);
  S2D.cards = TOK.map((tk, j) => {
    const tw = textW(tk, CARD_FONT);
    const cw = Math.max(104, tw + 2 * L2.pad);
    const yc = L2.y0 + L2.dy * j;
    let tx = L2.x + L2.pad, tb = yc + cjkMid(CARD_FONT);
    if (tk === '，' || tk === '。') { const ib = inkBox(tk, CARD_FONT); tx = L2.x + cw / 2 - (ib.l + ib.r) / 2; tb = yc - (ib.t + ib.b) / 2; }
    return { tk, tw, cw, yc, tx, tb };
  });
  S2D.idAdv = textW('0', ID_FONT);
  // S3 vectors
  const rng = mulberry32(777);
  S2D.NC = 42;
  S2D.vec = [];
  for (let i = 0; i < 7; i++) { const row = []; for (let k = 0; k < S2D.NC; k++) row.push(Math.tanh(gaussR(rng) * 0.85)); S2D.vec.push(row); }
  S2D.flash = []; for (let n = 0; n < 16; n++) S2D.flash.push({ i: Math.floor(rng() * 7), k: Math.floor(rng() * 38), te: 13.7 + rng() * 1.2 });
  S2D.nums = []; const used = new Set();
  for (let n = 0; n < 9; n++) {
    let i, k; do { i = 1 + Math.floor(rng() * 6); k = 2 + Math.floor(rng() * 34); } while (used.has(i * 100 + (k >> 2)));
    used.add(i * 100 + (k >> 2));
    S2D.nums.push({ i, k, te: 13.65 + n * 0.13 + rng() * 0.05 });
  }
  S2D.rowColor = S2D.vec.map((row, i) => { let m = 0; for (const v of row) m += v; m /= row.length; return mixRgb(CMAP(clamp(m * 5 + (i % 2 ? 0.55 : 0.7), -1, 1)), hexRgb(COL.ice), 0.45); });
});

function tokenOffsets(t) {
  const gaps = CUT_T.map(T => t < T ? 0 : GAP * spring(t - T, 3.0, 0.5));
  const total = gaps.reduce((a, b) => a + b, 0);
  const off = TOK_START.map(st => { let s = 0; CUT_B.forEach((b, k) => { if (b <= st) s += gaps[k]; }); return s - total / 2; });
  return { gaps, off };
}
function tokenOf(c) { let j = 0; for (let k = 0; k < TOK_START.length; k++) if (TOK_START[k] <= c) j = k; return j; }

/* ---------------- S2 ---------------- */
function drawS2(t, R) {
  const w = R.w, g = R.g;
  const flying = t >= 10.0;
  const O = tokenOffsets(Math.min(t, 10.0));
  // ------ sentence (before / during cuts)
  if (!flying) {
    w.font = SENT_FONT; w.fillStyle = COL.text; w.textAlign = 'left'; w.textBaseline = 'alphabetic';
    const [dx, dy] = drift(t, 31, 0.8, 0.4);
    for (let c = 0; c < SENT.length; c++) {
      const j = tokenOf(c);
      w.fillText(SENT[c], SENT_X0() + 72 * c + O.off[j] + dx, S2D.b72 + dy);
    }
    // anticipation ticks at future cut positions
    const ga = E.expoOut(seg(t, 8.2, 8.45));
    for (let k = 0; k < 6; k++) {
      const T = CUT_T[k];
      if (t >= T - 0.02) continue;
      const jl = tokenOf(CUT_B[k] - 1);
      const x = SENT_X0() + 72 * CUT_B[k] + O.off[jl];
      const a = ga * 0.7 * (0.8 + 0.2 * Math.sin(t * 9 + k));
      w.fillStyle = rgba(COL.cyan, a);
      w.fillRect(x - 0.75, 960 - 104, 1.5, 12); w.fillRect(x - 0.75, 960 + 92, 1.5, 12);
    }
  }
  // ------ blades + sparks
  for (let k = 0; k < 6; k++) {
    const T = CUT_T[k];
    if (t < T - 0.045 || t > T + 0.6) continue;
    const jl = tokenOf(CUT_B[k] - 1);
    const x = SENT_X0() + 72 * CUT_B[k] + O.off[jl] + O.gaps[k] / 2;
    const yT = 960 - 90, yB = 960 + 90;
    const yh = lerp(yT, yB, E.cubicOut(seg(t, T - 0.04, T + 0.04)));
    const yt = lerp(yT, yB, E.cubicIn(seg(t, T - 0.02, T + 0.1)));
    if (t < T + 0.1 && yh > yt + 0.5) {
      const gr = w.createLinearGradient(0, yt, 0, yh);
      gr.addColorStop(0, rgba(COL.ice, 0)); gr.addColorStop(1, COL.iceX);
      w.fillStyle = gr; w.fillRect(x - 1, yt, 2, yh - yt);
      g.fillStyle = rgba(COL.cyan, 0.9); g.fillRect(x - 3, yt, 6, yh - yt);
      drawSprite(g, softDot('c', COL.iceX), x, yh, 16, 0.9);
    }
    // afterglow of the cut
    if (t > T) {
      const a = Math.exp(-(t - T) / 0.16);
      w.fillStyle = rgba(COL.cyan, 0.5 * a); w.fillRect(x - 0.75, yT, 1.5, yB - yT);
      // horizontal flare at the text midline
      const fl = Math.exp(-(t - T) / 0.07);
      g.fillStyle = rgba(COL.cyan, 0.8 * fl); g.fillRect(x - 60 * fl - 10, 958, 120 * fl + 20, 4);
      drawSprite(g, softDot('c', COL.cyan), x, 960, 50, 0.7 * fl);
    }
    // sparks
    if (t >= T) {
      for (let s = 0; s < 9; s++) {
        const h1 = hash2(k * 31 + 7, s), h2 = hash2(k * 31 + 11, s), h3 = hash2(k * 31 + 13, s);
        const life = 0.28 + 0.24 * h3, tau = t - T;
        if (tau > life) continue;
        const side = s % 2 ? 1 : -1;
        const vx = side * (240 + 460 * h1), vy = (h2 - 0.5) * 420;
        const td = 0.14, kk = 1 - Math.exp(-tau / td);
        const ox = x, oy = 960 + (hash2(k * 31 + 17, s) - 0.5) * 130;
        const px = ox + vx * td * kk, py = oy + vy * td * kk + 160 * tau * tau;
        const sp = Math.exp(-tau / td);
        const lx = vx * sp * 0.022, ly = vy * sp * 0.022;
        const a = Math.pow(1 - tau / life, 1.6);
        w.strokeStyle = mixHex(COL.iceX, COL.cyan, tau / life, a); w.lineWidth = 1.5; w.lineCap = 'round';
        w.beginPath(); w.moveTo(px - lx - side * 1, py - ly); w.lineTo(px, py); w.stroke();
        drawSprite(g, softDot('c', COL.cyan), px, py, 6, a * 0.8);
      }
    }
  }
  // ------ flight into the list + cards
  if (flying) {
    for (let j = 0; j < 7; j++) {
      const cd = S2D.cards[j];
      const p = E.expoInOut(seg(t, 10.0 + 0.05 * j, 10.45 + 0.05 * j));
      const sx = SENT_X0() + 72 * TOK_START[j] + O.off[j], sb = S2D.b72;
      const x = lerp(sx, cd.tx, p) - 90 * Math.sin(Math.PI * p);
      const b = lerp(sb, cd.tb, p) + 10 * Math.sin(Math.PI * p);
      const s = lerp(1, 52 / 72, p);
      // card
      const q = E.expoOut(seg(p, 0.35, 1));
      if (q > 0) drawTokenCard(w, g, j, t, q, 1);
      // text (regular -> medium crossfade)
      w.save(); w.translate(x, b); w.scale(s, s);
      w.textAlign = 'left';
      if (p < 1) { w.globalAlpha = 1 - p; w.font = SENT_FONT; w.fillStyle = COL.text; w.fillText(cd.tk, 0, 0); }
      w.globalAlpha = p; w.font = FNT.pf(72, 500); w.fillStyle = COL.text; w.fillText(cd.tk, 0, 0);
      w.restore(); w.globalAlpha = 1;
    }
    drawIds(w, g, t, 1);
  }
}
function SENT_X0() { return 180; }

function drawTokenCard(w, g, j, t, q, alpha, opts = {}) {
  const cd = S2D.cards[j];
  const x = L2.x, y = cd.yc - L2.h / 2;
  const cw = lerp(cd.tw * 0.9, cd.cw, q), ch = lerp(52, L2.h, q);
  const cx = x + cd.cw / 2 + (1 - q) * 0;
  w.save(); w.globalAlpha = alpha * q;
  rrect(w, cx - cw / 2, cd.yc - ch / 2, cw, ch, L2.r);
  w.fillStyle = COL.card; w.fill();
  w.lineWidth = 1.5; w.strokeStyle = opts.stroke || COL.stroke; w.stroke();
  w.restore();
}
function cardTextDraw(w, j, alpha, font = CARD_FONT, color = COL.text) {
  const cd = S2D.cards[j];
  w.globalAlpha = alpha; w.font = font; w.fillStyle = color; w.textAlign = 'left';
  w.fillText(cd.tk, cd.tx, cd.tb); w.globalAlpha = 1;
}
function idRollPos(t, T, target) {
  const V = 24, tau = 0.18, s = T - t;
  if (s <= 0) return target + 0.22 * springKick(-s, 4.5, 0.45);
  if (s <= tau) return target - V * s * s / (2 * tau);
  return target - V * tau / 2 - V * (s - tau);
}
function drawIdDigits(w, str, x, yc, t, rowLock, alpha) {
  const n = str.length, adv = S2D.idAdv, lh = 46;
  const base = yc + 14;
  w.font = ID_FONT; w.textAlign = 'left';
  for (let j = 0; j < n; j++) {
    const T = rowLock - (n - 1 - j) * 0.045;
    const target = +str[j] + 100;
    const pos = idRollPos(t, T, target);
    const f0 = Math.floor(pos), fr = pos - f0;
    const cx = x + j * adv;
    w.save(); w.beginPath(); w.rect(cx - 2, yc - 30, adv + 4, 60); w.clip();
    for (let k = 0; k <= 1; k++) {
      const off = (k - fr) * lh;
      const a = alpha * (1 - Math.pow(Math.min(1, Math.abs(off) / lh), 1.3) * 0.85);
      if (a <= 0.01) continue;
      w.globalAlpha = a; w.fillText(String(mod(f0 + k, 10)), cx, base + off);
    }
    w.restore();
  }
  w.globalAlpha = 1;
}
function drawIds(w, g, t, alpha, opts = {}) {
  if (t < 10.5) return;
  const ap = E.expoOut(seg(t, 10.5, 10.65)) * alpha;
  const pulse = bump(t, 11.5, 11.62, 11.68, 12.0);
  for (let i = 0; i < 7; i++) {
    const cd = S2D.cards[i];
    const lock = 10.90 + 0.08 * i;
    // dashed leader
    const lx0 = L2.x + cd.cw + 14, lx1 = L2.idX - 14;
    const lp = E.expoOut(seg(t, 10.5 + 0.03 * i, 10.8 + 0.03 * i));
    if (lp > 0 && !opts.noLeader) {
      w.save(); w.setLineDash([3, 6]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.text2, 0.5 * alpha * (opts.leaderA ?? 1));
      w.beginPath(); w.moveTo(lx0, cd.yc); w.lineTo(lerp(lx0, lx1, lp), cd.yc); w.stroke(); w.restore();
    }
    if (opts.skipId && opts.skipId(i)) continue;
    const flash = t >= lock ? Math.exp(-(t - lock) / 0.12) : 0;
    w.fillStyle = mixHex(COL.cyan, COL.iceX, Math.max(flash, pulse * 0.8));
    drawIdDigits(w, TOK_ID[i], L2.idX, cd.yc, t, lock, ap);
    const gA = 0.45 * flash + 0.75 * pulse;
    if (gA > 0.01) {
      g.font = ID_FONT; g.fillStyle = COL.cyan; g.globalAlpha = gA * alpha; g.textAlign = 'left';
      g.fillText(TOK_ID[i], L2.idX, cd.yc + 14); g.globalAlpha = 1;
    }
  }
}
registerScene({ name: 'S2', t0: 8.0, t1: 12.0, draw: drawS2 });

/* ---------------- S3 ---------------- */
function vecVal(i, k, t) {
  const b = S2D.vec[i][k % S2D.NC];
  const amp = smooth(seg(t, 13.6, 14.2)) * (1 - smooth(seg(t, 14.9, 15.2)) * 0.3);
  if (amp <= 0) return b;
  return clamp(b * (1 - 0.45 * amp) + amp * 0.8 * Noise.n2(k * 0.19 - t * 1.05, i * 2.3 + 0.7), -1, 1);
}
function drawS3(t, R) {
  const w = R.w, g = R.g;
  const collapseAll = seg(t, 15.0, 15.5);
  // cards + labels
  for (let i = 0; i < 7; i++) {
    const cd = S2D.cards[i];
    const cp = E.expoInOut(seg(t, 15.0 + 0.035 * i, 15.3 + 0.035 * i));   // card -> label
    const cardA = 1 - E.expoOut(seg(t, 15.0 + 0.035 * i, 15.25 + 0.035 * i));
    if (cardA > 0.001) drawTokenCard(w, g, i, t, 1, cardA);
    // text: from card text to small label left of the point
    const lf = FNT.pf(24, 500);
    const lx1 = 407 - 18 - textW(cd.tk, lf), lb1 = cd.yc + cjkMid(lf);
    const x = lerp(cd.tx, lx1, cp), b = lerp(cd.tb, lb1, cp), s = lerp(1, 24 / 52, cp);
    w.save(); w.translate(x, b); w.scale(s, s); w.font = CARD_FONT; w.fillStyle = mixHex(COL.text, COL.ice, cp); w.fillText(cd.tk, 0, 0); w.restore();
    // leader
    const la = 1 - E.expoOut(seg(t, 15.0, 15.2));
    if (la > 0) {
      w.save(); w.setLineDash([3, 6]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.text2, 0.5 * la);
      w.beginPath(); w.moveTo(L2.x + cd.cw + 14, cd.yc); w.lineTo(L2.idX - 14, cd.yc); w.stroke(); w.restore();
    }
  }
  // IDs morph into the first cell
  for (let i = 0; i < 7; i++) {
    const cd = S2D.cards[i];
    const T = 12.25 + 0.125 * i;
    const m = E.expoIn(seg(t, T, T + 0.1));
    if (m < 1) {
      w.save(); w.translate(L2.idX, 0); w.scale(1 - 0.85 * m, 1); w.translate(-L2.idX, 0);
      w.globalAlpha = 1 - m; w.font = ID_FONT; w.fillStyle = COL.cyan; w.fillText(TOK_ID[i], L2.idX, cd.yc + 14);
      w.restore(); w.globalAlpha = 1;
    }
  }
  // dimension ruler above row 0
  const ra = E.expoOut(seg(t, 12.3, 12.8)) * (1 - E.expoOut(seg(t, 15.0, 15.25)));
  if (ra > 0) {
    const y = L2.y0 - 42;
    w.font = FNT.mono(18); w.textAlign = 'center';
    for (let m = 0; m <= 3; m++) {
      const k = m * 10, x = L2.idX + 17 * k + 7;
      const tk = E.expoOut(seg(t, 12.31 + 0.011 * k, 12.5 + 0.011 * k)) * ra;
      w.fillStyle = rgba(COL.text2, 0.8 * tk); w.fillRect(x - 0.75, y - 10, 1.5, 8);
      w.fillText(String(k), x, y - 18);
    }
    const tk = ra * E.expoOut(seg(t, 12.7, 13.0));
    w.fillStyle = rgba(COL.text2, 0.6 * tk); w.fillRect(L2.idX, y - 3, 1008 - L2.idX, 1.5);
    w.textAlign = 'right'; w.fillStyle = rgba(COL.text2, tk); w.fillText('……', 1008, y - 18);
    w.textAlign = 'left';
  }
  // heat strips
  for (let i = 0; i < 7; i++) {
    const cd = S2D.cards[i];
    const T = 12.25 + 0.125 * i;
    if (t < T + 0.04) continue;
    const cp = E.expoInOut(seg(t, 15.0 + 0.035 * i, 15.32 + 0.035 * i));
    for (let k = 0; k < S2D.NC; k++) {
      const hp = seg(t, T + 0.06 + 0.011 * k, T + 0.29 + 0.011 * k);
      if (hp <= 0) break;
      let h = 56 * E.backOut(hp, 1.4);
      let x = L2.idX + 17 * k;
      if (x > 1090) break;
      let v = vecVal(i, k, t);
      let col = CMAP(v);
      for (const f of S2D.flash) if (f.i === i && f.k === k) { const b = bump(t, f.te, f.te + 0.04, f.te + 0.08, f.te + 0.42); if (b > 0) { col = mixRgb(col, hexRgb(COL.iceX), b); drawSprite(g, softDot('c', COL.ice), x + 7, cd.yc, 26, b * 0.8); } }
      let a = 1;
      if (cp > 0) { x = L2.idX + (x - L2.idX) * (1 - cp); h = lerp(h, 14, cp); col = mixRgb(col, S2D.rowColor[i], cp); a = 1 - smooth(seg(cp, 0.75, 1)); }
      w.fillStyle = rgbStr(col, a);
      w.fillRect(x, cd.yc - h / 2, 14, h);
    }
    // collapsed point
    if (cp > 0.6) {
      const pa = smooth(seg(cp, 0.6, 1));
      const col = rgbStr(S2D.rowColor[i], pa);
      w.fillStyle = col; w.beginPath(); w.arc(407, cd.yc, 7, 0, TAU); w.fill();
      drawSprite(g, softDot('c', COL.cyan), 407, cd.yc, 30, 0.8 * pa);
    }
  }
  // floating numbers
  for (const nm of S2D.nums) {
    const tau = t - nm.te;
    if (tau < 0 || tau > 0.95) continue;
    const cd = S2D.cards[nm.i];
    const x = L2.idX + 17 * nm.k + 7;
    const v = vecVal(nm.i, nm.k, nm.te);
    const str = (v < 0 ? '−' : '') + Math.abs(v).toFixed(3);
    const a = bump(tau, 0, 0.12, 0.55, 0.95);
    const yy = cd.yc - 36 - 10 * E.expoOut(tau / 0.95);
    w.font = FNT.mono(18); w.textAlign = 'center'; w.fillStyle = rgba(COL.iceX, a);
    w.fillText(str, x, yy);
    w.fillStyle = rgba(COL.ice, 0.5 * a); w.fillRect(x - 0.75, yy + 6, 1.5, cd.yc - 28 - yy - 6);
    w.textAlign = 'left';
  }
}
registerScene({ name: 'S3', t0: 12.0, t1: 15.5, draw: drawS3 });
