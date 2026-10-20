/* ==========================================================================
   kinetic_keyword — a keyword that focuses in character by character
   (rise + un-blur + fade, staggered), with an optional highlight backing
   (plate / bar / underline) that grows in behind it, and a glow on the
   accent characters. Exits with a short cubic-in blur-out.

   Ported from 《在我开口之前》 ui.js drawFocusText + the S0 copy lines
   (hard-coded x/y/tIn/colour became params; colours/fonts come from tokens).
   ========================================================================== */
import { E, clamp, seg, rgba, rrect, tokColor, tokFont, softDot, drawSprite } from '../engine/core.js';
import { layoutChars, cjkMid, focusText, focusInk, stringInk } from '../engine/text.js';

export const id = 'kinetic_keyword';
export const role = 'overlay';
export const desc = '关键词逐字聚焦入场（上浮+去模糊+淡入，逐字错峰），可选高亮底（plate/bar/underline），强调字带辉光；结尾短促模糊淡出。';
export const sfx_hints = [{ id: 'pop_soft', at: 'start' }];

export const params = {
  text: { default: '', type: 'string', desc: '关键词。留空时由分镜解析器取 start 词锚的 text。' },
  sub: { default: '', type: 'string', desc: '可选副行（小字，如英文/解释），在主词之后 0.12s 入场。' },
  x: { default: 0.5, type: 'number', min: 0, max: 1, desc: '水平位置（画布宽度比例），配合 align。' },
  y: { default: 0.2, type: 'number', min: 0, max: 1, desc: '主词字面中心的垂直位置（画布高度比例）。' },
  align: { default: 'center', type: 'enum', values: ['left', 'center', 'right'], desc: '水平对齐。' },
  type: { default: 'keyword', type: 'string', desc: '字形角色（tokens.type 下的键），决定字体/字重/字号。' },
  size: { default: null, type: 'number', desc: '覆盖字号（px，按 1080 宽设计，随画布宽缩放）。' },
  weight: { default: null, type: 'number', desc: '覆盖字重。' },
  tracking: { default: null, type: 'number', desc: '覆盖字距（px）。' },
  max_width: { default: 0.84, type: 'number', min: 0.2, max: 1, desc: '最大宽度（画布宽比例），超出自动缩小字号。' },
  color: { default: '@text', type: 'color', desc: '常规字颜色（token 引用 @name 或 #hex）。' },
  hi_color: { default: '@accent', type: 'color', desc: '强调字颜色。' },
  hi: { default: 'all', type: 'any', desc: "强调字范围：'all' | 'none' | [起, 止)（按字符序号）。" },
  highlight: {
    default: { mode: 'plate', color: '@panel_2', alpha: 0.78, line: '@accent', pad_x: 30, pad_y: 18, radius: 14, delay: 0.04, dur: 0.42 },
    type: 'object', desc: "高亮底：mode 'none'|'plate'（深色底板+强调色底线）|'bar'（强调色实底，字用 highlight_text 色）|'underline'。",
  },
  stagger: { default: null, type: 'number', desc: '逐字错峰秒数，缺省取 tokens.motion.stagger。' },
  dur: { default: null, type: 'number', desc: '单字聚焦时长，缺省取 tokens.motion.focus_dur。' },
  blur: { default: null, type: 'number', desc: '入场起始模糊 px。' },
  dy: { default: null, type: 'number', desc: '入场上浮距离 px。' },
  scale0: { default: 1.1, type: 'number', desc: '单字入场起始缩放。' },
  out_dur: { default: null, type: 'number', desc: '退场时长，缺省取 tokens.motion.out_dur。' },
  glow: { default: 0.55, type: 'number', min: 0, max: 2, desc: '强调字辉光强度（0 关闭）。' },
};

function isHi(p, i) {
  if (p.hi === 'all') return true;
  if (p.hi === 'none' || !p.hi) return false;
  return Array.isArray(p.hi) && i >= p.hi[0] && i < p.hi[1];
}

