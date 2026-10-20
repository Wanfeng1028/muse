// pixel-dissolve recipe: validation, scene plan, cell order, plugin assets.
// Read by scripts/scaffold.mjs; never copied into the project. No music bed
// (no musicArgs export), so the scaffold skips it.
//
// cellOrder() is the reference for the seeded reveal order; index.html carries
// the same mulberry32 + Fisher-Yates code (it cannot import this file) and the
// scaffold selfcheck proves the two agree.

// GSAP is copied from the official hyperframes plugin at scaffold time (its
// own standard license); the font is the bundled OFL face.
// NanumSquare (SIL OFL 1.1, OFL.txt beside it) is shared by the CJK recipes: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/NanumSquare_acEB.ttf", "assets/fonts/OFL.txt"];

export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};

export const canvas = { width: 1080, height: 830 };
export const TOTAL = 6; // seconds, fixed skeleton
export const SEED = 719; // fixed: same CONFIG -> same cell order -> same frames
export const limits = { transitionAt: [0.5, 4.5], transitionDur: [0.2, 3], pixelSize: [10, 200], hold: 0.5 };

const HEX = /^#[0-9a-fA-F]{6}$/;
const BG = ["paper", "charcoal", "red"];

export function validate(c) {
  const err = [];
  for (const k of ["textA", "textB"]) {
    if (typeof c[k] !== "string" || !c[k].trim()) err.push(`${k} must be a non-empty string`);
  }
  const [alo, ahi] = limits.transitionAt;
  if (!(c.transitionAt >= alo && c.transitionAt <= ahi)) err.push(`transitionAt must be ${alo}..${ahi}, got ${c.transitionAt}`);
  const [dlo, dhi] = limits.transitionDur;
  if (!(c.transitionDur >= dlo && c.transitionDur <= dhi)) err.push(`transitionDur must be ${dlo}..${dhi}, got ${c.transitionDur}`);
  if (c.transitionAt + c.transitionDur > TOTAL - limits.hold) {
    err.push(`transitionAt + transitionDur must leave a ${limits.hold}s hold on scene B (<= ${TOTAL - limits.hold}), got ${c.transitionAt + c.transitionDur}`);
  }
  const [plo, phi] = limits.pixelSize;
  if (!Number.isInteger(c.pixelSize) || c.pixelSize < plo || c.pixelSize > phi) err.push(`pixelSize must be an integer ${plo}..${phi}, got ${c.pixelSize}`);
  for (const k of ["bgA", "bgB"]) {
    if (!BG.includes(c[k])) err.push(`${k} must be one of ${BG.join(", ")}, got ${c[k]}`);
  }
  for (const k of BG) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// Scene plan -> { elementId: [data-start, data-duration] } in seconds.
// sA holds until the dissolve ends; sB (and the pixel layer above it) starts
// with the dissolve and holds to the end.
export function timing(c) {
  const end = r(c.transitionAt + c.transitionDur);
  const at = {
    stage: [0, TOTAL],
    sA: [0, end],
    sB: [c.transitionAt, r(TOTAL - c.transitionAt)],
    fx: [c.transitionAt, r(c.transitionDur)],
  };
  return { at, total: TOTAL };
}

export const grid = (c) => ({ cols: Math.ceil(canvas.width / c.pixelSize), rows: Math.ceil(canvas.height / c.pixelSize) });

// Seeded reveal order: mulberry32(SEED) driving a Fisher-Yates shuffle of the
// cell indices. No unseeded randomness anywhere.
export function cellOrder(n, seed = SEED) {
  let s = seed >>> 0;
  const rand = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}
