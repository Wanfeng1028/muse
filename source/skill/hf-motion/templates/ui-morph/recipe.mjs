// ui-morph recipe: validation, scene plan, plugin assets, music args.
// Read by scripts/scaffold.mjs; never copied into the project.
//
// The skeleton is fixed: 28 beats (7 bars), one shape morphing through 14
// states. Parameters swap the content only; bpm scales the whole grid.
// index.html re-derives the length only to refuse to build on a mismatch.

// GSAP is copied from the official hyperframes plugin at scaffold time
// (GreenSock standard license), never redistributed from this repo. No plugin
// SFX: the UI taps are synthesized into the music bed by scripts/make_music.py.
export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};

// Geist (SIL OFL 1.1, OFL.txt beside it) is shared with launch-film: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/geist/Geist-Variable.woff2", "assets/fonts/geist/OFL.txt"];

export const canvas = { width: 1440, height: 1440 };
export const BEATS = 28;
// Beats with a UI tap in the bed: clicks 0 6 15 17 18, drag grab/release 8 9 11 13,
// check 3, hover 21 22, Cmd K 23, toast 26. Fixed by the skeleton.
export const TAPS = [0, 3, 6, 8, 9, 11, 13, 15, 17, 18, 21, 22, 23, 26];

// [min, max] characters per text key (measured so nothing overflows at the
// maximum, then shrink-to-fit takes care of wide glyphs).
export const limits = {
  buttonLabel: [1, 16], trackTitle: [1, 24], trackArtist: [1, 24], chartTitle: [1, 28],
  paletteQuery: [1, 12], toastText: [1, 24], tab: [1, 10], paletteItem: [1, 20],
  tabs: [3, 3], chartData: [6, 8], paletteItems: [3, 5], bpm: [90, 150],
};

// Glyphs the bundled Geist face has (read from its cmap): printable ASCII,
// Latin-1 without the soft hyphen, and a few typographic marks. Anything else
// (Hangul, CJK, emoji) would fall back to another font, so it is refused.
const GLYPHS = /^[\x20-\x7E -¬®-ÿ–—‘’“”•…]*$/;
const HEX = /^#[0-9a-fA-F]{6}$/;
const NUM = /^\d{1,6}(\.\d{1,2})?$/;
const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

function text(err, key, v, [lo, hi]) {
  const n = typeof v === "string" ? Array.from(v.trim()).length : -1;
  if (n < lo || n > hi) err.push(`${key} needs ${lo}..${hi} characters, got ${n}`);
  else if (!GLYPHS.test(v)) err.push(`${key} '${v}' has characters outside the bundled Geist (Latin) face`);
}

function list(err, key, v, [lo, hi]) {
  const n = Array.isArray(v) ? v.length : -1;
  if (n < lo || n > hi) err.push(`${key} needs ${lo}..${hi} items, got ${n}`);
  return n >= lo && n <= hi;
}

export function validate(c) {
  const err = [];
  for (const k of ["buttonLabel", "trackTitle", "trackArtist", "chartTitle", "paletteQuery", "toastText"]) text(err, k, c[k], limits[k]);
  if (list(err, "tabs", c.tabs, limits.tabs)) c.tabs.forEach((t, i) => text(err, `tabs[${i}]`, t, limits.tab));
  if (list(err, "paletteItems", c.paletteItems, limits.paletteItems)) {
    c.paletteItems.forEach((t, i) => text(err, `paletteItems[${i}]`, t, limits.paletteItem));
    const q = String(c.paletteQuery ?? "").toLowerCase();
    const hits = c.paletteItems.filter((s) => String(s).toLowerCase().includes(q)).length;
    if (hits === 0) err.push(`paletteQuery '${c.paletteQuery}' matches no paletteItems; the Enter step needs one`);
    if (hits === c.paletteItems.length) err.push(`paletteQuery '${c.paletteQuery}' matches every paletteItem; at least one must filter out`);
  }
  if (list(err, "chartData", c.chartData, limits.chartData)) {
    const bad = c.chartData.filter((v) => !NUM.test(String(v)));
    if (bad.length) err.push(`chartData must be plain non-negative numbers (up to 6 digits, 2 decimals), got ${bad.join(", ")}`);
    else if (Math.max(...c.chartData.map(Number)) <= 0) err.push(`chartData needs at least one value above 0`);
  }
  const [blo, bhi] = limits.bpm;
  if (!(c.bpm >= blo && c.bpm <= bhi)) err.push(`bpm must be ${blo}..${bhi}, got ${c.bpm}`);
  for (const k of ["paper", "charcoal", "red"]) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  if (!err.some((e) => e.includes("colour"))) {
    for (const k of ["paper", "charcoal"]) {
      const r = contrast(c.red, c[k]);
      if (r < 3) err.push(`red ${c.red} has ${r.toFixed(2)}:1 contrast on ${k} ${c[k]}; needs >= 3:1`);
    }
    const tc = contrast(c.paper, c.charcoal);
    if (tc < 4.5) err.push(`paper/charcoal contrast is ${tc.toFixed(2)}:1; the UI text needs >= 4.5:1`);
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// { elementId: [data-start, data-duration] } in seconds; one window spans it all.
export function timing(c) {
  const total = r((BEATS * 60) / c.bpm);
  return { total, at: { stage: [0, total], scene: [0, total], music: [0, total] } };
}

export function musicArgs(c) {
  return ["scripts/make_music.py", "--bpm", String(c.bpm), "--duration", String(timing(c).total),
    "--taps", TAPS.join(","), "--seed", "719", "--out", "assets/music.wav"];
}
