# video20-a2-shots

Shared Python/PIL + OpenCV + numpy rendering code for the "A2" batch of video 20's shot library: shot 13 (全屏对话框/fullscreen-dialog), 14a (风格速切+四宫格/style-quick-cut-grid), 14b (风格刷/style-brush), 18 (左右分屏工作台/split-screen-workbench). These render as `shots/{s13,s14,s18}/` output folders; the code for the files below is identical across all three, so it's ported once here (from `s13/src/`).

## What this is

- `shot13.py` — Shot 13, full-screen chat UI.
- `shot14a2.py` — `Shot14a`, the style-quick-cut + 2x2-grid design actually used for the first half of shot 14 (the render path calls this for frames before the 14a/14b jump cut).
- `shot14.py` — `Shot14`, whose `frame14b()` is the style-brush design used for the second half of shot 14. See "Notes" below on the rest of this file.
- `shot18.py` — Shot 18, split-screen workbench.
- `a2common.py` — shared drawing/compositing kit (copied verbatim — see Notes, it needed no path patch).
- `a2paths.py` — shared paths (patched, see below).

## Environment variables

- `XM_VIDEO_PROJECT_ROOT` (`a2paths.py`) — root of your own video-production working directory. Defaults to `.`.
- `XM_RAW_FOOTAGE` (`a2paths.py`) — your own camera source file, replacing a hardcoded `~/Downloads/copy_*.MOV`. Defaults to `raw_footage.mov`.
- `XM_DEMOS_DIR` (`a2paths.py`) — directory holding the vlog/kepu/faceless demo clips referenced by shot 18's workbench panel. Defaults to `../demos`.
- `XM_SCRATCH_DIR` (`a2paths.py`) — scratch directory for transient mattes/plates/compiled Vision tools. Defaults to `/tmp/xm_scratch` (this batch nests its own work under `<scratch>/a2`).

`a2paths.py` didn't originally `import os`; that import was added so `os.environ.get(...)` works.

## Notes

**`a2common.py` needed no patch.** Despite the general pattern elsewhere in this repo, `a2common.py` has zero hardcoded personal paths — it only imports already-patched names (`SRC_VIDEO, WORK, W, H, FPS, DEMOS`) from `a2paths.py` and never defines or references a `VP` of its own. It's copied verbatim.

**`shot14.py` contains dead code, confirmed against the actual render path.** Its `Shot14.frame14a()` (table-with-cutting-mat design) is superseded by `shot14a2.py`'s `Shot14a` — the source project's own `render.py` only ever instantiates `shot14.Shot14()` for `frame14b()` (the brush design) and routes all earlier frames to `shot14a2.Shot14a`. `frame14a` is only called by a stills-preview tool that wasn't ported. It's harmless to read but not part of any live path.

**`shot13.py`/`shot18.py` docstrings mention `render_v2.py` components — verified NOT a runtime dependency.** Their docstrings say things like "same components as storyboard shot13a/13b (render_v2 chat_bubble / attach_chip / chat_input / ime_bar / chat_header...)" and "(render_v2 workbench / role_card / scissors)", which reads like an import dependency on `storyboard_v2/src/render_v2.py` (1372 lines, not ported here — out of scope for this pass, not fully vetted for personal content, and it mixes in unrelated storyboard-still-rendering code for many other shots). On inspection this wording describes design lineage, not an actual import: both files carry their own local, complete copies of every one of those functions they call — `shot13.py` defines `chat_bubble`/`attach_chip`/`chat_input`/`ime_bar`/`chat_header` itself near the top of the file, `shot18.py` defines `pill`/`role_card`/`scissors` itself. Neither file imports from or otherwise depends on `render_v2.py`, so both run standalone (module-wise) despite the docstring wording. `render_v2.py`'s other exports (`badge`, `hud_brackets`, `glow`) aren't called by either file at all. Treat the "not ported" note as a provenance gap only, not a missing-symbol risk.

**Excluded: `s14/src/assets/`.** Not copied — `style_magazine.png`, `style_film.jpg`, `style_collage.jpg`, `style_launch.png` (the four style-card reference images used by shot 14a's quick-cut grid) have the presenter's own likeness composited into them, and the folder also carries a ~13MB embedded font under `assets/fonts/`. None of this should ship. `library/style-quick-cut-grid/README.md` notes the same gap.
