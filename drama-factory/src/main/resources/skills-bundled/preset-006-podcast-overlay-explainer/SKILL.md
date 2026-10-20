---
name: preset-006-podcast-overlay-explainer
description: "Preset 006 'Podcast-Overlay Explainer' - a full editing skill locked to one captured style: a single static talking-head in a dark, desaturated studio carrying a bright graphics layer - UI-mimicking overlays, full-screen cutaway diagrams, one yellow keyword, white drop-shadow captions, a brand end-card. Measured from a reference. Use when a client wants this exact 'podcast framing + explainer engine' format."
---

# Preset 006 - Podcast-Overlay Explainer (a full skill, locked to one style)

**A preset is not a separate thing.** It is the same skill as everything else in
this pack - same sections, same depth, same laws - but the look, motion grammar
and pacing are **pre-decided from a captured reference** instead of chosen.

**Provenance.** Captured from a **56.6 s, 16:9 single-presenter talking-head explainer** (a local-SEO / Google-ranking lesson) via a **2 FPS frame-level analysis (113 frames, every frame read)** plus measured palette, scene-cut detection and loudness. Palette = **measured**. Cut times and caption behaviour = **measured from frames**. Audio = **measured** (EBU R128).

**Scope.** Single-presenter talking-head explainers in this captured style: intro, comparison, UI/search demo, captions, algorithm explainer, end-card. 40-70 s, 16:9 with a 9:16 cut.

**Asset tier: 1-2. The piece is a person - it needs **the presenter's footage** (supplied). Keep the room (do NOT matte - the set is the background). Generatable assets get prompts in ASSETS-PROMPT.md.**

**Parent skill (PRESET -> SKILL LINKAGE).** This preset is the locked look for
**`skills/podcast-talking-head/SKILL.md`**. When a client asks for this exact style, build
from this preset; when the AI triggers `podcast-talking-head` by name, the skill carries the
same reference-learned patterns (see its "Reference-learned patterns" section).

> **CAPTURED STYLE.** The palette and grammar below are the measured reference,
> requested by the user. Per the pack's style freedom this is simply the chosen
> look. The Camera Law, Sentence Law, caption system, render gate and QA gate all
> still apply.


## STEP 0 — SOURCE GATE (mandatory, BEFORE the assets prompt)

**You cannot plan assets without the material.** Before writing
`ASSETS-PROMPT.md`, obtain at least ONE of:

1. **the video clip** — the footage to edit, or
2. **the voiceover / audio** — the narration track, or
3. **the transcript / script** — the words.

Ask for it up front. If the build is genuinely from-scratch graphics (no source
exists), say so and record it — the concept you write becomes the script.

**Then analyse the source and save the evidence** as `SOURCE-ANALYSIS.json`:

- **If a clip -> video analytics:** `ffprobe` (codec, size, fps, duration, audio
  channels); scene detection for cut times and ASL
  (`ffmpeg -i in.mp4 -filter:v "select='gt(scene,0.3)',showinfo" -f null -`);
  loudness (integrated LUFS + true peak); palette sample (quantise frames ->
  hex); beat/BPM if there is music.
- **If audio -> word-level transcription:** faster-whisper with
  `word_timestamps=True` -> a JSON of `{word, start, end}` per word, plus
  segments. This drives the Visual Narration Plan, the captions and the word
  sync. Recipe: decode to 16 kHz mono WAV with ffmpeg, pass a numpy array, run
  with `MKL_THREADING_LAYER=GNU OMP_NUM_THREADS=1` and `cpu_threads=1`, model
  `tiny` (base/small for accuracy).
- **If text only ->** the sentence list, mapped to the Sentence Law table.

**Only once the source is in hand and analysed** do you write
`ASSETS-PROMPT.md` — so every prompt reflects what the build actually needs.

## STEP 0.5 — A-ROLL PREP (matting first — mandatory when a person speaks)

