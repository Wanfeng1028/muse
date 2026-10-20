# Working on footage: talking heads, captions, b-roll, demos, long to short

Remotion API truth: `~/.claude/skills/remotion-captions/` (transcribe, display, import SRT),
`~/.claude/skills/remotion-markup/video-editing.md`, `embedding-videos.md`, `silence-detection.md`, `cropping.md`,
`~/.claude/skills/remotion-render/transparent-videos.md`. Use `<Video>` from `@remotion/media` (it falls back to
`OffthreadVideo` itself); older advice to always use `OffthreadVideo` predates it.

Contents
1. Intake questions
2. Ingest and admission
3. Transcription
4. Silence and filler cuts
5. Captions
6. Overlay cards on a talking head
7. B-roll and cutaways
8. Punch-ins and reframing
9. Screen and product demos
10. Long to short
11. Safe zones and platform specs
12. Audio on footage
13. QA for footage

---

## 1. Intake questions

Ask once, 2 to 5 questions per round, each with a recommended default; skip them entirely when the user says "decide
for me" and state the picks in one sentence.

- Mode: captions only, overlay cards, b-roll, silence and filler cut, long to short, screen demo.
- Output ratio, recommended from the source: w/h ≥ 1.5 → 16:9; ≤ 0.7 → 9:16; between → 4:5 (1080×1350).
- Layout of video and graphics: split, stack, picture-in-picture, overlay (§6).
- Tone or a named reference style.
- Density: cards auto / fewer (×0.6) / more (×1.5) / an exact number; b-roll medium or heavy (for ~33 s: medium 3 clips,
  heavy 4 to 5; pick heavy, cutting is easier than adding).
- Caption identity: shortlist 2 to 3 and recommend one; unsure → a quiet lower-third rail.
- Spoken language (it decides the transcription model).
- Platforms, and whether it plays muted.
- Brand assets and a facts file.
- Demos: URL, login, viewport, scripted or interactive take.

## 2. Ingest and admission

- Probe with ffprobe: size, `r_frame_rate` (evaluate the fraction), duration. Extract audio once (16 kHz mono WAV for
  transcription). Look at a 1 fps contact sheet (`scripts/sheets.sh contact`) and frames at 20/50/80%.
- Refuse or split when: the clip contains hard cuts or cutaways (trim to the largest single-subject segment or split per
  shot; cut detection: frame-diff spikes, as in `qa_video.py`); the source already has burned-in captions (don't add a
  second system); under 3 s, no speech or no clear face; the transcript is gibberish after one retry with a bigger model;
  the subject fills over 70% of the frame (no clean zone for side text, use a lower third).
- Probe for letterbox bars (keep text inside the content rect + 10 to 20 px) and baked graphics (logos, bugs, watermarks:
  map their boxes and keep text out).
- Normalise when needed: H.264 yuv420p, keyframe every second (`-g <fps> -keyint_min <fps>`) for smooth scrubbing, even
  dimensions. Match the composition fps to the footage fps: if they differ, change the composition (generated motion
  retimes for free). Never convert 25 → 30 by duplicating frames; the person stutters next to smooth graphics. Compare
  `r_frame_rate` with `avg_frame_rate` for variable frame rate; near-zero differences every few frames mean baked-in
  duplicates (`mpdecimate`). Host video must match the voice within one frame or lip sync drifts.
- Grade per segment while extracting, never after concatenation. Think slope (highlights), offset (shadows), power
  (midtones); change one thing, look at a frame, repeat.
- Green screen on CPU: a green-dominance key plus `despill=green:mix=0.18` and a 1 px feather (mix 0.5 turns white shirts
  pink). Alpha WebM in Remotion needs a component that supports transparency (check `transparent-videos.md`), or the
  transparent area renders black. VP9 alpha hides in side data: `yuv420p` in ffprobe doesn't mean no alpha.
