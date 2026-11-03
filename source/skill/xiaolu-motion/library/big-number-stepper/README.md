# big-number-stepper · 大号数字+步骤条 (big-number-stepper, 镜12)

A giant outlined "4" slams down alongside a "个步骤" (steps) tag, introducing the four-step process the video is about to walk through.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s12` (plus its `s12_parts()` asset cache).

## How it works
The numeral is built from `sticker_outline(plain_text('4', ...))` — a large filled digit with a white die-cut sticker outline — and slams into place (`slam_curve`) with three short impact strokes radiating from its corner. Slightly after, the "个步骤" tag (`vlabel`, yellow background) pops in next to it (`pop_curve`, a bouncy scale-overshoot). Both ease out toward the end of the shot. The step-bar chrome itself (the four-segment progress bar the shot's name also refers to) is drawn by this batch's outer render loop — `a0render.py`'s `global_layer`, not ported here — using `a0lib.py:step_bar_image()`, one of the primitives documented under `../_shared/paper-craft-components/`.

## Notes
See `../_shared/paper-craft-components/src/README.md` for the step-bar primitive itself; this shot only owns the big-number/tag part of the composition.
