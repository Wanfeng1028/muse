'use strict';
/* ==========================================================================
   Overlay: subtitles + HUD (not affected by camera zoom / shake)
   ========================================================================== */
const SUBS = [
  { tIn: 8.10, tOut: 9.95, text: '先把你的话，切成小块' },
  { tIn: 10.25, tOut: 11.75, text: '每一块，对应一个编号' },
  { tIn: 12.10, tOut: 15.35, text: '每个编号，展开成一长串数字' },
  { tIn: 16.10, tOut: 19.30, text: '意思相近的词，住得也近' },
  { tIn: 20.10, tOut: 22.20, text: '每个字，都会回头看前面的字' },
  { tIn: 22.50, tOut: 25.55, text: '下一个字，最在意「秋天」', hi: [9, 11] },
  { tIn: 26.10, tOut: 31.40, text: '一层，又一层' },
  { tIn: 32.25, tOut: 33.70, text: '再给所有可能的字，打个分' },
  { tIn: 34.00, tOut: 35.55, text: '绝大多数，几乎是零' },
  { tIn: 36.10, tOut: 39.20, text: '最后，掷一次骰子' },
  { tIn: 40.60, tOut: 42.20, text: '亿万次运算，只为这一个字', warm: true, center: true },
  { tIn: 42.50, tOut: 43.72, text: '下一个字，再走一遍', warm: true, center: true },
];
const SUB_FONT = FNT.pf(56, 600);

/* generic per-char "focus in" text block. opts: font, x, y, align, color(fn or str), stagger, dur, dy, blur, tIn, tOut, outDur */
function drawFocusText(ctx, str, t, o) {
  const L = layoutChars(str, o.font, o.ls || 0);
  let x0 = o.x;
  if (o.align === 'center') x0 = o.x - L.width / 2; else if (o.align === 'right') x0 = o.x - L.width;
  const stag = o.stagger ?? 0.022, dur = o.dur ?? 0.42, dy0 = o.dy ?? 18, bl0 = o.blur ?? 10;
  let outP = 0;
  if (o.tOut !== undefined && t >= o.tOut) outP = E.cubicIn(seg(t, o.tOut, o.tOut + (o.outDur ?? 0.26)));
  if (outP >= 1) return;
  ctx.font = o.font; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  for (const ch of L.chars) {
    const tau = t - o.tIn - ch.i * stag;
    if (tau <= 0) continue;
    const e = E.expoOut(tau / dur);
    const a = e * (1 - outP) * (o.alpha ?? 1);
    if (a <= 0.003) continue;
    const dy = dy0 * (1 - e) - 10 * outP;
    const bl = bl0 * (1 - e) + 6 * outP;
    setFilter(ctx, bl);
    ctx.globalAlpha = a;
    ctx.fillStyle = typeof o.color === 'function' ? o.color(ch.i, e) : o.color;
    ctx.fillText(ch.c, x0 + ch.x, o.y + dy);
  }
  ctx.filter = 'none'; ctx.globalAlpha = 1;
  return { x0, width: L.width, L };
}

function subScrim(ctx, t) {
  // soft dark band behind the subtitle area when the picture is busy
  let s = 0;
  s = Math.max(s, bump(t, 15.8, 16.3, 19.3, 19.7) * 0.85);  // star field
  s = Math.max(s, bump(t, 26.0, 26.4, 31.4, 31.8) * 0.5);   // planes
  s = Math.max(s, bump(t, 32.0, 32.25, 35.3, 35.8) * 0.9);  // score grid
  if (s <= 0.01) return;
  const g = ctx.createLinearGradient(0, 110, 0, 560);
  const c = hexRgb(COL.bg);
  g.addColorStop(0, `rgba(${c},0)`);
  g.addColorStop(0.18, `rgba(${c},${0.78 * s})`);
  g.addColorStop(0.72, `rgba(${c},${0.78 * s})`);
  g.addColorStop(1, `rgba(${c},0)`);
  ctx.fillStyle = g; ctx.fillRect(0, 110, W, 450);
}

