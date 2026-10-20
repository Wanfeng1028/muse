'use strict';
/* ==========================================================================
   S9   THE WORD   40.00 – 44.00
   leaves / dust   40.00 – 60.00
   S10  montage    44.00 – 50.60
   ========================================================================== */
const BIG_F = FNT.song(620, 900);
const POEM_F = FNT.song(80, 700);
const S9D = {};
registerInit(() => {
  const ib = inkBox('凉', BIG_F);
  S9D.bigDx = -(ib.l + ib.r) / 2; S9D.bigDy = -(ib.t + ib.b) / 2;   // offsets that centre the ink at (0,0)
  S9D.bigInk = ib;
  const ibB = inkBox('凉', FNT.song(620, 700));
  S9D.boldDx = -(ibB.l + ibB.r) / 2; S9D.boldDy = -(ibB.t + ibB.b) / 2;
  const lf1 = FNT.song(44, 700);
  const w1 = textW('凉', lf1);
  const seg0 = S7D.segs[0];
  const lx = 660 - w1, lb = seg0.ly + cjkMid(lf1);
  const z = 1.04;
  const ib44 = inkBox('凉', lf1);
  const cx = lx + (ib44.l + ib44.r) / 2, cy = lb + (ib44.t + ib44.b) / 2;
  S9D.start = [540 + (cx - 540) * z, 960 + (cy - 960) * z];
  S9D.startScale = 44 * z / 620;
  // poem cells
  const pf = POEM_F;
  const mid = cjkMid(pf);
  S9D.poem = [];
  const add = (ch, col, row, tLand) => S9D.poem.push({ ch, x: col === 0 ? 640 : 480, yc: 540 + 92 * row, b: 540 + 92 * row + mid, tLand });
  add('凉', 0, 0, 40.0); add('︒', 0, 1, 44.75);
  const L = [['夏', 45.375], ['天', 45.435], ['终', 45.875], ['于', 45.935], ['把', 46.375], ['话', 46.75], ['说', 47.125], ['完', 47.185], ['了', 47.375], ['︒', 47.625]];
  L.forEach(([ch, tl], i) => add(ch, 1, i, tl));
  S9D.seal = buildSeal();
});