If this piece has a **person speaking to camera** (talking-head, voiceover,
avatar, podcast), the **first job is the background**, before the concept.
Decide the path in `a-roll-matting`: **keep it / matte it / key it** — and by
default get the character **off the background** (or onto green). Matte FIRST
unlocks text-behind-subject, screen replacement, graphic backgrounds and floating
UI. Use `tools/matte.py` for the local matte (rembg + ffmpeg). Record the matte
as an asset in the manifest and check it at the QA gate (no holes, no baked-
caption artifacts, stable alpha). If the background is the message, keep it.

## STEP 1 — CONCEPT.md (write the plan before any prompt)

With the source analysed, write **CONCEPT.md** — the single plan the whole build
follows. **Everything is connected: every line here drives a later stage, and
every later stage writes its result back here.** Follow `THINKING-SYSTEM.md` — the
planning stack, the four lenses (EZRA), and (when you have only a script) the
only-a-script path.

- **Premise** — the video in one sentence + its emotional arc.
- **THINKING PASS (mandatory).** Work the stack **top-down** — goal -> audience ->
  angle -> concept -> script -> beats -> shots — and record:
  - the target **emotion** per section (EZRA: Emotion, Story, Rhythm, Action);
  - the **beat map** with the **two-column (said | shown)** filled for every row;
  - the **visual plan** table: beat -> viewer question -> visual evidence ->
    risk to review -> final asset;
  - the **retention check** — where the video is most likely to lose people, and
    the fix.
- **Style** — the named build style (this skill) and how it applies here.
- **STYLE PASS (mandatory).** Pick deliberately and record: the **motion style**
  and the **UI style** from `MOTION-UI-STYLE-LIBRARY.md`, and the **caption
  style** from `CAPTION-STYLES.md`. One primary + at most one garnish; name the
  chosen style's failure mode.
- **Segment plan** — the beat map with timings, taken from the analysis.
- **Sentence table** — one row per narration sentence: sentence -> visual concept
  -> lane (A speaker / B visual) -> the **stressed word** to land on -> timing ->
  element bindings -> **camera** (reason + target + zoom). (The Sentence Law.)
- **Camera-track plan** — the ordered camera entries
  (READ / EMPHASIZE / REVEAL / FOLLOW / BREATHE) with their word bindings.
  (The Camera Law.)
- **FEATURE MAP — the Feature Pass (mandatory).** Walk the **full catalogue** in
  `ADVANCED-FEATURE-USE-CASES.md` — camera & framing, motion & animation, speed &
  time, transitions, text, colour, compositing & VFX, audio, AI, stills & design,
  workflow — and record for **every** feature whether it applies and how:
  `feature -> applies? -> where (scene/timecode/sentence) -> how (implementation)
  -> why (the job it does)`. **Every group is visited; no group is skipped.** The
  concept is not finished until every applicable advanced feature has a row (a
  "yes" with no *how* is not a plan; every "no" is a deliberate choice).
- **Contact-sheet plan** — which sign-off variants will be built (V1 Classic Grid
  / V2 Storyboard Filmstrip / V3 Pro QC Sheet) and why. **The variant the user
  picks is written back here.**
- **Sync map** — the word-level timings that drive text and visuals.
- **Asset manifest** — what the build needs (fed by the feature map); this feeds
  STEP 2.

Then STEP 2 writes `ASSETS-PROMPT.md` from this plan.

### PIPELINE CONNECTIVITY LAW (mandatory)
Everything is connected — no stage is decided in isolation, and no stage is
skipped:

- **SOURCE** -> analysed into `SOURCE-ANALYSIS.json`, which feeds the concept.
- **CONCEPT** -> drives the thinking pass, the style pass, the asset manifest, the
  camera track, the sentence table and the feature map; it is the single source of
  truth for the build.
- **ASSETS-PROMPT** -> written from the concept's manifest; nothing unplanned
  appears in the build.
- **BUILD** -> follows the concept's sentence table, camera track and feature map
  exactly.
- **RENDER GATE** -> the contact-sheet variants visualise the concept's beat map;
  the variant the user picks is written **back into CONCEPT.md**.
