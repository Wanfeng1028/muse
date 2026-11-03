# paper-craft-components

Documentation home for video 20's recurring "paper craft" visual primitives — the small set of drawing functions that reappear across most of its A0/A1-batch shots. `sb_lib.py` and `a0lib.py` are duplicated here verbatim from `../video20-a0-shots/src/` and `../video20-a1-shots/src/` purely so these concepts have one place to be read and pointed at, independent of which shot batch happens to use them at runtime. (`sb_lib.py`'s `FONTS` constant originally used `os.path.expanduser('~/Projects/xiaolu-motion/fonts')` — a personal path that a literal `/Users/`/`maxzhl` grep doesn't catch; patched here and in both other copies to an `XM_FONT_DIR`-overridable default, same pattern as the rest of this repo's ported code.) The copies actually imported by the shots are the ones under the `video20-a{0,1}-shots` folders.

## Function → concept map

**纸条字幕 / paper-strip subtitle**
Static version: `sb_lib.py:subtitle_c()`. Animated "production" version (marker-brush stroke-in + keyword pop): `a0lib.py:strip_geometry()` / `strip_image()` / `strip_state()`.

**关键词弹出 / keyword pop**
`a0lib.py:pop_curve()` (the bounce easing curve) + `sb_lib.py:label()` / `vlabel()` (the pill/tag chip the keyword pops into). Note: this repo's `components/kinetic_keyword.js` is a **different, already-shipped implementation** of the same concept — character-by-character rise + blur + fade, a "tech HUD" visual style, ported from a different source project. The two are not interchangeable; they're different visual languages for the same idea. Neither supersedes the other here.

**步骤条 / step bar**
Static: `sb_lib.py:step_bar()`. Animated: `a0lib.py:step_bar_image()`. Note: `components/chapter_tag.js` also has a segmented-progress-bar mechanic (HUD scanline style vs. this paper-card look) — same "two styles, not merged" relationship as above.

**右下人像框 / bottom-right PiP frame**
Static: `sb_lib.py:pip_crop()` / `pip_card()` / `add_pip()`. Animated (the "whole frame warps into the box" version actually used in the video): `a0lib.py:pip_region()` / `pip_layer()` / `_pip_frame()`. The "eyelid closes" variant is separate, hand-animated logic specific to one shot — see `library/clip-narration-pip/README.md` — not a generic parameter of these functions.

**章节铃 / chapter tag**
`sb_lib.py:chapter_tab()`. Note: `components/chapter_tag.js` is the already-shipped, more complete JS version (different visual style) — same both-exist relationship as above.

## Notes for whoever writes `LIBRARY.md`

These 4 concepts don't have their own `preview.mp4`/`thumb.jpg` here — they're building blocks used throughout many shots, not one isolated moment. Link each row to whichever shot's preview best demonstrates it:

- paper subtitle strip — visible in nearly every shot preview in this library.
- step bar — `library/big-number-stepper/` (镜12).
- PiP frame — `library/clip-narration-pip/` (镜7-9).
- chapter tag — `library/fullscreen-dialog/`, `library/film-lightbox/`, `library/live-selfcheck-redo/`, `library/split-screen-workbench/` (镜13/14/15/16/18) all show the chapter tab.
