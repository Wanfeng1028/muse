'use strict';
/* ==========================================================================
   Ink on paper, in time. Everything the pen makes is a Stroke (a fineliner ribbon with
   pressure, tremor and a touch-down blob) revealed along its own length, so lines are really
   drawn, never faded in. A Drawing is one pen job (strokes in order, with pen travel between
   them); a Writing is one pen job that writes a line of type (LXGW WenKai) glyph by glyph.
   ========================================================================== */
const PP = { paper: '#F4EFE4', ink: '#23262D', ink2: '#5B574F', mute: '#8E877B', red: '#CF4A2C', hl: '#FFD84A', blue: '#7F9CC4', card: '#FFFDF7', note: '#FBE59A' };

/* ------------------------------------------------------------------ Stroke */
class Stroke {
  /* pts: raw polyline; o: {w, seed, amp, wl, color, alpha, raw, taper, endW, blob, dash} */
  constructor(pts, o = {}) {
    this.o = o;
    const w = o.w ?? 4, seed = o.seed ?? 1;
    const P = o.raw ? resample(pts, 2) : resample(wobble(pts, seed, o.amp ?? 1.6, o.wl ?? 90), 2);
    this.P = P; this.w = w; this.color = o.color ?? PP.ink; this.alpha = o.alpha ?? 0.94;
    const n = P.length, S = new Float32Array(n), NX = new Float32Array(n), NY = new Float32Array(n), HW = new Float32Array(n), HE = new Float32Array(n);
    for (let i = 1; i < n; i++) S[i] = S[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
    const total = S[n - 1] || 1; this.L = total; this.S = S;
    for (let i = 0; i < n; i++) {
      const a = P[Math.max(0, i - 1)], b = P[Math.min(n - 1, i + 1)];
      let nx = -(b[1] - a[1]), ny = b[0] - a[0]; const len = Math.hypot(nx, ny) || 1; NX[i] = nx / len; NY[i] = ny / len;
      const s = S[i];
      let pr = 0.9 + 0.12 * Noise.n1(s / 60, seed + 5);
      if (o.taper !== false) pr *= lerp(0.55, 1, smooth(s / Math.min(18, total * 0.2)));
      HW[i] = w * pr / 2;                                     // while drawing (pen down at the tip)
      const endK = o.taper === false ? 1 : lerp(1, o.endW ?? 0.5, smooth((s - (total - Math.min(26, total * 0.25))) / Math.min(26, total * 0.25)));
      HE[i] = HW[i] * endK;                                   // finished (lifted) stroke
    }
    this.NX = NX; this.NY = NY; this.HW = HW; this.HE = HE;
  }
  idxAt(s) { const S = this.S; let lo = 0, hi = S.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (S[m] <= s) lo = m; else hi = m - 1; } return lo; }
  tip(frac) {
    const s = clamp(frac) * this.L, k = this.idxAt(s), P = this.P;
    if (k >= P.length - 1) return P[P.length - 1].slice();
    const u = (s - this.S[k]) / Math.max(1e-6, this.S[k + 1] - this.S[k]);
    return [lerp(P[k][0], P[k + 1][0], u), lerp(P[k][1], P[k + 1][1], u)];
  }
  draw(ctx, frac, alphaMul = 1) {
    if (frac <= 0) return;
    const done = frac >= 1, s = clamp(frac) * this.L, P = this.P, k = this.idxAt(s), HWs = done ? this.HE : this.HW;
    if (this.o.dash) return this.drawDash(ctx, s, done);
    const Lp = [], Rp = [];
    for (let i = 0; i <= k; i++) { const h = HWs[i]; Lp.push(P[i][0] + this.NX[i] * h, P[i][1] + this.NY[i] * h); Rp.push(P[i][0] - this.NX[i] * h, P[i][1] - this.NY[i] * h); }
    let end = P[k], hEnd = HWs[k];
    if (!done && k < P.length - 1) {
      const e = this.tip(frac); end = e; hEnd = this.HW[k];
      Lp.push(e[0] + this.NX[k] * hEnd, e[1] + this.NY[k] * hEnd); Rp.push(e[0] - this.NX[k] * hEnd, e[1] - this.NY[k] * hEnd);
    }
    ctx.save(); ctx.globalAlpha = this.alpha * alphaMul; ctx.fillStyle = this.color;
    ctx.beginPath(); ctx.moveTo(Lp[0], Lp[1]);
    for (let i = 2; i < Lp.length; i += 2) ctx.lineTo(Lp[i], Lp[i + 1]);
    for (let i = Rp.length - 2; i >= 0; i -= 2) ctx.lineTo(Rp[i], Rp[i + 1]);
    ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.arc(P[0][0], P[0][1], this.w * (this.o.blob ?? 0.6), 0, TAU); ctx.fill();
    ctx.beginPath(); ctx.arc(end[0], end[1], Math.max(0.6, hEnd * 0.98), 0, TAU); ctx.fill();
    ctx.restore();
  }
  drawDash(ctx, s, done) {   // dashed line: short ink ticks along the path
    const [on, off] = this.o.dash, P = this.P;
    ctx.save(); ctx.globalAlpha = this.alpha; ctx.fillStyle = this.color;
    for (let a = 0; a < s; a += on + off) {
      const b = Math.min(s, a + on), i0 = this.idxAt(a), i1 = this.idxAt(b);
      ctx.beginPath();
      for (let i = i0; i <= i1; i++) { const h = this.HW[i] * 0.9; ctx.lineTo(P[i][0] + this.NX[i] * h, P[i][1] + this.NY[i] * h); }
      for (let i = i1; i >= i0; i--) { const h = this.HW[i] * 0.9; ctx.lineTo(P[i][0] - this.NX[i] * h, P[i][1] - this.NY[i] * h); }
      ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }
  get start() { return this.P[0]; }
  get end() { return this.P[this.P.length - 1]; }
}

/* ------------------------------------------------------------------ pen jobs */
const PEN_JOBS = [];
class Drawing {
  /* strokes drawn in order inside [t0, t1]; time per stroke ~ its length, plus pen travel between strokes */
  constructor(strokes, t0, t1, o = {}) {
    this.strokes = strokes; this.t0 = t0; this.t1 = t1; this.sheet = o.sheet ?? null; this.name = o.name || '';
    const travel = [], lens = strokes.map(s => s.L);
    for (let i = 1; i < strokes.length; i++) travel.push(Math.hypot(strokes[i].start[0] - strokes[i - 1].end[0], strokes[i].start[1] - strokes[i - 1].end[1]));
    const drawW = lens.reduce((a, b) => a + b, 0), travW = travel.reduce((a, b) => a + b, 0) * 0.35 + travel.length * 18;
    const k = (t1 - t0) / Math.max(1e-6, drawW + travW);
    let t = t0; this.slots = [];
    strokes.forEach((s, i) => {
      if (i) t += (travel[i - 1] * 0.35 + 18) * k;
      this.slots.push([t, t + s.L * k]); t += s.L * k;
    });
    if (!o.noPen) PEN_JOBS.push(this);
  }
  frac(i, t) { const [a, b] = this.slots[i]; return seg(t, a, b); }
  draw(ctx, t, alphaMul = 1) { if (t < this.t0) return; this.strokes.forEach((s, i) => s.draw(ctx, this.frac(i, t), alphaMul)); }
  pen(t) {
    for (let i = 0; i < this.slots.length; i++) {
      const [a, b] = this.slots[i];
      if (t <= b) {
        if (t >= a) return { p: this.strokes[i].tip(seg(t, a, b)), down: 1 };
        const prev = i ? this.strokes[i - 1].end : this.strokes[0].start, u = E.sineInOut(seg(t, i ? this.slots[i - 1][1] : a, a));
        const nx = this.strokes[i].start;
        return { p: [lerp(prev[0], nx[0], u), lerp(prev[1], nx[1], u) - Math.sin(u * Math.PI) * 10], down: 0.35 };
      }
    }
    return { p: this.strokes[this.strokes.length - 1].end, down: 0 };
  }
  get startPt() { return this.strokes[0].start; }
  get endPt() { return this.strokes[this.strokes.length - 1].end; }
}

/* text written glyph by glyph; slots = [[a,b], ...] per glyph (e.g. the spoken syllables) */
class Writing {
  constructor(str, x, y, o) {
    this.str = str; this.x = x; this.y = y; this.font = o.font; this.size = o.size; this.color = o.color ?? PP.ink; this.alpha = o.alpha ?? 0.95;
    this.rot = (o.rot ?? 0) * DEG; this.align = o.align || 'left'; this.sheet = o.sheet ?? null;
    this.L = layoutChars(str, this.font, o.ls ?? 0); logText(str, this.font);
    this.x0 = this.align === 'center' ? x - this.L.width / 2 : this.align === 'right' ? x - this.L.width : x;
    const n = this.L.chars.length;
    this.slots = o.slots || this.L.chars.map((c, i) => [lerp(o.t0, o.t1, i / n), lerp(o.t0, o.t1, (i + 1) / n)]);
    this.t0 = this.slots[0][0]; this.t1 = this.slots[n - 1][1];
    const ib = inkBox('国', this.font); this.asc = -ib.t; this.desc = ib.b;
    if (!o.noPen) PEN_JOBS.push(this);
  }
  local(px, py) { const c = Math.cos(this.rot), s = Math.sin(this.rot); return [this.x + (px - this.x) * c - (py - this.y) * s, this.y + (px - this.x) * s + (py - this.y) * c]; }
  draw(ctx, t, alphaMul = 1) {
    if (t < this.t0) return;
    ctx.save(); ctx.translate(this.x, this.y); ctx.rotate(this.rot); ctx.translate(-this.x, -this.y);
    ctx.font = this.font; ctx.fillStyle = this.color; ctx.textBaseline = 'alphabetic'; ctx.globalAlpha = this.alpha * alphaMul;
    this.L.chars.forEach((ch, i) => {
      const u = seg(t, this.slots[i][0], this.slots[i][1]);
      if (u <= 0) return;
      const gx = this.x0 + ch.x;
      if (u >= 1) { ctx.fillText(ch.c, gx, this.y); return; }
      ctx.save(); ctx.beginPath();
      // a slightly slanted wipe, like a stroke order sweeping down-right
      const top = this.y - this.asc - 6, bot = this.y + this.desc + 6, cw = ch.w + 8, e = E.sineInOut(u);
      ctx.moveTo(gx - 4, top); ctx.lineTo(gx - 4 + cw * e + 18, top); ctx.lineTo(gx - 4 + cw * e - 6, bot); ctx.lineTo(gx - 4, bot); ctx.closePath(); ctx.clip();
      ctx.fillText(ch.c, gx, this.y); ctx.restore();
    });
    ctx.restore();
  }
  pen(t) {
    const n = this.L.chars.length;
    for (let i = 0; i < n; i++) {
      const [a, b] = this.slots[i], ch = this.L.chars[i];
      if (t <= b) {
        const cx = this.x0 + ch.x, midY = this.y - this.asc * 0.45;
        if (t >= a) {
          const u = seg(t, a, b), e = E.sineInOut(u);
          const px = cx + ch.w * (0.08 + 0.84 * e) + Math.sin(u * TAU * 2.5) * ch.w * 0.12;
          const py = midY + Math.sin(u * TAU * 3.2 + 0.7) * this.asc * 0.32;
          return { p: this.local(px, py), down: 1 };
        }
        const pv = i ? [this.x0 + this.L.chars[i - 1].x + this.L.chars[i - 1].w * 0.92, midY] : [cx, midY];
        const u = E.sineInOut(seg(t, i ? this.slots[i - 1][1] : a, a));
        return { p: this.local(lerp(pv[0], cx + ch.w * 0.08, u), midY - Math.sin(u * Math.PI) * 8), down: 0.35 };
      }
    }
    const lc = this.L.chars[n - 1];
    return { p: this.local(this.x0 + lc.x + lc.w * 0.92, this.y - this.asc * 0.45), down: 0 };
  }
  get startPt() { return this.local(this.x0 + this.L.chars[0].w * 0.08, this.y - this.asc * 0.45); }
  get endPt() { const lc = this.L.chars[this.L.chars.length - 1]; return this.local(this.x0 + lc.x + lc.w * 0.92, this.y - this.asc * 0.45); }
  bbox() { return [this.x0 - 2, this.y - this.asc - 2, this.x0 + this.L.width + 2, this.y + this.desc + 2]; }
}

/* ------------------------------------------------------------------ paper */
function makePaper(seed) {
  const c = mk(W, H), ctx = c.getContext('2d');
  ctx.fillStyle = PP.paper; ctx.fillRect(0, 0, W, H);
  const sw = 120, sh = 214, m = mk(sw, sh), x = m.getContext('2d'), id = x.createImageData(sw, sh);
  for (let j = 0; j < sh; j++) for (let i = 0; i < sw; i++) {
    const n = Noise.fbm(i / 22 + seed * 3.1, j / 22 + seed, 4), v = 128 + n * 90, k = (j * sw + i) * 4;
    id.data[k] = v; id.data[k + 1] = v; id.data[k + 2] = v; id.data[k + 3] = 255;
  }
  x.putImageData(id, 0, 0);
  ctx.save(); ctx.globalCompositeOperation = 'soft-light'; ctx.globalAlpha = 0.22; ctx.imageSmoothingQuality = 'high'; ctx.drawImage(m, 0, 0, W, H); ctx.restore();
  const r = mulberry32(seed * 977 + 1);
  for (let i = 0; i < 4300; i++) {
    const x0 = r() * W, y0 = r() * H, a = r() * TAU, L = 3 + r() * 14, dark = r() < 0.55;
    ctx.strokeStyle = dark ? `rgba(120,100,72,${0.035 + r() * 0.05})` : `rgba(255,255,250,${0.25 + r() * 0.3})`;
    ctx.lineWidth = 0.6 + r() * 0.7; ctx.beginPath(); ctx.moveTo(x0, y0);
    ctx.quadraticCurveTo(x0 + Math.cos(a + 0.5) * L * 0.5, y0 + Math.sin(a + 0.5) * L * 0.5, x0 + Math.cos(a) * L, y0 + Math.sin(a) * L); ctx.stroke();
  }
  const v = ctx.createRadialGradient(W / 2, H * 0.46, 520, W / 2, H * 0.46, 1250);
  v.addColorStop(0, 'rgba(160,130,90,0)'); v.addColorStop(1, 'rgba(150,120,80,0.15)');
  ctx.save(); ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = v; ctx.fillRect(0, 0, W, H); ctx.restore();
  // static fine grain (paper tooth), baked in
  const g = ctx.getImageData(0, 0, W, H), d = g.data;
  for (let i = 0, p = 0; i < d.length; i += 4, p++) {
    const n = (hash2(p, seed * 31 + 7) + hash2(p * 7 + 3, seed) - 1) * 6;
    d[i] += n; d[i + 1] += n; d[i + 2] += n;
  }
  ctx.putImageData(g, 0, 0);
  return c;
}

/* ------------------------------------------------------------------ highlighter band (pre-rendered, revealed left -> right) */
class Highlight {
  constructor(x0, x1, yc, h, o = {}) {
    this.x0 = x0; this.x1 = x1; this.yc = yc; this.h = h; this.t0 = o.t0 ?? 0; this.dur = o.dur ?? 0.22;
    const pad = 30, cw = x1 - x0 + pad * 2, ch = h * 2 + pad * 2, c = mk(cw, ch), x = c.getContext('2d');
    const col = o.color ?? PP.hl, seed = o.seed ?? 5, r = mulberry32(seed), passes = o.passes ?? 2;
    const ox = x0 - pad, oy = yc - h - pad;
    for (let p = 0; p < passes; p++) {
      const dy = (p - (passes - 1) / 2) * h * 0.22 + (r() - 0.5) * 3, tilt = (o.tilt ?? -0.012) + (r() - 0.5) * 0.01;
      const xa = x0 - 6 + r() * 10 + (p ? 14 * r() : 0), xb = x1 + 4 - r() * 10, top = [], bot = [];
      for (let xx = xa; xx <= xb; xx += 6) {
        top.push([xx - ox, yc + dy + (xx - xa) * tilt - h * 0.5 + Noise.n1(xx / 40, seed + p) * 1.6 - oy]);
        bot.push([xx - ox, yc + dy + (xx - xa) * tilt + h * 0.5 + Noise.n1(xx / 37, seed + p + 9) * 1.6 - oy]);
      }
      x.fillStyle = rgba(col, o.alpha ?? 0.62);
      x.beginPath(); x.moveTo(top[0][0] + 5, top[0][1]); top.forEach(q => x.lineTo(q[0], q[1]));
      const e = top[top.length - 1]; x.lineTo(e[0] + 7, (e[1] + bot[bot.length - 1][1]) / 2);
      for (let i = bot.length - 1; i >= 0; i--) x.lineTo(bot[i][0], bot[i][1]);
      x.lineTo(top[0][0] - 3, (top[0][1] + bot[0][1]) / 2); x.closePath(); x.fill();
    }
    x.globalCompositeOperation = 'destination-out';
    for (let k = 0; k < 7; k++) { const yy = h + pad + (r() - 0.5) * h * 0.84; x.globalAlpha = 0.08 + r() * 0.12; x.fillStyle = '#000'; x.fillRect(pad + r() * 40, yy, (x1 - x0) * (0.4 + r() * 0.6), 1 + r() * 1.5); }
    this.c = c; this.ox = ox; this.oy = oy;
  }
  draw(ctx, t) {
    const u = E.cubicOut(seg(t, this.t0, this.t0 + this.dur)); if (u <= 0) return;
    ctx.save(); ctx.beginPath(); ctx.rect(this.ox, this.oy, (this.c.width) * u, this.c.height); ctx.clip();
    ctx.globalCompositeOperation = 'multiply'; ctx.drawImage(this.c, this.ox, this.oy); ctx.restore();
  }
}

/* ------------------------------------------------------------------ rubber stamp (白文: the character is left unprinted) */
function makeStamp(ch, size, seed = 1, color = PP.red) {
  const pad = 12, c = mk(size + pad * 2, size + pad * 2), x = c.getContext('2d'), r = mulberry32(seed * 131 + 7);
  x.translate(pad, pad);
  // slightly irregular block
  const pts = []; const jag = () => (r() - 0.5) * size * 0.012;
  const rr = size * 0.07;
  for (let i = 0; i <= 24; i++) pts.push([rr + (size - 2 * rr) * i / 24 + jag(), jag()]);
  for (let i = 0; i <= 24; i++) pts.push([size + jag(), rr + (size - 2 * rr) * i / 24 + jag()]);
  for (let i = 0; i <= 24; i++) pts.push([size - rr - (size - 2 * rr) * i / 24 + jag(), size + jag()]);
  for (let i = 0; i <= 24; i++) pts.push([jag(), size - rr - (size - 2 * rr) * i / 24 + jag()]);
  x.fillStyle = color; x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(p[0], p[1]) : x.moveTo(p[0], p[1])); x.closePath(); x.fill();
  // the character, knocked out
  const f = FT.heavy(Math.round(size * 0.74)); logText(ch, f);
  const ib = inkBox(ch, f);
  x.save(); x.globalCompositeOperation = 'destination-out'; x.font = f; x.fillStyle = '#000';
  x.fillText(ch, size / 2 - (ib.l + ib.r) / 2, size / 2 - (ib.t + ib.b) / 2); x.restore();
  // inner rim line (like a carved border)
  x.save(); x.globalCompositeOperation = 'destination-out'; x.lineWidth = Math.max(2, size * 0.018); x.strokeStyle = '#000';
  x.strokeRect(size * 0.055, size * 0.055, size * 0.89, size * 0.89); x.restore();
  // ink texture: uneven pressure + speckles of missing ink
  const id = x.getImageData(0, 0, c.width, c.height), d = id.data;
  for (let j = 0; j < c.height; j++) for (let i = 0; i < c.width; i++) {
    const k = (j * c.width + i) * 4; if (!d[k + 3]) continue;
    const n = Noise.fbm(i / (size * 0.09) + seed, j / (size * 0.09) - seed, 3), sp = hash2(i * 3 + seed, j * 5 - seed);
    let a = 0.9 + n * 0.35; if (sp > 0.985) a *= 0.2; if (n < -0.32) a *= 0.55 + (n + 0.6) * 1.2;
    d[k + 3] = Math.round(d[k + 3] * clamp(a, 0.08, 1));
  }
  x.putImageData(id, 0, 0);
  return { c, pad, size };
}

