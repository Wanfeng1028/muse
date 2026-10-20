/* ==========================================================================
   flow_nodes — 连线工作流卡
   Nodes of a small workflow light up one after another; links draw between
   them; packets of light stream along the links, stage by stage, and pour
   into the result node, whose ring charges up and completes with a burst.

   Look: the cold light of 《在我开口之前》 — near-black blue, ice cyan and
   violet, hairline HUD, dark glass node chips with a hairline stroke, glow
   carried by the bloom pass. Links are cubic Béziers; packets are drawn as
   short streaks along the path tangent (plus real sub-frame motion blur).
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, spring, springKick, hash2, rgba, rrect, tokFont, mkCanvas, softDot, drawSprite, Noise } from '../engine/core.js';
import { layoutChars } from '../engine/text.js';
import { dust } from '../engine/particles.js';

export const id = 'flow_nodes';
export const role = 'card';
export const desc = '连线工作流卡：节点依次亮起，节点间连线，数据光点沿线逐级流动，最后汇入结果节点，结果节点充能完成并爆发。冷光风格。全屏不透明。';

export const params = {
  nodes: {
    default: [
      { id: 'a', label: '口播素材', icon: 'film', x: 0.27, y: 0.21 },
      { id: 'b', label: '文案', icon: 'text', x: 0.73, y: 0.21 },
      { id: 'c', label: '分镜', icon: 'grid', x: 0.5, y: 0.37 },
      { id: 'd', label: '动效', icon: 'spark', x: 0.27, y: 0.53 },
      { id: 'e', label: '音效', icon: 'wave', x: 0.73, y: 0.53 },
      { id: 'f', label: '成片', icon: 'play', x: 0.5, y: 0.69, result: true, sub: '1080×1920 · 00:58' },
    ], type: 'any', desc: '节点：id、label、icon（film/text/grid/spark/wave/play）、位置（画面比例）；result=true 为结果节点。',
  },
  links: { default: [['a', 'c'], ['b', 'c'], ['c', 'd'], ['c', 'e'], ['d', 'f'], ['e', 'f']], type: 'any', desc: '连线 [from, to]，按层级依次出现。' },
  title: { default: 'WORKFLOW', type: 'string', desc: '顶部小标签。' },
  cyan: { default: '#6EE7F5', type: 'color', desc: '冰青。' },
  violet: { default: '#8E7DFF', type: 'color', desc: '紫。' },
};

/* ------------------------------------------------------------------ graph + timing */
function levels(p) {
  const lv = {};
  const ids = p.nodes.map(n => n.id);
  ids.forEach(i => { lv[i] = 0; });
  for (let k = 0; k < ids.length; k++) for (const [a, b] of p.links) lv[b] = Math.max(lv[b], lv[a] + 1);
  return lv;
}
export function timing(p) {
  const lv = levels(p), maxL = Math.max(...Object.values(lv));
  const node = {}, link = [];
  let order = 0;
  for (let L = 0; L <= maxL; L++) {
    const ns = p.nodes.filter(n => lv[n.id] === L);
    ns.forEach((n, j) => { node[n.id] = 0.2 + L * 0.46 + j * 0.13; order++; });
  }
  p.links.forEach(([a, b]) => { link.push({ a, b, t0: node[b] - 0.24, t1: node[b] - 0.02 }); });
  const flow0 = node[p.nodes.find(n => n.result).id] + 0.15;
  const stage = 0.42;                                  // packets take one stage per level
  const done = flow0 + stage * maxL + 0.35;
  return { node, link, lv, maxL, flow0, stage, done, blips: Object.values(node).sort((x, y) => x - y) };
}

/* ------------------------------------------------------------------ geometry */
function nodeGeo(n, env) {
  const w = (n.result ? 420 : 304) * env.s, h = (n.result ? 166 : 120) * env.s;
  return { x: n.x * env.W, y: n.y * env.H, w, h };
}
function bez(a, b) {                     // vertical S-curve from the bottom of a to the top of b
  const p0 = [a.x, a.y + a.h / 2], p3 = [b.x, b.y - b.h / 2], dy = (p3[1] - p0[1]) * 0.55;
  return [p0, [p0[0], p0[1] + dy], [p3[0], p3[1] - dy], p3];
}
function bpt(B, u) {
  const v = 1 - u;
  return [v * v * v * B[0][0] + 3 * v * v * u * B[1][0] + 3 * v * u * u * B[2][0] + u * u * u * B[3][0],
    v * v * v * B[0][1] + 3 * v * v * u * B[1][1] + 3 * v * u * u * B[2][1] + u * u * u * B[3][1]];
}
function drawPartial(ctx, B, u0, u1, steps = 40) {
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) { const q = bpt(B, lerp(u0, u1, i / steps)); if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }
  ctx.stroke();
}