- Face safe zone from a detector, never by eye: sample face boxes once per second, take the union, extend 60% upward for
  hair and add 30 px all round. No text, card or caption enters it.
- Clamp every graphic's end and the composition duration to the media duration; transcripts often put the last word past
  the end of the file.

## 3. Transcription

- Official: `@remotion/whisper-webgpu` `transcribe()` + `toCaptions()` → `Caption[]` (needs a compatible GPU; English
  `small.en`; other languages need a multilingual model and an explicit `language`; no auto-detect). See
  `remotion-captions/transcribe-captions.md`.
- Alternatives: whisper.cpp, WhisperX (`uvx`, better alignment), Parakeet on Apple Silicon (faster, lower error, 25
  European languages including Spanish), cloud `whisper-1` / Groq `whisper-large-v3` with word timestamps. For TTS
  voiceovers, use the TTS provider's alignment instead of transcribing.
- `.en` models silently translate other languages into English. Always pass the language.
- Existing `.srt`: `parseSrt()` (phrase-level only, no per-word effects).
- Read the transcript before using it: over 20% music symbols or nonsense → retry one model up; strip non-word tokens;
  drop words in near-silent audio (Whisper invents "Thank you." over silence); flag words shorter than 50 ms.
- Fix names, numbers and homophones by editing `text` only; never move timestamps. Never merge two spoken words into one
  timed entry. Log creative substitutions ("15%" for "fifteen percent").
- Mid-clip silences over 3 s: ask (linger, title card, or cut).

## 4. Silence and filler cuts

- Work from the transcript; look at frames only at decision points. Pack it into phrase lines (break on ≥ 0.5 s silence
  or a speaker change), each prefixed `[start-end]`: word-level precision at a tenth of the tokens of raw JSON. Cache
  transcripts per source file.
- Agree the edit strategy first: 4 to 8 plain sentences (shape, take choices, cut direction, graphics plan, grade,
  caption style, estimated length), then wait for confirmation. Show a dry-run cut report before applying it.
- Adaptive silence detection: pass 1 `loudnorm=print_format=json` → `input_thresh`; pass 2
  `silencedetect=noise=<input_thresh>dB:d=0.5`. Fixed −30 dB thresholds break across microphones.
- **Where it is safe to cut**: gaps ≥ 400 ms are clean; 150 to 400 ms only after looking at the frame; under 150 ms is
  mid-phrase, never. Never inside a word. Pad every cut edge 30 to 200 ms (ASR drifts 50 to 100 ms; a shipped edit used
  50 ms before the first kept word and 80 ms after the last; tighter for montage, looser for documentary).
- Speaker handoffs need 400 to 600 ms of air. Extend past laughs and punchlines: the reaction is the beat.
- **Order is fixed**: cut fillers, false starts and long pauses first, then compute word timestamps, then everything
  else. Editing audio after timestamps shifts every beat.
- Compress silences ≥ 0.7 s to ~0.35 s using the quietest window of real room tone, never digital silence. Leave 0.25 s at
  the head and 0.5 s at the tail. Apply the same edit list to picture and audio so they stay the same length.
- With a script, the script is ground truth: cut only ASR insertions that aren't in it (filler, repeats). Never cut a word
  ASR merely misheard. Without one, cut only exact matches against a conservative filler list; report short repeats.
- Multi-take assembly goes by beat, not by source order. Edit rows: `{source, start, end, beat, quote, reason}`. Archetypes:
  launch = HOOK, PROBLEM, SOLUTION, BENEFIT, EXAMPLE, CTA; tutorial = INTRO, SETUP, STEPS, GOTCHAS, RECAP.
- Transcript-driven cuts: remove filler words (compare lowercase bare tokens), stutters, self-corrections, repeated
  "you know"; merge overlapping removals; drop kept pieces shorter than 0.2 s. Honour deliberate pauses of 1.5 s+.
