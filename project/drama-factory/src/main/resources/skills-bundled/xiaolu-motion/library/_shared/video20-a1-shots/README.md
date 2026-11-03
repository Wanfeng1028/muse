# video20-a1-shots

Shared Python/PIL + OpenCV rendering code for the "A1" batch of video 20's shot library: shots 7/8/9 (narration + bottom-right PiP), 10 (paper box), 11 (toss to agent). These four shots render as `shots/{s07,s08,s09,s10,s11}/` output folders in the source project, but the code itself is byte-identical across all five folders — only each folder's own `segment.mp4`/`meta.json` differ, so it's ported once here.

## What this is

- `explain.py` — `Shot07`/`Shot08`/`Shot09` (subclasses of a shared `ExplainShot`): plain narration + PiP for 7/8, with `Shot09` layering an eyelid-close animation on top. See `library/clip-narration-pip/README.md`.
- `boxshots.py` — `Shot10` (立体纸盒/paper-box-3d) and `Shot11` (抛给Agent/toss-to-agent).
- `a1lib.py` — drawing primitives specific to this batch (verbatim, no personal paths).
- `sb_lib.py` — the shared storyboard drawing kit (verbatim; also duplicated under `../paper-craft-components/` for the reusable-primitive documentation).
- `a1paths.py` — shared paths and the shot table (`SHOTS`, mapping each shot to its v2 frame range), patched (see below).

## Environment variables

- `XM_VIDEO_PROJECT_ROOT` — root of your own video-production working directory. Defaults to `.`.
- `XM_SCRATCH_DIR` — scratch/temp directory for intermediate render files (`WORK`/`BIN` live under `<scratch>/a1_work`). Defaults to `/tmp/xm_scratch`.

## Notes

Confirmed byte-identical across `s07`–`s11`'s `src/` copies for all five files above before porting; this is the canonical copy. Heavy ffmpeg/Vision calls in this batch should be wrapped with `python3 scripts/with_heavy_lock.py -- ...` (this repo's generic heavy-task lock) rather than the per-render `with_heavy_lock.py` duplicate that shipped alongside the original code, which was not ported.
