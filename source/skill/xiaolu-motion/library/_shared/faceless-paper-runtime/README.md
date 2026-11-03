# faceless-paper-runtime

Shared runtime for the 3 shot-library entries ported from the `faceless` demo (纸本手绘/不露脸 paper hand-drawn explainer, `faceless_demo.mp4`, 31.8s).

## What this is

Verbatim copies of the demo's HTML Canvas rendering code:

- `ink.js` — pen-and-ink primitives. `Stroke` is a single hand-tremor'd line (a wobbled/resampled path, tapered width) that reveals itself progressively along its own length as it's "drawn" — never a fade or a mask wipe. `Drawing` sequences several `Stroke`s in order inside a time window, allotting simulated pen-travel time between them. `Writing` does the same for a line of text, glyph by glyph, each character wiped in with a slanted reveal that mimics stroke order. `makeStamp()` builds a red rubber-stamp bitmap (白文 style — the character is knocked out of a solid block via `destination-out` compositing) with jittered edges and fbm-noise-driven ink texture/missing-ink speckling.
- `scene.js` — the paper scene built from those primitives: multiple `Sheet`s (pages) that slide in, ink items placed on them via the `drawn()`/`written()` helpers, and the `Card` class (a chapter-card state machine: drop onto the page, settle, fly to a slot and shrink into a step tag, optionally dim, then fly off).

Same rendering approach as `kepu-scene-runtime`, but here it really is `<canvas>` 2D: `scene.js` exposes `renderFrame(ctx, t)`, called once per output frame — by a Playwright-driven headless-Chrome pipeline, not included — with the destination canvas context and a timestamp; everything is drawn with direct `ctx` calls rather than DOM/CSS. Both files had zero personal-path hits and needed no changes.

## Used by

`stroke-growth`, `index-card-stamp`, `step-label`.