- Click-free splices: a 30 ms fade at every splice (≈1 frame at 30 fps: a `volume` interpolate over the segment's first
  and last frame, or pre-cut audio with ffmpeg `afade` played as one `<Audio>` under muted video segments).
- Intermediate audio pieces as WAV, never AAC: AAC priming adds 25 to 35 ms of silence per piece that concat bakes in.
- In Remotion, prefer no new file: each kept segment is its own `<Video>` node with `trimBefore`, `durationInFrames`,
  `premountFor={fps}`, inside a `<Series>` so later clips reflow. One JSX node per clip (no `.map`) so Studio can edit each
  cut. `trimBefore = Math.floor(start * fps)`, `durationInFrames = Math.ceil(end * fps) − trimBefore`.
- Re-map caption times after cuts: `t_new = t_old − removedBefore(t_old)`; drop words inside removed spans.
- Hide jump cuts with a punch-in (§8).

## 5. Captions

**Model.** Every phrase is `drop` (filler, not shown), `rail` (the verbatim lower third, in front, carrying most of the
text) or `embed` (a promoted peak word, possibly composited behind the subject). Rail first for talking heads and
explainers. Embeds are scarce: at most one per sentence, never two at once, ≥ 0.6 s apart, one apex per clip. Captions
are an overlay, not a reserved band: keep the layout centred on the true centre; only keep small critical text out of the
bottom ~80 px centre. Display 70 to 85% of the transcript; drop restatements; no `[laughs]` tags (that's accessibility
captioning, a separate SRT/VTT deliverable).

**Grouping** (word → page).
- Hard break at pauses ≥ 500 ms and sentence ends; break at ≥ 250 ms only after punctuation; also on discourse resets
  ("but", "so"). Cap at 6 words, 2.5 s and 42 characters per line; at most 2 lines.
- Words per page by energy: 2 to 3 high, 3 to 5 conversational, 4 to 6 calm; pop style 1 to 3; karaoke 3 to 7. Vary sizes;
  never a fixed word count.
- Short-form preset that shipped: about 2 words per cue, uppercase, closing on punctuation or a ≥ 0.3 s pause, growing to 3
  words rather than flashing a cue under 0.35 s; rendered last, above every overlay. Documentary preset: 4 to 7 words,
  sentence case, larger, 60 to 80 px from the bottom at 1080p. Cue times are output-timeline offsets
  (`word.start − segment.start + segment.offset`).
- Counterweight to "animate every word": follow-along captions can stay plain (whole phrases, no animation) with at most
  ~3 keyword pops per film.
- Flag lines over 38 characters, more than two lines, six words in under 0.6 s, or any cue more than ±100 ms off its word.
  Fix captions from the clean picture and burn once; never burn on top of old captions.
- At least 2 words per page (one-word exceptions: an interjection or the climax line).
- Timing: in = first word − 0.08 s; out = min(next in − 0.05 s, last word + 0.6 s). The page window must envelop its words.
- Remotion: `createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds, breakOnSilenceAfterMilliseconds: 500})`
  (≈1200 to 1500 ms combine for 3 to 5 word pages); `pageBreakAfter` forces a break.

**Readability.**
- Minimum on screen: 0.7 s for pop captions, 0.5 s for a verbatim rail. At most 17 characters per second.
- No 1 to 3 frame gaps between pages (strobing). A word highlights on its start frame, never before; every word within
  80 ms of its transcript time.
- Don't start a caption at t=0; let the last one exit before the video ends.

**Type and size.**
- Rail ≈ 4.5% of frame height; body cap height 3.5 to 5% of height (9:16 body 65 to 95 px, hook 130 to 170 px; 16:9 body
  40 to 55 px, emphasis 70 to 100 px). Express sizes as a fraction of height.
