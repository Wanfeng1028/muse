// Sub-pixel camera renderer for the whiteboard edits (what a browser based compositor would
// do with a moving crop, without shipping 4K bitmaps through Chrome).
//
// For every output frame it samples the planned viewport [x0, y0, w] out of the 4K source
// with a separable Catmull-Rom kernel whose positions and weights are computed in floating
// point from the exact fractional viewport (no rounding to whole pixels anywhere), widened by
// the downscale ratio so downscaling is properly filtered (no aliasing). Y, U and V planes
// are resampled directly (4:2:0, limited range), so there is no colour conversion either.
//
// THIS COPY (subpixel_render_ov.mjs) also composites overlays (captions, headline) in the same
// pass, straight into the Y, U and V planes before the x264 encode: one encode, frame exact.
// overlays.json (from overlay_build.py): { layers: {name: {w, h, file}}, frames: [[[name, x, y], ...] per output frame] }
// Layers are straight alpha RGBA; colours go to BT.709 limited range, chroma blended at 4:2:0 with
// the 2x2 block's alpha weighted mean, layer positions on even pixels.
//
// Usage: node subpixel_render_ov.mjs <props.json> <out.mp4> <firstOutFrame> <lastOutFrame> [crf] [overlays.json]
// props.json: { src (absolute path), srcW, srcH, outW, outH, segments[{srcFrame,frames,outFrame}], camera[[x0,y0,w]], grade? }
// grade (optional): absolute path of the video's house grade .cube (grade.py lut, stamped by grade.py props). When set,
// the planes are resampled in float and graded (grade_lut.mjs) before rounding and before any overlay.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { makeGrader } from "./grade_lut.mjs";

const [, , propsPath, outPath, f0s, f1s, crf = "16", ovPath = ""] = process.argv;
const P = JSON.parse(fs.readFileSync(propsPath, "utf8"));
const { srcW: SW, srcH: SH, outW: OW, outH: OH, segments, camera } = P;
const F0 = +f0s, F1 = +f1s;
const FPS_N = 24000, FPS_D = 1001;

// ---------------------------------------------------------------- kernel
const catmull = (x) => {
  x = Math.abs(x);
  if (x < 1) return 1.5 * x * x * x - 2.5 * x * x + 1;
  if (x < 2) return -0.5 * x * x * x + 2.5 * x * x - 4 * x + 2;
  return 0;
};
// weights for one axis: n output samples, source positions start + (i + 0.5) * step - 0.5
function axisTable(n, start, step, srcLen) {
  const sc = Math.max(1, step); // widen the kernel when downscaling
  const support = 2 * sc;
  const taps = Math.ceil(2 * support) + 1;
  const idx = new Int32Array(n * taps), wt = new Float32Array(n * taps);
  for (let i = 0; i < n; i++) {
    const c = start + (i + 0.5) * step - 0.5;
    const lo = Math.floor(c - support) + 1;
    let sum = 0;
    for (let k = 0; k < taps; k++) {
      const s = lo + k;
      const w = catmull((s - c) / sc);
      idx[i * taps + k] = Math.min(srcLen - 1, Math.max(0, s));
      wt[i * taps + k] = w;
      sum += w;
    }
    for (let k = 0; k < taps; k++) wt[i * taps + k] /= sum;
  }
  return { idx, wt, taps };
}

let ACC = new Float32Array(1);
// resample one plane: src (Uint8Array, sw x sh) -> dst (Uint8Array, dw x dh)
function resamplePlane(src, sw, sh, dst, dw, dh, x0, y0, vw, vh, tmp, asFloat = false) {
  const H = axisTable(dw, x0, vw / dw, sw);
  const V = axisTable(dh, y0, vh / dh, sh);
  // rows actually needed
  let rmin = sh, rmax = 0;
  for (let i = 0; i < V.idx.length; i++) { const r = V.idx[i]; if (r < rmin) rmin = r; if (r > rmax) rmax = r; }
  const nr = rmax - rmin + 1;
  const T = tmp.length >= nr * dw ? tmp : new Float32Array(nr * dw);
  const ht = H.taps, hi = H.idx, hw = H.wt;
  for (let r = 0; r < nr; r++) {
    const row = (rmin + r) * sw, orow = r * dw;
    for (let i = 0; i < dw; i++) {
      let acc = 0;
      const b = i * ht;
      for (let k = 0; k < ht; k++) acc += hw[b + k] * src[row + hi[b + k]];
      T[orow + i] = acc;
    }
  }
  const vt = V.taps, vi = V.idx, vwt = V.wt;
  const acc = ACC.length >= dw ? ACC : (ACC = new Float32Array(dw));
  for (let j = 0; j < dh; j++) {
    const b = j * vt, orow = j * dw;
    acc.fill(asFloat ? 0 : 0.5, 0, dw);
    for (let k = 0; k < vt; k++) {
      const wk = vwt[b + k];
      if (wk === 0) continue;
      const base = (vi[b + k] - rmin) * dw;
      for (let i = 0; i < dw; i++) acc[i] += wk * T[base + i];
    }
    if (asFloat) for (let i = 0; i < dw; i++) dst[orow + i] = acc[i];
    else for (let i = 0; i < dw; i++) { const v = acc[i]; dst[orow + i] = v < 0 ? 0 : v > 255 ? 255 : v; }
  }
  return T;
}

