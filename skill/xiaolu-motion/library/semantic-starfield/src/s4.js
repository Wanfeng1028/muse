'use strict';
/* ==========================================================================
   S4  03 MEANING  (15.50 – 20.00, incl. the S3 -> 3D hand-off)
   Deterministic 3D word cloud, perspective projection, depth of field.
   ========================================================================== */
const CLUSTERS = [
  { key: 'autumn', c: [260, -120, 420], s: 300, tint: '#D6F6FF', words: ['秋天', '凉', '爽', '落叶', '枫叶', '桂花', '中秋', '月亮', '大雁', '霜降', '丰收', '稻田', '金黄', '秋风', '思念', '银杏', '秋雨', '重阳', '登高', '萧瑟', '秋分', '立秋', '红叶', '菊花', '凉意', '露水', '秋收', '秋夜', '落日', '芦苇', '桂香', '候鸟'] },
  { key: 'summer', c: [-760, -1000, 980], s: 260, tint: '#8FB8FF', words: ['夏天', '蝉鸣', '西瓜', '暴雨', '冰棍', '游泳', '晒', '热', '萤火虫', '荷花', '空调', '汽水', '暑假', '烈日', '蚊子', '凉席', '立夏', '雷阵雨'] },
  { key: 'winter', c: [980, 900, 1150], s: 260, tint: '#A9C8FF', words: ['冬天', '雪', '寒冷', '围巾', '暖气', '冰', '腊月', '春节', '年夜饭', '北风', '雪人', '壁炉', '冬至', '饺子', '霜'] },
  { key: 'spring', c: [-980, 760, 320], s: 240, tint: '#9FE0E8', words: ['春天', '花开', '柳絮', '春雨', '燕子', '清明', '樱花', '嫩芽', '踏青', '立春', '桃花', '春风'] },
  { key: 'desc', c: [-380, -1250, -320], s: 250, tint: '#B7A8FF', words: ['形容', '描述', '比喻', '形容词', '词语', '字', '句子', '表达', '修辞', '一个', '描写', '措辞', '语气', '意象', '概括', '名词', '动词'] },
  { key: 'func', c: [-120, 1250, -380], s: 250, tint: '#9AA6C4', words: ['用', '把', '的', '了', '在', '，', '。', '是', '和', '就', '也', '被', '吗', '呢', '、', '！', '？'] },
  { key: 'color', c: [1060, -1400, 180], s: 230, tint: '#9AD6F0', words: ['红', '橙', '黄', '绿', '蓝', '紫', '金色', '银色', '灰', '白', '黑', '琥珀', '青', '靛'] },
  { key: 'emotion', c: [880, 1620, -260], s: 230, tint: '#A99CFF', words: ['开心', '难过', '孤独', '温柔', '怀念', '平静', '焦虑', '惆怅', '感动', '安心', '期待', '失落'] },
  { key: 'city', c: [-1150, 1760, 840], s: 230, tint: '#7FA6D9', words: ['北京', '上海', '杭州', '成都', '南京', '西安', '苏州', '重庆', '广州', '深圳', '哈尔滨'] },
  { key: 'tech', c: [-1300, -280, 1350], s: 230, tint: '#6EE7F5', words: ['模型', '算法', '芯片', '数据', '向量', '神经网络', '代码', '服务器', '显卡', '注意力'] },
  { key: 'food', c: [1220, 380, 720], s: 240, tint: '#9EC9E6', words: ['火锅', '奶茶', '面条', '米饭', '苹果', '橘子', '石榴', '糖炒栗子', '板栗', '红薯'] },
  { key: 'time', c: [-560, 280, -980], s: 220, tint: '#8FA3C8', words: ['今天', '明天', '昨天', '早晨', '黄昏', '夜晚', '周末', '季节'] },
  { key: 'nature', c: [760, -560, -860], s: 230, tint: '#9CC3E0', words: ['山', '河', '湖', '海', '云', '雨', '风', '星空', '森林', '月'] },
  { key: 'life', c: [240, 520, -1180], s: 260, tint: '#8C9BD6', words: ['猫', '狗', '鸟', '鱼', '熊猫', '房间', '窗户', '灯', '书', '椅子', '妈妈', '朋友', '孩子', '老师', '走', '看', '听', '说', '想', '写', '歌', '钢琴'] },
];
const NEIGH = [['凉', [175, -125, -70]], ['落叶', [-205, 150, 45]], ['桂花', [235, 120, 95]], ['中秋', [-150, -185, 80]], ['丰收', [70, 235, -55]], ['秋风', [-255, -15, -90]]];
const NEIGH_D = ['0.14', '0.19', '0.23', '0.21', '0.26', '0.16'];
const NEIGH_T = [18.00, 18.17, 18.33, 18.50, 18.67, 18.83];
const S4D = { pts: [], tok: [], f: 1200 };