- Measure text height in rendered pixels, not code: `fontSize × every ancestor scale × cos(rotateY)`. A `scale(0.72)` group
  turns 26 px into 18.7 px. At 1080p, narrative captions ≥ 56 px, secondary text ≥ 32 px; the closing URL or CTA is never
  the smallest line. Text is either texture (blurred or darkened so nobody tries to read it) or readable; nothing between.
- One family, at most two weights; hierarchy by weight and size. One saturated accent plus neutrals.
- No italics for emphasis. Pills and boxes only for social or playful identities, never for cinematic ones.
- Emphasis budget: ~70% plain, 20% light lift (colour or weight, not both), 8% full emphasis (1.3 to 1.6×), 2% climax
  (held ~1.5 s). Flag brand names, numbers, CTA words and emotional keywords. A rhythm break every ~30 s.
- Fit text against the longest wrapped line with headroom for the emphasis scale (`measuring-text.md`).

**Motion.**
- Stagger is the main expressive axis: 40 ms urgent, 80 ms conversational, 150 ms documentary, 250 ms+ ceremonial.
- Rail: 150 to 250 ms fade-up in and down out; active-word pop ≤ 1.1×. Exits ≈ 75% of entries.
- Animate transform, opacity and clip only; never letter-spacing, font size, weight or blur on words (reflow jumps).
- Never fade both the container and the words (opacity multiplies).
- Each caption absolutely positioned in its plane; centre with a full-width container, not `left: 50%; translate(-50%)`.

**Position and legibility.**
- Landscape: lower third, baseline 80 to 120 px above the bottom. Portrait: lower middle, about 600 to 700 px above the
  bottom of 1920, clear of platform UI. Inside title-safe and inside any bars.
- Never cover the face (eye box + 20 px is sacred).
- Contrast by the caption area's luminance (0 to 255): below 60 light text as is; 60 to 180 add a glyph shadow or narrow
  scrim; above 180 opaque text plus a scrim. Prefer, in order: a 2 to 3 px dark stroke with soft shadow, a narrow 30 to 40%
  scrim sized to the text, a local 10 to 15% plate dim, a pill (last resort). Never grade, vignette or texture the
  speaker's footage.
- Letterbox bars on a 9:16 version of a 16:9 source are caption real estate.

**Text behind the subject** (embedded words): base `<Video>` → word layer → person matte on top. Generate the matte
outside Remotion (rembg human segmentation or BiRefNet portrait, CPU); play it as a PNG sequence first (deterministic)
and verify alpha video before relying on it. Rules: hero 30 to 55% occluded, 0.22 to 0.34 × frame height, across the upper
body, never covering the face (≥ 30% of the face visible in every 0.3 s window), matte fps equal to composition fps, hold
the climax ≥ 1 s.

## 6. Overlay cards on a talking head

Workflow: probe and extract audio → transcribe → correct → storyboard (cards with id, intent, start, end, zone, content
hints) → ask ratio, layout, style, count → build cards → stills at each card → render → report.

- Card count: base pace by duration (under 1 min 6 to 8 s per card; 1 to 3 min 8 to 12; 3 to 10 min 12 to 20; 10 to 30
  min 20 to 35; over 30 min 30 to 60) × density (dense data 0.7, mixed 1.0, one reflective story 1.5); floor of 5.
- A card held over 15 s needs a multi-step build; a static one-liner is boring past 8 s.
- Cards come from what is said; 2 to 3 repeatable motion patterns per film.
- Layouts at 1920×1080 / 1080×1920:
  - `split`: video on the right half / bottom half; cards in the side panel (right 42% / bottom 40%).
  - `stack`: video top 52% / top 44%; cards in a bottom band.
  - `pip`: cards full frame, video in a rounded inset (e.g. 400×300 at bottom right) with ring and shadow.
  - `overlay`: video full bleed; a glass card floats.
  - 4:5: keep portrait x and width, scale y and height by 1350/1920 ≈ 0.703.
