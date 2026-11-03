'use strict';
/* 天空为什么是蓝的 · Lin-style explainer scene.
   Pure function of time: renderFrame(t) sets every element for output time t (s) and returns the
   host layout (room transform, PiP mapping) plus element boxes for QA. Three layers are captured
   separately by render.py: L_room (host's space, behind him), L_board (full-screen stage), L_front. */

const W = 1080, H = 1920;
const NS = 'http://www.w3.org/2000/svg';
let TL = null;

/* ---------------------------------------------------------------- helpers */
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const seg = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  lin: x => x,
  inCubic: x => x * x * x,
  outCubic: x => 1 - Math.pow(1 - x, 3),
  outQuint: x => 1 - Math.pow(1 - x, 5),
  inOutCubic: x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
  inOutSine: x => -(Math.cos(Math.PI * x) - 1) / 2,
  outBack: (x, s = 1.70158) => 1 + (s + 1) * Math.pow(x - 1, 3) + s * Math.pow(x - 1, 2),
};
/* damped spring 0 -> 1 (t in seconds since start) */
function spring(t, freq = 3.2, damp = 0.42) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * freq, z = damp, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z * w / wd) * Math.sin(wd * t));
}
function mulberry32(a) { a >>>= 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function S(parent, tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e); return e;
}
function D_(parent, cls = '', style = '', html = '') {
  const e = document.createElement('div');
  if (cls) e.className = cls;
  if (style) e.style.cssText = style;
  if (html) e.innerHTML = html;
  parent.appendChild(e); return e;
}
const $ = id => document.getElementById(id);
function wavePath(x0, y0, x1, y1, lam, amp, phase = 0, taper = 0) {
  const dx = x1 - x0, dy = y1 - y0, L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, nx = -uy, ny = ux;
  let d = '';
  const n = Math.max(16, Math.ceil(L / 3));
  for (let i = 0; i <= n; i++) {
    const s = (i / n) * L;
    let A = amp;
    if (taper > 0) A *= Math.min(1, s / taper, (L - s) / taper);
    const o = A * Math.sin(2 * Math.PI * (s / lam + phase));
    d += (i ? 'L' : 'M') + (x0 + ux * s + nx * o).toFixed(1) + ' ' + (y0 + uy * s + ny * o).toFixed(1);
  }
  return d;
}
function specRGB(nm) {             // approximate sRGB of a spectral colour
  let r = 0, g = 0, b = 0;
  if (nm < 440) { r = -(nm - 440) / 60; b = 1; } else if (nm < 490) { g = (nm - 440) / 50; b = 1; }
  else if (nm < 510) { g = 1; b = -(nm - 510) / 20; } else if (nm < 580) { r = (nm - 510) / 70; g = 1; }
  else if (nm < 645) { r = 1; g = -(nm - 645) / 65; } else { r = 1; }
  let f = 1; if (nm < 420) f = 0.35 + 0.65 * (nm - 380) / 40; else if (nm > 700) f = 0.35 + 0.65 * (780 - nm) / 80;
  const k = v => Math.round(255 * Math.pow(clamp(v * f), 0.8));
  return `rgb(${k(r)},${k(g)},${k(b)})`;
}
function setT(el, tf, op) { el.style.transform = tf; if (op !== undefined) el.style.opacity = op.toFixed(4); }
/* pop-in / hold / pop-out envelope for key words: returns {a (opacity), s (scale), r (rot deg), y (px)} */
function popEnv(t, t0, t1, o = {}) {
  const inDur = o.inDur ?? 0.34, outDur = o.outDur ?? 0.22;
  if (t < t0 - 0.02 || t > t1 + outDur) return { a: 0, s: 0.6, r: 0, y: 0 };
  const u = t - t0;
  let s = lerp(o.from ?? 0.35, 1, spring(u, o.freq ?? 3.0, o.damp ?? 0.38));
  let a = clamp(u / 0.08);
  let r = (o.rot ?? 0) * (1 - spring(u, 2.6, 0.5));
  let y = (o.dy ?? 0) * (1 - E.outCubic(seg(u, 0, inDur)));
  if (t > t1) { const v = seg(t, t1, t1 + outDur); a *= 1 - E.inCubic(v); s *= 1 - 0.25 * E.inCubic(v); y -= 30 * E.inCubic(v); }
  if (o.shake && u > 0) r += o.shake * Math.exp(-u * 6) * Math.sin(u * 48);
  return { a, s, r, y };
}

/* glossy props (from the approved style frame) */
function sun(sv, x, y, r, grad = 'url(#sunG)') {
  const g = S(sv, 'g');
  const halo = S(g, 'circle', { cx: x, cy: y, r: r * 2.4, fill: '#FFD27A', opacity: .22, filter: 'url(#soft14)' });
  const body = S(g, 'circle', { cx: x, cy: y, r, fill: grad });
  const hl = S(g, 'ellipse', { cx: x - r * .32, cy: y - r * .38, rx: r * .32, ry: r * .2, fill: '#fff', opacity: .7 });
  g._set = (X, Y, R, op = 1) => {
    halo.setAttribute('cx', X); halo.setAttribute('cy', Y); halo.setAttribute('r', R * 2.4);
    body.setAttribute('cx', X); body.setAttribute('cy', Y); body.setAttribute('r', R);
    hl.setAttribute('cx', X - R * .32); hl.setAttribute('cy', Y - R * .38); hl.setAttribute('rx', R * .32); hl.setAttribute('ry', R * .2);
    g.setAttribute('opacity', op);
  };
  return g;
}
function molecule(sv, x, y, r, ang, kind = 'N') {
  const g = S(sv, 'g', { transform: `translate(${x} ${y})` });
  const dx = Math.cos(ang) * r * .82, dy = Math.sin(ang) * r * .82, f = kind === 'N' ? 'url(#molN)' : 'url(#molO)';
  S(g, 'ellipse', { cx: 6, cy: r * 1.35, rx: r * 1.6, ry: r * .3, fill: '#000', opacity: .16, filter: 'url(#soft6)' });
  S(g, 'circle', { cx: -dx, cy: -dy, r, fill: f });
  S(g, 'circle', { cx: dx, cy: dy, r, fill: f });
  S(g, 'ellipse', { cx: -dx - r * .3, cy: -dy - r * .35, rx: r * .3, ry: r * .18, fill: '#fff', opacity: .8 });
  g._x = x; g._y = y;
  return g;
}
function kick(el) { el.dataset.k = 'txt'; return el; }
function cardEl(parent, cls, x, y, w, h) {
  const c = D_(parent, 'card ' + cls, `left:${x}px;top:${y}px;width:${w}px;height:${h}px`);
  c.innerHTML = `<svg class="noise" width="${w}" height="${h}"><rect width="${w}" height="${h}" filter="url(#noise)"/></svg>` +
    `<div class="dash" style="left:14px;top:14px;right:14px;bottom:14px"></div>`;
  return c;
}
function kwEl(parent, html, x, y, style = '') {
  const k = D_(parent, 'kw', `left:${x}px;top:${y}px;${style}`, html);
  k.dataset.k = 'txt';
  return k;
}

