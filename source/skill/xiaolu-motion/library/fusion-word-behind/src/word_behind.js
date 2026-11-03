/* ==========================================================================
   word_behind — 字在人后（真人融合）
   Real footage split into three depths with an Apple Vision person matte:
   the wall (live plate, the person region filled from a clean plate), a huge
   word standing between wall and speaker, and the speaker in front. The word
   racks into focus as it is said; a slow push-in moves the three layers at
   different rates (wall < word < person), so the head keeps covering part of
   the word with a real sense of depth. The word casts a soft shadow on the
   wall. Footage colours are untouched: the person layer is the plate itself
   (edge colours un-mixed from the known wall), drawn at full opacity.
   ========================================================================== */
import { E, clamp, lerp, seg, smooth, rgba, tokFont, mkCanvas } from '../engine/core.js';
import { inkBox, layoutChars } from '../engine/text.js';
import { PLATE, preparePlate, frameAt, faceStats } from './plate.js';

export const id = 'word_behind';
export const role = 'fusion';
export const desc = '字在人后：巨大的词放在人和墙之间，被头部遮住一部分；推镜时墙、字、人按不同速度运动，有轻微视差。人物颜色保持原片。';

export const params = {
  plate_start: { default: 1586, type: 'number', desc: '底片起始帧。' },
  plate_end: { default: 1726, type: 'number', desc: '底片结束帧（不含）。' },
  text: { default: '开源', type: 'string', desc: '人身后的词（建议 2 个字）。' },
  at: { default: 1.08, type: 'number', desc: '这个词被说出的时刻（本镜头内，秒）；字在此刻对焦落定。' },
  color: { default: '#2448C9', type: 'color', desc: '字色。' },
  size: { default: 430, type: 'number', desc: '字号（px）。' },
  y: { default: 350, type: 'number', desc: '字面中心的 y（px）。' },
  gap: { default: 150, type: 'number', desc: '两字之间留给头部的空隙（px）。' },
  push: { default: [1.022, 1.042, 1.062], type: 'any', desc: '结束时的缩放：墙、字、人（视差由这三者的差决定）。' },
  drift: { default: [-6, -13, -20], type: 'any', desc: '结束时的水平漂移（px）：墙、字、人。' },
};

export async function prepare(p) { await preparePlate(p, { layers: ['bg', 'person'], json: ['faces'] }); return faceStats(); }
export function timing(p) { return { at: p.at, in0: p.at - 0.42 }; }

let ANCHOR = null;
function xf(ctx, k, t, p, env) {                    // layer transform: push about the face centre + drift
  if (!ANCHOR) { const f = faceStats(); ANCHOR = f ? [f.x + f.w / 2, f.y + f.h / 2] : [540, 900]; }
  const u = E.sineInOut(seg(t, 0, env.dur));
  const s = lerp(1, p.push[k], u), dx = p.drift[k] * u;
  ctx.translate(ANCHOR[0] + dx, ANCHOR[1]); ctx.scale(s, s); ctx.translate(-ANCHOR[0], -ANCHOR[1]);
}

function drawWord(ctx, t, p, tk, env, shadowOnly) {
  const chars = [...p.text];
  const font = tokFont(tk, 'serif', p.size, 900);
  const u = E.expoOut(seg(t, p.at - 0.42, p.at + 0.08));        // rack focus into place
  if (u <= 0.001) return;
  const blur = 26 * (1 - u), sc = lerp(1.18, 1, u), a = clamp(u * 1.4);
  ctx.save();
  ctx.translate(env.W / 2, p.y); ctx.scale(sc, sc); ctx.translate(-env.W / 2, -p.y);
  ctx.font = font; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'center';
  const n = chars.length, cw = p.size * 0.98;
  const total = n * cw + (n - 1) * p.gap;
  chars.forEach((ch, i) => {
    const cx = env.W / 2 - total / 2 + cw / 2 + i * (cw + p.gap);
    const ib = inkBox(ch, font), base = p.y - (ib.t + ib.b) / 2;
    if (shadowOnly) {
      ctx.filter = `blur(${(16 + blur).toFixed(1)}px)`; ctx.fillStyle = `rgba(60,48,36,${(0.26 * a).toFixed(3)})`;
      ctx.fillText(ch, cx + 18, base + 24);
    } else {
      ctx.filter = blur > 0.3 ? `blur(${blur.toFixed(2)}px)` : 'none';
      const g = ctx.createLinearGradient(0, base + ib.t, 0, base + ib.b);
      g.addColorStop(0, mixc(p.color, '#FFFFFF', 0.12)); g.addColorStop(1, mixc(p.color, '#000000', 0.18));
      ctx.globalAlpha = a; ctx.fillStyle = g; ctx.fillText(ch, cx, base);
      ctx.globalAlpha = 1;
    }
  });
  ctx.filter = 'none'; ctx.restore();
}
function mixc(a, b, t) {
  const A = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16)), B = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], t))).join(',')})`;
}

export function mbSamples(t, p) { return (t > p.at - 0.5 && t < p.at + 0.2) ? 6 : 1; }

export function draw(ctx, t, p, tk, env) {
  const fr = frameAt(t, env.fps);
  if (!fr) { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, env.W, env.H); return; }
  // 1) wall
  ctx.save(); xf(ctx, 0, t, p, env); ctx.drawImage(fr.bg, 0, 0); ctx.restore();
  // 2) the word's shadow on the wall, then the word (both at the word's depth)
  ctx.save(); xf(ctx, 1, t, p, env); drawWord(ctx, t, p, tk, env, true); drawWord(ctx, t, p, tk, env, false); ctx.restore();
  // 3) the speaker, untouched plate pixels with the Vision matte as alpha
  ctx.save(); xf(ctx, 2, t, p, env); ctx.drawImage(fr.person, 0, 0); ctx.restore();
}

export function bbox(t, p, tk, env) {
  const n = [...p.text].length, cw = p.size * 0.98, total = n * cw + (n - 1) * p.gap;
  return [{ kind: 'text', label: p.text, x: env.W / 2 - total / 2, y: p.y - p.size / 2, w: total, h: p.size, font_px: p.size, layer: 'behind' }];
}