function drawSubtitles(ctx, t) {
  for (const s of SUBS) {
    if (t < s.tIn || t > s.tOut + 0.3) continue;
    const warm = !!s.warm;
    const base = warm ? COL.wtext : COL.text;
    const hiCol = warm ? COL.gold : COL.cyan;
    drawFocusText(ctx, s.text, t, {
      font: SUB_FONT, x: s.center ? 540 : 72, y: s.center ? 1330 : 420, align: s.center ? 'center' : 'left',
      tIn: s.tIn, tOut: s.tOut,
      color: (i) => (s.hi && i >= s.hi[0] && i < s.hi[1]) ? hiCol : base,
    });
  }
}

/* ---------------- HUD ---------------- */
const CHAPTERS = [
  { n: '01', zh: '切分', en: 'TOKENIZE', t0: 8, t1: 12 },
  { n: '02', zh: '向量', en: 'EMBED', t0: 12, t1: 16 },
  { n: '03', zh: '语义', en: 'MEANING', t0: 16, t1: 20 },
  { n: '04', zh: '注意力', en: 'ATTENTION', t0: 20, t1: 26 },
  { n: '05', zh: '层层', en: 'LAYERS', t0: 26, t1: 32 },
  { n: '06', zh: '打分', en: 'SCORE', t0: 32, t1: 36 },
  { n: '07', zh: '采样', en: 'SAMPLE', t0: 36, t1: 40 },
];
const TOKEN_LAND = [40.0, 44.75, 45.375, 45.875, 46.375, 46.75, 47.125, 47.375, 47.625];
/* S6 pass times and displayed layer numbers */
const PASS_T = (() => { const a = [26.0, 26.5, 27.0, 27.5]; for (let i = 0; i < 8; i++) a.push(28.0 + 0.25 * i); for (let i = 0; i < 12; i++) a.push(30.0 + 0.125 * i); return a; })();
const LAYER_NUM = [1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 44, 48, 54, 60, 66, 72, 80, 88, 96];
const SEG_W = (936 - 6 * 8) / 7;

function modelTime(t) {
  if (t < 40.0) return Math.max(0, (t - 7.5) / 1000);
  // warm: 0.0325 per emitted token, rolling while the next token is being computed
  let v = 0.0325;
  for (let j = 1; j < TOKEN_LAND.length; j++) {
    const L = TOKEN_LAND[j], S = Math.max(TOKEN_LAND[j - 1], 44.5);
    if (t >= L) v = 0.0325 * (j + 1);
    else if (t > S) { v = 0.0325 * (j + E.sineInOut((t - S) / (L - S))); break; }
    else break;
  }
  return v;
}
function tokensLit(t) { let n = 0; for (const L of TOKEN_LAND) if (t >= L) n++; return n; }

function chapterAt(t) { for (let i = CHAPTERS.length - 1; i >= 0; i--) if (t >= CHAPTERS[i].t0) return i; return 0; }

function drawChapterLabel(ctx, ch, x, y, alpha, warm) {
  ctx.globalAlpha = alpha;
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  let cx = x;
  if (ch.n) {
    ctx.font = FNT.mono(24, 500); ctx.fillStyle = warm ? COL.amber : COL.cyan;
    ctx.fillText(ch.n, cx, y); cx += textW(ch.n, FNT.mono(24, 500)) + 16;
  }
  ctx.font = FNT.pf(28, 500); ctx.fillStyle = warm ? COL.wtext : COL.text;
  ctx.fillText(ch.zh, cx, y); cx += textW(ch.zh, FNT.pf(28, 500)) + 14;
  ctx.font = FNT.av(18, 600); ctx.fillStyle = warm ? COL.wtext2 : COL.text2; ctx.letterSpacing = (18 * 0.22).toFixed(2) + 'px';
  ctx.fillText(ch.en, cx, y);
  ctx.letterSpacing = '0px';
  ctx.globalAlpha = 1;
}

