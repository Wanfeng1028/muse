/* ==========================================================================
   frame_tunnel — 画框隧道卡
   Picture frames nested one inside the next recede into the dark, each turned
   a few degrees from the last. The camera pushes through them — every frame
   rushes past the lens — and settles on the innermost canvas, where a title
   in gold focuses in.

   Look: a gallery at night. Oxblood-black velvet space, warm haze in the
   depth, gilded frames built from a real molding profile (bead, cove, flat,
   ogee, sight edge) lit per side from above, a brass picture light on every
   other frame. All vector (sharp at any scale), perspective by 1/z.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, hash2, rgba, tokFont, mkCanvas, softDot, drawSprite, Noise } from '../engine/core.js';
import { inkBox } from '../engine/text.js';
import { dust } from '../engine/particles.js';

export const id = 'frame_tunnel';
export const role = 'card';
export const desc = '画框隧道卡：一层层嵌套的描金画框向深处排列并逐层微转，镜头穿过画框向前推，最后停在最里层画布上，金色标题聚焦出现。全屏不透明。';

export const params = {
  title: { default: '下一幕', type: 'string', desc: '最里层画布上的标题。' },
  sub: { default: 'ACT II', type: 'string', desc: '标题下的小字。' },
  frames: { default: 9, type: 'number', desc: '画框层数（含最里层）。' },
  twist: { default: 5, type: 'number', desc: '相邻画框的旋转角（度）。' },
  gold: { default: '#D6AE5F', type: 'color', desc: '金色高光。' },
  wall: { default: '#120607', type: 'color', desc: '深处底色。' },
  t_push: { default: 0.25, type: 'number', desc: '开始推进。' },
  t_arrive: { default: 3.2, type: 'number', desc: '停在最里层。' },
};

/* ------------------------------------------------------------------ world */
const F = 1500;                         // focal length (px)
const GAP = 760;                        // depth between frames
const Z0 = 1500;                        // depth of the first frame
function frameZ(k) { return Z0 + k * GAP; }
function endCam(p) { return frameZ(p.frames - 1) - 1680; }          // where the camera stops
function camZ(t, p) {
  const u = seg(t, p.t_push, p.t_arrive);
  // slow start, long fast middle, soft landing
  const e = u < 0.5 ? 0.5 * Math.pow(2 * u, 2.2) : 1 - 0.5 * Math.pow(2 * (1 - u), 2.6);
  return endCam(p) * e;
}
export function timing(p) {
  // when each frame passes the lens (for the whooshes)
  const passes = [];
  for (let k = 0; k < p.frames - 1; k++) {
    let lo = p.t_push, hi = p.t_arrive;
    if (camZ(hi, p) < frameZ(k) - 60) continue;
    for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (camZ(m, p) < frameZ(k) - 60) lo = m; else hi = m; }
    passes.push(+hi.toFixed(4));
  }
  return { push: p.t_push, arrive: p.t_arrive, passes, title: p.t_arrive + 0.1 };
}

/* ------------------------------------------------------------------ frame drawing */
const STYLE = [
  { name: 'gilt', base: [214, 174, 95], dark: [74, 48, 20], M: 150 },
  { name: 'lacquer', base: [60, 44, 36], dark: [14, 9, 8], M: 118, lip: [214, 174, 95] },
  { name: 'gilt2', base: [200, 158, 88], dark: [66, 40, 16], M: 132 },
];
// molding profile: [from, to, kind] as fractions of the molding width, outside -> inside
const PROFILE = [[0, 0.05, 'edge'], [0.05, 0.13, 'bead'], [0.13, 0.36, 'cove'], [0.36, 0.56, 'flat'], [0.56, 0.82, 'ogee'], [0.82, 0.93, 'liner'], [0.93, 1, 'fillet']];
// light factor per side (top lit from the picture light above, left from the key)
const SIDE_LIGHT = { top: 1.12, left: 0.92, right: 0.62, bottom: 0.48 };

function col(c, k, a = 1) { return `rgba(${Math.min(255, c[0] * k) | 0},${Math.min(255, c[1] * k) | 0},${Math.min(255, c[2] * k) | 0},${a})`; }
function mixc(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }

