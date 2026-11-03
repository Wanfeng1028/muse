// Normalized cross-correlation of two s16le mono PCM files.
// Usage: node xcorr.mjs cam.raw wav.raw sampleRate maxLagMs
// Positive lag L means wav[n] best matches cam[n+L]: the polished audio is EARLY by L (needs delaying by L).
import fs from 'fs';
const [,, a, b, srS, lagS] = process.argv;
const sr = +srS, maxLag = Math.round(+lagS * sr / 1000);
const rd = f => { const buf = fs.readFileSync(f); const x = new Float64Array(buf.length / 2); for (let i = 0; i < x.length; i++) x[i] = buf.readInt16LE(i * 2); const m = x.reduce((s, v) => s + v, 0) / x.length; for (let i = 0; i < x.length; i++) x[i] -= m; return x; };
const cam = rd(a), wav = rd(b);
const n = Math.min(cam.length, wav.length);
let best = -Infinity, bestL = 0; const vals = new Map();
for (let L = -maxLag; L <= maxLag; L++) {
  let s = 0, ec = 0, ew = 0;
  const i0 = Math.max(0, -L), i1 = Math.min(n, n - L);
  for (let i = i0; i < i1; i++) { const c = cam[i + L], w = wav[i]; s += c * w; ec += c * c; ew += w * w; }
  const r = s / Math.sqrt(ec * ew);
  vals.set(L, r);
  if (r > best) { best = r; bestL = L; }
}
const ym = vals.get(bestL - 1), y0 = vals.get(bestL), yp = vals.get(bestL + 1);
const frac = (ym !== undefined && yp !== undefined) ? 0.5 * (ym - yp) / (ym - 2 * y0 + yp) : 0;
// second best peak away from main (sanity)
let second = -Infinity; for (const [L, r] of vals) if (Math.abs(L - bestL) > sr * 0.02 && r > second) second = r;
console.log(JSON.stringify({ lagSamples: bestL + frac, lagMs: +((bestL + frac) / sr * 1000).toFixed(3), peakR: +best.toFixed(4), secondPeakR: +second.toFixed(4) }));
