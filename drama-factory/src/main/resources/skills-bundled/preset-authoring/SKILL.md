---
name: preset-authoring
description: "Turns a reference video (supplied as a frame-level contact-sheet PDF, a video file, or a link) into a reusable PRESET: a named, portable style recipe covering palette, type behaviour, motion grammar, transitions, pacing and structure, saved as a skill file under presets/. Use when the user supplies reference frames or a video and wants that exact editing style captured and reproduced."
---

# Preset Authoring — capture a reference's editing style

**Scope.** Given a reference (contact-sheet PDF, video file, or link), produce a
**preset**: a portable skill file that reproduces that style. One reference →
one `presets/preset-NNN-<name>/SKILL.md`.

**This is the one sanctioned override of the Apple Standard** — a preset is
explicitly requested by the user. Everywhere else, Apple Standard governs.

## PRESET -> SKILL LINKAGE LAW (mandatory)

A preset is not a dead end. When you capture a reference into a preset you MUST
also **patch the parent skill** it belongs to, so the AI that triggers the *skill*
by name (not the preset) inherits the real-world learnings.

For every new preset:
1. Name its **parent skill** (e.g. a podcast-explainer preset -> `podcast-talking-head`).
2. Add a **"Reference-learned patterns"** section to that skill: the 4-8 concrete
   patterns measured from the reference (the camera rule, the overlay grammar, the
   type system, the rhythm).
3. Add a one-line **pointer** in the parent skill to the preset, and in the preset
   to the parent skill (the "Parent skill (PRESET -> SKILL LINKAGE)" line).
4. Keep the pack's laws (Camera Law, Sentence Law, caption system, gates) unless
   the reference genuinely differs - then say so.

This is why "the skill vs the real editing concept is the main thing": the preset
locks ONE look, but the *skill* must get smarter from every reference captured.

## STEP 0 — SOURCE GATE (mandatory)

Before anything, obtain at least one of: the **video clip**, the
**voiceover/audio**, or the **transcript/script** — then analyse it and save
`SOURCE-ANALYSIS.json` (video analytics, a word-level transcription JSON, or the
sentence list). Only then write `ASSETS-PROMPT.md` and the preset. A preset
cannot be authored from nothing.

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

## STEP 2 — ASSETS-PROMPT.md (mandatory, from the concept)

The preset build produces the same mandatory prompt file as every skill:
**`ASSETS-PROMPT.md`**, one executable brief per asset, addressed to an AI agent
with **image generation, audio generation and coding**. Six categories:
**images · transparent images (PNG/alpha) · logos · music · sound effects ·
Code components** (glass cards, animated type, diagrams, UI mockups, shaders —
delivered as a kit folder: `index.html`, `styles.css`, `README.md`, `assets/`,
zipped). **This file IS the prompt** — write it as a self-contained instruction handed straight to the agent, ending with the deliverable tree (ONE master zip containing MULTIPLE zips inside) and acceptance checks. A worked example: `EXAMPLE-ASSETS-PROMPT.md`. **Voiceover and ALL video clips are excluded** — the user supplies A-roll (voice/footage/transcription) at the start, and any B-roll is requested **separately**, never listed in this prompt file. (The agent generates images, audio and code only — not video.)
Full format: `ASSET-REQUEST-GUIDE.md`.

## 1. Accept the input
| Input | What you can measure |
|---|---|
| **Contact-sheet PDF** (frames + timestamps) | palette (sampled), type, composition, beat map, pacing (approximate) |
| **Video file** | everything above + true cut times, ASL, motion, audio |
| **Link only** | script/structure from the transcript; no pixels — say so |

State plainly which of the three you got.

## 2. Extraction procedure (frame-level)
1. **Render** the PDF pages to images (one page = a grid of frames, in time
   order). Read each frame: what is on screen, any text verbatim, the layout.
2. **Build the beat map** — a table of `timecode -> beat -> what is on screen`.
   The timestamps on the sheet give the order; the frames give the content.
3. **Sample the palette programmatically** — quantise the frames and take the
   dominant colours as hex. Never eyeball a palette you can measure:
   `Image.open(p).quantize(colors=6).convert('RGB')` → most-common → hex.
   Record 5–6 colours: base, mid, light, ink, accent.
4. **Read the type system** — family (sans/serif/script), weight, the size
   hierarchy (which line is largest), tracking, case, and where text sits.
5. **Read the motion grammar** — how elements enter (rise/fade/scale/blur), the
   transition vocabulary (hard cut / dissolve / wipe / whip), and whether the
   camera moves. From frames only, mark these as *inferred*.
6. **Read the pacing** — how many beats per second, where it speeds up, where it
   breathes. From a video file, compute ASL; from frames, approximate.
7. **Name the signature devices** — the 3–6 moves that make it feel like itself.

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

