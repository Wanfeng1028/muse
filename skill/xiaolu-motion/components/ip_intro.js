/* ==========================================================================
   ip_intro — 小鹿 IP 固定开场（全屏）
   点阵暖纸底；三张白描边大头贴按音节弹性连闪（最后一张拍下落定）；
   「我是小鹿」大字（名字高亮）+ 副标题；往期封面卡斜贴四周，带纸胶带、
   视差漂移；整屏统一纸纹和颗粒。画幅 9:16 / 3:4 自动切版式。

   Assets: components/ip_intro/assets/manifest.json (stickers, committed) and
   assets/covers/covers.json (local cover cards, not committed). They are
   decoded once at import time (top-level await, browser only) so draw() stays
   synchronous and deterministic; Node can still import this file for specs.
   Docs: components/ip_intro/README.md
   ========================================================================== */
import { E, TAU, DEG, clamp, lerp, seg, spring, springKick, mulberry32, gaussR, hashU, Noise, rgba, tokColor, tokFont, mkCanvas, rrect } from '../engine/core.js';

export const id = 'ip_intro';
export const role = 'overlay';
export const desc = '小鹿 IP 固定开场（全屏）：点阵暖纸底 + 大头贴按音节弹性连闪（末张拍下落定）+「我是小鹿」大字（名字高亮）+ 副标题 + 往期封面卡斜贴四周（纸胶带、视差漂移）+ 统一纸纹颗粒；9:16 / 3:4 自动版式。';
export const sfx_hints = [
  { id: 'pop_soft', at: '每张大头贴回弹顶点：beats[i] + 0.12s（最后一张为 beats[-1]），pitch 0/+2/+4' },
  { id: 'land', at: '最后一张大头贴落定：beats[-1] + 0.085s' },
];

export const params = {
  stickers: { default: ['smile', 'surprise', 'wink'], type: 'any', desc: '大头贴列表：assets/manifest.json 里的 key（或 assets/ 下已登记的相对路径），按顺序在 beats 上连闪。' },
  beats: { default: [0.0, 0.85, 1.83], type: 'any', desc: '词锚点（镜头内秒）：每张大头贴出现的时刻，取对应音节起点前约 0.04s；长度须与 stickers 相同。' },
  words: { default: [], type: 'any', desc: '词级时间码（镜头内秒）[{w, s, e}]。给了就让标题逐字跟读音出现、副标题从它第一个字的读音起出现；不给则标题跟 beats[0]、副标题跟 beats[1]。' },
  prefix: { default: '我是', type: 'string', desc: '大字里名字前面的字。' },
  name: { default: '小鹿', type: 'string', desc: '名字（用 name_color）。' },
  name_color: { default: '#EC6E26', type: 'color', desc: '名字高亮色；副标题里 sub_hi 片段同色。' },
  sub: { default: '一个会玩AI的文科生', type: 'string', desc: '副标题（留空不画）。' },
  sub_hi: { default: ['AI'], type: 'any', desc: '副标题中用高亮色的片段列表。' },
  sub_mode: { default: 'stagger', type: 'enum', values: ['stagger', 'sync'], desc: "副标题出现方式：stagger 从首字读音起逐字快速错峰（约 0.3s 出齐，方便读）；sync 每个字跟自己的读音。" },
  covers: { default: ['token90', 'autoedit', 'shoucang', 'keng', 'qianetou', 'photo25'], type: 'any', desc: '封面卡：assets/covers/covers.json 里的 key，依次放进版式的 6 个位置（左上、右上、左中、右中、左下、右下）；缺图画空白纸卡占位。' },
  cover_tape: { default: {}, type: 'object', desc: "按 key 指定胶带位置 {key: 'tr'|'tl'|'top'}。未指定时：主页截图裁的卡（covers.json grid_ui=true）贴右上角斜胶带，盖住原播放键位置；其余贴顶边。" },
  layout: { default: 'auto', type: 'enum', values: ['auto', '9x16', '3x4'], desc: '版式：auto 按画布比例选（高/宽 > 1.6 用 9x16）。' },
  out: { default: 'cut', type: 'enum', values: ['cut', 'pop'], desc: '退场：cut 硬切给下一镜（对标做法）；pop 最后 out_dur 秒整体缩小淡出。' },
  out_dur: { default: 0.2, type: 'number', min: 0.05, max: 1, desc: 'pop 退场时长。' },
  paper: { default: '#F3EBDD', type: 'color', desc: '纸底色（取自出镜者旧版开场）。' },
  dot: { default: '#DCD0BC', type: 'color', desc: '点阵颜色。' },
  ink: { default: '#231C17', type: 'color', desc: '大字墨色。' },
  sub_color: { default: '#3A302A', type: 'color', desc: '副标题颜色。' },
  grain: { default: 0.6, type: 'number', min: 0, max: 1.5, desc: '颗粒强度（整屏统一，逐帧变化）。' },
  drift: { default: 1, type: 'number', min: 0, max: 3, desc: '封面卡漂移 + 视差推近强度（0 = 静止）。' },
  seed: { default: 7, type: 'number', desc: '纸纹 / 漂移随机种子。' },
};

