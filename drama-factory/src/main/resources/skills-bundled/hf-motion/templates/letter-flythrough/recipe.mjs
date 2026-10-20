// letter-flythrough recipe: validation, scene plan, plugin assets and the
// generated glyphs.js. Read by scripts/scaffold.mjs; never copied into the
// project. No music bed (no musicArgs export), so the scaffold skips it.
//
// Glyph outlines come from the bundled OFL font itself, read at scaffold time
// by the small TrueType reader below (node stdlib only): the letters are laid
// out as SVG paths, the target glyph's counter (the inner contour with the
// opposite winding) is the hole the camera flies into, and the frame-ratio
// rectangle inscribed in that hole is where the dive lands. A letter with no
// counter ("I", "K", "ㄱ") is refused here, before anything is written.
import { readFileSync } from "node:fs";

// NanumSquare (SIL OFL 1.1, OFL.txt beside it) is shared by the CJK recipes: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/NanumSquare_acEB.ttf", "assets/fonts/OFL.txt"];

export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};

export const canvas = { width: 1080, height: 830 };
export const TOTAL = 6; // seconds, fixed skeleton
// diveAt floor: the letters' 1.0 s entrance finishes before the camera moves.
export const limits = { diveAt: [1, 4.5], diveDur: [0.5, 4], hold: 0.5, letters: 6 };
const BOX = { w: 920, h: 600 }; // the word's outline box on the hero frame
const MARGIN = 0.9; // the landing rect is this fraction of the largest one in the hole

const HEX = /^#[0-9a-fA-F]{6}$/;
const FONT = new URL("../_shared/assets/fonts/NanumSquare_acEB.ttf", import.meta.url);

// ---- TrueType reader: cmap (4/12), hmtx, loca, glyf (simple + composite)
let font;
function loadFont() {
  if (font) return font;
  const b = readFileSync(FONT);
  const u16 = (o) => b.readUInt16BE(o), i16 = (o) => b.readInt16BE(o), u32 = (o) => b.readUInt32BE(o);
  const T = {};
  for (let i = 0; i < u16(4); i++) T[b.toString("latin1", 12 + 16 * i, 16 + 16 * i)] = u32(20 + 16 * i);
  const longLoca = i16(T.head + 50) === 1, nHm = u16(T.hhea + 34);
  const loca = (g) => (longLoca ? u32(T.loca + 4 * g) : 2 * u16(T.loca + 2 * g));
  let sub4, sub12;
  for (let i = 0; i < u16(T.cmap + 2); i++) {
    const r = T.cmap + 4 + 8 * i, off = T.cmap + u32(r + 4), fmt = u16(off);
    if (u16(r) === 3 || u16(r) === 0) { if (fmt === 4) sub4 ??= off; if (fmt === 12) sub12 ??= off; }
  }
  const cmap = (c) => {
    if (sub12) {
      for (let i = 0, n = u32(sub12 + 12); i < n; i++) {
        const g = sub12 + 16 + 12 * i;
        if (c >= u32(g) && c <= u32(g + 4)) return u32(g + 8) + c - u32(g);
      }
      return 0;
    }
    const seg = u16(sub4 + 6), ends = sub4 + 14, starts = ends + seg + 2, deltas = starts + seg, ros = deltas + seg;
    for (let i = 0; i < seg; i += 2) {
      if (c > u16(ends + i)) continue;
      if (c < u16(starts + i)) return 0;
      const ro = u16(ros + i);
      if (!ro) return (c + u16(deltas + i)) & 0xffff;
      const g = u16(ros + i + ro + 2 * (c - u16(starts + i)));
      return g ? (g + u16(deltas + i)) & 0xffff : 0;
    }
    return 0;
  };
  // contours: [[{x, y, on}]] in font units, y up
  const glyph = (g) => {
    const o = T.glyf + loca(g);
    if (loca(g + 1) === loca(g)) return [];
    const nc = i16(o);
    if (nc < 0) { // composite: offset (and scale) each component
      const out = [];
      for (let p = o + 10, more = true; more;) {
        const fl = u16(p), child = u16(p + 2);
        p += 4;
        const words = fl & 1;
        const dx = words ? i16(p) : b.readInt8(p), dy = words ? i16(p + 2) : b.readInt8(p + 1);
        p += words ? 4 : 2;
        const f2 = (q) => i16(q) / 16384;
        let m = [1, 0, 0, 1];
        if (fl & 0x8) { m = [f2(p), 0, 0, f2(p)]; p += 2; }
        else if (fl & 0x40) { m = [f2(p), 0, 0, f2(p + 2)]; p += 4; }
        else if (fl & 0x80) { m = [f2(p), f2(p + 2), f2(p + 4), f2(p + 6)]; p += 8; }
        // ponytail: point-matched components (ARGS_ARE_XY_VALUES unset) are taken as offsets 0
        const [ox, oy] = fl & 2 ? [dx, dy] : [0, 0];
        for (const c of glyph(child)) out.push(c.map(({ x, y, on }) => ({ x: m[0] * x + m[2] * y + ox, y: m[1] * x + m[3] * y + oy, on })));
        more = fl & 0x20;
      }
      return out;
    }
    const endPts = Array.from({ length: nc }, (_, i) => u16(o + 10 + 2 * i));
    const n = nc ? endPts[nc - 1] + 1 : 0;
    let p = o + 10 + 2 * nc;
    p += 2 + u16(p);
    const flags = [];
    while (flags.length < n) {
      const f = b[p++];
      flags.push(f);
      if (f & 8) for (let r = b[p++]; r > 0; r--) flags.push(f);
    }
    const coords = (short, same) => {
      let v = 0;
      return flags.map((f) => {
        if (f & short) { const d = b[p++]; v += f & same ? d : -d; }
        else if (!(f & same)) { v += i16(p); p += 2; }
        return v;
      });
    };
    const xs = coords(2, 16), ys = coords(4, 32);
    const out = [];
    for (let i = 0, s = 0; i < nc; s = endPts[i++] + 1) {
      out.push(xs.slice(s, endPts[i] + 1).map((x, k) => ({ x, y: ys[s + k], on: !!(flags[s + k] & 1) })));
    }
    return out;
  };
  font = { cmap, glyph, adv: (g) => u16(T.hmtx + 4 * Math.min(g, nHm - 1)) };
  return font;
}

