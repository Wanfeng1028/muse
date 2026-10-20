# creative-film-runtime

Shared rendering harness for the 10 shot-library entries ported from《在我开口之前》(*Before I Speak*), Claude's autonomous 60-second code-generated short film that visualizes how an LLM generates one character of a response.

## What this is

This directory holds verbatim copies of the film's original rendering pipeline:

- `index.html` — the render target page: a bare canvas host loaded by headless Chrome.
- `main.js` — the driver. Exposes `window.renderFrame(t)`, which headless Chrome calls once per output frame with a timestamp `t` (seconds); it dispatches to whichever scene module owns that time range and drives the overall 60s timeline.
- `core.js` — shared drawing primitives and utilities used across scene modules (easing, color helpers, layout math, the `blurRing` ring-blur helper, etc.).
- `ui.js` — shared UI/text/layout chrome used by multiple scenes (labels, HUD-style overlays, common typography helpers).
- `post.js` — the WebGL2 post-processing pipeline: takes the Canvas2D output each frame and composites sub-frame motion blur, glow/bloom, and film grain on top of it.

The actual rendering flow was: headless Chrome (via Playwright) loads `index.html`, repeatedly calls `window.renderFrame(t)` to draw a frame to a Canvas2D context, then that frame is composited through the WebGL2 `post.js` pipeline for motion blur/glow/grain, and the resulting frames are streamed directly into `ffmpeg` over a local HTTP connection — there is no intermediate PNG sequence.

## Why it's here

Each of the 10 scene files (`s23.js`, `s4.js`, `s56.js`, `s78.js`, `s910.js`, one or more per `library/<scene>/src/` entry) is written against this harness's conventions and calling contract (`renderFrame(t)`, the shared helpers in `core.js`/`ui.js`, the post pipeline in `post.js`). Rather than duplicating this harness inside all 10 scene folders, it lives once here and every entry's README points back to it.

## Relationship to `engine/`

This repo's newer `engine/post.js` and `engine/core.js` contain a **separately ported, simplified, and decoupled** version of this same motion-blur + glow/bloom + grain machinery, generalized for use outside this specific film. **Use the `engine/` version for any new work.** This copy under `_shared/creative-film-runtime/` is kept only so the 10 scene source files in `library/<scene>/src/` — which were written against this exact harness — still make sense to read as self-contained, runnable-in-context code. It is not wired into this repo's current render pipeline.