- Cards over visible video have transparent roots; only full-frame or side-panel cards paint backgrounds.
- Timing: enter ~0.4 s (out ease), exit ~0.35 s (in ease) ending on the card's end; layout moves of the video wrapper 0.5
  to 0.7 s in the gaps between cards. Quantise to frames.
- Portrait sizes ≈ landscape × 1.3 (titles 88 to 132 px, body 30 to 40 px, big stats 64 to 88 px).
- Remotion: one `<Sequence premountFor={fps}>` per card; animate a wrapper around `<Video>`, never the video element's
  own size; `cropLeft/Right/Top/Bottom` for editable crops. Source audio stays on the base video.

## 7. B-roll and cutaways

- **Beat density**: 3 to 8 visual beats per 30 to 60 s; zero is valid. Score candidates on structure, information and
  memorability (0 to 2 each) minus visual risk (0 to −2); below 3, keep the shot clean. Over budget, drop first the beats
  that only move something, then repeats of the previous beat's structure, then beats covering face, captions or product,
  then beats carrying less than the speaker's own delivery.
- Enter 2 to 5 frames before the keyword (or on it), never late. A pivot sentence ("but this time…") belongs to the next
  shot: clear the stage, then open the new idea on an empty frame.
- **Speaker mode per beat**: full-screen visual over the voice for hooks, chapter turns, conclusions and 1 to 3 s punches;
  picture-in-picture for longer tutorials; split when product and speaker matter equally; clean shot for strong emotion.
  PiP under 1.5 s reads as a flash; over 3 s with the speaker fully gone reads as a stock collage. PiP size 22 to 30% of
  frame width vertical, 16 to 24% horizontal; smaller than that, use split or full screen.
- **Default when b-roll plays over talk**: shrink the host to a live corner chip (never a still), centre in the bottom
  third, bottom edge at action-safe; bottom-left on vertical (the right edge belongs to the platform rail). The chip never
  drifts or breathes. Establish the host full or half-body for the first sentence (up to 8 s) before shrinking. Never two
  consecutive shots without the person (it becomes a narrated slideshow); a full exit lasts 3 to 6 s, once.
- Handoffs never overlap: the old panel exits, then the person moves, then the new panel enters (~0.15 s after the person,
  from the opposite side). 2 to 4 layout changes per minute, each triggered by a new argument, a chart, a before/after or
  a conclusion.
- Rotate layouts: track each shot's person form (half body, chip left/right, split cell, cut-out, absent) and media
  container (full bleed, framed, split, multi-image, long page). Three consecutive shots with the same pair fails; no card
  style in more than a third of the film; the same b-roll file never in adjacent shots. Every shot passing alone doesn't
  mean the film passes.
- On-screen budget: at most 3 subject groups at once (dimmed leftovers count), one empty quadrant, one hero per frame,
  on-screen text a ≤ 12-character distillation (never a copy of the caption), and anything not yet spoken fully invisible.
- Full-frame cutaways of 3 to 10 s with at least 2 s of face between them, or transparent panels in the empty space next
  to the speaker.
- Plan line by line from the word-timed transcript; tag each graphic `full cutaway`, `face stays` or `side panel`; get
  approval before rendering; graphics land on the spoken word.
- Many clips for an editor: render transparent overlays (ProRes 4444 or WebM alpha; `remotion-render/transparent-videos.md`)
  and deliver them on one review page.
- Never trust text inside AI-generated b-roll; overlay real text, with a ~55% dark tint under it on busy footage.
- Real product only: capture real UI; label recreations.

## 8. Punch-ins and reframing

- Camera on footage = one transform on a wrapper with keys [frame, zoom, x, y], `transformOrigin` on the face, zoom in
  perceptual scale; never zoom in and straight back out.
- Working defaults (validate by eye): punch to 1.08 to 1.15× on emphasis or to hide a jump cut after a removal; alternate
  punched and unpunched across consecutive cuts; make sure the source has the resolution (1.15× of 1080p goes soft; a 4K
  source has headroom).