// contour -> segments [{a, c?, b}] (c = quadratic control), implied on-points filled in
function segments(pts) {
  const n = pts.length, k = pts.findIndex((q) => q.on);
  const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, on: true });
  const ring = k < 0 ? [mid(pts[0], pts[1]), ...pts.slice(1), pts[0]] : [...pts.slice(k), ...pts.slice(0, k)];
  const start = ring[0], seg = [];
  let a = start, ctrl = null;
  for (const q of [...ring.slice(1), start]) {
    if (q.on) { seg.push({ a, c: ctrl, b: q }); a = q; ctrl = null; }
    else if (ctrl) { const m = mid(ctrl, q); seg.push({ a, c: ctrl, b: m }); a = m; ctrl = q; }
    else ctrl = q;
  }
  return seg;
}
const area = (poly) => poly.reduce((s, [x, y], i) => { const [u, v] = poly[(i + 1) % poly.length]; return s + x * v - u * y; }, 0) / 2;
const flatten = (seg) => seg.flatMap(({ a, c, b }) => {
  if (!c) return [[a.x, a.y]];
  return Array.from({ length: 8 }, (_, i) => { const t = i / 8, s = 1 - t; return [s * s * a.x + 2 * s * t * c.x + t * t * b.x, s * s * a.y + 2 * s * t * c.y + t * t * b.y]; });
});
const f2 = (v) => +v.toFixed(2);
const toPath = (seg) => "M" + f2(seg[0].a.x) + " " + f2(seg[0].a.y) +
  seg.map(({ c, b }) => (c ? `Q${f2(c.x)} ${f2(c.y)} ${f2(b.x)} ${f2(b.y)}` : `L${f2(b.x)} ${f2(b.y)}`)).join("") + "Z";

// does segment p->q touch the axis-aligned rect [x0,x1]x[y0,y1]? (Liang-Barsky)
function touches([px, py], [qx, qy], x0, y0, x1, y1) {
  let t0 = 0, t1 = 1;
  const dx = qx - px, dy = qy - py;
  for (const [p, q] of [[-dx, px - x0], [dx, x1 - px], [-dy, py - y0], [dy, y1 - py]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const r = q / p;
    if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; }
  }
  return true;
}
const insidePoly = (poly, x, y) => {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
};
// the rect is inside the hole iff its centre is and no hole edge touches it
const fits = (poly, cx, cy, hw, hh) => insidePoly(poly, cx, cy) &&
  poly.every((p, i) => !touches(p, poly[(i + 1) % poly.length], cx - hw, cy - hh, cx + hw, cy + hh));

// largest W:H rect inside the polygon: grid of centres, binary search on size, two refinements
function inscribe(poly, ratio) {
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  let best = { cx: 0, cy: 0, hw: 0 }, [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  for (let round = 0; round < 3; round++) {
    const N = 24, sx = (x1 - x0) / N, sy = (y1 - y0) / N;
    for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
      const cx = x0 + i * sx, cy = y0 + j * sy;
      if (!insidePoly(poly, cx, cy)) continue;
      let lo = 0, hi = Math.max(x1 - x0, (y1 - y0) * ratio);
      for (let k = 0; k < 24; k++) { const m = (lo + hi) / 2; if (fits(poly, cx, cy, m, m / ratio)) lo = m; else hi = m; }
      if (lo > best.hw) best = { cx, cy, hw: lo };
    }
    [x0, x1, y0, y1] = [best.cx - 2 * sx, best.cx + 2 * sx, best.cy - 2 * sy, best.cy + 2 * sy];
  }
  return best;
}