/* ---------------- asset preload (browser only; Node imports this file for specs) ---------------- */
const IMGS = new Map();          // key or relative path -> ImageBitmap
const COVER_META = new Map();    // cover key -> covers.json entry
const REPORT = { loaded: [], missing: [] };
if (typeof document !== 'undefined' && typeof fetch === 'function') {
  const base = new URL('./ip_intro/assets/', import.meta.url);
  const json = async rel => { try { const r = await fetch(new URL(rel, base), { cache: 'no-store' }); return r.ok ? await r.json() : null; } catch (e) { return null; } };
  const man = await json('manifest.json');
  const cov = await json('covers/covers.json');
  const entries = [...((man && man.stickers) || []), ...((cov && cov.covers) || [])];
  for (const c of (cov && cov.covers) || []) COVER_META.set(c.key, c);
  await Promise.all(entries.map(async e => {
    try {
      const r = await fetch(new URL(e.file, base), { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const bmp = await createImageBitmap(await r.blob());
      IMGS.set(e.key, bmp); IMGS.set(e.file, bmp); REPORT.loaded.push(e.file);
    } catch (err) { REPORT.missing.push(e.file); }
  }));
  if (typeof window !== 'undefined') window.XM_IP_INTRO = REPORT;
}
const img = ref => (ref && IMGS.get(typeof ref === 'string' ? ref : ref.key)) || null;

/* ---------------- layouts (px at 1080 wide; y in px of the given canvas height) ---------------- */
// card slot: [cx, cy, rot°, depth, group]  group 0 = settles from t=0, 1 = slides in on beats[1]
const LAYOUTS = {
  '3x4': {
    sticker: { cx: 540, cy: 548, h: 720 },
    title: { cy: 1066, size: 150, track: 6 },
    sub: { cy: 1198, size: 60, track: 3 },
    card: 250,
    slots: [[150, 158, -11, 1.25, 0], [932, 140, 9, 1.15, 0], [58, 650, 7, 1.35, 1], [1024, 705, -8, 1.3, 1], [76, 1390, -10, 1.2, 0], [1004, 1394, 10, 1.2, 0]],
  },
  '9x16': {
    sticker: { cx: 540, cy: 790, h: 800 },
    title: { cy: 1342, size: 164, track: 7 },
    sub: { cy: 1490, size: 66, track: 3 },
    card: 290,
    slots: [[176, 236, -11, 1.25, 0], [904, 214, 9, 1.15, 0], [66, 866, 7, 1.35, 1], [1018, 936, -8, 1.3, 1], [176, 1792, -9, 1.2, 0], [904, 1796, 9, 1.2, 0]],
  },
};
const POP = { f: 4.4, z: 0.42, s0: [0.5, 0.8] };        // sticker pop: first / later
const SLAP = { f: 3.8, z: 0.34, s0: 1.16 };             // last sticker: slap down (contact ≈ +0.085s)
const TAPES = ['#F4D27A', '#F2B28C', '#E9D6AE', '#F5C6A0', '#EFD9A0', '#F0BE9A'];

function layoutName(p, env) { return p.layout === 'auto' ? (env.H / env.W > 1.6 ? '9x16' : '3x4') : p.layout; }

/* ---------------- text units + timing ---------------- */
const PUNCT = /[\s　-〿＀-／：-＠!-/:-@[-`{-~·—…]/g;
const norm = s => s.normalize('NFKC').toLowerCase().replace(PUNCT, '');
function units(str) {                      // CJK chars one by one, latin/digit runs kept together
  const out = []; let run = '';
  for (const ch of [...str]) {
    if (/[A-Za-z0-9]/.test(ch)) { run += ch; continue; }
    if (run) { out.push(run); run = ''; }
    out.push(ch);
  }
  if (run) out.push(run);
  return out;
}
/* match display units to spoken characters in order -> reveal time per unit (null = unmatched) */
function matchTimes(unitLists, words) {
  const stream = [];
  for (const w of words || []) {
    const n = [...norm(String(w.w || ''))];
    if (!n.length) continue;
    const d = (w.e - w.s) / n.length;
    n.forEach((ch, k) => stream.push({ ch, t: w.s + k * d }));
  }
  let j = 0;
  return unitLists.map(list => list.map(u => {
    const n = [...norm(u)];
    if (!n.length || !stream.length) return null;
    let k = j;
    while (k < stream.length && stream[k].ch !== n[0]) k++;
    if (k >= stream.length) return null;
    j = k + n.length;
    return stream[k].t;
  }));
}
function hiMask(list, his) {            // unit index -> highlighted?
  const s = list.join(''); const mask = new Array(list.length).fill(false);
  const starts = []; let acc = 0; for (const u of list) { starts.push(acc); acc += u.length; }
  for (const h of his || []) {
    if (!h) continue;
    let k = s.indexOf(h);
    while (k >= 0) { for (let i = 0; i < list.length; i++) if (starts[i] < k + h.length && starts[i] + list[i].length > k) mask[i] = true; k = s.indexOf(h, k + h.length); }
  }
  return mask;
}

/* ---------------- shared layout (draw + bbox) ---------------- */
const MEASURE = (typeof OffscreenCanvas !== 'undefined') ? new OffscreenCanvas(8, 8).getContext('2d') : null;
function textLine(list, font, track) {
  const m = MEASURE; m.font = font;
  const ws = list.map(u => m.measureText(u).width);
  const width = ws.reduce((a, b) => a + b, 0) + track * Math.max(0, list.length - 1);
  const xs = []; let x = -width / 2;
  for (const w of ws) { xs.push(x + w / 2); x += w + track; }
  return { ws, xs, width };
}
function plan(p, tk, env) {
  const s = env.s, L = LAYOUTS[layoutName(p, env)];
  const yS = env.H / (L === LAYOUTS['9x16'] ? 1920 : 1440);
  const beats = (Array.isArray(p.beats) && p.beats.length ? p.beats : [0]).map(Number);
  const titleU = [...units(p.prefix || ''), ...units(p.name || '')];
  const nPre = units(p.prefix || '').length;
  const subU = p.sub ? units(p.sub) : [];
  const [tT, tS] = matchTimes([titleU, subU], p.words);
  const t0 = beats[0], t1 = beats[1] ?? beats[0] + 0.5;
  let last = t0;
  const titleT = titleU.map((u, i) => { const v = tT[i] ?? last + (i ? 0.05 : 0); last = v; return Math.max(0, v - 0.03); });
  const firstSub = tS.find(v => v !== null && v !== undefined);
  const subStart = (firstSub ?? t1) - 0.03;
  let lastS = subStart;
  const subT = subU.map((u, i) => {
    if (p.sub_mode === 'sync') { const v = tS[i] ?? lastS + 0.06; lastS = v; return Math.max(0, v - 0.03); }
    return subStart + i * 0.035;
  });
  const titleFont = tokFont(tk, 'sans', L.title.size * s, 900);
  const subFont = tokFont(tk, 'sans', L.sub.size * s, 700);
  const TL = textLine(titleU, titleFont, L.title.track * s);
  const SL = textLine(subU, subFont, L.sub.track * s);
  return { s, L, yS, beats, titleU, nPre, subU, titleT, subT, titleFont, subFont, TL, SL,
    subHi: hiMask(subU, p.sub_hi), cx: env.W / 2,
    titleY: L.title.cy * yS, subY: L.sub.cy * yS, tsize: L.title.size * s, ssize: L.sub.size * s };
}

/* global push for parallax: layer at depth d scales by z^d around the frame centre */
function push(t, env, p) { return 1 + 0.03 * clamp(p.drift) * E.sineInOut(t / Math.max(0.5, env.dur)); }
function applyDepth(ctx, env, z, d) { const k = Math.pow(z, d); ctx.translate(env.W / 2, env.H / 2); ctx.scale(k, k); ctx.translate(-env.W / 2, -env.H / 2); }

/* ---------------- paper, dots, grain (cached per canvas + params) ---------------- */
const CACHE = new Map();
function paperTex(env, p) {
  const key = `paper|${env.W}x${env.H}|${p.paper}|${p.dot}|${p.seed}`;
  if (CACHE.has(key)) return CACHE.get(key);
  const s = env.s, M = Math.round(env.W * 0.06);
  const c = mkCanvas(env.W + 2 * M, env.H + 2 * M), x = c.getContext('2d');
  const rng = mulberry32(hashU(p.seed * 7919 + 17));
  x.fillStyle = p.paper; x.fillRect(0, 0, c.width, c.height);
  // low-frequency mottling (fbm on a coarse grid, smoothly upscaled)
  const gw = 64, gh = Math.round(64 * c.height / c.width);
  const g = mkCanvas(gw, gh), gx = g.getContext('2d'), id = gx.createImageData(gw, gh);
  for (let yy = 0; yy < gh; yy++) for (let xx = 0; xx < gw; xx++) {
    const n = Noise.fbm(xx * 0.11 + p.seed * 3.1, yy * 0.11 - p.seed, 4);
    const o = (yy * gw + xx) * 4, v = n > 0 ? 255 : 90;
    id.data[o] = v; id.data[o + 1] = n > 0 ? 250 : 70; id.data[o + 2] = n > 0 ? 240 : 40; id.data[o + 3] = Math.round(clamp(Math.abs(n) * 0.55) * 255 * 0.16);
  }
  gx.putImageData(id, 0, 0);
  x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high';
  x.drawImage(g, 0, 0, c.width, c.height);
  // fibres
  x.lineCap = 'round';
  const nF = Math.round(c.width * c.height / 900);
  for (let i = 0; i < nF; i++) {
    const px = rng() * c.width, py = rng() * c.height, len = (5 + rng() * 20) * s, a = rng() * Math.PI;
    const dark = rng() < 0.55;
    x.strokeStyle = dark ? `rgba(122,96,62,${0.035 + rng() * 0.05})` : `rgba(255,253,246,${0.08 + rng() * 0.12})`;
    x.lineWidth = (0.5 + rng() * 0.9) * s;
    x.beginPath(); x.moveTo(px, py);
    x.quadraticCurveTo(px + Math.cos(a) * len * 0.5 + (rng() - 0.5) * 4 * s, py + Math.sin(a) * len * 0.5 + (rng() - 0.5) * 4 * s, px + Math.cos(a) * len, py + Math.sin(a) * len);
    x.stroke();
  }
  // specks
  for (let i = 0; i < nF / 5; i++) {
    x.fillStyle = `rgba(96,72,44,${0.05 + rng() * 0.12})`;
    x.beginPath(); x.arc(rng() * c.width, rng() * c.height, (0.4 + rng() * 0.9) * s, 0, TAU); x.fill();
  }
  // dot grid, centred on the frame centre
  const S = 36 * s, r = 1.7 * s;
  x.fillStyle = p.dot;
  const ox = (c.width / 2) % S, oy = (c.height / 2) % S;
  for (let yy = oy; yy < c.height; yy += S) for (let xx = ox; xx < c.width; xx += S) { x.beginPath(); x.arc(xx, yy, r, 0, TAU); x.fill(); }
  // soft light in the upper middle, warm falloff to the edges
  const gr = x.createRadialGradient(c.width / 2, c.height * 0.42, 0, c.width / 2, c.height * 0.46, Math.hypot(c.width, c.height) * 0.62);
  gr.addColorStop(0, 'rgba(255,252,244,0.30)'); gr.addColorStop(0.55, 'rgba(255,250,240,0)'); gr.addColorStop(1, 'rgba(120,86,48,0.16)');
  x.fillStyle = gr; x.fillRect(0, 0, c.width, c.height);
  const out = { c, M };
  CACHE.set(key, out);
  return out;
}
function grainTiles(seed) {
  const key = 'grain|' + seed;
  if (CACHE.has(key)) return CACHE.get(key);
  const rng = mulberry32(hashU(seed * 104729 + 5)), N = 256, tiles = [];
  for (let k = 0; k < 4; k++) {
    const c = mkCanvas(N, N), x = c.getContext('2d'), id = x.createImageData(N, N);
    for (let i = 0; i < N * N; i++) { const v = clamp(128 + gaussR(rng) * 40, 0, 255); id.data[4 * i] = v; id.data[4 * i + 1] = v; id.data[4 * i + 2] = v; id.data[4 * i + 3] = 255; }
    x.putImageData(id, 0, 0); tiles.push(c);
  }
  CACHE.set(key, tiles);
  return tiles;
}
function drawGrain(ctx, env, p) {
  if (!(p.grain > 0)) return;
  const tiles = grainTiles(p.seed), f = Math.floor(env.t * env.fps + 1e-6);
  const h = hashU(f * 2654435761 + p.seed);
  const pat = ctx.createPattern(tiles[h & 3], 'repeat');
  pat.setTransform(new DOMMatrix().translate((h >>> 3) & 255, (h >>> 11) & 255));
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = clamp(0.2 * p.grain);
  ctx.fillStyle = pat; ctx.fillRect(0, 0, env.W, env.H);
  ctx.restore();
}

/* ---------------- cover cards ---------------- */
function cardGeom(i, t, p, P, env) {
  const L = P.L, slot = L.slots[i], s = P.s, yS = P.yS;
  const wi = L.card * s, hi = wi * 4 / 3, b = 7 * s;
  let cx = slot[0] * s, cy = slot[1] * yS;
  let rot = slot[2] * DEG;
  const dx = cx - env.W / 2, dy = cy - env.H / 2, dn = Math.hypot(dx, dy) || 1, ux = dx / dn, uy = dy / dn;
  // entrance: corner cards settle from t=0, side cards slide in on beats[1]
  const tIn = slot[4] ? (P.beats[1] ?? 0.8) - 0.02 : 0.03 * i;
  const e = slot[4] ? spring(t - tIn, 2.3, 0.62) : spring(t - tIn + 0.06, 2.6, 0.55);
  const off = (slot[4] ? 300 : 70) * s * (1 - e);
  cx += ux * off; cy += uy * off; rot += (slot[4] ? 14 : 7) * DEG * (1 - e) * Math.sign(slot[2] || 1);
  // kick on every later beat (a small shove outward), and drift
  let kick = 0;
  for (let k = 1; k < P.beats.length; k++) kick += springKick(t - P.beats[k] - 0.06, 3.0, 0.35);
  cx += ux * 7 * s * kick; cy += uy * 7 * s * kick;
  const dr = clamp(p.drift, 0, 3), sd = hashU(p.seed * 31 + i * 101) % 997;
  cx += Noise.n1(t * 0.45, sd) * 7 * s * dr; cy += Noise.n1(t * 0.4, sd + 40) * 6 * s * dr;
  rot += Noise.n1(t * 0.35, sd + 80) * 0.9 * DEG * dr;
  const visible = t >= tIn - 1e-6 || !slot[4];
  return { cx, cy, rot, wi, hi, b, depth: slot[3], visible };
}
function tapeKind(key, p) {
  const o = (p.cover_tape || {})[typeof key === 'string' ? key : ''];
  if (o) return o;
  const m = COVER_META.get(key);
  return m && m.grid_ui ? 'tr' : 'top';
}
function drawTape(ctx, x, y, len, wid, ang, col, seed) {
  const rng = mulberry32(hashU(seed));
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
  const L2 = len / 2, W2 = wid / 2, teeth = 5;
  ctx.beginPath(); ctx.moveTo(-L2, -W2); ctx.lineTo(L2, -W2);
  for (let k = 1; k <= teeth; k++) ctx.lineTo(L2 + (k % 2 ? 1 : -1) * wid * 0.07 * (0.6 + rng()), -W2 + wid * k / teeth);
  ctx.lineTo(-L2, W2);
  for (let k = teeth - 1; k >= 0; k--) ctx.lineTo(-L2 + (k % 2 ? 1 : -1) * wid * 0.07 * (0.6 + rng()), -W2 + wid * k / teeth);
  ctx.closePath();
  ctx.shadowColor = 'rgba(80,55,25,0.16)'; ctx.shadowBlur = wid * 0.18; ctx.shadowOffsetY = wid * 0.05;
  ctx.fillStyle = rgba(col, 0.93); ctx.fill();
  ctx.shadowColor = 'transparent';
  ctx.save(); ctx.clip();
  ctx.globalAlpha = 0.16; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = wid * 0.12;
  for (let k = -len; k < len; k += wid * 0.42) { ctx.beginPath(); ctx.moveTo(k, -W2); ctx.lineTo(k + wid, W2); ctx.stroke(); }
  ctx.globalAlpha = 0.10; ctx.fillStyle = '#6b4a22'; ctx.fillRect(-L2 - 4, W2 - wid * 0.1, len + 8, wid * 0.1);
  ctx.restore();
  ctx.restore();
}
function drawPlaceholder(ctx, x, y, w, h, s) {
  ctx.fillStyle = '#FBF6EC'; ctx.fillRect(x, y, w, h);
  ctx.lineCap = 'round';
  for (let k = 0; k < 7; k++) {
    ctx.strokeStyle = k === 2 || k === 5 ? '#F2D37A' : '#E3D8C4'; ctx.lineWidth = 12 * s;
    const yy = y + h * (0.14 + k * 0.11), len = w * (0.55 + 0.25 * ((k * 37) % 5) / 4);
    ctx.beginPath(); ctx.moveTo(x + w * 0.14, yy); ctx.lineTo(x + w * 0.14 + len * 0.8, yy); ctx.stroke();
  }
}
function drawCard(ctx, i, t, p, P, env, z) {
  const key = (p.covers || [])[i];
  const G = cardGeom(i, t, p, P, env);
  if (!G.visible) return null;
  const s = P.s, W = G.wi + 2 * G.b, H = G.hi + 2 * G.b;
  ctx.save();
  applyDepth(ctx, env, z, G.depth);
  ctx.translate(G.cx, G.cy); ctx.rotate(G.rot);
  ctx.shadowColor = 'rgba(78,52,24,0.24)'; ctx.shadowBlur = 20 * s; ctx.shadowOffsetX = 2 * s; ctx.shadowOffsetY = 9 * s;
  rrect(ctx, -W / 2, -H / 2, W, H, 6 * s); ctx.fillStyle = '#FFFCF6'; ctx.fill();
  ctx.shadowColor = 'transparent';
  const bmp = img(key);
  ctx.save(); rrect(ctx, -G.wi / 2, -G.hi / 2, G.wi, G.hi, 3 * s); ctx.clip();
  if (bmp) { ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high'; ctx.drawImage(bmp, -G.wi / 2, -G.hi / 2, G.wi, G.hi); }
  else drawPlaceholder(ctx, -G.wi / 2, -G.hi / 2, G.wi, G.hi, s);
  ctx.restore();
  ctx.strokeStyle = 'rgba(120,96,64,0.18)'; ctx.lineWidth = 1 * s; rrect(ctx, -W / 2 + 0.5, -H / 2 + 0.5, W - 1, H - 1, 6 * s); ctx.stroke();
  // tape
  const kind = tapeKind(key, p), col = TAPES[(hashU(p.seed * 13 + i * 7) >>> 4) % TAPES.length];
  const tw = 0.17 * G.wi;
  if (kind === 'tr' || kind === 'tl') {
    const d = G.b + 0.071 * G.wi, sx = kind === 'tr' ? 1 : -1;       // covers the play-button spot of grid screenshots
    drawTape(ctx, sx * (W / 2 - d), -H / 2 + d, 0.46 * G.wi, tw, sx * 45 * DEG, col, p.seed * 97 + i);
  } else {
    drawTape(ctx, (hashU(i * 17 + p.seed) % 21 - 10) * 0.004 * G.wi, -H / 2 + 3 * s, 0.44 * G.wi, 0.15 * G.wi, ((hashU(i * 29 + p.seed) % 9) - 4) * DEG, col, p.seed * 97 + i);
  }
  ctx.restore();
  return G;
}

/* ---------------- stickers ---------------- */
function stickerAt(t, p, P) {
  const B = P.beats, n = Math.min(B.length, (p.stickers || []).length);
  let i = -1;
  for (let k = 0; k < n; k++) if (t >= B[k] - 1e-6) i = k;
  if (i < 0) return null;
  const tau = t - B[i], last = i === n - 1 && n > 1;
  let sc, rot, lift;
  const a = 1;                                   // hard swap: the new sticker is opaque from its first frame
  if (last) {
    const e = spring(tau, SLAP.f, SLAP.z);
    sc = SLAP.s0 + (1 - SLAP.s0) * e; rot = -5 * DEG * (1 - e); lift = clamp((sc - 1) / (SLAP.s0 - 1));
  } else {
    const s0 = i === 0 ? POP.s0[0] : POP.s0[1], e = spring(tau, POP.f, POP.z);
    sc = s0 + (1 - s0) * e; rot = (i % 2 ? 4 : -4) * DEG * (1 - spring(tau, 3.0, 0.5)); lift = clamp((sc - 1) / 0.12) * 0.6;
  }
  // after settling: a slow breath so the held sticker is not frozen
  const br = clamp((tau - 0.35) / 0.3);
  sc *= 1 + 0.006 * Math.sin(tau * 2.4) * br; rot += 0.35 * DEG * Math.sin(tau * 1.7 + i) * br;
  return { i, key: p.stickers[i], sc, rot, lift, a, tau };
}
function stickerBox(P, env) {
  const S = P.L.sticker, s = P.s;
  const h = S.h * s, w = h;                        // stickers are ~square (1216 x 1224)
  return { cx: S.cx * s, cy: S.cy * P.yS, w, h };
}

/* ---------------- text ---------------- */
function drawTextLine(ctx, list, xs, cy, font, size, times, t, colors, opt) {
  // two passes (strokes, then fills) so a later unit's white stroke never covers an earlier fill
  const st = [];
  for (let i = 0; i < list.length; i++) {
    const tau = t - times[i];
    if (tau < 0) { st.push(null); continue; }
    const a = clamp(tau / opt.fade);
    const e = spring(tau, opt.f, opt.z);
    const sc = opt.s0 + (1 - opt.s0) * e;
    const dy = (1 - E.expoOut(clamp(tau / opt.rise))) * opt.dy;
    st.push({ a, sc, dy, rot: opt.rot ? opt.rot * (i % 2 ? 1 : -1) * (1 - e) : 0 });
  }
  ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'; ctx.miterLimit = 2;
  for (const pass of ['stroke', 'fill']) {
    for (let i = 0; i < list.length; i++) {
      const S = st[i]; if (!S || S.a <= 0) continue;
      ctx.save(); ctx.globalAlpha = S.a;
      ctx.translate(xs[i], cy + S.dy); ctx.rotate(S.rot); ctx.scale(S.sc, S.sc);
      if (pass === 'stroke') {
        ctx.shadowColor = 'rgba(70,44,18,0.30)'; ctx.shadowBlur = size * 0.16; ctx.shadowOffsetY = size * 0.05;
        ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = size * opt.stroke; ctx.strokeText(list[i], 0, 0);
      } else {
        ctx.fillStyle = colors[i]; ctx.fillText(list[i], 0, 0);
      }
      ctx.restore();
    }
  }
}

/* ---------------- draw ---------------- */
export function draw(ctx, t, p, tk, env) {
  const P = plan(p, tk, env), s = P.s;
  const z = push(t, env, p);
  let outK = 1, outA = 1;
  if (p.out === 'pop') { const o = E.cubicIn(seg(t, env.dur - p.out_dur, env.dur)); outK = 1 - 0.1 * o; outA = 1 - o; }
  // L0 paper
  const pt = paperTex(env, p);
  ctx.save(); applyDepth(ctx, env, z, 0.3);
  ctx.drawImage(pt.c, -pt.M, -pt.M);
  ctx.restore();
  ctx.save();
  if (outK !== 1) { ctx.translate(env.W / 2, env.H / 2); ctx.scale(outK, outK); ctx.translate(-env.W / 2, -env.H / 2); }
  ctx.globalAlpha = outA;
  // L1 cover cards (behind everything else)
  const nC = Math.min((p.covers || []).length, P.L.slots.length);
  for (let i = 0; i < nC; i++) drawCard(ctx, i, t, p, P, env, z);
  // L2 sticker
  const st = stickerAt(t, p, P);
  if (st) {
    const bmp = img(st.key), B = stickerBox(P, env);
    ctx.save(); applyDepth(ctx, env, z, 0.55);
    ctx.globalAlpha = outA * st.a;
    ctx.translate(B.cx, B.cy - 26 * s * st.lift); ctx.rotate(st.rot); ctx.scale(st.sc, st.sc);
    ctx.shadowColor = `rgba(72,46,20,${0.30 - 0.08 * st.lift})`; ctx.shadowBlur = (18 + 26 * st.lift) * s; ctx.shadowOffsetY = (10 + 26 * st.lift) * s;
    if (bmp) {
      const h = B.h, w = h * bmp.width / bmp.height;
      ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(bmp, -w / 2, -h / 2, w, h);
    } else { rrect(ctx, -B.w / 2, -B.h / 2, B.w, B.h, 40 * s); ctx.fillStyle = '#FFFFFF'; ctx.fill(); }
    ctx.restore();
  }
  // L3 title + subtitle
  ctx.save(); applyDepth(ctx, env, z, 0.35);
  const nameC = tokColor(tk, p.name_color), ink = tokColor(tk, p.ink), subC = tokColor(tk, p.sub_color);
  drawTextLine(ctx, P.titleU, P.TL.xs.map(x => P.cx + x), P.titleY, P.titleFont, P.tsize, P.titleT, t,
    P.titleU.map((u, i) => i >= P.nPre ? nameC : ink),
    { fade: 0.05, f: 4.2, z: 0.45, s0: 0.45, rise: 0.22, dy: 26 * s, stroke: 0.15, rot: 5 * DEG });
  if (P.subU.length) {
    drawTextLine(ctx, P.subU, P.SL.xs.map(x => P.cx + x), P.subY, P.subFont, P.ssize, P.subT, t,
      P.subU.map((u, i) => P.subHi[i] ? nameC : subC),
      { fade: 0.08, f: 3.6, z: 0.6, s0: 0.8, rise: 0.25, dy: 16 * s, stroke: 0.2, rot: 0 });
  }
  ctx.restore();
  ctx.restore();
  // L4 unified grain over the whole frame
  drawGrain(ctx, env, p);
}

/* ---------------- bbox (same layout functions as draw) ---------------- */
export function bbox(t, p, tk, env) {
  if (!MEASURE) return [];
  const P = plan(p, tk, env), s = P.s, z = push(t, env, p), out = [];
  const tr = (x, y, d) => { const k = Math.pow(z, d); return [env.W / 2 + (x - env.W / 2) * k, env.H / 2 + (y - env.H / 2) * k, k]; };
  const nC = Math.min((p.covers || []).length, P.L.slots.length);
  for (let i = 0; i < nC; i++) {
    const G = cardGeom(i, t, p, P, env);
    if (!G.visible) continue;
    const W = G.wi + 2 * G.b, H = G.hi + 2 * G.b, c = Math.cos(G.rot), sn = Math.sin(G.rot);
    const pts = [[-W / 2, -H / 2], [W / 2, -H / 2], [W / 2, H / 2], [-W / 2, H / 2]].map(([x, y]) => tr(G.cx + x * c - y * sn, G.cy + x * sn + y * c, G.depth));
    const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]);
    out.push({ kind: 'shape', label: 'card:' + ((p.covers || [])[i] || i), x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys), bleed: true });
  }
  const st = stickerAt(t, p, P);
  if (st) {
    const B = stickerBox(P, env), [x, y, k] = tr(B.cx, B.cy - 26 * s * st.lift, 0.55);
    const w = B.w * st.sc * k, h = B.h * st.sc * k;
    out.push({ kind: 'shape', label: 'sticker:' + st.key, x: x - w / 2, y: y - h / 2, w, h, alpha: st.a });
  }
  const lineBox = (list, L, cy, times, size, label, stroke) => {
    const vis = times.map(v => t >= v);
    if (!vis.some(Boolean)) return;
    const [x0, y0, k] = tr(P.cx + L.xs[0] - L.ws[0] / 2, cy, 0.35);
    const pad = size * stroke / 2;
    out.push({ kind: 'text', label, x: x0 - pad * k, y: y0 - (size * 0.5 + pad) * k, w: (L.width + 2 * pad) * k, h: (size + 2 * pad) * k, font_px: Math.round(size * k) });
  };
  lineBox(P.titleU, P.TL, P.titleY, P.titleT, P.tsize, (p.prefix || '') + (p.name || ''), 0.15);
  if (P.subU.length) lineBox(P.subU, P.SL, P.subY, P.subT, P.ssize, p.sub, 0.2);
  return out;
}

export function mbSamples(t, p, tk, env) {
  const B = Array.isArray(p.beats) ? p.beats : [];
  for (const b of B) { if (t >= b - 0.01 && t < b + 0.09) return 8; if (t >= b && t < b + 0.22) return 4; }
  const b1 = B[1] ?? 0.8;
  if (t >= b1 && t < b1 + 0.35) return 3;
  return t < 0.25 ? 3 : 1;
}

export default { id, role, desc, params, sfx_hints, draw, bbox, mbSamples };