/* ---------------------------------------------------------------- build */
const R = {};   // element registry
function build() {
  const rng = mulberry32(7);
  /* ===== ROOM layer ===== */
  const rs = $('roomSvg');
  // sky wavelets (scattered blue light filling the sky)
  R.skyG = S(rs, 'g', { opacity: 0 });
  R.skySun = S(R.skyG, 'circle', { cx: 960, cy: 120, r: 230, fill: '#FFF6DA', opacity: .26, filter: 'url(#soft30)' });
  R.wavelets = [];
  for (let i = 0; i < 64; i++) {
    let x = 60 + rng() * 960, y = 120 + rng() * 1250; const a = rng() * Math.PI * 2, L = 34 + rng() * 40;
    if (x > 200 && x < 920 && y > 640) { y = 120 + rng() * 500; }
    const c = ['#EAF4FF', '#BFDcFF', '#8FC0FF', '#6AA7FF'][Math.floor(rng() * 4)];
    const p = S(R.skyG, 'path', { d: wavePath(-L / 2, 0, L / 2, 0, 13, 4.2, 0, 8), fill: 'none', stroke: c, 'stroke-width': 3.2, 'stroke-linecap': 'round', opacity: 0 });
    R.wavelets.push({ p, x, y, a, L, d: rng(), sp: 0.4 + rng() * 0.8 });
  }
  // sunset: low sun behind his shoulder + lit clouds
  R.duskG = S(rs, 'g', { opacity: 0 });
  S(R.duskG, 'circle', { cx: 905, cy: 1150, r: 330, fill: '#FFB060', opacity: .55, filter: 'url(#soft30)' });
  R.duskSun = S(R.duskG, 'circle', { cx: 905, cy: 1150, r: 120, fill: 'url(#sunR)' });
  R.clouds = [];
  const crng = mulberry32(21);
  [[190, 560, 1.0], [700, 470, 1.15], [930, 700, .8], [420, 790, .85], [110, 930, .7], [640, 980, .6]].forEach(([x, y, sc], i) => {
    const g = S(R.duskG, 'g', { filter: 'url(#soft3)' });
    const puffs = [];
    for (let j = 0; j < 7; j++) puffs.push([(j - 3) * 34 * sc + (crng() - .5) * 20, -Math.sin(Math.PI * (j + .5) / 7) * 34 * sc - crng() * 16 * sc, (26 + crng() * 26) * sc]);
    puffs.forEach(([px, py, r]) => S(g, 'circle', { cx: px, cy: py, r, fill: '#E9786A', opacity: .95 }));        // shaded body
    puffs.forEach(([px, py, r]) => S(g, 'circle', { cx: px - r * .18, cy: py - r * .22, r: r * .78, fill: '#FFC9A2', opacity: .95 }));   // lit from the low sun
    puffs.forEach(([px, py, r]) => S(g, 'circle', { cx: px - r * .28, cy: py - r * .38, r: r * .42, fill: '#FFF0D8', opacity: .8 }));
    S(g, 'ellipse', { cx: 0, cy: 10 * sc, rx: 150 * sc, ry: 16 * sc, fill: '#C9505A', opacity: .7 });
    R.clouds.push({ g, x, y, sp: 5 + i * 2.5 });
  });
  // bars chart behind the host (blue vs red scattering)
  R.barsG = S(rs, 'g', { opacity: 0 });
  R.barTrackB = S(R.barsG, 'rect', { x: 250, y: 178, width: 720, height: 58, rx: 29, fill: 'rgba(255,255,255,.16)' });
  R.barTrackR = S(R.barsG, 'rect', { x: 250, y: 262, width: 720, height: 58, rx: 29, fill: 'rgba(255,255,255,.16)' });
  R.barB = S(R.barsG, 'rect', { x: 250, y: 178, width: 0, height: 58, rx: 29, fill: 'url(#barB)', filter: 'url(#glowB)' });
  R.barR = S(R.barsG, 'rect', { x: 250, y: 262, width: 0, height: 58, rx: 29, fill: 'url(#barR)' });
  R.barHiB = S(R.barsG, 'rect', { x: 262, y: 186, width: 0, height: 12, rx: 6, fill: '#fff', opacity: .45 });
  R.barHiR = S(R.barsG, 'rect', { x: 262, y: 270, width: 0, height: 12, rx: 6, fill: '#fff', opacity: .45 });
  // title-scene props
  R.propsG = S(rs, 'g');
  R.mols1 = [molecule(R.propsG, 948, 560, 19, -0.5, 'N'), molecule(R.propsG, 730, 185, 13, 0.4, 'O'), molecule(R.propsG, 130, 640, 16, 0.9, 'N')];
  R.bigSun = sun(R.propsG, 905, 250, 64);

  const rc = $('roomCards');
  // title card
  R.cTitle = cardEl(rc, 'blueC', 88, 160, 590, 352);
  R.cTitle.style.transformOrigin = '6.8% 50%';
  R.kTitle = kick(D_(R.cTitle, 'abs en', 'left:44px;top:32px', 'WHY IS THE SKY BLUE?'));
  R.titleTxt = D_(R.cTitle, 'abs t1', 'left:40px;top:106px;line-height:1.32', '天空为什么<br>是<span id="lanChar" style="display:inline-block;transform-origin:50% 70%">蓝</span>的？');
  R.titleTxt.dataset.k = 'txt'; R.titleTxt.dataset.id = 'title';
  R.lanBurst = S(S(D_(R.cTitle, 'abs', 'left:0;top:0;width:590px;height:352px'), 'svg', { width: 590, height: 352 }), 'g', { opacity: 0 });
  // sunlight card
  R.cSun = cardEl(rc, 'creamC', 88, 160, 470, 430);
  R.cSun.style.transformOrigin = '8.1% 50%';
  R.kSun = kick(D_(R.cSun, 'abs en', 'left:40px;top:40px', 'SUNLIGHT'));
  const sh = D_(R.cSun, 'abs cardH', 'left:38px;top:94px', '太阳光'); sh.dataset.k = 'txt';
  const lensSv = S(D_(R.cSun, 'abs', 'left:0;top:0;width:470px;height:430px'), 'svg', { width: 470, height: 430 });
  R.lens = buildLens(lensSv, 262, 268, 112);
  R.sunCardSun = sun(lensSv, 70, 190, 30);
  R.sunBeam = S(lensSv, 'path', { d: '', fill: '#FFFFFF', opacity: .95, style: 'filter:drop-shadow(0 0 6px rgba(255,240,200,.95))' });
  R.lensCap = D_(R.cSun, 'abs lbl2', 'left:40px;top:388px;opacity:0', '放大看：各种颜色的光混在一起'); R.lensCap.dataset.k = 'txt';
  // props above the cards (still behind the host)
  const rs2 = S(rc, 'svg', { width: W, height: H, style: 'position:absolute;left:0;top:0' });
  R.flySun = sun(rs2, 905, 250, 64);

  const rk = $('roomKW');
  R.kwLanguang = kwEl(rk, '蓝光', 304, 188, 'font-size:236px;color:#F4FAFF;text-shadow:0 0 36px rgba(120,190,255,.95),0 0 90px rgba(80,150,255,.8),0 8px 24px rgba(10,40,120,.6)');
  R.kwWanxia = kwEl(rk, '晚霞', 290, 186, 'font-size:250px;background:linear-gradient(180deg,#FFF3B0 0%,#FFC04D 45%,#FF6A3D 80%,#E0342A 100%);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 30px rgba(255,150,70,.9)) drop-shadow(0 8px 18px rgba(90,20,30,.55))');
  R.barLblB = kwEl(rk, '蓝光', 114, 180, 'font-size:54px;color:#fff;text-shadow:0 2px 10px rgba(20,40,120,.8)');
  R.barLblR = kwEl(rk, '红光', 114, 264, 'font-size:54px;color:#fff;text-shadow:0 2px 10px rgba(120,30,20,.8)');
  R.barLblB.style.transformOrigin = R.barLblR.style.transformOrigin = '0 50%';
  R.chipCheng = kwEl(rk, '<i style="--c:#FF8A2A"></i>橙色', 128, 184, ''); R.chipCheng.className = 'chip'; R.chipCheng.style.background = 'linear-gradient(180deg,#FFA64D,#F2771E)';
  R.chipHong = kwEl(rk, '<i style="--c:#F0442F"></i>红色', 694, 184, ''); R.chipHong.className = 'chip'; R.chipHong.style.background = 'linear-gradient(180deg,#FF6A55,#D83424)';
  R.chipCheng.dataset.k = R.chipHong.dataset.k = 'txt';

  /* ===== BOARD layer ===== */
  const bc = $('boardCards');
  // A1: scattering diagram
  R.cScat = cardEl(bc, 'blueC', 70, 190, 940, 700);
  kick(D_(R.cScat, 'abs en', 'left:44px;top:40px', 'SCATTERING'));
  const h1 = D_(R.cScat, 'abs cardH', 'left:50px;top:80px', '阳光 × 空气分子'); h1.dataset.k = 'txt';
  const scSv = S(D_(R.cScat, 'abs', 'left:0;top:0;width:940px;height:700px'), 'svg', { width: 940, height: 700 });
  buildScatter(scSv);
  R.atmLbl = D_(R.cScat, "abs lbl", "left:730px;top:428px;opacity:0;font-size:32px", '大气层'); R.atmLbl.dataset.k = 'txt';
  R.molLbl = D_(R.cScat, "abs lbl", "left:596px;top:350px;opacity:0;font-size:32px", '空气分子'); R.molLbl.dataset.k = 'txt';
  // A2: the bluer, the stronger
  R.cSpec = cardEl(bc, 'creamC', 70, 190, 940, 700);
  R.cSpec.style.transformOrigin = '4.3% 60%';
  kick(D_(R.cSpec, 'abs en', 'left:44px;top:40px', 'SCATTERING'));
  const h2 = D_(R.cSpec, 'abs cardH', 'left:50px;top:80px', '越偏蓝，散射越厉害'); h2.dataset.k = 'txt';
  const spSv = S(D_(R.cSpec, 'abs', 'left:0;top:0;width:940px;height:700px'), 'svg', { width: 940, height: 700 });
  buildSpectrum(spSv);
  // B: noon vs sunset
  R.goldT = D_(bc, 'abs gold', 'left:540px;top:172px;transform:translateX(-50%);opacity:0', '光要走更远的路'); R.goldT.dataset.k = 'txt';
  R.cNoon = cardEl(bc, 'blueC', 76, 300, 440, 620);
  R.cDusk = cardEl(bc, 'peachC', 568, 300, 440, 620);
  [[R.cNoon, 'NOON', '正午', '路径短', '满天散射开的蓝光'], [R.cDusk, 'SUNSET', '傍晚', '路径长', '蓝光半路散射光，剩下橙红']].forEach(([c, en, zh, a, b]) => {
    D_(c, 'abs en', 'left:36px;top:36px', en);
    const hh = D_(c, 'abs cardH', 'left:34px;top:70px', zh); hh.dataset.k = 'txt';
    const f = D_(c, 'abs lbl2', 'left:36px;top:520px', a + '<br>' + b); f.dataset.k = 'txt';
    c._sv = S(D_(c, 'abs', 'left:0;top:0;width:440px;height:620px'), 'svg', { width: 440, height: 620 });
  });
  buildNoonDusk();
  // board key words (lower-left panel beside the PiP)
  const bk = $('boardKW');
  R.kwSanshe = kwEl(bk, '散射开', 114, 1046, 'font-size:150px;color:#8EC5FF;text-shadow:0 0 30px rgba(90,160,255,.7)');
  R.kwPianlan = kwEl(bk, '越偏蓝', 114, 1046, 'font-size:150px;color:#6FB0FF;text-shadow:0 0 30px rgba(90,160,255,.6)');
  R.kwLihai = kwEl(bk, '越厉害', 114, 1046, 'font-size:150px;color:#FFFFFF;text-shadow:0 0 26px rgba(255,255,255,.45)');
  R.kwBangwan = kwEl(bk, '傍晚', 114, 1046, 'font-size:160px;background:linear-gradient(180deg,#FFE3A0,#FF9A4A 55%,#E2553A);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 20px rgba(255,140,60,.55))');
  R.kwThick = kwEl(bk, '更厚的大气层', 112, 1070, 'font-size:88px;color:#FFE2B8;text-shadow:0 0 20px rgba(255,170,90,.55)');
  R.kwSanguang = kwEl(bk, '散射光了', 112, 1056, 'font-size:122px;color:#8EC5FF;text-shadow:0 0 24px rgba(90,160,255,.65)');
  R.burstSv = S($('boardSvg'), 'g', { opacity: 0 });
  for (let i = 0; i < 14; i++) S(R.burstSv, 'path', { d: '', stroke: '#8EC5FF', 'stroke-width': 5, 'stroke-linecap': 'round', fill: 'none' });

  /* ===== FRONT layer ===== */
  const fk = $('frontKW');
  R.kwColors = kwEl(fk, '<span style="color:#FF5A4E">各</span><span style="color:#FFB020">种</span><span style="color:#26B36A">颜</span><span style="color:#3C7BFF">色</span>',
    546, 178, 'font-size:104px;filter:drop-shadow(0 0 2px #fff) drop-shadow(0 0 2px #fff) drop-shadow(0 6px 14px rgba(0,0,0,.45))');
  R.kwBeishu = kwEl(fk, '好几倍', 548, 306, 'font-size:140px;color:#FFD60A;filter:drop-shadow(0 0 1.5px #1B2638) drop-shadow(0 0 1.5px #1B2638) drop-shadow(0 6px 14px rgba(0,0,0,.5))');
  R.kwColors.dataset.id = 'kw各种颜色'; R.kwBeishu.dataset.id = 'kw好几倍';
  buildCaptions();
}