// ---------------------------------------------------------------- overlays
const OV = ovPath ? JSON.parse(fs.readFileSync(ovPath, "utf8")) : null;
const ovDir = ovPath ? ovPath.slice(0, ovPath.lastIndexOf("/") + 1) : "";
const ovCache = new Map();
function ovLayer(name) {
  if (ovCache.has(name)) return ovCache.get(name);
  const L = OV.layers[name];
  const buf = fs.readFileSync(ovDir + L.file);
  const { w, h } = L;
  if (buf.length !== w * h * 4) throw new Error(`overlay ${name}: ${buf.length} bytes, expected ${w * h * 4}`);
  // per pixel premultiplied Y and alpha; per 2x2 block premultiplied Cb, Cr and mean alpha
  const Yp = new Float32Array(w * h), A = new Float32Array(w * h);
  const cw = w >> 1, ch = h >> 1;
  const Up = new Float32Array(cw * ch), Vp = new Float32Array(cw * ch), Ac = new Float32Array(cw * ch);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    const r = buf[i], g = buf[i + 1], b = buf[i + 2], a = buf[i + 3] / 255;
    const Y = 16 + (219 * (0.2126 * r + 0.7152 * g + 0.0722 * b)) / 255;
    const Cb = 128 + (224 * (-0.11457 * r - 0.38543 * g + 0.5 * b)) / 255;
    const Cr = 128 + (224 * (0.5 * r - 0.45415 * g - 0.04585 * b)) / 255;
    Yp[y * w + x] = Y * a; A[y * w + x] = a;
    const cx = x >> 1, cy = y >> 1;
    if (cx < cw && cy < ch) { const j = cy * cw + cx; Up[j] += (Cb * a) / 4; Vp[j] += (Cr * a) / 4; Ac[j] += a / 4; }
  }
  const o = { w, h, cw, ch, Yp, A, Up, Vp, Ac };
  ovCache.set(name, o);
  if (ovCache.size > 400) ovCache.delete(ovCache.keys().next().value);
  return o;
}
function composite(dst, f) {
  const list = OV.frames[f] || [];
  for (const [name, x0, y0] of list) {
    if ((x0 | y0) & 1) throw new Error(`overlay ${name} at odd position ${x0},${y0}`);
    const L = ovLayer(name);
    for (let y = 0; y < L.h; y++) {
      const oy_ = y0 + y; if (oy_ < 0 || oy_ >= OH) continue;
      for (let x = 0; x < L.w; x++) {
        const ox_ = x0 + x; if (ox_ < 0 || ox_ >= OW) continue;
        const a = L.A[y * L.w + x]; if (a === 0) continue;
        const k = oy_ * OW + ox_;
        const v = dst[k] * (1 - a) + L.Yp[y * L.w + x] + 0.5;
        dst[k] = v > 255 ? 255 : v;
      }
    }
    const cx0 = x0 >> 1, cy0 = y0 >> 1, OCW = OW >> 1, OCH = OH >> 1;
    for (let y = 0; y < L.ch; y++) {
      const oy_ = cy0 + y; if (oy_ < 0 || oy_ >= OCH) continue;
      for (let x = 0; x < L.cw; x++) {
        const ox_ = cx0 + x; if (ox_ < 0 || ox_ >= OCW) continue;
        const a = L.Ac[y * L.cw + x]; if (a === 0) continue;
        const k = oy_ * OCW + ox_;
        dst[oy + k] = dst[oy + k] * (1 - a) + L.Up[y * L.cw + x] + 0.5;
        dst[oy + oc + k] = dst[oy + oc + k] * (1 - a) + L.Vp[y * L.cw + x] + 0.5;
      }
    }
  }
}

// ---------------------------------------------------------------- io
const ySize = SW * SH, cSize = (SW / 2) * (SH / 2), frameSize = ySize + 2 * cSize;
const oy = OW * OH, oc = (OW / 2) * (OH / 2), outSize = oy + 2 * oc;

// The raw INPUT is tagged with the output's matrix and range: with an untagged input, ffmpeg 8 auto-inserts
// a scale (csp unknown -> bt709, range unknown -> tv) that re-converts every pixel (measured: luma
// -1.75 codes on a whiteboard frame, skin hue turned about 2 degrees; tagged = bit exact at crf 0).
// Only matrix and range go on the input, NOT primaries or transfer: those would reach the H.264 header
// (VUI 1,1,1 instead of 2,2,1), and a clip made with the other header (an intro or an end card, say)
// could no longer be stream copied onto a reel.
const enc = spawn("ffmpeg", ["-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", `${OW}x${OH}`,
  "-r", `${FPS_N}/${FPS_D}`, "-colorspace", "bt709", "-color_range", "tv", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p",
  "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
  "-x264-params", "keyint=96:min-keyint=24", "-movflags", "+faststart", outPath], { stdio: ["pipe", "inherit", "inherit"] });
