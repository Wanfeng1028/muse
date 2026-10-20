// Measures the camera motion actually present in a rendered video, frame to frame, and
// compares it with the plan. Independent of the renderer: it only reads output pixels.
//
// For each consecutive pair of frames it block-matches ~300 textured blocks (coarse search
// at half resolution, then a +-3 px search at full resolution and a parabolic sub-pixel
// fit), then fits p' = s * p + t (zoom about the frame centre plus a shift) with RANSAC, so
// the speaker's moving body is rejected as outliers and only the static board and wall drive the fit.
//
// Usage: node measure_motion.mjs <video> <firstFrame> <lastFrame> <camera.json> [outW outH]
// camera.json: {"camera": [[x0, y0, w], ...]} per output frame (4K source px)
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const [, , video, f0s, f1s, camPath, ow = "1920", oh = "1080", offs = "0"] = process.argv;
const OFF = +offs; // camera index = file frame + OFF
const F0 = +f0s, F1 = +f1s, W = +ow, H = +oh;
const fps = 24000 / 1001;
const camAll = JSON.parse(fs.readFileSync(camPath, "utf8")).camera;
const cam = new Proxy([], { get: (t, k) => (typeof k === "string" && /^\d+$/.test(k) ? camAll[+k + OFF] : undefined) });

const n = F1 - F0 + 1;
const raw = execFileSync("ffmpeg", ["-v", "error", "-i", video, "-vf", `select=between(n\\,${F0}\\,${F1}),format=gray`,
  "-vsync", "0", "-f", "rawvideo", "-"], { maxBuffer: 2 ** 31 });
if (raw.length !== n * W * H) throw new Error(`got ${raw.length} bytes, expected ${n * W * H}`);
const frames = [...Array(n)].map((_, i) => raw.subarray(i * W * H, (i + 1) * W * H));

const half = (img) => {
  const w = W >> 1, h = H >> 1, o = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = 2 * y * W + 2 * x;
    o[y * w + x] = (img[i] + img[i + 1] + img[i + W] + img[i + W + 1]) / 4;
  }
  return o;
};

const B = 20; // half block size at full res (41 x 41)
function matchPair(a, b, pred) {
  const ah = half(a), bh = half(b), w2 = W >> 1;
  const res = [];
  for (let cy = 90; cy < H - 90; cy += 48) for (let cx = 90; cx < W - 90; cx += 48) {
    // texture check
    let s = 0, s2 = 0;
    for (let y = -B; y <= B; y += 2) for (let x = -B; x <= B; x += 2) { const v = a[(cy + y) * W + cx + x]; s += v; s2 += v * v; }
    const m = 441, sd = Math.sqrt(Math.max(0, s2 / m - (s / m) ** 2));
    if (sd < 10) continue;
    // coarse: half resolution, search around the predicted displacement +-12 half px
    const px = pred.s * (cx - W / 2) + W / 2 + pred.tx - cx, py = pred.s * (cy - H / 2) + H / 2 + pred.ty - cy;
    const hx = cx >> 1, hy = cy >> 1, hb = B >> 1;
    let best = Infinity, bx = 0, by = 0;
    const R = 12;
    for (let dy = Math.round(py / 2) - R; dy <= Math.round(py / 2) + R; dy++) for (let dx = Math.round(px / 2) - R; dx <= Math.round(px / 2) + R; dx++) {
      let e = 0;
      for (let y = -hb; y <= hb; y++) {
        const ra = (hy + y) * w2 + hx, rb = (hy + y + dy) * w2 + hx + dx;
        for (let x = -hb; x <= hb; x++) { const d = ah[ra + x] - bh[rb + x]; e += d * d; }
        if (e > best) break;
      }
      if (e < best) { best = e; bx = dx; by = dy; }
    }
    // fine: full res +-3 around 2x coarse, SSD surface, parabolic sub-pixel
    const ssd = (dx, dy) => {
      let e = 0;
      for (let y = -B; y <= B; y++) {
        const ra = (cy + y) * W + cx, rb = (cy + y + dy) * W + cx + dx;
        for (let x = -B; x <= B; x++) { const d = a[ra + x] - b[rb + x]; e += d * d; }
      }
      return e;
    };
    let fb = Infinity, fx = 0, fy = 0;
    for (let dy = 2 * by - 3; dy <= 2 * by + 3; dy++) for (let dx = 2 * bx - 3; dx <= 2 * bx + 3; dx++) {
      if (cy + dy - B < 0 || cy + dy + B >= H || cx + dx - B < 0 || cx + dx + B >= W) continue;
      const e = ssd(dx, dy); if (e < fb) { fb = e; fx = dx; fy = dy; }
    }
    const ex0 = ssd(fx - 1, fy), ex2 = ssd(fx + 1, fy), ey0 = ssd(fx, fy - 1), ey2 = ssd(fx, fy + 1);
    const sx = (ex0 - ex2) / (2 * (ex0 - 2 * fb + ex2)), sy = (ey0 - ey2) / (2 * (ey0 - 2 * fb + ey2));
    if (!isFinite(sx) || !isFinite(sy) || Math.abs(sx) > 1 || Math.abs(sy) > 1) continue;
    res.push({ x: cx - W / 2, y: cy - H / 2, dx: fx + sx, dy: fy + sy });
  }
  return res;
}

