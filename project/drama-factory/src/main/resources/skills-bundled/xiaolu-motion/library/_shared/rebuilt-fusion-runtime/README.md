# rebuilt-fusion-runtime

`src/vision.swift` and `src/plate.js` are byte-identical across the 4 `fusion-*` real-person-compositing shots (`fusion-word-behind`, `fusion-screen-pip`, `fusion-type-scan`, `fusion-hand-throw`). Canonical reference copies live here; each shot keeps its own working duplicate so it stays independently runnable (`cd library/fusion-*/src && python3 build.py prep ...`) without extra path setup.

## `vision.swift`

The `prep` step's Apple Vision probe: per-frame person segmentation (`VNGeneratePersonSegmentationRequest`, accurate mode), face landmarks, and hand pose (`VNDetectHumanHandPoseRequest`) on the locked base-footage plate. Compiled on demand (needs Xcode command line tools' `swiftc`). Chunked — at most 300 frames per process, each frame wrapped in `autoreleasepool` — for the same memory reason as `qa/vision_probe.swift` at the repo root (see `SKILL.md`'s Vision-probing rule); this is a separate, shot-specific probe rather than a reuse of the root one because it additionally emits hand-pose and full person-segmentation masks that the QA probe doesn't need.

## `plate.js`

Reads the frame-by-frame assets `build.py prep` already produced (person cutout, clean background plate, per-frame face/hand JSON) and exposes them to the shot's own component (`word_behind.js`, `screen_pip.js`, `type_scan.js`, `hand_throw.js`) as a simple per-frame lookup — the actual compositing math (parallax, alpha edge un-premultiply against the known background color, PiP framing, etc.) lives in each shot's own component file, not here.

If you change either file, copy it into all 4 `library/fusion-*/src/` folders to keep them in sync.

## Why these 4 shots need real footage in their previews

Unlike the rest of this library, `fusion-*` shots composite graphics *onto* a real presenter (person segmentation, face tracking, hand-pose tracking) — that is the effect being demonstrated, so `preview.mp4`/`thumb.jpg` necessarily show a real person. This is footage from a video the repo owner already published, used here specifically to demonstrate this technique publicly (not incidental exposure). Every shot's README documents the exact source frame range, the quoted line being spoken, and a verification section (skin-tone color-drift measurement against the untouched original, plus a `qa.pixel_qa` pass) confirming the person's pixels are not degraded and no graphic covers a face/mouth/caption band.