function bigGlyphState(t) {
  // position (screen/world centre of ink), scale relative to 620px, font blend
  const C = [540, 900];
  if (t < 44.0) {
    const e = E.expoOut(seg(t, 40.0, 40.2));
    const x = lerp(S9D.start[0], C[0], e), y = lerp(S9D.start[1], C[1], e);
    let s;
    if (t < 40.2) s = lerp(S9D.startScale, 1.04, E.expoOut(seg(t, 40.0, 40.2)));
    else { const u = t - 40.2; s = 1 + 0.04 * Math.cos(Math.PI * u / 0.15) * Math.exp(-u / 0.09); }
    if (t > 40.6) s *= 1 + 0.005 * (1 - Math.cos(TAU * (t - 40.6) / 2.6));
    return { x, y, s, black: seg(t, 40.0, 40.04) };
  }
  // 44.0–44.5: shrink into the first cell of the poem
  const p0 = S9D.poem[0];
  const e = E.expoInOut(seg(t, 44.0, 44.5));
  const s0 = 1 + 0.005 * (1 - Math.cos(TAU * (44.0 - 40.6) / 2.6));
  const ibP = inkBox('凉', POEM_F);
  const px = p0.x - textW('凉', POEM_F) / 2 + (ibP.l + ibP.r) / 2, py = p0.b + (ibP.t + ibP.b) / 2;
  return { x: lerp(C[0], px, e), y: lerp(C[1], py, e) - 60 * Math.sin(Math.PI * e), s: lerp(s0, 80 / 620, e), black: 1 - seg(t, 44.25, 44.5) };
}
function drawBigGlyph(w, g, t) {
  const st = bigGlyphState(t);
  const ib = S9D.bigInk;
  w.save(); w.translate(st.x, st.y); w.scale(st.s, st.s);
  // gradient fill gold -> amber -> persimmon (top to bottom of the ink box)
  const gr = w.createLinearGradient(0, ib.t + S9D.bigDy, 0, ib.b + S9D.bigDy);
  gr.addColorStop(0, COL.gold); gr.addColorStop(0.5, COL.amber); gr.addColorStop(1, COL.persimmon);
  const poemMix = seg(t, 44.2, 44.5);
  w.textAlign = 'left'; w.textBaseline = 'alphabetic';
  const drawIt = (font, a, dx, dy) => {
    if (a <= 0.001) return;
    w.globalAlpha = a; w.font = font;
    w.fillStyle = gr; w.fillText('凉', dx, dy);
    if (poemMix > 0) { w.globalAlpha = a * poemMix; w.fillStyle = mixHex(COL.wtext, COL.gold, 0.35); w.fillText('凉', dx, dy); w.globalAlpha = a; }
    if (st.s > 0.3) { w.lineWidth = 1.5 / st.s; w.strokeStyle = 'rgba(255,240,210,0.45)'; w.strokeText('凉', dx, dy); }
  };
  drawIt(BIG_F, st.black, S9D.bigDx, S9D.bigDy);
  drawIt(FNT.song(620, 700), 1 - st.black, S9D.boldDx, S9D.boldDy);
  w.restore(); w.globalAlpha = 1;
  // outer glow: mostly from the outline, so the fill keeps its gold -> persimmon gradient (no clipping to lemon)
  g.save(); g.translate(st.x, st.y); g.scale(st.s, st.s); g.font = BIG_F;
  const flash = Math.exp(-(t - 40.0) / 0.25);
  const ga = (t > 44 ? 1 - seg(t, 44.0, 44.4) * 0.6 : 1);
  g.globalAlpha = clamp(0.07 + 0.3 * flash) * ga; g.fillStyle = COL.amber; g.fillText('凉', S9D.bigDx, S9D.bigDy);
  g.globalAlpha = clamp(0.2 + 0.3 * flash) * ga; g.strokeStyle = COL.persimmon; g.lineWidth = 10 / Math.max(0.2, st.s); g.lineJoin = 'round';
  g.strokeText('凉', S9D.bigDx, S9D.bigDy);
  g.restore(); g.globalAlpha = 1;
}
function drawS9(t, R) {
  const w = R.w, g = R.g;
  drawBigGlyph(w, g, t);
  // impact rings
  for (const [d, lw, a0] of [[0, 2.5, 0.9], [0.06, 1.5, 0.5]]) {
    const q = seg(t, 40.0 + d, 40.5 + d);
    if (q <= 0 || q >= 1) continue;
    const r = 900 * E.expoOut(q);
    const v = 900 * (E.expoOut(seg(t + 0.004, 40.0 + d, 40.5 + d)) - E.expoOut(q)) / 0.004;
    blurRing(w, 540, 900, r, v, lw, COL.gold, a0 * (1 - E.quadIn(q)));
    blurRing(g, 540, 900, r, v, lw * 3, COL.amber, 0.6 * a0 * (1 - q));
  }
  // core flash at the impact
  const fl = t >= 40.0 ? Math.exp(-(t - 40.0) / 0.08) : 0;
  if (fl > 0.01) drawSprite(g, softDot('c', COL.gold), 540, 900, 560, 0.55 * fl);
}