/* ---------------- S5 layout (shared with the pull-back) ---------------- */
const S5L = { x: 96, y0: 600, dy: 96, h: 72, r: 14, pad: 24, spine: 330, font: FNT.pf(48, 500) };
registerInit(() => {
  S5L.rows = [...TOK, ''].map((tk, i) => {
    const tw = tk ? textW(tk, S5L.font) : 0;
    const cw = Math.max(96, tw + 2 * S5L.pad);
    const yc = S5L.y0 + S5L.dy * i;
    let tx = S5L.x + S5L.pad, tb = yc + cjkMid(S5L.font);
    if (tk === '，' || tk === '。') { const ib = inkBox(tk, S5L.font); tx = S5L.x + cw / 2 - (ib.l + ib.r) / 2; tb = yc - (ib.t + ib.b) / 2; }
    return { tk, tw, cw, yc, tx, tb };
  });
});
function drawS5Card(w, g, i, alpha, grow = 1, hl = 0) {
  const r = S5L.rows[i];
  if (alpha <= 0.002) return;
  const cw = lerp(24, r.cw, grow), ch = lerp(24, S5L.h, grow);
  const cx = lerp(S5L.spine - 40, S5L.x + r.cw / 2, E.expoOut(grow));
  w.save(); w.globalAlpha = alpha;
  rrect(w, cx - cw / 2, r.yc - ch / 2, cw, ch, S5L.r);
  if (i < 7) {
    w.fillStyle = COL.card; w.fill(); w.lineWidth = 1.5; w.strokeStyle = mixHex(COL.stroke, COL.cyan, hl); w.stroke();
  } else {
    w.fillStyle = 'rgba(12,18,29,0.6)'; w.fill();
    w.setLineDash([6, 6]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.cyan, 0.9); w.stroke(); w.setLineDash([]);
  }
  w.restore();
  if (hl > 0.01) { g.save(); g.globalAlpha = alpha * hl; rrect(g, cx - cw / 2, r.yc - ch / 2, cw, ch, S5L.r); g.lineWidth = 6; g.strokeStyle = COL.cyan; g.stroke(); g.restore(); }
}