**For this skill:** every preset applies the advanced toolset the concept needs — keyframing, motion tracking, chroma key, masking, colour grade, audio mixing and the AI features.

### Sentence-level narration — the Sentence Law (mandatory)
Every **sentence** of narration gets its own visual event, bound to that
sentence's stressed word.
- One sentence -> one visual beat (a cutaway, a reveal, a label, a count, a camera move).
- Land the visual on the sentence's **stressed word** (±100 ms), not the sentence start.
- If a sentence has no visual, either give it one or cut the sentence.
- If a visual has no sentence, it belongs to a different beat.
- The camera move (READ / EMPHASIZE / REVEAL) is itself a sentence-level event, bound to a word or phrase.


## MANDATORY FEATURE USE-CASES (the modern standard)

Every preset build applies the mandatory feature set carried by the pack skills:
**★ zoom in (anchor zoom) · ★ zoom out (reveal) · ★ motion tracing / follow
camera · ★ keyframe everything · ★ easing curves (bezier) · ★ kinetic text /
word-pop · ★ count-up numbers · ★ readability zoom · ★ micro-interactions · ★
screen transitions · ★ cursor physics · ★ cut-on-beat · ★ a sound for every cut ·
★ correct then grade** — plus speed ramps, motion blur, parallax, mask reveals,
freeze frames, callouts, PiP, screen replacement and seamless loops where the
concept needs them. The preset's style governs HOW they look, never WHETHER they
are used.

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
Choose ONE named caption style (Apple-Clean / Vox-Highlighter / Sticker-Pop / Outline-Alpha / Karaoke-Word) and declare it in CONCEPT.md.

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

## WHICH LANE IS THE A-ROLL? (function, not source)

A-roll = whatever carries the meaning; B-roll = whatever supports it. In a
graphics-led piece the motion graphics ARE the A-roll and the footage becomes
B-roll — the hybrid inversion.

## 2b. A preset is a FULL skill — same depth, locked to one style

A preset is **not a separate, thinner document**. It is the same skill as every
other in this pack — the same sections, the same depth, the same laws — with the
look, motion grammar and pacing **pre-decided from the captured reference**.

A complete preset carries ALL of these, at the same depth as the pack skills:
- frontmatter + scope + provenance (source, date, measured vs inferred)
- the mandatory **ASSETS-PROMPT.md** block with its five categories and prompts
- intake · structure & pacing (the captured beat map) · the captured palette
  (as an explicit override) · the edit · audio
- industry benchmarks · a worked example · common mistakes
- the **full Visual Narration Layer spec** · signature techniques
- the **modern editing toolkit** (technique catalogue, terminal toolchain,
  tested FFmpeg recipes, production loop, premium rules)
- the **platform & delivery standards** · QA · hard limits

If a preset is a few kilobytes, it is incomplete — rebuild it from a pack skill
as the base, replacing only the style-specific sections.

## 3. The preset file format (copy this)
```markdown
---
name: preset-<slug>
description: "<one line: what this style is and when to use it>"
---
# Preset <NNN> — <name>

**Source:** <what it was captured from, and how (PDF / video / link)>
**Captured:** <date>  ·  **Confidence:** <measured / inferred>

## The look (explicit override of the Apple Standard)
- Palette (sampled): base `<hex>` · mid `<hex>` · light `<hex>` · ink `<hex>` ·
  accent `<hex>`
- Type: <family, weights, hierarchy, tracking, case>
- Composition: <framing, placements, whitespace>

## Motion grammar
<entrances, transitions, camera, easing — marked measured/inferred>

## Pacing & structure
| Time | Beat | On screen |

## Signature devices
1. …

## Build recipe (how to reproduce it)
1. …

## Do-not-copy line
Methods only — never the source's name, logo, copy, or exact marks.
```

## 4. Apply a preset
Open the preset, read the build recipe, and build with it. Where the preset and
the Apple Standard disagree, **the preset wins for this job** (it was requested)
— but keep Apple's type ramp, motion laws, readability, sync and QA unless the
preset explicitly records a different value.

## 5. QA — does it match?
- Palette matches the sampled hexes (compare a probe frame to the reference).
- The beat map timings are reproduced (±10%).
- The signature devices are all present.
- The type hierarchy reads the same at phone size.
- Nothing clanky; every craft law still holds.

## 6. Limits

- **Assets still need prompts.** A preset build also produces the mandatory
  `ASSETS-PROMPT.md` (images, transparent images, logos, music, SFX — one prompt
  each; voice and footage excluded). See `ASSET-REQUEST-GUIDE.md`.
- **Methods, never content.** Never copy the source's name, logo, copy, or marks.
- **Honest confidence.** Sampled colour is measured; motion and audio are
  inferred from frames unless a video file was supplied — say which.
- **Assets still apply.** A preset changes the LOOK, not the asset tier — if the
  style needs footage or a cut-out subject, request it.
- Never reproduce a living person's likeness or a protected mark.
