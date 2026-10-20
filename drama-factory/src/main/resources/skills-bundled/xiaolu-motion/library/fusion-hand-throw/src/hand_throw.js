/* ==========================================================================
   hand_throw — 手势抛字（真人融合）
   Real footage. Apple Vision hand pose (VNDetectHumanHandPoseRequest, run in
   the prep step) tracks the hand; every time the speaker names an item and
   the hand flicks, that word pops out of the hand, rides it for a moment and
   is thrown along the hand's own direction of motion, arcing up to stick on
   the wall beside his head. The biggest flick throws the biggest word.

   Release frame = the frame of peak upward speed of the smoothed knuckle
   track inside a window around the spoken word; launch direction and speed
   come from the hand. Tags are styled after what they name (collage paper,
   film frame, magazine masthead, keynote slide). Footage pixels are never
   altered; everything flies to the side of the face, never across it.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, springKick, hash2, rgba, rrect, tokFont, mkCanvas, softDot, drawSprite } from '../engine/core.js';
import { inkBox, layoutChars } from '../engine/text.js';
import { PLATE, preparePlate, frameAt, faceStats } from './plate.js';

export const id = 'hand_throw';
export const role = 'fusion';
export const desc = '手势抛字：用 Vision 手部姿态追踪真人的手，手一甩，说到的词从手的位置飞出，沿手的运动方向抛到头部一侧的墙上贴住。';

export const params = {
  plate_start: { default: 2550, type: 'number', desc: '底片起始帧（prep 写入的帧号）。' },
  plate_end: { default: 2685, type: 'number', desc: '底片结束帧（不含）。' },
  words: {
    default: [{ text: '拼接', at: 0.54, style: 'collage' }, { text: '胶片', at: 1.49, style: 'film' },
      { text: '杂志', at: 2.5, style: 'mag' }, { text: '发布会', at: 3.33, style: 'keynote' }],
    type: 'any', desc: '要抛出的词：text、at（这个词开口的时刻，相对本镜头，秒）、style（collage/film/mag/keynote）。',
  },
  slots: { default: [[985, 285, -4], [978, 400, 3], [988, 515, -3], [980, 630, 4]], type: 'any', desc: '每个词最后贴住的位置 [x, y, 旋转度]。' },
  flight: { default: 0.5, type: 'number', desc: '飞行时长（秒）。' },
  window: { default: [-0.35, 0.25], type: 'any', desc: '在词开口前后多长的窗口里找手甩出的那一帧（秒）。' },
};

/* ------------------------------------------------------------------ hand track from Vision */
let TRACK = null, REL = null;
function knuckles(h) {                              // top of the hand: the knuckle row (MCP joints)
  const ks = ['indexMCP', 'middleMCP', 'ringMCP', 'littleMCP'];
  const pts = ks.map(k => h.pts[k]).filter(v => v && v[2] > 0.3);
  if (pts.length < 2) return null;
  return [pts.reduce((a, v) => a + v[0], 0) / pts.length, Math.min(...pts.map(v => v[1]))];
}
function buildTrack(p) {
  const n = p.plate_end - p.plate_start, fs = faceStats();
  const cx = fs ? fs.x + fs.w / 2 : 540;
  const raw = new Array(n).fill(null);
  let prev = null;
  for (let i = 0; i < n; i++) {
    const d = PLATE.data.hands.get(i);
    if (!d) continue;
    // the hand on the far side of the face centre that we have been following (nearest to the last point)
    const cands = d.hands.map(knuckles).filter(k => k && k[0] > cx + 120);
    if (!cands.length) continue;
    cands.sort((a, b) => (prev ? Math.hypot(a[0] - prev[0], a[1] - prev[1]) - Math.hypot(b[0] - prev[0], b[1] - prev[1]) : a[1] - b[1]));
    raw[i] = cands[0]; prev = cands[0];
  }
  // fill gaps linearly, hold the ends
  const idx = raw.map((v, i) => (v ? i : -1)).filter(i => i >= 0);
  const filled = raw.map((v, i) => {
    if (v) return v;
    const a = idx.filter(j => j < i).pop(), b = idx.find(j => j > i);
    if (a === undefined) return raw[b]; if (b === undefined) return raw[a];
    const u = (i - a) / (b - a); return [lerp(raw[a][0], raw[b][0], u), lerp(raw[a][1], raw[b][1], u)];
  });
  // Gaussian smoothing (sigma 1.2 frames) removes the one-frame fit flips, keeps real flicks
  const K = [-3, -2, -1, 0, 1, 2, 3].map(k => [k, Math.exp(-k * k / (2 * 1.44))]);
  const sm = filled.map((_, i) => { let x = 0, y = 0, w = 0; for (const [k, g] of K) { const j = clamp(i + k, 0, n - 1); x += filled[j][0] * g; y += filled[j][1] * g; w += g; } return [x / w, y / w]; });
  return { pos: sm, seen: raw.map(Boolean) };
}
function findReleases(p) {
  const n = TRACK.pos.length, out = [];
  for (const w of p.words) {
    const a = clamp(Math.round((w.at + p.window[0]) * 30), 1, n - 2), b = clamp(Math.round((w.at + p.window[1]) * 30), 1, n - 2);
    let best = -1, bs = -1e9;
    for (let i = a; i <= b; i++) {
      const vx = (TRACK.pos[i + 1][0] - TRACK.pos[i - 1][0]) / 2, vy = (TRACK.pos[i + 1][1] - TRACK.pos[i - 1][1]) / 2;
      const s = -vy + 0.3 * vx;                           // upward (and outward) speed
      if (s > bs) { bs = s; best = i; }
    }
    const i = best, vx = (TRACK.pos[i + 1][0] - TRACK.pos[i - 1][0]) / 2, vy = (TRACK.pos[i + 1][1] - TRACK.pos[i - 1][1]) / 2;
    out.push({ frame: i, t: i / 30, pos: TRACK.pos[i], v: [vx * 30, vy * 30], speed: bs * 30, strong: bs > 6 });
  }
  return out;
}
export async function prepare(p) {
  await preparePlate(p, { layers: ['plate'], json: ['faces', 'hands'] });
  TRACK = buildTrack(p);
  REL = findReleases(p);
  return REL;
}
export function timing(p) {
  if (!REL) return null;
  return { releases: REL.map(r => r.t), appear: REL.map(r => r.t - 0.16), land: REL.map(r => r.t + p.flight), speeds: REL.map(r => Math.round(r.speed)),
    strong: REL.map(r => r.strong), words: p.words.map(w => w.text) };
}

