# step-label · 步骤标签 · Step Label

Four chapter cards, already shrunk into a row of step tags, sit together along the top of the page before flying up and off screen.

## Source
`scene.js:132-142` (the `Card` class's fly-to-slot-and-dim phase), demo `faceless_demo.mp4`, t=23.8-27.3s of the finished video (all four step tags visible together, then fly away — a clean natural cut point). Depends on the shared runtime in `../_shared/faceless-paper-runtime/` (see its README).

## How it works
Once a `Card` reaches its post-fly resting state, `pose(t)` holds it at a fixed slot position (`slotX`, spaced 238px apart per step) and tag scale (`TAG_S`). An optional `tDim` window fades its alpha and shrinks it slightly, for de-emphasizing an earlier step once a later one becomes active. Past `tExit`, a `cubicIn`-eased tween lifts the tag straight up and off the top of the page. With four `Card` instances sharing the same slot row (each card's `step`, 1-4, sets its own `slotX`/rotation), the result reads as a row of labeled tabs across the top of the page.

## Notes
Genuinely face-free and brand-free throughout (this demo's whole format is paper hand-drawn, no-face by design). Shares the `Card` class with `index-card-stamp`, which covers the earlier drop/stamp phases of the same object.
