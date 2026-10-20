// intro-kinetic recipe: validation, scene plan, plugin assets, music args.
// Read by scripts/scaffold.mjs; never copied into the project.
//
// The scene plan (lengths in beats) is the single source for every static
// timing attribute. index.html re-derives the same lengths only to refuse to
// build when the attributes and CONFIG disagree.

import { contrast } from "../_shared/contrast.mjs";

// Files taken from the official hyperframes plugin at scaffold time, never
// redistributed from this repo: GSAP ships under its own standard license and
// the SFX under the Pixabay Content License (both bundled by that plugin).
// NanumSquare (SIL OFL 1.1, OFL.txt beside it) is shared by the CJK recipes: it lives in
// templates/_shared and the scaffold copies it.
export const sharedAssets = ["assets/fonts/NanumSquare_acEB.ttf", "assets/fonts/OFL.txt"];

export const pluginAssets = {
  "assets/vendor/gsap.min.js": { glob: "skills/*/assets/vendor/gsap.min.js" },
  "assets/sfx/impact-bass-1.mp3": { path: "skills/media-use/audio/assets/sfx/impact-bass-1.mp3" },
  "assets/sfx/whoosh-short.mp3": { path: "skills/media-use/audio/assets/sfx/whoosh-short.mp3" },
};

export const limits = { tools: [1, 3], flash: [2, 8], finale: [1, 4], bpm: [90, 150] };

const HEX = /^#[0-9a-fA-F]{6}$/;

export function validate(c) {
  const err = [];
  for (const k of ["title", "name", "team", "employer", "yearsUnit", "subsLabel", "toolsLabel"]) {
    if (typeof c[k] !== "string" || !c[k].trim()) err.push(`${k} must be a non-empty string`);
  }
  for (const k of ["tools", "flash", "finale"]) {
    const [lo, hi] = limits[k];
    const n = Array.isArray(c[k]) ? c[k].length : -1;
    if (n < lo || n > hi) err.push(`${k} needs ${lo}..${hi} items, got ${n}`);
  }
  const [blo, bhi] = limits.bpm;
  if (!(c.bpm >= blo && c.bpm <= bhi)) err.push(`bpm must be ${blo}..${bhi}, got ${c.bpm}`);
  if (!Number.isInteger(c.years) || c.years < 0 || c.years > 999) err.push(`years must be an integer 0..999`);
  if (!Number.isInteger(c.subsTarget) || c.subsTarget < 0) err.push(`subsTarget must be a non-negative integer`);
  if (!["ko", "comma"].includes(c.subsFormat)) err.push(`subsFormat must be ko or comma`);
  if (c.subsFormat === "ko" && c.subsTarget < 1000) err.push(`subsFormat=ko counts in thousands; use subsTarget >= 1000 or subsFormat=comma`);
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

// The default title carries the original author's name; follow `name` unless title= was passed.
export function derive(c, given) {
  if (given.has("name") && !given.has("title") && typeof c.name === "string") c.title = `${c.name.trim()} 자기소개`;
}

const r = (x) => +x.toFixed(6);

// Scene plan in beats -> { elementId: [data-start, data-duration] } in seconds.
export function timing(c) {
  const B = 60 / c.bpm;
  const T = c.tools.length, F = c.flash.length, L = c.finale.length;
  const beats = [["s1", 4], ["s2", 4], ["s3", 4], ["s4", 2 + 2 * T], ["s5", F], ["s6", 2 * L + 2]];
  const at = {};
  let b = 0;
  for (const [id, n] of beats) {
    at[id] = [r(b * B), r(n * B)];
    b += n;
  }
  const total = r(b * B);
  at.stage = [0, total];
  at.t12 = [at.s2[0], r(0.5 * B)];
  at.music = [0, total];
  at["sfx-impact-open"] = [0, 2];
  ["s2", "s3", "s4", "s5"].forEach((id, i) => { at[`sfx-whoosh-${i + 1}`] = [r(at[id][0] - 0.3), 0.57]; });
  at["sfx-impact-finale"] = [at.s6[0], 2];
  const flashBeat = 4 + 4 + 4 + 2 + 2 * T; // first beat of s5
  return { at, total, flashBeat, finaleBeat: flashBeat + F };
}

export function musicArgs(c) {
  const { total, flashBeat, finaleBeat } = timing(c);
  return ["scripts/make_music.py", "--bpm", String(c.bpm), "--duration", String(total),
    "--flash-beat", String(flashBeat), "--finale-beat", String(finaleBeat),
    "--seed", "719", "--out", "assets/music.wav"];
}
