/* ==========================================================================
   screen_pip — 穿进录屏（真人融合）
   Real footage. The full-screen talking shot shrinks into a rounded 3:4
   frame (about 300×400) that always keeps the head and upper body — the crop
   is derived from the Vision face track — holds for a beat, then flies into a
   screen recording: a generic editor window, landing in its presenter-cam
   slot. The window then works: tasks tick off, clips drop onto the timeline,
   the playhead runs. Footage pixels are drawn untouched (scaled only).
   No product UI, no brand names.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, springKick, hash2, rgba, rrect, tokFont, softDot, drawSprite } from '../engine/core.js';
import { layoutChars } from '../engine/text.js';
import { PLATE, preparePlate, frameAt, faceStats } from './plate.js';

export const id = 'screen_pip';
export const role = 'fusion';
export const desc = '穿进录屏：真人全屏画面缩进约 300×400 的圆角框（按人脸追踪取景，保证露出头和上半身），停一拍后飞进一个录屏界面的主播小窗位。';

export const params = {
  plate_start: { default: 3477, type: 'number', desc: '底片起始帧。' },
  plate_end: { default: 3597, type: 'number', desc: '底片结束帧（不含）。' },
  pip: { default: [300, 400], type: 'any', desc: '小窗尺寸（宽, 高），3:4。' },
  t_shrink: { default: [0.45, 1.15], type: 'any', desc: '缩进圆角框的起止（秒）。' },
  t_fly: { default: [1.38, 2.02], type: 'any', desc: '飞进录屏界面的起止（秒）。' },
  title: { default: '口播剪辑 · 自动成片', type: 'string', desc: '窗口标题。' },
  tasks: { default: ['识别口播', '生成字幕', '排版动效', '混音配乐'], type: 'any', desc: '右侧任务列表（依次打勾）。' },
  accent: { default: '#5B8CFF', type: 'color', desc: '界面强调色。' },
};

let CROP = null;
export async function prepare(p) {
  await preparePlate(p, { layers: ['plate'], json: ['faces'] });
  // 3:4 crop around the face track: never cut the head (hair sits ~0.45 face-heights above the box)
  const f = faceStats();
  const cw = 960, ch = 1280;
  const cx = clamp(f.x + f.w / 2, cw / 2, 1080 - cw / 2);
  const top = clamp(Math.min(f.minY - 0.5 * f.h, f.y + f.h * 0.5 - ch * 0.42), 0, 1920 - ch);
  CROP = { x: cx - cw / 2, y: top, w: cw, h: ch, face: f };
  return CROP;
}
export function timing(p) {
  return { shrink: p.t_shrink, fly: p.t_fly, dock: p.t_fly[1], tasks: p.tasks.map((_, i) => p.t_fly[1] + 0.35 + i * 0.42), clips: [0, 1, 2, 3].map(i => p.t_fly[1] + 0.25 + i * 0.3) };
}

/* ------------------------------------------------------------------ layout */
const WIN = { x: 35, y: 500, w: 1010, h: 680 };
function dockRect(p) { return { x: WIN.x + WIN.w - p.pip[0] - 22, y: WIN.y + WIN.h - p.pip[1] - 26, w: p.pip[0], h: p.pip[1] }; }   // inside the window, like a camera overlay in a recording
function midRect(p) { return { x: 540 - p.pip[0] / 2, y: 830 - p.pip[1] / 2, w: p.pip[0], h: p.pip[1] }; }

