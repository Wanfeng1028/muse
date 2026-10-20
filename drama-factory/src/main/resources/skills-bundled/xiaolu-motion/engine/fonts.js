/* ==========================================================================
   xiaolu-motion · engine/fonts.js
   Font injection through FontFace(ArrayBuffer): the render driver resolves
   each face listed in the style tokens to a font file (extracting a single
   face from .ttc collections), serves the bytes, and the page registers them
   here. No @font-face url(), no file:// fetches -> no CORS problems, and the
   exact same bytes are used on every render.
   faces: [{family, url, weight, style, key}]
   ========================================================================== */
export async function loadFonts(faces) {
  const report = [];
  for (const f of faces) {
    const t0 = performance.now();
    const r = await fetch(f.url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`font ${f.key}: HTTP ${r.status}`);
    const buf = await r.arrayBuffer();
    const ff = new FontFace(f.family, buf, { weight: String(f.weight ?? 400), style: f.style || 'normal', display: 'block' });
    await ff.load();
    document.fonts.add(ff);
    report.push({ key: f.key, family: f.family, weight: f.weight, bytes: buf.byteLength, ms: Math.round(performance.now() - t0), status: ff.status });
  }
  await document.fonts.ready;
  return report;
}

/* proof that a family renders with the injected face and not a fallback:
   compare glyph advances against the generic fallback */
export function fontProbe(family, weight, sample = '剪映Skill字AI01') {
  const c = (typeof OffscreenCanvas !== 'undefined') ? new OffscreenCanvas(8, 8) : document.createElement('canvas');
  const x = c.getContext('2d');
  x.font = `${weight} 100px "${family}"`; const a = x.measureText(sample).width;
  x.font = `${weight} 100px monospace`; const b = x.measureText(sample).width;
  return { family, weight, width: Math.round(a * 10) / 10, fallbackWidth: Math.round(b * 10) / 10, check: document.fonts.check(`${weight} 100px "${family}"`, sample) };
}