- **QA GATE** -> `edit-qa-validator` / `tools/qa_check.py` re-check that every
  feature the map marked "yes" actually made it into the edit.
- **SIGN-OFF -> RENDER** -> the full render happens only after the variant AND
  the cut are finalised.
- **A new contact sheet means a new CONCEPT revision.** If the sheet reveals a
  change, the concept is updated FIRST, then the build follows. The record stays
  connected end to end: source -> concept -> assets -> build -> sheet -> sign-off
  -> render.

## ASSETS-PROMPT.md — MANDATORY (strict rule)

After the concept, produce ONE file — **`ASSETS-PROMPT.md`** — listing every
asset the build needs, **one executable brief per item**, addressed to **an AI
agent that has image generation, audio generation AND coding**. No prompt list,
no build.

1. **Images** — image briefs: subject · composition · style · palette (hex) ·
   lighting · aspect + background · negatives.
2. **Transparent images (PNG/alpha)** — briefs ending "transparent background,
   PNG with alpha, no background".
3. **Logos** — a brief, or "client supplies".
4. **Music** — audio briefs: mood · genre · BPM · length · instrumentation.
5. **Sound effects** — audio briefs: type · character · duration.
6. **Code components** — CODING briefs for what code does best (glass cards,
   animated type, diagrams, count-ups, UI mockups, particles, shaders, 3D):
   exact values (hex, px, easing, durations), the motion, and the
   **nested-zip deliverable**: ONE master zip containing a zip per category and
   a zip per component kit (each kit unzips to `index.html`, `styles.css`,
   `README.md`, `assets/`, palette exposed as CSS variables).

**This file IS the prompt** — write it as a self-contained instruction you
hand straight to the agent, ending with the deliverable tree (one zip) and
acceptance checks. A full worked example: `EXAMPLE-ASSETS-PROMPT.md`.

**EXCLUDED — never in this file:** **voiceover** and **ALL video clips**
(A-roll and B-roll). The user supplies the A-roll — voice, primary footage, or a
transcription JSON — at the start. If the build needs any **B-roll clip**, ask
the user for it **separately**; clips are never listed in this prompt file.
(The agent can only generate images, audio and code — it cannot generate video.)

Full format, the kit shape, and a worked example: `ASSET-REQUEST-GUIDE.md`.

## 1. The captured style - what this preset is

**The look in one line:** a **single static talking-head in a dark, desaturated studio**, carrying a **bright graphics layer** in two modes - **UI-mimicking overlays** on the speaker and **full-screen cutaway diagrams** - with **one yellow keyword**, white drop-shadow captions and a brand end-card. Podcast framing, explainer engine.

## 2. Captured palette (measured hex)

| Role | Hex | Use |
|---|---|---|
| Near-black (footage) | `#0D0C0C` / `#0F0D0E` / `#171416` | the dark room |
| Muted warm greys | `#696666` · `#898686` · `#B1A8A5` · `#776664` | skin, walls, sofa |
| Lime green (graphics) | (bright lime) | graphic ground |
| Bright yellow | (highlight) | the keyword |
| White | `#FFFFFF` | UI cards, captions |

## 3. The type system

- **Font:** bold sans-serif, sentence case; a clean UI font for the mimicked interface.
- **Emphasis:** **one yellow keyword** per beat (a highlight), never a whole line.
- **Captions:** white bold, subtle drop shadow, bottom.
- **Badges:** pill labels ('ALGORITHM PREFERENCE', 'MOST RELEVANT').
- **Colour:** the footage is dark; the graphics are bright - that contrast is the strategy.

## 4. Motion grammar

- **Camera:** one **static medium shot**, eye-level, centred - it never moves.
- **Two graphic modes, alternated:** (1) **on-speaker overlay** (face stays visible); (2) **full-screen cutaway** (cut away to a diagram).
- **UI mime:** build a real interface on screen **in sync with the speech** (a search bar types, results appear one by one).
- **Hard cuts** between modes; ~4 s ASL; **breathing stretches** of pure talking-head.
- **Easing:** quick, eased reveals.

## 5. Structure & the captured beat map