/* ------------------------------------------------------------------ the pen (fineliner, seen from above) */
function drawPen(ctx, tx, ty, ang, lift = 0, L = 560) {
  const d = [Math.cos(ang), Math.sin(ang)], n = [-d[1], d[0]];
  const prof = [[0, 1.3], [9, 2.2], [14, 4.2], [52, 11.5], [60, 13.5], [66, 14.2], [210, 14.8], [218, 16.5], [L, 16.5]];
  const hwAt = (s) => { for (let i = 1; i < prof.length; i++) if (s <= prof[i][0]) { const t = (s - prof[i - 1][0]) / (prof[i][0] - prof[i - 1][0]); return lerp(prof[i - 1][1], prof[i][1], t); } return prof[prof.length - 1][1]; };
  const P = (s, w) => [tx + d[0] * s + n[0] * w, ty + d[1] * s + n[1] * w];
  const outline = (s0, s1, off = [0, 0], k = 0) => {
    const pts = [];
    for (let s = s0; s <= s1; s += 4) { const p = P(s, hwAt(s)); pts.push([p[0] + off[0] * (s * k + lift * 16), p[1] + off[1] * (s * k + lift * 16)]); }
    for (let s = s1; s >= s0; s -= 4) { const p = P(s, -hwAt(s)); pts.push([p[0] + off[0] * (s * k + lift * 16), p[1] + off[1] * (s * k + lift * 16)]); }
    return pts;
  };
  const poly = (pts) => { ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); };
  ctx.save(); ctx.filter = `blur(${9 + lift * 4}px)`; ctx.fillStyle = `rgba(70,55,35,${0.32 - lift * 0.08})`; poly(outline(0, L, [0.55, 0.62], 0.13)); ctx.fill(); ctx.restore();
  ctx.save(); ctx.filter = `blur(${2 + lift * 4}px)`; ctx.fillStyle = `rgba(60,45,30,${0.25 - lift * 0.12})`; poly(outline(0, 60, [0.55, 0.62], 0.05)); ctx.fill(); ctx.restore();
  const shade = (s0, s1, stops) => {
    const a = P((s0 + s1) / 2, 18), b = P((s0 + s1) / 2, -18), g = ctx.createLinearGradient(a[0], a[1], b[0], b[1]);
    stops.forEach(([o2, c2]) => g.addColorStop(o2, c2)); ctx.fillStyle = g; poly(outline(s0, s1)); ctx.fill();
  };
  shade(0, 14, [[0, '#5d6168'], [0.4, '#c9ccd1'], [1, '#4a4e55']]);
  shade(14, 60, [[0, '#7c828a'], [0.3, '#e4e6e9'], [0.55, '#a9aeb5'], [1, '#5f646c']]);
  shade(60, 214, [[0, '#15171b'], [0.28, '#4a4f58'], [0.45, '#2a2d33'], [1, '#101216']]);
  shade(214, 222, [[0, '#3a3e45'], [0.3, '#9aa0a8'], [1, '#2a2d33']]);
  shade(222, L, [[0, '#1b1d22'], [0.26, '#5a606a'], [0.42, '#30343b'], [1, '#141619']]);
  ctx.strokeStyle = 'rgba(0,0,0,0.35)'; ctx.lineWidth = 1.2;
  for (let s = 80; s < 200; s += 9) { const a = P(s, 14), b = P(s, -14); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
}

