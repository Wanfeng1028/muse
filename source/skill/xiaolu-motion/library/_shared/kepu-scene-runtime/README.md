# kepu-scene-runtime

Shared runtime for the 3 shot-library entries ported from the `kepu` demo (小Lin说式科普 talking-head science explainer, `kepu_demo.mp4`, 27.3s).

## What this is

`scene.js` (verbatim) is the entire visual scene. It is **not** a `<canvas>` renderer — it's an HTML/SVG/DOM scene: HTML `<div>` "cards" positioned and animated with CSS 3D transforms (`translate3d`/`rotateY`/`rotateX`/`scale`), inline SVG for vector shapes (the scattering diagram, the lens, the bar chart, the burst lines), and CSS `text-shadow`/gradient tricks for the glowing keyword text. It's a pure function of time: `renderFrame(t)` — exposed as `window.renderFrame` — sets every element's transform/opacity/attribute for a given timestamp `t` and returns layout data used for QA. It has zero personal-path hits and needed no changes.

## What isn't included

The finished video composites three things per frame that aren't part of `scene.js`:

1. This scene, screenshotted by a headless-Chrome/Playwright pipeline calling `renderFrame(t)`.
2. A person-matting pass (Apple Vision-derived alpha matte) that cuts the presenter out of the raw camera recording for this specific take.
3. A graded clean-plate room background that the matted presenter is composited over.

That compositing pipeline (`render.py`, `prep.py`, `audio.py`, `timeline.json`, `build.sh`) is tied to this one recording — the specific room, camera angle, and take — and isn't included here; it's pipeline plumbing, not a generalizable visual effect. `scene.js`'s DOM/animation logic for the cards, keywords, and diagrams is the part worth reusing.

## Used by

`title-card-behind-person`, `diagram-grow`, `bg-swap-glow-text`.
