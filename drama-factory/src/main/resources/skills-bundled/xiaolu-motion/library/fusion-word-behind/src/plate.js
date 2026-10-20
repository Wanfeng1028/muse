/* ==========================================================================
   plate.js — footage access for the fusion shots (identical in every fusion-* entry)
   The kit's prep step writes the plate segment as PNG frames (and, per shot,
   person cut-outs, a background fill, a clean plate, Vision JSON) into the
   work dir, served at /work/. Frames are decoded without colour conversion
   (the footage pixels stay exactly as decoded from BT.709) and loaded a chunk
   at a time: the kit calls window.__XM_PRELOAD(a, b) before rendering frames
   [a, b), so draw() stays synchronous and every sub-frame of frame i sees
   plate frame i.
   ========================================================================== */
export const PLATE = { start: 0, layers: ['plate'], frames: new Map(), clean: null, data: {}, ready: false };

const pad = n => String(n).padStart(6, '0');
async function bmp(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return createImageBitmap(await r.blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'default' });
}
async function preload(a, b) {
  for (const [k, v] of PLATE.frames) if (k < a - 1) { for (const x of Object.values(v)) x.close(); PLATE.frames.delete(k); }
  const jobs = [];
  for (let i = a; i < b; i++) {
    if (PLATE.frames.has(i)) continue;
    jobs.push((async () => {
      const o = {};
      for (const L of PLATE.layers) o[L] = await bmp(`/work/${L}/${pad(PLATE.start + i)}.png`);
      PLATE.frames.set(i, o);
    })());
  }
  await Promise.all(jobs);
}
/* layers: sub-folders of the work dir to load per frame ('plate', 'person', 'bg');
   json: Vision data files to load once ('faces', 'hands'); clean: also load clean.png */
export async function preparePlate(p, { layers = ['plate'], json = [], clean = false } = {}) {
  if (PLATE.ready && PLATE.start === p.plate_start) return PLATE;
  PLATE.start = p.plate_start; PLATE.layers = layers;
  for (const name of json) {
    const r = await fetch(`/work/${name}.json`, { cache: 'no-store' });
    if (!r.ok) throw new Error(`/work/${name}.json: HTTP ${r.status} (run build.py prep first)`);
    const arr = await r.json();
    PLATE.data[name] = new Map(arr.map(d => [d.frame - p.plate_start, d]));   // keyed by local frame
  }
  if (clean) PLATE.clean = await bmp('/work/clean.png');
  window.__XM_PRELOAD = preload;
  PLATE.ready = true;
  return PLATE;
}
export function frameAt(t, fps) {
  const i = Math.floor(t * fps + 1e-6);
  return PLATE.frames.get(i) || PLATE.frames.get(i - 1) || null;
}
/* median face box over the shot (for layout decisions that must never touch the face) */
export function faceStats() {
  const F = PLATE.data.faces;
  if (!F) return null;
  const boxes = [...F.values()].map(d => d.faces && d.faces[0] && d.faces[0].box).filter(Boolean);
  const med = k => { const v = boxes.map(b => b[k]).sort((a, b) => a - b); return v[v.length >> 1]; };
  const ext = (k, f) => boxes.reduce((m, b) => f(m, b[k]), boxes[0][k]);
  return { n: boxes.length, x: med(0), y: med(1), w: med(2), h: med(3),
    minX: ext(0, Math.min), minY: ext(1, Math.min), maxR: boxes.reduce((m, b) => Math.max(m, b[0] + b[2]), 0), maxB: boxes.reduce((m, b) => Math.max(m, b[1] + b[3]), 0) };
}
