# Higher-fidelity capture (optional, feature-demo)

The default take (`record_video`) is about 25 fps VP8 at CSS-pixel size. That is enough for bug reports and most client walkthroughs at 720p. Offer a crisper path only when the client will watch full-screen on a large or Retina display, or when the UI has small text. Each option costs setup and render time; say so.

| Option | Quality | Effort | Notes |
|---|---|---|---|
| Bigger viewport (`viewport: [1600, 900]`) | sharper text, same fps | none | export still caps at 720p unless `--height 1080` |
| Playwright `page.screencast` (Node, Playwright ≥ 1.59) | JPEG frames with timestamps via `onFrame`; built-in action highlight and chapter cards | medium: a Node recorder instead of record.py | frame timestamps remove the clock offset; output via `path` is still VP8 25 fps, so pipe frames to ffmpeg x264 yourself |
| CDP `Page.startScreencast` | per-frame JPEG/PNG at viewport × deviceScaleFactor | medium | Chromium only; you handle variable frame timing |
| Deterministic frame capture (e.g. demo-video-skill, MIT) | 60 fps, sharp, reproducible; cursor and zoom drawn in post | high, slow renders | re-pace without re-recording; animations need care (rAF is unreliable headless) |
| playwright-recast (MIT) | trace.zip → MP4 with idle speed-up, subtitles, voiceover, zoom | medium (Node) | reported sync drift between speed map, voiceover and zoom in its issues; pin a version |
| Screen recording app (Cap, Screen Studio) by the user | 4K/60, auto-zoom | user does it | then `edl.py --edit-only` for trimming only |

## Bridging back into this pipeline

Whatever records the frames, keep the contract: produce `raw.webm` (or any ffmpeg-readable file renamed accordingly), an `events.json` with the same event kinds and a `video_offset` (0 when frame timestamps are exact), and the storyboard copy. Then `edl.py`, `verify.py`, `export.py` and `report.py` work unchanged.

## Check before promising

- Run one 10-second test at the target size and inspect a frame at 100% (`ffmpeg -ss 3 -i … -frames:v 1 f.png`).
- Compare render time against the deadline; deterministic capture can take minutes per minute of video.
- Remotion-based routes need a company licence above 3 employees; check before choosing them.