/* ------------------------------------------------------------------ tags */
const CACHE = {};
function tagSprite(w, tk) {
  const key = w.text + w.style;
  if (CACHE[key]) return CACHE[key];
  const S = 2, pad = 16;
  const font = w.style === 'mag' ? tokFont(tk, 'serif', 52, 900) : w.style === 'film' ? tokFont(tk, 'serif', 46, 700) : tokFont(tk, 'sans', 46, w.style === 'collage' ? 900 : 700);
  const tw = layoutChars(w.text, font).width;
  const W = Math.round(tw + pad * 2), H = w.style === 'film' ? 116 : 96;
  const c = mkCanvas((W + 20) * S, (H + 20) * S), x = c.getContext('2d');
  x.scale(S, S); x.translate(10, 10);
  const ib = inkBox(w.text, font), base = H / 2 - (ib.t + ib.b) / 2;
  x.font = font; x.textBaseline = 'alphabetic'; x.textAlign = 'center';
  if (w.style === 'collage') {                  // kraft scrap with torn edges + a strip of tape
    x.beginPath();
    for (let i = 0; i <= 20; i++) x.lineTo((W * i) / 20, 3 * hash2(1, i));
    for (let i = 0; i <= 8; i++) x.lineTo(W - 3 * hash2(2, i), (H * i) / 8);
    for (let i = 20; i >= 0; i--) x.lineTo((W * i) / 20, H - 3 * hash2(3, i));
    for (let i = 8; i >= 0; i--) x.lineTo(3 * hash2(4, i), (H * i) / 8);
    x.closePath(); x.fillStyle = '#C9A67A'; x.fill();
    x.fillStyle = 'rgba(90,60,30,0.12)'; for (let i = 0; i < 40; i++) x.fillRect(hash2(5, i) * W, hash2(6, i) * H, 2, 2);
    x.fillStyle = '#1B1712'; x.fillText(w.text, W / 2, base);
    x.fillStyle = 'rgba(245,240,225,0.6)'; x.save(); x.translate(W / 2, 0); x.rotate(-0.08); x.fillRect(-34, -10, 68, 22); x.restore();
  } else if (w.style === 'film') {              // a frame of film: black base, sprocket holes, warm type
    rrect(x, 0, 0, W, H, 6); x.fillStyle = '#141210'; x.fill();
    x.fillStyle = '#EDE3CF';
    for (let i = 8; i < W - 10; i += 22) { rrect(x, i, 6, 12, 9, 2); x.fill(); rrect(x, i, H - 15, 12, 9, 2); x.fill(); }
    x.fillStyle = '#F2C879'; x.fillText(w.text, W / 2, base + 2);
  } else if (w.style === 'mag') {               // masthead: white stock, red serif, black rules
    x.fillStyle = '#FBF8F2'; x.fillRect(0, 0, W, H);
    x.fillStyle = '#111'; x.fillRect(10, 8, W - 20, 3); x.fillRect(10, H - 11, W - 20, 3);
    x.fillStyle = '#D5261E'; x.fillText(w.text, W / 2, base + 2);
  } else {                                      // keynote: dark glass slide, white sans, a thin light line
    rrect(x, 0, 0, W, H, 14);
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, '#20263A'); g.addColorStop(1, '#0B0E18');
    x.fillStyle = g; x.fill(); x.strokeStyle = 'rgba(160,190,255,0.5)'; x.lineWidth = 1.5; x.stroke();
    x.fillStyle = '#FFFFFF'; x.fillText(w.text, W / 2, base);
    x.fillStyle = 'rgba(140,180,255,0.9)'; x.fillRect(W / 2 - 20, H - 16, 40, 3);
  }
  CACHE[key] = { c, W: W + 20, H: H + 20 };
  return CACHE[key];
}