function drawFrame(ctx, glow, k, cx, cy, s, rot, fog, p, st) {
  const fw = 1000, fh = 1500;                        // outer size in world units (portrait canvas)
  const M = st.M;
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.scale(s, s);
  const ox = fw / 2, oy = fh / 2;
  const fogc = [18, 6, 7];
  for (const [a, b, kind] of PROFILE) {
    const o0 = M * a, o1 = M * b;                     // inset of this band
    const sides = [
      ['top', [-ox + o0, -oy + o0], [ox - o0, -oy + o0], [ox - o1, -oy + o1], [-ox + o1, -oy + o1], [0, -oy + o0], [0, -oy + o1]],
      ['bottom', [-ox + o1, oy - o1], [ox - o1, oy - o1], [ox - o0, oy - o0], [-ox + o0, oy - o0], [0, oy - o0], [0, oy - o1]],
      ['left', [-ox + o0, -oy + o0], [-ox + o1, -oy + o1], [-ox + o1, oy - o1], [-ox + o0, oy - o0], [-ox + o0, 0], [-ox + o1, 0]],
      ['right', [ox - o1, -oy + o1], [ox - o0, -oy + o0], [ox - o0, oy - o0], [ox - o1, oy - o1], [ox - o0, 0], [ox - o1, 0]],
    ];
    for (const [side, A, B, C, D, g0, g1] of sides) {
      const L = SIDE_LIGHT[side];
      let c0, c1, c2;
      const base = kind === 'liner' && st.lip ? st.lip : st.base, dark = st.dark;
      if (kind === 'edge') { c0 = dark; c1 = dark; c2 = mixc(dark, base, 0.4); }
      else if (kind === 'bead') { c0 = mixc(dark, base, 0.5); c1 = base; c2 = mixc(dark, base, 0.4); }
      else if (kind === 'cove') { c0 = mixc(dark, base, 0.25); c1 = mixc(dark, base, 0.55); c2 = mixc(base, [255, 236, 190], 0.25); }
      else if (kind === 'flat') { c0 = mixc(dark, base, 0.75); c1 = base; c2 = mixc(dark, base, 0.8); }
      else if (kind === 'ogee') { c0 = mixc(base, [255, 240, 200], 0.45); c1 = base; c2 = mixc(dark, base, 0.35); }
      else if (kind === 'liner') { c0 = st.lip ? mixc(st.lip, [255, 240, 200], 0.2) : mixc(dark, base, 0.2); c1 = st.lip ? st.lip : mixc(dark, base, 0.1); c2 = dark; }
      else { c0 = [255, 236, 190]; c1 = base; c2 = dark; }
      const f = 1 - fog;
      const g = ctx.createLinearGradient(g0[0], g0[1], g1[0], g1[1]);
      g.addColorStop(0, col(mixc(fogc, c0, f), L)); g.addColorStop(0.5, col(mixc(fogc, c1, f), L)); g.addColorStop(1, col(mixc(fogc, c2, f), L));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.lineTo(C[0], C[1]); ctx.lineTo(D[0], D[1]); ctx.closePath(); ctx.fill();
    }
    if (kind === 'bead' && s * M > 40) {           // carved bead chain (only when big enough to read)
      const r = (o1 - o0) * 0.42, inset = (o0 + o1) / 2, step = r * 2.3;
      const hl = col(mixc(fogc, [255, 238, 196], 1 - fog), 1, 0.8), sh = col(mixc(fogc, st.dark, 1 - fog), 1, 0.7);
      for (const [x0, y0, x1, y1, L] of [[-ox + inset, -oy + inset, ox - inset, -oy + inset, 1.1], [-ox + inset, oy - inset, ox - inset, oy - inset, 0.5], [-ox + inset, -oy + inset, -ox + inset, oy - inset, 0.9], [ox - inset, -oy + inset, ox - inset, oy - inset, 0.6]]) {
        const len = Math.hypot(x1 - x0, y1 - y0), n = Math.floor(len / step);
        for (let i = 0; i <= n; i++) {
          const x = lerp(x0, x1, i / n), y = lerp(y0, y1, i / n);
          ctx.fillStyle = sh; ctx.beginPath(); ctx.arc(x + r * 0.2, y + r * 0.25, r, 0, TAU); ctx.fill();
          ctx.fillStyle = col(mixc(fogc, st.base, 1 - fog), L); ctx.beginPath(); ctx.arc(x, y, r * 0.92, 0, TAU); ctx.fill();
          ctx.fillStyle = hl; ctx.beginPath(); ctx.arc(x - r * 0.3, y - r * 0.35, r * 0.28, 0, TAU); ctx.fill();
        }
      }
    }
  }
  // corner cartouches (carved leaf clusters) on the gilt frames
  if (st.name !== 'lacquer' && s * M > 25) {
    for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const x = sx * (ox - M * 0.25), y = sy * (oy - M * 0.25);
      const L = sy < 0 ? 1.1 : 0.55;
      ctx.fillStyle = col(mixc([18, 6, 7], st.dark, 1 - fog), 1, 0.9);
      ctx.beginPath(); ctx.ellipse(x + 4, y + 5, M * 0.3, M * 0.3, 0, 0, TAU); ctx.fill();
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * TAU + (sx * sy > 0 ? 0.3 : -0.3);
        ctx.fillStyle = col(mixc([18, 6, 7], mixc(st.base, [255, 236, 190], 0.2 * (i % 2)), 1 - fog), L);
        ctx.beginPath(); ctx.ellipse(x + Math.cos(a) * M * 0.14, y + Math.sin(a) * M * 0.14, M * 0.13, M * 0.06, a, 0, TAU); ctx.fill();
      }
      ctx.fillStyle = col(mixc([18, 6, 7], [255, 240, 205], 1 - fog), L); ctx.beginPath(); ctx.arc(x - M * 0.02, y - M * 0.03, M * 0.06, 0, TAU); ctx.fill();
    }
  }
  ctx.restore();
  // picture light above every other frame: brass bar + warm pool on the top rail (in the glow layer too)
  if (k % 2 === 0 && fog < 0.9) {
    const lx = cx + Math.sin(rot) * (fh / 2 + 70) * s, ly = cy - Math.cos(rot) * (fh / 2 + 70) * s;
    ctx.save(); ctx.translate(lx, ly); ctx.rotate(rot);
    ctx.fillStyle = col([176, 132, 72], 1 - 0.8 * fog); ctx.fillRect(-180 * s, -14 * s, 360 * s, 28 * s);
    ctx.fillStyle = col([255, 226, 170], 1 - 0.8 * fog, 0.8); ctx.fillRect(-180 * s, -14 * s, 360 * s, 5 * s);
    ctx.restore();
    const a = (1 - fog) * 0.9;
    drawSprite(ctx, softDot('lamp', '#FFD9A0'), lx, ly + 40 * s, 360 * s, 0.35 * a);
    if (glow) drawSprite(glow, softDot('lampg', '#FFC478'), lx, ly + 20 * s, 300 * s, 0.7 * a);
  }
}

