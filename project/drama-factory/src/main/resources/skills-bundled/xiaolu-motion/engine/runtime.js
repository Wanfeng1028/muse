/* ==========================================================================
   xiaolu-motion · engine/runtime.js
   renderFrame(t) kernel: a pure function of t for a resolved storyboard.
   - loads component modules (components/<id>.js, ES modules)
   - per frame: motion-blur sub-frames (count requested by active components),
     each sub-frame clears the world layer (W x H) and the half-res glow layer,
     draws every active shot/transition in z order, accumulates in WebGL,
     then bloom / vignette / flash / grain (engine/post.js)
   - bboxes(t): the boxes every active component reports, for QA
   - transport: raw RGBA (premultiplied in overlay mode) POSTed to the
     driver's local sink, which pipes it into ffmpeg (no PNG sequence on disk)

   Orchestration pattern ported from 《在我开口之前》 src/main.js; the film's
   hard-coded camera / motion-blur schedule became per-component hooks.
   Component contract (see components/*.js):
     id, role, params{name:{default,type,desc}},
     draw(ctx, localT, params, tokens, env), bbox(localT, params, tokens, env),
     optional mbSamples(localT, params, tokens, env), post(localT, ...) -> {flash, ca}
   env = {W, H, fps, s (=W/1080), dur, t, glow (half-res ctx, same coordinates), subdt, mode, seed, id, invert}
   invert: the shot is on the 'invert' layer (storyboard `invert: true`), difference-blended over the
   footage by render/composite.py premul_diff; components that export `invert = true` draw plain
   white ink there (hierarchy by alpha) and no glow.
   ========================================================================== */
import { E, hashStr, resetCtx, mkCanvas } from './core.js';
import { createPost } from './post.js';
import { loadFonts, fontProbe } from './fonts.js';

let CFG = null, W = 0, H = 0, FPS = 30, TOK = null, ITEMS = [], MODS = {};
let POST = null, WC = null, wctx = null, GC = null, gctx = null, PIX = null, SUBDT = 0;
const STATS = { frames: 0, render: 0, read: 0, post: 0, subframes: 0 };

function deepMerge(a, b) {
  if (b === undefined) return a;
  if (a && typeof a === 'object' && !Array.isArray(a) && b && typeof b === 'object' && !Array.isArray(b)) {
    const o = { ...a }; for (const k of Object.keys(b)) o[k] = deepMerge(a[k], b[k]); return o;
  }
  return b;
}
export function defaultsOf(mod) {
  const d = {};
  for (const [k, v] of Object.entries(mod.params || {})) d[k] = v.default;
  return d;
}
function envFor(it, t) {
  return { W, H, fps: FPS, s: W / 1080, dur: it.t1 - it.t0, t, glow: gctx, subdt: SUBDT, mode: CFG.mode, seed: it.seed, id: it.id, invert: it.layer === 'invert' };
}

/* ---- global camera (L4) + parallax ------------------------------------------------------
   Same maths as render/camera.py: zoom log-interpolated, centre linear, `ease` of the key that
   ends the segment. A layer at depth d sees zoom z^d around a centre pulled toward the frame
   centre by d: T_d(P) = (P - c_d) * z^d + C,  c_d = C + (c - C) * d.
   d = 1 moves exactly with the footage, d = 0 is screen-locked (HUD), 0 < d < 1 parallax. */
let CAM = null;
function camState(t) {
  const K = CAM;
  if (!K || !K.length) return { z: 1, cx: 0.5, cy: 0.5 };
  if (t <= K[0].t || K.length === 1) return { z: K[0].zoom, cx: K[0].cx, cy: K[0].cy };
  const L = K[K.length - 1];
  if (t >= L.t) return { z: L.zoom, cx: L.cx, cy: L.cy };
  for (let i = 0; i < K.length - 1; i++) {
    const a = K[i], b = K[i + 1];
    if (t >= a.t && t < b.t) {
      const x = Math.min(1, Math.max(0, (t - a.t) / Math.max(1e-9, b.t - a.t)));
      const e = (E[b.ease || 'sineInOut'] || E.sineInOut)(x);
      return { z: a.zoom * Math.pow(b.zoom / a.zoom, e), cx: a.cx + (b.cx - a.cx) * e, cy: a.cy + (b.cy - a.cy) * e };
    }
  }
  return { z: L.zoom, cx: L.cx, cy: L.cy };
}
/* canvas transform [s, tx, ty] (x' = s*x + tx) for a layer at depth d at time t */
export function layerXform(t, d) {
  if (!d) return [1, 0, 0];
  const c = camState(t);
  const w = W / c.z, h = H / c.z;
  const x0 = Math.min(Math.max(c.cx * W - w / 2, 0), W - w), y0 = Math.min(Math.max(c.cy * H - h / 2, 0), H - h);
  const vx = x0 + w / 2, vy = y0 + h / 2;                       // view centre in footage coords
  const zd = Math.pow(c.z, d), cdx = W / 2 + (vx - W / 2) * d, cdy = H / 2 + (vy - H / 2) * d;
  return [zd, W / 2 - cdx * zd, H / 2 - cdy * zd];
}