const encDone = new Promise((res, rej) => enc.on("close", (c) => (c === 0 ? res() : rej(new Error(`encoder exit ${c}`)))));
const writeOut = (buf) => new Promise((res) => (enc.stdin.write(buf) ? res() : enc.stdin.once("drain", res)));

// pieces: (srcFrame, count, outFrame) clipped to [F0, F1]
const pieces = [];
for (const s of segments) {
  const a = Math.max(F0, s.outFrame), b = Math.min(F1, s.outFrame + s.frames - 1);
  if (a <= b) pieces.push({ srcFrame: s.srcFrame + (a - s.outFrame), count: b - a + 1, outFrame: a });
}

function decoder(p) {
  // accurate input seek a quarter frame before the wanted frame: the first frame kept is srcFrame
  const t = ((p.srcFrame - 0.25) * FPS_D) / FPS_N;
  const d = spawn("ffmpeg", ["-v", "error", "-hwaccel", "videotoolbox", "-ss", t.toFixed(6), "-i", P.src,
    "-map", "0:v:0", "-frames:v", String(p.count), "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], { stdio: ["ignore", "pipe", "inherit"] });
  const chunks = []; let have = 0; let waiting = null; let ended = false;
  d.stdout.on("data", (c) => { chunks.push(c); have += c.length; if (have >= frameSize * 3) d.stdout.pause(); if (waiting) { const w = waiting; waiting = null; w(); } });
  d.stdout.on("end", () => { ended = true; if (waiting) { const w = waiting; waiting = null; w(); } });
  async function next() {
    while (have < frameSize && !ended) await new Promise((r) => (waiting = r));
    if (have < frameSize) return null;
    const buf = Buffer.allocUnsafe(frameSize); let off = 0;
    while (off < frameSize) {
      const c = chunks[0]; const take = Math.min(c.length, frameSize - off);
      c.copy(buf, off, 0, take); off += take;
      if (take === c.length) chunks.shift(); else chunks[0] = c.subarray(take);
    }
    have -= frameSize; if (have < frameSize * 3) d.stdout.resume();
    return buf;
  }
  return { next, proc: d };
}

const out = Buffer.allocUnsafe(outSize);
const GR = P.grade ? makeGrader(P.grade, OW, OH) : null;
let tmp = new Float32Array(1);
let done = 0; const t0 = Date.now();
for (const p of pieces) {
  const dec = decoder(p);
  for (let k = 0; k < p.count; k++) {
    const f = dec.next ? await dec.next() : null;
    if (!f) throw new Error(`decoder ran short at piece src ${p.srcFrame} frame ${k}/${p.count}`);
    const [x0, y0, w] = camera[p.outFrame + k];
    const h = (w * OH) / OW;
    const Y = f.subarray(0, ySize), U = f.subarray(ySize, ySize + cSize), V = f.subarray(ySize + cSize);
    if (GR) {
      tmp = resamplePlane(Y, SW, SH, GR.FY, OW, OH, x0, y0, w, h, tmp, true);
      tmp = resamplePlane(U, SW / 2, SH / 2, GR.FU, OW / 2, OH / 2, x0 / 2, y0 / 2, w / 2, h / 2, tmp, true);
      tmp = resamplePlane(V, SW / 2, SH / 2, GR.FV, OW / 2, OH / 2, x0 / 2, y0 / 2, w / 2, h / 2, tmp, true);
      GR.apply(out);
    } else {
      tmp = resamplePlane(Y, SW, SH, out.subarray(0, oy), OW, OH, x0, y0, w, h, tmp);
      tmp = resamplePlane(U, SW / 2, SH / 2, out.subarray(oy, oy + oc), OW / 2, OH / 2, x0 / 2, y0 / 2, w / 2, h / 2, tmp);
      tmp = resamplePlane(V, SW / 2, SH / 2, out.subarray(oy + oc), OW / 2, OH / 2, x0 / 2, y0 / 2, w / 2, h / 2, tmp);
    }
    if (OV) composite(out, p.outFrame + k);
    await writeOut(Buffer.from(out));
    done++;
    if (done % 240 === 0) process.stderr.write(`${outPath.split("/").pop()}: ${done}/${F1 - F0 + 1} frames, ${(done / ((Date.now() - t0) / 1000)).toFixed(1)} fps\n`);
  }
  dec.proc.kill();
}
enc.stdin.end();
await encDone;
process.stderr.write(`${outPath.split("/").pop()}: done ${done} frames in ${((Date.now() - t0) / 1000).toFixed(1)} s${GR ? `, graded ${P.grade.split("/").pop()}` : ""}\n`);
