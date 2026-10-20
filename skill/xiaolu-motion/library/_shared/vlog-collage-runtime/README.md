# vlog-collage-runtime

Shared runtime for the 3 shot-library entries ported from the `vlog` demo (拼贴手账 scrapbook-style vlog, `vlog_demo.mp4`, 29.0s) — a Python/PIL/OpenCV frame compositor, not a browser/Canvas renderer like the `kepu` and `faceless` demos.

## What this is

Verbatim (except one patched path) copies of the demo's rendering code:

- `engine.py` — the frame compositor: easing functions, premultiplied-alpha sprite compositing (`draw()`), a scale-to-cover cropper, a warm film grade, and the page-to-page transition functions (`trans_sweep()`, `trans_tearoff()`, `trans_flip()`, `trans_swipe()`). Deterministic — every frame is a pure function of `t`.
- `vlog.py` — built on `engine.py`. The `El` class is the generic timed-element state machine: enter/exit animation curves (pop/drop/stamp/slap/spin/write/rise/flip-in) driven by the easing functions in `engine.py`, plus an 8Hz "boil" jitter that re-randomizes each sticker's position/rotation a little every frame for a hand-jittered, stop-motion feel. Element builders like `b_polaroid()` sit alongside a `card(kind, ...)` dispatcher that registers a builder (`time_card`/`weather_card`/`mood_card`, from `collage.py`) and wraps it in an `El`. The rest of the file is this specific video's own day-by-day storyline — which clips play when, captions, and which of the presenter's real days were resequenced into the fictional "我的一天" narrative. That part is a worked example of how to drive the engine, not something to reuse literally.
- `collage.py` — the paper-craft asset kit (PIL/numpy/cv2): torn paper, washi tape, stickers, and the polaroid/time/weather/mood card art. One personal path was patched (below); everything else is verbatim.

The reusable mechanism, concretely: `engine.py`'s `trans_flip()` transition and `vlog.py`'s `El` class + `b_polaroid()`/`card()` dispatcher.

## Personal-path fix

`collage.py:18` hardcoded an absolute path to the repo owner's local `fonts/` directory.

Patched to:

```python
FONT_DIR = os.environ.get("XM_FONT_DIR", str(Path(__file__).resolve().parents[4] / "fonts") + "/")
```

which resolves to this repo's own `fonts/` by default — computed relative to this file's own location (`library/_shared/vlog-collage-runtime/src/collage.py`, so `parents[4]` is the repo root) rather than hardcoded — and can be overridden with the `XM_FONT_DIR` env var. `import os` and `from pathlib import Path` were added alongside the existing imports. Verified by importing the module directly: `FONT_DIR` resolves to a real, existing font file on disk.

## Used by

`page-turn-transition`, `polaroid-card`, `weather-mood-card`.