function handAt(t) {                               // sub-frame interpolated knuckle position
  const n = TRACK.pos.length, f = clamp(t * 30, 0, n - 1), i = Math.min(n - 2, Math.floor(f)), u = f - i;
  return [lerp(TRACK.pos[i][0], TRACK.pos[i + 1][0], u), lerp(TRACK.pos[i][1], TRACK.pos[i + 1][1], u)];
}
function qbez(a, c, b, u) { const v = 1 - u; return [v * v * a[0] + 2 * v * u * c[0] + u * u * b[0], v * v * a[1] + 2 * v * u * c[1] + u * u * b[1]]; }

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  if (!REL) return 1;
  for (const r of REL) if (t > r.t - 0.2 && t < r.t + p.flight + 0.15) return 10;
  return 1;
}

export function draw(ctx, t, p, tk, env) {
  const fr = frameAt(t, env.fps);
  if (fr) ctx.drawImage(fr.plate, 0, 0); else { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, env.W, env.H); }
  if (!REL) return;
  const glow = env.glow;
  p.words.forEach((w, k) => {
    const r = REL[k], slot = p.slots[k], sp = tagSprite(w, tk);
    const tA = r.t - 0.16, tR = r.t, tL = r.t + p.flight;
    if (t < tA) return;
    let x, y, sc, rot, a = 1, shadow = 0;
    if (t < tR) {                                           // pops out of the hand and rides it
      const u = E.backOut(clamp((t - tA) / 0.16), 2.0);
      const h = handAt(t);
      x = Math.min(h[0] + 10, 1000); y = Math.min(h[1] - 70, 1370); sc = lerp(0.35, 0.86, u); rot = -0.1; a = clamp((t - tA) / 0.05);   // above the caption band
    } else if (t < tL) {                                     // thrown: leaves along the hand's velocity, arcs to its slot
      const u = (t - tR) / (tL - tR), e = E.cubicOut(u);
      const P0 = [Math.min(r.pos[0] + 10, 1000), Math.min(r.pos[1] - 70, 1370)], P2 = [slot[0], slot[1]];
      // up the right-hand side (never across the face): control point beside the start, leaning with the hand
      const vv = Math.hypot(r.v[0], r.v[1]) || 1;
      const C = [Math.max(P0[0], P2[0]) + 40 + 30 * Math.max(0, r.v[0] / vv), lerp(P0[1], P2[1], 0.55)];
      [x, y] = qbez(P0, C, P2, e);
      sc = lerp(0.86, 1.0, E.cubicOut(u)); rot = lerp(-0.1, slot[2] * Math.PI / 180, e) + Math.sin(Math.PI * u) * 0.35 * (k % 2 ? -1 : 1);
    } else {                                                 // stuck on the wall: small slap + settle
      const s = t - tL;
      sc = 1 + springKick(s, 5, 0.4) * 0.08; rot = slot[2] * Math.PI / 180 + springKick(s, 6, 0.5) * 0.05;
      x = slot[0]; y = slot[1]; shadow = clamp(s / 0.12);
    }
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.scale(sc, sc); ctx.globalAlpha = a;
    // contact shadow on the wall once stuck, soft drop shadow in the air
    ctx.save(); ctx.filter = `blur(${lerp(14, 5, shadow).toFixed(1)}px)`; ctx.fillStyle = `rgba(40,30,20,${lerp(0.22, 0.32, shadow).toFixed(3)})`;
    ctx.fillRect(-sp.W / 2 + 10 + lerp(18, 6, shadow), -sp.H / 2 + 10 + lerp(26, 8, shadow), sp.W - 20, sp.H - 20); ctx.restore();
    ctx.drawImage(sp.c, -sp.W / 2, -sp.H / 2, sp.W, sp.H);
    ctx.restore(); ctx.globalAlpha = 1;
    // release burst at the hand
    const s2 = t - tR;
    if (s2 >= 0 && s2 < 0.35) {
      for (let i = 0; i < 12; i++) {
        const an = -Math.PI / 2 + (hash2(k, i) - 0.5) * 2.2, d = (40 + 160 * hash2(k + 9, i)) * E.cubicOut(s2 / 0.35);
        const px = r.pos[0] + 10 + Math.cos(an) * d, py = r.pos[1] - 60 + Math.sin(an) * d;
        drawSprite(ctx, softDot('rb', '#FFFFFF'), px, py, 3, 0.8 * (1 - s2 / 0.35));
        if (glow) drawSprite(glow, softDot('rbg', '#FFE2A8'), px, py, 12, 0.8 * (1 - s2 / 0.35));
      }
    }
  });
}

export function bbox(t, p, tk, env) {
  return (p.slots || []).map(([x, y], k) => ({ kind: 'card', label: p.words[k].text, x: x - 100, y: y - 50, w: 200, h: 100, font_px: 46 }));
}