| Beat | ~Time | Mode | What |
|---|---|---|---|
| Intro | 0-1 | Talking head | direct address |
| Comparison | 1-6 | Cutaway | card + competitors + 'Shared leads / High intent / Expensive' |
| Search demo | 9-18.6 | Overlay | search bar types 'kitchen remodel near me'; results #1-#3 |
| Captions | 18.6-22 | Overlay | white captions |
| Breathing | 22-33 | Talking head | ~11 s, no graphics |
| Algorithm | 33.8-39.6 | Cutaway | G-sphere, relevance diagram, document highlight |
| Breathing | 39.6-51.8 | Talking head | ~12 s, no graphics |
| End card | 51.8-55.3 | Cutaway | brand mark + one line |

## 6. Audio (measured)

- Integrated **-14.1 LUFS**, true peak **-0.5 dBTP**. Voice-led with a ducked bed.

## 7. Signature techniques

- **UI mime** - a real interface built on screen in sync with the words.
- **Overlay <-> cutaway alternation** (never three graphic beats in a row).
- **One yellow keyword** as the emphasis system.
- **Dark footage + bright graphics** (the contrast is deliberate).
- **Breathing stretches** of unbroken talking-head.
- A **brand end-card** that resolves the argument into one line.

## 8. Common mistakes to avoid

- Moving the camera (this style is a static shot).
- Three graphic beats in a row (alternate overlay <-> cutaway).
- Highlighting a whole line (one keyword only).
- No breathing stretches (the graphics stop landing).


## WHICH LANE IS THE A-ROLL? (function, not source)

**A-roll = whatever carries the meaning. B-roll = whatever supports it.** The
lane is defined by FUNCTION, never by whether it came off a camera.

- In a **talking-head** piece the speaker is the A-roll; graphics and footage
  are B-roll.
- In a **graphics-led** piece — the motion graphics carrying the argument, the
  footage used as cutaways — **the motion graphics ARE the A-roll and the
  footage becomes B-roll.** This inversion is normal and correct; it is the
  hybrid format.
- So when the visual narration carries the meaning, treat the graphics as the
  spine: plan them first, bind them to the words, and let the footage serve them.

## ADVANCED FEATURE USE-CASES (mandatory — the professional toolset)

**"Mandatory" means: if the concept needs it, you use it.** These are the
features that separate a professional edit from an amateur one. Reading
"mandatory" is the prompt to reach for the feature; using the feature is what
makes the video hold up. Full guide + terminal recipes:
`ADVANCED-FEATURE-USE-CASES.md`.

**Timeline & structure** — **multi-track timeline** (layer video/audio/effects,
never a flat single track) · **multi-camera editing** (sync angles, cut on
speaker/action) · **proxy editing** (cut proxies, re-render the same cut list on
the originals) · **batch export** (every ratio from one master) · project
collaboration.

**Motion & animation** — **keyframing** (position, scale, opacity, rotation,
blur on an eased curve) · **motion tracking** (bind text/effects to a moving
object; lowpass the track first) · **masking & rotoscoping** (frame-by-frame
isolation) · **speed ramping / time remapping** (speed curves across a beat) ·
**stabilisation** (2-pass warp) · **frame blending / optical flow** (smooth slow
motion).

**Colour** — **colour correction** (exposure, white balance, contrast FIRST) ·
**colour grading** (the look: LUT, film emulation, split-tone, SECOND) ·
**scopes** (waveform, vectorscope, histogram, RGB parade — grade by the numbers)
· **HDR grading** (only on request; tone-map to SDR for delivery).

**Compositing & effects** — **chroma key** (green/blue removal with spill
suppression and a clean edge) · **compositing / VFX** (combine layers into one
scene) · **3D camera tracking** (solve the move, place 3D in real footage) ·
**advanced transitions & effects** (blur, glow, glitch, light leaks, grain,
chromatic aberration — each timed to a cut or beat).

