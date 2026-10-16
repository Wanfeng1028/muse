// painted-provider 通用场景模板。占位符：__TITLE__（镜头描述）、__DUR__（时长秒）。
// 由 PaintedAnimationVideoProvider 替换后写入工作目录 src/scenes/shot.js。
(() => {
  const TITLE = __TITLE__;
  const DUR = __DUR__;

  function sky(t) {
    boilSeed('psky');
    // 水彩天空：三层横向 wash
    paint(rectPts(-60, -60, W + 120, H * 0.45), { wash: '#A8C8E8', washOp: 200, ink: null });
    paint(rectPts(-60, H * 0.35, W + 120, H * 0.35), { wash: '#D8E8F5', washOp: 180, ink: null });
    paint(rectPts(-60, H * 0.6, W + 120, H * 0.5), { wash: '#F5E8D0', washOp: 160, ink: null });
    // 太阳
    boilSeed('psun');
    const sx = W * 0.78, sy = H * 0.22;
    paint(ellPts(sx, sy, 90, 90, 28), { wash: '#FFE9A8', washOp: 220, ink: null });
    paint(ellPts(sx, sy, 60, 60, 24), { fill: '#FFD970', fillOp: 200, ink: null });
    // 云（随时间漂移）
    for (let i = 0; i < 4; i++) {
      boilSeed('pcloud' + i);
      const cx = ((hash(i * 7) * (W + 400) + t * (20 + i * 8)) % (W + 400)) - 200;
      const cy = H * (0.12 + hash(i * 13) * 0.25);
      paint(ellPts(cx, cy, 120 + hash(i) * 60, 36, 20), { wash: '#FFFFFF', washOp: 170, ink: null });
      paint(ellPts(cx + 60, cy + 10, 80, 28, 18), { wash: '#FFFFFF', washOp: 150, ink: null });
    }
  }

  function hills(t) {
    boilSeed('phills');
    paint(ellPts(W * 0.25, H * 1.05, W * 0.45, H * 0.35, 36), { wash: '#9DBE8C', washOp: 200, ink: null });
    paint(ellPts(W * 0.8, H * 1.1, W * 0.5, H * 0.4, 36), { wash: '#7BA86B', washOp: 200, ink: null });
    // 草叶摆动
    for (let i = 0; i < 24; i++) {
      const x = hash(i * 3) * W, y = H * (0.78 + hash(i * 5) * 0.18);
      const sw = Math.sin(t * 2 + i) * 6;
      inkLine([[x, y], [x + sw, y - 26 - hash(i) * 14]], 1.2, '#5A8A4A', 'inkfine', 0.5);
    }
  }

  function titleCard(t) {
    // 标题文字：淡入 → 停留 → 淡出
    const aIn = seg(t, 0.3, 1.2), aOut = seg(t, DUR - 1.2, DUR - 0.3);
    const alpha = Math.min(aIn, 1 - aOut);
    if (alpha <= 0.01) return;
    outX.save();
    outX.globalAlpha = alpha;
    outX.font = '600 64px "Noto Serif CJK SC", serif';
    outX.textAlign = 'center';
    outX.fillStyle = '#2B2B2B';
    // 自动换行
    const words = TITLE.split('');
    const lines = [];
    let cur = '';
    for (const ch of words) {
      cur += ch;
      if (cur.length >= 14) { lines.push(cur); cur = ''; }
    }
    if (cur) lines.push(cur);
    lines.slice(0, 3).forEach((ln, i) => {
      outX.fillText(ln, W / 2, H * 0.42 + i * 84);
    });
    outX.restore();
  }

  function shotMain(t) {
    sky(t);
    hills(t);
    titleCard(t);
  }

  shots([[0, shotMain]]);
})();
