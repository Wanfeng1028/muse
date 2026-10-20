'use strict';
/* ==========================================================================
   Orchestration: camera, motion-blur sub-frames, scene dispatch, uniforms,
   frame transport.  window.renderFrame(t) is a pure function of t.
   ========================================================================== */
const WC = mkCanvas(W, H), wctx = WC.getContext('2d');
const GC = mkCanvas(W / 2, H / 2), gctx = GC.getContext('2d');
const UC = mkCanvas(W, H), uctx = UC.getContext('2d');
const PIX = new Uint8Array(W * H * 4);


/* ---------------- camera ---------------- */
const SHAKES = [[22.0, 3], [32.0, 6], [40.0, 8]];
function shotZoom(t) {
  if (t < 3.85) return 1 + 0.03 * E.sineInOut(seg(t, 0, 3.35));
  if (t < 4.0) return 1;
  if (t < 8.0) return 1 + 0.02 * E.sineInOut(seg(t, 4.0, 7.5)) * (1 - E.expoInOut(seg(t, 7.5, 8.0)));
  if (t < 15.5) return 1 + 0.035 * E.sineInOut(seg(t, 8.0, 15.0)) * (1 - E.expoInOut(seg(t, 15.0, 15.5)));
  if (t < 20.0) return 1;
  if (t < 26.0) return 1 + 0.025 * E.sineInOut(seg(t, 20.0, 24.5));
  if (t < 32.0) return 1;
  if (t < 36.0) return (1 + 0.015 * E.sineInOut(seg(t, 32.0, 34.0))) * lerp(1, 0.86 / 1.015, E.expoInOut(seg(t, 34.0, 34.75)));
  if (t < 40.0) return 1 + 0.04 * E.sineInOut(seg(t, 39.5, 40.0));
  if (t < 44.0) return 1 + 0.02 * E.sineInOut(seg(t, 40.4, 44.0));
  if (t < 50.0) return 1 + 0.055 * s10Push(t) + 0.02 * E.sineInOut(seg(t, 47.72, 50.0));
  if (t < 56.0) return 1 + 0.03 * E.sineInOut(seg(t, 50.0, 56.0));
  return 1 + 0.02 * E.sineInOut(seg(t, 56.0, 60.0));
}
function shakeAt(t) {
  let sx = 0, sy = 0;
  for (const [t0, amp] of SHAKES) {
    const s = t - t0;
    if (s >= 0 && s < 0.35) {
      const env = amp * Math.exp(-s / 0.09) * (1 - s / 0.35);
      sx += env * Math.sin(TAU * 17 * s + t0) ;
      sy += env * Math.sin(TAU * 13 * s + 1.7 + t0) * 0.8;
    }
  }
  return [sx, sy];
}
function camera(t) {
  const z = shotZoom(t);
  const [sx, sy] = shakeAt(t);
  const cy = (t >= 40 && t < 44) ? 900 : 960;
  return { zoom: z, sx, sy, cx: 540, cy, rot: shotRot(t) };
}
function shotRot(t) {
  if (t < 44.75 || t >= 50.6) return 0;
  return 1.0 * DEG * s10Push(t);
}
/* S10: accelerating push 44.75 -> 47.625, settles softly, then the quiet hold */
function s10Push(t) {
  const p = seg(t, 44.75, 47.72);
  const acc = Math.pow(p, 1.7);
  return acc * acc * (3 - 2 * acc);
}
/* R: per-subframe render context passed to scenes */
const R = {
  w: wctx, g: gctx, u: uctx, planes: [], focal: 1400, cam: null, t: 0,
  camOn(ctx) {
    const c = R.cam, s = ctx === gctx ? 0.5 : 1;
    const cr = Math.cos(c.rot || 0) * c.zoom * s, sr = Math.sin(c.rot || 0) * c.zoom * s;
    // screen = centre + shake + R(rot)·zoom·(p - centre)
    ctx.setTransform(cr, sr, -sr, cr, (c.cx + c.sx) * s - (cr * c.cx - sr * c.cy), (c.cy + c.sy) * s - (sr * c.cx + cr * c.cy));
  },
  screenOn(ctx) { const s = ctx === gctx ? 0.5 : 1; ctx.setTransform(s, 0, 0, s, 0, 0); },
  both(fn) { fn(wctx, 1); fn(gctx, 0.5); },
};
function resetCtx(ctx, w, h) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ctx.filter = 'none'; ctx.clearRect(0, 0, w, h); ctx.lineCap = 'butt'; ctx.lineJoin = 'miter'; ctx.setLineDash([]);
  ctx.shadowBlur = 0; ctx.shadowColor = 'transparent'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.letterSpacing = '0px';
}
function drawWorld(t) {
  resetCtx(wctx, W, H); resetCtx(gctx, W / 2, H / 2);
  R.t = t; R.planes = []; R.cam = camera(t);
  if (POSTER_MODE) { R.cam = { zoom: 1, sx: 0, sy: 0, cx: 540, cy: 960, rot: 0 }; drawPoster(POSTER_MODE, R); return; }
  for (const s of SCENES) {
    if (t >= s.t0 && t < s.t1) {
      R.camOn(wctx); R.camOn(gctx);
      wctx.save(); gctx.save();
      s.draw(t, R);
      wctx.restore(); gctx.restore();
      wctx.globalAlpha = 1; gctx.globalAlpha = 1; wctx.filter = 'none'; gctx.filter = 'none';
    }
  }
  if (typeof drawUIGlow === 'function') { R.screenOn(gctx); drawUIGlow(t, gctx); }
}