function buildLens(sv, cx, cy, Rr) {
  const g = S(sv, 'g');
  const clip = S(S(sv, 'defs'), 'clipPath', { id: 'lensClip' }); S(clip, 'circle', { cx, cy, r: Rr - 8 });
  S(g, 'circle', { cx, cy, r: Rr - 8, fill: '#1E2533' });
  const inner = S(g, 'g', { 'clip-path': 'url(#lensClip)' });
  const nms = [410, 450, 490, 530, 570, 610, 660];
  const waves = nms.map((nm, i) => S(inner, 'path', { d: '', fill: 'none', stroke: specRGB(nm), 'stroke-width': 4, 'stroke-linecap': 'round', opacity: 0, _nm: nm }));
  const white = S(inner, 'rect', { x: cx - Rr, y: cy - 16, width: 2 * Rr, height: 32, fill: '#fff', opacity: 0, filter: 'url(#soft6)' });
  S(g, 'circle', { cx, cy, r: Rr - 8, fill: 'none', stroke: 'rgba(255,255,255,.35)', 'stroke-width': 3 });
  S(g, 'circle', { cx, cy, r: Rr, fill: 'none', stroke: '#2B3342', 'stroke-width': 16 });
  S(g, 'path', { d: `M ${cx + Rr * .7} ${cy + Rr * .7} L ${cx + Rr * 1.12} ${cy + Rr * 1.12}`, stroke: '#2B3342', 'stroke-width': 26, 'stroke-linecap': 'round' });
  S(g, 'ellipse', { cx: cx - 48, cy: cy - 54, rx: 38, ry: 16, fill: '#fff', opacity: .16, transform: `rotate(-35 ${cx - 48} ${cy - 54})` });
  return { cx, cy, Rr, waves, nms, white };
}

/* A1 geometry (card-local): Earth arc + atmosphere shell, sun top-left, beam into a molecule, scatter burst */
function buildScatter(sv) {
  const cx = 470, R0 = 1500, top = 600, h = 180, cy = top + R0;
  const clip = S(S(sv, 'defs'), 'clipPath', { id: 'scClip' }); S(clip, 'rect', { x: 14, y: 14, width: 912, height: 672, rx: 14 });
  const g = S(sv, 'g', { 'clip-path': 'url(#scClip)' });
  R.scShell = S(g, 'circle', { cx, cy, r: R0 + h, fill: 'rgba(110,165,235,.34)' });
  S(g, 'circle', { cx, cy, r: R0 + h, fill: 'none', stroke: 'rgba(70,120,200,.5)', 'stroke-width': 2, 'stroke-dasharray': '8 8' });
  S(g, 'circle', { cx, cy, r: R0, fill: '#7E8FA6' });
  S(g, 'circle', { cx, cy, r: R0 - 14, fill: '#91A2B8' });
  R.scSun = sun(g, 118, 214, 44);
  R.scHit = [492, 498];
  R.scBeam = S(g, 'path', { d: '', stroke: '#FFFFFF', 'stroke-width': 9, 'stroke-linecap': 'round', fill: 'none', style: 'filter:drop-shadow(0 0 6px rgba(255,245,210,.95))' });
  R.scBeam2 = S(g, 'path', { d: '', stroke: '#FFF3D6', 'stroke-width': 6, 'stroke-linecap': 'round', fill: 'none', opacity: 0 });
  R.scMols = [[492, 498, 22, -0.4, 'N'], [300, 540, 18, 0.7, 'O'], [680, 470, 20, 0.3, 'N'], [820, 548, 17, -0.9, 'N'], [150, 575, 16, 0.2, 'O']]
    .map(([x, y, r, a, k]) => molecule(g, x, y, r, a, k));
  R.scWaves = [];
  const rng = mulberry32(11);
  for (let i = 0; i < 16; i++) {
    const ang = -Math.PI + (i / 16) * 2 * Math.PI + (rng() - .5) * .25;
    const blue = i % 4 !== 3;
    const col = blue ? ['#2F6BD8', '#3E86F0', '#1F4FB5'][i % 3] : (i % 8 === 3 ? '#35B36B' : '#E5533D');
    const p = S(g, 'path', { d: '', fill: 'none', stroke: col, 'stroke-width': blue ? 4.2 : 3, 'stroke-linecap': 'round', opacity: 0 });
    R.scWaves.push({ p, ang, blue, len: blue ? 120 + rng() * 60 : 58 + rng() * 20, lam: blue ? 14 : 24 });
  }
}

