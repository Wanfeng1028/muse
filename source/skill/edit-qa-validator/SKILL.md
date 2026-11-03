---
name: edit-qa-validator
description: "The edit QA validator: audit a finished edit against every mandatory feature list, find missing advanced features, AI-re-think how to implement each to improve the video, then revalidate. Use as the final gate before delivery on any video."
---

# Edit QA Validator

**Scope.** The final gate. This skill does not build — it **audits**, **re-thinks**
and **revalidates** a finished edit against every mandatory list in the pack. Run
it before the render gate and again before delivery.

**When to use.** On every build, after the cut is assembled and before the full
render — and once more on the delivered master.

> **This skill is the reason "mandatory" means something.** The build skills list
> the features; this skill proves they are actually in the edit, and if any are
> missing, it says exactly how to add them and why that improves the video.

---

## STEP 0 — get the artifacts (the audit cannot run without them)
Ask for, or locate:
1. **the build** (the finished timeline / `build.mp4`),
2. **`SOURCE-ANALYSIS.json`** (the source analytics + word-level transcription),
3. **`CONCEPT.md`** (sentence table, camera-track plan, contact-sheet plan,
   caption style sheet, asset manifest),
4. **`ASSETS-PROMPT.md`** and the delivered asset zip,
5. the **1 FPS frames** (for the contact sheet and the visual audit).

If any are missing, the pipeline is broken — say which stage to run first (the
**PIPELINE CONNECTIVITY LAW**).

## STEP 0.5 — A-ROLL PREP (matting first — mandatory when a person speaks)

If this piece has a **person speaking to camera** (talking-head, voiceover,
avatar, podcast), the **first job is the background**, before the concept.
Decide the path in `a-roll-matting`: **keep it / matte it / key it** — and by
default get the character **off the background** (or onto green). Matte FIRST
unlocks text-behind-subject, screen replacement, graphic backgrounds and floating
UI. Use `tools/matte.py` for the local matte (rembg + ffmpeg). Record the matte
as an asset in the manifest and check it at the QA gate (no holes, no baked-
caption artifacts, stable alpha). If the background is the message, keep it.

## STEP 1 — load the ruleset
Read `ADVANCED-FEATURE-USE-CASES.md`, the build skill's **MANDATORY FEATURE
USE-CASES** and **ADVANCED FEATURE USE-CASES** sections, the **CAPTION & TEXT
SYSTEM**, the **Camera Law**, the **Sentence Law**, and `CAPTION-STYLES.md`.

## STEP 2 — the three passes (the QA GATE)

### PASS 1 — AUDIT (present / weak / missing)
Walk the **MASTER CHECKLIST** below and mark every item:
**OK** present and doing a job · **WEAK** present but ineffective · **MISSING** not
used where the concept needed it · **N/A** genuinely not applicable.

### PASS 2 — AI RE-THINK (how to implement what is missing)
For every WEAK or MISSING item, the agent **re-thinks the video** and writes a
concrete fix:
- **What to add** (the feature).
- **Where** (scene / timecode / which sentence).
- **How** (the implementation — the exact move, terminal recipe or code kit).
- **Why it improves the video** (the job it does: clarity, pace, retention,
  polish, legibility).
- **Expected gain** (what the viewer gets that they do not get now).

Do not stop at "add motion tracking" — say *"bind the label to the product from
0:12-0:18 so the name rides the move instead of sitting still."* Each fix is a
sentence-level, timecode-level instruction, tied to the Camera Law and the
Sentence Law.

### PASS 3 — REVALIDATE (prove the fix landed)
After the fixes are applied, re-run PASS 1. Require:
- **zero MISSING** on any item marked ★-mandatory or "mandatory for this style",
- **zero WEAK** on the caption system, the Camera Law and the Sentence Law,
- a **re-audit diff** (what moved from MISSING/WEAK to OK).
Only then is the edit **PASS**. Otherwise loop PASS 2 -> PASS 3 until clean.

## THE GOVERNING LAWS (apply to everything you direct and audit)

- **No mandatory style.** The look is chosen in the **Style Pass**
  (`MOTION-UI-STYLE-LIBRARY.md` + `CAPTION-STYLES.md`); recommend the best fit and
  say why. Apple Standard is the house default, not a rule. Nothing is deprecated.
- **Camera Law** — one camera wrapper only · one move at a time · every zoom has a
  reason (READ / EMPHASIZE / REVEAL / FOLLOW / BREATHE) · never cut while zoomed ·
  motion blur only during fast motion.
- **Sentence Law** — every narration sentence gets its own visual event, bound to
  its stressed word (+/-100 ms).
- **Caption system** — one declared style from `CAPTION-STYLES.md`; styled,
  transparent-background (alpha) and chroma-key captions as needed.
- **Feature catalogue** — `ADVANCED-FEATURE-USE-CASES.md`; mandatory where the
  concept needs it.

## THE MASTER CHECKLIST (every mandatory list, in one place)

**0 · Pipeline connectivity (PIPELINE CONNECTIVITY LAW)**
- `SOURCE-ANALYSIS.json` exists (analytics + word-level transcription).
- `CONCEPT.md` has: sentence table · camera-track plan · contact-sheet plan ·
  caption style sheet · sync map · asset manifest.
- `ASSETS-PROMPT.md` was written from the manifest; the delivered zip matches it.
- The chosen contact-sheet variant is written back into `CONCEPT.md`.