function hudColdAlpha(t) {
  if (t < 7.6 || t >= 40.6) return 0;
  return 1 - E.cubicInOut(seg(t, 40.0, 40.42));
}
function hudWarmAlpha(t) {
  if (t < 40.8 || t > 50.4) return 0;
  return E.expoOut(seg(t, 40.8, 41.2)) * (1 - E.cubicInOut(seg(t, 50.0, 50.4)));
}

function drawHUD(ctx, t) {
  const ac = hudColdAlpha(t), aw = hudWarmAlpha(t);
  if (ac > 0) {
    const ds = seg(t, 40.0, 40.2);                 // desaturate while fading under the warm front
    if (ds > 0) ctx.filter = `saturate(${(1 - ds).toFixed(3)})`;
    drawHUDCold(ctx, t, ac);
    ctx.filter = 'none';
  }
  if (aw > 0) drawHUDWarm(ctx, t, aw);
}
function hudWipe(t) { return E.expoOut(seg(t, 7.6, 8.0)); }

function drawHUDCold(ctx, t, alpha) {
  const wipe = hudWipe(t);
  const wx = lerp(40, 1060, wipe);
  ctx.save();
  if (wipe < 1) { ctx.beginPath(); ctx.rect(0, 0, wx, 320); ctx.clip(); }
  ctx.globalAlpha = alpha;
  // progress bar
  const ci = t >= 8 ? chapterAt(t) : -1;
  for (let i = 0; i < 7; i++) {
    const x = 72 + i * (SEG_W + 8);
    ctx.fillStyle = COL.hair; ctx.fillRect(x, 176, SEG_W, 3);
    let f = 0, a = 1;
    if (i < ci) { f = 1; a = 0.6; }
    else if (i === ci) { const c = CHAPTERS[i]; f = clamp((t - c.t0) / (c.t1 - c.t0)); }
    if (f > 0) { ctx.globalAlpha = alpha * a; ctx.fillStyle = COL.cyan; ctx.fillRect(x, 176, SEG_W * f, 3); ctx.globalAlpha = alpha; }
  }
  // chapter label (wipe between chapters, 350ms)
  const cur = t >= 8 ? chapterAt(t) : 0;
  const c = CHAPTERS[cur];
  const sw = t >= c.t0 ? seg(t, c.t0, c.t0 + 0.35) : 1;
  if (cur > 0 && sw < 1) {
    const e = E.expoInOut(sw), ex = lerp(60, 520, e);
    ctx.save(); ctx.beginPath(); ctx.rect(ex, 190, 600, 70); ctx.clip();
    drawChapterLabel(ctx, CHAPTERS[cur - 1], 72, 236, alpha, false); ctx.restore();
    ctx.save(); ctx.beginPath(); ctx.rect(0, 190, ex, 70); ctx.clip();
    drawChapterLabel(ctx, c, 72, 236, alpha, false); ctx.restore();
    ctx.globalAlpha = alpha * (1 - Math.abs(e - 0.5) * 2) * 0.9; ctx.fillStyle = COL.cyan; ctx.fillRect(ex - 1, 206, 2, 40); ctx.globalAlpha = alpha;
  } else drawChapterLabel(ctx, c, 72, 236, alpha, false);
  // timer
  drawTimer(ctx, t, alpha, false);
  // LAYER counter (S6)
  if (t >= 26.0 && t < 32.1) {
    let k = -1; for (let i = 0; i < PASS_T.length; i++) if (t >= PASS_T[i]) k = i;
    const la = alpha * E.expoOut(seg(t, 26.0, 26.3)) * (1 - seg(t, 31.9, 32.05));
    const n = k >= 0 ? LAYER_NUM[k] : 0;
    const tw = textW('t = 0.0000 s', FNT.mono(26));
    const xr = 1008 - tw - 28;
    ctx.globalAlpha = la; ctx.textAlign = 'right';
    const num = String(n).padStart(2, '0');
    const kick = k >= 0 ? Math.exp(-(t - PASS_T[k]) / 0.06) : 0;
    ctx.font = FNT.mono(26, 500); ctx.fillStyle = mixHex(COL.cyan, COL.iceX, kick);
    ctx.fillText(num, xr, 236);
    ctx.font = FNT.mono(18); ctx.fillStyle = COL.text2;
    ctx.fillText('LAYER', xr - textW(num, FNT.mono(26, 500)) - 10, 236);
    ctx.textAlign = 'left'; ctx.globalAlpha = 1;
  }
  ctx.restore();
  if (wipe > 0 && wipe < 0.999) { ctx.globalAlpha = (1 - wipe) * 0.9; ctx.fillStyle = COL.cyan; ctx.fillRect(wx - 1, 160, 2, 120); ctx.globalAlpha = 1; }
}

