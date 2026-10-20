'use strict';
/* ==========================================================================
   「快速提升剪辑网感的四件事」· 纸本手绘 faceless demo, 1080x1920 @ 30 fps.
   Every time below is read from the presenter's own voice (timing.json: syllable onsets of 口播.m4a),
   through A()/endOf()/slots(); nothing is typed in by hand.
   Layers: sheets (paper + ink) -> chapter cards / step tags -> pen -> subtitle (screen space).
   ========================================================================== */
const FPS = 30, T_END = 31.8, SLIDE = 0.28;
let TM = null;
const SHEETS = [], CARDS = [], CUES = [], QA = [], SHAKES = [], PUSHES = [], RECAP_PULSE = { t: 99 };

/* ------------------------------------------------------------------ timing anchors */
function A(str, near = 0) {
  const s = TM.text; let best = null;
  for (let i = s.indexOf(str); i >= 0; i = s.indexOf(str, i + 1)) {
    const t = TM.chars[i][1];
    if (!best || Math.abs(t - near) < Math.abs(best.t - near)) best = { i, t };
  }
  if (!best) throw new Error('no anchor ' + str);
  return best;
}
const at = (str, near) => A(str, near).t;
const endOf = (str, near) => { const a = A(str, near); return TM.chars[a.i + [...str].length - 1][2]; };
/* per-glyph writing slots from the spoken syllables; each glyph finishes at ~85% of its syllable */
const slots = (str, near, k = 0.85, shift = 0) => { const a = A(str, near); return [...str].map((c, j) => { const s = TM.chars[a.i + j][1] + shift, e = TM.chars[a.i + j][2] + shift; return [s, s + Math.max(0.07, (e - s) * k)]; }); };
const even = (n, t0, t1) => Array.from({ length: n }, (_, j) => [lerp(t0, t1, j / n), lerp(t0, t1, (j + 1) / n)]);

function cue(id, t, o = {}) { CUES.push({ id, at: +t.toFixed(3), ...o }); }
function shake(t, amp = 4) { SHAKES.push({ t, amp }); }
function qaText(sheet, box, t0, t1, label) { QA.push({ sheet: sheet ? sheet.id : null, box: box.map(v => Math.round(v)), t0: +t0.toFixed(3), t1: +t1.toFixed(3), label }); }

/* ------------------------------------------------------------------ sheets */
class Sheet {
  constructor(id, tIn, seed, page) { this.id = id; this.tIn = tIn; this.paper = makePaper(seed); this.items = []; this.page = page; this.rest = [932, 1178]; }
  offset(t) { return this.tIn <= 0 ? 0 : W * (1 - E.cubicOut(seg(t, this.tIn, this.tIn + SLIDE))); }
  add(item) { this.items.push(item); return item; }
  get tOut() { const n = SHEETS[this.id + 1]; return n ? n.tIn + SLIDE : 1e9; }
}
function sheetOf(t) { let s = SHEETS[0]; for (const x of SHEETS) if (t >= x.tIn) s = x; return s; }

/* item helpers ---------------------------------------------------- */
const S = (pts, o = {}) => new Stroke(pts, o);
function drawn(sheet, strokes, t0, t1, o = {}) { const d = new Drawing(strokes, t0, t1, { ...o, sheet }); if (!o.hidden) sheet.add(o.wrap ? o.wrap(d) : { draw: (ctx, t) => d.draw(ctx, t) }); return d; }
function written(sheet, str, x, y, o) {
  const w = new Writing(str, x, y, { ...o, sheet });
  if (!o.hidden) sheet.add({ draw: (ctx, t) => w.draw(ctx, t, o.fade ? 1 - seg(t, o.fade[0], o.fade[1]) : 1) });
  qaText(sheet, w.bbox(), w.t0, o.fade ? o.fade[1] : sheet.tOut, str);
  return w;
}
/* typeset word that pops in (scale about its centre, spring settle) */
function popWord(sheet, str, x, y, font, t0, o = {}) {
  logText(str, font);
  const L = layoutChars(str, font, o.ls ?? 0), ib = inkBox(str, font);
  const x0 = o.align === 'center' ? x - L.width / 2 : x, cx = x0 + L.width / 2, cy = y + (ib.t + ib.b) / 2;
  sheet.add({
    draw(ctx, t) {
      if (t < t0) return;
      const u = t - t0, sc = lerp(o.from ?? 1.55, 1, springOut(u / 0.42)), a = seg(u, 0, 0.05);
      ctx.save(); ctx.translate(cx, cy); ctx.scale(sc, sc); ctx.translate(-cx, -cy);
      ctx.globalAlpha = a * (o.alpha ?? 0.96); ctx.font = font; ctx.fillStyle = o.color || PP.ink; ctx.textBaseline = 'alphabetic';
      L.chars.forEach(ch => ctx.fillText(ch.c, x0 + ch.x, y)); ctx.restore();
    },
  });
  const box = [x0, y + ib.t, x0 + L.width, y + ib.b];
  qaText(sheet, box, t0, sheet.tOut, str);
  return { box, cx, cy, width: L.width };
}
/* any drawn group that pops in about (cx, cy) */
function popGroup(sheet, t0, cx, cy, fn, o = {}) {
  sheet.add({
    draw(ctx, t) {
      if (t < t0) return;
      const u = t - t0, sc = lerp(o.from ?? 0.2, 1, springOut(u / (o.dur ?? 0.36))), a = seg(u, 0, 0.04);
      ctx.save(); ctx.translate(cx, cy); ctx.scale(sc, sc); ctx.translate(-cx, -cy); ctx.globalAlpha = a; fn(ctx, t); ctx.restore();
    },
  });
}
function strokesFull(ctx, list, a = 1) { list.forEach(s => s.draw(ctx, 1, a)); }
function sketchBox(x, y, w, h, o = {}) {
  const r = mulberry32(o.seed || 3), ov = o.over ?? 7, j = () => (r() - 0.5) * 3;
  const sides = [[[x - ov * r(), y + j()], [x + w + ov * r(), y + j()]], [[x + w + j(), y - ov * r()], [x + w + j(), y + h + ov * r()]], [[x + w + ov * r(), y + h + j()], [x - ov * r(), y + h + j()]], [[x + j(), y + h + ov * r()], [x + j(), y - ov * r()]]];
  return sides.map((s, i) => S(sLine(s[0], s[1]), { ...o, seed: (o.seed || 3) * 7 + i, amp: o.amp ?? 1.1 }));
}
function arrowHeadStrokes(end, from, size, o = {}) {
  const ang = Math.atan2(end[1] - from[1], end[0] - from[0]), s1 = ang + Math.PI * 0.8, s2 = ang - Math.PI * 0.8;
  return [S(sQuad([end[0] + Math.cos(s1) * size, end[1] + Math.sin(s1) * size], [end[0] + Math.cos(s1) * size * 0.45, end[1] + Math.sin(s1) * size * 0.45 + 1], end), { ...o, seed: (o.seed || 1) + 71, amp: 0.4 }),
          S(sQuad(end, [end[0] + Math.cos(s2) * size * 0.5, end[1] + Math.sin(s2) * size * 0.5], [end[0] + Math.cos(s2) * size, end[1] + Math.sin(s2) * size]), { ...o, seed: (o.seed || 1) + 73, amp: 0.4 })];
}
function penCirclePts(cx, cy, rx, ry, o = {}) {
  const a0 = o.a0 ?? -2.2, turns = o.turns ?? 1.08, P = [], n = 90;
  for (let i = 0; i <= n; i++) { const t = a0 + TAU * turns * i / n, k = 1 + 0.03 * Math.sin(t * 2 + (o.seed || 1)) + 0.05 * i / n; P.push([cx + Math.cos(t) * rx * k, cy + Math.sin(t) * ry * k]); }
  return P;
}

