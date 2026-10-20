# bg-swap-glow-text · 换背景加人后发光字 · BG Swap Glow Text

Large glowing text materializes behind the presenter, layered over a swapped-in background.

## Source
`scene.js:188` (`R.kwLanguang` — the "蓝光" keyword element) and `scene.js:543-546` (its position/scale animation), demo `kepu_demo.mp4`, t=14.0-17.5s of the finished video. Depends on the shared runtime in `../_shared/kepu-scene-runtime/` (see its README).

## How it works
The glow is pure CSS: a large `font-size` span with a layered `text-shadow` (a tight bright core plus two wider, softer, bluer glows) that reads as a light source rather than flat colored text. `popEnv()` — a small spring-based pop-in/out envelope helper — drives its `translateY`/`scale`/opacity over the given time window, so the word rises and settles into place, then eases back out later. In the source recording, a **separate compositing step** (an Apple Vision-derived alpha matte over a graded clean-plate background) swaps the room behind the presenter; that part is not included here (see `../_shared/kepu-scene-runtime/README.md`). The glowing-text-behind-person layer shown in this preview is the generalizable part, from `scene.js`.

## Notes
Presenter is on camera throughout, by design — this demo's whole format is a talking-head explainer. The background swap is pipeline plumbing (Python/Vision matting) tied to this specific recording and isn't ported; only the text-glow layer is.