/* ---------------- motion blur policy ---------------- */
function mbSamples(t) {
  const inR = (a, b) => t >= a && t < b;
  if (inR(25.45, 26.3)) return 16;                                 // S6 dive through L01
  if (inR(30.0, 31.95) || inR(40.0, 40.3)) return 12;              // fastest layers / impact
  if (inR(26.0, 32.0)) return 8;                                   // S6 fly-through
  if (inR(19.35, 20.05)) return 12;                                // star field pull-back
  if (inR(44.5, 47.7)) return 10;                                  // S10 flash-backs
  if (inR(40.3, 40.6) || inR(44.0, 44.5)) return 8;
  if (inR(0.1, 0.56) || inR(3.3, 3.95) || inR(4.0, 4.55) || inR(7.5, 8.05)) return 8;
  if (inR(8.44, 9.9) || inR(10.0, 10.8)) return 8;                 // cuts, card flight
  if (inR(10.5, 11.45)) return 6;                                  // rolling digits
  if (inR(15.55, 16.15)) return 12;
  if (inR(15.0, 16.35)) return 8;
  if (inR(24.4, 26.0)) return 8;
  if (inR(21.98, 22.2)) return 6;
  if (inR(22.45, 24.4)) return 4;                                  // beat pulses
  if (inR(31.9, 32.5) || inR(35.0, 35.8) || inR(36.0, 36.8)) return 8;
  if (inR(39.48, 39.6)) return 6;
  if (inR(40.6, 44.0)) return 3;                                   // falling leaves
  if (inR(16.0, 19.35) || inR(20.2, 21.8)) return 2;
  if (t >= 44.0) return 2;
  return 1;
}
function shutterFrac(t) { return (t >= 26 && t < 32) ? 0.75 : 0.5; }

/* ---------------- per-frame uniforms ---------------- */
function frameUniforms(t) {
  const U = { time: t, frame: Math.round(t * FPS), front: [540, 900, 0, 0], warm: 0, bloomA: 1.0, bloomB: 0.85, vig: 0.30, flash: 0, ca: 0, fade: 1, dither: 1.0, bgGlow: 1.0, sigA: 4.0, sigB: 8.0 };
  if (t >= 40.0) {
    const p = seg(t, 40.0, 40.58);
    if (p >= 1) U.warm = 1;
    else { U.front = [540, 900, lerp(20, 2300, E.expoOut(p) * 0.45 + E.cubicInOut(p) * 0.55), (1 - p) * 1.0]; }
  }
  // S6 -> S7 white flash (single, no strobe)
  if (t >= 31.9 && t < 32.0) U.flash = 0.85 * E.cubicIn(seg(t, 31.9, 32.0));
  else if (t >= 32.0 && t < 32.6) U.flash = 0.85 * Math.exp(-(t - 32.0) / 0.075);
  // chromatic aberration on the three hits (1-2 frames)
  for (const [t0, a] of [[22.0, 0.0025], [32.0, 0.0045], [40.0, 0.006]]) { const s = t - t0; if (s >= 0 && s < 2.5 / FPS) U.ca = a * (1 - s * FPS / 2.5); }
  if (t >= 59.2) U.fade = 1 - E.sineInOut(seg(t, 59.2, 59.96));
  return U;
}