function pipState(t, p) {
  const T = timing(p), full = { x: 0, y: 0, w: 1080, h: 1920 };
  const us = E.cubicInOut(seg(t, T.shrink[0], T.shrink[1]));
  const uf = seg(t, T.fly[0], T.fly[1]);
  // source crop: full frame -> the 3:4 head-and-shoulders crop
  const S = { x: lerp(0, CROP.x, us), y: lerp(0, CROP.y, us), w: lerp(1080, CROP.w, us), h: lerp(1920, CROP.h, us) };
  const asp = S.w / S.h;
  let D, rot = 0, r = 34 * us;
  if (uf <= 0) {
    const M = midRect(p);
    const h = Math.exp(lerp(Math.log(1920), Math.log(M.h), us));                 // size shrinks geometrically
    const cx = lerp(540, M.x + M.w / 2, us), cy = lerp(960, M.y + M.h / 2, us);
    D = { x: cx - h * asp / 2, y: cy - h / 2, w: h * asp, h };
  } else {
    const M = midRect(p), K = dockRect(p), e = E.cubicInOut(uf);
    const c0 = [M.x + M.w / 2, M.y + M.h / 2], c2 = [K.x + K.w / 2, K.y + K.h / 2], c1 = [lerp(c0[0], c2[0], 0.5) + 40, Math.min(c0[1], c2[1]) - 40];
    const v = 1 - e, cx = v * v * c0[0] + 2 * v * e * c1[0] + e * e * c2[0], cy = v * v * c0[1] + 2 * v * e * c1[1] + e * e * c2[1];
    const sc = 1 + 0.06 * Math.sin(Math.PI * e);
    D = { x: cx - K.w * sc / 2, y: cy - K.h * sc / 2, w: K.w * sc, h: K.h * sc };
    rot = -0.09 * Math.sin(Math.PI * e);
  }
  const s = t - T.dock;
  if (s > 0) { const b = springKick(s, 4, 0.4) * 0.05; D = { x: D.x - D.w * b / 2, y: D.y - D.h * b / 2, w: D.w * (1 + b), h: D.h * (1 + b) }; }
  return { S, D, rot, r, us, uf };
}

