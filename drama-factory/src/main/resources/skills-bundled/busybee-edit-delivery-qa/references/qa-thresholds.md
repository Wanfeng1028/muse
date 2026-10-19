# QA Thresholds

These are defaults. Adjust them for slower edits, cinematic pieces, tutorials, explainers, or intentionally sparse work.

## Dense Social Montage

- Duration: `30-40s`
- Segment count for `35s`: `70-90`
- Average segment duration: `0.35-0.50s`
- Vertical: `1080x1920`
- Landscape: `1920x1080`
- Frame rate: `30fps` or higher
- Audio: required
- Contact sheet: required

## Slower Cinematic Cut

- Segment count can be much lower.
- Average segment duration may be `1.5-4s`.
- Visual QA should focus on shot quality, pacing, and emotional continuity rather than beat density.
- Audio is still required unless the deliverable is intentionally silent.

## Internal Proof Cut

- Specs can be looser if speed matters.
- Generated placeholders are allowed if clearly labeled.
- Provenance ambiguity is acceptable if the cut is not public.
- Contact sheet is still recommended.

## Public Delivery

- No unapproved generated placeholders.
- No stock-preview overlays, watermarks, or price marks.
- Source provenance should be reviewed.
- Final render specs should match platform target.
- Watch the final render, not only the contact sheet.

## Automated Flags Worth Adding

Future QA scripts can flag:

- repeated source starts too close together
- too many accents relative to main footage
- source mix too narrow
- missing priority-5 segments
- contact sheet frames with low brightness or low saturation
- likely black/blank frames
- mismatch between expected and actual duration