/* A2: scattering strength vs colour, curve ∝ λ^-4 (no numbers on screen) */
function buildSpectrum(sv) {
  const x0 = 110, x1 = 850, yb = 560, yt = 210;
  const X = nm => x0 + (nm - 400) / 300 * (x1 - x0);
  const Y = nm => yb - (yb - yt) * Math.pow(400 / nm, 4);
  const g = S(sv, 'g');
  // axes
  S(g, 'path', { d: `M ${x0} ${yt - 30} L ${x0} ${yb} L ${x1 + 26} ${yb}`, stroke: '#1B2638', 'stroke-width': 3, fill: 'none' });
  S(g, 'path', { d: `M ${x0 - 8} ${yt - 22} L ${x0} ${yt - 36} L ${x0 + 8} ${yt - 22}`, stroke: '#1B2638', 'stroke-width': 3, fill: 'none' });
  R.spYlbl = S(g, 'text', { x: x0 + 18, y: yt - 12, style: 'font:700 28px SHS;fill:#1B2638', 'data-k': 'txt' }, '散射强度');
  // spectrum strip under the axis
  const stripG = S(g, 'g');
  for (let nm = 400; nm < 700; nm += 3) S(stripG, 'rect', { x: X(nm), y: yb + 12, width: X(nm + 3) - X(nm) + .6, height: 34, fill: specRGB(nm) });
  const names = [['紫', 410], ['蓝', 460], ['青', 495], ['绿', 530], ['黄', 575], ['橙', 610], ['红', 670]];
  names.forEach(([c, nm]) => S(g, 'text', { x: X(nm), y: yb + 100, 'text-anchor': 'middle', style: 'font:700 27px SHS;fill:#3A4458', 'data-k': 'txt' }, c));
  // area under the curve as spectral hairlines, then the curve
  R.spFill = S(g, 'g');
  R.spLines = [];
  for (let nm = 400; nm <= 700; nm += 6) {
    const l = S(R.spFill, 'line', { x1: X(nm), x2: X(nm), y1: yb, y2: yb, stroke: specRGB(nm), 'stroke-width': 3.2, opacity: .75 });
    R.spLines.push({ l, nm, y: Y(nm) });
  }
  let d = '';
  for (let nm = 700; nm >= 400; nm -= 2) d += (d ? 'L' : 'M') + X(nm).toFixed(1) + ' ' + Y(nm).toFixed(1);
  R.spCurve = S(g, 'path', { d, stroke: '#1B2638', 'stroke-width': 5, fill: 'none', 'stroke-linecap': 'round' });
  R.spCurveLen = R.spCurve.getTotalLength();
  R.spHot = S(g, 'circle', { cx: X(412), cy: Y(412), r: 24, fill: '#7FA8FF', opacity: 0, filter: 'url(#soft6)' });
  R.spDot = S(g, 'circle', { cx: X(700), cy: Y(700), r: 10, fill: '#fff', stroke: '#1B2638', 'stroke-width': 4, opacity: 0 });
  R.spUp = S(g, 'path', { d: `M ${X(412) + 46} ${Y(412) + 70} L ${X(412) + 46} ${Y(412) + 4} M ${X(412) + 30} ${Y(412) + 22} L ${X(412) + 46} ${Y(412) + 4} L ${X(412) + 62} ${Y(412) + 22}`,
    stroke: '#2F6BD8', 'stroke-width': 7, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity: 0 });
  // "越偏蓝" arrow along the strip, pointing to the blue end
  R.spArrow = S(g, 'path', { d: '', stroke: '#2F6BD8', 'stroke-width': 7, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity: 0 });
  R.spX = X; R.spY = Y; R.spYb = yb;
}

function earth(sv, cx, topY, Rr, h, id) {
  const cy = topY + Rr;
  const clip = S(S(sv, 'defs'), 'clipPath', { id }); S(clip, 'rect', { x: 14, y: 140, width: 412, height: 360, rx: 12 });
  const g = S(sv, 'g', { 'clip-path': `url(#${id})` });
  const shell = S(g, 'circle', { cx, cy, r: Rr + h, fill: 'rgba(120,170,235,.30)' });
  S(g, 'circle', { cx, cy, r: Rr + h, fill: 'none', stroke: 'rgba(80,130,200,.45)', 'stroke-width': 1.5, 'stroke-dasharray': '6 6' });
  S(g, 'circle', { cx, cy, r: Rr, fill: '#7E8FA6' });
  S(g, 'circle', { cx, cy, r: Rr - 10, fill: '#8FA0B6' });
  const pin = S(g, 'g');
  S(pin, 'path', { d: `M ${cx} ${topY} l -9 -22 a 11 11 0 1 1 18 0 z`, fill: '#1B2638' });
  S(pin, 'circle', { cx, cy: topY - 29, r: 4.5, fill: '#fff' });
  return { g, shell, pin };
}
function buildNoonDusk() {
  const Rr = 380, h = 70, cx = 220, topY = 400;
  // noon: sun overhead, short vertical path
  const n = R.cNoon._sv, eN = earth(n, cx, topY, Rr, h, 'ccN');
  R.nSun = sun(n, cx, 196, 24);
  R.nBeam = S(eN.g, 'line', { x1: cx, y1: 222, x2: cx, y2: 222, stroke: '#FFFFFF', 'stroke-width': 7, 'stroke-linecap': 'round', style: 'filter:drop-shadow(0 0 5px rgba(255,245,210,.95))' });
  R.nTicks = [[cx, topY - 56, -2.6], [cx, topY - 42, -3.4], [cx, topY - 62, -0.7], [cx, topY - 28, 2.8], [cx, topY - 48, 0.3]].map(([x, y, a]) => {
    const ux = Math.cos(a), uy = Math.sin(a);
    return S(eN.g, 'path', { d: wavePath(x + ux * 8, y + uy * 8, x + ux * 40, y + uy * 40, 9, 3.2, 0), fill: 'none', stroke: '#2F6BD8', 'stroke-width': 2.6, 'stroke-linecap': 'round', opacity: 0 });
  });
  R.nBr = S(eN.g, 'path', { d: `M ${cx + 26} ${topY - h} l 8 0 l 0 ${h - 4} l -8 0`, fill: 'none', stroke: '#1B2638', 'stroke-width': 2, opacity: 0 });
  R.nLbl = S(n, 'text', { x: cx + 44, y: topY - h / 2 + 8, style: 'font:700 28px SHS;fill:#1B2638', opacity: 0, 'data-k': 'txt' }, '短');
  // sunset: sun on the horizon, tangent path through a long stretch of air
  const d = R.cDusk._sv, ox = cx + 110, eD = earth(d, ox, topY, Rr, h, 'ccD');
  R.dShell = eD.shell; R.dPin = eD.pin;
  const chord = Math.sqrt((Rr + h) ** 2 - Rr ** 2), x0 = ox - chord;
  R.dGeo = { x0, ox, y: topY - 12, chord };
  R.dSun = sun(d, x0 - 6, topY - 14, 23);
  const grad = S(S(d, 'defs'), 'linearGradient', { id: 'duskG', x1: x0, y1: 0, x2: ox, y2: 0, gradientUnits: 'userSpaceOnUse' });
  [[0, '#FFFFFF'], [.35, '#FFE9A8'], [.68, '#FFB25C'], [1, '#F2552E']].forEach(([o, c]) => S(grad, 'stop', { offset: o, 'stop-color': c }));
  R.dBeamW = S(eD.g, 'line', { x1: x0 + 14, y1: topY - 12, x2: x0 + 14, y2: topY - 12, stroke: '#FFFFFF', 'stroke-width': 7, 'stroke-linecap': 'round', style: 'filter:drop-shadow(0 0 5px rgba(255,235,200,.9))' });
  R.dBeamC = S(eD.g, 'line', { x1: x0 + 14, y1: topY - 12, x2: ox - 14, y2: topY - 12, stroke: 'url(#duskG)', 'stroke-width': 7, 'stroke-linecap': 'round', opacity: 0, style: 'filter:drop-shadow(0 0 5px rgba(255,190,140,.9))' });
  R.dTicks = [];
  for (let i = 0; i < 6; i++) {
    const tt = (i + .5) / 6, x = lerp(x0 + 26, ox - 40, tt), a = i % 2 ? -1.95 : -1.2, ux = Math.cos(a), uy = Math.sin(a), y = topY - 12;
    R.dTicks.push(S(eD.g, 'path', { d: wavePath(x + ux * 8, y + uy * 8, x + ux * 36, y + uy * 36, 9, 3.2, 0), fill: 'none', stroke: '#2F6BD8', 'stroke-width': 2.6, 'stroke-linecap': 'round', opacity: 0 }));
  }
  R.dBr = S(eD.g, 'path', { d: `M ${x0 + 14} ${topY + 6} l 0 8 l ${chord - 28} 0 l 0 -8`, fill: 'none', stroke: '#1B2638', 'stroke-width': 2, opacity: 0 });
  R.dLbl = S(d, 'text', { x: (x0 + ox) / 2 - 12, y: topY + 46, style: 'font:700 28px SHS;fill:#1B2638', opacity: 0, 'data-k': 'txt' }, '长');
  R.dGlow = S(d, 'circle', { cx: ox, cy: topY - 29, r: 26, fill: '#FF8A3D', opacity: 0, filter: 'url(#soft6)' });
}

