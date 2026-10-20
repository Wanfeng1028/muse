/* ==========================================================================
   chapter_tag — chapter label with a HUD progress bar.
   Segmented progress track (one segment per chapter; earlier chapters dim-
   filled, the current one fills over the shot), chapter number (mono, accent)
   + Chinese title + tracked English label, revealed by a left-to-right wipe
   with a scan line; glowing progress head; wipes away to the right on exit.
   Supports the invert layer (storyboard `invert: true`): everything is drawn in plain white,
   hierarchy by alpha (INV_ALPHA), no glow; the compositor difference-blends that pass so the tag
   reads dark on light footage and light on dark footage (dead zone: mid-grey, see
   references/director.md). Normal passes are unchanged.

   Ported from 《在我开口之前》 ui.js drawHUDCold / drawChapterLabel / drawUIGlow
   (the 7 hard-coded chapters, x=72, y=176/236, 936 px width became params).
   ========================================================================== */
import { E, clamp, seg, lerp, rgba, tokColor, tokFont, softDot, drawSprite } from '../engine/core.js';
import { textW, stringInk } from '../engine/text.js';

export const id = 'chapter_tag';
export const role = 'hud';
export const desc = '章节标签 + HUD 分段进度条：编号（等宽强调色）+ 中文标题 + 英文小标，左到右擦入带扫描线，进度头辉光，退场向右擦出。支持 invert: true（反相混合图层：纯白墨、无辉光，亮底变暗、暗底保持亮）。';
export const sfx_hints = [{ id: 'tick', at: 'start' }];
export const invert = true;   // may sit on the difference-blended 'invert' layer

// invert pass: white ink only, the token role decides the alpha (difference with white = inverse of the footage)
const INV_ALPHA = { '@accent': 1, '@text': 1, '@text_dim': 0.6, '@hair': 0.3 };
function ink(ctx, tk, env, color) {
  if (env.invert) { ctx.fillStyle = '#FFFFFF'; return INV_ALPHA[color] ?? 1; }
  ctx.fillStyle = tokColor(tk, color);
  return 1;
}

export const params = {
  n: { default: '01', type: 'string', desc: '章节编号（可为空字符串）。' },
  zh: { default: '', type: 'string', desc: '中文章节名。' },
  en: { default: '', type: 'string', desc: '英文小标（自动大写、加字距）。' },
  index: { default: 0, type: 'integer', min: 0, desc: '当前章节序号（0 起），决定进度条哪一段在走。' },
  count: { default: 5, type: 'integer', min: 1, max: 12, desc: '章节总数（进度条段数）。' },
  progress: { default: 'auto', type: 'any', desc: "当前段进度：'auto'（随镜头时长走满）| 0..1 常数 | [起, 止]（镜头内从起到止）。" },
  right: { default: '', type: 'string', desc: '右侧等宽小字（如 STEP 1/5），空则不画。' },
  x: { default: 0.0667, type: 'number', min: 0, max: 1, desc: '左边缘（画布宽比例）。' },
  y: { default: 0.085, type: 'number', min: 0, max: 1, desc: '进度条的垂直位置（画布高比例）；标签基线在其下方 60px。' },
  width: { default: 0.8667, type: 'number', min: 0.2, max: 1, desc: '总宽（画布宽比例）。' },
  label_gap: { default: 60, type: 'number', desc: '进度条到标签基线的距离 px。' },
  wipe_dur: { default: 0.42, type: 'number', desc: '擦入时长。' },
  out_dur: { default: 0.32, type: 'number', desc: '擦出时长。' },
  glow: { default: 0.55, type: 'number', min: 0, max: 2, desc: '进度头辉光强度。' },
};

function progressAt(t, p, env, wipeDur, tOut) {
  const pr = p.progress;
  if (typeof pr === 'number') return clamp(pr);
  if (Array.isArray(pr)) return lerp(pr[0], pr[1], E.sineInOut(seg(t, wipeDur * 0.5, tOut)));
  return clamp((t - wipeDur * 0.5) / Math.max(0.1, tOut - wipeDur * 0.5));
}

function layout(t, p, tk, env) {
  const s = env.s, T = tk.type || {};
  const x0 = p.x * env.W, width = p.width * env.W, barY = p.y * env.H;
  const gap = 8 * s, count = Math.max(1, p.count | 0);
  const segW = (width - (count - 1) * gap) / count;
  const base = barY + p.label_gap * s;
  const tOut = Math.max(p.wipe_dur, env.dur - p.out_dur);
  const wIn = E.expoOut(seg(t, 0, p.wipe_dur));
  const wOut = E.expoInOut(seg(t, tOut, tOut + p.out_dur));
  const clipL = lerp(x0 - 24 * s, x0 + width + 24 * s, wOut);   // exit: left edge sweeps right
  const clipR = lerp(x0 - 24 * s, x0 + width + 24 * s, wIn);    // entry: right edge sweeps right
  const tn = T.chapter_num || { font: 'mono', weight: 500, size: 26 };
  const tz = T.chapter_zh || { font: 'sans', weight: 500, size: 32 };
  const te = T.chapter_en || { font: 'latin', weight: 600, size: 19, tracking_em: 0.22 };
  const fN = tokFont(tk, tn.font, tn.size * s, tn.weight), fZ = tokFont(tk, tz.font, tz.size * s, tz.weight), fE = tokFont(tk, te.font, te.size * s, te.weight);
  const lsE = (te.tracking_em ?? 0.22) * te.size * s;
  const parts = [];
  let cx = x0;
  if (p.n) { parts.push({ str: p.n, font: fN, x: cx, color: '@accent', ls: 0, size: tn.size * s }); cx += textW(p.n, fN) + 16 * s; }
  if (p.zh) { parts.push({ str: p.zh, font: fZ, x: cx, color: '@text', ls: 0, size: tz.size * s }); cx += textW(p.zh, fZ) + 14 * s; }
  if (p.en) { const en = p.en.toUpperCase(); parts.push({ str: en, font: fE, x: cx, color: '@text_dim', ls: lsE, size: te.size * s }); }
  let right = null;
  if (p.right) { const tr = T.label || { font: 'mono', weight: 400, size: 22 }; const fR = tokFont(tk, tr.font, tr.size * s, tr.weight); right = { str: p.right, font: fR, x: x0 + width - textW(p.right, fR), size: tr.size * s }; }
  const prog = progressAt(t, p, env, p.wipe_dur, tOut);
  const idx = Math.min(count - 1, Math.max(0, p.index | 0));
  const headX = x0 + idx * (segW + gap) + segW * prog;
  return { s, x0, width, barY, gap, count, segW, base, tOut, wIn, wOut, clipL, clipR, parts, right, prog, idx, headX };
}

