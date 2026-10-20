# polaroid-card · 拍立得 · Polaroid Card

Two polaroid-style photo cards drop onto the page and settle with a bouncy overshoot, each holding a cropped video frame inside its paper border.

## Source
`vlog.py:b_polaroid()`, demo `vlog_demo.mp4`, t=4.3-6.5s of the finished video. Depends on the shared runtime in `../_shared/vlog-collage-runtime/` (see its README).

## How it works
`b_polaroid()` renders a textured paper card (via `collage.py`'s paper texture) with a thin inner border and a bottom caption strip, wraps it in a soft drop shadow, and returns both the sprite and a "window" rectangle describing where photo content should sit inside the border. That window is filled in later — by `b_still_card()` for a single still frame, or by `El`'s `media_sprite()` for live video — with a scale-to-cover crop of the source footage. The drop-in motion itself is generic: each polaroid is an `El` with `enter='drop'`, which animates it falling from off-screen with a back-out ease and a bit of rotation settling out, plus the shared 8Hz "boil" jitter for a hand-placed feel.

## Notes
Face-free by inspection in this preview — the clip is shot from behind. `b_polaroid()` is also the base for `b_still_card()` (a thin wrapper that fills the polaroid window with a single still frame) elsewhere in `vlog.py`.