/* ---------------- leaves & dust ---------------- */
const LEAF = { sprites: {} };
function ginkgoPath(x) {
  // unit leaf: petiole at (0,0.45), blade fans upward, notch at top centre
  x.beginPath();
  x.moveTo(0, 0.08);
  const N = 28;
  for (let i = 0; i <= N; i++) {
    const u = i / N, a = lerp(-1.02, 1.02, u);
    let r = 0.5 + 0.035 * Math.sin(u * 37) + 0.02 * Math.sin(u * 91);
    const notch = Math.exp(-Math.pow((u - 0.5) / 0.035, 2)) * 0.2;
    r -= notch;
    x.lineTo(Math.sin(a) * r, 0.08 - Math.cos(a) * r * 0.95);
  }
  x.closePath();
}
function buildLeafSprite(col, blur = 0) {
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  x.translate(s / 2, s * 0.56); x.scale(s * 0.9, s * 0.9);
  if (blur) x.filter = `blur(${(blur * 0.35).toFixed(2)}px)`;
  const base = hexRgb(col);
  const gr = x.createLinearGradient(0, -0.45, 0, 0.1);
  gr.addColorStop(0, rgbStr(mixRgb(base, [255, 244, 210], 0.35))); gr.addColorStop(1, rgbStr(mixRgb(base, [150, 80, 25], 0.18)));
  ginkgoPath(x); x.fillStyle = gr; x.fill();
  // veins
  x.strokeStyle = rgbStr(mixRgb(base, [90, 45, 10], 0.35), 0.35); x.lineWidth = 0.008;
  for (let i = 0; i < 9; i++) { const a = lerp(-0.9, 0.9, i / 8); x.beginPath(); x.moveTo(0, 0.08); x.lineTo(Math.sin(a) * 0.46, 0.08 - Math.cos(a) * 0.44); x.stroke(); }
  // petiole
  x.strokeStyle = rgbStr(mixRgb(base, [110, 60, 20], 0.4)); x.lineWidth = 0.035; x.lineCap = 'round';
  x.beginPath(); x.moveTo(0, 0.08); x.quadraticCurveTo(0.02, 0.26, -0.03, 0.4); x.stroke();
  return c;
}
function maplePath(x) {
  const pts = [];
  const lobes = [[-90, 1], [-45, 0.78], [-10, 0.95], [30, 0.62], [60, 0.78]];
  x.beginPath();
  const N = 90;
  for (let i = 0; i <= N; i++) {
    const a = -Math.PI / 2 + (i / N) * TAU;
    const deg = ((a * 180 / Math.PI) + 450) % 360 - 90;
    let r = 0.18;
    for (const [c, h] of [[-90, 0.5], [-30, 0.42], [30, 0.42], [-150, 0.36], [150, 0.36]]) {
      const dd = Math.abs(((deg - c + 540) % 360) - 180);
      r = Math.max(r, h * Math.exp(-dd * dd / 500) + 0.04 * Math.sin(i * 2.9) * Math.exp(-dd * dd / 1500));
    }
    if (Math.abs(((deg - 90 + 540) % 360) - 180) < 12) r = Math.max(r, 0.12);
    x.lineTo(Math.cos(a) * r, Math.sin(a) * r);
  }
  x.closePath();
}
function buildMapleSprite(col) {
  const s = 128, c = mkCanvas(s, s), x = c.getContext('2d');
  x.translate(s / 2, s / 2); x.scale(s * 0.9, s * 0.9);
  maplePath(x); x.fillStyle = col; x.fill();
  x.strokeStyle = 'rgba(60,15,5,0.35)'; x.lineWidth = 0.012;
  for (const a of [-90, -30, 30, -150, 150]) { const r = a * DEG; x.beginPath(); x.moveTo(0, 0); x.lineTo(Math.cos(r) * 0.4, Math.sin(r) * 0.4); x.stroke(); }
  x.strokeStyle = col; x.lineWidth = 0.03; x.beginPath(); x.moveTo(0, 0.05); x.lineTo(0.02, 0.45); x.stroke();
  return c;
}
registerInit(() => {
  const S = LEAF.sprites;
  S.g0 = buildLeafSprite(COL.gold); S.g1 = buildLeafSprite(COL.amber); S.g2 = buildLeafSprite('#FFE3A3'); S.g3 = buildLeafSprite('#D98E2B');
  S.m0 = buildMapleSprite(COL.persimmon); S.m1 = buildMapleSprite(COL.maple);
  S.b0 = buildLeafSprite(COL.amber, 18); S.b1 = buildLeafSprite(COL.gold, 22);
  const rng = mulberry32(4040);
  LEAF.leaves = [];
  for (let i = 0; i < 56; i++) {
    const maple = i >= 50;
    const a = rng() * TAU, sp = 420 + rng() * 950;
    LEAF.leaves.push({
      i, maple, spr: maple ? (i % 2 ? 'm0' : 'm1') : ['g0', 'g1', 'g2', 'g3'][i % 4],
      size: maple ? 22 + rng() * 18 : 10 + Math.pow(rng(), 1.4) * 24,
      x0: 540 + (rng() - 0.5) * 360, y0: 900 + (rng() - 0.5) * 380,
      vx: Math.cos(a) * sp, vy: Math.sin(a) * sp * 0.85 - 120, td: 0.28 + rng() * 0.22,
      vf: 55 + rng() * 70, amp: 22 + rng() * 50, fq: 0.5 + rng() * 0.7, ph: rng() * TAU,
      rot0: rng() * TAU, spin: (rng() - 0.5) * 2.4, ff: 0.18 + rng() * 0.35, fph: rng() * TAU, h: rng(),
    });
  }
  LEAF.dust = [];
  for (let i = 0; i < 150; i++) {
    const a = rng() * TAU, sp = 380 + rng() * 1500;
    LEAF.dust.push({ i, x0: 540 + (rng() - 0.5) * 300, y0: 900 + (rng() - 0.5) * 320, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp * 1.25, td: 0.3 + rng() * 0.35, vf: 18 + rng() * 44, amp: 10 + rng() * 30, fq: 0.25 + rng() * 0.5, ph: rng() * TAU, r: 1.2 + rng() * 2.2, tw: 1 + rng() * 3, h: rng() });
  }
  LEAF.fg = [];
  // edge lanes only (x < ~190 or > ~890): they never cross the poem columns or the S11 lines
  for (let i = 0; i < 4; i++) LEAF.fg.push({ i, x: [70, 1010, 120, 960][i], size: 120 + rng() * 60, delay: 0.3 + i * 0.9, vf: 38 + rng() * 22, amp: 22 + rng() * 18, fq: 0.25 + rng() * 0.2, ph: rng() * TAU, spin: (rng() - 0.5) * 0.8, spr: i % 2 ? 'b1' : 'b0' });
});
function warpT(t) {   // slowed particle time after 50s
  if (t <= 50) return t - 40;
  if (t <= 51.5) { const u = t - 50; return 10 + u - 0.15 * u * u; }
  return 10 + 1.5 - 0.3375 + 0.55 * (t - 51.5);
}
function density(t) { if (t < 50) return 1; if (t < 51.5) return lerp(1, 0.45, smooth((t - 50) / 1.5)); if (t < 56) return 0.45; return lerp(0.45, 0.25, smooth((t - 56) / 2)); }
function particlePos(p, t) {
  const tau = t - 40.0, T = warpT(t);
  const k = 1 - Math.exp(-tau / p.td);
  let x = p.x0 + p.vx * p.td * k + p.amp * Math.sin(TAU * p.fq * T + p.ph) * smooth(tau / 1.2);
  let y = p.y0 + p.vy * p.td * k + p.vf * Math.max(0, T - p.td * k);
  const c = Math.floor((y + 100) / (H + 200));
  if (c > 0) { y = mod(y + 100, H + 200) - 100; x += (hash2(p.i * 7 + 3, c) - 0.5) * 760; }
  x = mod(x + 60, W + 120) - 60;
  return [x, y, T];
}
function glyphClear(x, y, t) {   // keep the burst out of the glyph's face while it settles (leaves are behind it anyway)
  if (t >= 41.0) return 1;
  const r = Math.hypot((x - 540) / 340, (y - 900) / 330);
  return Math.max(smooth((r - 0.95) / 0.35), smooth((t - 40.6) / 0.4));
}
function drawParticles(t, R) {
  const w = R.w, g = R.g;
  R.screenOn(w); R.screenOn(g);
  const dens = density(t);
  // dust
  for (const d of LEAF.dust) {
    const [x, y, T] = particlePos(d, t);
    const a = clamp((dens - d.h) / 0.08) * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(T * d.tw + d.ph))) * glyphClear(x, y, t);
    if (a < 0.02 || y < -20 || y > H + 20) continue;
    drawSprite(w, softDot('d', COL.gold), x, y, d.r * 2.2, a * 0.9);
    drawSprite(g, softDot('c', COL.gold), x, y, d.r * 5, a * 0.5);
  }
  // leaves
  for (const L of LEAF.leaves) {
    const [x, y, T] = particlePos(L, t);
    const a = clamp((dens - L.h) / 0.08) * glyphClear(x, y, t);
    if (a < 0.02 || y < -60 || y > H + 60) continue;
    const flip = Math.cos(TAU * L.ff * T + L.fph);
    const rot = L.rot0 + L.spin * T;
    const spr = LEAF.sprites[L.spr];
    const sz = L.size * 1.35;
    w.save(); w.translate(x, y); w.rotate(rot); w.scale(Math.max(0.08, Math.abs(flip)) * Math.sign(flip || 1), 1);
    w.globalAlpha = a * (0.78 + 0.22 * Math.abs(flip));
    w.drawImage(spr, -sz / 2, -sz * 0.56, sz, sz);
    w.restore(); w.globalAlpha = 1;
    if (L.size > 20) drawSprite(g, softDot('c', L.maple ? COL.persimmon : COL.amber), x, y, L.size * 0.9, 0.18 * a);
  }
}
function drawFgLeaves(t, R) {
  if (t < 40.2) return;
  const w = R.w;
  R.screenOn(w);
  const dens = density(t);
  for (const f of LEAF.fg) {
    const tt = t - 40.0 - f.delay;
    if (tt < 0) continue;
    const T = warpT(t) - f.delay;
    let y = -200 + f.vf * T * 1.2;
    const c = Math.floor((y + 220) / (H + 440));
    y = mod(y + 220, H + 440) - 220;
    const x = f.x + f.amp * Math.sin(TAU * f.fq * T + f.ph) + (c > 0 ? (hash2(f.i, c) - 0.5) * 40 : 0);
    const a = 0.11 * clamp(tt / 0.8) * clamp((dens - 0.2 * f.i / 4) / 0.3) * smooth((y - 330) / 90);   // not in the HUD band
    if (a < 0.02) continue;
    w.save(); w.translate(x, y); w.rotate(f.ph + f.spin * T); w.scale(Math.cos(0.3 * T + f.ph) * 0.4 + 0.6, 1); w.globalAlpha = a;
    const sp = LEAF.sprites[f.spr];
    w.drawImage(sp, -f.size / 2, -f.size * 0.56, f.size, f.size);
    w.restore(); w.globalAlpha = 1;
  }
}
registerScene({ name: 'LEAVES', t0: 40.0, t1: 60.0, draw: drawParticles });   // behind the glyph and the text
registerScene({ name: 'S9', t0: 40.0, t1: 44.0, draw: drawS9 });