/* shared layout for draw() and bbox() */
function layout(t, p, tk, env) {
  const s = env.s, M = tk.motion || {};
  const ty = (tk.type && tk.type[p.type]) || { font: 'sans', weight: 600, size: 96 };
  let size = (p.size ?? ty.size) * s;
  const weight = p.weight ?? ty.weight;
  const ls = (p.tracking ?? ty.tracking ?? 0) * s;
  let font = tokFont(tk, ty.font, size, weight);
  let L = layoutChars(p.text, font, ls);
  const maxW = p.max_width * env.W;
  if (L.width > maxW) { size *= maxW / L.width; font = tokFont(tk, ty.font, size, weight); L = layoutChars(p.text, font, ls); }
  const base = p.y * env.H + cjkMid(font);
  const outDur = p.out_dur ?? M.out_dur ?? 0.26;
  const tOut = Math.max(0.3, env.dur - outDur);
  const hl = p.highlight || { mode: 'none' };
  let x0 = p.x * env.W;
  if (p.align === 'center') x0 -= L.width / 2; else if (p.align === 'right') x0 -= L.width;
  const ink = stringInk(p.text, font, x0, base, ls) || { x: x0, y: base - size, w: L.width, h: size };
  // highlight geometry (full size), grows with expoOut from the left, retracts on exit
  let plate = null;
  if (hl.mode && hl.mode !== 'none') {
    const px = (hl.pad_x ?? 28) * s, py = (hl.pad_y ?? 16) * s;
    const gIn = E.expoOut(seg(t, hl.delay ?? 0.04, (hl.delay ?? 0.04) + (hl.dur ?? 0.42)));
    const gOut = E.cubicIn(seg(t, tOut, tOut + outDur));
    const g = gIn * (1 - gOut);
    if (g > 0.002) {
      const full = { x: ink.x - px, y: ink.y - py, w: ink.w + 2 * px, h: ink.h + 2 * py };
      if (hl.mode === 'underline') { full.y = ink.y + ink.h + py * 0.55; full.h = Math.max(3, 5 * s); }
      plate = { ...full, w: full.w * g, g, full };
    }
  }
  const sub = p.sub ? (() => {
    const st = (tk.type && tk.type.label) || { font: 'mono', weight: 400, size: 24 };
    const f = tokFont(tk, st.font, st.size * s, st.weight);
    const sb = ink.y + ink.h + ((hl.pad_y ?? 16) + 30) * s + (st.size * s) * 0.8;
    const Ls = layoutChars(p.sub, f, (st.tracking ?? 0) * s);
    let sx = p.x * env.W; if (p.align === 'center') sx -= Ls.width / 2; else if (p.align === 'right') sx -= Ls.width;
    return { font: f, x: sx, base: sb, ls: (st.tracking ?? 0) * s, size: st.size * s };
  })() : null;
  return { s, size, font, ls, L, x0, base, ink, tOut, outDur, plate, hl, sub, M };
}

function focusOpts(p, G, tk, color) {
  return {
    font: G.font, x: G.x0, y: G.base, align: 'left', ls: G.ls, color,
    stagger: p.stagger ?? G.M.stagger ?? 0.035, dur: p.dur ?? G.M.focus_dur ?? 0.42,
    dy: (p.dy ?? G.M.focus_dy ?? 18) * G.s, blur: (p.blur ?? G.M.focus_blur ?? 10) * G.s,
    tIn: 0, tOut: G.tOut, outDur: G.outDur, scale0: p.scale0,
    easeIn: G.M.ease_in || 'expoOut', easeOut: G.M.ease_out || 'cubicIn',
  };
}

