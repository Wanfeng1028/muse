// screen-dive recipe: validation, scene plan, plugin assets. Read by
// scripts/scaffold.mjs; never copied into the project. No music bed (no
// musicArgs export), so the scaffold skips it.

// GSAP is copied from the official hyperframes plugin at scaffold time (its
// own standard license); the font is the bundled OFL face. The laptop is drawn
// in CSS inside index.html: no image asset at all.
// NanumSquare (SIL OFL 1.1, OFL.txt beside it) is shared by the CJK recipes: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/NanumSquare_acEB.ttf", "assets/fonts/OFL.txt"];

export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
};

export const canvas = { width: 1080, height: 830 };
export const TOTAL = 6; // seconds, fixed skeleton
// diveAt floor: the laptop's 1.0 s entrance finishes before the camera moves.
export const limits = { diveAt: [1, 4.5], diveDur: [0.5, 4], hold: 0.5 };
export const DEVICES = ["laptop"];

const HEX = /^#[0-9a-fA-F]{6}$/;

export function validate(c) {
  const err = [];
  if (typeof c.screenText !== "string" || !c.screenText.trim()) err.push("screenText must be a non-empty string");
  const [alo, ahi] = limits.diveAt;
  if (!(c.diveAt >= alo && c.diveAt <= ahi)) err.push(`diveAt must be ${alo}..${ahi}, got ${c.diveAt}`);
  const [dlo, dhi] = limits.diveDur;
  if (!(c.diveDur >= dlo && c.diveDur <= dhi)) err.push(`diveDur must be ${dlo}..${dhi}, got ${c.diveDur}`);
  if (c.diveAt + c.diveDur > TOTAL - limits.hold) {
    err.push(`diveAt + diveDur must leave a ${limits.hold}s full-screen hold (<= ${TOTAL - limits.hold}), got ${c.diveAt + c.diveDur}`);
  }
  if (!DEVICES.includes(c.deviceStyle)) err.push(`deviceStyle must be one of ${DEVICES.join(", ")}, got ${c.deviceStyle}`);
  for (const k of ["paper", "charcoal", "red"]) {
    if (!HEX.test(c[k] ?? "")) err.push(`${k} must be a #rrggbb colour`);
  }
  return err;
}

const r = (x) => +x.toFixed(6);

// Scene plan -> { elementId: [data-start, data-duration] } in seconds.
// The screen layer runs the whole 6 s (one DOM from the first frame to the
// last, so the dive is continuous). The device layer (lid + base) leaves the
// timeline when the dive lands: by then it is entirely off-canvas, and
// dropping it guarantees no bezel edge survives into the hold.
export function timing(c) {
  const at = {
    stage: [0, TOTAL],
    device: [0, r(c.diveAt + c.diveDur)],
    screen: [0, TOTAL],
  };
  return { at, total: TOTAL };
}
