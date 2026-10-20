---
name: smooth-render
description: >-
  Render an HTML/CSS animation to a smooth, sharp MP4 at native resolution (up to 2K/4K)
  without choppy motion. Use when a CSS/JS animation (especially glassy/blur/backdrop-filter,
  gradient, or continuous-motion scenes) renders JANKY or stuttery via screenshot/screencast
  capture, when you need per-frame-accurate logical-time output with no wall-clock drift, or
  when muxing audio onto a rendered animation. Triggers: "render my animation to video",
  "the capture is choppy/stuttering", "export this HTML animation as MP4", "2K render of my
  web animation", "frames are dropping when I record the page".
---

# Smooth Render

Capture an HTML/CSS animation to a crisp MP4 where motion is **buttery, not choppy** — even for the cases that normally stutter: `backdrop-filter`/blur, glassy cards, gradients, and always-on continuous animations.

## Why naive capture is choppy
Chrome's CDP screencast (and most "screenshot every frame" loops) **coalesces** gradual changes — a smooth CSS transition emits far fewer frames than it should, and the result judders. Slowing the *output* fps doesn't fix the missing frames.

## The fix (two tricks, in `scripts/render.js`)
1. **Slow logical clock** — the page advances its own time `t` by `dt * window.__RATE` (e.g. RATE=0.7). Each logical second now spans more wall-clock time, so the screencast emits **more frames per logical second**. Every captured frame is tagged with the page's logical `t`, then remapped on the way out → exact timing, **no drift**.
2. **Heartbeat** — a 1px corner dot mutated every `requestAnimationFrame` so the screencast never sees a "still" region and keeps emitting at a uniform high rate.

Output is per-frame JPEGs + `frames.json` (per-frame logical timestamps). `scripts/assemble.js` turns that into an ffmpeg concat list with **per-frame durations** (= logical-time diffs), so the final encode is perfectly timed regardless of capture jitter.

## Wiring your page (required)
The page must expose globals `t` (logical seconds), `TOTAL`, `seek(t)`, `play()`, and in its rAF loop advance time by the rate:
```js
function tick(now){ if(!playing) return;
  if (last==null) last=now; t += ((now-last)/1000) * (window.__RATE||1); last=now;  // slow clock
  if (t>=TOTAL) { t=TOTAL; pause(); }
  render(t); requestAnimationFrame(tick);
}
```
**Scale your CSS durations by 1/RATE** so motion stays correctly timed in *logical* time. Either author them as `calc(var(--k)*…)` and set `--k` from `__TK`, or inject a stylesheet at render time that multiplies every `transition-duration`/`animation-duration`/delay you use by `K = 1/RATE`. Keep one scaled rule per animated selector — whenever you add or change a duration in the page, update its scaled rule too (the #1 source of "render timing looks off").

## Usage
```bash
# serve the page (a local static server avoids file:// quirks)
python3 -m http.server 8755 &
RENDER_URL=http://localhost:8755/index.html RENDER_W=2560 RENDER_H=1440 RENDER_RATE=0.7 \
  NODE_PATH=$(npm root) node scripts/render.js          # -> frames/ + frames/frames.json
node scripts/assemble.js frames                          # -> frames/list.txt
( cd frames && ffmpeg -y -f concat -safe 0 -i list.txt -i ../audio.mp3 \
    -vf "fps=30,format=yuv420p" -c:v libx264 -crf 18 -preset medium \
    -c:a aac -b:a 192k -movflags +faststart -shortest ../out.mp4 )
```
Drop the `-i ../audio.mp3` / audio flags for a silent render.

## Knobs & gotchas
- **RATE**: 0.6–0.8 is the sweet spot (still ≥30 logical fps, far fewer frames than 0.28). Lower RATE = more frames + bigger frame cache + slower. Pages with lots of always-on animation saturate the screencast quickly → prefer the higher end.
- **GPU flags** (`--use-angle=metal`, `--enable-gpu-rasterization`) keep 2K capture from being throttled by software compositing. Drop `backdrop-filter` (blur) at capture time — it's per-frame expensive and visually negligible over a soft gradient.
- **Disk**: frames are small (~0.1 MB at 2K), but a 2–3 min video is thousands of files — delete `frames/` after encoding.
- **Audio**: render silent, then mux a separately-built track onto the logical timeline (see the `audio-stems` skill). Mute/stub any `<audio>` during capture.
