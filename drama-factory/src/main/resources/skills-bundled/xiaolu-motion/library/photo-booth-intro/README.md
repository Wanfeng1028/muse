# photo-booth-intro · 大头贴开场 (photo-booth-intro, 镜6)

Documentation-only entry — no source is copied here.

## Source
None to port. In the source project, shot 6's own code (`a0shots.py`'s `s06`, in `../_shared/video20-a0-shots/src/`) is just a thin playback wrapper: a small `IpIntro` class that opens a precomposed video file (`s06_overlay.mov`) with a raw frame reader and returns one frame per call — `def s06(f, base): return Canvas(IPI.frame(f - 752))`. It does no drawing of its own; the actual generator that produced that precomposed clip already exists in this repo as `../../components/ip_intro.js`.

## How it works
See `../../components/ip_intro/README.md` for the real mechanism — the fixed opening card that plays back the presenter's three big-head stickers on a warm dotted-paper background with the "我是小鹿" title and past-cover-card decorations, described there in full (parameters, word-anchor timing, asset layout). This shot is simply that component's rendered output, played back frame-for-frame inside the rest of video 20's timeline.

## Notes
No `src/` folder is included for this entry — there is no reusable generation code specific to this shot beyond `components/ip_intro.js`, which is already part of this repo outside `library/`.