function posterUniforms() {
  return { time: 50, frame: 0, front: [540, 900, 0, 0], warm: 1, bloomA: 1.0, bloomB: 0.85, vig: 0.3, flash: 0, ca: 0, fade: 1, dither: 1.0, bgGlow: 1.0, sigA: 4.0, sigB: 8.0 };
}
/* ---------------- frame ---------------- */
function renderFrame(t) {
  const N = POSTER_MODE ? 1 : mbSamples(t), sh = shutterFrac(t) / FPS;
  SUBDT = N > 1 ? sh / N : 0;
  GLX.begin(N);
  for (let k = 0; k < N; k++) {
    const ts = t + (N > 1 ? (k / N) * sh : 0);
    drawWorld(ts);
    GLX.addSub(WC, GC, R.planes, R.focal);
  }
  resetCtx(uctx, W, H);
  if (!POSTER_MODE && typeof drawUI === 'function') drawUI(t, uctx);
  GLX.finish(UC, POSTER_MODE ? posterUniforms() : frameUniforms(t));
}
let POSTS = 0;
async function renderAndPost(t, url) {
  // frame blobs live outside the JS heap; collect them regularly so blob storage never fills up
  if (typeof gc === 'function' && (++POSTS % 12 === 0)) gc();
  const a = performance.now();
  renderFrame(t);
  const b = performance.now();
  GLX.read(PIX);
  const c = performance.now();
  const blob = new Blob([PIX]);
  let r = null, err = null;
  for (let attempt = 0; attempt < 4; attempt++) {           // transient localhost hiccups: retry the same bytes
    try { r = await fetch(url, { method: 'POST', body: blob, headers: { 'Content-Type': 'application/octet-stream' } }); if (r.ok) break; err = new Error('post failed ' + r.status); }
    catch (e) { err = e; }
    await new Promise(res => setTimeout(res, 50 * (attempt + 1)));
    r = null;
  }
  if (!r) throw err;
  const d = performance.now();
  return [b - a, c - b, d - c];
}
async function renderRange(i0, i1, base) {
  const times = [0, 0, 0];
  for (let i = i0; i < i1; i++) {
    const r = await renderAndPost(i / FPS, base + '?i=' + i);
    times[0] += r[0]; times[1] += r[1]; times[2] += r[2];
  }
  return times;
}
window.renderFrame = renderFrame;
window.renderAndPost = renderAndPost;
window.renderRange = renderRange;

/* ---------------- boot ---------------- */
(async function boot() {
  try {
    const specs = [
      FNT.mono(40), FNT.mono(40, 600), FNT.pf(40), FNT.pf(40, 500), FNT.pf(40, 600), FNT.song(40, 700), FNT.song(40, 900), FNT.av(20, 600),
    ];
    specs.push(FNT.sfpro(220, 250));
    await Promise.all(specs.map(s => document.fonts.load(s, '0123456789.凉字ABC')));
    await document.fonts.ready;
    await loadCues();
    // cross-check the cue sheet against the shared timeline constants
    if (CUES.tokenLand && CUES.tokenLand.length) { const exp = TOKEN_LAND.slice(1); if (CUES.tokenLand.some((v, i) => Math.abs(v - exp[i]) > 1e-6)) CUES.warnings.push('token lands differ'); }
    if (CUES.planes && CUES.planes.length) { if (CUES.planes.some((v, i) => Math.abs(v - PASS_T[i]) > 1e-6)) CUES.warnings.push('plane passes differ'); }
    window.CUEINFO = { version: CUES.version, warnings: CUES.warnings };
    for (const f of INITS) f();
    // warm-up render so shader compilation / glyph caches are hot
    renderFrame(0); GLX.read(PIX);
    window.GLINFO = GLX.info();
    window.READY = true;
  } catch (e) {
    window.BOOT_ERROR = String(e && e.stack || e);
    console.error(window.BOOT_ERROR);
  }
})();