/* ---------------- seal ---------------- */
function buildSeal() {
  const s = 176, c = mkCanvas(s, s), x = c.getContext('2d');
  const rng = mulberry32(48);
  const cx = s / 2, cy = s / 2, half = 72;   // 144px at 2x = 72px
  x.save();
  x.beginPath();
  const N = 160;
  for (let i = 0; i < N; i++) {
    const u = i / N;
    let px, py;
    const side = Math.floor(u * 4), f = u * 4 - side;
    const r = 12;
    if (side === 0) { px = -half + r + f * (2 * half - 2 * r); py = -half; }
    else if (side === 1) { px = half; py = -half + r + f * (2 * half - 2 * r); }
    else if (side === 2) { px = half - r - f * (2 * half - 2 * r); py = half; }
    else { px = -half; py = half - r - f * (2 * half - 2 * r); }
    const n = Noise.n2(i * 0.35, 3.3) * 2.6 + (rng() - 0.5) * 1.6;
    const nx = side === 1 ? 1 : side === 3 ? -1 : 0, ny = side === 0 ? -1 : side === 2 ? 1 : 0;
    x.lineTo(cx + px + nx * n, cy + py + ny * n);
  }
  x.closePath();
  x.fillStyle = COL.seal; x.fill();
  x.restore();
  // uneven ink: lighter specks & slightly darker blotches
  for (let i = 0; i < 260; i++) {
    const px = cx + (rng() - 0.5) * 2 * half, py = cy + (rng() - 0.5) * 2 * half, r = 0.6 + rng() * 2.2;
    x.fillStyle = rng() < 0.7 ? `rgba(255,230,210,${0.05 + rng() * 0.12})` : `rgba(90,10,5,${0.06 + rng() * 0.1})`;
    x.beginPath(); x.arc(px, py, r, 0, TAU); x.fill();
  }
  // knocked-out 言
  const f = FNT.song(104, 700);
  const ib = inkBox('言', f);
  x.font = f; x.fillStyle = COL.wtext; x.textAlign = 'left';
  x.fillText('言', cx - (ib.l + ib.r) / 2, cy - (ib.t + ib.b) / 2);
  // erode the white strokes a little (stamp texture)
  x.globalCompositeOperation = 'source-atop';
  for (let i = 0; i < 90; i++) { x.fillStyle = `rgba(196,58,47,${0.15 + rng() * 0.3})`; x.beginPath(); x.arc(cx + (rng() - 0.5) * 110, cy + (rng() - 0.5) * 110, 0.8 + rng() * 1.8, 0, TAU); x.fill(); }
  x.globalCompositeOperation = 'source-over';
  return c;
}