/* ---------------------------------------------------------------- captions (C: paper label) */
function buildCaptions() {
  const cap = $('cap');
  R.caps = TL.captions.map((c, i) => {
    const wrap = D_(cap, '', 'position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:0');
    const strip = D_(wrap, 'capstrip');
    let html = '', rest = c.text;
    const marks = [];
    // wrap key substrings in <b>
    const parts = [];
    let idx = 0;
    const keys = c.key.map((k, j) => ({ k, pos: c.text.indexOf(k), kt: c.kt[j] })).filter(o => o.pos >= 0).sort((a, b) => a.pos - b.pos);
    keys.forEach(o => { if (o.pos > idx) parts.push({ s: c.text.slice(idx, o.pos) }); parts.push({ s: o.k, key: true, kt: o.kt }); idx = o.pos + o.k.length; });
    if (idx < c.text.length) parts.push({ s: c.text.slice(idx) });
    const txt = D_(wrap, 'captext');
    txt.innerHTML = parts.map((p, j) => p.key ? `<b data-j="${j}">${p.s}</b>` : `<span>${p.s}</span>`).join('');
    txt.dataset.k = 'txt'; txt.dataset.id = 'cap' + i; txt.dataset.cap = '1';
    return { c, wrap, strip, txt, parts, marks };
  });
}
function layoutCaptions() {
  R.caps.forEach(o => {
    const w = o.txt.getBoundingClientRect().width;
    const x = Math.round((W - w) / 2);
    o.txt.style.left = x + 'px';
    o.strip.style.left = (x - 30) + 'px'; o.strip.style.width = (w + 60) + 'px';
    o.txt.querySelectorAll('b').forEach(b => {
      const r = b.getBoundingClientRect();
      const j = +b.dataset.j;
      const m = D_(o.wrap, 'mark', `left:${r.left - 6}px;top:${1433 + 28}px;width:${r.width + 12}px;transform-origin:0 50%;transform:scaleX(0)`);
      o.wrap.insertBefore(m, o.txt);
      o.marks.push({ m, kt: o.parts[j].kt });
    });
  });
}

/* ---------------------------------------------------------------- per-frame */
function roomD(t) {
  const k = TL.room_D;
  if (t <= k[0][0]) return k[0][1];
  for (let i = 1; i < k.length; i++) if (t <= k[i][0]) return lerp(k[i - 1][1], k[i][1], E.inOutCubic(seg(t, k[i - 1][0], k[i][0])));
  return k[k.length - 1][1];
}
function roomS(t) {
  const B = TL.beats;
  let s = 1;
  s += 0.03 * E.outCubic(seg(t, B.beishu - 0.05, B.beishu + 0.25)) * (1 - E.inOutCubic(seg(t, B.bars_out, B.bars_out + 0.5)));
  s += 0.022 * E.inOutSine(seg(t, 26.3, B.end));
  return s;
}
function pipP(t) {
  for (const [a, b, c, d] of TL.pip.segments) {
    if (t >= a && t < b) return E.inOutCubic(seg(t, a, b));
    if (t >= b && t < c) return 1;
    if (t >= c && t < d) return 1 - E.inOutCubic(seg(t, c, d));
  }
  return 0;
}
function vis(t, a, b) { return t >= a && t <= b; }

