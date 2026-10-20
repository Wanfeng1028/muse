# Engine architecture (read before editing `example-explainer.html`)

The explainer is one self-contained HTML file: a **stylized UI mockup** (`.world`) inside a 16:9 `.stage`, driven by a small timeline engine. Everything is data-driven by the `SCENES` array.

## Layout
- `.stage` — 16:9, `container: stage / size` so all sizes use `cqw` units (scale to the stage).
- `.world` — the moving "camera" layer; `transform-origin:0 0` + a CSS transition on `transform`.
- Inside `.world`: the dashboard chrome (top bar, sidebar), the main area (cards row + a left config column + a right result column), a slide-in **proof drawer**, intro/outro **overlays**, and a synthetic **cursor**.

## Scenes
`SCENES = [{ id, cam, cfg, panel, ... , cap, dur, start }]`
- `cam: {cx, cy, s}` — camera focus: center (`cx,cy` as 0..1 of the stage) + scale `s`. `applyCam` converts to `translate()+scale()`.
- `est` + `estHold` — optional "establish" shot: show a wider view (usually `FULL`) for `estHold` ms, then zoom to `cam` (the "show the section, then zoom in" feel). Only during play; `seek` jumps straight to `cam`.
- `cfg` — which left config panel to show (`data-cfg`). `panel` — which right result panel (`data-panel`).
- `hot` — a card to highlight (others dim).
- `cap` — the on-screen caption (acts as burned-in subtitle).
- `dur` — set to the matching VO clip length so audio↔video stay aligned.
- `cues` — see below.
- `overlay` — `"intro"` / `"outro"` title card.

`renderScene(i, instant)` applies all of the above. `seek` calls it with `instant=true` (no establish). `tick` (rAF) advances the clock and calls `frameUpdate()` each frame.

## Cues — 3D lift on the spoken word
`cues: [{ at: <seconds into scene>, k: <key>, cam? }]`. `applyCues` picks the latest cue with `at <= localTime` and:
- **cards**: zooms the camera to that card's `cam` and adds `.lift` (3D rise) to it.
- **lanes / guardrails**: adds `.lift` to the named dropdown item / checklist row.
- **sdk**: opens + lifts the matching dropdown (client / language / model).

Cue `at` times come from the **TTS word timestamps** — find the keyword's start time in `alignments.json` (see `scripts/elevenlabs.py`). That's how a lift lands exactly when the narrator says the word.

## Signature animations
- **Camera establish→zoom** — `est`/`estHold`, CSS transition on `.world`.
- **3D lift** — `.lift` class: `translateY + scale + rotateX` + glow, with `perspective` on the parent.
- **In-place ciphertext→plaintext morph** — `morphHTML(plain, p)`: renders `plain.slice(0,rev)` then a scrambled-but-same-positions remainder (whitespace preserved), so each character flips in place left-to-right as `p` 0→1. (Do NOT slide a separate hex block.)
- **Typed prompt → Send → result** (`animFlow`): phases keyed to scene-local time — type into the input (caret), cursor clicks Send (`.pressed` + click ring), "receiving", ciphertext, in-place decrypt, attestation chips light up, verified. Used by any "run a prompt" scene.
- **3D dropdowns** — perspective `rotateX` open + staggered item reveal.
- **Synthetic cursor** — lives INSIDE `.world`; positioned by transform-invariant layout coords (`placeCursor`) and counter-scaled by `1/cam.s`, so it tracks elements through camera moves.

## Audio as master clock
An `<audio id="vo">` holds the concatenated voiceover. `tick` uses `t = vo.currentTime` when it's playing (`voActive()`), else falls back to a rAF delta clock. Scene `dur`s are set to the VO clip lengths so scene boundaries == audio boundaries → gap-free, in sync.

## Rendering & sync (critical)
Use `scripts/render.js`. Two hard-won rules:
1. **Render at native target resolution** (set `EXPLAINER_W/H`). Never capture small and upscale — that's the #1 cause of a blurry result.
2. **Tag every frame with the player's logical `t`, not wall-clock.** The script logs `[performance.now(), t]` in `window.__log` during a real-time Chrome **screencast** (high fps), then remaps each frame's wall timestamp → logical `t` via `performance.timeOrigin`. Assemble with ffmpeg using per-frame durations = logical-time diffs. This gives screencast's frame rate AND perfect audio sync.
   - A plain screencast timestamped by wall-clock drifts ~2% (voice ends up ~2s ahead). A screenshot loop is sync-correct but too slow at 2K. A "slow-playback" trick breaks CSS transitions (they're wall-clock). The log-and-remap approach avoids all three.

Assembly (after `render.js` writes `frames/` + `frames.json`):
```
# build concat list with per-frame durations = diffs of frames.json times, then:
ffmpeg -f concat -safe 0 -i list.txt -i vo_full.mp3 \
  -vf "fps=30,tpad=stop_mode=clone:stop_duration=4,format=yuv420p" \
  -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest -movflags +faststart out.mp4
```
Verify sync by extracting frames at scene boundaries with `-ss AFTER -i` (frame-accurate) and confirming the visual matches the spoken word. Delete `frames/` afterward (can be hundreds of MB).

## 3D card-rise & button-press on REAL screenshots
When a scene is a real screenshot (not the SVG mockup), you can still get the signature
"element lifts as it's named" and "button presses itself" effects by overlaying *crops of
the same screenshot*:

- **Card-rise:** for a card at fractional rect `{x,y,w,h}`, make an absolutely-positioned
  div over that rect whose background is the screenshot, cropped to the card:
  `background-size: (100/w)% (100/h)%; background-position: (x/(1-w)*100)% (y/(1-h)*100)%`.
  Flat, it sits pixel-identical over the base (invisible). To lift it, use a **self-perspective**
  transform so no ancestor `perspective` is needed:
  `transform: perspective(900px) translateY(-2.4%) translateZ(34px) rotateX(7deg) scale(1.045)`
  plus a drop shadow + violet outline. Dim the base layer (~0.45) while a card is raised so the
  lifted crop pops and the duplicate underneath reads as "below".
- **Stepped sequence:** when narration names several items in one card, lift each crop for a
  short window with staggered `at` times (they rise & fall like steps).
- **Angled fast scroll:** to fly through a long catalog (32 guardrails, all frameworks…),
  zoom in and apply a slight `rotateX` to the scrolling list while translating it quickly —
  "cards moving fast, seen from an angle".
- **Button press (subtle):** crop the button rect and briefly apply
  `transform: scale(.93) translateY(.6%)` + faint glow for ~0.2s, then release, then dissolve
  to the "after" screenshot. Keep it subtle — a big 3D button bounce reads as gimmicky
  (user feedback). Pair with the click choreography: zoom to the button → press → zoom out to
  the result that changed.

## Two production modes
1. **Stylized recreation** (default): rebuild the UI in HTML/CSS from `example-explainer.html`.
   Fully animatable (3D lifts, ciphertext morph, typed prompts). Best when you want polish and
   control. If screens look empty, increase font sizes and fill with real content/elements
   rather than zooming so far in that context is lost.
2. **Real screenshots**: capture the actual product (full-res, consistent theme), show each
   screen full-frame with gentle zoom/pan + the crop-overlay lifts above. Most faithful ("show
   the dashboard as it is"). Capture full states incl. before/after of interactive steps.
