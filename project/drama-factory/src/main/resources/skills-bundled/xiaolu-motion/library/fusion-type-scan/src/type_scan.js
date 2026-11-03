/* ==========================================================================
   type_scan — 活字扫描（真人融合）
   Real footage split with an Apple Vision person matte. A first scan line
   turns the wall behind the speaker into a forme of metal type — the
   characters are the video's own script, set in reading order. When he says
   the checking line, a brighter check-scan sweeps down the wall: every sort
   in its band rises toward the lens and flips over to a freshly polished
   face; the row above his head turns over to spell the checked phrase in
   gold. The speaker stays in front, in his own untouched colours (the matte
   edge colours are un-mixed from the known wall, so no beige halo on dark
   metal).

   Sorts are lit 3-D blocks while they move (perspective, rotation about the
   horizontal axis, culling); the glyph is drawn on whichever face looks at
   the camera, mapped through its own corners, so it is never mirrored.
   ========================================================================== */
import { E, TAU, clamp, lerp, seg, smooth, hash2, rgba, tokFont, mkCanvas, softDot, drawSprite } from '../engine/core.js';
import { inkBox } from '../engine/text.js';
import { PLATE, preparePlate, frameAt, faceStats } from './plate.js';

export const id = 'type_scan';
export const role = 'fusion';
export const desc = '活字扫描：人身后的墙变成排满金属活字的版面；说到“检查”时扫描线自上而下扫过，活字随扫描线升起、翻面，头顶一行翻出金色短语。人物保持原片彩色在最前面。';

export const params = {
  plate_start: { default: 3600, type: 'number', desc: '底片起始帧。' },
  plate_end: { default: 3738, type: 'number', desc: '底片结束帧（不含）。' },
  text: { default: '', type: 'string', desc: '墙上排的字（按阅读顺序，自动去掉非汉字）。' },
  text2: { default: '', type: 'string', desc: '翻面后露出的字。' },
  phrase: { default: '自己检查一遍', type: 'string', desc: '头顶那一行翻出的金色短语。' },
  phrase_row: { default: 2, type: 'number', desc: '金色短语所在行（从 0 数）。' },
  reveal: { default: [0.12, 1.0], type: 'any', desc: '第一道扫描（墙变活字）的起止（秒）。' },
  scan: { default: [2.2, 3.9], type: 'any', desc: '检查扫描的起止（秒）。' },
  pitch: { default: 128, type: 'number', desc: '活字间距（px）。' },
};

let KEEP = null;                                   // union of the face boxes: sorts there are blank spacers (quads)
export async function prepare(p) {
  await preparePlate(p, { layers: ['plate', 'person'], json: ['faces'] });
  const f = faceStats(); const m = 24;
  KEEP = f ? { x0: f.minX - m, y0: f.minY - m, x1: f.maxR + m, y1: f.maxB + m } : null;
  return KEEP;
}
export function timing(p) {
  const rows = Math.ceil(1920 / p.pitch) + 1;
  const rowAt = (r, a, b) => lerp(a, b, (r * p.pitch + p.pitch / 2) / 1920);
  return { reveal: p.reveal, scan: p.scan, rowsRevealed: [...Array(rows).keys()].map(r => rowAt(r, ...p.reveal)).filter(t => t < p.reveal[1]),
    rowsFlipped: [...Array(rows).keys()].map(r => rowAt(r, ...p.scan)).filter(t => t < p.scan[1]), phraseAt: rowAt(p.phrase_row, ...p.scan) + 0.12 };
}

