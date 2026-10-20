// text-sandwich recipe: validation, scene plan, plugin assets, user asset.
// Read by scripts/scaffold.mjs; never copied into the project. No music bed
// (no musicArgs export), so the scaffold skips it.

// GSAP is copied from the official hyperframes plugin at scaffold time (its
// own standard license); the font is the bundled OFL face. The character image
// is the user's own file: never bundled here. userAssets maps the CONFIG key
// that names it to the fixed path the scaffold copies it to; the scaffold
// refuses (and writes nothing) when that file cannot be read.
// NanumSquare (SIL OFL 1.1, OFL.txt beside it) is shared by the CJK recipes: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/NanumSquare_acEB.ttf", "assets/fonts/OFL.txt"];

export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};
export const userAssets = { characterImage: "assets/character.png" };

export const canvas = { width: 1080, height: 830 };
export const TOTAL = 6; // seconds, fixed skeleton
// passAt floor: the letters' entrance (stagger) has landed before the pass.
export const limits = { passAt: [1, 4.5], passDur: [0.5, 4], hold: 0.5, wordLen: 12 };
export const DIRECTIONS = ["ltr", "rtl"];
// Raster only: the scaffold copies any of these to assets/character.png and the
// browser sniffs the real format; an SVG would not render under that name.
const IMAGE = /\.(png|webp|jpe?g|gif)$/i;
const HEX = /^#[0-9a-fA-F]{6}$/;

export function validate(c) {
  const err = [];
  const n = typeof c.word === "string" ? [...c.word.trim()].length : 0;
  if (!n || n > limits.wordLen) err.push(`word must be 1..${limits.wordLen} characters, got ${n}`);
  if (typeof c.characterImage !== "string" || !IMAGE.test(c.characterImage)) {
    err.push("characterImage must be a path to a .png/.webp/.jpg/.gif image");
  }
  const [alo, ahi] = limits.passAt;
  if (!(c.passAt >= alo && c.passAt <= ahi)) err.push(`passAt must be ${alo}..${ahi}, got ${c.passAt}`);
  const [dlo, dhi] = limits.passDur;
  if (!(c.passDur >= dlo && c.passDur <= dhi)) err.push(`passDur must be ${dlo}..${dhi}, got ${c.passDur}`);
  if (c.passAt + c.passDur > TOTAL - limits.hold) {
    err.push(`passAt + passDur must leave a ${limits.hold}s hold (<= ${TOTAL - limits.hold}), got ${c.passAt + c.passDur}`);
  }
  if (!DIRECTIONS.includes(c.direction)) err.push(`direction must be one of ${DIRECTIONS.join(", ")}, got ${c.direction}`);
  for (const k of ["paper", "charcoal", "red"]) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// Scene plan -> { elementId: [data-start, data-duration] } in seconds.
// Both letter layers run the whole 6 s; the character exists only while it
// crosses (it starts and ends fully off-canvas).
export function timing(c) {
  const at = {
    stage: [0, TOTAL],
    back: [0, TOTAL],
    character: [r(c.passAt), r(c.passDur)],
    front: [0, TOTAL],
  };
  return { at, total: TOTAL };
}