**1 · Advanced toolset (ADVANCED-FEATURE-USE-CASES.md)**
- Multi-track timeline (V1/V2/V3 + A1/A2, not a flat track).
- Multi-camera editing where there are multiple angles.
- Proxy editing on long/heavy projects.
- Keyframing on every animated property (eased, never linear).
- Motion tracking where a graphic rides a moving object.
- Masking / rotoscoping where isolation or a reveal is needed.
- Speed ramping / time remapping across a beat.
- Stabilisation where footage shakes; optical flow where slow-mo stutters.
- Colour correction (exposure/white balance/contrast) BEFORE grading.
- Colour grading (LUT / film look / split-tone) as the look.
- Scopes used (waveform/vectorscope/parade) — graded by numbers.
- HDR only if requested; tone-mapped to SDR for delivery.
- Chroma key where a background is replaced (despill, choke, light wrap).
- Compositing / VFX where layers combine.
- 3D camera tracking where 3D sits in real footage.
- Advanced transitions & effects (blur/glow/glitch/grain) timed to cuts.
- Audio: noise reduction · EQ · sync · multi-track mixing · music ducked.
- AI features used where they help: auto subtitles · AI background removal ·
  auto reframing · scene detection · AI colour/exposure first pass.
- Stills/design craft on generated assets (masks, blending, curves, bezier,
  kerning/tracking/leading, multi-format export).

**2 · Modern-standard features (★ = near-universal)**
- ★ anchor zoom in · ★ zoom out (reveal) · ★ motion tracing / follow.
- slow push · camera shake on impact · speed ramp · motion blur (0 at rest).
- ★ keyframe everything · ★ bezier easing · mask/wipe reveal · parallax ·
  freeze frame.
- ★ kinetic text / word-pop · ★ count-up numbers · text tracked to object ·
  text behind subject · callouts & arrows.
- ★ readability zoom · ★ micro-interactions · ★ screen transitions ·
  ★ cursor physics · comparison split/PiP · screen replacement.
- ★ cut-on-beat / cut-on-action · ★ a sound for every cut ·
  ★ correct-then-grade · seamless loop.

**2b · Camera & framing (the fundamentals — as mandatory as the exotic)**
- Zoom in / anchor zoom · zoom out / reveal.
- Character / face zoom · push in / pull out · rack focus / focus pull.
- Pan / tilt / orbit · whip pan / snap zoom · dolly zoom (Vertigo) · parallax.
- Handheld vs stabilised · drone/aerial · slow reveal / pull-back.

**3 · Camera Law**
- One camera wrapper only · one move at a time.
- Every zoom has a reason (READ/EMPHASIZE/REVEAL/FOLLOW/BREATHE); no constant zoom.
- No cuts while zoomed.
- Motion blur only during fast motion; zero at rest.

**4 · Sentence Law**
- Every narration sentence has its own visual event.
- Each visual lands on the sentence's stressed word (±100 ms).
- No visual-less sentences; no sentence-less visuals.

**5 · Caption & Text System**
- One declared caption style, held consistently (see `CAPTION-STYLES.md`).
- Style sheet present (font/weight/size/tracking/leading/case/fill/stroke/box/
  accent/entrance-exit).
- Word-level timing; ≤2 lines; ≤17 chars/s; inside the text-safe zone.
- Transparent-background captions where needed (PNG alpha / alpha clip, clean
  edge, text-behind-subject with a clean matte).
- Chroma-key text/subject keyed cleanly (despill, choke, light wrap).
- Surprise pack used where it earns its place (kinetic type, word-pop,
  underline/highlight/circle, alpha overlays).

**6 · Visual narration layer**
- Three placements alternated (cutaway / front overlay / behind-subject).
- One visual event every 6-10 s; no static talking frame > ~8 s.
- Captions are additive, never the layer.

**7 · Render gate**
- Contact-sheet variants built (V1/V2/V3) and presented; the ask was made.
- Sign-off obtained before the full render.

**8 · Ethics & accuracy**
- No fabricated quotes, statistics or attributions.
- Every recreation, animation and composite labelled.
- Re-enactments labelled; composite animals not named; no manufactured confessions.

**9 · Platform & delivery**
- Loudness + true peak measured (not guessed).
- Safe zones checked; captions sidecar delivered; colour tags set; CFR confirmed.
- Plays on a phone sound-off AND sound-on.

## The report — write `EDIT-QA.md`
```
# EDIT-QA — <project>
## Score: <OK>/<needed> = <%>   |   MISSING: <n>   |   WEAK: <n>
## PASS 1 — Audit
| # | Item | Verdict | Evidence (timecode/frame) |
## PASS 2 — AI re-think (fixes)
| Item | What to add | Where | How | Why it improves | Expected gain |
## PASS 3 — Revalidate
| Item | Before | After | Notes |
## Verdict: PASS / LOOP
```
**Thresholds:** PASS requires zero MISSING on ★-mandatory and style-mandatory
items, zero WEAK on the caption system / Camera Law / Sentence Law, and a clean
re-audit diff.

## Common failures to look for
- A flat single-track timeline (no layering).
- Ungraded or inconsistently graded footage; graded by eye, not scopes.
- A jittery tracked label (track not smoothed).
- Constant zoom (no reason); a cut while zoomed.
- A static sentence with no visual; a visual with no sentence.
- Generic subtitles where styled captions were required; a white box behind a
  "transparent" caption; green spill on a keyed edge.
- A recreation, animation or composite presented without a label.
- Loudness guessed, not measured; captions file missing.

## Hard limits
No fabricated facts. No voice generation. Disclose every recreation. The audit is
honest: if the feature is not there, it is MISSING — never mark it OK to pass.