- Cut at peak velocity; keep the sign of the zoom across a cut.
- Never put `will-change` on an element the camera scales.
- Reframing 16:9 → 9:16: crop camera footage framed on the face (non-destructively with `crop*` props or a translated
  wrapper), never designed graphics, which are re-laid out instead. Two speakers: stack them, or switch framing on speaker
  turns.

## 9. Screen and product demos

**Record or rebuild.** Recording (Playwright) is fast and truthful; rebuilding the UI in code gives razor-sharp, fully
animatable elements (`design.md` §7). Anonymise with one fictional company everywhere.

**Playwright capture.**
- `recordVideo.size` = viewport (1920×1080 typical; 390×844 phone). Laptop look: viewport 1920·s × 1080·s with
  `deviceScaleFactor: 1/s` (s = 0.75) still records 1080p.
- `slowMo` 50 ms (75 to 100 ms for complex UIs); ~500 ms between fields, 2 to 3 s on results; `waitForLoadState('networkidle')`.
- Fresh context per take; log in once and reuse `storageState`; dismiss or hide cookie banners.
- Everything injected into the DOM is recorded; injected scripts reset on navigation.
- Visible typing ~100 ms per character; smooth scroll in 200 px steps every 300 ms.
- `--hide-scrollbars`, fixed `colorScheme`, `locale`, `timezoneId`.
- Convert WebM to MP4 (`libx264 -crf 20 -movflags faststart`) and report duration and frame count.

**Fitting to narration.** speed = source seconds / scene seconds. Remotion `playbackRate` is constant per element; ramps
or speeds beyond 0.25 to 4× are pre-processed with ffmpeg. Screen recordings usually drop their audio for VO and SFX.

**Cursor.**
- Record without a visible cursor, log click coordinates and times, and replay them as a synthetic cursor layer driven by
  a keyframe array `[frame, x, y, click]`.
- Size ≈ 7% of frame width full frame (≈134 px at 1920), 4.6 to 5.5% inside a device mock. One arrow design per film.
- Enters from off-screen in one decelerating glide (0.4 to 0.9 s); never fades in. The tip is the hotspot and lands on
  the target's centre.
- Click: scale 0.84 over 0.1 s, back over 0.22 s, pivoting at the tip; the target reacts at the same time (0.94).
- Every click causes the next beat in the same frame. Between its beats the cursor drifts aside; no idle wobble.
- It exits physically (off the nearest edge with an ease-in) or carries into the next scene's click point at matched
  velocity.
- Zoom to the click target for small UI (scale + counter-translate, `motion.md` §11), then back out on the next beat.

**Zooms on screen recordings.**
- Levels: 1.0 full page, 1.1 to 1.3 a section, 1.8 to 2.5 one chart or a few columns, 2.8 to 3.5 one metric or button.
  Source resolution caps it (~2.5× for 720p, ~3.5× for 1080p); above 2.5× keep the focus point within 5 to 95% of the frame.
- Timing: arrive ~0.5 s before the narrator names the element and hold 2 to 3 s; far moves 1 to 1.5 s; adjacent elements
  pan at the same zoom over 3 to 5 s; between two zoomed targets drop only to ~1.5×; targets closer than ~1.5 s chain into
  one pan instead of zooming out and back. Start and end at 1.0. Ease `Easing.bezier(0.16, 1, 0.3, 1)`.
- Build the camera as translate + scale with `transformOrigin: '0 0'` (`tx = W/2 − zoom·x`, `ty = H/2 − zoom·y`), clamping
  the visible rectangle inside the media so no empty stage shows. Animating `transform-origin` with scale bends the path.
- Cursor-follow smoothing is stateful and Remotion renders frames out of order: precompute the camera path per frame in a
  Node script into JSON and read it with `useCurrentFrame()`.
