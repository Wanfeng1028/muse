# index-card-stamp · 索引卡盖章 · Index Card Stamp

A chapter card drops onto the page, a red stamp lands on it with a little settle-bounce, then the whole card shrinks down into its tag slot.

## Source
`scene.js:113-160` (`Card` class `pose()`/`draw()`) and `ink.js:230-259` (`makeStamp()`), demo `faceless_demo.mp4`, t=3.2-5.2s of the finished video. Depends on the shared runtime in `../_shared/faceless-paper-runtime/` (see its README).

## How it works
`Card.pose(t)` is a small state machine keyed off a handful of timestamps on the card instance (`tDrop`/`tLand`/`tFly`/`tStamp`/`tDim`/`tExit`): it falls in with a `quadIn` ease and a rotation settle, rests with a tiny damped bounce, and later flies to its slot along an arced path (a sine-shaped lift) while shrinking to tag scale. `draw()` renders the card bitmap with a drop shadow that grows with height, then — once `t >= tStamp` — draws the stamp bitmap on top with `multiply` blending and a brief overshoot-then-settle scale (a quick snap down from 1.22x to rest), so it reads as a physical stamp making contact. The stamp graphic itself comes from `makeStamp()`: a jittered rubber-block shape with the character knocked out via `destination-out` compositing (白文 seal style), plus fbm-noise-driven ink texture and small missing-ink speckles for realism.

## Notes
Genuinely face-free and brand-free throughout (this demo's whole format is paper hand-drawn, no-face by design). `Card` is the same class used by `step-label`; this entry covers its drop/stamp phases, `step-label` covers its later fly-to-slot/exit phase.