/* ---------------- S10 ---------------- */
/* ---------- S10: every token is "manufactured" on its own landing cell ----------
   7 intervals, 7 motifs each (blade, strips, stars, arc fan, frames, char grid, lock), warm line art,
   all centred on the next token's landing cell. The last two intervals give each motif ~2 frames. */
const FB = [
  { S: 44.75, L: 45.375, tok: '夏天', rows: [0, 1] },
  { S: 45.375, L: 45.875, tok: '终于', rows: [2, 3] },
  { S: 45.875, L: 46.375, tok: '把', rows: [4] },
  { S: 46.375, L: 46.75, tok: '话', rows: [5] },
  { S: 46.75, L: 47.125, tok: '说完', rows: [6, 7] },
  { S: 47.125, L: 47.375, tok: '了', rows: [8] },
  { S: 47.375, L: 47.625, tok: '︒', rows: [9] },
];
const FB_X = 480;
function fbCellY(r) { return 540 + 92 * r; }
function fbState(t) {
  for (let j = 0; j < FB.length; j++) {
    const F = FB[j];
    const s0 = F.S + 0.015, s1 = F.L - 0.004;
    if (t < s0 || t >= s1) continue;
    const d = (s1 - s0) / 7, m = Math.min(6, Math.floor((t - s0) / d));
    return { j, m, p: (t - s0 - m * d) / d, d };
  }
  return null;
}
function fbColor(i) { return [COL.gold, COL.amber, COL.persimmon][mod(i, 3)]; }
function drawMotif(w, g, F, m, p, j, t) {
  const X = FB_X, Y = fbCellY(F.rows[0]) + (F.rows.length > 1 ? 46 : 0);
  const env = bump(p, 0, 0.14, 0.78, 1);
  const A = 0.52 * env;
  if (A <= 0.004) return;
  const seed = 101 + j * 13 + m;
  w.save(); g.save();
  w.lineCap = 'round'; w.lineJoin = 'round';
  switch (m) {
    case 0: { // blade: a vertical laser cuts through the landing cell
      const yh = lerp(Y - 820, Y + 820, E.cubicOut(clamp(p / 0.55))), yt = lerp(Y - 820, Y + 820, E.cubicIn(clamp((p - 0.1) / 0.8)));
      w.fillStyle = rgba(COL.gold, A * 1.4); w.fillRect(X - 1.25, yt, 2.5, Math.max(0, yh - yt));
      g.fillStyle = rgba(COL.amber, A); g.fillRect(X - 4, yt, 8, Math.max(0, yh - yt));
      const fl = bump(p, 0.25, 0.4, 0.5, 0.8);
      w.fillStyle = rgba(COL.gold, A * fl); w.fillRect(X - 260, Y - 1, 520, 2);
      w.strokeStyle = rgba(COL.amber, A); w.lineWidth = 1.5;
      rrect(w, X - 58 - 14 * p, Y - 44, 44, 88, 10); w.stroke(); rrect(w, X + 14 + 14 * p, Y - 44, 44, 88, 10); w.stroke();
      break;
    }
    case 1: { // strips: heat bars sweep across the landing row
      const head = lerp(-60, 1140, E.cubicOut(p));
      for (let r = -2; r <= 2; r++) {
        const yy = Y + r * 34;
        for (let k = 0; k < 72; k++) {
          const x = k * 15 + 6;
          if (x > head) break;
          const v = hash3(seed, r + 3, k), h = 6 + 24 * v;
          const nearHead = Math.exp(-(head - x) / 90);
          w.strokeStyle = rgba(fbColor(k + r), A * (0.35 + 0.65 * v) + 0.4 * A * nearHead);
          w.lineWidth = 3; w.beginPath(); w.moveTo(x, yy - h / 2); w.lineTo(x, yy + h / 2); w.stroke();
        }
      }
      g.fillStyle = rgba(COL.gold, A * 0.8); g.fillRect(head - 3, Y - 90, 6, 180);
      break;
    }
    case 2: { // stars converge onto the landing point
      const e = E.expoIn(clamp(p * 1.05));
      for (let i = 0; i < 64; i++) {
        const a = hash2(seed, i) * TAU, r0 = 260 + 560 * hash2(seed + 1, i);
        const r1 = r0 * (1 - e), r2 = r0 * (1 - Math.max(0, e - 0.12));
        const x1 = X + Math.cos(a) * r1, y1 = Y + Math.sin(a) * r1 * 1.25, x2 = X + Math.cos(a) * r2, y2 = Y + Math.sin(a) * r2 * 1.25;
        w.strokeStyle = rgba(fbColor(i), A * 0.9); w.lineWidth = 1.6;
        w.beginPath(); w.moveTo(x2, y2); w.lineTo(x1 + 0.01, y1); w.stroke();
        w.fillStyle = rgba(COL.gold, A); w.beginPath(); w.arc(x1, y1, 2.2, 0, TAU); w.fill();
      }
      w.strokeStyle = rgba(COL.gold, A); w.lineWidth = 1.5; w.beginPath(); w.arc(X, Y, 18 + 60 * (1 - e), 0, TAU); w.stroke();
      break;
    }
    case 3: { // arc fan blooming around the landing cell
      const open = E.expoOut(p);
      // a fan of concentric arcs opening upward-right from the cell, plus the spokes that carry it
      const a0 = -Math.PI * 0.42 + (j % 2 ? 0.25 : -0.1);
      const span = Math.PI * (0.18 + 0.5 * open);
      for (let i = 0; i < 9; i++) {
        const r = 70 + i * 58 * (0.6 + 0.4 * open);
        w.strokeStyle = rgba(fbColor(i), A * (1.1 - i * 0.07)); w.lineWidth = 1.5 + (i % 3 === 0 ? 1.2 : 0);
        w.beginPath(); w.arc(X, Y, r, a0 - span / 2, a0 + span / 2); w.stroke();
        w.beginPath(); w.arc(X, Y, r * 0.8, a0 + Math.PI - span * 0.35, a0 + Math.PI + span * 0.35); w.stroke();
      }
      w.lineWidth = 1.2; w.strokeStyle = rgba(COL.gold, A * 0.8);
      for (let i = -3; i <= 3; i++) { const a = a0 + (i / 3) * span / 2; w.beginPath(); w.moveTo(X + Math.cos(a) * 50, Y + Math.sin(a) * 50); w.lineTo(X + Math.cos(a) * (70 + 8 * 58 * (0.6 + 0.4 * open)), Y + Math.sin(a) * (70 + 8 * 58 * (0.6 + 0.4 * open))); w.stroke(); }
      break;
    }
    case 4: { // 3–4 frames rush at the camera out of the landing cell
      for (let i = 0; i < 4; i++) {
        const u = clamp(p * 1.35 - i * 0.12); if (u <= 0) continue;
        const sc = 0.07 + Math.pow(u, 2.2) * 2.3;
        const ww = 540 * sc, hh = 960 * sc;
        w.strokeStyle = rgba(fbColor(i), A * (1 - u) * 1.3); w.lineWidth = 1.5 + 1.5 * (1 - u);
        rrect(w, X - ww / 2, Y - hh / 2, ww, hh, 34 * sc); w.stroke();
      }
      break;
    }
    case 5: { // a band of the character grid flickers; the next character is lit
      const fr = Math.floor(t * FPS);
      w.font = FNT.pf(22, 400); w.textAlign = 'center';
      const tgt = F.tok[0];
      for (let r = -1; r <= 1; r++) for (let c = 0; c < 36; c++) {
        const x = 15 + c * 30, yy = Y + r * 30;
        if (Math.abs(x - X) < 16 && r === 0) continue;
        const v = hash3(seed + fr, r + 2, c);
        w.fillStyle = rgba(fbColor(c), A * (0.25 + 0.6 * v * v));
        w.fillText(GB1[Math.floor(hash3(seed, r + 5, c) * GB1.length)], x, yy + 8);
      }
      w.font = FNT.pf(30, 500); w.fillStyle = rgba(COL.gold, Math.min(1, A * 1.9)); w.fillText(tgt, X, Y + 11);
      g.globalAlpha = A; drawSprite(g, softDot('c', COL.gold), X, Y, 40, 0.9); g.globalAlpha = 1;
      w.textAlign = 'left';
      break;
    }
    case 6: { // probability column + laser lock on the landing cell (with the token's name)
      const cx = X + 190, top = Y - 300, hgt = 600;
      const cuts = [0, 0.34, 0.52, 0.64, 0.73, 0.8, 0.86, 0.9, 1];
      w.lineWidth = 1.5;
      for (let i = 0; i < cuts.length - 1; i++) {
        const y0 = top + hgt * cuts[i] + 1, y1 = top + hgt * cuts[i + 1] - 1;
        w.strokeStyle = rgba(fbColor(i), A * (i === 0 ? 1.4 : 0.8)); w.strokeRect(cx - 18, y0, 36, y1 - y0);
      }
      const le = E.expoOut(clamp(p / 0.5));
      const ly = lerp(top + hgt * 0.62, Y, le);
      w.fillStyle = rgba(COL.gold, Math.min(1, A * 1.8)); w.fillRect(X - 150, ly - 1.5, (cx + 60 - (X - 150)) * le, 3);
      g.fillStyle = rgba(COL.amber, A); g.fillRect(X - 150, ly - 5, (cx + 60 - (X - 150)) * le, 10);
      w.font = FNT.pf(28, 500); w.fillStyle = rgba(COL.gold, Math.min(1, A * 1.9)); w.textAlign = 'left';
      w.fillText(F.tok, cx + 34, top + hgt * 0.17 + 10);
      w.fillStyle = rgba(COL.amber, Math.min(1, A * 1.6)); w.beginPath(); w.moveTo(cx - 22, ly); w.lineTo(cx - 36, ly - 8); w.lineTo(cx - 36, ly + 8); w.closePath(); w.fill();
      break;
    }
  }
  w.restore(); g.restore();
}
function drawFbSlot(w, g, F, t, j) {
  // the landing slot of the token being made, with a faint ghost of the characters to come
  const a = E.expoOut(seg(t, F.S, F.S + 0.08)) * (1 - E.expoIn(seg(t, F.L - 0.06, F.L)));
  if (a <= 0.004) return;
  const y0 = fbCellY(F.rows[0]) - 44, h = 92 * F.rows.length - 4;
  w.save(); w.setLineDash([5, 6]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.gold, 0.55 * a);
  rrect(w, FB_X - 46, y0, 92, h, 12); w.stroke(); w.restore();
  const ghost = 0.18 + 0.22 * seg(t, F.S, F.L);
  w.font = POEM_F; w.lineWidth = 1; w.strokeStyle = rgba(COL.gold, ghost * a); w.textAlign = 'left';
  F.rows.forEach((r, i) => {
    const c = S9D.poem.find(o => o.x === 480 && Math.abs(o.yc - fbCellY(r)) < 1);
    if (c) w.strokeText(c.ch, c.x - textW(c.ch, POEM_F) / 2, c.b);
  });
}
function drawPoemMask(w, t) {
  const a = bump(t, 44.6, 44.9, 47.65, 48.2) * 0.5;
  if (a <= 0.004) return;
  const gx = w.createLinearGradient(380, 0, 760, 0);
  const c = hexRgb(COL.wbg);
  gx.addColorStop(0, `rgba(${c},0)`); gx.addColorStop(0.22, `rgba(${c},${a})`); gx.addColorStop(0.78, `rgba(${c},${a})`); gx.addColorStop(1, `rgba(${c},0)`);
  w.save(); w.fillStyle = gx; w.beginPath(); w.roundRect(390, 450, 360, 1000, 140); w.filter = 'blur(40px)'; w.fill(); w.restore(); w.filter = 'none';
}
function drawS10(t, R) {
  const w = R.w, g = R.g;
  const poemOut = 1 - E.cubicInOut(seg(t, 50.0, 50.38));
  if (t < 44.5) drawBigGlyph(w, g, t);
  // the machine, re-run on each landing cell, behind the poem (with a soft dark mask for legibility)
  if (t >= 44.7 && t < 47.7) {
    const st = fbState(t);
    if (st) drawMotif(w, g, FB[st.j], st.m, st.p, st.j, t);
  }
  drawPoemMask(w, t);
  if (t >= 44.7 && t < 47.7) { const st = fbState(t); if (st) drawFbSlot(w, g, FB[st.j], t, st.j); }
  // poem
  w.textAlign = 'left';
  for (const c of S9D.poem) {
    let a = 1, dy = 0, bl = 0, fl = 0;
    if (c.ch === '凉' && c.tLand === 40.0) { if (t < 44.5) continue; }
    else {
      const t0 = c.tLand - 0.08;
      if (t < t0) continue;
      const e = E.expoOut((t - t0) / 0.2);
      a = e; dy = -30 * (1 - e); bl = 8 * (1 - e);
      fl = t >= c.tLand ? Math.exp(-(t - c.tLand) / 0.14) : 0;
    }
    a *= poemOut;
    if (a <= 0.003) continue;
    const ww = textW(c.ch, POEM_F);
    const x = c.x - ww / 2;
    setFilter(w, bl);
    w.globalAlpha = a; w.font = POEM_F;
    w.fillStyle = c.ch === '凉' ? mixHex(COL.wtext, COL.gold, 0.35) : mixHex(COL.wtext, COL.gold, fl * 0.8);
    w.fillText(c.ch, x, c.b + dy);
    w.filter = 'none'; w.globalAlpha = 1;
    if (fl > 0.01) drawSprite(g, softDot('c', COL.amber), c.x, c.yc, 90, 0.9 * fl * poemOut);
    g.globalAlpha = 0.25 * a; g.font = POEM_F; g.fillStyle = COL.amber; g.fillText(c.ch, x, c.b + dy); g.globalAlpha = 1;
  }
  // seal
  if (t >= 47.9) {
    const sd = t < 48.0 ? E.cubicIn(seg(t, 47.9, 48.0)) : 1;
    const sc = t < 48.0 ? lerp(1.35, 1.0, sd) : 1 - 0.035 * springKick(t - 48.0, 5, 0.4);
    const a = (t < 48.0 ? sd : 1) * poemOut;
    const S = S9D.seal;
    w.save(); w.translate(380, 1350); w.scale(sc * 0.5, sc * 0.5); w.globalAlpha = a;
    w.drawImage(S, -S.width / 2, -S.height / 2); w.restore(); w.globalAlpha = 1;
    if (t >= 48.0) drawSprite(g, softDot('c', COL.persimmon), 380, 1350, 90, 0.7 * Math.exp(-(t - 48.0) / 0.2) * poemOut);
  }
}
registerScene({ name: 'S10', t0: 44.0, t1: 50.6, draw: drawS10 });