async function importComponent(id) {
  if (!MODS[id]) {
    const m = await import(`/components/${id}.js`);
    MODS[id] = m.default || m;
    if (MODS[id].id !== id) throw new Error(`component file ${id}.js exports id ${MODS[id].id}`);
  }
  return MODS[id];
}

export async function boot(cfg) {
  CFG = cfg; W = cfg.canvas.w; H = cfg.canvas.h; FPS = cfg.fps; TOK = cfg.tokens; CAM = cfg.camera || null;
  const fontReport = await loadFonts(cfg.fonts || []);
  const oneWeight = w => { const n = String(w).split(/\s+/).map(Number); return n.length > 1 ? Math.max(n[0], Math.min(400, n[1])) : n[0]; };
  const probes = (cfg.fonts || []).map(f => fontProbe(f.family, oneWeight(f.weight)));
  const ids = [...new Set([...(cfg.shots || []).map(s => s.component), ...(cfg.transitions || []).map(t => t.type)])];
  for (const id of ids) await importComponent(id);
  ITEMS = [];
  (cfg.shots || []).forEach((s, k) => {
    const mod = MODS[s.component];
    ITEMS.push({ kind: 'shot', id: s.id, comp: mod, t0: s.t0, t1: s.t1, p: deepMerge(defaultsOf(mod), s.params || {}), z: s.z ?? k, seed: hashStr(s.id),
      layer: s.layer || 'front', depth: s.depth ?? 0 });
  });
  (cfg.transitions || []).forEach((tr, k) => {
    const mod = MODS[tr.type];
    ITEMS.push({ kind: 'transition', id: tr.id, comp: mod, t0: tr.t0, t1: tr.t1, p: deepMerge(defaultsOf(mod), tr.params || {}), z: 1000 + (tr.z ?? k), seed: hashStr(tr.id),
      layer: 'front', depth: 0 });
  });
  // one render pass per compositing layer: 'behind' (L1, under the person), 'front' (L3) or 'invert' (L3i); null = all
  if (cfg.layer) ITEMS = ITEMS.filter(it => it.layer === cfg.layer);
  ITEMS.sort((a, b) => a.z - b.z);
  WC = mkCanvas(W, H); wctx = WC.getContext('2d');
  GC = mkCanvas(Math.max(1, W >> 1), Math.max(1, H >> 1)); gctx = GC.getContext('2d');
  POST = createPost(W, H);
  PIX = new Uint8Array(W * H * 4);
  renderFrame(0); POST.read(PIX);             // warm-up: shader compile, glyph caches
  return { gl: POST.info(), fonts: fontReport, probes, components: ids, layer: cfg.layer || 'all',
    items: ITEMS.map(i => ({ id: i.id, kind: i.kind, comp: i.comp.id, t0: i.t0, t1: i.t1, layer: i.layer, depth: i.depth })) };
}

function activeAt(t) { return ITEMS.filter(it => t >= it.t0 && t < it.t1); }

function uniforms(t) {
  const P = TOK.post, mode = CFG.mode;
  const pick = v => (v && typeof v === 'object' && !Array.isArray(v)) ? (v[mode] ?? 0) : (v ?? 0);
  const U = {
    mode, frame: Math.round(t * FPS), bg: TOK.colors.bg, bgGlow: TOK.colors.bg_glow || TOK.colors.bg,
    bloom: P.bloom || [1, 0.85], sigma: P.bloom_sigma || [4, 8], glowAlpha: P.glow_alpha === 'luma' ? 1 : 0,
    vig: pick(P.vignette), vigR: P.vignette_radius || [0.30, 0.78], flash: 0, flashTint: [1, 1, 1], ca: 0, fade: 1, grain: pick(P.grain),
  };
  for (const it of activeAt(t)) {
    if (!it.comp.post) continue;
    const r = it.comp.post(t - it.t0, it.p, TOK, envFor(it, t));
    if (!r) continue;
    if (r.flash > U.flash) { U.flash = r.flash; if (r.flashTint) U.flashTint = r.flashTint; }
    U.ca = Math.max(U.ca, r.ca || 0);
    if (r.fade !== undefined) U.fade = Math.min(U.fade, r.fade);
  }
  // the invert pass is difference-blended: a white flash would invert the whole frame, a black
  // vignette is a no-op that only adds coverage, bloom is additive haze; fade (layer opacity) stays
  if (CFG.layer === 'invert') { U.flash = 0; U.vig = 0; U.bloom = [0, 0]; }
  if (CFG.overrides) Object.assign(U, CFG.overrides);
  return U;
}