function renderFrame(t) {
  const B = TL.beats;
  const Dv = roomD(t), sv = roomS(t);
  /* ---------- ROOM: plate follows the host transform exactly */
  $('plate').style.transform = `translate(0px, ${Dv.toFixed(3)}px) scale(${sv.toFixed(5)})`;
  const skyA = E.inOutCubic(seg(t, B.sky, B.sky + 0.65));
  $('sky').style.opacity = skyA > 0 ? 1 : 0;
  { const e = (-22 + 122 * skyA).toFixed(2); const m = `linear-gradient(180deg, #000 ${e}%, transparent ${(+e + 22).toFixed(2)}%)`;
    $('sky').style.webkitMaskImage = skyA >= 1 ? 'none' : m; $('sky').style.maskImage = skyA >= 1 ? 'none' : m; }
  const duskA = E.inOutSine(seg(t, B.banlu, B.boardB_out + 0.2));
  $('sunset').style.opacity = duskA.toFixed(4);
  R.skyG.setAttribute('opacity', (skyA * (1 - 0.6 * duskA)).toFixed(4));
  R.wavelets.forEach((w, i) => {
    const appear = B.sky + 0.25 + w.d * 0.6 + (w.d > 0.45 ? (B.mantian - B.sky - 0.4) : 0);
    const a = clamp((t - appear) / 0.35) * (0.55 + 0.45 * Math.sin(t * 2.2 + i));
    const dx = Math.cos(w.a) * w.sp * 26 * (t - B.sky), dy = Math.sin(w.a) * w.sp * 26 * (t - B.sky);
    w.p.setAttribute('transform', `translate(${(w.x + dx).toFixed(1)} ${(w.y + dy).toFixed(1)}) rotate(${(w.a * 57.3).toFixed(1)})`);
    w.p.setAttribute('opacity', (a * (1 - duskA)).toFixed(3));
  });
  R.duskG.setAttribute('opacity', duskA.toFixed(4));
  R.clouds.forEach(c => c.g.setAttribute('transform', `translate(${(c.x + c.sp * (t - B.banlu)).toFixed(1)} ${c.y})`));
  const sunRise = E.outCubic(seg(t, B.boardB_out, B.boardB_out + 1.2));
  R.duskSun.setAttribute('cy', (1230 - 70 * sunRise).toFixed(1));

  // title-scene props: sun + molecules (fade before the board)
  const propA = clamp(t / 0.35) * (1 - seg(t, B.sun_card_out - 0.1, B.sun_card_out + 0.2));
  R.propsG.setAttribute('opacity', propA.toFixed(3));
  R.mols1.forEach((m, i) => m.setAttribute('transform', `translate(${(m._x + 10 * Math.sin(t * 1.3 + i * 2)).toFixed(1)} ${(m._y + 12 * Math.sin(t * 1.1 + i)).toFixed(1)}) rotate(${(20 * Math.sin(t * .8 + i)).toFixed(1)})`));
  const sunIn = spring(t - 0.08, 2.6, 0.5);
  // big sun flies into the sunlight card at the scene change
  const fly = E.inOutCubic(seg(t, B.sun_card, B.sun_card + 0.42));
  R.bigSun._set(905, 250, 64 * sunIn, fly > 0 ? 0 : 1);
  const cardSunCanvas = [88 + 70, 160 + 190];
  R.flySun._set(lerp(905, cardSunCanvas[0], fly), lerp(250, cardSunCanvas[1], fly) - 60 * Math.sin(Math.PI * fly), lerp(64, 30, fly), fly > 0 && fly < 1 ? 1 : 0);

  // title card
  {
    const u = t - B.title_in;
    const y = lerp(-560, 0, spring(u - 0.02, 2.0, 0.55));
    const rz = lerp(-12, -3, spring(u, 2.2, 0.6));
    const out = E.inCubic(seg(t, B.sun_card - 0.04, B.sun_card + 0.14));
    const op = clamp(u / 0.06) * (1 - out);
    setT(R.cTitle, `translate3d(0px, ${(y - 36 * out).toFixed(1)}px, 0) rotateY(${(16 + 22 * out).toFixed(2)}deg) rotateX(4deg) rotateZ(${(rz * 0.67).toFixed(2)}deg) scale(${(1 - 0.08 * out).toFixed(4)})`, op);
    R.cTitle.style.display = op > 0.001 ? 'block' : 'none';
    R.kTitle.style.opacity = clamp(1 - 4 * out).toFixed(3);          // small kicker leaves first while the card swings
    const lu = t - B.lan;
    const ls = lu > 0 ? 1 + 0.26 * Math.exp(-lu * 5) * Math.sin(Math.min(lu * 14, Math.PI * 0.999)) + 0.08 * spring(lu, 3, .5) : 1;
    const lc = lu > 0 ? '#2F6BD8' : '#1B2638';
    const lan = $('lanChar');
    lan.style.transform = `scale(${ls.toFixed(4)}) rotate(${lu > 0 ? (-6 * Math.exp(-lu * 4)).toFixed(2) : 0}deg)`;
    lan.style.color = lc;
    lan.style.textShadow = lu > 0 ? `0 0 ${(18 * Math.exp(-lu * 2) + 6).toFixed(1)}px rgba(47,107,216,.55)` : 'none';
    // burst lines around 蓝
    const bu = seg(t, B.lan, B.lan + 0.45);
    R.lanBurst.setAttribute('opacity', bu > 0 && bu < 1 ? (1 - bu).toFixed(3) : 0);
    if (bu > 0 && bu < 1) {
      let d = '';
      const cx = 138, cy = 296;
      for (let i = 0; i < 9; i++) {
        const a = -Math.PI * 0.9 + i * Math.PI * 1.8 / 8, r0 = 58 + 40 * E.outCubic(bu), r1 = r0 + 26 * (1 - bu);
        d += `M ${cx + Math.cos(a) * r0} ${cy + Math.sin(a) * r0} L ${cx + Math.cos(a) * r1} ${cy + Math.sin(a) * r1} `;
      }
      if (!R.lanBurst.firstChild) S(R.lanBurst, 'path', { stroke: '#2F6BD8', 'stroke-width': 6, 'stroke-linecap': 'round', fill: 'none' });
      R.lanBurst.firstChild.setAttribute('d', d);
    }
  }
  // sunlight card
  {
    const u = t - B.sun_card;
    const inP = spring(u - 0.16, 2.3, 0.6);
    const out = E.inCubic(seg(t, B.sun_card_out, B.sun_card_out + 0.2));
    const op = clamp((u - 0.16) / 0.08) * (1 - out);
    setT(R.cSun, `translate3d(0px, ${(lerp(-30, 0, inP) - 36 * out).toFixed(1)}px, 0) rotateY(${(lerp(40, 16, inP) + 22 * out).toFixed(2)}deg) rotateX(3deg) rotateZ(-2deg) scale(${(1 - 0.08 * out).toFixed(4)})`, op);
    R.cSun.style.display = op > 0.001 ? 'block' : 'none';
    R.kSun.style.opacity = (clamp((inP - 0.85) / 0.15) * clamp(1 - 4 * out)).toFixed(3);   // ... and arrives last
    R.sunCardSun._set(70, 190, 30, fly >= 1 ? 1 : 0);
    // white beam from the sun into the lens
    const bp = E.outCubic(seg(t, B.sun_card + 0.4, B.sun_card + 0.8));
    const L = R.lens, bx0 = 96, by0 = 196, bx1 = L.cx - L.Rr + 6;
    const ex = lerp(bx0, bx1, bp), ey = lerp(by0, L.cy, bp);
    R.sunBeam.setAttribute('d', bp > 0 ? `M ${bx0} ${by0 - 5} L ${ex} ${ey - 26 * bp} L ${ex} ${ey + 26 * bp} L ${bx0} ${by0 + 5} Z` : '');
    // colours inside the lens: appear on 各种颜色, converge to white on 混在一起
    const mergeP = E.inOutCubic(seg(t, B.merge, B.merge + 0.5));
    L.waves.forEach((w, i) => {
      const ap = E.outBack(seg(t, B.colors - 0.08 + i * 0.05, B.colors + 0.22 + i * 0.05));
      const y = L.cy - 72 + i * 24;
      const yy = lerp(y, L.cy, mergeP);
      const amp = 6 * (1 - mergeP);
      w.setAttribute('d', wavePath(L.cx - L.Rr - 40 + 80 * (1 - clamp(ap)), yy, L.cx + L.Rr, yy, L.nms[i] * 0.075, amp, 0.1 * i - 0.6 * t));
      w.setAttribute('opacity', (clamp(ap) * (1 - 0.85 * mergeP)).toFixed(3));
    });
    const whiteIn = bp * (1 - E.outCubic(seg(t, B.colors - 0.06, B.colors + 0.2)));      // white light enters the lens ...
    L.white.setAttribute('opacity', Math.max(whiteIn, mergeP * (1 - 0.3 * seg(t, B.merge + 0.5, B.merge + 0.9))).toFixed(3));   // ... splits, then merges back
    R.lensCap.style.opacity = E.outCubic(seg(t, B.colors + 0.25, B.colors + 0.55)).toFixed(3);
  }
  // key word 各种颜色 (front)
  {
    const e = popEnv(t, B.colors - 0.04, B.merge + 0.55, { rot: -8, dy: 30 });
    const whiten = E.inOutCubic(seg(t, B.merge, B.merge + 0.45));
    setT(R.kwColors, `translateY(${e.y.toFixed(1)}px) scale(${e.s.toFixed(4)}) rotate(${e.r.toFixed(2)}deg)`, e.a);
    [...R.kwColors.children].forEach((sp, i) => { sp.style.transform = `translateY(${(-18 * Math.exp(-Math.max(0, t - B.colors - i * 0.06) * 7) * (t > B.colors + i * 0.06 ? 1 : 0)).toFixed(1)}px)`; sp.style.opacity = t > B.colors - 0.04 + i * 0.06 ? 1 : 0; });
    R.kwColors.style.filter = `drop-shadow(0 0 2px #fff) drop-shadow(0 0 2px #fff) drop-shadow(0 6px 14px rgba(0,0,0,.45)) saturate(${(1 - whiten).toFixed(3)}) brightness(${(1 + 0.9 * whiten).toFixed(3)})`;
  }
  // bars: blue vs red scattering (behind the host)
  {
    const on = seg(t, B.blue_bar - 0.35, B.blue_bar - 0.05) * (1 - seg(t, B.bars_out, B.bars_out + 0.3));
    R.barsG.setAttribute('opacity', on.toFixed(3));
    const bw = 700 * clamp(E.outBack(seg(t, B.blue_bar, B.blue_bar + 0.5), 1.2));
    const rw = 128 * clamp(E.outBack(seg(t, B.red_bar, B.red_bar + 0.3), 1.4));
    R.barB.setAttribute('width', Math.max(0, bw).toFixed(1)); R.barHiB.setAttribute('width', Math.max(0, bw - 30).toFixed(1));
    R.barR.setAttribute('width', Math.max(0, rw).toFixed(1)); R.barHiR.setAttribute('width', Math.max(0, rw - 30).toFixed(1));
    const lb = popEnv(t, B.blue_bar - 0.2, B.bars_out, { from: 0.6, dy: 0, outDur: 0.3 });
    const lr = popEnv(t, B.red_bar - 0.2, B.bars_out, { from: 0.6, dy: 0, outDur: 0.3 });
    setT(R.barLblB, `scale(${lb.s.toFixed(4)})`, lb.a); setT(R.barLblR, `scale(${lr.s.toFixed(4)})`, lr.a);
    const e = popEnv(t, B.beishu - 0.03, B.bars_out, { from: 0.2, rot: -10, freq: 3.4, damp: 0.34, outDur: 0.3 });
    setT(R.kwBeishu, `translateY(${e.y.toFixed(1)}px) scale(${e.s.toFixed(4)}) rotate(${(e.r - 4).toFixed(2)}deg)`, e.a);
  }
  // sky key word 蓝光 (behind the host)
  {
    const e = popEnv(t, B.languang - 0.04, B.boardB_in + 0.3, { from: 0.5, dy: 40, freq: 2.4, damp: 0.5, outDur: 0.35 });
    setT(R.kwLanguang, `translateY(${e.y.toFixed(1)}px) scale(${e.s.toFixed(4)})`, e.a);
  }
  // sunset chips + 晚霞
  {
    const c1 = popEnv(t, B.cheng - 0.04, B.wanxia - 0.45, { rot: -8, dy: 20 });
    const c2 = popEnv(t, B.hong - 0.04, B.wanxia - 0.45, { rot: 8, dy: 20 });
    setT(R.chipCheng, `translateY(${c1.y.toFixed(1)}px) scale(${c1.s.toFixed(4)}) rotate(${c1.r.toFixed(2)}deg)`, c1.a);
    setT(R.chipHong, `translateY(${c2.y.toFixed(1)}px) scale(${c2.s.toFixed(4)}) rotate(${c2.r.toFixed(2)}deg)`, c2.a);
    const e = popEnv(t, B.wanxia - 0.05, 99, { from: 0.45, dy: 50, freq: 2.2, damp: 0.5 });
    setT(R.kwWanxia, `translateY(${e.y.toFixed(1)}px) scale(${(e.s * (1 + 0.02 * seg(t, B.wanxia + 0.5, B.end))).toFixed(4)})`, e.a);
  }

  /* ---------- BOARD */
  const P = pipP(t);
  const boardOn = P > 0.0001;
  {
    // A1 scatter card
    const a1in = spring(t - B.boardA_in - 0.1, 2.2, 0.62), a1out = E.inCubic(seg(t, B.spec_in - 0.2, B.spec_in - 0.02));
    setT(R.cScat, `translate3d(0, ${(lerp(120, 0, a1in) - 90 * a1out).toFixed(1)}px, ${(-200 * a1out).toFixed(1)}px) rotateX(${lerp(24, 8, a1in).toFixed(2)}deg)`, clamp((t - B.boardA_in - 0.05) / 0.15) * (1 - a1out));
    R.cScat.style.display = vis(t, B.boardA_in, B.spec_in) ? 'block' : 'none';
    const bp = E.outCubic(seg(t, B.beam, B.beam + 0.6));
    const [hx, hy] = R.scHit, sx = 140, sy = 232;
    R.scBeam.setAttribute('d', bp > 0 ? `M ${sx} ${sy} L ${lerp(sx, hx, bp)} ${lerp(sy, hy, bp)}` : '');
    const sc = seg(t, B.scatter, B.scatter + 0.7);
    R.scBeam2.setAttribute('d', `M ${hx} ${hy} L ${lerp(hx, hx + 200, E.outCubic(sc))} ${lerp(hy, hy + 150, E.outCubic(sc))}`);
    R.scBeam2.setAttribute('opacity', (sc > 0 ? 0.7 : 0).toFixed(2));
    R.atmLbl.style.opacity = E.outCubic(seg(t, B.atm_label, B.atm_label + 0.3)).toFixed(3);
    R.scShell.setAttribute('fill', `rgba(110,165,235,${(0.34 + 0.16 * Math.exp(-Math.max(0, t - B.atm_label) * 3) * (t > B.atm_label ? 1 : 0)).toFixed(3)})`);
    R.scMols.forEach((m, i) => {
      const s = clamp(E.outBack(seg(t, B.mols + i * 0.13, B.mols + i * 0.13 + 0.3), 2.2));
      const wob = 3 * Math.sin(t * 2 + i);
      m.setAttribute('transform', `translate(${m._x} ${(m._y + wob).toFixed(1)}) scale(${s.toFixed(4)}) rotate(${(8 * Math.sin(t + i)).toFixed(1)})`);
      m.setAttribute('opacity', s > 0 ? 1 : 0);
    });
    R.molLbl.style.opacity = E.outCubic(seg(t, B.mols + 0.3, B.mols + 0.6)).toFixed(3);
    R.scWaves.forEach((w, i) => {
      const u = seg(t, B.scatter + (i % 5) * 0.03, B.scatter + 0.75 + (i % 5) * 0.03);
      if (u <= 0) { w.p.setAttribute('opacity', 0); return; }
      const r0 = 30 + 40 * E.outCubic(u), r1 = r0 + w.len * E.outCubic(Math.min(1, u * 1.6));
      const ux = Math.cos(w.ang), uy = Math.sin(w.ang);
      w.p.setAttribute('d', wavePath(hx + ux * r0, hy + uy * r0, hx + ux * r1, hy + uy * r1, w.lam, 5, -t * 2, 10));
      const hold = 1 - 0.35 * seg(t, B.scatter + 0.9, B.scatter + 1.4);
      w.p.setAttribute('opacity', ((w.blue ? 1 : 0.55) * clamp(u * 4) * hold).toFixed(3));
    });
    // A2 spectrum card
    const a2in = spring(t - B.spec_in - 0.02, 2.3, 0.6), a2out = E.inCubic(seg(t, B.spec_out - 0.12, B.spec_out + 0.08));
    setT(R.cSpec, `translate3d(0, ${(lerp(-40, 0, a2in) - 40 * a2out).toFixed(1)}px, 0) rotateY(${(lerp(22, 0, a2in) + 18 * a2out).toFixed(2)}deg) rotateX(6deg)`, clamp((t - B.spec_in - 0.02) / 0.1) * (1 - a2out));
    R.cSpec.style.display = vis(t, B.spec_in, B.spec_out + 0.1) ? 'block' : 'none';
    const arr = E.outCubic(seg(t, B.pianlan, B.pianlan + 0.5));
    const yA = R.spYb + 110, xA1 = R.spX(680), xA0 = lerp(xA1, R.spX(430), arr);
    R.spArrow.setAttribute('d', arr > 0 ? `M ${xA1} ${yA} L ${xA0} ${yA} M ${xA0 + 22} ${yA - 16} L ${xA0} ${yA} L ${xA0 + 22} ${yA + 16}` : '');
    R.spArrow.setAttribute('opacity', arr > 0 ? 1 : 0);
    const cu = E.inOutCubic(seg(t, B.spec_in + 0.02, B.spec_in + 0.36));
    const hot = seg(t, B.lihai - 0.05, B.lihai + 0.6);
    R.spHot.setAttribute('opacity', (hot > 0 ? 0.9 * (1 - 0.5 * hot) : 0).toFixed(3));
    R.spHot.setAttribute('r', (24 + 60 * E.outCubic(hot)).toFixed(1));
    R.spUp.setAttribute('opacity', E.outCubic(seg(t, B.lihai - 0.05, B.lihai + 0.2)).toFixed(3));
    R.spUp.setAttribute('transform', `translate(0 ${(-14 * E.outBack(seg(t, B.lihai - 0.05, B.lihai + 0.35))).toFixed(1)})`);
    R.spCurve.setAttribute('stroke-dasharray', `${(R.spCurveLen * cu).toFixed(1)} 9999`);
    R.spCurve.setAttribute('opacity', cu > 0 ? 1 : 0);
    R.spLines.forEach(o => { const v = clamp((cu - (700 - o.nm) / 300 * 0.9) / 0.1); o.l.setAttribute('y2', lerp(R.spYb, o.y, v).toFixed(1)); });
    if (cu > 0) { const p = R.spCurve.getPointAtLength(R.spCurveLen * cu); R.spDot.setAttribute('cx', p.x); R.spDot.setAttribute('cy', p.y); }
    R.spDot.setAttribute('opacity', cu > 0 ? 1 : 0);
    R.spYlbl.setAttribute('opacity', E.outCubic(seg(t, B.spec_in + 0.1, B.spec_in + 0.4)).toFixed(3));
    // B: noon vs sunset
    const bin = t - B.boardB_in;
    const nIn = spring(bin - 0.2, 2.2, 0.62), dIn = spring(bin - 0.32, 2.2, 0.62);
    const bOut = E.inCubic(seg(t, B.boardB_out - 0.05, B.boardB_out + 0.25));
    setT(R.cNoon, `translate3d(0, ${(lerp(140, 0, nIn) + 60 * bOut).toFixed(1)}px, 0) rotateX(${lerp(30, 12, nIn).toFixed(2)}deg)`, clamp((bin - 0.15) / 0.12) * (1 - bOut));
    const focus = E.outCubic(seg(t, B.bangwan, B.bangwan + 0.35));
    setT(R.cDusk, `translate3d(0, ${(lerp(140, 0, dIn) + 60 * bOut).toFixed(1)}px, 0) rotateX(${lerp(30, 12, dIn).toFixed(2)}deg) scale(${(1 + 0.03 * focus).toFixed(4)})`, clamp((bin - 0.27) / 0.12) * (1 - bOut));
    R.cDusk.style.boxShadow = `inset 0 2px 0 rgba(255,255,255,.8), inset 0 -3px 0 rgba(0,0,0,.06), 0 8px 0 #D6A884, 0 40px 70px rgba(0,0,0,.40), 0 0 ${(60 * focus).toFixed(0)}px rgba(255,160,90,${(0.55 * focus).toFixed(3)})`;
    R.cNoon.style.display = R.cDusk.style.display = vis(t, B.boardB_in, B.boardB_out + 0.3) ? 'block' : 'none';
    R.goldT.style.opacity = (E.outCubic(seg(t, B.path - 0.1, B.path + 0.25)) * (1 - bOut)).toFixed(3);
    R.goldT.style.transform = `translateX(-50%) translateY(${(18 * (1 - E.outCubic(seg(t, B.path - 0.1, B.path + 0.35)))).toFixed(1)}px)`;
    // noon: short beam + blue ticks
    const nb = E.outCubic(seg(t, B.path, B.path + 0.3));
    R.nBeam.setAttribute('y2', lerp(222, 400 - 34, nb).toFixed(1));
    R.nTicks.forEach((p, i) => p.setAttribute('opacity', (0.9 * clamp((t - B.path - 0.25 - i * 0.07) / 0.15)).toFixed(3)));
    R.nBr.setAttribute('opacity', nb.toFixed(3)); R.nLbl.setAttribute('opacity', nb.toFixed(3));
    // sunset: long beam
    const g = R.dGeo, db = E.inOutCubic(seg(t, B.path + 0.15, B.path + 1.0));
    R.dBeamW.setAttribute('x2', lerp(g.x0 + 14, g.ox - 14, db).toFixed(1));
    const q = E.inOutSine(seg(t, B.banlu, B.sanshe + 0.5));
    R.dBeamW.setAttribute('opacity', (1 - q).toFixed(3)); R.dBeamC.setAttribute('opacity', q.toFixed(3));
    R.dTicks.forEach((p, i) => { const u = seg(t, B.banlu + 0.05 + i * 0.26, B.banlu + 0.3 + i * 0.26); p.setAttribute('opacity', (0.95 * u).toFixed(3)); p.setAttribute('transform', `translate(${(-6 * u).toFixed(1)} ${(-10 * u).toFixed(1)})`); });
    const th = seg(t, B.thick, B.thick + 0.5);
    R.dShell.setAttribute('fill', `rgba(120,170,235,${(0.30 + 0.25 * Math.sin(Math.PI * th)).toFixed(3)})`);
    R.dBr.setAttribute('opacity', E.outCubic(seg(t, B.thick - 0.1, B.thick + 0.2)).toFixed(3));
    R.dLbl.setAttribute('opacity', E.outCubic(seg(t, B.thick - 0.1, B.thick + 0.2)).toFixed(3));
    R.dGlow.setAttribute('opacity', (0.85 * E.outCubic(seg(t, B.sanshe + 0.3, B.sanshe + 0.7))).toFixed(3));
    // board key words, one at a time in the lower-left panel
    const kws = [[R.kwSanshe, B.scatter - 0.02, B.spec_in - 0.05, { rot: -6, shake: 0 }], [R.kwPianlan, B.pianlan - 0.03, B.lihai - 0.26, { rot: -5 }],
      [R.kwLihai, B.lihai - 0.03, B.spec_out - 0.1, { rot: 0, shake: 5 }], [R.kwBangwan, B.bangwan - 0.03, B.thick - 0.26, { rot: -5 }],
      [R.kwThick, B.thick - 0.03, B.sanshe - 0.26, { rot: -3 }], [R.kwSanguang, B.sanshe - 0.03, B.boardB_out - 0.05, { rot: -4, shake: 3 }]];
    kws.forEach(([el, a, b, o]) => { const e = popEnv(t, a, b, Object.assign({ dy: 24, outDur: 0.18 }, o)); setT(el, `translateY(${e.y.toFixed(1)}px) scale(${e.s.toFixed(4)}) rotate(${e.r.toFixed(2)}deg)`, e.a); el.style.transformOrigin = '0% 60%'; });
    // burst lines around 散射开 / 散射光了
    const bt = [B.scatter, B.sanshe].find(x => t >= x && t < x + 0.5);
    R.burstSv.setAttribute('opacity', bt !== undefined ? (1 - seg(t, bt, bt + 0.5)).toFixed(3) : 0);
    if (bt !== undefined) {
      const u = E.outCubic(seg(t, bt, bt + 0.5)), cx = 330, cy = 1128;
      [...R.burstSv.children].forEach((p, i) => { const a = i / 14 * Math.PI * 2, r0 = 190 + 70 * u, r1 = r0 + 36 * (1 - u); p.setAttribute('d', `M ${cx + Math.cos(a) * r0 * 1.25} ${cy + Math.sin(a) * r0 * .55} L ${cx + Math.cos(a) * r1 * 1.25} ${cy + Math.sin(a) * r1 * .55}`); });
    }
  }
  /* ---------- PiP mapping (room composite -> rounded rect) */
  const pr = TL.pip.rect, k1 = TL.pip.k;
  const rect = [lerp(0, pr[0], P), lerp(0, pr[1], P), lerp(W, pr[2], P), lerp(H, pr[3], P)];
  const kk = Math.exp(Math.log(k1) * P);
  const wc = TL.pip.window_center_src;
  const Pc = [(wc[0] - 540) * sv + 540, (wc[1] - 1920) * sv + 1920 + Dv];
  const Pr = [lerp(Pc[0], pr[0] + pr[2] / 2, P), lerp(Pc[1], pr[1] + pr[3] / 2, P)];
  const rad = lerp(0, TL.pip.radius, P);
  const ring = $('pipRing'), shd = $('pipShadow');
  if (P > 0.02) {
    Object.assign(ring.style, { display: 'block', left: rect[0] - 2 + 'px', top: rect[1] - 2 + 'px', width: rect[2] + 4 + 'px', height: rect[3] + 4 + 'px', borderRadius: rad + 2 + 'px', opacity: clamp((P - 0.02) * 4).toFixed(3) });
    Object.assign(shd.style, { display: 'block', left: rect[0] + 6 + 'px', top: rect[1] + 18 + 'px', width: rect[2] + 'px', height: rect[3] + 'px', opacity: P.toFixed(3) });
  } else { ring.style.display = 'none'; shd.style.display = 'none'; }

  /* ---------- captions */
  let capIdx = -1;
  R.caps.forEach((o, i) => {
    const c = o.c;
    const on = t >= c.t0 && t < c.t1;
    if (on) capIdx = i;
    const u = t - c.t0;
    o.wrap.style.opacity = on ? clamp(u / 0.1).toFixed(3) : 0;
    o.wrap.style.transform = on ? `translateY(${(10 * (1 - E.outCubic(clamp(u / 0.14)))).toFixed(1)}px)` : '';
    o.marks.forEach(m => { const v = E.outCubic(seg(t, Math.max(c.t0 + 0.05, m.kt - 0.04), Math.max(c.t0 + 0.05, m.kt - 0.04) + 0.16)); m.m.style.transform = `scaleX(${v.toFixed(4)})`; });
  });

  return {
    t, D: Dv, s: sv, pip: { P, rect, k: kk, Pc, Pr, radius: rad }, board: boardOn, cap: capIdx,
    sky: skyA, dusk: duskA,
  };
}