// least squares for d = (s - 1) p + t
function fit(pts) {
  let Sxx = 0, Sx = 0, Sy = 0, Sdx = 0, Sdy = 0, Sxd = 0, N = pts.length;
  for (const p of pts) { Sxx += p.x * p.x + p.y * p.y; Sx += p.x; Sy += p.y; Sdx += p.dx; Sdy += p.dy; Sxd += p.x * p.dx + p.y * p.dy; }
  // unknowns a, tx, ty: normal equations
  const A = [[Sxx, Sx, Sy], [Sx, N, 0], [Sy, 0, N]], b = [Sxd, Sdx, Sdy];
  // solve 3x3
  const det = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const D = det(A);
  const col = (k) => A.map((r, i) => r.map((v, j) => (j === k ? b[i] : v)));
  return { a: det(col(0)) / D, tx: det(col(1)) / D, ty: det(col(2)) / D };
}
function ransac(pts) {
  let best = null, bestIn = [];
  let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
  for (let it = 0; it < 400; it++) {
    const s = [pts[Math.floor(rnd() * pts.length)], pts[Math.floor(rnd() * pts.length)], pts[Math.floor(rnd() * pts.length)]];
    const m = fit(s);
    const inl = pts.filter((p) => Math.hypot(m.a * p.x + m.tx - p.dx, m.a * p.y + m.ty - p.dy) < 0.6);
    if (inl.length > bestIn.length) { bestIn = inl; best = m; }
  }
  const m = fit(bestIn);
  const resid = bestIn.map((p) => Math.hypot(m.a * p.x + m.tx - p.dx, m.a * p.y + m.ty - p.dy));
  return { ...m, inliers: bestIn.length, total: pts.length, rms: Math.sqrt(resid.reduce((s, r) => s + r * r, 0) / resid.length) };
}

// plan: output px p_out = (p_src - (x0,y0)) * W / w  ->  frame f to f+1 (centre origin)
const planStep = (f) => {
  const [x0a, y0a, wa] = cam[f], [x0b, y0b, wb] = cam[f + 1];
  const s = wa / wb, k = W / wb;
  // p_b = s * p_a + ((x0a - x0b) * k) in top-left origin; convert to centre origin
  const tx = (x0a - x0b) * k + (s - 1) * (W / 2), ty = (y0a - y0b) * k + (s - 1) * (H / 2);
  return { s, tx, ty };
};

const rows = [];
let cumS = 1;
for (let i = 0; i < n - 1; i++) {
  const f = F0 + i;
  const p = planStep(f);
  const m = ransac(matchPair(frames[i], frames[i + 1], p));
  cumS *= 1 + m.a;
  rows.push({ frame: f + OFF, t: +((f + OFF) / fps).toFixed(3), plan_scale: +(3840 / cam[f + 1][2]).toFixed(5),
    plan_step_s: +p.s.toFixed(5), meas_step_s: +(1 + m.a).toFixed(5),
    plan_tx: +p.tx.toFixed(2), meas_tx: +m.tx.toFixed(2), plan_ty: +p.ty.toFixed(2), meas_ty: +m.ty.toFixed(2),
    meas_cum_scale: +(cumS * 3840 / cam[F0][2]).toFixed(5), inliers: `${m.inliers}/${m.total}`, rms_px: +m.rms.toFixed(3) });
}
console.log(JSON.stringify(rows));