/* ------------------------------------------------------------------ sprites */
const CACHE = {};
function face(ch, S, tk, gold, polish) {
  const k = ch + S + (gold ? 'g' : '') + polish;
  if (CACHE[k]) return CACHE[k];
  const c = mkCanvas(S, S), x = c.getContext('2d');
  // field: dark oxidised metal, machining lines
  const g = x.createLinearGradient(0, 0, S, S);
  g.addColorStop(0, gold ? '#3E3222' : '#2E2925'); g.addColorStop(1, gold ? '#1E170F' : '#171411');
  x.fillStyle = g; x.fillRect(0, 0, S, S);
  for (let i = 0; i < S; i += 3) { x.fillStyle = `rgba(255,236,210,${0.025 + 0.03 * hash2(S, i)})`; x.fillRect(0, i, S, 1); }
  x.strokeStyle = 'rgba(255,230,200,0.18)'; x.lineWidth = 2; x.strokeRect(1, 1, S - 2, S - 2);
  if (ch === ' ') { CACHE[k] = c; return c; }         // spacer quad: no face
  // raised glyph: shadow, shoulder, polished face, bevel
  const font = tokFont(tk, 'serif', S * 0.72, 900);
  const ib = inkBox(ch, font), gx = S / 2 - (ib.l + ib.r) / 2, gy = S / 2 - (ib.t + ib.b) / 2;
  x.font = font; x.textBaseline = 'alphabetic';
  x.filter = 'blur(1.2px)'; x.fillStyle = 'rgba(0,0,0,0.85)'; x.fillText(ch, gx + 2, gy + 3); x.filter = 'none';
  const top = gold ? '#FFE4A0' : polish ? '#F4ECE2' : '#B8AC9E', bot = gold ? '#B47A28' : polish ? '#A89A8B' : '#6E645A';
  const gg = x.createLinearGradient(0, gy + ib.t, 0, gy + ib.b); gg.addColorStop(0, top); gg.addColorStop(1, bot);
  x.fillStyle = gg; x.fillText(ch, gx, gy);
  const rim = mkCanvas(S, S), r = rim.getContext('2d');
  r.font = font; r.textBaseline = 'alphabetic'; r.fillStyle = gold ? '#FFF3D0' : '#FFF6EA'; r.fillText(ch, gx, gy);
  r.globalCompositeOperation = 'destination-out'; r.fillText(ch, gx + 1.3, gy + 1.6);
  x.globalAlpha = polish || gold ? 0.9 : 0.5; x.drawImage(rim, 0, 0); x.globalAlpha = 1;
  CACHE[k] = c;
  return c;
}
function cjk(s) { return [...(s || '')].filter(ch => /[一-鿿]/.test(ch)); }
const DEFAULT_A = '不会剪辑也能做出这样的视频如果你想做做科普或者做不露脸的视频但是你又不想剪辑或者说你也不会剪辑那你可以看看我这个免费的开源工具本期视频的所有工具都已经放入了文档里面我是小鹿一个很会玩的文科生这是转场多一点字幕做成贴纸时间天气心情这些小卡片它会自己点缀上去而这是科普你讲到的原理会变成图和动画跟着你的内容一步步画出来';
const DEFAULT_B = '第一步确认选题第二步画面风格第三步分镜脚本第四步剪辑成片完成前三步之后会进行视频的剪辑动效音效等包装完成后它会自己检查一遍如果出现字压到脸上或者说挡住字幕等影响观感的情况就会自己去重新做一遍';

