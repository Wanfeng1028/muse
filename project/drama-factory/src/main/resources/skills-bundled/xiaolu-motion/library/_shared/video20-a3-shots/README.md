# video20-a3-shots

Shared Python/PIL + OpenCV rendering code for the "A3" batch of video 20's shot library: shot 15 (胶片灯箱/film-lightbox) and shot 16 (实拍自检含重做小卡/live-selfcheck-redo). These render as `shots/{s15,s16}/` output folders.

## What this is

- `shot15.py` — Shot 15, film lightbox.
- `shot16.py` — Shot 16, live self-check + redo card.
- `a3common.py` — shared paths, timeline/word-onset helpers, frame IO, drawing and compositing helpers, and a few small helpers (`pill`, `badge`, `hud_brackets`, `glow`, `scissors`, `check_chip`) copied verbatim from `storyboard_v2/src/render_v2.py` to avoid importing that module's keyframe caches.
- `faces_track.py` — face/outer-lip box tracking via Apple Vision (`vision_frames.swift`, not ported — see the global "never copy" list; this file is the Python driver, not the compiled tool).

## Environment variables

- `XM_VIDEO_PROJECT_ROOT` (`a3common.py`) — root of your own video-production working directory. Defaults to `.`.
- `XM_RAW_FOOTAGE` (`faces_track.py`) — your own camera source file, replacing a hardcoded `~/Downloads/copy_*.MOV`. Defaults to `raw_footage.mov`.

## Notes

`s15/src/` and `s16/src/` are near-identical, but three files diverge (`a3common.py`, `build.py`, `shot16.py`) — confirmed by diff before porting; `shot15.py`, `faces_track.py`, and `vision_frames.swift` (not ported) are byte-identical between the two. This copy sources everything from `s16/src/`, the later/final versions (its file timestamps run hours after `s15/src/`'s, consistent with `s16` being the actively-iterated copy). Note that `a3common.py`'s own docstring claims "This file is identical in s15/src and s16/src (build.py checks the copies match)" — that claim no longer holds; `s16`'s copy was evidently revised after `s15`'s was finalized. `build.py` itself isn't part of this port either way — it's per-render orchestration plumbing, not reusable visual-effect code.
