/* ==========================================================================
   xiaolu-motion · engine/particles.js
   Deterministic particles (pure functions of time + seed, no state):
   - sparks(): short-lived streaks thrown sideways from a cut point
     (from 《在我开口之前》 s23.js blade sparks)
   - dust(): slow drifting motes with twinkle (from s910.js dust / poster.js)
   - textPoints() + converge(): sample a string's filled outline into target
     points, then fly particles from scattered start positions onto them so
     they land forming the text shape (see references/director.md "粒子聚成文字").
   All draw the crisp particle into ctx and a soft halo into glow (if given).
   ========================================================================== */
import { TAU, clamp, lerp, E, hash2, mixHex, softDot, drawSprite, Noise, mkCanvas } from './core.js';
import { inkBox } from './text.js';

/* burst of streak sparks emitted at t = 0 (tau = time since the cut).
   o: {x, y, seed, count, spreadY (px vertical spread of emitters), speed [min,max] px/s,
       life [min,max] s, gravity px/s^2, colorHot, colorCool, glowColor, width, s (scale)} */
export function sparks(ctx, glow, tau, o) {
  if (tau < 0) return;
  const n = o.count ?? 9, s = o.s ?? 1;
  const sp = o.speed || [240, 700], lf = o.life || [0.28, 0.52];
  for (let i = 0; i < n; i++) {
    const h1 = hash2(o.seed * 31 + 7, i), h2 = hash2(o.seed * 31 + 11, i), h3 = hash2(o.seed * 31 + 13, i), h4 = hash2(o.seed * 31 + 17, i);
    const life = lf[0] + (lf[1] - lf[0]) * h3;
    if (tau > life) continue;
    const side = (o.dir ?? 0) !== 0 ? Math.sign(o.dir) : (i % 2 ? 1 : -1);
    const vx = side * (sp[0] + (sp[1] - sp[0]) * h1) * s, vy = (h2 - 0.5) * 420 * s;
    const td = 0.14, kk = 1 - Math.exp(-tau / td);
    const ox = o.x, oy = o.y + (h4 - 0.5) * (o.spreadY ?? 130) * s;
    const px = ox + vx * td * kk, py = oy + vy * td * kk + (o.gravity ?? 160) * s * tau * tau;
    const spd = Math.exp(-tau / td);
    const lx = vx * spd * 0.022, ly = vy * spd * 0.022;
    const a = Math.pow(1 - tau / life, 1.6);
    if (ctx) {
      ctx.strokeStyle = mixHex(o.colorHot || '#ffffff', o.colorCool || o.colorHot || '#ffffff', tau / life, a);
      ctx.lineWidth = (o.width ?? 1.5) * s; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(px - lx - side, py - ly); ctx.lineTo(px, py); ctx.stroke();
    }
    if (glow) drawSprite(glow, softDot('c', o.glowColor || o.colorCool || '#ffffff'), px, py, 6 * s, a * 0.8);
  }
}

/* drifting dust motes over a rect. o: {x, y, w, h, count, seed, color, glowColor, r [min,max],
   speed (px/s drift), alpha, fadeIn (0..1 multiplier)} */
export function dust(ctx, glow, t, o) {
  const n = o.count ?? 40, rr = o.r || [1.1, 3.0];
  for (let i = 0; i < n; i++) {
    const h1 = hash2(o.seed * 17 + 1, i), h2 = hash2(o.seed * 17 + 2, i), h3 = hash2(o.seed * 17 + 3, i), h4 = hash2(o.seed * 17 + 4, i);
    const vx = (h3 - 0.5) * (o.speed ?? 14), vy = -(0.3 + 0.7 * h4) * (o.speed ?? 14);
    let x = o.x + ((h1 * o.w + vx * t + Noise.n1(t * 0.3, i + o.seed) * 12) % o.w + o.w) % o.w;
    let y = o.y + ((h2 * o.h + vy * t) % o.h + o.h) % o.h;
    const tw = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * (1 + 3 * h3) + TAU * h4));
    const a = clamp((o.alpha ?? 0.6) * tw * (o.fadeIn ?? 1));
    if (a < 0.02) continue;
    const r = rr[0] + (rr[1] - rr[0]) * h4;
    if (ctx) drawSprite(ctx, softDot('d', o.color || '#ffffff'), x, y, r * 2.2, a * 0.9);
    if (glow) drawSprite(glow, softDot('c', o.glowColor || o.color || '#ffffff'), x, y, r * 5, a * 0.5);
  }
}

