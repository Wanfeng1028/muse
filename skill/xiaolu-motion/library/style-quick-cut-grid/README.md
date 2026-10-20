# style-quick-cut-grid · 风格速切+四宫格 (style-quick-cut-grid, 镜14a)

The live frame quick-swipes through several visual "look" filters, then shrinks into a 2x2 grid of style options that expands back out once one is picked.

## Source
`../_shared/video20-a2-shots/src/shot14a2.py`, class `Shot14a`.

## How it works
On each style-name word (拼接/胶片/杂志/发布会), the whole live frame wipes to that style through a horizontal swipe with motion blur and a soft-light seam at the boundary — like swiping between camera filters — while the style's name eases in using its own distinct typeface. Two of the styles get brief flash-preview swipes before settling. On the next cue the frame shrinks into the top-left cell of a 2x2 grid (turning into the "collage" style) while the other three styles slide in from the edges — every cell is still the presenter's live footage, just re-styled. A yellow ring and green checkmark highlight the chosen collage cell, which then pushes out to fill the full screen again before the cut to `style-brush`. The presenter's face and skin tone are deliberately kept undistorted in every style variant.

## Notes
This file (and `style-brush`'s `shot14.py`) reference an `assets/` folder for the style reference images/fonts (`ASSETS / 'fonts/SourceHanSerifCN-Heavy.otf'` here) that is **not included** in this port — see `../_shared/video20-a2-shots/src/README.md` for why (`style_magazine.png`/`style_film.jpg`/`style_collage.jpg`/`style_launch.png` have the presenter's own likeness composited in, and the folder carries a ~13MB embedded font). Unlike the `render_v2.py` note on the `fullscreen-dialog`/`split-screen-workbench` entries, this one is a genuine missing-file dependency if you try to run this file as-is — supply your own style reference images and a serif font at the same relative paths to make it runnable.