**Audio** — **noise reduction** (hiss, hum, room tone) · **EQ** (high-pass
dialogue, de-mud, carve space for music) · **audio syncing** (by waveform or
timecode) · **multi-track mixing** (dialogue/music/SFX; duck music 12–18 dB under
voice) · surround/spatial only where the delivery needs it.

**AI & smart** — **auto subtitles** (word-level timing drives captions AND the
narration plan) · **AI background removal** (matte without a green screen) ·
**auto reframing** (re-frame for 9:16 / 1:1 / 4:5 keeping the subject safe) ·
**scene detection & auto cutting** (cut list from scene changes) · **AI
colour/exposure correction** (first pass, then grade by hand).

**Assets & stills** (for every generated image/graphic) — layer-based editing,
layer masks, blending modes · frequency separation (skin retouch) · dodge & burn ·
content-aware fill / object removal · perspective correction · RAW processing ·
tone curves · HDR merge · panorama stitch · AI-assisted selection ·
non-destructive workflow · vector editing (bezier) · gradient mesh · typography
controls (kerning, tracking, leading) · symbol/asset libraries · artboards · grid
systems · multi-format export.

### The Camera Law (mandatory wherever there is a camera)
1. **One camera wrapper only** — all zooms/pans from a single master camera;
   never local ad-hoc transforms on nested elements.
2. **One camera move at a time** — never stack camera transforms.
3. **Every zoom has a reason** — READ / EMPHASIZE / REVEAL / FOLLOW / BREATHE.
   Constant zoom = no zoom.
4. **Do not cut while zoomed** — return to rest or hold the scene.
5. **Motion blur only during fast motion** — `blur = clamp(v*k, 0, max)`, zero at
   rest (start k ≈ 0.012, max ≈ 24 px). **Anchor zoom** sets the origin on the
   target; **follow** keeps the subject in a safe zone with a damped spring.

**The test:** walk the timeline. For each feature the concept needed, ask "is it
there, and is it doing a job?" A missing needed feature — a flat single track, an
ungraded image, a jittery tracked label — means the edit is not finished.

**For this skill:** multi-track layering, keyframing, motion tracking for the overlay, masking, the UI-mime build (code components), colour grade (dark + desaturated), multi-track audio, and the cutaway diagrams.

## MANDATORY FEATURE USE-CASES (the modern standard)

These are not optional extras. Each has a job; if the job is missing, the edit
reads as amateur. Apply what the concept needs — the items marked **★** apply to
almost every build.

**Camera & motion**
- **★ Zoom in (anchor zoom)** — bring a detail to readable size; origin on the
  target; return to rest before the next cut.
- **★ Zoom out (reveal)** — pull back for context after a detail; wide <-> detail
  rhythm is the pacing engine.
- **★ Motion tracing / follow camera** — the camera follows the cursor or the
  action (safe-zone follow, spring-damped); never leave motion under a static
  frame.
- **Slow push** — <=8% over 3-5s for tension.
- **Camera shake on impact** — a brief 2-4 frame shake on a hit.
- **Speed ramp** — slow->fast or fast->slow across a key beat.
- **Motion blur (velocity)** — blur only while fast; exactly 0 at rest.

**Keyframing & animation**
- **★ Keyframe everything** — position, scale, opacity, rotation, blur; nothing
  moves without keyframes and a curve.
- **★ Easing curves (bezier)** — every move eased, never linear; curve the PATH
  (bezier), not just the timing.
- **Mask / wipe reveal** — draw-on reveals, mask transitions, trim-path draws.
- **Parallax / 2.5D depth** — layers move at different rates (<=3-6% travel).
- **Freeze frame / hold** — stop on the moment that matters.

**Text & data**
- **★ Kinetic text / word-pop** — words appear on the beat; one accent keyword
  per line.
- **★ Count-up numbers** — every stat animates to its value on the spoken word.
- **Text tracked to an object** / **text behind the subject** — for hybrid pieces.
- **Callouts & arrows** — draw-on annotations pointing at the thing.

**UI & product (mandatory for ANY demo)**
- **★ Readability zoom** — any UI text the viewer must read renders >=4% of frame
  height (>=44px at 1080p).