/* ---------------- data ---------------- */
registerInit(() => {
  const rng = mulberry32(4242);
  const pts = [];
  const auto = CLUSTERS[0];
  const placed = [];
  const tooClose = (p, d) => placed.some(q => Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]) < d || (Math.abs(q[0] - p[0]) < 120 && Math.abs(q[1] - p[1]) < 60));
  const add = (p, label, cl, kind) => { const o = { p, label, cl, tint: cl.tint, kind, r: kind === 'dust' ? 3 + rng() * 2.5 : 6.5, ph: rng() * TAU }; pts.push(o); if (label) placed.push(p); return o; };
  const qt = auto.c.slice();
  add(qt, '秋天', auto, 'word');
  const nb = {};
  for (const [wd, off] of NEIGH) nb[wd] = add([qt[0] + off[0], qt[1] + off[1], qt[2] + off[2]], wd, auto, 'word');
  for (const cl of CLUSTERS) {
    for (const wd of cl.words) {
      if (cl === auto && (wd === '秋天' || nb[wd])) continue;
      let p, tries = 0;
      do {
        const g1 = gaussR(rng), g2 = gaussR(rng), g3 = gaussR(rng);
        const s = cl === auto ? 1.35 : 1;
        p = [cl.c[0] + g1 * cl.s * s, cl.c[1] + g2 * cl.s * s * 1.1, cl.c[2] + g3 * cl.s * s * 0.9];
        if (cl === auto && (Math.hypot(p[0] - qt[0], p[1] - qt[1], p[2] - qt[2]) < 330 || Math.hypot(p[0] - qt[0], (p[1] - qt[1]) * 1.6) < 240)) continue;
        tries++;
      } while ((tooClose(p, 150) && tries < 80) || (cl === auto && (Math.hypot(p[0] - qt[0], p[1] - qt[1], p[2] - qt[2]) < 330 || Math.hypot(p[0] - qt[0], (p[1] - qt[1]) * 1.6) < 240)));
      add(p, wd, cl, 'word');
    }
  }
  // food-autumn bridge words
  const food = CLUSTERS.find(c => c.key === 'food');
  ['月饼', '螃蟹', '柿子'].forEach((wd, i) => {
    const u = 0.38 + i * 0.12;
    add([lerp(qt[0], food.c[0], u) + gaussR(rng) * 60, lerp(qt[1], food.c[1], u) + 240 + gaussR(rng) * 90, lerp(qt[2], food.c[2], u) + gaussR(rng) * 60], wd, food, 'word');
  });
  // dust
  for (let n = 0; n < 470; n++) {
    let p, cl;
    if (n < 330) { cl = CLUSTERS[Math.floor(rng() * CLUSTERS.length)]; p = [cl.c[0] + gaussR(rng) * cl.s * 1.9, cl.c[1] + gaussR(rng) * cl.s * 2.0, cl.c[2] + gaussR(rng) * cl.s * 1.8]; }
    else { cl = CLUSTERS[Math.floor(rng() * CLUSTERS.length)]; p = [(rng() - 0.5) * 3600, (rng() - 0.5) * 4800, (rng() - 0.5) * 3400]; }
    add(p, null, cl, 'dust');
  }
  // prompt tokens
  const rngS = mulberry32(99);
  for (const o of pts) o.show = o.label && (o.cl.key === 'autumn' || ['月饼', '螃蟹', '柿子'].includes(o.label) || rngS() < 0.42);
  S4D.tok = TOK.map(tk => pts.find(o => o.label === tk));
  S4D.tok.forEach((o, i) => { o.kind = 'token'; o.ti = i; });
  S4D.pts = pts;
  S4D.qt = qt;
  S4D.nb = NEIGH.map(([wd]) => nb[wd]);
  S4D.order = pts.map((_, i) => i);
  // ---- depth enrichment ----
  const r2 = mulberry32(5150);
  // micro dust: 520 tiny stars through a deep volume (parallax depth cue)
  S4D.micro = [];
  for (let n = 0; n < 520; n++) S4D.micro.push({ p: [(r2() - 0.5) * 6400, (r2() - 0.5) * 8600, -3000 + r2() * 9000], a: 0.1 + 0.26 * r2(), sz: r2() < 0.8 ? 1.2 : 2.0, ph: r2() * TAU, c: r2() < 0.5 ? '#CFF6FF' : (r2() < 0.5 ? '#8FB8FF' : '#B7A8FF') });
  // far clusters, placed deep behind the autumn cluster as seen from the close-up camera
  const fwd = [Math.sin(11 * DEG) * Math.cos(-4 * DEG), Math.sin(-4 * DEG), Math.cos(11 * DEG) * Math.cos(-4 * DEG)];
  // offsets chosen so that, from the close-up camera, the clusters sit in the corners away from 秋天 and its neighbours
  const FAR = [
    { off: [1536, -1980, 0], dz: 5000, words: ['蛙声', '晚风', '星河', '蒲扇', '竹席'] },
    { off: [-1850, 2480, 0], dz: 5600, words: ['立冬', '小雪', '雾凇', '大寒', '炉火'] },
    { off: [2050, 3420, 0], dz: 6400, words: ['地铁', '霓虹', '街灯', '楼宇', '车流'] },
  ];
  S4D.far = [];
  FAR.forEach((F, fi) => {
    const c = [qt[0] + fwd[0] * F.dz + F.off[0], qt[1] + fwd[1] * F.dz + F.off[1], qt[2] + fwd[2] * F.dz + F.off[2]];
    for (let n = 0; n < 60; n++) S4D.far.push({ p: [c[0] + gaussR(r2) * 260, c[1] + gaussR(r2) * 300, c[2] + gaussR(r2) * 260], label: null, a: 0.25 + 0.35 * r2(), fi });
    const LAY = [[-330, -260], [220, -420], [-120, 170], [360, 60], [60, 520]];
    F.words.forEach((wd, wi) => S4D.far.push({ p: [c[0] + LAY[wi][0], c[1] + LAY[wi][1], c[2] + (r2() - 0.5) * 120], label: wd, a: 0.2 + 0.1 * r2(), fi }));
  });
  // foreground bokeh (very faint) and nebula washes
  S4D.bokeh = [];
  for (let n = 0; n < 7; n++) S4D.bokeh.push({ x: r2() * W, y: 200 + r2() * 1500, r: 90 + r2() * 150, a: 0.03 + 0.03 * r2(), par: 0.6 + r2() * 0.8, c: ['#6EE7F5', '#8E7DFF', '#8FB8FF'][n % 3] });
  S4D.neb = [{ x: 300, y: 620, rx: 620, ry: 520, c: '#2E3FBF', a: 0.055 }, { x: 820, y: 1260, rx: 560, ry: 640, c: '#6EE7F5', a: 0.035 }, { x: 560, y: 980, rx: 820, ry: 900, c: '#8E7DFF', a: 0.03 }];
});
function s4Backdrop(w, t, cam, fs, fadeAll) {
  // nebula washes (screen space, slight parallax with yaw)
  const yawPx = (cam.sy ? Math.asin(clamp(cam.sy, -1, 1)) : 0) * 600;
  for (const n of S4D.neb) {
    const x = n.x - yawPx * 0.4, y = n.y;
    const g = w.createRadialGradient(x, y, 0, x, y, 1);
    const c = hexRgb(n.c);
    g.addColorStop(0, `rgba(${c},${n.a * fadeAll})`); g.addColorStop(0.55, `rgba(${c},${n.a * 0.45 * fadeAll})`); g.addColorStop(1, `rgba(${c},0)`);
    w.save(); w.translate(x, y); w.scale(n.rx, n.ry); w.fillStyle = g; w.beginPath(); w.arc(0, 0, 1, 0, TAU); w.fill(); w.restore();
  }
  // micro dust
  for (const m of S4D.micro) {
    const c = toCam(cam, [m.p[0] * fs, m.p[1] * fs, m.p[2] * fs]);
    if (c[2] < 80) continue;
    const sx = CX + cam.f * c[0] / c[2], sy = CY + cam.f * c[1] / c[2];
    if (sx < -4 || sx > W + 4 || sy < -4 || sy > H + 4) continue;
    const depthA = clamp((9000 - c[2]) / 4000) * clamp((c[2] - 80) / 300);
    const a = m.a * depthA * (0.75 + 0.25 * Math.sin(t * 2.1 + m.ph)) * fadeAll;
    if (a < 0.01) continue;
    w.globalAlpha = a; w.fillStyle = m.c; w.fillRect(sx - m.sz / 2, sy - m.sz / 2, m.sz, m.sz);
  }
  w.globalAlpha = 1;
  // far clusters: faint star clumps with small labels
  for (const o of S4D.far) {
    const c = toCam(cam, [o.p[0] * fs, o.p[1] * fs, o.p[2] * fs]);
    if (c[2] < 200) continue;
    const sx = CX + cam.f * c[0] / c[2], sy = CY + cam.f * c[1] / c[2];
    if (sx < -40 || sx > W + 40 || sy < -40 || sy > H + 40) continue;
    const a = o.a * fadeAll;
    if (!o.label) { drawSprite(w, softDot('d', '#9FB6E8'), sx, sy, 3.2, a); continue; }
    w.fillStyle = '#AFC3EA'; w.globalAlpha = a * 1.2; w.beginPath(); w.arc(sx, sy, 1.8, 0, TAU); w.fill();
    const zone = smooth((sy - 300) / 40) * smooth((sx - 30) / 40) * smooth((1000 - sx - textW(o.label, FNT.pf(19, 400))) / 40);
    if (zone > 0.01) S4LB.push({ text: o.label, font: FNT.pf(19, 400), x: sx + 7, b: sy + 7, size: 19, col: '#9AAAD0', a: a * zone, pri: 10 - c[2] / 1e5 });
    w.globalAlpha = 1;
  }
}
function s4Bokeh(w, t, cam, fadeAll) {
  const yawPx = (cam.sy ? Math.asin(clamp(cam.sy, -1, 1)) : 0) * 600;
  for (const b of S4D.bokeh) {
    const x = b.x - yawPx * b.par + Math.sin(t * 0.3 + b.r) * 12, y = b.y + Math.cos(t * 0.25 + b.r) * 10;
    drawSprite(w, softDot('b', b.c, 0.3), x, y, b.r, b.a * fadeAll);
  }
}