/* ------------------------------------------------------------------ one sort, flipping about its horizontal axis */
const F3 = 2600;
function drawFlip(ctx, x0, y0, S, ang, lift, fA, fB, lightK) {
  // block centre at (x0 + S/2, y0 + S/2); faces at z = +d/2 (front) and -d/2 (back); rotate about X by ang
  const d = S * 0.8, cx = x0 + S / 2, cy = y0 + S / 2, zc = lift - d / 2;
  const P = (x, y, z) => {                        // local (x, y, z) about the centre -> screen
    const ca = Math.cos(ang), sa = Math.sin(ang);
    const yy = y * ca - z * sa, zz = y * sa + z * ca + zc + d / 2;
    const s = F3 / (F3 - zz);
    return [540 + (cx + x - 540) * s, 900 + (cy + yy - 900) * s];
  };
  const h = S / 2, hz = d / 2;
  const front = [P(-h, -h, hz), P(h, -h, hz), P(h, h, hz), P(-h, h, hz)];
  const back = [P(-h, h, -hz), P(h, h, -hz), P(h, -h, -hz), P(-h, -h, -hz)];   // listed so that it reads upright once flipped
  const nz = Math.cos(ang);                          // front normal z after rotation
  const quad = q => { ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); for (let i = 1; i < 4; i++) ctx.lineTo(q[i][0], q[i][1]); ctx.closePath(); };
  // the side face that shows while it turns (top or bottom), lead-alloy grey lit from above
  const sa = Math.sin(ang);
  if (Math.abs(sa) > 0.02) {
    const side = sa > 0 ? [P(-h, h, hz), P(h, h, hz), P(h, h, -hz), P(-h, h, -hz)] : [P(-h, -h, -hz), P(h, -h, -hz), P(h, -h, hz), P(-h, -h, hz)];
    quad(side); ctx.fillStyle = `rgb(${(96 * lightK) | 0},${(88 * lightK) | 0},${(80 * lightK) | 0})`; ctx.fill();
  }
  const q = nz >= 0 ? front : back, img = nz >= 0 ? fA : fB;
  ctx.save(); quad(q); ctx.clip();
  const [tl, tr, , bl] = q;
  ctx.transform((tr[0] - tl[0]) / img.width, (tr[1] - tl[1]) / img.width, (bl[0] - tl[0]) / img.height, (bl[1] - tl[1]) / img.height, tl[0], tl[1]);
  ctx.drawImage(img, 0, 0);
  ctx.restore();
  const shade = 1 - Math.abs(nz);
  if (shade > 0.02) { quad(q); ctx.fillStyle = `rgba(0,0,0,${(0.55 * shade).toFixed(3)})`; ctx.fill(); }
}

/* ------------------------------------------------------------------ component API */
export function mbSamples(t, p) {
  if (t > p.reveal[0] - 0.05 && t < p.reveal[1] + 0.1) return 6;
  if (t > p.scan[0] - 0.05 && t < p.scan[1] + 0.4) return 8;
  return 1;
}