/* ---------------------------------------------------------------- QA boxes
   every visible text block (data-k="txt") with its layer; room boxes are in room-composite
   coordinates (render.py maps them through the PiP transform when the host is in the PiP) */
function boxes() {
  const out = [];
  const layerOf = e => e.closest('#L_room') ? 'room' : e.closest('#L_board') ? 'board' : 'front';
  document.querySelectorAll('[data-k~="txt"]').forEach(e => {
    let op = 1, n = e;
    while (n && n.nodeType === 1 && n !== document.body) { const cs = getComputedStyle(n); if (cs.display === 'none' || cs.visibility === 'hidden') { op = 0; break; } op *= parseFloat(cs.opacity); n = n.parentElement; }
    if (e.getAttribute && e.getAttribute('opacity') !== null) op *= parseFloat(e.getAttribute('opacity'));
    if (op < 0.05) return;
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const fs = parseFloat(getComputedStyle(e).fontSize) || 0;
    out.push({ id: e.dataset.id || (e.textContent || '').trim().slice(0, 12), text: (e.textContent || '').trim(), layer: layerOf(e), cap: !!e.dataset.cap, x: r.left, y: r.top, w: r.width, h: r.height, a: +op.toFixed(3), font_px: fs });
  });
  return out;
}

async function init() {
  TL = await (await fetch('timeline.json')).json();
  build();
  await document.fonts.ready;
  document.body.dataset.show = 'room board front';
  layoutCaptions();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  window.READY = true;
}
window.renderFrame = renderFrame;
window.qaBoxes = boxes;
window.setShow = s => { document.body.dataset.show = s; };
init();