function drawTimer(ctx, t, alpha, warm) {
  const v = modelTime(t);
  const num = v.toFixed(4);
  ctx.globalAlpha = alpha; ctx.textAlign = 'right'; ctx.textBaseline = 'alphabetic';
  const f = FNT.mono(26);
  const sW = textW(' s', f), nW = textW(num, f);
  ctx.font = f;
  ctx.fillStyle = warm ? COL.wtext2 : COL.text2; ctx.fillText(' s', 1008, 236);
  ctx.fillStyle = warm ? COL.wtext : COL.text; ctx.fillText(num, 1008 - sW, 236);
  ctx.fillStyle = warm ? COL.wtext2 : COL.text2; ctx.fillText('t = ', 1008 - sW - nW, 236);
  ctx.font = FNT.pf(18); ctx.fillStyle = warm ? COL.wtext2 : COL.text2;
  ctx.fillText('慢放 1000 倍', 1008, 268);
  ctx.textAlign = 'left'; ctx.globalAlpha = 1;
}

function drawHUDWarm(ctx, t, alpha) {
  const lift = 8 * (1 - E.expoOut(seg(t, 40.8, 41.3)));
  ctx.save(); ctx.translate(0, lift);
  // 9 token dots
  const n = tokensLit(t);
  ctx.globalAlpha = alpha;
  ctx.fillStyle = rgba(COL.amber, 0.18); ctx.fillRect(72, 176.75, 936, 1.5);
  for (let i = 0; i < 9; i++) {
    const x = 72 + i * 117, y = 177.5;
    const lit = i < n;
    const pop = lit ? Math.exp(-(t - TOKEN_LAND[i]) / 0.12) : 0;
    ctx.beginPath(); ctx.arc(x, y, 5 + 3 * pop, 0, TAU);
    if (lit) { ctx.fillStyle = mixHex(COL.amber, COL.gold, pop); ctx.fill(); }
    else { ctx.fillStyle = COL.wbg; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = rgba(COL.amber, 0.45); ctx.stroke(); }
  }
  drawChapterLabel(ctx, { n: '', zh: '输出', en: 'OUTPUT' }, 72, 236, alpha, true);
  drawTimer(ctx, t, alpha, true);
  ctx.restore();
}

/* glow contributions of the overlay (drawn into the glow layer each sub-frame) */
function drawUIGlow(t, g) {
  const ac = hudColdAlpha(t);
  if (ac > 0 && t >= 8) {
    const ci = chapterAt(t), c = CHAPTERS[ci];
    const f = clamp((t - c.t0) / (c.t1 - c.t0));
    const x = 72 + ci * (SEG_W + 8) + SEG_W * f;
    const wipe = hudWipe(t);
    drawSprite(g, softDot('ui', COL.cyan), x, 177.5, 16, 0.55 * ac * wipe);
  }
  const aw = hudWarmAlpha(t);
  if (aw > 0) {
    const n = tokensLit(t);
    for (let i = 0; i < n; i++) {
      const pop = Math.exp(-(t - TOKEN_LAND[i]) / 0.15);
      drawSprite(g, softDot('ui', COL.amber), 72 + i * 117, 177.5, 18 + 20 * pop, (0.5 + 0.5 * pop) * aw);
    }
  }
}

function drawUI(t, ctx) {
  subScrim(ctx, t);
  drawHUD(ctx, t);
  drawSubtitles(ctx, t);
}
