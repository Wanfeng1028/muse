# recap-flash · 回顾快闪 (recap-flash, 镜17)

A quick recap: the presenter shrinks into a PiP again while the three demo clips (vlog/科普/不露脸) fly back in as small rotated cards, closing on a "4 步" sticker.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s17`.

## How it works
Structurally mirrors `flash-card-hook`: the presenter eases into a bottom-right PiP and back out (`pip_layer`) over a paper background, while three pre-cached 15-frame demo-clip snippets (`DemoClip`) are cropped to card size and slammed into staggered positions with a slight scale-settle, each timed to its own recap beat. A "4 步" sticker (`four_bu()`, die-cut outline like the big-number shot) slams in near the end and eases back out as the shot exits.

## Notes
Reuses the vlog/kepu/faceless demo clips also used by `paper-box-3d`/`toss-to-agent` (A1 batch) and `finished-clip-insert`, but reads its own short in-memory cache of frames rather than sharing state with those shots.
