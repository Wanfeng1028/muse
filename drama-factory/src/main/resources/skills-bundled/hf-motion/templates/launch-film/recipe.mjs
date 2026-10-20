// launch-film recipe: validation, scene plan, plugin assets, music args.
// Read by scripts/scaffold.mjs; never copied into the project.
//
// The skeleton is a fixed 54 beats; parameters only swap content. index.html
// re-derives the length from bpm only to refuse to build when the static
// attributes and CONFIG disagree.

// GSAP is taken from the official hyperframes plugin at scaffold time (its own
// standard license), never redistributed from this repo. The fonts (Archivo,
// Geist; SIL OFL 1.1, licence beside each) and the placeholder photos (drawn
// for this repo by scripts/make_photos.py) are part of the template.
// Geist comes from templates/_shared (also used by ui-morph).
export const sharedAssets = ["assets/fonts/geist/Geist-Variable.woff2", "assets/fonts/geist/OFL.txt"];
export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};

// photos=a.jpg|b.jpg|... copies each file to assets/<basename>.
export const userFiles = ["photos"];

export const canvas = { width: 1440, height: 1440 };
export const BEATS = 54;
export const limits = { photos: [9, 12], bpm: [90, 150], sizes: [2, 4], frameColors: [2, 3] };

const HEX = /^#[0-9a-fA-F]{6}$/;
// Latin only: the bundled Archivo / Geist subsets cover Basic Latin + Latin-1.
const LATIN = /^[\x20-\x7E -ÿ]+$/;
const TEXT = { openLabel: 16, lockDate: 24, trackTitle: 28, trackArtist: 28, landingHeadline: 40, productName: 24, orderLabel: 18 };

const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
export const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

export function validate(c) {
  const err = [];
  const latin = (k, v, max) => {
    if (typeof v !== "string" || !v.trim() || v !== v.trim()) err.push(`${k} must be a non-empty string without leading/trailing spaces`);
    else if (!LATIN.test(v)) err.push(`${k} must be Latin text (the bundled fonts cover Basic Latin + Latin-1 only)`);
    else if ([...v].length > max) err.push(`${k} is at most ${max} characters, got ${[...v].length}`);
  };
  if (typeof c.wordmark !== "string" || !/^[A-Za-z]{3,9}$/.test(c.wordmark)) err.push(`wordmark must be one Latin word of 3..9 letters (A-Z, a-z), got '${c.wordmark}'`);
  if (typeof c.glassWord !== "string" || !/^[A-Za-z]{3,8}$/.test(c.glassWord)) err.push(`glassWord must be one Latin word of 3..8 letters, got '${c.glassWord}'`);
  if (typeof c.lockTime !== "string" || !/^[0-9]{1,2}:[0-9]{2}$/.test(c.lockTime)) err.push(`lockTime must look like 9:41, got '${c.lockTime}'`);
  for (const [k, max] of Object.entries(TEXT)) latin(k, c[k], max);
  if (!Array.isArray(c.steps) || c.steps.length !== 4) err.push(`steps needs exactly 4 items (ordered|printing|shipping|delivered), got ${Array.isArray(c.steps) ? c.steps.length : -1}`);
  else c.steps.forEach((s, i) => latin(`steps[${i}]`, s, 14));
  const [slo, shi] = limits.sizes;
  if (!Array.isArray(c.sizes) || c.sizes.length < slo || c.sizes.length > shi) err.push(`sizes needs ${slo}..${shi} items, got ${Array.isArray(c.sizes) ? c.sizes.length : -1}`);
  else c.sizes.forEach((s, i) => latin(`sizes[${i}]`, s, 6));
  const [flo, fhi] = limits.frameColors;
  const fc = c.frameColors;
  if (!Array.isArray(fc) || fc.length < flo || fc.length > fhi) err.push(`frameColors needs ${flo}..${fhi} items, got ${Array.isArray(fc) ? fc.length : -1}`);
  else if (fc.some((x) => !["paper", "charcoal", "red"].includes(x)) || new Set(fc).size !== fc.length) err.push(`frameColors must be distinct palette names: paper, charcoal, red`);
  const [plo, phi] = limits.photos;
  const ph = c.photos;
  if (!Array.isArray(ph) || ph.length < plo || ph.length > phi) err.push(`photos needs ${plo}..${phi} images, got ${Array.isArray(ph) ? ph.length : -1}`);
  else ph.forEach((p, i) => { if (typeof p !== "string" || !/^assets\/[^\\]+\.(jpe?g|png|webp)$/i.test(p)) err.push(`photos[${i}] must be a .jpg/.png/.webp under assets/; pass photos=a.jpg|b.jpg|...`); });
  const [blo, bhi] = limits.bpm;
  if (!(c.bpm >= blo && c.bpm <= bhi)) err.push(`bpm must be ${blo}..${bhi}, got ${c.bpm}`);
  let hexOk = true;
  for (const k of ["paper", "charcoal", "red"]) {
    if (!HEX.test(c[k] ?? "")) { err.push(`${k} must be a #rrggbb colour`); hexOk = false; }
  }
  if (hexOk) {
    for (const k of ["paper", "charcoal"]) {
      const r = contrast(c.red, c[k]);
      if (r < 3) err.push(`red must keep 3:1 contrast on ${k}, got ${r.toFixed(2)}:1`);
    }
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// One fixed 54-beat scene -> { elementId: [data-start, data-duration] }.
export function timing(c) {
  const total = r((BEATS * 60) / c.bpm);
  return { at: { stage: [0, total], film: [0, total], music: [0, total] }, total };
}

export function musicArgs(c) {
  return ["scripts/make_music.py", "--bpm", String(c.bpm), "--glass-letters", String([...c.glassWord].length),
    "--digits", String([...c.lockTime].length), "--seed", "719", "--out", "assets/music.wav"];
}