export function renderFrame(t) {
  let N = 1;
  const sh = (TOK.post.shutter ?? 0.5) / FPS;
  for (const it of ITEMS) {
    if (!(t + sh >= it.t0 && t < it.t1) || !it.comp.mbSamples) continue;
    N = Math.max(N, it.comp.mbSamples(Math.max(0, t - it.t0), it.p, TOK, envFor(it, t)) | 0);
  }
  N = Math.max(1, Math.min(N, TOK.post.mb_max || 16));
  if (CFG.overrides && CFG.overrides.mb === 1) N = 1;
  SUBDT = N > 1 ? sh / N : 0;
  POST.begin(N);
  for (let k = 0; k < N; k++) {
    const ts = t + (N > 1 ? (k / N) * sh : 0);
    resetCtx(wctx, W, H); resetCtx(gctx, GC.width, GC.height);
    gctx.setTransform(0.5, 0, 0, 0.5, 0, 0);
    for (const it of ITEMS) {
      if (!(ts >= it.t0 && ts < it.t1)) continue;
      wctx.save(); gctx.save();
      if (it.depth) { const [sc, tx, ty] = layerXform(ts, it.depth); wctx.setTransform(sc, 0, 0, sc, tx, ty); gctx.setTransform(0.5 * sc, 0, 0, 0.5 * sc, 0.5 * tx, 0.5 * ty); }
      it.comp.draw(wctx, ts - it.t0, it.p, TOK, envFor(it, ts));
      wctx.restore(); gctx.restore();
      wctx.globalAlpha = 1; gctx.globalAlpha = 1; wctx.filter = 'none'; gctx.filter = 'none';
    }
    POST.addSub(WC, GC);
  }
  POST.finish(uniforms(t));
  STATS.subframes += N;
  return N;
}

export function bboxes(t) {
  const out = [];
  for (const it of activeAt(t)) {
    if (!it.comp.bbox) continue;
    const bs = it.comp.bbox(t - it.t0, it.p, TOK, envFor(it, t)) || [];
    const [sc, tx, ty] = layerXform(t, it.depth);
    for (const b of bs) {
      out.push({ item: it.id, item_kind: it.kind, component: it.comp.id, role: b.role || it.comp.role || (it.kind === 'transition' ? 'transition' : 'overlay'),
        layer: it.layer, depth: it.depth,
        kind: b.kind || 'shape', label: b.label || '', x: b.x * sc + tx, y: b.y * sc + ty, w: b.w * sc, h: b.h * sc, alpha: b.alpha ?? 1,
        font_px: b.font_px ? b.font_px * sc : null, bleed: !!b.bleed, full: !!b.full });
    }
  }
  return out;
}

let POSTS = 0;
export async function renderAndPost(t, url) {
  if (typeof gc === 'function' && (++POSTS % 12 === 0)) gc();
  const a = performance.now();
  renderFrame(t);
  const b = performance.now();
  POST.read(PIX);
  const c = performance.now();
  const blob = new Blob([PIX]);
  let r = null, err = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try { r = await fetch(url, { method: 'POST', body: blob, headers: { 'Content-Type': 'application/octet-stream' } }); if (r.ok) break; err = new Error('post failed ' + r.status); }
    catch (e) { err = e; }
    await new Promise(res => setTimeout(res, 50 * (attempt + 1)));
    r = null;
  }
  if (!r) throw err;
  const d = performance.now();
  STATS.frames++; STATS.render += b - a; STATS.read += c - b; STATS.post += d - c;
  return [b - a, c - b, d - c];
}
/* frames [i0, i1) at t = i / fps */
export async function renderRange(i0, i1, base) {
  const times = [0, 0, 0];
  for (let i = i0; i < i1; i++) {
    const r = await renderAndPost(i / FPS, base + '?i=' + i);
    times[0] += r[0]; times[1] += r[1]; times[2] += r[2];
  }
  return times;
}
export function stats() { return { ...STATS }; }
export async function specs(ids) {
  const out = {};
  for (const id of ids) { const m = await importComponent(id); out[id] = { id: m.id, role: m.role, desc: m.desc, params: m.params, sfx_hints: m.sfx_hints || [], invert: !!m.invert }; }
  return out;
}

export const api = { boot, renderFrame, renderAndPost, renderRange, bboxes, stats, specs };