/* Sample a filled string's outline into target points for converge() below.
   Call once (not per frame) — the result is static and can be cached in a component's params/state.
   font/x/y follow the ctx.fillText baseline convention (x = start, y = baseline).
   o: {step (px sample stride between candidate points, default 5), pad (px canvas padding, default 8)} */
export function textPoints(str, font, x, y, o = {}) {
  const step = o.step ?? 5, pad = o.pad ?? 8;
  const ib = inkBox(str, font);
  const w = Math.max(1, Math.ceil(ib.r - ib.l) + pad * 2), h = Math.max(1, Math.ceil(ib.b - ib.t) + pad * 2);
  const c = mkCanvas(w, h), g = c.getContext('2d');
  const ox = pad - ib.l, oy = pad - ib.t;   // offset so the glyph ink sits fully inside [0,w]x[0,h]
  g.font = font; g.textAlign = 'left'; g.textBaseline = 'alphabetic'; g.fillStyle = '#fff';
  g.fillText(str, ox, oy);
  const { data } = g.getImageData(0, 0, w, h);
  const pts = [];
  for (let py = 0; py < h; py += step)
    for (let px = 0; px < w; px += step)
      if (data[(py * w + px) * 4 + 3] > 128) pts.push({ x: x - ox + px, y: y - oy + py });
  return pts;
}

/* Particles flying from scattered start positions onto textPoints() targets, landing as the text shape.
   tau: overall progress 0..1 (ease it before calling if you want a slower start/settle).
   o: {targets (required, from textPoints()), count (default targets.length), seed (default 1),
       r [min,max] px dot radius, color, glowColor,
       from {x,y,w,h} px box particles start scattered in (default: a box padded around the targets' bbox),
       spread (0..1, fraction of tau over which particles' own flights are staggered, default 0.35)} */
export function converge(ctx, glow, tau, o) {
  const targets = o.targets || [];
  if (!targets.length) return;
  const n = o.count ?? targets.length, seed = o.seed ?? 1, rr = o.r || [1.4, 3.2], stag = o.spread ?? 0.35;
  let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
  for (const p of targets) { bx0 = Math.min(bx0, p.x); by0 = Math.min(by0, p.y); bx1 = Math.max(bx1, p.x); by1 = Math.max(by1, p.y); }
  const from = o.from || { x: bx0 - 140, y: by0 - 140, w: (bx1 - bx0) + 280, h: (by1 - by0) + 280 };
  for (let i = 0; i < n; i++) {
    const tgt = targets[i % targets.length];
    const h1 = hash2(seed * 41 + 3, i), h2 = hash2(seed * 41 + 7, i), h3 = hash2(seed * 41 + 11, i), h4 = hash2(seed * 41 + 13, i);
    const x0 = from.x + h1 * from.w, y0 = from.y + h2 * from.h;
    const delay = h3 * stag;                                    // this particle's flight starts at tau = delay
    const u = clamp((tau - delay) / Math.max(0.05, 1 - delay));
    if (u <= 0) continue;
    const e = E.expoOut(u);
    const jx = Noise.n1(tau * 3 + seed, i) * 5 * (1 - e), jy = Noise.n1(tau * 3 + seed + 50, i) * 5 * (1 - e);
    const x = lerp(x0, tgt.x, e) + jx, y = lerp(y0, tgt.y, e) + jy;
    const a = clamp(u * 3);                                     // quick fade-in at the start of this particle's own flight
    const r = rr[0] + (rr[1] - rr[0]) * h4;
    if (ctx) drawSprite(ctx, softDot('cv', o.color || '#ffffff'), x, y, r, a);
    if (glow) drawSprite(glow, softDot('cvg', o.glowColor || o.color || '#ffffff'), x, y, r * 3, a * 0.6);
  }
}