export function draw(ctx, t, p, tk, env) {
  const { W, H } = env, glow = env.glow;
  const fr = frameAt(t, env.fps);
  if (!fr) { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); return; }
  ctx.drawImage(fr.plate, 0, 0);                                     // untouched footage underneath
  const S0 = p.pitch, S = S0 - 10, cols = Math.ceil(W / S0) + 1, rows = Math.ceil(H / S0) + 1;
  const ox = (W - cols * S0) / 2 + 5, oy = -S0 * 0.35;
  const A = cjk(p.text) .length ? cjk(p.text) : cjk(DEFAULT_A), B = cjk(p.text2).length ? cjk(p.text2) : cjk(DEFAULT_B);
  const phrase = cjk(p.phrase), pc0 = Math.floor((cols - phrase.length) / 2);
  const revealY = lerp(-60, H + 60, E.sineInOut(seg(t, p.reveal[0], p.reveal[1])));
  const scanY = lerp(-80, H + 80, E.sineInOut(seg(t, p.scan[0], p.scan[1])));
  // the type wall, clipped above the reveal line (below it the real wall still shows)
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, Math.max(0, revealY)); ctx.clip();
  ctx.fillStyle = '#0E0C0A'; ctx.fillRect(0, 0, W, H);
  const lit = (y) => 0.72 + 0.28 * Math.exp(-(((y - H * 0.35) / (H * 0.6)) ** 2));      // soft top key on the forme
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const x0 = ox + c * S0, y0 = oy + r * S0, yc = y0 + S / 2;
    const k = r * cols + c;
    const isP = r === p.phrase_row && c >= pc0 && c < pc0 + phrase.length;
    const blank = KEEP && x0 + S > KEEP.x0 && x0 < KEEP.x1 && y0 + S > KEEP.y0 && y0 < KEEP.y1 && !isP;
    const fA = face(blank ? ' ' : A[k % A.length], S, tk, false, false);
    const fB = isP ? face(phrase[c - pc0], S, tk, true, true) : face(blank ? ' ' : B[k % B.length], S, tk, false, true);
    // reveal pop: sorts just uncovered by the first line settle down from a small rise
    const dR = revealY - yc, pop = dR > 0 && dR < 260 ? Math.sin(Math.PI * dR / 260) : 0;
    // check scan: rise toward the lens, turn over (half turn about X), settle
    const dS = (scanY - yc) / 300 - (c / (cols - 1) - 0.5) * 0.7;    // flip front leans: sorts turn over in a diagonal wave
    const flipU = clamp(dS + 0.35, 0, 1);                            // starts slightly before the line arrives
    const ang = Math.PI * E.cubicInOut(flipU) * (1 + 0.06 * (hash2(k, 3) - 0.5));
    const lift = 60 * Math.sin(Math.PI * flipU) + 26 * pop;
    const band = Math.exp(-(((scanY - yc) / 110) ** 2));
    const L = lit(yc) * (1 + 0.55 * band);
    if (flipU <= 0 && pop <= 0.001) { ctx.globalAlpha = 1; ctx.drawImage(fA, x0, y0, S, S); }
    else if (flipU >= 1) { ctx.drawImage(fB, x0, y0, S, S); }
    else drawFlip(ctx, x0, y0, S, ang, lift, fA, fB, L);
    if (L < 1) { ctx.fillStyle = `rgba(0,0,0,${(1 - L).toFixed(3)})`; ctx.fillRect(x0, y0, S, S); }
    else if (band > 0.02) { ctx.fillStyle = `rgba(200,240,255,${(0.16 * band).toFixed(3)})`; ctx.fillRect(x0, y0, S, S); }
    if (isP && flipU >= 1 && glow) { const s2 = clamp((t - (p.scan[0] + (yc + 80) / (H + 160) * (p.scan[1] - p.scan[0]))) / 0.6); drawSprite(glow, softDot('gp', '#FFC766'), x0 + S / 2, y0 + S / 2, S * 0.9, 0.45 * (1 - 0.5 * s2)); }
  }
  ctx.restore();
  // scan lines (on the wall, behind the speaker)
  const line = (y, a, col, gw) => {
    if (a <= 0.01 || y < -40 || y > H + 40) return;
    const g = ctx.createLinearGradient(0, y - gw, 0, y + gw);
    g.addColorStop(0, rgba(col, 0)); g.addColorStop(0.5, rgba(col, 0.35 * a)); g.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = g; ctx.fillRect(0, y - gw, W, gw * 2);
    ctx.fillStyle = rgba('#FFFFFF', 0.9 * a); ctx.fillRect(0, y - 1.5, W, 3);
    if (glow) { glow.fillStyle = rgba(col, 0.9 * a); glow.fillRect(0, y - 6, W, 12); }
  };
  line(revealY, bumpA(t, p.reveal), '#FFC98A', 60);
  line(scanY, bumpA(t, p.scan), '#BFEFFF', 90);
  // the speaker in front, untouched plate pixels with the Vision matte as alpha
  if (revealY > 0) ctx.drawImage(fr.person, 0, 0);
  // bloom is added over the finished frame, so light that belongs to the wall must not land on the speaker:
  // cut the person out of the glow layer (what remains near the silhouette reads as a soft light wrap)
  if (glow) { glow.save(); glow.globalCompositeOperation = 'destination-out'; glow.drawImage(fr.person, 0, 0); glow.restore(); }
}
function bumpA(t, [a, b]) { return smooth(seg(t, a - 0.05, a + 0.1)) * (1 - smooth(seg(t, b - 0.1, b + 0.05))); }

export function bbox(t, p, tk, env) { return [{ kind: 'shape', label: 'type wall', x: 0, y: 0, w: env.W, h: env.H, layer: 'behind', full: true }]; }
