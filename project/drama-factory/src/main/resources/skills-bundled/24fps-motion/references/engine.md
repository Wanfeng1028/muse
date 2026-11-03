# 24fps engine reference

Trimmed copy of https://24fps.dev/video-editor/llms.txt (the live file also lists every preset by id). Engine: https://24fps.dev/editor/engine.js (MIT, ES module, no dependencies).

## How to apply a preset
1. Fetch the engine: https://24fps.dev/editor/engine.js (ES module, no dependencies).
2. Fetch a preset: https://24fps.dev/video-editor/{section}/{id}/preset.json
3. mount(overlayElement, { kind, preset, script?, media }) then render(seconds) per frame. kind is captions | text | transition | effect | layout (hooks and font pairs are "text").
   media: { main } for most kinds, { a, b } for transitions, plus { second, fg } for layouts; fg is a transparent cut-out of the subject (needed for z: "behind-subject" text).
4. HyperFrames: drive render from the paused GSAP timeline. Remotion: call render(frame / fps) in useLayoutEffect.
Sizes are fractions of frame height; positions are fractions of width/height. Fonts are Google Fonts.
Agents: search with the MCP tool search_editor_assets (https://24fps.dev/mcp); get_editor_asset returns the preset, a ready agent prompt and a HyperFrames or Remotion starter file.

## Which kind do I need
- Words said in the video, timed to the voice: captions
- A title, quote or stat on screen for a few seconds: text
- The first three seconds of a short, with the line and the staging: hook
- Moving from clip A to clip B: transition
- A zoom, shake, grain or colour grade on one clip: effect
- Where the speaker sits, split screens, picture-in-picture: layout
- Which Google fonts to pair for display, captions and accent: font-pair
- Text hidden behind the speaker: text with z: "behind-subject" (needs a cut-out)
- Word-by-word highlight (karaoke): captions
- A branded look for the whole video: effect with a grade, plus a font-pair

## Transition energy
- Calm (interviews, essays): crossfade, blur-dissolve, ink
- Medium (vlogs, tutorials): whip, push, zoom-in, zoom-out
- High (hype, music, gaming): glitch, flash, rgb-split, strips
- Hard cut or dip to black or white: cut, dip
- Reveals and section breaks: wipe, circle, shape, blinds
- preset.at is the time of the cut and preset.dur its length; each preset's type is its transition name

## HyperFrames CLI cheat-sheet
- npx hyperframes beats song.mp3: beat timestamps to place cuts and hits
- npx hyperframes transcribe clip.mp4: word timestamps for the captions kind
- npx hyperframes remove-background clip.mp4 -o clip.fg.webm: the fg cut-out for behind-subject text
- npx hyperframes media-use resolve --type sfx --intent "whoosh" --project .: fetch a sound effect (needs heygen auth login, or --local-only)
- npx hyperframes render: render the composition to MP4
- npx hyperframes check: lint and validate before rendering

# Preset fields
### Fonts
Google Fonts only (open licenses), exact family names as on fonts.google.com, weights that family actually has.
Font object: `{"family": "Anton", "weight": 400, "italic": false}`. Mix families freely (bold sans + italic serif is a classic).

### Units
Sizes are fractions of frame HEIGHT (0.06 = 6% of the height). x/y are fractions of width/height, 0..1, measured to the
element centre. Times are seconds. Previews run ~5 s clips; keep entrances inside 0–4 s.

### captions
Word-timed captions. Envelope adds `"script": "Sample line with *emphasis* words"` (asterisks mark emphasis words).
preset keys:
- font, emphasisFont (font object + optional color, scale (0.8–1.8), stroke, gradient, case)
- size 0.03–0.12 · y 0.1–0.9 · align left|center|right · wordsPerLine 1–6 · maxLines 1–3 · lineHeight · gap (em)
- animIn: none|fade|rise|drop|slide-left|slide-right|pop|slam|scale|blur|bounce|mask-up|flip|stretch|spin|type|glitch|
  wipe-right|wipe-left|wipe-down|reveal-center|iris|flip-x|flip-y|zoom-in|shrink|swing|roll|fly-in|corner|drop-bounce|jelly|flicker|blur-slide|rise-blur|squeeze|rotate-in|disintegrate
- animDur 0.05–0.6 · animScope word|page · stagger (s, for page scope) · ease linear|out|in|inOut|expo|back|elastic|snap
- karaoke: none|color|past|bg|scale|underline|dim · color · activeColor · activeBg
- stroke {width: 0.02–0.2 (em), color} · shadow true|"css text-shadow" · case upper|lower|none · tracking (em)
- box {bg, pad (em), radius (em)} · gradient ("linear-gradient(...)") · hold (s after last word)

### text (kinetic text scene)
preset: {"duration": 5, "layers": [layer, ...]} (1–6 layers). Layer keys:
- text (required; \n breaks lines; blank " " makes a one-line panel with bg), font, size 0.03–0.6, x, y, align left|center|right, width (0..1, for wrapping)
- z: back | behind-subject | front  (behind-subject = between the background footage and the cut-out person; use with sample talking-head/vertical-talking)
- color, gradient, stroke {width,color} (outline text: color "transparent" + stroke), shadow, bg (box behind text), radius, blend (CSS mix-blend-mode: difference, overlay, screen…), opacity, rotate (deg), tracking (em), case, lineHeight
- in: {type: <animIn values>, split: none|words|chars, order: forward|reverse|random|center|edges, at, dur, stagger, ease}
- out: {type, at, dur, order, ease} (the exit plays the entrance backwards: scale, rotation, flips and wipes all apply)
- loop: none|float|pulse|shake|marquee|swing|wobble|jump|wave|flicker|spin|heartbeat|breathe|rainbow|glitch
- shine: {"color": css (rgba(255,255,255,.9)), "every": s between sweeps (2.5), "width": highlight width as frac of the text (0.2), "dur": sweep time (0.8)} — a highlight sweeps across the letters once the layer has entered, until its exit.
- emit: {"kind": snow|dust|sparkle|embers|confetti|hearts|stars|bubbles|bokeh|rain, "count" (per letter, 1–12, default 3), "colors": [...], "size" (frac of height), "life" (s), "from": "letters", "when": "in"|"out"|"loop"} — particles burst from each letter's box as it enters, as it exits (needs `out`) or continuously. Pair `out.type: "disintegrate"` (letters drift, blur and fade away) with `when: "out"` for a dissolve-into-particles exit; works with split chars/words or whole-layer text.
Think in scenes: giant word behind the subject + small caption in front; stacked multi-font headline; outline + filled duplicates; ticker; label + number; etc.

### transition (between clip A and clip B)
preset: {type, at: 1.2, dur 0.15–1.2, dir left|right|up|down, color, ease, blur (px), slices, cx, cy}
type: cut|crossfade|dip|flash|push|whip|zoom-in|zoom-out|spin|wipe|circle|diagonal|blinds|glitch|burn|rgb-split|
 flip (3D card flip)|cube (3D cube rotate)|page-turn|split (doors opening from centre)|clock (radial sweep)|strips (staggered bars)|
 checker (random tiles)|shape (shape: diamond|star|heart, cx, cy)|ink (soft radial bleed)|slide (B slides over A)|uncover (A slides off B)|
 stretch|swirl|blur-dissolve|light-sweep|luma
luma: {"dir": left|right|up|down (default left), "soft": edge softness 0–1 (0.4; 0.05 is nearly hard), "color": optional css colour, dips to it at the midpoint} — B is revealed through a moving gradient mask (a luma fade / soft wipe).

### effect (on one clip)
preset: {type, amount, dur, beats [s,...], speed, bpm, over, size, at, ox, oy, grain (bool), vignette 0–1,
 grade {contrast, saturate, brightness, sepia, hue (deg), tint (css color or gradient), tintBlend (css blend)}}
type: punch-in|slow-zoom|ken-burns|shake|handheld|bounce-zoom|blur-in|rgb-split|flicker|vhs|mirror|letterbox|speed-ramp|light-leak|freeze-flash|duotone|grain|grade|
 swing (pendulum)|sway|spin-loop|flip-3d|zoom-hit (on beats)|strobe (bpm)|invert-flash (on beats)|blur (amount px)|dir-blur (motion blur, amount)|
 wave (water warp, amount)|heat (heat haze, amount)|flare (moving lens flare)|particles (kind)|pixelate (mosaic)|tilt-shift
tilt-shift: {"type": "tilt-shift", "amount": blur px (10), "size": height of each blurred band as frac of the frame (0.35), "focus": y of the sharp zone centre, 0.2–0.8 (0.5), "only": "top"|"bottom" (default both)} — two bands blur the frame (backdrop-filter + mask) and fade to sharp towards the focus: the miniature look. Takes grade/vignette like any effect (saturate 1.4 sells the toy-town look).
particles: {"kind": "snow|dust|rain|confetti|embers|bubbles|bokeh|sparkle|hearts|stars", "count", "color", "colors": [...], "size"} — on any effect, or type "particles" with "kind".
grade also takes grayscale (0..1) and invert (0..1).
subject: {"outline": css color, "width": cqh (0.35), "glow": css color, "blur": cqh (1.2), "pulse": Hz} — traces the cut-out subject (media.fg) with an outline and/or glow; use type "subject" (no move on the background) or combine with grade to dim the background. `"subject": {}` alone keeps the person sharp and still while blur/spin/warp effects move only the background.
pixelate: {"type": "pixelate", "size": block size as frac of height (0.04), "from", "to": animate it over "dur" (1.2 s, from "at", ease inOut) — {"from": 0.08, "to": 0} resolves from mosaic to sharp; blocks under 2 px turn the effect off}. SVG filter: costly on large frames.
echo: {"count": 1–6, "dx": frac of width per copy, "dy": frac of height, "scale": per-copy scale step (-0.05 shrinks), "opacity": first copy (later ones fade), "delay": s of time offset per copy (video cut-outs only), "tint": css colour (flat silhouette), "blend": mix-blend-mode, "spread": animated sway (frac of width), "ox"/"oy": scale origin} — copies of the cut-out beneath the real one: clone, echo, afterimage, "triple". Needs media.fg like subject (the library gives it automatically); combines with `subject`. Use type "echo" (no move on the background).
stack: [effect preset, ...] (1–5, layer `type` optional = no motion) — several effects on the same footage; the top-level preset is the first layer. Scale multiplies, translate/rotate/blur add, filters concatenate, overlays (grain, vignette, particles, flare, tint, letterbox, scanlines) all apply. e.g. {"type": "handheld", "stack": [{"type": "light-leak"}, {"vignette": 0.4}]}. Stack layers can carry subject/echo too (only one `subject` outline applies).
(`grade` = colour look only; any type can also carry grade/grain/vignette.)

### layout (subject positioning / composition)
preset: {bg, inDur, slots: {main, second, fg}, layers: [text layers]}. main = A-roll (talking head), second = B-roll, fg = cut-out person (transparent).
Each slot may set focus {x, y} (0–1, default 0.5, 0.25): the point of the clip kept in frame when the slot crops it; the default keeps a talking head's face in a circle or half-split.
slot: {x, y, w, h (0..1 of frame, top-left origin), radius (fraction of height), z, shadow (bool), border {width (cqh), color}, fit cover|contain, from {x, y, scale} (entrance offset)}
Examples: split top/bottom, PiP corner, pop-out presenter over B-roll, framed card with headline, side-by-side, cinematic letterbox with title.

### hook (first 1–3 seconds)
Envelope adds: "formula": "the copy pattern with [slots]", "examples": ["3–5 example hook lines"], "structure": [{"at": 0, "dur": 0.8, "beat": "what happens"}],
"pairs": {"captions": "<captions id>", "effect": "<effect id>", "transition": "<transition id>"} (ids from other files when you know them, else omit),
and "preset": a text-scene preset rendering the first example line (kind text rules).

### font-pair
Envelope adds "fonts": {"display": font, "caption": font, "accent": font (optional)}, "mood": "...",
and "preset": a text-scene preset showing the pairing (e.g. display word + accent italic word + small caption line).

### Engine API
`mount(root, opts)` returns `{ render(t), destroy(), ready }`. `ready` is a Promise that resolves when the fonts the preset asked for have loaded (v0.4.0+; `await fx.ready` before the first captured frame in an export, `await (fx.ready ?? Promise.resolve())` to also support 0.3).
