# rebuilt-shotkit

`src/shotkit.py` is byte-identical across all 11 rebuilt shots (the 7 `card-*` fullscreen motion cards and the 4 `fusion-*` real-person-fusion shots) — this is the canonical reference copy for reading/diffing. Each shot's own `src/shotkit.py` is kept as a working duplicate rather than an import from here, so every shot folder stays independently runnable (`cd library/<shot>/src && python3 build.py render ...`) without any extra `sys.path`/`PYTHONPATH` setup.

## What it does

Renders a shot's component (a `components/*.js`-contract module: `params`/`draw`/`bbox`/`mbSamples`/`post`) in headless Chrome via the repo's own `engine/runtime.js`, with sub-frame motion blur, glow, vignette and grain; mixes in `xlaudio`-synthesized sound effects; muxes audio and video, verifies the frame count, atomically renames the output, and produces the 360p `preview.mp4` + `thumb.jpg` pair each shot folder ships. Each shot's `src/build.py` just supplies its own `SHOT` config (component module, params, sound cues, timing) and calls into this.

If you change something here, copy the same file into all 11 `library/{card-*,fusion-*}/src/shotkit.py` to keep them in sync (or diff against this copy before assuming a shot folder is current).