/* ------------------------------------------------------------------ icons (vector, stroke) */
function icon(ctx, kind, x, y, r, col) {
  ctx.save(); ctx.translate(x, y); ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  if (kind === 'film') { rrect(ctx, -r, -r * 0.72, 2 * r, 1.44 * r, 4); ctx.stroke(); for (let i = -2; i <= 2; i++) { ctx.fillRect(i * r * 0.4 - 2, -r * 0.62, 4, 4); ctx.fillRect(i * r * 0.4 - 2, r * 0.5, 4, 4); } ctx.beginPath(); ctx.moveTo(-r * 0.2, -r * 0.3); ctx.lineTo(r * 0.3, 0); ctx.lineTo(-r * 0.2, r * 0.3); ctx.closePath(); ctx.fill(); }
  else if (kind === 'text') { for (let i = 0; i < 4; i++) { ctx.beginPath(); ctx.moveTo(-r, -r * 0.6 + i * r * 0.4); ctx.lineTo(i === 3 ? r * 0.2 : r, -r * 0.6 + i * r * 0.4); ctx.stroke(); } }
  else if (kind === 'grid') { for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) { rrect(ctx, -r + i * r * 1.08, -r * 0.8 + j * r * 0.86, r * 0.9, r * 0.72, 3); ctx.stroke(); } }
  else if (kind === 'spark') { for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2; ctx.beginPath(); ctx.moveTo(Math.cos(a) * r * 0.25, Math.sin(a) * r * 0.25); ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); ctx.stroke(); } ctx.beginPath(); ctx.arc(0, 0, r * 0.14, 0, TAU); ctx.fill(); }
  else if (kind === 'wave') { ctx.beginPath(); for (let i = 0; i <= 24; i++) { const xx = -r + (2 * r * i) / 24, yy = Math.sin(i * 0.9) * r * 0.6 * Math.sin(Math.PI * i / 24); if (i) ctx.lineTo(xx, yy); else ctx.moveTo(xx, yy); } ctx.stroke(); }
  else if (kind === 'play') { ctx.beginPath(); ctx.moveTo(-r * 0.45, -r * 0.62); ctx.lineTo(r * 0.7, 0); ctx.lineTo(-r * 0.45, r * 0.62); ctx.closePath(); ctx.fill(); }
  ctx.restore();
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  const T = timing(p);
  if (t > T.flow0 - 0.1 && t < T.done + 0.3) return 8;
  return 5;
}
export function post(t, p) {
  const T = timing(p), s = t - T.done;
  return { fade: smooth(seg(t, 0, 0.25)), flash: s >= 0 && s < 0.25 ? 0.18 * Math.exp(-s / 0.06) : 0, flashTint: [0.85, 0.97, 1] };
}

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, glow = env.glow, T = timing(p);
  const geo = {}; p.nodes.forEach(n => { geo[n.id] = nodeGeo(n, env); });
  // ground: near-black blue, a faint glow where the result will be, hairline dot grid
  ctx.fillStyle = '#05070C'; ctx.fillRect(0, 0, W, H);
  const res = p.nodes.find(n => n.result), rg0 = geo[res.id];
  const charge = seg(t, T.flow0 + T.stage * (T.maxL - 1), T.done), burst = t >= T.done ? Math.exp(-(t - T.done) / 0.6) : 0;
  const bg = ctx.createRadialGradient(W / 2, H * 0.52, 20, W / 2, H * 0.52, H * 0.62);
  bg.addColorStop(0, '#0E1628'); bg.addColorStop(1, '#05070C');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  const rg = ctx.createRadialGradient(rg0.x, rg0.y, 10, rg0.x, rg0.y, 520);
  rg.addColorStop(0, rgba(p.violet, 0.10 + 0.25 * charge + 0.3 * burst)); rg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
  for (let gy = 60; gy < H; gy += 60) for (let gx = 30; gx < W; gx += 60) { ctx.fillStyle = 'rgba(120,150,190,0.07)'; ctx.fillRect(gx, gy, 2, 2); }
  // slow drift / parallax
  const dx = Noise.n1(t * 0.25, 2) * 8, dy = Noise.n1(t * 0.25, 5) * 8 - 10 * E.sineInOut(seg(t, 0, env.dur));
  ctx.save(); ctx.translate(dx, dy);
  if (glow) { glow.save(); glow.translate(dx, dy); }
  // links
  for (const L of T.link) {
    const B = bez(geo[L.a], geo[L.b]);
    const u = E.cubicInOut(seg(t, L.t0, L.t1));
    if (u <= 0) continue;
    ctx.strokeStyle = rgba(p.cyan, 0.28); ctx.lineWidth = 2; drawPartial(ctx, B, 0, u);
    ctx.strokeStyle = rgba('#CFF6FF', 0.9); ctx.lineWidth = 2.5;
    if (u < 1) { drawPartial(ctx, B, Math.max(0, u - 0.08), u, 8); const q = bpt(B, u); drawSprite(ctx, softDot('tip', '#E6FBFF'), q[0], q[1], 10, 1); if (glow) drawSprite(glow, softDot('tipg', p.cyan), q[0], q[1], 30, 0.9); }
    if (glow) { glow.strokeStyle = rgba(p.cyan, 0.35); glow.lineWidth = 5; drawPartial(glow, B, 0, u, 24); }
  }
  // packets: each link carries a stream during its stage (level of its source node)
  for (const L of T.link) {
    const B = bez(geo[L.a], geo[L.b]);
    const st = T.flow0 + T.lv[L.a] * T.stage;
    for (let k = 0; k < 7; k++) {
      const t0 = st + k * 0.055 + 0.02 * hash2(k, L.a.charCodeAt(0));
      const u = (t - t0) / (T.stage * 0.95);
      if (u <= 0 || u >= 1) continue;
      const e = E.sineInOut(u);
      const q = bpt(B, e), q2 = bpt(B, Math.max(0, e - 0.06));
      ctx.strokeStyle = rgba('#E6FBFF', 0.9); ctx.lineWidth = 3; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(q2[0], q2[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); ctx.lineCap = 'butt';
      drawSprite(ctx, softDot('pk', '#FFFFFF'), q[0], q[1], 7, 1);
      if (glow) drawSprite(glow, softDot('pkg', k % 3 ? p.cyan : p.violet), q[0], q[1], 26, 0.9);
    }
  }
  // nodes
  for (const n of p.nodes) {
    const g = geo[n.id], tn = T.node[n.id];
    const a = E.expoOut(seg(t, tn, tn + 0.35));
    if (a <= 0.001) continue;
    const pop = springKick(t - tn, 4, 0.45) * 0.06;
    // incoming packets make a node pulse (arrival of its stage)
    const arr = T.flow0 + (T.lv[n.id] - 1) * T.stage + T.stage * 0.95;
    const pulse = T.lv[n.id] > 0 && t > arr ? Math.exp(-(t - arr) / 0.25) : 0;
    const sc = 0.9 + 0.1 * a + pop + 0.04 * pulse;
    ctx.save(); ctx.translate(g.x, g.y); ctx.scale(sc, sc); ctx.globalAlpha = a;
    ctx.filter = a < 0.98 ? `blur(${(6 * (1 - a)).toFixed(2)}px)` : 'none';
    const done = n.result && t >= T.done;
    rrect(ctx, -g.w / 2, -g.h / 2, g.w, g.h, 18 * env.s);
    const fill = ctx.createLinearGradient(0, -g.h / 2, 0, g.h / 2);
    fill.addColorStop(0, n.result ? '#141B33' : '#0E1524'); fill.addColorStop(1, '#090D17');
    ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = n.result ? rgba(done ? '#E6FBFF' : p.violet, 0.55 + 0.45 * (charge + burst)) : rgba(p.cyan, 0.45 + 0.5 * pulse); ctx.lineWidth = 1.8; ctx.stroke();
    ctx.filter = 'none';
    // icon + label
    const ic = n.result ? 28 : 22;
    icon(ctx, n.icon, -g.w / 2 + (n.result ? 62 : 50) * env.s, 0, ic * env.s, n.result ? (done ? '#E6FBFF' : rgba(p.violet, 0.9)) : rgba(p.cyan, 0.95));
    ctx.font = tokFont(tk, 'sans', (n.result ? 52 : 40) * env.s, n.result ? 700 : 500); ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
    ctx.fillStyle = n.result && !done ? rgba('#ECE9E2', 0.6 + 0.4 * charge) : '#ECE9E2';
    ctx.fillText(n.label, -g.w / 2 + (n.result ? 112 : 92) * env.s, n.sub ? -14 * env.s : 2 * env.s);
    if (n.sub) { ctx.font = tokFont(tk, 'sans', 24 * env.s, 500); ctx.fillStyle = rgba('#7C8698', 1); ctx.fillText(n.sub, -g.w / 2 + 114 * env.s, 38 * env.s); }
    // index tag
    const idx = String(p.nodes.indexOf(n) + 1).padStart(2, '0');
    ctx.font = tokFont(tk, 'sans', 17 * env.s, 500); ctx.fillStyle = rgba(p.cyan, 0.7); ctx.textBaseline = 'alphabetic';
    ctx.fillText(idx, -g.w / 2 + 14 * env.s, -g.h / 2 - 10 * env.s);
    ctx.restore(); ctx.globalAlpha = 1;
    if (glow) { glow.save(); glow.globalAlpha = a * (0.25 + 0.6 * pulse + (n.result ? 0.6 * charge + 0.9 * burst : 0)); rrect(glow, g.x - g.w / 2, g.y - g.h / 2, g.w, g.h, 18); glow.strokeStyle = n.result ? p.violet : p.cyan; glow.lineWidth = 6; glow.stroke(); glow.restore(); }
    // result: charging ring, then a burst
    if (n.result) {
      const R = g.w * 0.62;
      if (charge > 0) {
        ctx.strokeStyle = rgba(p.violet, 0.25); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(g.x, g.y, R, 0, TAU); ctx.stroke();
        ctx.strokeStyle = rgba('#E6FBFF', 0.9); ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(g.x, g.y, R, -Math.PI / 2, -Math.PI / 2 + TAU * E.cubicInOut(charge)); ctx.stroke();
        if (glow) { glow.strokeStyle = rgba(p.cyan, 0.7); glow.lineWidth = 8; glow.beginPath(); glow.arc(g.x, g.y, R, -Math.PI / 2, -Math.PI / 2 + TAU * E.cubicInOut(charge)); glow.stroke(); }
      }
      const s2 = t - T.done;
      if (s2 >= 0 && s2 < 1.0) {
        const r2 = R + 520 * E.expoOut(s2 / 1.0);
        ctx.strokeStyle = rgba('#CFF6FF', 0.6 * (1 - s2)); ctx.lineWidth = 3 * (1 - s2) + 1; ctx.beginPath(); ctx.arc(g.x, g.y, r2, 0, TAU); ctx.stroke();
        for (let i = 0; i < 24; i++) {
          const a2 = (i / 24) * TAU + 0.13, rr = R + (80 + 260 * hash2(9, i)) * E.expoOut(s2 / 0.8);
          drawSprite(ctx, softDot('bp', '#E6FBFF'), g.x + Math.cos(a2) * rr, g.y + Math.sin(a2) * rr, 4, (1 - s2) * 0.9);
          if (glow) drawSprite(glow, softDot('bpg', i % 2 ? p.cyan : p.violet), g.x + Math.cos(a2) * rr, g.y + Math.sin(a2) * rr, 16, (1 - s2) * 0.8);
        }
      }
    }
  }
  ctx.restore(); if (glow) glow.restore();
  // HUD
  const ha = smooth(seg(t, 0.1, 0.6));
  ctx.font = tokFont(tk, 'sans', 20, 500); ctx.letterSpacing = '6px'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = rgba('#7C8698', 0.9 * ha); ctx.fillText(p.title, 108, 262);                // below the top band (12 % H)
  ctx.fillStyle = rgba('#1B2230', ha); ctx.fillRect(108, 278, W - 216, 1);
  const prog = clamp((t - 0.2) / (T.done - 0.2));
  ctx.fillStyle = rgba(p.cyan, 0.8 * ha); ctx.fillRect(108, 278, (W - 216) * prog, 1.5);
  ctx.textAlign = 'right'; ctx.fillStyle = rgba('#7C8698', 0.8 * ha);
  const on = p.nodes.filter(n => t >= T.node[n.id]).length;
  ctx.fillText(`${String(on).padStart(2, '0')} / ${String(p.nodes.length).padStart(2, '0')}`, W - 108, 262);
  ctx.letterSpacing = '0px'; ctx.textAlign = 'left';
  dust(ctx, glow, t, { x: 0, y: 0, w: W, h: H, count: 40, seed: 9, color: '#CFF6FF', glowColor: p.cyan, r: [0.6, 1.8], speed: 8, alpha: 0.35, fadeIn: ha });
}

export function bbox(t, p, tk, env) {
  return p.nodes.map(n => { const g = nodeGeo(n, env); return { kind: 'card', label: n.label, x: g.x - g.w / 2, y: g.y - g.h / 2, w: g.w, h: g.h, font_px: 36 }; });
}
