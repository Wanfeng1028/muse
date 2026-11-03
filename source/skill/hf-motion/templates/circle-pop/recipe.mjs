// circle-pop recipe: validation, scene plan, plugin assets. Read by
// scripts/scaffold.mjs; never copied into the project. No music bed (no
// musicArgs export), so the scaffold skips it.
//
// POP / FILL are fixed by the skeleton; index.html carries the same two
// numbers (it cannot import this file), its timing guard throws when the
// scene windows disagree, and the scaffold selfcheck pins both copies.

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
export const POP = 0.4; // circle pops to its small radius, overshooting once
export const FILL = 0.5; // circle grows from there to cover the whole frame
export const limits = { transitionAt: [0.5, 4], overshoot: [1, 1.5] }; // T <= 4: B holds >= 1.1 s after full cover

const HEX = /^#[0-9a-fA-F]{6}$/;
const COLORS = ["paper", "charcoal", "red"];

// "center" or "x,y" as fractions of the frame (0..1 each) -> [x, y] or null
export function parseOrigin(s) {
  if (s === "center") return [0.5, 0.5];
  const m = /^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\s*$/.exec(String(s));
  if (!m) return null;
  const xy = [Number(m[1]), Number(m[2])];
  return xy.every((v) => v >= 0 && v <= 1) ? xy : null;
}

export function validate(c) {
  const err = [];
  for (const k of ["textA", "textB"]) {
    if (typeof c[k] !== "string" || !c[k].trim()) err.push(`${k} must be a non-empty string`);
  }
  const [alo, ahi] = limits.transitionAt;
  if (!(c.transitionAt >= alo && c.transitionAt <= ahi)) {
    err.push(`transitionAt must be ${alo}..${ahi} (keeps scene B on screen after the circle covers), got ${c.transitionAt}`);
  }
  if (!parseOrigin(c.popOrigin)) err.push(`popOrigin must be "center" or "x,y" with 0..1 fractions, got ${c.popOrigin}`);
  if (!COLORS.includes(c.popColor)) err.push(`popColor must be one of ${COLORS.join(", ")}, got ${c.popColor}`);
  const [olo, ohi] = limits.overshoot;
  if (!(c.overshoot >= olo && c.overshoot <= ohi)) err.push(`overshoot must be ${olo}..${ohi}, got ${c.overshoot}`);
  for (const k of COLORS) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// Scene plan -> { elementId: [data-start, data-duration] } in seconds.
// sA holds until the circle covers the frame; sB (whose background IS the
// circle) starts with the pop and holds to the end.
export function timing(c) {
  const at = {
    stage: [0, TOTAL],
    sA: [0, r(c.transitionAt + POP + FILL)],
    sB: [c.transitionAt, r(TOTAL - c.transitionAt)],
  };
  return { at, total: TOTAL };
}
