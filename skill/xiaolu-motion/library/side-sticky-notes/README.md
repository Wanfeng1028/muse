# side-sticky-notes · 两侧竖贴纸 (side-sticky-notes, 镜3)

Two vertical sticker labels — "不想剪辑" and "不会剪辑" — slam in from the left and right edges of the frame, one per spoken phrase, then slide back off screen together.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s03`.

## How it works
Each sticker is a rotated vertical label (`vlabel`) pre-rendered once and cached. On its cue word, it slams into place from an oversized, slightly-offscreen start (`slam_curve`) with a soft drop shadow, and a small radial burst of impact lines flashes above it (away from the presenter's face) for its first dozen frames. Near the end of the shot both stickers slide back out sideways together (`ease_in_cubic`), clearing the frame before the cut.

## Notes
Reuses `sb_lib.py`'s `vlabel()` (documented as a reusable primitive under `../_shared/paper-craft-components/`).