/* ------------------------------------------------------------------ chapter cards -> step tags */
const CARD_W = 640, CARD_H = 300, TAG_S = 0.36, TAG_Y = 244, HOLD = [540, 790];
function makeCardBitmap(label, seed) {
  const pad = 40, c = mk(CARD_W + pad * 2, CARD_H + pad * 2), x = c.getContext('2d'), r = mulberry32(seed);
  x.translate(pad, pad);
  x.fillStyle = PP.card; x.beginPath(); x.roundRect(0, 0, CARD_W, CARD_H, 6); x.fill();
  x.save(); x.beginPath(); x.roundRect(0, 0, CARD_W, CARD_H, 6); x.clip();
  for (let yy = 118; yy < CARD_H; yy += 44) { x.strokeStyle = rgba(PP.blue, 0.32); x.lineWidth = 1.4; x.beginPath(); x.moveTo(0, yy); x.lineTo(CARD_W, yy + 0.5); x.stroke(); }
  x.strokeStyle = rgba(PP.red, 0.55); x.lineWidth = 2; x.beginPath(); x.moveTo(0, 74); x.lineTo(CARD_W, 74.5); x.stroke();
  for (let i = 0; i < 900; i++) { x.fillStyle = `rgba(120,100,70,${0.03 + r() * 0.04})`; x.fillRect(r() * CARD_W, r() * CARD_H, 1 + r() * 2, 1); }
  x.restore();
  const f = FT.kai(100); logText(label, f);
  x.font = f; x.fillStyle = PP.ink; x.globalAlpha = 0.95; x.fillText(label, 42, 212); x.globalAlpha = 1;
  // washi tape
  x.save(); x.translate(CARD_W / 2 - 20, -6); x.rotate(3 * DEG); x.fillStyle = 'rgba(232,219,186,0.82)';
  x.beginPath(); x.moveTo(-86, -20); for (let k = 0; k <= 6; k++) x.lineTo(-86 + (k % 2) * 4, -20 + k * 40 / 6); x.lineTo(86, 20); for (let k = 0; k <= 6; k++) x.lineTo(86 - (k % 2) * 4, 20 - k * 40 / 6); x.closePath(); x.fill(); x.restore();
  return { c, pad };
}
class Card {
  constructor(o) {
    Object.assign(this, o);
    this.bmp = makeCardBitmap(o.label, 40 + o.step);
    this.stamp = makeStamp(o.ch, 216, 7 + o.step);
    this.slotX = 70 + 115 + (o.step - 1) * 238;
    this.tagRot = [-2.2, 1.6, -1.2, 2.0][o.step - 1] * DEG;
    this.rot = [-2.5, 1.8, -1.6, 2.2][o.step - 1] * DEG;
  }
  pose(t) {
    if (t < this.tDrop) return null;
    if (t < this.tLand) {             // falling onto the page
      const u = seg(t, this.tDrop, this.tLand), e = E.quadIn(u);
      return { x: HOLD[0] + (1 - e) * 40, y: lerp(-260, HOLD[1], e), s: lerp(1.08, 1, e), rot: this.rot + (1 - e) * 11 * DEG, lift: 1 - e, a: 1 };
    }
    if (t < this.tFly) {              // resting (tiny settle after the landing)
      const u = t - this.tLand, b = Math.exp(-u * 18) * Math.sin(u * 40) * 5;
      return { x: HOLD[0], y: HOLD[1] - b, s: 1, rot: this.rot, lift: 0, a: 1 };
    }
    const f1 = this.tFly + 0.38;
    let x, y, s, rot, a = 1;
    if (t < f1) {
      const u = E.cubicInOut(seg(t, this.tFly, f1));
      x = lerp(HOLD[0], this.slotX, u); y = lerp(HOLD[1], TAG_Y, u) - Math.sin(u * Math.PI) * 60; s = lerp(1, TAG_S, u); rot = lerp(this.rot, this.tagRot, u);
      return { x, y, s, rot, lift: Math.sin(u * Math.PI), a };
    }
    x = this.slotX; y = TAG_Y; s = TAG_S; rot = this.tagRot;
    if (this.tDim && t > this.tDim) { a = lerp(1, 0.5, seg(t, this.tDim, this.tDim + 0.3)); s = lerp(TAG_S, TAG_S * 0.92, seg(t, this.tDim, this.tDim + 0.3)); }
    if (t > this.tExit) { const u = E.cubicIn(seg(t, this.tExit, this.tExit + 0.3)); y = lerp(TAG_Y, -140, u); }
    return { x, y, s, rot, lift: 0, a };
  }
  draw(ctx, t) {
    const p = this.pose(t); if (!p || p.y < -200) return;
    ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.scale(p.s, p.s); ctx.globalAlpha = p.a;
    // shadow grows with height
    ctx.save(); ctx.filter = `blur(${8 + p.lift * 14}px)`; ctx.fillStyle = `rgba(80,60,35,${0.26 - p.lift * 0.08})`;
    ctx.fillRect(-CARD_W / 2 + 10 + p.lift * 18, -CARD_H / 2 + 14 + p.lift * 26, CARD_W - 8, CARD_H - 6); ctx.restore();
    ctx.drawImage(this.bmp.c, -CARD_W / 2 - this.bmp.pad, -CARD_H / 2 - this.bmp.pad);
    if (t >= this.tStamp) {           // stamp: contact frame = tStamp
      const u = t - this.tStamp, sc = u < 0.05 ? lerp(1.22, 0.96, u / 0.05) : lerp(0.96, 1, E.cubicOut((u - 0.05) / 0.1));
      const sx = CARD_W / 2 - 42 - 108, sy = 8;
      ctx.save(); ctx.translate(sx, sy); ctx.rotate(-4 * DEG); ctx.scale(sc, sc);
      ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = p.a * 0.95;
      ctx.drawImage(this.stamp.c, -this.stamp.size / 2 - this.stamp.pad, -this.stamp.size / 2 - this.stamp.pad); ctx.restore();
    }
    ctx.restore();
  }
}

/* ------------------------------------------------------------------ build */
function build(timing) {
  TM = timing; TM.text = TM.chars.map(c => c[0]).join('');
  PEN_JOBS.length = 0;
  const tIn = [0, endOf('四件事', 3) - 0.02, at('第二', 9.5) - 0.32, at('第三', 17.2) - 0.32, at('第四', 22.6) - 0.32, endOf('直接用', 27.1) + 0.04];
  tIn.forEach((t, i) => SHEETS.push(new Sheet(i, t, 11 + i * 7, i + 1)));
  sceneHook(SHEETS[0]);
  sceneGuess(SHEETS[1]);
  sceneTakeApart(SHEETS[2]);
  sceneComments(SHEETS[3]);
  sceneSave(SHEETS[4]);
  sceneRecap(SHEETS[5]);
  // sheet transitions: paper slide
  SHEETS.slice(1).forEach(s => cue('whoosh_mid', s.tIn, { align: 'motion', gain_db: -9, pan: -0.3, params: { dur: 0.45, travel: -0.8, bright: 0.35 } }));
  CARDS.forEach((c, i) => { if (CARDS[i + 1]) c.tDim = CARDS[i + 1].tFly + 0.3; c.tExit = SHEETS[5].tIn - 0.02 + i * 0.04; });
  PEN_JOBS.sort((a, b) => a.t0 - b.t0);
  return { sheets: SHEETS.length, penJobs: PEN_JOBS.length, cues: CUES.length };
}

function chapter(step, label, ch, tLand, tStamp, tFly) {
  const c = new Card({ step, label, ch, tDrop: tLand - 0.2, tLand, tStamp, tFly });
  CARDS.push(c);
  cue('whoosh_fast', c.tDrop, { align: 'motion', gain_db: -8, params: { dur: 0.22, travel: 0.2, bright: 0.4 } });
  cue('land', tLand, { gain_db: -5, params: { bright: 0.35 } });
  cue('stamp', tStamp, { gain_db: -1 });
  shake(tStamp, 5);
  cue('whoosh_fast', tFly, { align: 'motion', gain_db: -11, pan: -0.4, params: { dur: 0.36, travel: -0.6, bright: 0.45 } });
  qaText(null, [HOLD[0] - CARD_W / 2, HOLD[1] - CARD_H / 2, HOLD[0] + CARD_W / 2, HOLD[1] + CARD_H / 2], tLand, tFly, 'card:' + label);
  return c;
}

/* ================================================================== 0 · hook */
function sceneHook(sh) {
  drawn(sh, [S(sLine([70, 300], [1010, 299]), { w: 1.8, seed: 9, amp: 0.8, wl: 160, alpha: 0.42 })], 0.03, 0.34);
  written(sh, '想快速提升', 108, 452, { font: FT.kai(80), size: 80, color: PP.ink2, rot: -1.2, slots: slots('想快速提升', 0.8) });
  written(sh, '剪辑', 100, 692, { font: FT.kai(172), size: 172, slots: slots('剪辑', 1.7, 0.9) });
  const tW = at('网感', 2.0);
  const hl = new Highlight(116, 724, 948, 118, { t0: tW + 0.1, dur: 0.24, seed: 21 });
  sh.add({ draw: (ctx, t) => hl.draw(ctx, t) });
  popWord(sh, '网感', 120, 1010, FT.heavy(300), tW, { ls: 4, from: 1.35 });
  cue('reverse_whoosh', tW, { align: 'end', gain_db: -8, params: { dur: 0.35 } });
  cue('hit', tW, { gain_db: -4, params: { bright: 0.45 } });
  shake(tW, 6);
  written(sh, '就练', 108, 1188, { font: FT.kai(70), size: 70, color: PP.ink2, slots: slots('就练', 2.4) });
  // four empty boxes: the four things
  const a4 = A('四件事', 2.7), tb = [TM.chars[a4.i][1], TM.chars[a4.i + 1][1], TM.chars[a4.i + 2][1], TM.chars[a4.i + 2][1] + 0.13];
  tb.forEach((t, k) => {
    const x = 300 + k * 140, y = 1100, box = sketchBox(x, y, 100, 100, { w: 3.4, seed: 60 + k * 5, over: 7 });
    const num = String(k + 1), f = FT.kai(62); logText(num, f);
    popGroup(sh, t, x + 50, y + 50, (ctx) => { strokesFull(ctx, box); ctx.font = f; ctx.fillStyle = PP.ink2; ctx.textAlign = 'center'; ctx.fillText(num, x + 50, y + 72); ctx.textAlign = 'left'; });
    cue('pop_soft', t + 0.03, { gain_db: -7, params: { pitch: [0, 2, 4, 7][k] } });
    qaText(sh, [x - 8, y - 8, x + 108, y + 108], t, sh.tOut, 'box' + num);
  });
}

