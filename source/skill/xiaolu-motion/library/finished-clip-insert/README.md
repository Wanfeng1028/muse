# finished-clip-insert · 成片插入 (finished-clip-insert)

A brief cutaway to a finished demo clip (vlog / 科普 / 不露脸) playing full screen, tagged with a small "成片 · <kind>" pill in the top-left so the viewer knows they're looking at a rendered example, not raw footage.

## Source
`../_shared/video20-a0-shots/src/a0shots.py`, function `s_insert(kind)` (a factory — called once per demo kind, returning the actual per-frame render function).

## How it works
`s_insert('vlog' | '科普' | '不露脸')` returns a shot function that takes the finished-demo frame as its base plate (the cut point comes from `timeline.py`'s `PIECES` table, matched by `kind`) and composites a small dark pill reading "成片 · <kind>" with a play-button glyph, sliding in from off-screen left with an ease-out-cubic over 5 frames. There are three insert instances in the actual video (vlog, 科普/kepu, 不露脸/faceless), each a jump-cut cutaway inside shot 1's demo-card sequence — the preview below captures the vlog instance.

## Notes
Depends on `timeline.py` (`storyboard_v2/src/timeline.py`, read-only authority for frame-to-source mapping) for locating each insert's source frames — not ported here, per the "never copy" list; treat it as an external authority your own render loop would need to supply.
