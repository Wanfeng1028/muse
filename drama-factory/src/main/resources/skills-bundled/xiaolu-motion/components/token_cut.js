/* ==========================================================================
   token_cut — full-screen "blade scan" transition (a mask-style cover/reveal).
   Phase 1: a bright blade sweeps across the frame; the panel (style colour,
            scan lines, token seams) closes in behind it.
   Hold   : the frame is 100 % covered (alpha = 1 everywhere) -> a cut in the
            base footage placed at the transition midpoint is invisible.
   Phase 2: a second blade sweeps the same way and uncovers the next shot.
   Sparks fly off the blade where it crosses each token seam.

   Ported from 《在我开口之前》 s23.js (blades, afterglow, sparks, anticipation
   ticks) and s78.js (scan line + gradient trail); the film cut a sentence
   into tokens at 6 hard-coded times, here the blade cuts the whole frame.
   ========================================================================== */
import { E, clamp, seg, lerp, rgba, mixHex, tokColor, tokFont, softDot, drawSprite, DEG } from '../engine/core.js';
import { textW, cjkMid } from '../engine/text.js';
import { sparks } from '../engine/particles.js';

export const id = 'token_cut';
export const role = 'transition';
export const desc = '切刀扫描转场：刀线扫过、面板随刀合拢（全屏遮罩），中点全遮盖可藏底片剪切点，第二道刀线同向扫开露出下一镜。';
export const sfx_hints = [{ id: 'whoosh', at: 'start' }, { id: 'cut', at: 'mid' }];

export const params = {
  direction: { default: 'ltr', type: 'enum', values: ['ltr', 'rtl'], desc: '刀线扫动方向。' },
  angle: { default: 9, type: 'number', min: -30, max: 30, desc: '刀线相对竖直方向的倾角（度）。' },
  sweep: { default: 0.4, type: 'number', min: 0.2, max: 0.5, desc: '每道扫动占转场时长的比例；中间 1-2*sweep 为全遮盖保持段。' },
  ease: { default: 'cubicInOut', type: 'string', desc: '扫动缓动（engine/core.js E 中的名字）。' },
  slices: { default: 6, type: 'integer', min: 1, max: 24, desc: '面板上的 token 分隔缝数量（刀过缝时迸火花）。' },
  panel: { default: '@panel', type: 'color', desc: '面板底色。' },
  panel_glow: { default: '@bg_glow', type: 'color', desc: '面板中心微光色。' },
  seam: { default: '@stroke', type: 'color', desc: '分隔缝颜色。' },
  blade: { default: '@accent_hi', type: 'color', desc: '刀线核心色。' },
  edge: { default: '@accent', type: 'color', desc: '刀线辉光/拖尾色。' },
  scanlines: { default: 0.3, type: 'number', min: 0, max: 1, desc: '面板横向扫描线强度（0 关闭）。' },
  label: { default: '', type: 'string', desc: '全遮盖时中央显示的等宽小字（可空）。' },
  sparks: { default: true, type: 'boolean', desc: '刀过分隔缝时是否迸火花。' },
  glow: { default: 1.0, type: 'number', min: 0, max: 2, desc: '刀线辉光强度。' },
};

