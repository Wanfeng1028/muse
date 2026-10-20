/* ==========================================================================
   xiaolu-motion · engine/text.js
   Chinese per-character typesetting: measurement caches, per-char layout,
   ink boxes, CJK optical centring, and the "focus in" character animation.

   Ported from 《在我开口之前》 core.js (textW / layoutChars / inkBox / cjkMid)
   and ui.js (drawFocusText). New: every drawing helper also reports the box it
   occupies, so components can return exact bboxes for QA.
   ========================================================================== */
import { E, clamp, seg, setFilter } from './core.js';

let _m = null;
function M() {
  if (!_m) {
    const c = (typeof OffscreenCanvas !== 'undefined') ? new OffscreenCanvas(8, 8) : document.createElement('canvas');
    _m = c.getContext('2d');
  }
  return _m;
}
const _wCache = new Map(), _lCache = new Map(), _iCache = new Map(), _cjk = new Map();

/* advance width of a string, drawn char by char with letter spacing ls (px) */
export function textW(str, font, ls = 0) {
  const key = font + '|' + ls + '|' + str;
  let w = _wCache.get(key);
  if (w === undefined) {
    const m = M(); m.font = font; m.letterSpacing = '0px';
    w = 0; const arr = [...str];
    for (const ch of arr) w += m.measureText(ch).width + ls;
    if (arr.length) w -= ls;
    _wCache.set(key, w);
  }
  return w;
}
/* per-char layout: {chars:[{c,x,w,i}], width}; x relative to the string start */
export function layoutChars(str, font, ls = 0) {
  const key = font + '|' + ls + '|' + str;
  let L = _lCache.get(key);
  if (L) return L;
  const m = M(); m.font = font; m.letterSpacing = '0px';
  const chars = []; let x = 0;
  const arr = [...str];
  arr.forEach((ch, i) => {
    const w = m.measureText(ch).width;
    chars.push({ c: ch, x, w, i });
    x += w + (i < arr.length - 1 ? ls : 0);
  });
  L = { chars, width: x };
  _lCache.set(key, L);
  return L;
}
/* glyph ink bounds relative to (0, alphabetic baseline): l,r,t(<0),b */
export function inkBox(str, font) {
  const key = font + '|' + str;
  let b = _iCache.get(key);
  if (!b) {
    const m = M(); m.font = font; m.letterSpacing = '0px';
    const r = m.measureText(str);
    b = { l: -r.actualBoundingBoxLeft, r: r.actualBoundingBoxRight, t: -r.actualBoundingBoxAscent, b: r.actualBoundingBoxDescent, w: r.width,
      fa: r.fontBoundingBoxAscent, fd: r.fontBoundingBoxDescent };
    _iCache.set(key, b);
  }
  return b;
}
/* baseline offset that centres CJK ink (measured on 字) at a given y: baseline = y + cjkMid(font) */
export function cjkMid(font) {
  let v = _cjk.get(font);
  if (v === undefined) { const b = inkBox('字', font); v = -(b.t + b.b) / 2; _cjk.set(font, v); }
  return v;
}
/* union ink box of a laid-out string at (x0, baseline), in canvas px */
export function stringInk(str, font, x0, base, ls = 0) {
  const L = layoutChars(str, font, ls);
  let l = Infinity, r = -Infinity, t = Infinity, b = -Infinity;
  for (const ch of L.chars) {
    if (!ch.c.trim()) continue;
    const ib = inkBox(ch.c, font);
    l = Math.min(l, x0 + ch.x + ib.l); r = Math.max(r, x0 + ch.x + ib.r);
    t = Math.min(t, base + ib.t); b = Math.max(b, base + ib.b);
  }
  if (!Number.isFinite(l)) return null;
  return { x: l, y: t, w: r - l, h: b - t };
}

/* ---------------------------------------------------------------------------
   Focus-in text (per-char stagger: rise + un-blur + fade in, cubic-in exit).
   o: {font, x, y(baseline), align, color (str | fn(i,e)), ls, stagger, dur, dy,
       blur, tIn, tOut, outDur, alpha, easeIn, easeOut, scale0}
   Returns {x0, width, L, chars:[{i,c,x,y,a,e}]} describing what was (or would be)
   drawn; pass ctx = null to get the geometry only (used by bbox()).
   --------------------------------------------------------------------------- */
export function focusText(ctx, str, t, o) {
  const L = layoutChars(str, o.font, o.ls || 0);
  let x0 = o.x;
  if (o.align === 'center') x0 = o.x - L.width / 2; else if (o.align === 'right') x0 = o.x - L.width;
  const stag = o.stagger ?? 0.022, dur = o.dur ?? 0.42, dy0 = o.dy ?? 18, bl0 = o.blur ?? 10;
  const eIn = E[o.easeIn || 'expoOut'], eOut = E[o.easeOut || 'cubicIn'];
  const s0 = o.scale0 ?? 1;
  let outP = 0;
  if (o.tOut !== undefined && t >= o.tOut) outP = eOut(seg(t, o.tOut, o.tOut + (o.outDur ?? 0.26)));
  const res = { x0, width: L.width, L, chars: [] };
  if (outP >= 1) return res;
  if (ctx) { ctx.font = o.font; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.letterSpacing = '0px'; }
  for (const ch of L.chars) {
    const tau = t - (o.tIn || 0) - ch.i * stag;
    if (tau <= 0) continue;
    const e = eIn(tau / dur);
    const a = e * (1 - outP) * (o.alpha ?? 1);
    if (a <= 0.003) continue;
    const dy = dy0 * (1 - e) - 10 * outP;
    const bl = bl0 * (1 - e) + 6 * outP;
    const sc = s0 + (1 - s0) * e;
    const cx = x0 + ch.x, cy = o.y + dy;
    res.chars.push({ i: ch.i, c: ch.c, x: cx, y: cy, a, e, w: ch.w, sc });
    if (!ctx) continue;
    setFilter(ctx, bl);
    const ga = ctx.globalAlpha;
    ctx.globalAlpha = ga * a;
    ctx.fillStyle = typeof o.color === 'function' ? o.color(ch.i, e) : o.color;
    if (sc !== 1) {
      ctx.save(); ctx.translate(cx + ch.w / 2, cy); ctx.scale(sc, sc); ctx.fillText(ch.c, -ch.w / 2, 0); ctx.restore();
    } else ctx.fillText(ch.c, cx, cy);
    ctx.globalAlpha = ga;
  }
  if (ctx) ctx.filter = 'none';
  return res;
}
/* ink box of the visible characters of a focusText() result */
export function focusInk(res, font, minA = 0.05) {
  let l = Infinity, r = -Infinity, t = Infinity, b = -Infinity, amax = 0;
  for (const ch of res.chars) {
    if (ch.a < minA || !ch.c.trim()) continue;
    const ib = inkBox(ch.c, font);
    const sc = ch.sc || 1, cxm = ch.x + ch.w / 2;
    l = Math.min(l, cxm + (ch.x + ib.l - cxm) * sc); r = Math.max(r, cxm + (ch.x + ib.r - cxm) * sc);
    t = Math.min(t, ch.y + ib.t * sc); b = Math.max(b, ch.y + ib.b * sc);
    amax = Math.max(amax, ch.a);
  }
  if (!Number.isFinite(l)) return null;
  return { x: l, y: t, w: r - l, h: b - t, alpha: amax };
}
