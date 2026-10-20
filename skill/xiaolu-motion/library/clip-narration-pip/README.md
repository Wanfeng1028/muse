# clip-narration-pip · 成片讲解+右下人像框含眼皮合上 (clip-narration-pip, 镜7/8/9)

The presenter narrates over a finished demo clip playing in a bottom-right PiP frame — shots 7 (vlog) and 8 (科普/kepu) are the plain version; shot 9 (不露脸/faceless) additionally closes the PiP like an eyelid while the presenter explains "如果你不想露脸".

## Source
`../_shared/video20-a1-shots/src/explain.py`, classes `Shot07`, `Shot08`, `Shot09` (all subclass a shared `ExplainShot` base defined earlier in the same file).

## How it works
Each shot maps its own output frames to source demo-clip frames through a `TimeMap` — a list of `(f0, f1, 'play'|'hold', demo_frame)` segments hand-tuned so specific on-screen events in the demo footage (a page flip, a sticker subtitle popping, a diagram being drawn) land on the matching spoken word, with idle stretches held or skipped rather than played at 1:1 speed. The demo content is composited into a rounded PiP card via the shared PiP primitives. Shot 7 additionally applies local "zoom" pushes (`zoom_m`) onto specific UI elements inside the demo footage (a subtitle sticker, a time/weather/mood card) timed to their own keyword. Shot 8 patches out the demo's own nested PiP-within-a-PiP using a Coons-patch inpaint (`coons_patch`) of the surrounding dark stage, so only the presenter's real face reads as "in frame." Shot 9 layers on the eyelid: two paper flaps close over the PiP at eye level (`closure()`, an eased 0→1 progress), hold shut for under 3 seconds while the presenter says "不想露脸," then reopen on "配上你的解说."

## Notes
Shot07/Shot08 are the plain narration+PiP variant (no eyelid animation), using the same PiP mechanism documented as a reusable primitive under `../_shared/paper-craft-components/` (`pip_region`/`pip_layer`/`_pip_frame` in `a0lib.py`). Shot09 layers the eyelid-close on top of that same PiP — the eyelid itself is hand-animated logic specific to this one shot, not a generic parameter of the shared PiP primitives.