function geom(p, env) {
  const tn = Math.tan(p.angle * DEG), W = env.W, H = env.H, s = env.s;
  const reach = Math.abs(tn) * H / 2 + 40 * s;          // blade half-lean + margin
  const x0 = -reach - 30 * s, x1 = W + reach + 30 * s;   // blade centre travel (fully off-frame at both ends)
  const sw = p.sweep * env.dur;
  return { tn, W, H, s, x0, x1, sw, tA0: 0, tA1: sw, tB0: env.dur - sw, tB1: env.dur, ez: E[p.ease] || E.cubicInOut };
}
const flip = (p, W, x) => (p.direction === 'rtl' ? W - x : x);
/* blade centre x (in 'ltr' space) at local time t for sweep [a, b] */
function bladeX(G, t, a, b) { return lerp(G.x0, G.x1, G.ez(seg(t, a, b))); }
/* local time at which the blade of sweep [a,b] crosses x at mid-height (bisection on the monotone ease) */
function crossT(G, x, a, b) {
  let lo = a, hi = b;
  for (let i = 0; i < 24; i++) { const m = (lo + hi) / 2; if (bladeX(G, m, a, b) < x) lo = m; else hi = m; }
  return (lo + hi) / 2;
}
function state(t, p, env) {
  const G = geom(p, env);
  let mode, bx;
  if (t < G.tA1) { mode = 'cover'; bx = bladeX(G, t, G.tA0, G.tA1); }
  else if (t < G.tB0) { mode = 'hold'; bx = G.x1; }
  else { mode = 'reveal'; bx = bladeX(G, t, G.tB0, G.tB1); }
  return { G, mode, bx };
}
/* covered polygon in ltr space */
function coverPoly(S) {
  const { G, mode, bx } = S, H = G.H, W = G.W, e = 12;
  const xl = y => bx + (y - H / 2) * G.tn;
  if (mode === 'hold') return [[-e, -e], [W + e, -e], [W + e, H + e], [-e, H + e]];
  if (mode === 'cover') return [[-e, -e], [xl(-e), -e], [xl(H + e), H + e], [-e, H + e]];
  return [[xl(-e), -e], [W + e, -e], [W + e, H + e], [xl(H + e), H + e]];
}