/* ---------------- camera ---------------- */
function makeCam(T, yaw, pitch, dist, f) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const fwd = [sy * cp, sp, cy * cp];
  return { P: [T[0] - dist * fwd[0], T[1] - dist * fwd[1], T[2] - dist * fwd[2]], cy, sy, cp, sp, f, dist };
}
function toCam(c, X) {
  const dx = X[0] - c.P[0], dy = X[1] - c.P[1], dz = X[2] - c.P[2];
  const x1 = c.cy * dx - c.sy * dz, z1 = c.sy * dx + c.cy * dz;
  return [x1, c.cp * dy - c.sp * z1, c.sp * dy + c.cp * z1];
}
function unproject(c, sx, sy, z) {
  const xc = (sx - CX) * z / c.f, yc = (sy - CY) * z / c.f;
  const dy = c.cp * yc + c.sp * z, z1 = -c.sp * yc + c.cp * z;
  const dx = c.cy * xc + c.sy * z1, dz = -c.sy * xc + c.cy * z1;
  return [c.P[0] + dx, c.P[1] + dy, c.P[2] + dz];
}
function s4Cam(t) {
  const u = E.cubicInOut(seg(t, 16.6, 19.2));
  const back = seg(t, 19.4, 20.0);
  const qt = S4D.qt;
  let T = [lerp(0, qt[0], u), lerp(0, qt[1], u), lerp(0, qt[2], u)];
  let yaw = lerp(-14, 11, E.sineInOut(seg(t, 16.4, 19.3))) * DEG;
  let pitch = lerp(3, -4, u) * DEG;
  let dist = Math.exp(lerp(Math.log(2950), Math.log(760), u)) - 60 * seg(t, 15.5, 16.6) - 18 * seg(t, 19.2, 19.4);
  if (back > 0) { const bb = E.cubicIn(seg(t, 19.4, 20.0)); dist = lerp(dist, 7000, bb); T = T.map(v => v * (1 - bb)); yaw *= 1 - bb; }
  return makeCam(T, yaw, pitch, dist, S4D.f);
}
function fieldScale(t) { return t < 16 ? 0.62 : lerp(0.62, 1, E.expoOut(seg(t, 16.0, 16.9))); }