export function draw(ctx, t, p, tk, env) {
  const G = layout(t, p, tk, env);
  const s = G.s;
  if (G.clipR <= G.clipL) return;
  const glow = env.invert ? null : env.glow;   // additive glow would only grey out a difference-blended layer
  ctx.save();
  ctx.beginPath(); ctx.rect(G.clipL, G.barY - 40 * s, G.clipR - G.clipL, G.base - G.barY + 80 * s); ctx.clip();
  // progress track
  for (let i = 0; i < G.count; i++) {
    const x = G.x0 + i * (G.segW + G.gap);
    ctx.globalAlpha = ink(ctx, tk, env, '@hair'); ctx.fillRect(x, G.barY, G.segW, 3 * s); ctx.globalAlpha = 1;
    let f = 0, a = 1;
    if (i < G.idx) { f = 1; a = 0.6; } else if (i === G.idx) f = G.prog;
    if (f > 0) { ctx.globalAlpha = a * ink(ctx, tk, env, '@accent'); ctx.fillRect(x, G.barY, G.segW * f, 3 * s); ctx.globalAlpha = 1; }
  }
  // label
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  for (const q of G.parts) {
    ctx.font = q.font; ctx.globalAlpha = ink(ctx, tk, env, q.color); ctx.letterSpacing = q.ls ? q.ls.toFixed(2) + 'px' : '0px';
    ctx.fillText(q.str, q.x, G.base);
  }
  ctx.letterSpacing = '0px';
  if (G.right) { ctx.font = G.right.font; ctx.globalAlpha = ink(ctx, tk, env, '@text_dim'); ctx.fillText(G.right.str, G.right.x, G.base); }
  ctx.globalAlpha = 1;
  ctx.restore();
  // scan line at the moving wipe edge (entry and exit)
  const edge = (x, a) => { if (a <= 0.01) return; ctx.globalAlpha = a * ink(ctx, tk, env, '@accent'); ctx.fillRect(x - 1 * s, G.barY - 22 * s, 2 * s, G.base - G.barY + 44 * s); ctx.globalAlpha = 1;
    if (glow) { glow.globalAlpha = a * 0.8; glow.fillStyle = tokColor(tk, '@accent'); glow.fillRect(x - 3 * s, G.barY - 22 * s, 6 * s, G.base - G.barY + 44 * s); glow.globalAlpha = 1; } };
  if (G.wIn > 0 && G.wIn < 0.999) edge(G.clipR, (1 - G.wIn) * 0.9 + 0.1);
  if (G.wOut > 0.001 && G.wOut < 1) edge(G.clipL, 0.9 * (1 - G.wOut) + 0.1);
  // glowing progress head
  if (glow && p.glow > 0 && G.headX > G.clipL && G.headX < G.clipR) {
    drawSprite(glow, softDot('ui', tokColor(tk, '@accent')), G.headX, G.barY + 1.5 * s, 16 * s, p.glow * G.wIn * (1 - G.wOut));
  }
}

export function bbox(t, p, tk, env) {
  const G = layout(t, p, tk, env);
  if (G.clipR <= G.clipL) return [];
  const clipBox = (b) => {
    if (!b) return null;
    const l = Math.max(b.x, G.clipL), r = Math.min(b.x + b.w, G.clipR);
    return r > l ? { ...b, x: l, w: r - l } : null;
  };
  const out = [];
  const bar = clipBox({ x: G.x0, y: G.barY - 2 * G.s, w: G.width, h: 7 * G.s });
  if (bar) out.push({ kind: 'shape', label: 'progress', ...bar });
  let lab = null, fpx = 99;
  for (const q of G.parts) {
    const ib = stringInk(q.str, q.font, q.x, G.base, q.ls);
    if (!ib) continue;
    fpx = Math.min(fpx, q.size);
    lab = lab ? { x: Math.min(lab.x, ib.x), y: Math.min(lab.y, ib.y), w: Math.max(lab.x + lab.w, ib.x + ib.w) - Math.min(lab.x, ib.x), h: Math.max(lab.y + lab.h, ib.y + ib.h) - Math.min(lab.y, ib.y) } : ib;
  }
  const lb = clipBox(lab);
  if (lb) out.push({ kind: 'text', label: [p.n, p.zh, p.en].filter(Boolean).join(' '), ...lb, font_px: Math.round(fpx) });
  if (G.right) { const rb = clipBox(stringInk(G.right.str, G.right.font, G.right.x, G.base, 0)); if (rb) out.push({ kind: 'text', label: p.right, ...rb, font_px: Math.round(G.right.size) }); }
  return out;
}

export function mbSamples() { return 1; }

export default { id, role, desc, params, sfx_hints, invert, draw, bbox, mbSamples };
