# version-sticker-curve · 版本贴纸+手绘曲线 (version-sticker-curve, 镜19)

A "v1.0 / 第一版" sticker slaps on, then a hand-drawn S-curve traces itself onto the frame in sync with speech, ending with a "第二曲线" (second curve) tag popping onto its upswing.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s19`.

## How it works
The version sticker (`v10()`) is a two-line die-cut label ("v1.0" + "第一版") that slams in top-right and eases back out. Separately, `curve_points()` generates a fixed S-shaped polyline (a flat dip followed by a steep sigmoid rise), which is progressively revealed point-by-point as the shot's own on-screen "drawing" — a thick yellow marker-stroke under a thinner ink line, plus axis lines and an arrowhead once the draw completes — timed to run exactly across the relevant spoken phrase. A "第二曲线" label tag pops in right as that word is spoken, positioned on the curve's rising segment.

## Notes
None beyond the shared batch notes.