/* ---------------- draw ---------------- */
function drawS4(t, R) {
  const w = R.w, g = R.g;
  const cam = s4Cam(t);
  const fs = fieldScale(t);
  const f = cam.f;
  const intro = seg(t, 15.5, 16.0);
  const burst = bump(t, 16.0, 16.06, 16.12, 16.5);
  const back = seg(t, 19.4, 20.0);
  const zf = cam.dist;
  const camStart = s4Cam(15.5);
  const hand = seg(t, 15.5, 16.0);   // S3 -> 3D hand-off
  const lab0 = E.expoOut(seg(t, 16.0, 16.7));
  S4LB.length = 0;
  const P = [];
  for (const o of S4D.pts) {
    let X = [o.p[0] * fs, o.p[1] * fs, o.p[2] * fs];
    let a = 1;
    if (o.kind !== 'token' && t < 16.0) {
      const e = E.expoOut(seg(t, 15.5 + 0.35 * hash1(o.ph * 1000), 16.0));
      X = [X[0], X[1], X[2] + (1 - e) * 2600]; a = e;
    }
    let c = toCam(cam, X);
    let sx = CX + f * c[0] / c[2], sy = CY + f * c[1] / c[2], z = c[2];
    if (o.kind === 'token' && hand < 1) {
      // list (2D) -> perspective rotation -> star position
      const i = o.ti, cd = S2D.cards[i];
      const L = unproject(camStart, 407, cd.yc, 1500);
      const Lc = unproject(camStart, 407, 940, 1500);
      const ang = 62 * DEG * E.expoIn(seg(t, 15.5, 15.86));
      const ca = Math.cos(ang), sa = Math.sin(ang);
      const rx = (L[0] - Lc[0]) * ca - (L[2] - Lc[2]) * sa, rz = (L[0] - Lc[0]) * sa + (L[2] - Lc[2]) * ca;
      const Lr = [Lc[0] + rx, L[1], Lc[2] + rz];
      const e2 = E.expoInOut(seg(t, 15.6, 16.0));
      const Y = [lerp(Lr[0], X[0], e2), lerp(Lr[1], X[1], e2), lerp(Lr[2], X[2], e2)];
      c = toCam(cam, Y); sx = CX + f * c[0] / c[2]; sy = CY + f * c[1] / c[2]; z = c[2];
    }
    if (z < 40) continue;
    P.push({ o, sx, sy, z, a });
  }
  P.sort((A, B) => B.z - A.z);
  const fadeBack = (1 - E.expoIn(seg(t, 19.4, 19.9))) * E.expoOut(seg(t, 15.5, 16.1));
  s4Backdrop(w, t, cam, fs, fadeBack);
  const K = 16;
  const fade = 1 - E.expoIn(seg(t, 19.4, 19.92));
  for (const q of P) {
    const o = q.o;
    const tokenish = o.kind === 'token';
    const r = f * o.r / q.z;
    const coc = K * Math.abs(q.z - zf) / q.z;
    const rd = Math.sqrt(r * r + coc * coc);
    let a = q.a * Math.pow(r / rd, 1.1) * (o.kind === 'dust' ? 0.75 : 1);
    a = Math.max(a, 0.05 * q.a) * (1 + 0.8 * burst);
    if (!tokenish) a *= fade;
    if (a < 0.004 || q.sx < -80 || q.sx > W + 80 || q.sy < -80 || q.sy > H + 80) continue;
    if (tokenish && back > 0) continue;   // tokens drawn separately during the pull-back
    const tw = Math.sin(t * 1.3 + o.ph) * 0.12 + 0.88;
    const col = tokenish ? COL.iceX : o.tint;
    if (tokenish) {
      const rr = lerp(7, Math.max(4.5, r * 0.9), E.expoInOut(hand));
      w.fillStyle = rgbStr(mixRgb(S2D.rowColor[o.ti], hexRgb(COL.iceX), E.expoInOut(hand))); w.beginPath(); w.arc(q.sx, q.sy, rr, 0, TAU); w.fill();
    } else if (coc > 2.2 || r < 1.2) drawSprite(w, softDot('d', col), q.sx, q.sy, rd * 1.9 + 1, clamp(a * tw) * (o.kind === 'dust' ? 0.9 : 1));
    else { w.globalAlpha = clamp(a * tw); w.fillStyle = col; w.beginPath(); w.arc(q.sx, q.sy, Math.max(1.3, r * 0.75), 0, TAU); w.fill(); w.globalAlpha = 1; }
    if (tokenish) drawSprite(g, softDot('c', COL.cyan), q.sx, q.sy, 30, 0.85);
    else if (o.kind !== 'dust' && coc < 7) drawSprite(g, softDot('c', col), q.sx, q.sy, Math.max(8, r * 3), a * 0.35);
    // labels
    if (o.label) {
      let la;
      if (tokenish) la = 1;
      else {
        if (!o.show) continue;
        const dCenter = Math.hypot(q.sx - CX, q.sy - CY) / 900;
        const near = clamp((zf + 350 - q.z) / 700);
        const foc = clamp(1 - (coc - 1.2) / 4.5);
        la = clamp((lab0 * 1.25) - dCenter * 0.3) * (0.07 + 0.93 * foc * near) * q.a;
        // keep the HUD / subtitle zones clean
        const zoneHud = smooth((q.sy - 300) / 40)                        // no word labels inside the HUD band
          * smooth((q.sx - 24) / 50) * smooth((1030 - q.sx - textW(o.label, FNT.pf(26, 400))) / 50);   // nor cut by the frame edge
        const zoneSub = 1 - bump(q.sy, 300, 345, 445, 490) * 0.85 * bump(t, 16.0, 16.2, 19.3, 19.6);
        la *= zoneHud * zoneSub;
      }
      if (tokenish && hand >= 1) la *= smooth((q.sy - 300) / 40);
      la *= tokenish ? 1 : Math.pow(fade, 3);
      if (la < 0.02) continue;
      const fsz = Math.round(clamp(20 + 11 * (1500 / q.z - 0.55), 22, 30));
      const lf = (tokenish && hand < 1) ? FNT.pf(24, 500) : FNT.pf(fsz, 400);
      let lx = q.sx + Math.max(r, 3) + (tokenish ? 16 : 8), lb = q.sy + cjkMid(lf);
      let lcol = o.cl.key === 'autumn' ? COL.ice : mixHex(o.tint, COL.text2, 0.45);
      if (tokenish) lcol = COL.iceX;
      if (o.label === '凉') { const b = E.expoOut(seg(t, 18.5, 18.8)); lcol = mixHex(lcol, COL.iceX, b); la = Math.max(la, b * fade); }
      if (tokenish && hand < 1) {
        // label slides from the left side (S3 label) to the right side
        const lf24 = FNT.pf(24, 500);
        const e = E.expoInOut(seg(t, 15.55, 15.95));
        const lxL = q.sx - 18 - textW(o.label, lf24);
        lx = lerp(lxL, lx, e);
      }
      if (tokenish && hand < 1) la *= 1 - bump(t, 15.62, 15.7, 15.86, 15.94);   // no smeared labels in the fastest part of the flight
      const isNb = NEIGH.some(([wd]) => wd === o.label) && o.cl.key === 'autumn';
      const pri = tokenish ? 100 : isNb ? 90 : (o.cl.key === 'autumn' ? 50 : 30) - q.z / 1e5;
      S4LB.push({ text: o.label, font: lf, x: lx, b: lb, size: tokenish && hand < 1 ? 24 : fsz, col: lcol, a: clamp(la * (tokenish ? 1 : 0.95)), pri, liang: o.label === '凉' ? q : null });
    }
    if (tokenish && back <= 0) {
      const hr = Math.max(10, r * 1.6);
      w.lineWidth = 1.5; w.strokeStyle = rgba(COL.cyan, 0.8 * E.expoOut(hand)); w.beginPath(); w.arc(q.sx, q.sy, hr + 8 * (1 - E.expoOut(hand)), 0, TAU); w.stroke();
    }
  }
  // neighbour lines from 秋天 (their distance pills block other labels)
  const qtP = projectPt(cam, S4D.qt, fs);
  const blockers = [];
  if (t >= 17.9 && back < 0.3) {
    const la = 1 - E.expoOut(seg(t, 19.4, 19.55));
    S4D.nb.forEach((o, j) => {
      const p = E.expoOut(seg(t, NEIGH_T[j], NEIGH_T[j] + 0.2));
      if (p <= 0.6) return;
      const b = projectPt(cam, o.p, fs);
      const ang = Math.atan2(b.y - qtP.y, b.x - qtP.x), nx = -Math.sin(ang), ny = Math.cos(ang), side = ny < 0 ? -1 : 1;
      const lxp = (qtP.x + b.x) / 2 + nx * 20 * side, lyp = (qtP.y + b.y) / 2 + ny * 20 * side;
      blockers.push({ box: [lxp - 30, lyp - 17, lxp + 30, lyp + 17], a: la * seg(p, 0.6, 1) });
    });
  }
  resolveS4Labels(blockers);
  if (t >= 17.9 && back < 0.3) {
    const la = 1 - E.expoOut(seg(t, 19.4, 19.55));
    S4D.nb.forEach((o, j) => {
      const T0 = NEIGH_T[j];
      const p = E.expoOut(seg(t, T0, T0 + 0.2));
      if (p <= 0) return;
      const b = projectPt(cam, o.p, fs);
      const ex = lerp(qtP.x, b.x, p), ey = lerp(qtP.y, b.y, p);
      const ang = Math.atan2(b.y - qtP.y, b.x - qtP.x);
      const s0 = 14, s1 = 10;
      w.strokeStyle = rgba(COL.cyan, 0.7 * la); w.lineWidth = 1.5;
      w.beginPath(); w.moveTo(qtP.x + Math.cos(ang) * s0, qtP.y + Math.sin(ang) * s0); w.lineTo(ex - Math.cos(ang) * s1 * p, ey - Math.sin(ang) * s1 * p); w.stroke();
      g.strokeStyle = rgba(COL.cyan, 0.35 * la); g.lineWidth = 3; g.beginPath(); g.moveTo(qtP.x, qtP.y); g.lineTo(ex, ey); g.stroke();
      if (p > 0.6) {
        const mx = (qtP.x + b.x) / 2, my = (qtP.y + b.y) / 2;
        const nx = -Math.sin(ang), ny = Math.cos(ang);
        const side = ny < 0 ? -1 : 1;
        const da = la * seg(p, 0.6, 1), lxp = mx + nx * 20 * side, lyp = my + ny * 20 * side;
        w.globalAlpha = da; rrect(w, lxp - 26, lyp - 13, 52, 26, 7); w.fillStyle = 'rgba(5,7,12,0.85)'; w.fill();
        w.font = FNT.mono(18); w.textAlign = 'center'; w.fillStyle = COL.ice;
        w.fillText(NEIGH_D[j], lxp, lyp + 6); w.textAlign = 'left'; w.globalAlpha = 1;
      }
    });
  }
  drawS4Labels(w, g, t, fade);
  s4Bokeh(w, t, cam, (1 - E.expoIn(seg(t, 19.4, 19.9))) * E.expoOut(seg(t, 15.7, 16.4)));
  // pull-back: token points -> spine anchors, labels -> card texts, cards form
  if (back > 0) drawS4ToList(t, R, cam, fs);
}
/* ---- label layout: higher priority labels win; others fade smoothly by how much they overlap ---- */
const S4LB = [];
function lbInk(L) { const w = textW(L.text, L.font); return [L.x - 1, L.b - 0.84 * L.size, L.x + w + 1, L.b + 0.12 * L.size]; }
// Labels never overlap: walking down the priority list, a label fades out as it comes within S4LR.gap px of any
// label (or distance pill) already placed, and is gone by the time the two would touch. The fade depends only on
// positions at time t, so it stays continuous from frame to frame without any stored state.
const S4LR = { gap: 16, gain: 20 };
function resolveS4Labels(blockers) {
  const acc = blockers.map(b => ({ box: b.box, w: Math.min(1, b.a * S4LR.gain) }));
  const order = S4LB.slice().sort((A, B) => B.pri - A.pri || B.a - A.a);
  for (const L of order) {
    const bx = lbInk(L);
    let s = 0;
    for (const A of acc) {
      const gap = Math.max(A.box[0] - bx[2], bx[0] - A.box[2], A.box[1] - bx[3], bx[1] - A.box[3]);   // < 0: overlapping
      if (gap >= S4LR.gap) continue;
      s = Math.max(s, A.w * (1 - smooth(gap / S4LR.gap)));
      if (s >= 1) break;
    }
    L.ea = L.a * (1 - s);
    if (L.ea > 0) acc.push({ box: bx, w: Math.min(1, L.ea * S4LR.gain) });
  }
}
function drawS4Labels(w, g, t, fade) {
  for (const L of S4LB) {
    if (!(L.ea > 0.012)) continue;
    w.font = L.font; w.fillStyle = L.col; w.globalAlpha = clamp(L.ea); w.textAlign = 'left';
    w.fillText(L.text, L.x, L.b);
    if (L.liang) {
      const b = E.expoOut(seg(t, 18.5, 18.8));
      if (b > 0) { g.font = L.font; g.globalAlpha = 0.9 * b * fade; g.fillStyle = COL.ice; g.fillText('凉', L.x, L.b); g.globalAlpha = 1; drawSprite(g, softDot('c', COL.ice), L.liang.sx, L.liang.sy, 34, 0.9 * b * fade); }
    }
  }
  w.globalAlpha = 1;
}
function softClampPt(p) {   // keep far-offscreen start points just outside the frame (limits fly-in speed)
  const dx = p.x - CX, dy = (p.y - CY) * 0.56, r = Math.hypot(dx, dy), R = 780;
  if (r < 1e-3) return p;
  const k = R * Math.tanh(r / R) / r;
  return { x: CX + dx * k, y: CY + dy * k / 0.56, z: p.z };
}
function projectPt(cam, X, fs) { const c = toCam(cam, [X[0] * fs, X[1] * fs, X[2] * fs]); return { x: CX + cam.f * c[0] / c[2], y: CY + cam.f * c[1] / c[2], z: c[2] }; }