export function draw(ctx, t, p, tk, env) {
  if (!p.text) return;
  const G = layout(t, p, tk, env);
  const hl = G.hl;
  const cText = tokColor(tk, p.color), cHi = tokColor(tk, p.hi_color);
  // backing
  if (G.plate) {
    const P = G.plate;
    if (hl.mode === 'plate') {
      ctx.save(); ctx.globalAlpha = (hl.alpha ?? 0.8) * clamp(P.g * 1.4);
      rrect(ctx, P.x, P.y, P.w, P.h, (hl.radius ?? 14) * G.s); ctx.fillStyle = tokColor(tk, hl.color || '@panel_2'); ctx.fill();
      ctx.restore();
      const lh = Math.max(2, 4 * G.s);
      ctx.fillStyle = tokColor(tk, hl.line || '@accent');
      ctx.fillRect(P.x + (hl.radius ?? 14) * G.s * 0.6, P.y + P.h - lh, Math.max(0, P.w - (hl.radius ?? 14) * G.s * 1.2), lh);
      if (env.glow && p.glow > 0) { env.glow.fillStyle = rgba(tokColor(tk, hl.line || '@accent'), 0.8 * p.glow * P.g); env.glow.fillRect(P.x + 8 * G.s, P.y + P.h - lh * 2, Math.max(0, P.w - 16 * G.s), lh * 3); }
    } else if (hl.mode === 'bar') {
      rrect(ctx, P.x, P.y, P.w, P.h, (hl.radius ?? 10) * G.s);
      ctx.save(); ctx.globalAlpha = hl.alpha ?? 1; ctx.fillStyle = tokColor(tk, hl.color || '@highlight_bg'); ctx.fill(); ctx.restore();
    } else if (hl.mode === 'underline') {
      ctx.fillStyle = tokColor(tk, hl.line || hl.color || '@accent'); ctx.fillRect(P.x, P.y, P.w, P.h);
      if (env.glow && p.glow > 0) { env.glow.fillStyle = rgba(tokColor(tk, hl.line || '@accent'), 0.9 * p.glow); env.glow.fillRect(P.x, P.y - P.h, P.w, P.h * 3); }
    }
  }
  const onBar = hl.mode === 'bar';
  const barText = tokColor(tk, '@highlight_text');
  const col = (i) => onBar ? barText : (isHi(p, i) ? cHi : cText);
  const res = focusText(ctx, p.text, t, focusOpts(p, G, tk, col));
  // glow of the accent characters (half-res glow layer, same coordinates)
  if (env.glow && p.glow > 0 && !onBar) {
    const g = env.glow;
    g.font = G.font; g.textAlign = 'left'; g.textBaseline = 'alphabetic';
    for (const ch of res.chars) {
      if (!isHi(p, ch.i)) continue;
      g.globalAlpha = clamp(p.glow * ch.a * (0.85 + 0.15 * Math.sin(env.t * 3.1 + ch.i)));
      g.fillStyle = cHi; g.fillText(ch.c, ch.x, ch.y);
    }
    g.globalAlpha = 1;
  }
  if (G.sub) {
    focusText(ctx, p.sub, t, { font: G.sub.font, x: G.sub.x, y: G.sub.base, align: 'left', ls: G.sub.ls, color: tokColor(tk, '@text_dim'),
      stagger: 0.012, dur: 0.36, dy: 10 * G.s, blur: 6 * G.s, tIn: 0.12, tOut: G.tOut, outDur: G.outDur });
  }
}

export function bbox(t, p, tk, env) {
  if (!p.text) return [];
  const G = layout(t, p, tk, env);
  const out = [];
  const res = focusText(null, p.text, t, focusOpts(p, G, tk, '#fff'));
  const ink = focusInk(res, G.font);
  if (ink) out.push({ kind: 'text', label: p.text, ...ink, font_px: Math.round(G.size) });
  if (G.plate) out.push({ kind: 'shape', label: 'highlight:' + G.hl.mode, x: G.plate.x, y: G.plate.y, w: G.plate.w, h: G.plate.h, alpha: clamp(G.plate.g) });
  if (G.sub) {
    const r2 = focusText(null, p.sub, t, { font: G.sub.font, x: G.sub.x, y: G.sub.base, align: 'left', ls: G.sub.ls, stagger: 0.012, dur: 0.36, tIn: 0.12, tOut: G.tOut, outDur: G.outDur });
    const i2 = focusInk(r2, G.sub.font);
    if (i2) out.push({ kind: 'text', label: p.sub, ...i2, font_px: Math.round(G.sub.size) });
  }
  return out;
}

export function mbSamples() { return 1; }

export default { id, role, desc, params, sfx_hints, draw, bbox, mbSamples };
