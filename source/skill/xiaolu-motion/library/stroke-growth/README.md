# stroke-growth · 笔画生长 · Stroke Growth

A header line draws itself onto the page stroke by stroke, then a line of handwritten text strokes in character by character.

## Source
`ink.js` `Stroke`/`Drawing`/`Writing` classes, invoked via `scene.js`'s `drawn()`/`written()` helpers, demo `faceless_demo.mp4`, t=0.0-2.5s of the finished video. Depends on the shared runtime in `../_shared/faceless-paper-runtime/` (see its README).

## How it works
A `Stroke` wobbles and resamples a raw path for hand tremor, tapers its width toward each end, and reveals itself by rebuilding its filled ribbon polygon up to the current progress fraction — found via a binary search into cumulative arc length — so it's genuinely drawn, not a fade or a wipe mask. `Drawing` sequences several `Stroke`s inside a time window, allotting time per stroke proportional to its length and adding simulated pen-travel time between strokes. `Writing` does the same for text, giving each glyph its own time slot (here, one per spoken syllable — see the `slots()` helper in `scene.js`) and revealing each character with a slanted clip wipe that mimics stroke order. `scene.js`'s `drawn()`/`written()` wrap these into "sheet" items and register them on a page.

## Notes
Individual pen-strokes in this demo are each under about a second by design, so this preview necessarily includes an adjacent pop-in effect alongside the pure stroke growth — there's no isolated "pen only" moment left in the source at this point in the timeline. Genuinely face-free and brand-free throughout (this demo's whole format is paper hand-drawn, no-face by design).
