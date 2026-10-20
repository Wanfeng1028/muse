---
name: walkthrough-film
description: >-
  Build a long-form (2-6 minute) narrated product walkthrough film as a deterministic
  logical-clock HTML page, then render it per scene and assemble a pacing-warped mix.
  Use when a product demo is too long for a single-page explainer, when a film must ship
  in many review rounds or in several brand skins from ONE source tree, when scene
  durations must be derived from voiceover word timestamps, when a client keeps sending
  frame-by-frame feedback, or when parallel builder subagents each own part of one film.
  Triggers: "long product walkthrough video", "chaptered demo film", "white-label this
  film for another brand", "dark and light versions of the same video", "re-render just
  one scene", "the render judders / drops frames", "sync the chapters to the voiceover",
  "film spec for the builders", "version 7 of the video".
---

# Walkthrough Film

A **deterministic logical-clock HTML film**: one page, one `render(gt)`, N chapter scenes, rendered
frame-by-frame and assembled offline. Built for the case a single-page explainer cannot survive —
a 3+ minute walkthrough that ships in 9 versions across 2 brands, where a client reviews it frame
by frame and each round must re-render only what moved.

**What makes it different from `explainer-video`/`smooth-render`:** the timeline is *computed from
voiceover word timestamps*, not authored; each scene renders as its own MP4 by `seek()+screenshot`
(zero dropped frames, re-render one scene in minutes); pacing is warped at assembly, not in the page;
and the whole look is theme-token driven so a second brand is a URL parameter, not a fork.

## When to use
- Chaptered product tours, platform walkthroughs, white-label demo films, launch films > 90 s.
- Anything that will go through review rounds: the per-scene render + `VER` versioning is the point.
- Not for: a 30-60 s single-idea explainer (use `explainer-video`), a pure CSS loop, a screen recording recut.

## The one hard rule
**Every visual is a pure function of time.** A scene draws from its scene-local `lt` (and the ground
from global `gt`) with no state carried between frames, no timers, no `Date`, no CSS transitions.
Corollaries, each learned the expensive way:
- **One easing curve per move.** Never two writers on the same element's transform in one frame.
- **Verify at 1/30 s.** Shoot consecutive frames `t, t+.033, t+.067 …` across every move you touch and
  confirm the element advances monotonically by a similar delta. Pops and stalls are invisible at 0.5 s steps.
- Scrubbing to any `t` must produce the exact frame the render produces. If it doesn't, the render is not reproducible.

## Method

1. **Script and record VO first.** Per-scene clips with **word-level timestamps** (see the `vo-sync` skill).
   The script is the spine; nothing gets animated before the words exist.
2. **Compute the timeline** (`scripts/compute_timing.js`): a `CONFIG` array of `{id, cues:[[key, spokenWord]]}`
   turns word timestamps into per-scene `start`, `dur` and named `cues[]`. Durations come from
   `max(HEAD + voLength + TAIL, lastCue + 1.0, MIN[id])`, so every chapter ends ~1 s after its last spoken word.
   Outputs `timing.json` + `timing.js` (`window.__TIMING`), VO events and sentence captions.
   `CUT=a,b node compute_timing.js` drops scenes to make a short cut without touching the page.
3. **Build the page.** `engine.js` owns the clock, the scene registry, layers, the theme flag and the
   per-frame hooks; each chapter is its own `js/ch_<id>.js` + `css/ch_<id>.css` exporting `{layer, draw(lt,dur), enter?, exit?}`.
   Scenes read their cue times from `window.__TIMING` — **never hard-code a beat that a cue can anchor**.
   See `reference/PIPELINE.md`.
4. **Verify continuously.** `node scripts/play.mjs 14` (headless high-rate sweep) must end `errors: 0`;
   `node scripts/shots.mjs <dir> <t…>` for frames, and **look at every JPEG** — an error-free sweep proves nothing about layout.
5. **Render per scene** (`scripts/render_scene_step.mjs`): for each output frame, `seek(start+(k+.5)/30)`,
   wait two rAFs, screenshot, then encode. Deterministic, no duplicated or dropped frames whatever the page's
   real-time speed. `scripts/render_all.sh` runs 3 workers and **skips existing files**, so a re-render is
   "delete the stale clips, run again".
6. **Assemble the mix** (`scripts/build_mix.mjs`): per-scene pacing warp, VO tempo-fit per segment,
   an SFX event table keyed off cues, a music bed beat-locked to one cue and sidechain-ducked under the
   voice, two-pass loudnorm, concat, output to `Versions/<name>_${VER}_final.mp4`.

## Theme switching (one tree, many skins)
`?theme=<name>` → engine sets `window.__THEME` and adds `theme-<name>` to **both** `<body>` and
`<html>` → CSS custom-property token blocks do the rest. Rules:
- All ink/ground/glass values are tokens (`--bg --txt --dim --glass-bg --grad …`). **No hard-coded colour outside the token sheet.**
- **Card-scoped ink:** when a surface is light on a dark ground (or vice versa), re-declare the ink tokens
  *on the surface element itself*, so text inside cards stays readable whatever the ground is doing.
- A ground that changes over time writes the dynamic tokens **per frame** from a `GROUND3.update(gt)` hook
  the engine calls before the scene draws. Ink should flip fast (a narrow smoothstep) while the ground crossfades slowly.
- **Every change is gated** (`.theme-x` selector or `if (__THEME==='x')`) so earlier versions stay pixel-identical.
  Prove it: run the sweep in the old themes too, and shoot one old-theme frame from your area.
- Assets are chosen per theme (dark vs light wordmark) at the point of use, not at parse time. See `reference/THEMING.md`.

## Multi-version workflow
One `VER` env threads through everything: `renders_${VER}/NN_id.mp4` → `warped_${VER}/` →
`Versions/<name>_${VER}_final.mp4`. To ship round N+1: change the page, delete only the affected
`NN_id.mp4` **and** its warped twin, re-run `render_all.sh` (it skips the rest), re-run the mix.
Keep a `SPEC.md` decision log with one dated bullet per round — it is the only record of why a frame looks
the way it does, and the client will ask.

## Parallel builders
Rounds are large; split them. Write a brief (`reference/SUBAGENT_BRIEF_TEMPLATE.md`) that gives each owner
**an exclusive file set** (two agents editing one file will clobber each other), the tokens to use, the exact
frame times to check, and the standing rules. Every owner must also **prove no regression**: run the sweep in
the other themes and shoot one frame from each of them in their own area. Collect deviations back into the spec.

## Files
- `reference/PIPELINE.md` — timing → scenes → render → mix in detail, with the config shapes.
- `reference/THEMING.md` — token tables, card-scoped ink, the load-order trap, per-frame token lerp.
- `reference/PITFALLS.md` — 24 numbered gotchas, each of which cost a render cycle.
- `reference/SUBAGENT_BRIEF_TEMPLATE.md` — the parallel-builder brief.
- `scripts/compute_timing.js` — word timestamps + CONFIG → `timing.json`, cues, captions, VO events.
- `scripts/render_scene_step.mjs` — deterministic seek+screenshot render of one scene.
- `scripts/render_all.sh` — all scenes, N workers, skip-existing, `VER` → `renders_${VER}`.
- `scripts/shots.mjs` / `scripts/play.mjs` — frame shots and the error sweep (both honour `THEME`).
- `scripts/build_mix.mjs` — warp / SFX / music / duck / loudnorm / concat → final MP4.

Companions: `vo-sync` (word timestamps), `smooth-render` (real-time capture when frame-step is overkill),
`audio-stems` (music + SFX generation), `motion-graphics` (the move vocabulary).
