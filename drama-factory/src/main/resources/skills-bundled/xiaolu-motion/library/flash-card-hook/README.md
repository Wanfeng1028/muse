# flash-card-hook · 快闪卡片钩子 (flash-card-hook, 镜1)

Opening hook: five demo/photo cards slam into a pile behind the presenter one by one, then two hand-lettered labels punch in to read "不会剪辑也能做出这样的视频" (you don't need to know how to edit to make videos like this).

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s01`.

## How it works
The presenter shrinks from full frame into a small bottom-right PiP box and back out (`pip_region`/`pip_layer`), while five cards (three demo-video thumbnails, two photo cards) slam into a rotated pile behind him — each one scales in from 1.25x with an ease-out-cubic over 4 frames, landing on its own beat. Once the pile has settled, two text labels pop in: "不会剪辑也能做出" eases in gently, then "这样的视频" slams down harder (`slam_curve`) in sync with the spoken word, with a radial burst FX and motion-blur streaks (`speed_lines_layer`) reinforcing the hit. Both labels slide up and fade out just before the shot ends.

## Notes
Card art (`vlog_9.60.png`, `kepu_20.00.png`, `faceless_20.00.png`, `card01_2.9.png`, `card02_2.6.png`, `card03_3.55.png`) is loaded from a local `ASSETS`/`assets` working directory (`a0common.py`'s `WORK / 'assets'`) that isn't part of this port — supply your own frame grabs/photos there, named to match `S1_CARDS` in `a0shots.py`, to run this shot standalone. The paper-strip subtitle and step-bar chrome seen in the full video are drawn by this batch's outer render loop (`a0render.py`, not ported — see the shared dir's README), not by `s01` itself.