export function draw(ctx, t, p, tk, env) {
  const S = state(t, p, env), G = S.G, s = G.s, W = G.W, H = G.H;
  const poly = coverPoly(S).map(([x, y]) => [flip(p, W, x), y]);
  const panel = tokColor(tk, p.panel), pglow = tokColor(tk, p.panel_glow), edge = tokColor(tk, p.edge), blade = tokColor(tk, p.blade);
  // ---- panel (clipped to the covered region)
  ctx.save();
  ctx.beginPath(); ctx.moveTo(poly[0][0], poly[0][1]); for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i][0], poly[i][1]); ctx.closePath();
  ctx.clip();
  ctx.fillStyle = panel; ctx.fillRect(0, 0, W, H);
  const rg = ctx.createRadialGradient(W / 2, H * 0.48, 0, W / 2, H * 0.48, Math.max(W, H) * 0.62);
  rg.addColorStop(0, rgba(pglow, 0.95)); rg.addColorStop(1, rgba(pglow, 0));
  ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
  if (p.scanlines > 0) {
    ctx.fillStyle = rgba(tokColor(tk, '@hair'), clamp(p.scanlines));
    for (let y = 0; y < H; y += 6 * s) ctx.fillRect(0, y, W, 1 * s);
  }
  // token seams + ticks (the "anticipation ticks" of the original)
  for (let k = 1; k < p.slices; k++) {
    const x = flip(p, W, (k / p.slices) * W);
    ctx.fillStyle = rgba(tokColor(tk, p.seam), 0.9); ctx.fillRect(x - 0.75 * s, 0, 1.5 * s, H);
    ctx.fillStyle = rgba(edge, 0.7);
    ctx.fillRect(x - 0.75 * s, H * 0.5 - 104 * s, 1.5 * s, 12 * s); ctx.fillRect(x - 0.75 * s, H * 0.5 + 92 * s, 1.5 * s, 12 * s);
  }
  // label while fully covered
  if (p.label && S.mode === 'hold') {
    const holdLen = G.tB0 - G.tA1, u = seg(t, G.tA1, G.tA1 + Math.min(0.12, holdLen * 0.5));
    const tl = (tk.type && tk.type.label) || { font: 'mono', weight: 400, size: 24 };
    const f = tokFont(tk, tl.font, tl.size * s * 1.3, tl.weight);
    ctx.globalAlpha = E.expoOut(u); ctx.font = f; ctx.fillStyle = tokColor(tk, '@text'); ctx.textAlign = 'left';
    ctx.fillText(p.label, W / 2 - textW(p.label, f) / 2, H / 2 + cjkMid(f)); ctx.globalAlpha = 1;
  }
  ctx.restore();

  // ---- blade (not during hold)
  if (S.mode !== 'hold') {
    const bxl = S.bx;
    const top = [bxl + (-20 - H / 2) * G.tn, -20], bot = [bxl + (H + 20 - H / 2) * G.tn, H + 20];
    const A = [flip(p, W, top[0]), top[1]], B = [flip(p, W, bot[0]), bot[1]];
    const dirS = p.direction === 'rtl' ? -1 : 1;
    // gradient trail on the already-cut side
    const trail = 110 * s;
    ctx.save();
    const lg = ctx.createLinearGradient(flip(p, W, bxl), 0, flip(p, W, bxl - trail), 0);
    lg.addColorStop(0, rgba(edge, S.mode === 'cover' ? 0.22 : 0.16)); lg.addColorStop(1, rgba(edge, 0));
    ctx.fillStyle = lg;
    ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.lineTo(B[0] - dirS * trail, B[1]); ctx.lineTo(A[0] - dirS * trail, A[1]); ctx.closePath(); ctx.fill();
    ctx.restore();
    ctx.strokeStyle = blade; ctx.lineWidth = 2.5 * s; ctx.lineCap = 'butt';
    ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
    if (env.glow && p.glow > 0) {
      const g = env.glow;
      g.strokeStyle = rgba(edge, 0.85 * clamp(p.glow)); g.lineWidth = 7 * s;
      g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke();
      for (let k = 0; k < 3; k++) {
        const yy = H * (0.2 + 0.3 * k);
        drawSprite(g, softDot('c', blade), flip(p, W, bxl + (yy - H / 2) * G.tn), yy, 34 * s, 0.55 * p.glow);
      }
    }
  }
  // ---- sparks where each blade crossed a seam (they outlive the blade a little)
  if (p.sparks) {
    for (const [a, b, tag] of [[G.tA0, G.tA1, 1], [G.tB0, G.tB1, 2]]) {
      if (t < a) continue;
      for (let k = 1; k < p.slices; k++) {
        const sx = (k / p.slices) * W;
        const tc = crossT(G, sx, a, b), tau = t - tc;
        if (tau < 0 || tau > 0.6) continue;
        const yy = H * (0.18 + 0.64 * ((k * 0.618 + tag * 0.29) % 1));
        const xx = sx + (yy - H / 2) * G.tn;
        sparks(ctx, env.glow, tau, { x: flip(p, W, xx), y: yy, seed: k * 7 + tag * 101 + (env.seed % 997), count: 7, s,
          dir: 0, spreadY: 60, colorHot: blade, colorCool: edge, glowColor: edge });
        if (env.glow && tau < 0.25) drawSprite(env.glow, softDot('c', edge), flip(p, W, xx), yy, 60 * s, 0.7 * Math.exp(-tau / 0.07));
      }
    }
  }
}

export function bbox(t, p, tk, env) {
  const S = state(t, p, env), G = S.G, W = G.W, H = G.H;
  const xs = coverPoly(S).map(([x]) => flip(p, W, x));
  const l = clamp(Math.min(...xs), 0, W), r = clamp(Math.max(...xs), 0, W);
  const out = [];
  if (r > l) out.push({ kind: 'shape', label: S.mode === 'hold' ? 'panel(full)' : 'panel', x: l, y: 0, w: r - l, h: H, full: S.mode === 'hold', bleed: true });
  return out;
}

/* fast blade -> more sub-frames */
export function mbSamples(t, p, tk, env) {
  const G = geom(p, env);
  return (t < G.tA1 || t >= G.tB0) ? 10 : 1;
}

export default { id, role, desc, params, sfx_hints, draw, bbox, mbSamples };