/* innermost canvas: dark painting ground + the title */
function drawCanvas(ctx, glow, t, cx, cy, s, rot, fog, p, tk, T) {
  const fw = 1000 - 2 * STYLE[(p.frames - 1) % 3].M, fh = 1500 - 2 * STYLE[(p.frames - 1) % 3].M;
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.scale(s, s);
  const g = ctx.createRadialGradient(0, -fh * 0.15, 20, 0, 0, fh * 0.75);
  g.addColorStop(0, col(mixc([18, 6, 7], [62, 38, 30], 1 - fog), 1)); g.addColorStop(1, col(mixc([18, 6, 7], [20, 12, 12], 1 - fog), 1));
  ctx.fillStyle = g; ctx.fillRect(-fw / 2, -fh / 2, fw, fh);
  // canvas weave
  ctx.globalAlpha = 0.08 * (1 - fog);
  for (let y = -fh / 2; y < fh / 2; y += 6) { ctx.fillStyle = y % 12 === 0 ? '#000' : '#fff'; ctx.fillRect(-fw / 2, y, fw, 1); }
  ctx.globalAlpha = 1;
  const u = seg(t, T.title, T.title + 0.8);
  if (u > 0) {
    const e = E.expoOut(u);
    const font = tokFont(tk, 'serif', 170, 900);
    ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = '24px';
    const ib = inkBox(p.title, font);
    ctx.filter = `blur(${(14 * (1 - e)).toFixed(2)}px)`;
    const tg = ctx.createLinearGradient(0, -130, 0, 40);
    tg.addColorStop(0, '#FFE9B8'); tg.addColorStop(0.5, p.gold); tg.addColorStop(1, '#8C6326');
    ctx.fillStyle = tg; ctx.globalAlpha = e;
    ctx.fillText(p.title, 12, -(ib.t + ib.b) / 2 - 40 + 30 * (1 - e));
    ctx.filter = 'none'; ctx.letterSpacing = '12px';
    ctx.font = tokFont(tk, 'sans', 40, 500); ctx.fillStyle = col([214, 174, 95], 1, 0.75 * e);
    ctx.fillText(p.sub, 6, 150);
    ctx.fillStyle = col([214, 174, 95], 1, 0.45 * e); ctx.fillRect(-90 * e, 92, 180 * e, 2);
    ctx.letterSpacing = '0px'; ctx.globalAlpha = 1;
  }
  ctx.restore();
  if (glow && u > 0) { const e = E.expoOut(u); drawSprite(glow, softDot('tg', '#E8B868'), cx, cy - 40 * s, 420 * s, 0.35 * e); }
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  const u = seg(t, p.t_push, p.t_arrive);
  if (u > 0.08 && u < 0.97) return 12;
  if (u > 0 && u < 1) return 6;
  return 2;
}
export function post(t, p) { return { fade: smooth(seg(t, 0, 0.25)) }; }

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, T = timing(p), glow = env.glow;
  const cz = camZ(t, p);
  // velvet dark + warm haze in the depth
  ctx.fillStyle = p.wall; ctx.fillRect(0, 0, W, H);
  const hz = ctx.createRadialGradient(W / 2, H * 0.47, 10, W / 2, H * 0.47, H * 0.55);
  hz.addColorStop(0, 'rgba(120,52,34,0.35)'); hz.addColorStop(0.4, 'rgba(60,20,16,0.18)'); hz.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = hz; ctx.fillRect(0, 0, W, H);
  // camera roll follows the twist a little, plus a drift
  const roll = -(cz / endCam(p)) * (p.frames - 1) * (p.twist * Math.PI / 180);   // the innermost frame ends upright
  const cx = W / 2 + Noise.n1(t * 0.3, 3) * 6, cy = H * 0.47 + Noise.n1(t * 0.3, 9) * 6;
  // frames far -> near
  for (let k = p.frames - 1; k >= 0; k--) {
    const z = frameZ(k) - cz;
    if (z < 40) continue;
    const s = F / z;
    if (s > 6) continue;
    const rot = k * p.twist * Math.PI / 180 + roll;
    const fog = clamp((z - 1700) / 5200, 0, 0.92);
    const st = STYLE[k % 3];
    if (k === p.frames - 1) drawCanvas(ctx, glow, t, cx, cy, s, rot, fog, p, tk, T);
    drawFrame(ctx, glow, k, cx, cy, s, rot, fog, p, st);
  }
  // motes drifting in the lamp light
  dust(ctx, glow, t, { x: 0, y: 0, w: W, h: H, count: 60, seed: 5, color: '#FFD9A6', glowColor: '#E0A860', r: [0.8, 2.6], speed: 12, alpha: 0.4, fadeIn: smooth(seg(t, 0, 0.6)) });
}

export function bbox(t, p, tk, env) {
  return [{ kind: 'text', label: p.title, x: env.W * 0.2, y: env.H * 0.38, w: env.W * 0.6, h: env.H * 0.16, font_px: 120 }];
}
