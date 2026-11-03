# Asset production — real UI, real motion, real data

This is the heaviest step and the easiest to fake. Two hard rules:

1. **If the product has a real screen, screenshot the real screen.** No generated mock UI.
2. **If the product has real data, use the real number.** No invented stats.

## Make the demo environment fully real first

The film's asset quality is capped by the demo dataset. Do this before capturing anything:

- Strip placeholder / seeded fake content so the demo site shows only real items.
- Make sure every item has the fields the film will show (cover, transcript, analysis, score…).
- Verify each listed item actually opens / plays.

If the demo data is hollow, no amount of motion design will hide it — the film will be full of
empty cards and zero counts.

## Capture the UI

- **Real browser, `deviceScaleFactor=2`,** so full-HD captures are 3840×2160 and stay sharp on
  push-ins. Shoot at the target viewport (e.g. 1920×1080) for landscape.
- Drive the real page and, where the film needs it, **inject the real interaction** — type the real
  keyword, open the real dialog, click the real button — then capture that state.
- Record the geometry of the region you'll zoom into (the pixel box of the control), because the
  audit's push-in probe and any overlay placement need those coordinates.
- Capture the specific states the storyboard calls for (empty, filled, playing, report open), not a
  single generic hero shot.

## Capture motion as motion

Anything that reads as "this is alive" must be **real footage**, not a still:

- A video actually playing in the product.
- A click / hover / press feedback in the real UI.
- Text actually being typed.

Pull a short clip with ffmpeg and place it as a real video element on the composition's timeline so
it genuinely plays during the render, rather than swapping in a static frame.

## Provenance and licensing

- Keep a track record of where each non-original asset came from (music, fonts, third-party logos).
- Attribute where the license requires it.
- Use third-party logos only for identification — never as your own brand or to imply endorsement.

## When you swap placeholders for real assets, re-run the checks

A subtle regression class: the placeholder version passes, and the real-asset version fails.

- A light grey placeholder box under a caption gives dark text plenty of contrast. A **real photo**
  in that slot may be dark, and the caption's contrast drops below the threshold. This happened on a
  real film: replacing "cover" placeholders with actual photos (correct fix) triggered a WCAG
  contrast failure under the bottom meta row — fixed by giving that row its own light backing plate.
- **Rule:** after any placeholder→real swap, re-run the renderer's `check` and read the contrast and
  occlusion sections again. Do not assume a passing layout stays passing when the pixels change.
- Prefer a backing plate / solid chip behind HUD text if it can sit over arbitrary imagery, rather
  than relying on the image being light.

## Real images, not text placeholders

If a card, tile, or thumbnail represents content, it shows a **real image**. A box that reads
"cover", "image", or "placeholder" ships a film that looks broken to the viewer — it was one of the
most damaging defects found in testing, and it survived multiple QC passes because the placeholder
looked "intentional". Crop and compress real covers (`PIL` to a sensible size, e.g. 480×640 JPEG at
q≈86) before committing them.