/* ================================================================== 1 · 猜 */
function sceneGuess(sh) {
  const tLand = at('第一', 3.5) + 0.04, tSt = at('猜', 4.2) + 0.03, tFly = endOf('先猜', 4.3) + 0.06;
  chapter(1, '第一步', '猜', tLand, tSt, tFly);
  drawnHeader(sh);
  // phone
  const PX = 130, PY = 420, PW = 420, PH = 760;
  const t0 = at('刷到', 4.9) + 0.02, tPlay = at('频', 5.3), tData = at('先别看', 5.4);
  const phone = [S(sRoundRect(PX, PY, PW, PH, 54), { w: 4.2, seed: 101, amp: 1.2, wl: 140 }),
                 S(sLine([PX + PW / 2 - 44, PY + 26], [PX + PW / 2 + 44, PY + 26]), { w: 5, seed: 102, amp: 0.3 }),
                 S(sRoundRect(PX + 18, PY + 50, PW - 36, PH - 100, 20, 0.02), { w: 1.8, seed: 103, amp: 0.8, alpha: 0.55 })];
  drawn(sh, phone, t0, tPlay);
  const pc = [PX + 170, PY + 360];
  drawn(sh, [S(sPoly([[pc[0] - 30, pc[1] - 42], [pc[0] + 44, pc[1]], [pc[0] - 30, pc[1] + 42], [pc[0] - 30, pc[1] - 44]]), { w: 3.6, seed: 104, amp: 0.6 })], tPlay, tData - 0.02);
  // caption scribbles (pre-printed UI, pop with the data column)
  const cap = [S(sLine([PX + 40, PY + PH - 118], [PX + 250, PY + PH - 116]), { w: 3, seed: 105, amp: 1.4, color: PP.ink2 }),
               S(sLine([PX + 40, PY + PH - 84], [PX + 190, PY + PH - 83]), { w: 3, seed: 106, amp: 1.4, color: PP.ink2 })];
  // data column: heart / comment / star + numbers
  const DX = PX + PW - 70, rows = [[PY + 330, '2.3万'], [PY + 450, '812'], [PY + 570, '1.1万']];
  const icons = [heartPts(DX, rows[0][0], 30), bubblePts(DX, rows[1][0], 30), starPts(DX, rows[2][0], 30)].map((p, k) => S(p, { w: 3.2, seed: 110 + k, amp: 0.4 }));
  const nf = FT.sans(32);
  rows.forEach(([y, s]) => logText(s, nf));
  popGroup(sh, tData, DX, PY + 450, (ctx) => {
    strokesFull(ctx, icons); strokesFull(ctx, cap);
    ctx.font = nf; ctx.fillStyle = PP.ink; ctx.textAlign = 'center'; rows.forEach(([y, s]) => ctx.fillText(s, DX, y + 62)); ctx.textAlign = 'left';
  }, { from: 0.85, dur: 0.3 });
  cue('pop_soft', tData + 0.03, { gain_db: -9, params: { pitch: 2 } });
  rows.forEach(([y, s]) => qaText(sh, [DX - 46, y + 38, DX + 46, y + 70], tData, sh.tOut, s));
  // sticky note slaps over the numbers ("先别看数据"), gets a "?", later peels off ("对答案")
  const tSlap = at('别看', 5.7) + 0.04, tQ0 = at('数据', 5.9), tQ1 = endOf('数据', 6.2) - 0.02, tPeel = at('对答案', 8.5) - 0.06;
  const N = { x: DX - 78, y: PY + 250, w: 156, h: 420 };
  const q = new Drawing([S(sCubic([N.x + 48, N.y + 150], [N.x + 50, N.y + 70], [N.x + 132, N.y + 80], [N.x + 104, N.y + 170]), { w: 7, seed: 120, amp: 0.8 }),
                         S(sQuad([N.x + 104, N.y + 170], [N.x + 80, N.y + 200], [N.x + 80, N.y + 244]), { w: 7, seed: 121, amp: 0.6 }),
                         S(sEllipse(N.x + 80, N.y + 290, 7, 7, 0, TAU * 1.1), { w: 7, seed: 122, amp: 0.2 })], tQ0, tQ1, { sheet: sh });
  sh.add({
    draw(ctx, t) {
      if (t < tSlap - 0.1) return;
      let dx = 0, dy = 0, rot = 3 * DEG, sc = 1, a = 1;
      if (t < tSlap) { const u = seg(t, tSlap - 0.1, tSlap); sc = lerp(1.25, 1, E.quadIn(u)); a = u; }
      if (t > tPeel) { const u = E.quadIn(seg(t, tPeel, tPeel + 0.3)); dx = u * 560; dy = -u * 760; rot += u * 38 * DEG; }
      if (t > tPeel + 0.3) return;
      const cx = N.x + N.w / 2, cy = N.y + N.h / 2;
      ctx.save(); ctx.globalAlpha = a; ctx.translate(cx + dx, cy + dy); ctx.rotate(rot); ctx.scale(sc, sc); ctx.translate(-cx, -cy);
      ctx.save(); ctx.filter = 'blur(6px)'; ctx.fillStyle = 'rgba(80,60,30,0.22)'; ctx.fillRect(N.x + 6, N.y + 10, N.w, N.h); ctx.restore();
      ctx.fillStyle = PP.note; ctx.fillRect(N.x, N.y, N.w, N.h);
      ctx.fillStyle = 'rgba(200,160,60,0.18)'; ctx.fillRect(N.x, N.y, N.w, 26);
      q.draw(ctx, t);
      ctx.restore();
    },
  });
  cue('impact_soft', tSlap, { gain_db: -9, params: { bright: 0.3, dur: 0.4 } });
  cue('pluck', tQ1 - 0.05, { gain_db: -10, params: { note: 'D5', dur: 0.8 } });
  // flames: how hot could it get
  const base = 905, fl = [[650, 88], [780, 138], [925, 196]];
  const tf = [at('估', 6.7), at('它', 6.95), at('能', 7.14), endOf('火', 7.35)];
  const flameStrokes = fl.map(([x, h], k) => flamePts(x, base, h).map((p, j) => S(p, { w: j ? 2.4 : 3.6, seed: 130 + k * 3 + j, amp: 0.7 })));
  flameStrokes.forEach((st, k) => {
    const d = new Drawing(st, tf[k], tf[k + 1] - 0.02, { sheet: sh });
    const [x, h] = fl[k], tDone = tf[k + 1];
    sh.add({
      draw(ctx, t) {
        const fa = seg(t, tDone - 0.02, tDone + 0.12);
        if (fa > 0) {       // yellow wash inside the flame once it is drawn
          ctx.save(); ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = rgba(PP.hl, 0.55 * fa);
          const P = flamePts(x, base, h)[0]; ctx.beginPath(); P.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.fill(); ctx.restore();
        }
        if (k === 2 && t > tDone) {   // the big one pulses on "火"
          const u = t - tDone, sc = 1 + 0.12 * Math.exp(-u * 7) * Math.sin(u * 16 + 0.3);
          ctx.save(); ctx.translate(x, base); ctx.scale(sc, sc); ctx.translate(-x, -base); d.draw(ctx, t); ctx.restore();
        } else d.draw(ctx, t);
      },
    });
  });
  cue('hit', tf[3], { gain_db: -12, params: { bright: 0.55 } });
  shake(tf[3], 3);
  drawn(sh, [S(sLine([588, base + 12], [1004, base + 13]), { w: 2.6, seed: 140, amp: 0.8, alpha: 0.8 })], at('到什么', 7.44), at('什么', 7.56) + 0.02);
  // the guess: circle the middle flame, write 我猜
  const tg0 = at('什么', 7.56) + 0.03, tg1 = endOf('程度', 8.0) - 0.08;
  drawn(sh, [S(penCirclePts(780, base - 66, 84, 104, { seed: 5, a0: -2.0 }), { w: 4.2, seed: 141, amp: 1.1, color: PP.red })], tg0, tg1);
  written(sh, '我猜', 730, 990, { font: FT.kai(54), size: 54, color: PP.red, rot: -3, slots: even(2, tg1 + 0.02, at('再去', 8.32) - 0.02) });
  // the answer: note peels off, circle the real number, tick the big flame
  cue('whoosh_fast', tPeel, { align: 'motion', gain_db: -8, pan: 0.5, params: { dur: 0.3, travel: 0.8, bright: 0.55 } });
  const ta0 = at('答案', 8.62), ta1 = endOf('答案', 8.9);
  drawn(sh, [S(penCirclePts(DX, rows[0][0] + 54, 66, 32, { seed: 9, a0: -2.6 }), { w: 4, seed: 150, amp: 0.9, color: PP.red })], ta0, ta1);
  const tick = [S(sPoly([[890, 778], [918, 812], [978, 722]]), { w: 6, seed: 151, amp: 0.6, color: PP.red })];
  drawn(sh, tick, ta1 + 0.01, ta1 + 0.22);
  cue('pluck', ta1 + 0.2, { gain_db: -8, params: { note: 'A5', dur: 1.0 } });
}
function drawnHeader(sh) {   // pre-printed rule on every later sheet
  const st = S(sLine([70, 300], [1010, 299]), { w: 1.8, seed: 9 + sh.id, amp: 0.8, wl: 160, alpha: 0.42 });
  sh.add({ draw: (ctx) => st.draw(ctx, 1) });
}
function heartPts(cx, cy, s) { return sPoly([]).concat(sCubic([cx, cy + s * 0.9], [cx - s * 1.5, cy - s * 0.1], [cx - s * 0.7, cy - s * 1.2], [cx, cy - s * 0.35], 30), sCubic([cx, cy - s * 0.35], [cx + s * 0.7, cy - s * 1.2], [cx + s * 1.5, cy - s * 0.1], [cx, cy + s * 0.9], 30)); }
function bubblePts(cx, cy, s) { const P = sEllipse(cx, cy - s * 0.1, s * 1.05, s * 0.8, 2.2, 2.2 + TAU * 0.93); return P.concat(sPoly([P[P.length - 1], [cx - s * 0.9, cy + s * 0.9], [cx - s * 0.45, cy + s * 0.55]])); }
function starPts(cx, cy, s) { const P = []; for (let i = 0; i <= 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, r = i % 2 ? s * 0.45 : s * 1.05; P.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return sPoly(P); }
function flamePts(x, base, h) {
  const w = h * 0.62;
  const outer = sPoly([]).concat(sCubic([x, base], [x - w * 1.05, base - 2], [x - w * 0.9, base - h * 0.62], [x - w * 0.18, base - h * 0.78], 30),
    sCubic([x - w * 0.18, base - h * 0.78], [x - w * 0.12, base - h * 0.55], [x + w * 0.05, base - h * 0.5], [x + w * 0.05, base - h], 24),
    sCubic([x + w * 0.05, base - h], [x + w * 0.85, base - h * 0.6], [x + w * 1.1, base - h * 0.1], [x, base], 30));
  const inner = sCubic([x - w * 0.02, base - 6], [x - w * 0.45, base - h * 0.12], [x - w * 0.2, base - h * 0.38], [x + w * 0.02, base - h * 0.5], 24).concat(
    sCubic([x + w * 0.02, base - h * 0.5], [x + w * 0.35, base - h * 0.3], [x + w * 0.3, base - h * 0.08], [x - w * 0.02, base - 6], 24).slice(1));
  return [outer, inner];
}

/* ================================================================== 2 · 拆 */
function sceneTakeApart(sh) {
  const tLand = at('第二', 9.5) + 0.04, tSt = at('拆开看', 10.07) + 0.03, tFly = endOf('拆开看', 10.4) + 0.02;
  chapter(2, '第二步', '拆', tLand, tSt, tFly);
  drawnHeader(sh);
  const X0 = 110, X1 = 970, Y0 = 690, Y1 = 950, cutX = [X0 + (X1 - X0) / 3, X0 + (X1 - X0) * 2 / 3];
  const t0 = at('遇到', 10.96), tv = at('好视频', 11.16);
  const outline = [S(sRoundRect(X0, Y0, X1 - X0, Y1 - Y0, 18, 0.03), { w: 4, seed: 201, amp: 1.2, wl: 150 })];
  const sprockets = [S(sLine([X0 + 22, Y0 + 24], [X1 - 22, Y0 + 24]), { w: 11, seed: 202, amp: 0.4, raw: true, taper: false, dash: [14, 20], alpha: 0.8 }),
                     S(sLine([X0 + 22, Y1 - 24], [X1 - 22, Y1 - 24]), { w: 11, seed: 203, amp: 0.4, raw: true, taper: false, dash: [14, 20], alpha: 0.8 })];
  const dStrip = new Drawing(outline.concat(sprockets), t0, at('多看', 11.68) - 0.16, { sheet: sh });
  const pc = [540, (Y0 + Y1) / 2];
  const play = new Drawing([S(sPoly([[pc[0] - 26, pc[1] - 36], [pc[0] + 38, pc[1]], [pc[0] - 26, pc[1] + 36], [pc[0] - 26, pc[1] - 38]]), { w: 3.6, seed: 204, amp: 0.5 })], at('多看', 11.68) - 0.15, at('多看', 11.68) - 0.02, { sheet: sh });
  const loopP = sEllipse(pc[0] + 4, pc[1], 72, 72, -0.4, -0.4 + TAU * 0.86);
  const loop = new Drawing([S(loopP, { w: 3.4, seed: 205, amp: 0.8, color: PP.red })].concat(arrowHeadStrokes(loopP[loopP.length - 1], loopP[loopP.length - 6], 18, { w: 3.4, color: PP.red, seed: 206 })), at('多看', 11.68), at('两遍', 12.02) - 0.02, { sheet: sh });
  const x2 = new Writing('×2', 612, 655, { font: FT.kai(76), size: 76, color: PP.red, rot: -4, sheet: sh, slots: slots('两遍', 12.1, 0.9) });
  const tX2 = endOf('两遍', 12.3);
  qaText(sh, x2.bbox(), x2.t0, at('看它', 12.8) + 0.3, '×2');
  cue('pluck', tX2 - 0.05, { gain_db: -9, params: { note: 'D5', dur: 0.9 } });
  // cut into three (看它…): two dashed cuts, the pieces slide apart
  const tc = at('看它', 12.79);
  const cuts = cutX.map((x, k) => S(sLine([x, Y0 - 26], [x + 2, Y1 + 26]), { w: 3, seed: 210 + k, amp: 0.3, raw: true, taper: false, dash: [12, 9], color: PP.red }));
  const dCut = new Drawing(cuts, tc, tc + 0.2, { sheet: sh });
  const tSep0 = tc + 0.2, tSep1 = tc + 0.36, sep = [-26, 0, 26];
  cue('laser_zip', tc + 0.01, { gain_db: -12, params: { dur: 0.08 } });
  cue('laser_zip', tc + 0.12, { gain_db: -12, params: { dur: 0.08, pitch: 2 } });
  cue('clack', tSep1, { gain_db: -9 });
  const inner = (ctx, t) => { play.draw(ctx, t, 1 - seg(t, tc - 0.05, tc + 0.15)); loop.draw(ctx, t, 1 - seg(t, tc - 0.05, tc + 0.15)); };
  const bandX = [[X0, cutX[0]], [cutX[0], cutX[1]], [cutX[1], X1]];
  // three blocks: what is inside each one
  const blocks = [{ label: '开头', lt: '开头', ln: 13.02 }, { label: '画面', lt: '画面', ln: 14.11 }, { label: '音乐', lt: '音乐', ln: 15.69 }];
  const bc = bandX.map(([a, b], k) => [(a + b) / 2 + sep[k], (Y0 + Y1) / 2]);
  const hls = bandX.map(([a, b], k) => new Highlight(a + sep[k] + 16, b + sep[k] - 16, (Y0 + Y1) / 2, Y1 - Y0 - 70, { t0: at(blocks[k].lt, blocks[k].ln) - 0.02, dur: 0.2, seed: 230 + k, alpha: 0.42, passes: 1 }));
  hls.forEach((h, k) => cue('pluck', at(blocks[k].lt, blocks[k].ln), { gain_db: -12, params: { note: ['D5', 'F#5', 'A5'][k], dur: 0.7 } }));
  const edges = [];
  bandX.forEach(([a, b], k) => { if (k > 0) edges.push([k, S(sLine([a, Y0 + 3], [a + 1, Y1 - 3]), { w: 4, seed: 270 + k, amp: 0.5 })]); if (k < 2) edges.push([k, S(sLine([b, Y0 + 3], [b + 1, Y1 - 3]), { w: 4, seed: 280 + k, amp: 0.5 })]); });
  sh.add({
    draw(ctx, t) {
      const sp = E.cubicOut(seg(t, tSep0, tSep1));
      if (t < tSep0) { dStrip.draw(ctx, t); inner(ctx, t); dCut.draw(ctx, t); }
      else {
        bandX.forEach(([a, b], k) => {
          const ca = k ? a : a - 40, cb = k === 2 ? b + 40 : b;
          ctx.save(); ctx.translate(sep[k] * sp, 0);
          ctx.save(); ctx.beginPath(); ctx.rect(ca, Y0 - 40, cb - ca, Y1 - Y0 + 80); ctx.clip(); dStrip.draw(ctx, 1e9); ctx.restore();
          edges.filter(e => e[0] === k).forEach(e => e[1].draw(ctx, 1));
          ctx.restore();
        });
        dCut.draw(ctx, t, 1 - seg(t, tSep0, tSep1));
      }
      x2.draw(ctx, t, 1 - seg(t, tc + 0.1, tc + 0.3));
      hls.forEach(h => h.draw(ctx, t));
    },
  });
  // block contents + labels
  const LB = 1066;
  // 1 · 开头 … 留人: a hook
  written(sh, '开头', bc[0][0], LB, { font: FT.kai(74), size: 74, align: 'center', slots: slots('开头', 13.1, 0.9) });
  const hk = [bc[0][0] + 6, Y0 + 60];
  const hookS = [S(sLine([hk[0], hk[1]], [hk[0], hk[1] + 92]), { w: 4, seed: 240, amp: 0.4 }),
                 S(sCubic([hk[0], hk[1] + 92], [hk[0], hk[1] + 150], [hk[0] - 70, hk[1] + 150], [hk[0] - 64, hk[1] + 96]), { w: 4, seed: 241, amp: 0.4 }),
                 S(sLine([hk[0] - 64, hk[1] + 96], [hk[0] - 48, hk[1] + 112]), { w: 4, seed: 242, amp: 0.3 }),
                 S(sEllipse(hk[0], hk[1] - 8, 9, 9, 0, TAU * 1.05), { w: 3, seed: 243, amp: 0.2 })];
  drawn(sh, hookS, at('留人', 13.58), endOf('留人', 13.9) - 0.04, { wrap: d => ({ draw: (ctx, t) => { ctx.save(); ctx.translate(sep[0] * E.cubicOut(seg(t, tSep0, tSep1)), 0); d.draw(ctx, t); ctx.restore(); } }) });
  // 2 · 画面 … 推近: a little scene, then corner brackets close in (push-in)
  written(sh, '画面', bc[1][0], LB, { font: FT.kai(74), size: 74, align: 'center', slots: slots('画面', 14.2, 0.9) });
  const c2 = bc[1], tP = at('推进', 14.96);
  const scn = [S(sPoly([[c2[0] - 86, c2[1] + 52], [c2[0] - 30, c2[1] - 16], [c2[0] + 6, c2[1] + 22], [c2[0] + 36, c2[1] - 6], [c2[0] + 86, c2[1] + 52]]), { w: 3.4, seed: 250, amp: 0.6 }),
               S(sEllipse(c2[0] + 50, c2[1] - 50, 17, 17, 0, TAU * 1.05), { w: 3, seed: 251, amp: 0.3 })];
  const dScn = new Drawing(scn, at('什么时候', 14.48), tP - 0.05, { sheet: sh });
  const br = (s) => { const w = 120 * s, h = 86 * s, L = 26; const cx = c2[0], cy = c2[1] + 4; return [[[cx - w, cy - h + L], [cx - w, cy - h], [cx - w + L, cy - h]], [[cx + w - L, cy - h], [cx + w, cy - h], [cx + w, cy - h + L]], [[cx + w, cy + h - L], [cx + w, cy + h], [cx + w - L, cy + h]], [[cx - w + L, cy + h], [cx - w, cy + h], [cx - w, cy + h - L]]]; };
  sh.add({
    draw(ctx, t) {
      const z = E.cubicInOut(seg(t, tP + 0.02, tP + 0.34)), s = lerp(1, 1.42, z);
      ctx.save(); ctx.beginPath(); ctx.rect(c2[0] - 128, Y0 + 40, 256, Y1 - Y0 - 80); ctx.clip();
      ctx.translate(c2[0], c2[1]); ctx.scale(s, s); ctx.translate(-c2[0], -c2[1]); dScn.draw(ctx, t); ctx.restore();
      if (t >= tP - 0.02) {
        const bs = lerp(1, 0.66, z), a = seg(t, tP - 0.02, tP + 0.04);
        ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = PP.red; ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        br(bs).forEach(pl => { ctx.beginPath(); pl.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke(); });
        ctx.restore();
      }
    },
  });
  cue('push', tP, { align: 'motion', gain_db: -7, params: { dur: 0.4 } });
  // 3 · 音乐 … 哪一秒变: a waveform that changes, marked in red
  written(sh, '音乐', bc[2][0], LB, { font: FT.kai(74), size: 74, align: 'center', slots: slots('音乐', 15.75, 0.9) });
  const c3 = bc[2], wx0 = c3[0] - 118, wx1 = c3[0] + 118, chg = c3[0] + 8, wv = [];
  for (let x = wx0; x <= wx1; x += 2.5) { const big = x > chg, amp = big ? 44 : 12, f = big ? 0.19 : 0.33; wv.push([x, c3[1] + Math.sin((x - wx0) * f) * amp * (0.75 + 0.25 * Math.sin((x - wx0) * 0.05))]); }
  const tWv0 = at('在哪', 15.92), tMk = at('秒', 16.32), tBian = at('遍', 16.46);
  drawn(sh, [S(wv, { w: 3, seed: 260, amp: 0.3, raw: true })], tWv0, tMk - 0.02, { wrap: d => ({ draw: (ctx, t) => { ctx.save(); ctx.translate(sep[2] * E.cubicOut(seg(t, tSep0, tSep1)), 0); d.draw(ctx, t); ctx.restore(); } }) });
  const mk1 = [S(sLine([chg + sep[2], Y0 + 44], [chg + sep[2], Y1 - 44]), { w: 4, seed: 261, amp: 0.3, color: PP.red })];
  drawn(sh, mk1, tMk, tBian - 0.01);
  popGroup(sh, tBian, chg + sep[2], Y0 + 30, (ctx) => { ctx.fillStyle = PP.red; ctx.beginPath(); ctx.moveTo(chg + sep[2] - 14, Y0 + 14); ctx.lineTo(chg + sep[2] + 14, Y0 + 14); ctx.lineTo(chg + sep[2], Y0 + 38); ctx.closePath(); ctx.fill(); }, { from: 0.1, dur: 0.3 });
  cue('blip', tBian, { gain_db: -8, params: { pitch: 3 } });
}
function drawEdge(ctx, x, y0, y1, seed) {   // clean vertical edge of a cut strip piece
  ctx.save(); ctx.fillStyle = PP.ink; ctx.globalAlpha = 0.85; ctx.fillRect(x - 1.6, y0 + 2, 3.2, y1 - y0 - 4); ctx.restore();
}

/* ================================================================== 3 · 验 */
function sceneComments(sh) {
  const tLand = at('第三', 17.22) + 0.04, tSt = at('验证', 18.38) + 0.03, tFly = endOf('验证', 18.7) + 0.05;
  chapter(3, '第三步', '验', tLand, tSt, tFly);
  drawnHeader(sh);
  const B = [[84, 392, 430, 164, -1], [566, 440, 430, 164, 1], [100, 640, 430, 164, -1], [574, 712, 430, 164, 1]];
  const kf = FT.heavy(50); logText('转场', kf);
  const tpop = [at('大家都', 19.23), at('都', 19.35), at('在聊', 19.48), at('聊', 19.68)];
  const order = [1, 0, 2, 3];                 // the top-right bubble comes first: the pen draws it during 去评论区
  const tp = []; order.forEach((b, k) => tp[b] = tpop[k]);
  const tD0 = at('评论区', 17.88), tD1 = at('验证', 18.38) - 0.05;
  const wordFx = [0.56, 0.5, 0.62, 0.52];
  const circ = [];
  B.forEach(([x, y, w, h, side], k) => {
    const r = mulberry32(300 + k), tail = side < 0 ? [[x + 70, y + h - 4], [x + 52, y + h + 40], [x + 120, y + h - 2]] : [[x + w - 120, y + h - 2], [x + w - 52, y + h + 40], [x + w - 70, y + h - 4]];
    const body = [S(sRoundRect(x, y, w, h, 34, 0.04), { w: 3.4, seed: 310 + k, amp: 1.0, wl: 120 }), S(tail, { w: 3.4, seed: 320 + k, amp: 0.5 })];
    const av = S(sEllipse(x + 50, y + 50, 20, 20, 0, TAU * 1.04), { w: 2.6, seed: 330 + k, amp: 0.3, color: PP.ink2 });
    const ww = textW('转场', kf, 2), wx = x + w * wordFx[k], rowY = y + 104, wy = rowY + 17;
    const lines = [S(sLine([x + 84, y + 50], [x + 84 + 70 + r() * 50, y + 51]), { w: 2.6, seed: 340 + k, amp: 1.2, color: PP.mute })];
    const l0 = x + 36, l1 = wx - ww / 2 - 40, r0 = wx + ww / 2 + 40, r1 = x + w - 44;
    if (l1 - l0 > 30) lines.push(S(sLine([l0, rowY], [l1, rowY + 1]), { w: 2.6, seed: 350 + k, amp: 1.4, color: PP.mute }));
    if (r1 - r0 > 30) lines.push(S(sLine([r0, rowY], [r1, rowY + 1]), { w: 2.6, seed: 355 + k, amp: 1.4, color: PP.mute }));
    const fill = (ctx, a = 1) => { ctx.save(); ctx.globalAlpha *= a; ctx.fillStyle = 'rgba(255,253,247,0.9)'; ctx.beginPath(); ctx.roundRect(x, y, w, h, 34); ctx.fill(); ctx.restore(); };
    const content = (ctx) => { av.draw(ctx, 1); strokesFull(ctx, lines); ctx.font = kf; ctx.fillStyle = PP.ink; ctx.fillText('转场', wx - ww / 2, wy); };
    if (k === 1) {
      const d = new Drawing(body, tD0, tD1, { sheet: sh });
      sh.add({
        draw(ctx, t) {
          if (t >= tp[k]) fill(ctx, seg(t, tp[k], tp[k] + 0.06));
          d.draw(ctx, t);
          if (t >= tp[k]) { const sc = lerp(0.5, 1, springOut((t - tp[k]) / 0.34)); ctx.save(); ctx.globalAlpha = seg(t, tp[k], tp[k] + 0.05); ctx.translate(x + w / 2, y + h / 2); ctx.scale(sc, sc); ctx.translate(-x - w / 2, -y - h / 2); content(ctx); ctx.restore(); }
        },
      });
      qaText(sh, [x, y, x + w, y + h], tD0, sh.tOut, 'bubble' + k); qaText(sh, [Math.min(...tail.map(p => p[0])) - 4, y + h, Math.max(...tail.map(p => p[0])) + 4, y + h + 44], tD0, sh.tOut, 'tail' + k);
    } else {
      popGroup(sh, tp[k], side < 0 ? x + 70 : x + w - 70, y + h, (ctx) => { fill(ctx); strokesFull(ctx, body); content(ctx); }, { from: 0.3, dur: 0.34 });
      qaText(sh, [x, y, x + w, y + h], tp[k], sh.tOut, 'bubble' + k); qaText(sh, [Math.min(...tail.map(p => p[0])) - 4, y + h, Math.max(...tail.map(p => p[0])) + 4, y + h + 44], tp[k], sh.tOut, 'tail' + k);
    }
    cue('pop_soft', tp[k] + 0.03, { gain_db: -8, pan: side * 0.35, params: { pitch: [0, 2, 4, 7][order.indexOf(k)] } });
    circ.push([wx, rowY, ww, k]);
  });
  // circle the word everyone is talking about
  const tcs = [at('那个点', 19.96), at('个点', 20.06), at('点', 20.16), endOf('那个点', 20.3) - 0.04];
  circ.forEach(([cx, cy, ww], k) => {
    drawn(sh, [S(penCirclePts(cx, cy, ww / 2 + 22, 38, { seed: 360 + k, a0: -2.5, turns: 1.1 }), { w: 4, seed: 370 + k, amp: 0.8, color: PP.red })], tcs[k], tcs[k] + 0.11);
    cue('tick', tcs[k] + 0.08, { gain_db: -8, params: { pitch: k * 2 } });
  });
  // all lines lead to the real hook: 爆点
  const tB = at('爆点', 21.6), BX = 540, BY = 1152;
  const tl0 = tcs[3] + 0.16, tl1 = tB - 0.3;
  const conv = circ.map(([cx, cy, ww, k]) => {
    let P;
    const [bx, by, bw, bh] = B[k];
    if (k === 0) P = sCubic([bx - 8, by + bh / 2 + 10], [44, by + bh], [40, 900], [424, 968], 70);
    else if (k === 1) P = sCubic([bx + bw + 8, by + bh / 2 + 10], [1034, by + bh], [1038, 900], [656, 966], 70);
    else { const s0 = [cx, cy + 40], e = k === 2 ? [484, 972] : [598, 972]; P = sQuad(s0, [lerp(s0[0], e[0], 0.5) + (k === 2 ? -30 : 30), lerp(s0[1], e[1], 0.5)], e); }
    return S(P, { w: 2.6, seed: 380 + k, amp: 0.6, dash: [16, 12], color: PP.red, alpha: 0.85 });
  });
  drawn(sh, conv, tl0, tl1);
  const hl = new Highlight(BX - 196, BX + 196, BY - 58, 92, { t0: tB + 0.12, dur: 0.2, seed: 390 });
  sh.add({ draw: (ctx, t) => hl.draw(ctx, t) });
  const w = popWord(sh, '爆点', BX, BY, FT.heavy(196), tB, { align: 'center', ls: 4, from: 1.7 });
  const burst = [];
  for (let i = 0; i <= 22; i++) { const a = -Math.PI / 2 + i * TAU / 22, rr = i % 2 ? 1 : 1.2; burst.push([BX + Math.cos(a) * 262 * rr, BY - 70 + Math.sin(a) * 128 * rr]); }
  const burstS = [S(burst, { w: 3.6, seed: 395, amp: 1.0, color: PP.red })];
  popGroup(sh, tB + 0.03, BX, BY - 70, (ctx) => strokesFull(ctx, burstS), { from: 0.4, dur: 0.4 });
  cue('reverse_whoosh', tB, { align: 'end', gain_db: -8, params: { dur: 0.4 } });
  cue('hit', tB, { gain_db: -3, params: { bright: 0.55 } });
  shake(tB, 7);
  PUSHES.push({ t0: tB, t1: tB + 0.34, t2: SHEETS[4].tIn, s: 1.055, f: [BX, 1080] });
}

/* ================================================================== 4 · 存 */
function sceneSave(sh) {
  const tLand = at('第四', 22.59) + 0.04, tSt = at('存下来', 23.26) + 0.03, tFly = endOf('存下来', 23.7) - 0.14;
  chapter(4, '第四步', '存', tLand, tSt, tFly);
  drawnHeader(sh);
  const F = [{ x: 110, y: 880, w: 390, h: 260, label: '镜头' }, { x: 580, y: 880, w: 390, h: 260, label: '音效' }];
  const tF = tFly - 0.02;
  cue('whoosh_fast', tF, { align: 'motion', gain_db: -12, params: { dur: 0.3, travel: 0.1, bright: 0.3 } });
  const slideUp = (t) => (1 - E.cubicOut(seg(t, tF, tF + 0.32))) * 700;
  const folderBack = (ctx, f) => {
    ctx.fillStyle = '#E9D6A6'; ctx.beginPath(); ctx.moveTo(f.x, f.y + 30); ctx.lineTo(f.x, f.y - 8); ctx.quadraticCurveTo(f.x, f.y - 30, f.x + 20, f.y - 30);
    ctx.lineTo(f.x + 150, f.y - 30); ctx.quadraticCurveTo(f.x + 168, f.y - 30, f.x + 176, f.y - 12); ctx.lineTo(f.x + 184, f.y); ctx.lineTo(f.x + f.w, f.y); ctx.lineTo(f.x + f.w, f.y + 30); ctx.closePath(); ctx.fill();
  };
  const frontS = F.map((f, k) => [S(sPoly([[f.x - 6, f.y + 40], [f.x + f.w + 6, f.y + 40], [f.x + f.w - 8, f.y + f.h], [f.x + 8, f.y + f.h], [f.x - 6, f.y + 40]]), { w: 3.6, seed: 400 + k, amp: 0.8 })]);
  const backS = F.map((f, k) => [S(sPoly([[f.x, f.y + 40], [f.x, f.y - 8], [f.x + 20, f.y - 30], [f.x + 150, f.y - 30], [f.x + 184, f.y], [f.x + f.w, f.y], [f.x + f.w, f.y + 40]]), { w: 3, seed: 410 + k, amp: 0.6 })]);
  // items drawn above each folder, then dropped in
  const it1 = filmFrame(305, 690, 1), it2 = waveIcon(775, 690);
  const tI1 = at('好镜头', 23.91) + 0.02, tD1 = endOf('好镜头', 24.3) - 0.16, tI2 = at('好音效', 24.8) + 0.02, tD2 = endOf('好音效', 25.2) - 0.12;
  const dI1 = new Drawing(it1, tI1, tD1 - 0.04, { sheet: sh }), dI2 = new Drawing(it2, tI2, tD2 - 0.04, { sheet: sh });
  const tOut = at('直接用', 26.76), tSnap = at('用', 27.08);
  cue('whoosh_fast', tD1, { align: 'motion', gain_db: -11, params: { dur: 0.2, travel: -0.2 } });
  cue('land', tD1 + 0.2, { gain_db: -10, params: { bright: 0.3 } });
  cue('whoosh_fast', tD2, { align: 'motion', gain_db: -11, params: { dur: 0.2, travel: 0.3 } });
  cue('land', tD2 + 0.2, { gain_db: -10, params: { bright: 0.3, pitch: 2 } });
  const drop = (t, td) => E.quadIn(seg(t, td, td + 0.2)) * 330;
  // timeline (下次剪…) and the clip flying onto it (直接用)
  const TL = { x: 130, y: 440, w: 820, h: 86 };
  const tT0 = at('下次剪', 26.28), tT1 = at('直接', 26.76) - 0.04;
  const tlS = [S(sRoundRect(TL.x, TL.y, TL.w, TL.h, 12, 0.03), { w: 3.4, seed: 420, amp: 0.8, wl: 150 }),
               S(sLine([TL.x + 20, TL.y + 20], [TL.x + 330, TL.y + 20]), { w: 2, seed: 421, amp: 0.5, color: PP.ink2 }),
               S(sLine([TL.x + 460, TL.y + 20], [TL.x + 800, TL.y + 20]), { w: 2, seed: 422, amp: 0.5, color: PP.ink2 })];
  drawn(sh, tlS, tT0, tT1);
  const gap = { x: TL.x + 344, y: TL.y + 8, w: 104, h: TL.h - 16 };
  sh.add({
    draw(ctx, t) {
      if (t < tF) return;
      const oy = slideUp(t);
      // hatched existing clips on the track
      if (t > tT1 - 0.2) {          // the clips already on the track, swiped in like a marker fill
        const u = E.cubicOut(seg(t, tT1 - 0.2, tT1));
        ctx.save(); ctx.globalAlpha = 0.5; ctx.fillStyle = PP.ink2; ctx.fillRect(TL.x + 20, TL.y + 30, 310 * u, 40); ctx.fillRect(TL.x + 460, TL.y + 30, 340 * u, 40); ctx.restore();
      }
      F.forEach((f, k) => {
        ctx.save(); ctx.translate(0, oy);
        folderBack(ctx, f); strokesFull(ctx, backS[k]);
        // item inside (clipped by the folder mouth)
        ctx.save(); ctx.beginPath(); ctx.rect(f.x - 60, 0, f.w + 120, f.y + 40); ctx.clip();
        ctx.translate(0, -oy);
        if (k === 0) itemDraw(ctx, t, dI1, tD1, 305, 690, tOut, tSnap, gap);
        if (k === 1) { ctx.save(); ctx.translate(0, drop(t, tD2)); dI2.draw(ctx, t); ctx.restore(); }
        ctx.restore();
        ctx.fillStyle = '#F2E2B8'; ctx.beginPath(); ctx.moveTo(f.x - 6, f.y + 40); ctx.lineTo(f.x + f.w + 6, f.y + 40); ctx.lineTo(f.x + f.w - 8, f.y + f.h); ctx.lineTo(f.x + 8, f.y + f.h); ctx.closePath(); ctx.fill();
        strokesFull(ctx, frontS[k]);
        ctx.restore();
      });
      // the clip after it left the folder, above everything
      if (t >= tOut) itemFly(ctx, t, dI1, 305, 690, tOut, tSnap, gap);
    },
  });
  F.forEach((f, k) => qaText(sh, [f.x - 6, f.y - 30, f.x + f.w + 6, f.y + f.h], tF, sh.tOut, 'folder' + k));
  // labels on the folders (分类收好)
  written(sh, '镜头', F[0].x + F[0].w / 2, F[0].y + 170, { font: FT.kai(76), size: 76, align: 'center', slots: slots('分类', 25.3, 0.95) });
  written(sh, '音效', F[1].x + F[1].w / 2, F[1].y + 170, { font: FT.kai(76), size: 76, align: 'center', slots: slots('收好', 25.7, 0.95) });
  cue('tock', endOf('收好', 25.9) - 0.02, { gain_db: -9 });
  cue('pop_soft', tOut + 0.04, { gain_db: -8, params: { pitch: 5 } });
  cue('whoosh_fast', tOut + 0.06, { align: 'motion', gain_db: -9, params: { dur: 0.24, travel: 0.2, bright: 0.6 } });
  cue('clack', tSnap, { gain_db: -4 });
  cue('pluck', tSnap + 0.02, { gain_db: -9, params: { note: 'A5', dur: 1.2 } });
  const hl = new Highlight(gap.x - 8, gap.x + gap.w + 8, TL.y + TL.h / 2, TL.h + 18, { t0: tSnap, dur: 0.14, seed: 430, alpha: 0.6 });
  sh.add({ draw: (ctx, t) => hl.draw(ctx, t) });
  shake(tSnap, 3);
}
function filmFrame(cx, cy, s) {
  const w = 170 * s, h = 118 * s, x = cx - w / 2, y = cy - h / 2;
  return [S(sRoundRect(x, y, w, h, 10, 0.03), { w: 3.6, seed: 450, amp: 0.8 }),
          S(sLine([x + 12, y + 14], [x + w - 12, y + 14]), { w: 8, seed: 451, raw: true, taper: false, dash: [9, 12], alpha: 0.8 }),
          S(sLine([x + 12, y + h - 14], [x + w - 12, y + h - 14]), { w: 8, seed: 452, raw: true, taper: false, dash: [9, 12], alpha: 0.8 }),
          S(sPoly([[cx - 14, cy - 20], [cx + 22, cy], [cx - 14, cy + 20], [cx - 14, cy - 21]]), { w: 3, seed: 453, amp: 0.4 })];
}
function waveIcon(cx, cy) {
  const w = 170, h = 118, x = cx - w / 2, y = cy - h / 2, pts = [];
  for (let i = 0; i <= 13; i++) { const xx = x + 22 + i * (w - 44) / 13, a = [10, 26, 42, 18, 34, 46, 22, 38, 14, 30, 44, 20, 12, 8][i]; pts.push([xx, cy - a / 2], [xx, cy + a / 2]); }
  return [S(sRoundRect(x, y, w, h, 10, 0.03), { w: 3.6, seed: 460, amp: 0.8 }), S(sPoly(pts), { w: 2.6, seed: 461, amp: 0.2, raw: true })];
}
function itemDraw(ctx, t, d, td, cx, cy, tOut, tSnap, gap) {   // film frame: drawn, dropped into the folder, later pops out
  if (t >= tOut) return;
  ctx.save(); ctx.translate(0, E.quadIn(seg(t, td, td + 0.2)) * 330); d.draw(ctx, t); ctx.restore();
}
function itemFly(ctx, t, d, cx, cy, tOut, tSnap, gap) {
  const u = seg(t, tOut, tSnap), e = E.cubicInOut(u);
  const sx = cx, sy = cy + 330 - 120, gx = gap.x + gap.w / 2, gy = gap.y + gap.h / 2;
  const rise = E.cubicOut(seg(t, tOut, tOut + 0.12));
  const x = lerp(sx, gx, e), y = lerp(sy - rise * 90, gy, e) - Math.sin(e * Math.PI) * 120, s = lerp(1, 0.56, e);
  const settle = t > tSnap ? 1 + 0.08 * Math.exp(-(t - tSnap) * 12) * Math.cos((t - tSnap) * 30) : 1;
  ctx.save(); ctx.translate(x, y); ctx.scale(s * settle, s * settle); ctx.rotate((1 - e) * -8 * DEG); ctx.translate(-cx, -cy);
  ctx.fillStyle = PP.card; ctx.fillRect(cx - 85, cy - 59, 170, 118);
  d.draw(ctx, 1e9); ctx.restore();
}

/* ================================================================== 5 · recap */
function sceneRecap(sh) {
  drawnHeader(sh);
  const C = [540, 800], R = 292, SZ = 190;
  const pos = [[C[0], C[1] - R], [C[0] + R, C[1]], [C[0], C[1] + R], [C[0] - R, C[1]]];
  const a4 = A('四件事每', 27.7), ts = [0, 1, 2, 3].map(k => TM.chars[a4.i + k][1] + 0.03);
  const st = ['猜', '拆', '验', '存'].map((ch, k) => makeStamp(ch, SZ, 70 + k));
  ts.forEach((t, k) => { cue('stamp', t, { gain_db: -3, params: { pitch: k } }); shake(t, 4); qaText(sh, [pos[k][0] - SZ / 2, pos[k][1] - SZ / 2, pos[k][0] + SZ / 2, pos[k][1] + SZ / 2], t, 99, 'stamp' + k); });
  sh.add({
    draw(ctx, t) {
      ts.forEach((t0, k) => {
        if (t < t0) return;
        const u = t - t0, pu = t - (RECAP_PULSE.t + k * 0.09);
        let sc = u < 0.05 ? lerp(1.3, 0.95, u / 0.05) : lerp(0.95, 1, E.cubicOut((u - 0.05) / 0.1));
        if (pu > 0 && pu < 0.3) sc *= 1 + 0.07 * Math.sin(pu / 0.3 * Math.PI);
        const [x, y] = pos[k];
        ctx.save(); ctx.translate(x, y); ctx.rotate([-4, 3, -2, 5][k] * DEG); ctx.scale(sc, sc); ctx.globalCompositeOperation = 'multiply';
        ctx.drawImage(st[k].c, -SZ / 2 - st[k].pad, -SZ / 2 - st[k].pad); ctx.restore();
      });
    },
  });
  // 每天循环: four arcs, clockwise, with arrow heads
  const tl0 = at('每天', 28.08) + 0.1, tl1 = endOf('循环', 28.8) - 0.02, arcs = [];
  for (let k = 0; k < 4; k++) {
    const a0 = -Math.PI / 2 + k * Math.PI / 2 + 0.44, a1 = -Math.PI / 2 + (k + 1) * Math.PI / 2 - 0.44;
    const P = sEllipse(C[0], C[1], R, R, a0, a1);
    arcs.push(S(P, { w: 4.2, seed: 500 + k, amp: 1.0 }), ...arrowHeadStrokes(P[P.length - 1], P[P.length - 5], 22, { w: 4.2, seed: 510 + k }));
  }
  drawn(sh, arcs, tl0, tl1);
  cue('whoosh_mid', tl0, { align: 'motion', gain_db: -10, params: { dur: 0.7, travel: 0.9, bright: 0.4 } });
  // 网感 in the middle
  const tW = at('网感', 29.08);
  const hl = new Highlight(C[0] - 142, C[0] + 142, C[1] + 8, 66, { t0: tW + 0.12, dur: 0.22, seed: 520 });
  sh.add({ draw: (ctx, t) => hl.draw(ctx, t) });
  popWord(sh, '网感', C[0], C[1] + 50, FT.heavy(138), tW, { align: 'center', ls: 4, from: 1.7 });
  cue('reverse_whoosh', tW, { align: 'end', gain_db: -9, params: { dur: 0.35 } });
  cue('hit', tW, { gain_db: -4, params: { bright: 0.5 } });
  shake(tW, 5);
  PUSHES.push({ t0: tW, t1: tW + 0.5, t2: 99, s: 1.04, f: C });
  // 练出来: the four stamps pulse once, in order (no pen near the key word)
  RECAP_PULSE.t = at('练出来', 29.84);
  cue('bell', endOf('的', 30.3) + 0.05, { gain_db: -12, params: { note: 'D6', dur: 2.2, space: 0.35 } });
}

/* ------------------------------------------------------------------ camera */
function camera(t) {
  let s = 1, f = [540, 820], dx = 0, dy = 0;
  for (const p of PUSHES) {
    if (t < p.t0 || t > p.t2 + 0.3) continue;
    const k = E.cubicOut(seg(t, p.t0, p.t1)) * (1 - E.cubicInOut(seg(t, p.t2, p.t2 + 0.3)));
    s *= lerp(1, p.s, k); f = [lerp(f[0], p.f[0], k), lerp(f[1], p.f[1], k)];
  }
  for (const sk of SHAKES) {
    const u = t - sk.t; if (u < 0 || u > 0.35) continue;
    const e = Math.exp(-u * 16) * sk.amp; dx += Math.sin(u * 95 + sk.t * 7) * e; dy += Math.cos(u * 77 + sk.t * 3) * e * 0.8;
  }
  return { s, f, dx, dy };
}

/* ------------------------------------------------------------------ pen */
const PEN_ANG = 50 * DEG;   // body toward the lower right, like a right hand drawing; idles at the right edge
function jobOffset(j, t) { return j.sheet ? j.sheet.offset(t) : 0; }
function penAt(t) {
  let prev = null, next = null;
  for (const j of PEN_JOBS) {
    if (t >= j.t0 && t <= j.t1) { const r = j.pen(t); return { p: [r.p[0] + jobOffset(j, t), r.p[1]], down: r.down }; }
    if (j.t1 < t && (!prev || j.t1 > prev.t1)) prev = j;
    if (j.t0 > t && (!next || j.t0 < next.t0)) next = j;
  }
  const sh = sheetOf(t), rest = sh.rest;
  const idle = (p) => [p[0] + Math.sin(t * 1.3) * 4, p[1] + Math.cos(t * 1.1) * 3];
  const p0 = prev ? [prev.endPt[0] + jobOffset(prev, t), prev.endPt[1]] : rest, t0 = prev ? prev.t1 : -1;
  const p1 = next ? [next.startPt[0] + jobOffset(next, t), next.startPt[1]] : rest, t1 = next ? next.t0 : 1e9;
  const gap = t1 - t0;
  if (gap > 1.3) {
    if (t < t0 + 0.4) { const u = E.cubicInOut(seg(t, t0, t0 + 0.4)); return { p: idle([lerp(p0[0], rest[0], u), lerp(p0[1], rest[1], u)]), down: 0 }; }
    if (t > t1 - 0.4) { const u = E.cubicInOut(seg(t, t1 - 0.4, t1)); return { p: idle([lerp(rest[0], p1[0], u), lerp(rest[1], p1[1], u)]), down: 0 }; }
    return { p: idle(rest), down: 0 };
  }
  const ta = Math.max(t0, t1 - 0.4), u = E.cubicInOut(seg(t, ta, t1));
  return { p: [lerp(p0[0], p1[0], u), lerp(p0[1], p1[1], u) - Math.sin(u * Math.PI) * 18], down: 0.2 * u };
}

/* ------------------------------------------------------------------ frame */
function renderFrame(ctx, t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
  const cam = camera(t);
  ctx.fillStyle = PP.paper; ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(cam.f[0] + cam.dx, cam.f[1] + cam.dy); ctx.scale(cam.s, cam.s); ctx.translate(-cam.f[0], -cam.f[1]);
  for (const sh of SHEETS) {
    if (t < sh.tIn || t > sh.tOut) continue;
    const ox = sh.offset(t);
    ctx.save(); ctx.translate(ox, 0);
    if (ox > 0) {   // shadow of the incoming sheet on the one below
      const g = ctx.createLinearGradient(-46, 0, 0, 0); g.addColorStop(0, 'rgba(70,50,30,0)'); g.addColorStop(1, 'rgba(70,50,30,0.28)');
      ctx.fillStyle = g; ctx.fillRect(-46, -200, 46, H + 400);
    }
    ctx.drawImage(sh.paper, 0, 0);
    ctx.drawImage(sh.paper, 0, 0, W, 60, 0, -120, W, 120); ctx.drawImage(sh.paper, 0, H - 60, W, 60, 0, H, W, 120);
    for (const it of sh.items) it.draw(ctx, t);
    ctx.restore();
  }
  for (const c of CARDS) c.draw(ctx, t);
  const pn = penAt(t);
  if (!window.NO_PEN) drawPen(ctx, pn.p[0], pn.p[1], PEN_ANG + Math.sin(t * 2.1) * 1.2 * DEG, 1 - pn.down);
  ctx.restore();
  // subtitle (screen space)
  let sub = null;
  for (const L of TM.lines) if (t >= L.show0 && t <= L.show1) sub = drawSubtitle(ctx, L, t) || sub;
  return { pen: pn, sub };
}