// Hero layout + hole + landing rect for CONFIG c, in canvas px (y down).
// Returns { error } when the letters cannot be built.
export function layout(c) {
  const f = loadFont();
  const chars = Array.from(c.letters);
  const gids = chars.map((ch) => f.cmap(ch.codePointAt(0)));
  const missing = chars.filter((ch, i) => !gids[i] && ch.trim());
  if (missing.length) return { error: `letters: no glyph in the bundled font for ${missing.map((m) => `'${m}'`).join(", ")}` };
  let pen = 0;
  const glyphs = gids.map((g) => { const out = f.glyph(g).map((ct) => ct.map((q) => ({ ...q, x: q.x + pen }))); pen += f.adv(g); return out; });
  const all = glyphs.flat(2);
  if (!all.length) return { error: "letters: nothing to draw" };
  const bx0 = Math.min(...all.map((q) => q.x)), bx1 = Math.max(...all.map((q) => q.x));
  const by0 = Math.min(...all.map((q) => q.y)), by1 = Math.max(...all.map((q) => q.y));
  const k = Math.min(BOX.w / (bx1 - bx0), BOX.h / (by1 - by0));
  const ox = (canvas.width - k * (bx1 - bx0)) / 2 - k * bx0, oy = (canvas.height + k * (by1 - by0)) / 2 + k * by0;
  const px = (q) => ({ x: ox + k * q.x, y: oy - k * q.y, on: q.on });
  const segs = glyphs.map((g) => g.map((ct) => segments(ct.map(px))));
  // counters: contours wound against the glyph's largest contour
  const target = segs[c.targetGlyphIndex] ?? [];
  const polys = target.map((s) => flatten(s)), areas = polys.map(area);
  const outer = areas.reduce((m, a) => (Math.abs(a) > Math.abs(m) ? a : m), 0);
  const holes = areas.map((a, i) => [a, i]).filter(([a]) => a * outer < 0).sort((p, q) => Math.abs(q[0]) - Math.abs(p[0]));
  if (!holes.length) {
    return { error: `letters: '${chars[c.targetGlyphIndex]}' (targetGlyphIndex ${c.targetGlyphIndex}) has no counter to fly into; target a glyph with an enclosed hole (A B D O P Q R, a e o, 0 6 8 9, or Hangul with ㅇ ㅁ ㅂ ㅎ)` };
  }
  const hi = holes[0][1], ratio = canvas.width / canvas.height;
  const r = inscribe(polys[hi], ratio);
  const hw = r.hw * MARGIN, hh = hw / ratio;
  return {
    ink: segs.flat().map(toPath).join(""),
    hole: toPath(target[hi]),
    rect: [f2(r.cx - hw), f2(r.cy - hh), f2(2 * hw), f2(2 * hh)],
  };
}

export function validate(c) {
  const err = [];
  const n = typeof c.letters === "string" ? Array.from(c.letters).length : 0;
  if (!n || !c.letters.trim()) err.push("letters must be a non-empty string");
  else if (n > limits.letters) err.push(`letters must be at most ${limits.letters} characters (big letters), got ${n}`);
  if (typeof c.nextText !== "string" || !c.nextText.trim()) err.push("nextText must be a non-empty string");
  const [alo, ahi] = limits.diveAt;
  if (!(c.diveAt >= alo && c.diveAt <= ahi)) err.push(`diveAt must be ${alo}..${ahi}, got ${c.diveAt}`);
  const [dlo, dhi] = limits.diveDur;
  if (!(c.diveDur >= dlo && c.diveDur <= dhi)) err.push(`diveDur must be ${dlo}..${dhi}, got ${c.diveDur}`);
  if (c.diveAt + c.diveDur > TOTAL - limits.hold) {
    err.push(`diveAt + diveDur must leave a ${limits.hold}s full-screen hold (<= ${TOTAL - limits.hold}), got ${c.diveAt + c.diveDur}`);
  }
  if (!(Number.isInteger(c.targetGlyphIndex) && c.targetGlyphIndex >= 0 && c.targetGlyphIndex < Math.max(n, 1))) {
    err.push(`targetGlyphIndex must be an integer 0..${Math.max(n - 1, 0)} (a position in letters), got ${c.targetGlyphIndex}`);
  }
  for (const k of ["paper", "charcoal", "red"]) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  if (!err.length) { const l = layout(c); if (l.error) err.push(l.error); }
  return err;
}

// Generated project files: glyphs.js holds the outlines for exactly these letters.
export function files(c) {
  const { ink, hole, rect } = layout(c);
  const g = { letters: c.letters, targetGlyphIndex: c.targetGlyphIndex, rect, hole, ink };
  return {
    "glyphs.js": "// Generated by hf-motion scaffold.mjs from the bundled font: do not edit.\n" +
      "// Re-run `scaffold.mjs letter-flythrough <dir> --update` after changing letters.\n" +
      `window.GLYPHS = ${JSON.stringify(g)};\n`,
  };
}

const r6 = (x) => +x.toFixed(6);

// Scene plan -> { elementId: [data-start, data-duration] } in seconds.
// The next scene runs the whole 6 s (it sits inside the hole from the first
// frame, so the dive is one continuous move). The letters leave the timeline
// when the dive lands: by then the hole covers the whole frame.
export function timing(c) {
  const at = {
    stage: [0, TOTAL],
    letters: [0, r6(c.diveAt + c.diveDur)],
    next: [0, TOTAL],
  };
  return { at, total: TOTAL };
}