/* ------------------------------------------------------------------ editor window (generic) */
function drawWindow(ctx, glow, t, p, tk, T, fr, alpha) {
  if (alpha <= 0.001) return;
  const { x, y, w, h } = WIN;
  ctx.save(); ctx.globalAlpha = alpha;
  ctx.save(); ctx.filter = 'blur(40px)'; ctx.fillStyle = 'rgba(0,0,0,0.7)'; rrect(ctx, x + 10, y + 40, w - 20, h, 26); ctx.fill(); ctx.restore();
  rrect(ctx, x, y, w, h, 22); ctx.fillStyle = '#16181E'; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.save(); rrect(ctx, x, y, w, h, 22); ctx.clip();
  // title bar
  ctx.fillStyle = '#1D2027'; ctx.fillRect(x, y, w, 52);
  ['#FF5F57', '#FEBC2E', '#28C840'].forEach((c, i) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(x + 28 + i * 24, y + 26, 7, 0, TAU); ctx.fill(); });
  ctx.font = tokFont(tk, 'sans', 20, 500); ctx.fillStyle = '#AEB4C0'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(p.title, x + w / 2, y + 27); ctx.textAlign = 'left';
  // left rail
  ctx.fillStyle = '#12141A'; ctx.fillRect(x, y + 52, 112, h - 52);
  const rail = ['素材', '字幕', '动效', '音效', '导出'];
  rail.forEach((lab, i) => {
    const yy = y + 96 + i * 78, on = i === Math.min(4, Math.floor(clamp((t - T.dock) / 0.42, 0, 3.99)) + 1) && t > T.dock;
    rrect(ctx, x + 30, yy - 22, 52, 36, 9); ctx.fillStyle = on ? rgba(p.accent, 0.9) : 'rgba(255,255,255,0.07)'; ctx.fill();
    ctx.font = tokFont(tk, 'sans', 17, 500); ctx.fillStyle = on ? '#E9EEFF' : '#7F8796'; ctx.textAlign = 'center'; ctx.fillText(lab, x + 56, yy + 34); ctx.textAlign = 'left';
  });
  // preview canvas: the very footage being edited, with a caption strip and a sticker being laid out
  const px = x + 140, py = y + 76, pw = 250, ph = 444;
  ctx.fillStyle = '#0B0C10'; ctx.fillRect(px - 6, py - 6, pw + 12, ph + 12);
  const load = clamp((t - T.dock - 0.1) / 0.35);                  // the recording loads into the editor once docked
  if (fr) {                                                        // blurred and dim until it has loaded, then sharp
    ctx.save(); ctx.filter = load < 1 ? `blur(${(12 * (1 - load)).toFixed(1)}px) brightness(${(0.35 + 0.65 * load).toFixed(2)})` : 'none';
    ctx.drawImage(fr.plate, 0, 0, 1080, 1920, px, py, pw, ph); ctx.restore();
  }
  if (load < 1) {
    ctx.fillStyle = 'rgba(255,255,255,0.06)'; rrect(ctx, px + pw / 2 - 60, py + ph / 2 - 3, 120, 6, 3); ctx.fill();
    ctx.fillStyle = rgba(p.accent, 0.8); rrect(ctx, px + pw / 2 - 60, py + ph / 2 - 3, 120 * (0.15 + 0.85 * ((t * 0.7) % 1)), 6, 3); ctx.fill();
  }
  const cap = clamp((t - T.tasks[1]) / 0.25);
  if (cap > 0) { ctx.fillStyle = `rgba(0,0,0,${0.55 * cap})`; rrect(ctx, px + 20, py + ph * 0.78, pw - 40, 30, 6); ctx.fill(); ctx.fillStyle = `rgba(255,255,255,${cap})`; ctx.font = tokFont(tk, 'sans', 15, 700); ctx.textAlign = 'center'; ctx.fillText('会进行视频的剪辑', px + pw / 2, py + ph * 0.78 + 16); ctx.textAlign = 'left'; }
  const st = clamp((t - T.tasks[2]) / 0.2);
  if (st > 0) { ctx.save(); ctx.translate(px + pw - 58, py + 70); ctx.rotate(0.12); ctx.scale(E.backOut(st, 2), E.backOut(st, 2)); rrect(ctx, -44, -18, 88, 36, 10); ctx.fillStyle = '#FFD43B'; ctx.fill(); ctx.fillStyle = '#1B1B1B'; ctx.font = tokFont(tk, 'sans', 17, 700); ctx.textAlign = 'center'; ctx.fillText('动效', 0, 1); ctx.restore(); ctx.textAlign = 'left'; }
  // task list (appears once the recording is in)
  const lx = x + 430, ly = y + 90, lw = 250;
  const tla = clamp((t - T.dock) / 0.3);
  ctx.globalAlpha = alpha * tla;
  ctx.font = tokFont(tk, 'sans', 18, 500); ctx.fillStyle = '#7F8796'; ctx.fillText('任务', lx, ly - 8);
  p.tasks.forEach((lab, i) => {
    const yy = ly + 34 + i * 58, done = t >= T.tasks[i], k = clamp((t - T.tasks[i]) / 0.18);
    rrect(ctx, lx, yy - 20, lw, 44, 10); ctx.fillStyle = done ? 'rgba(91,140,255,0.12)' : 'rgba(255,255,255,0.04)'; ctx.fill();
    ctx.fillStyle = done ? '#DDE5F7' : '#8B92A0'; ctx.font = tokFont(tk, 'sans', 20, 500); ctx.fillText(lab, lx + 48, yy + 2);
    ctx.beginPath(); ctx.arc(lx + 24, yy + 2, 10, 0, TAU); ctx.strokeStyle = done ? p.accent : 'rgba(255,255,255,0.25)'; ctx.lineWidth = 2; ctx.stroke();
    if (k > 0) { ctx.fillStyle = p.accent; ctx.beginPath(); ctx.arc(lx + 24, yy + 2, 10 * k, 0, TAU); ctx.fill(); ctx.strokeStyle = '#FFF'; ctx.lineWidth = 2.4; ctx.beginPath(); ctx.moveTo(lx + 19, yy + 2); ctx.lineTo(lx + 23, yy + 6); ctx.lineTo(lx + 30, yy - 3); ctx.stroke(); }
    else if (t > T.dock && i === p.tasks.findIndex((_, j) => t < T.tasks[j])) {    // the one in progress spins
      ctx.strokeStyle = p.accent; ctx.lineWidth = 2.4; ctx.beginPath(); ctx.arc(lx + 24, yy + 2, 10, t * 7, t * 7 + 4); ctx.stroke();
    }
  });
  const prog = clamp((t - T.dock) / (T.tasks[p.tasks.length - 1] - T.dock + 0.2));
  rrect(ctx, lx, ly + 34 + p.tasks.length * 58 - 6, lw, 8, 4); ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.fill();
  rrect(ctx, lx, ly + 34 + p.tasks.length * 58 - 6, lw * prog, 8, 4); ctx.fillStyle = p.accent; ctx.fill();
  ctx.globalAlpha = alpha;
  // timeline
  const tx = x + 130, ty = y + h - 118, tw = w - 130 - 360;
  ctx.fillStyle = '#101218'; ctx.fillRect(x + 112, ty - 16, w - 112 - 344, 134);
  const rows = [['#3C6FB0', 0.02, 0.62], ['#8E6BD8', 0.1, 0.5], ['#E0A23A', 0.28, 0.2], ['#3E9E6E', 0.02, 0.82]];
  rows.forEach(([c, a0, len], i) => {
    const k = E.cubicOut(clamp((t - T.clips[i]) / 0.3));
    if (k <= 0) return;
    rrect(ctx, tx + tw * a0, ty + i * 26, tw * len * k, 20, 5); ctx.fillStyle = c; ctx.fill();
  });
  const ph2 = clamp((t - T.dock) / 2.2);
  ctx.fillStyle = '#FF5A48'; ctx.fillRect(tx + tw * (0.05 + 0.6 * ph2), ty - 12, 2.5, 122);
  ctx.restore();
  ctx.restore();
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  const T = timing(p);
  if (t > T.shrink[0] - 0.05 && t < T.shrink[1] + 0.05) return 8;
  if (t > T.fly[0] - 0.05 && t < T.fly[1] + 0.2) return 10;
  return 2;
}

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, glow = env.glow, T = timing(p);
  const fr = frameAt(t, env.fps);
  if (!CROP) { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); return; }       // boot warm-up runs before prepare()
  const st = pipState(t, p);
  if (st.us <= 0) { if (fr) ctx.drawImage(fr.plate, 0, 0); return; }      // untouched full-screen footage
  // desk behind the screen
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#0A0B0F'); g.addColorStop(0.5, '#15171D'); g.addColorStop(1, '#08090C');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const rg = ctx.createRadialGradient(W / 2, WIN.y + WIN.h / 2, 40, W / 2, WIN.y + WIN.h / 2, 900);
  rg.addColorStop(0, rgba(p.accent, 0.12)); rg.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
  // the screen fades / racks in behind the shrinking frame
  const wa = smooth(seg(t, T.shrink[0] + 0.15, T.shrink[1] + 0.1));
  ctx.save();
  const wb = 10 * (1 - wa);
  if (wb > 0.3) ctx.filter = `blur(${wb.toFixed(1)}px)`;
  ctx.translate(W / 2, WIN.y + WIN.h / 2); ctx.scale(lerp(0.94, 1, wa), lerp(0.94, 1, wa)); ctx.translate(-W / 2, -(WIN.y + WIN.h / 2));
  drawWindow(ctx, glow, t, p, tk, T, fr, wa);
  ctx.restore(); ctx.filter = 'none';
  // dock slot glow when it lands
  const s = t - T.dock;
  if (s > 0 && s < 0.6 && glow) { const K = dockRect(p); glow.save(); glow.strokeStyle = rgba(p.accent, 0.8 * (1 - s / 0.6)); glow.lineWidth = 10; rrect(glow, K.x - 6, K.y - 6, K.w + 12, K.h + 12, 40); glow.stroke(); glow.restore(); }
  // the frame: footage crop into a rounded rect, white rim, soft shadow
  const { S, D, rot, r } = st;
  const cx = D.x + D.w / 2, cy = D.y + D.h / 2;
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.translate(-cx, -cy);
  ctx.save(); ctx.filter = 'blur(28px)'; ctx.fillStyle = `rgba(0,0,0,${(0.55 * st.us).toFixed(3)})`; rrect(ctx, D.x + 8, D.y + 26, D.w, D.h, r + 6); ctx.fill(); ctx.restore();
  ctx.save(); rrect(ctx, D.x, D.y, D.w, D.h, r); ctx.clip();
  if (fr) ctx.drawImage(fr.plate, S.x, S.y, S.w, S.h, D.x, D.y, D.w, D.h);
  ctx.restore();
  const rim = clamp(st.us * 1.5 - 0.3);
  if (rim > 0) { rrect(ctx, D.x, D.y, D.w, D.h, r); ctx.strokeStyle = `rgba(255,255,255,${(0.95 * rim).toFixed(3)})`; ctx.lineWidth = 5; ctx.stroke(); }
  // REC dot once docked
  if (t > T.dock) { const on = Math.floor((t - T.dock) / 0.5) % 2 === 0; ctx.fillStyle = on ? '#FF4B3E' : 'rgba(255,75,62,0.35)'; ctx.beginPath(); ctx.arc(D.x + 26, D.y + 26, 8, 0, TAU); ctx.fill(); }
  ctx.restore();
}

export function bbox(t, p, tk, env) { const K = dockRect(p); return [{ kind: 'card', label: 'pip', x: K.x, y: K.y, w: K.w, h: K.h }]; }