/* ------------------------------------------------------------------ subtitle: style C 纸条标签
   Source Han Sans SC Medium 66, near-black on a white paper label; keywords Heavy on a yellow marker block */
const SUB = { size: 66, ls: 2, padx: 30, pady: 20, cy: 1368, yellow: '#FFD60A', text: '#141414' };
function subtitleLayout(line) {
  const med = FT.sans(SUB.size), hv = FT.heavy(SUB.size);
  const flat = line.text.replace(/ /g, ''); const isKey = new Array(flat.length).fill(-1);
  line.keys.forEach((k, ki) => { for (let i = k.i0; i < k.i0 + k.n; i++) isKey[i] = ki; });
  const items = []; let x = 0, fi = 0;
  const arr = [...line.text];
  arr.forEach((ch, i) => {
    if (ch === ' ') { x += SUB.size * 0.42; return; }
    const kf = isKey[fi] >= 0 ? hv : med; _mc.font = kf; const w = _mc.measureText(ch).width;
    items.push({ ch, x, w, key: isKey[fi], font: kf }); x += w + (i < arr.length - 1 ? SUB.ls : 0); fi++;
    logText(ch, kf);
  });
  return { items, width: x };
}
function drawSubtitle(ctx, line, t) {
  const L = line._lay || (line._lay = subtitleLayout(line));
  const x0 = (W - L.width) / 2, base = SUB.cy + 24, top = base - 60 - SUB.pady, bot = base + 12 + SUB.pady;
  const a = seg(t, line.show0, line.show0 + 0.08) * (1 - seg(t, line.show1 - 0.06, line.show1));
  if (a <= 0) return null;
  const pop = 0.965 + 0.035 * E.cubicOut(seg(t, line.show0, line.show0 + 0.14));
  ctx.save(); ctx.globalAlpha = a;
  ctx.translate(W / 2, SUB.cy); ctx.scale(pop, pop); ctx.translate(-W / 2, -SUB.cy);
  // soft shadow + label
  ctx.save(); ctx.shadowColor = 'rgba(60,45,25,0.30)'; ctx.shadowBlur = 20; ctx.shadowOffsetY = 6;
  ctx.fillStyle = 'rgba(255,255,255,0.96)'; ctx.beginPath(); ctx.roundRect(x0 - SUB.padx, top, L.width + SUB.padx * 2, bot - top, 16); ctx.fill(); ctx.restore();
  // marker blocks (swipe in when the keyword is spoken)
  line.keys.forEach((k, ki) => {
    const its = L.items.filter(it => it.key === ki); if (!its.length) return;
    const kx0 = x0 + its[0].x - 6, kx1 = x0 + its[its.length - 1].x + its[its.length - 1].w + 6;
    const u = E.cubicOut(seg(t, k.t - 0.04, k.t + 0.14)); if (u <= 0) return;
    ctx.fillStyle = SUB.yellow; ctx.fillRect(kx0, base - 30, (kx1 - kx0) * u, 38);
  });
  ctx.fillStyle = SUB.text; ctx.textBaseline = 'alphabetic';
  L.items.forEach(it => { ctx.font = it.font; ctx.fillText(it.ch, x0 + it.x, base); });
  ctx.restore();
  return [x0 - SUB.padx, top, x0 + L.width + SUB.padx, bot];
}