- Auto-zoom candidates: cursor dwell of 0.45 to 2.6 s within 2% movement, spaced ≥ 1.8 s apart.
- Long commands on small screens: drive the camera from typing progress (characters × 0.6 · font size for monospace), zoom
  2.6 to 2.8×, type 12 to 20 characters/s, caret solid while typing, hold 0.6 to 0.9 s, pull back over 0.8 s. Typing SFX per
  word (2 to 3 hits), with varied volume and pitch, never per character.
- Blurry zoomed UI is rasterisation: Chromium rasterises transformed layers at layout size. Capture at
  `deviceScaleFactor: 2` (4× for hero cutouts), or zoom with CSS `zoom` rather than `transform: scale`.
- Verify every zoom target with stills at its exact time ("the narrator says X now; is X prominent?").

**Pages and captures.**
- Capture at 1920×1080 with `deviceScaleFactor: 2`; wait for `document.fonts.ready` plus 600 ms (live data 1.5 to 2 s more).
  Take per-element cutouts, an empty backplate for fly-ins, and a `layout.json` of each element's box. Freeze or redact
  customer, personal and secret data before capture.
- Fly-ins land in real layout slots; hovering elements read fake. Dense shots stay front-on; tilt is decided per shot.
- A web page is never a static screenshot as the subject: scroll at ~10% of page height per second, slowing to a stop for
  1 to 2 s on the key row, or tour, zoom or wipe it. Annotations on scrolling content move with the content.

## 10. Long to short

- One topic per short: split rather than compress. Find self-contained claims with a hook in the first 2 s
  (transcript-first), then cut tighter and faster than the original.
- Keep quick real-face shots from the original; regenerate VO in pieces if it's voiced.
- 9:16 talking head: speaker at the bottom, one graphic at the top, captions; nothing else.
- Landscape speaker on a portrait canvas: a video band at the top (stack) or full-bleed overlay; the empty bands hold
  captions and graphics.
- Designed graphics are re-laid out per format from the same timeline, never cropped.

## 11. Safe zones and platform specs

- Title-safe 80% of the frame (10% inset); action-safe 90%. Social full-bleed can use 5 to 6% margins plus the platform
  UI zones below.
- Product films: margins of about 110 px (16:9) and 80 px (9:16); every title on one line; essential text inside the
  centre 1080×1080 of a 9:16 frame.
- Vertical platform UI (TikTok, Reels, Shorts): working assumption, not a sourced spec: keep critical content out of the
  right ~15%, the bottom ~20 to 25% and the top ~10 to 12% of 1080×1920. Verify against current platform guides before
  final placement.
- Platform caps (duration, size) change often: check current limits at delivery time (`delivery.md` §4).

## 12. Audio on footage

- Duck music under speech by about 8 to 12 dB with a ~0.15 s attack and ~0.4 s release, merging gaps under 0.6 s
  (sound-design skill, `references/mix.md`). Baked alternative: `sidechaincompress=threshold=0.03:ratio=8:attack=200:release=400`.
- Loudness: social −14 LUFS, true peak −1 to −1.5 dBTP; podcasts −16 LUFS.
- Repair voice problems with the table in the sound-design skill (`references/mix.md`, diagnosing a voice).

## 13. QA for footage

- Preview frames at every caption page and card window before any full render.
- Checks: washout (light text on a bright region), text on text (scene text or two pages), reading order matches spoken
  order, nothing on the face, nothing in platform UI zones, pages invisible right after their end, words within 80 ms.
- Self-critique: does the caption or the subject read first; pills where the identity is cinematic; lower third on a
  close-up; more than two weights; italic emphasis; more than one accent; blur or letter-spacing animation; everything
  emphasised; 30 s without a rhythm break; filler displayed; a caption crossing a breath.
- A fresh-eyes sub-agent gets only the preview sheet and the checklist and answers PASS or FIX per frame.
- Report: work dir, transcription model, card and caption counts with a one-line rationale, caveats.