- **★ Micro-interactions** — hover, press, ripple, toggle, focus; the UI answers
  the cursor.
- **★ Screen transitions** — push/pull navigation, modal rise + scrim, sheet slide.
- **★ Cursor physics** — bezier path, minimum-jerk timing, overshoot, click anatomy.
- **Comparison split / PiP** — two states side by side.
- **Screen replacement** — UI on a device.

**Edit & finish**
- **★ Cut-on-beat / cut-on-action** — cuts land on the beat or mid-movement.
- **★ A sound for every cut** — whoosh/impact/tick; silence before the biggest hit.
- **★ Correct then grade** — exposure and white balance first, then the look.
- **Seamless loop** — for social/web loops (end state = start state).

**The test:** open the finished timeline and ask, for each ★, "did this build use
it where the concept needed it?" If a needed ★ is missing, the edit is not
finished.

## CAPTION & TEXT SYSTEM (mandatory)

**The Text Law.** On-screen text maps the visual — it is never generic subtitles.
A plain SRT ships separately as an optional accessibility file; it is NOT the
on-screen text. Every build declares ONE caption style and holds it.

### The three caption modes (choose per build; a build may use all three)
1. **Styled text captions** — designed, on-brand and animated: a declared style
   (font, weight, size, tracking, leading, case, fill, stroke/box, accent colour,
   entrance/exit) held consistently, keywords accented, text timed to the word.
   Never the OS default font, never a plain white box.
2. **Transparent-background captions (alpha)** — captions with **no background**,
   delivered as transparent PNGs (or an alpha clip: WebM VP9 alpha / ProRes 4444),
   so the type sits over or behind the picture: outline-only text, sticker/karaoke
   text, cut-out words, and **text-behind-subject**. Clean, premultiplied alpha.
3. **Chroma-key text & subject** — text or a subject shot on a flat green/blue
   screen and keyed so it floats over the graphic layer; or the subject keyed so
   text can pass behind them.

### Styled-caption spec (write it into CONCEPT.md)
- **Style sheet** — font · size (>=4% frame height for anything the viewer must
  read) · weight · tracking · leading · case · fill · stroke/shadow · box (none /
  subtle / solid) · accent colour · safe-zone position.
- **Timing** — word-level (from the transcription JSON); the caption lands on the
  spoken word (+/-100 ms); <=2 lines; <=17 characters/second; minimum cue ~0.84 s.
- **Motion** — entrance/exit eased (fade + rise, or a word-pop scale), never
  linear; one accent keyword per line.
- **Placement** — inside the text-safe zone (Platform standards); never under the
  platform UI.

### Transparent-caption spec
- Deliver as **PNG with alpha, no background** (or an alpha clip for animated
  type). Clean the edge: 1-2 px feather, no dark/light halo, premultiplied.
- **Text-behind-subject** — composite a text layer UNDER the subject's alpha
  matte (matte from chroma key or an AI matte). The subject needs a clean cut-out;
  where the cut is rough, choke the matte.
- Never a white box behind a "transparent" caption.