function drawS4ToList(t, R, cam, fs) {
  const w = R.w, g = R.g;
  const e = E.expoInOut(seg(t, 19.4, 19.95));
  const cardG = E.expoOut(seg(t, 19.72, 20.0));
  // spine grows
  const sp = E.expoInOut(seg(t, 19.66, 20.0));
  const y0 = S5L.y0 - 36, y1 = S5L.y0 + S5L.dy * 7 + 36;
  if (sp > 0) { w.fillStyle = rgba(COL.text2, 0.55); w.fillRect(S5L.spine - 0.75, y0, 1.5, (y1 - y0) * sp); }
  for (let i = 0; i < 8; i++) {
    const row = S5L.rows[i];
    let x, y, lab = null;
    if (i < 7) {
      const o = S4D.tok[i];
      const p = softClampPt(projectPt(cam, o.p, fs));
      x = lerp(p.x, S5L.spine, e); y = lerp(p.y, row.yc, e);
      lab = o.label;
      // label -> card text
      const fsz = lerp(24, 48, e);
      const lf = S5L.font;
      const lx0 = p.x + 14, lb0 = p.y + cjkMid(FNT.pf(24, 400));
      const lx = lerp(lx0, row.tx, e), lb = lerp(lb0, row.tb, e);
      drawS5Card(w, g, i, cardG, cardG);
      // the flying label is hidden during the fastest part (no smeared text); the card text resolves in place
      const la = Math.max(1 - smooth(e / 0.18), smooth((e - 0.72) / 0.28));
      if (la > 0.01) { w.save(); w.globalAlpha = la; w.translate(lx, lb); w.scale(fsz / 48, fsz / 48); w.font = lf; w.fillStyle = mixHex(COL.iceX, COL.text, e); w.fillText(lab, 0, 0); w.restore(); w.globalAlpha = 1; }
      // dotted leader to the spine, as S5 draws it
      if (cardG > 0.01) { w.save(); w.setLineDash([2, 5]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.text2, 0.5 * cardG); w.beginPath(); w.moveTo(S5L.x + row.cw + 12, row.yc); w.lineTo(S5L.spine - 10, row.yc); w.stroke(); w.restore(); }
    } else {
      x = S5L.spine; y = row.yc;
      const ap = E.expoOut(seg(t, 19.6, 19.9));
      if (ap <= 0) continue;
      w.lineWidth = 1.5; w.strokeStyle = rgba(COL.cyan, 0.9 * ap * (1 - cardG * 0.5)); w.beginPath(); w.arc(x, y, 4 + 18 * (1 - ap) + 6, 0, TAU); w.stroke();
      drawS5Card(w, g, 7, cardG, cardG);
      if (cardG > 0.01) {
        let lx0 = S5L.x + row.cw + 12;
        w.globalAlpha = cardG; w.font = FNT.mono(18); w.fillStyle = COL.text2; w.fillText('NEXT', lx0 + 2, row.yc + 6); w.globalAlpha = 1;
        lx0 += textW('NEXT', FNT.mono(18)) + 14;
        w.save(); w.setLineDash([2, 5]); w.lineWidth = 1.5; w.strokeStyle = rgba(COL.text2, 0.5 * cardG); w.beginPath(); w.moveTo(lx0, row.yc); w.lineTo(S5L.spine - 10, row.yc); w.stroke(); w.restore();
        const ca = clamp(1.8 * (0.5 + 0.5 * Math.cos(TAU * (t - 20.0))) - 0.4) * cardG;
        w.fillStyle = rgba(COL.cyan, ca); w.fillRect(S5L.x + 26, row.yc - 18, 2, 36);
      }
    }
    // the point itself (becomes the spine anchor)
    const rr = lerp(6, 4, e);
    w.fillStyle = i < 7 ? COL.iceX : COL.cyan; w.beginPath(); w.arc(x, y, rr, 0, TAU); w.fill();
    drawSprite(g, softDot('c', COL.cyan), x, y, 22, 0.8);
  }
}
registerScene({ name: 'S4', t0: 15.5, t1: 20.0, draw: drawS4 });