### Chroma-key spec
- Key on a **flat, evenly lit green (#00B140) or blue**; avoid green clothing,
  props and spill on hair/shoulders.
- Key, then: **despill** the edges · **choke** the matte 1-2 px · add a **light
  wrap** so the subject belongs to the new background · a **garbage matte** to
  remove rigs.
- Composite over the graphic layer with matched grain and colour; grade the
  subject and background together so the seam disappears.

### Pick the style from CAPTION-STYLES.md
Choose ONE named caption style — **Apple-Clean · Vox-Highlighter · Sticker-Pop ·
Outline-Alpha · Karaoke-Word** — and declare it in CONCEPT.md.

### Request these in ASSETS-PROMPT.md
The transparent caption PNGs / alpha clips go under **transparent images
(PNG/alpha)** (category 2); the styled-caption font/style and any animated
caption engine go under **code components** (category 6).

### Surprise pack — make the text move (use where the concept needs it)
- **Kinetic typography** — word-by-word reveal, anchor repositioning before each
  word, one accent word per line.
- **Word-pop / karaoke captions** — per-word scale pop from word-level timing.
- **Animated underline / highlight / hand-drawn circle** — draw-on accents on the
  key word.
- **Text-behind-subject / rotoscoped text** — type passing behind a keyed subject.
- **Alpha overlays** — lower-thirds, sticker captions, floating labels as PNG/alpha.

## RENDER GATE — the contact sheet (mandatory before the full render)

**Never render the full video without sign-off.** Before the final render,
extract one frame per second and build a **contact sheet** for approval:

`ffmpeg -i build.mp4 -vf fps=1 sheet/f%04d.jpg`

Then **offer the user a choice of contact-sheet variants** — build 2-3 and let
them pick. The sheet is the cheapest place to catch pacing, composition,
safe-zone and continuity problems; a variant lets the reviewer read the edit the
way that suits them.

### The contact-sheet variants (build at least TWO; label them V1 / V2 / V3)
- **V1 — Classic Grid.** A uniform grid of 1 FPS frames in time order (left to
  right, top to bottom), each frame labelled with its **timestamp**. The baseline
  read of the whole edit at a glance.
- **V2 — Storyboard Filmstrip.** Larger frames laid in horizontal rows over a
  **time ruler**, with **scene-cut ticks** marked on the ruler and a one-line
  **caption** under each frame (what happens in that second). Reads like a
  storyboard; best for reviewing pacing, flow and the beat map.
- **V3 — Pro QC Sheet.** A dense technical sheet: each thumbnail carries its
  **timecode**, a **scene-cut flag**, a **motion/velocity indicator**, and a
  **safe-zone overlay**; a **colour-swatch strip** (the sampled palette) and a
  **summary header** run across the top (duration, shot count, ASL, loudness
  LUFS + true-peak, palette). Best for technical sign-off and continuity.

Build them at whatever aspect suits the cut (grid for a horizontal piece, a
vertical column for 9:16). Keep the Apple Standard chrome and the brand accent.

### The ask (mandatory)
Present the variants and ask the user directly:

> "Here are the contact-sheet variants — V1, V2, V3. **Did you like any of
> these, or shall I generate more variants so you can choose?**"

Then wait. If they want more, generate additional variants. **Render the full
video only after they finalise** — both the variant they prefer and the cut.

## QA GATE — validate before delivery (mandatory)

Before the full render and again before delivery, run the **`edit-qa-validator`**
skill. It does three passes:

1. **AUDIT** — walk the MASTER CHECKLIST (every mandatory list in the pack: the
   advanced toolset, the modern-standard features, the Camera Law, the Sentence
   Law, the Caption & Text System, the visual narration layer, the render gate,
   ethics and platform) and mark each item OK / WEAK / MISSING / N/A.
2. **AI RE-THINK** — for every WEAK or MISSING item, propose the concrete fix:
   what to add, where (scene / timecode / sentence), how (the exact move or kit),
   why it improves the video, and the expected gain.
3. **REVALIDATE** — re-audit after the fixes and produce the diff; PASS only when
   no star-mandatory item is MISSING and the caption system, Camera Law and
   Sentence Law are clean.

Write the report as `EDIT-QA.md`. **The edit is not finished until the QA gate
passes.**

## Platform & delivery standards (self-contained reference)
Platform UI and specs change; values are working standards (2026). Where sources disagreed the more conservative value is used. Re-verify before a paid campaign.

### 1. Vertical safe zones (1080×1920)
Safe zones are a *margin*, not a pixel-exact map; they differ per app and Reels
can additionally crop the feed preview to 4:5.
| Zone | Rule |
|---|---|
| **Universal action-safe** | keep faces/products/key action inside the centre ≈ **900×1330** |
| **Universal text-safe** | keep captions, prices, CTAs, legal text inside the centre ≈ **860×1100**, biased slightly above centre |
| **Shorts (measured)** | top ≈ 240px · bottom ≈ 380px (title/Subscribe) · right ≈ 200px (action column) · left ≈ 60px |
| **TikTok / Reels** | bottom caption tray is deep; right button column ≈ 120–200px; Reels feed preview can crop top/bottom ≈ 285px |
| **Rule of thumb** | design for the most restrictive app (Instagram bottom UI); then it works everywhere |
Always preview in the platform's own safe-zone checker/template.

### 2. Audio loudness (ITU-R BS.1770 integrated)
| Destination | Integrated | True peak ceiling |
|---|---|---|
| YouTube long-form, music, web | **−14 LUFS** | **−1 dBTP** (−2 if heavy codec risk) |
| Social vertical (Reels/TikTok/Shorts), mobile | **−16 to −14 LUFS** | −1 dBTP |
| Podcast (stereo) | **−16 LUFS** (−19 mono) | −1 dBTP |
| Broadcast TV | −23 LUFS (EBU R128) / −24 LKFS (ATSC A/85) | −1 to −2 dBTP |
| Streaming/VOD drama spec | −24 to −27 | −2 dBTP |
Use a **true-peak-aware limiter**, not a sample-peak limiter. Dialogue sits
~6–10 dB above music beds; duck music 12–18 dB under voice. Platforms only turn
loud files *down*, so do not chase loudness past the target.

### 3. Picture
- **Frame rate:** keep source rate. 24 = cinematic; 25 = PAL regions; 30 = web/social/talking-head; 50/60 = gaming, sports, screen capture, slow-mo source. Never mix rates without conforming. 180° shutter for live action (shutter ≈ 2× fps).
- **Colour:** Rec.709 / sRGB delivery. Tag colour metadata (`-colorspace bt709 -color_primaries bt709 -color_trc bt709`) so players don't shift gamma. HDR only on explicit request.
- **Resolution:** 1080p minimum, 4K master where source allows. 1080×1920 vertical.
- **Export (H.264):** `-c:v libx264 -preset slow -crf 16-18 -pix_fmt yuv420p -profile:v high -movflags +faststart`, AAC 48 kHz 192–320 kbps. Constant frame rate (variable-rate screen recordings must be conformed first).

### 4. Captions & accessibility
- Always deliver a sidecar **SRT/VTT** (accessibility, SEO, translation). Burn captions in only for social-first formats.
- Burned captions: ≤2 lines, ≤ ~42 characters/line, ≤17 chars/sec, minimum cue ≈ 0.84s, high contrast (stroke or box), inside text-safe zone.
- Never rely on colour alone to carry meaning; keep contrast ≥ 4.5:1 for text.
- Flash safety: no more than 3 flashes per second (photosensitivity).

### 5. Pacing benchmarks (average shot length, ASL)
| Style | Typical ASL | Notes |
|---|---|---|
| Short-form retention | 1–3 s | visual change every 2–4 s |
| Esports / kinetic hype | 0.4–1.5 s | cut on the beat/drop |
| E-commerce / DTC ad | 1.5–3 s | hook ≤ 1 s |
| Talking-head / creator | 3–8 s | visual event every 6–10 s |
| Podcast multicam | 4–10 s | cut on speaker change; reaction shots 1–2 s |
| SaaS demo | 3–6 s | one action per beat |
| Corporate / brand film | 3–6 s (interview 6–20 s) | B-roll 2–5 s |
| Real-estate flagship | 4–8 s | slow, held, gimbal |
| Wedding / event highlight | 2–5 s | emotional beats held longer |
| Luxury / minimalist | 5–12 s | stillness is the point |

### 6. Delivery checklist (every skill)
Hook/first frame verified · loudness + true peak measured, not guessed · safe
zones checked in platform overlay · captions file delivered · colour tags set ·
CFR confirmed · file plays on a phone in sound-off AND sound-on.

## 6. QA
Best work first · rights confirmed per clip · credits accurate · cuts on beat · no repeated transitions · contact details legible ≥ 3 s. Director's review: would the target viewer understand and trust this in the first 5 seconds?

## 7. Hard limits
No claiming others' work, no unlicensed music or footage, no breaching client NDAs, no invented clients or results. No voice generation.
