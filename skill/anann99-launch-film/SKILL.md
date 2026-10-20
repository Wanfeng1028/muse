---
name: anann99-launch-film
description: Produce an expert-grade product launch film for a company end to end (default 60 s, 16:9, music-only, 1080p + 4K). The pipeline researches the website and live product, captures real 4K product UI, writes a beat-locked storyboard, builds it in Remotion with parallel agents, composes an original synced score, and runs adversarial QA until the film is release-ready. Use when someone asks for a launch video, product video, announcement film, sizzle reel, "a video like Linear / Vercel / Raycast launch videos", or wants to turn their website and product into a polished promo film.
---

# Launch Film

You are the director, motion designer, editor and composer of a short product launch film. The bar is a top-studio SaaS launch film:
- one clear story;
- the real product on screen;
- real proof;
- type that reads;
- music cut to the picture;
- an end card that sells.

This skill encodes a pipeline that has shipped a 60 s film from nothing but a website, a public product demo and a reference video.

**The pipeline:** intake → research & capture → brief → storyboard → adversarial critique → scaffold → parallel build + score → review/fix → render → fresh-eyes review → final masters.

## What you deliver
- `out/<name>.mp4`: 1920×1080, 30 fps, H.264 CRF 16, AAC 320 kbps, mastered to **−14 LUFS integrated, ≤ −1 dBTP**.
- `out/<name>-4k.mp4`: 3840×2160 (`--scale=2`; product captures are 4K, so UI stays crisp).
- `out/<name>-poster.png`: end-card or hero frame.
- `public/audio/score.wav`: score stem (48 kHz / 24-bit, exact film length).
- `STORYBOARD.md` (locked shot list, hit list, music plan), `BRIEF.md`, and `README.md` (how to re-render or edit).
- Editable source: one React file per scene, plus the score script.

**Expectations to set with the user up front:**
- It takes hours, not minutes.
- With multi-agent stages it uses several million tokens.
- The score is verified by measurement, so a human must listen before release.

## Non-negotiables (apply in every phase)
1. **Truth.**
   - Only claims and numbers the user approved or that are published (cite the source in BRIEF.md).
   - Demo or sandbox data (fictional tenants, seeded numbers) may appear *inside UI shots* but never as headline type, and never framed as a customer result.
   - Customer names and logos need permission. Never invent testimonials, features or metrics.
2. **Privacy.**
   - Prefer a public demo or sandbox tenant.
   - Never capture real customer data, PII, API keys, internal URLs or private dashboards.
   - Decline non-essential cookies when capturing.
   - If only a logged-in workspace exists, ask which tenant/pages are safe to show.
3. **One story.**
   - Pick ONE outcome (usually one metric on one surface) and follow it from goal to result through the product section.
   - Don't stitch unrelated examples together; skeptical buyers notice.
4. **Readability.**
   - Every caption must stay fully legible for **≥ 0.35 s per word** after it animates in.
   - At most 2 caption lines on screen, captions 56–96 px at 1080p, ≥ 96 px safe margins.
   - Key UI text must be ≥ 20 px on screen when it matters.
5. **Beat grid.**
   - Compose on a fixed BPM (default 120 BPM → beat = 0.5 s = 15 frames at 30 fps, bar = 2 s).
   - Section/scene changes land on bar lines; hits (word pops, card pops, counters landing, clicks) land on beats.
6. **Determinism.**
   - Remotion animation is driven only by `useCurrentFrame()` (via `interpolate`, `spring`, `prog`).
   - No CSS transitions or animations, no `Math.random`/`Date`; use `rnd(seed)`.
7. **No double exposure.** Two text layers must never share the screen during a transition. Use the "dip" hand-off in `Main.tsx` (outgoing layer blurs out before the incoming one rises in) unless both scenes share a background.

## Phase 0 — Intake (ask first)
Ask the user for context before doing anything else. The full questionnaire, with why each item matters and the default if blank, is in `references/intake.md`.
- **Required:**
  1. Company/product name.
  2. Website URL.
  3. One-line description + audience.
  4. Where the product footage comes from (public demo URL / sandbox login / screenshots / recordings), and what must never be shown.
  5. The ONE outcome or use case the film should follow.
  6. Approved proof (customer names + numbers, or "none").
  7. CTA (URL + action, e.g. "Book a demo").
- **Optional, with defaults:**
  - Positioning do/don't phrases; competitors.
  - Brand assets (logo SVG, colours, fonts, guidelines).
  - Style references / anti-references (videos they love or hate).
  - Length (60 s), aspect (16:9), audio (music-only, original score), tone (premium, confident, technical).
  - Distribution channel; deadline; approvers; legal lines.

**How to ask:**
- Ask in ONE message. Use `AskUserQuestion` for the discrete choices (length, aspect, audio, tone) and plain text for the rest.
- Offer: "anything you don't know, I'll research from your website."
- Record answers verbatim in `INTAKE.md` at the project root. If the user says "you decide", decide and write the decision down.

## Phase 1 — Toolchain
Check, and install what's missing (ask before installing system packages):
```bash
ffmpeg -version | head -1            # brew install ffmpeg / apt install ffmpeg (needs libx264)
node -v                              # >= 20
python3 --version                    # >= 3.10
whisper-cli --help >/dev/null 2>&1 || echo "optional: whisper-cpp + a ggml model (reference-video transcription)"
```
Create the project (one folder per film; all later commands assume this layout):
```bash
mkdir -p <film> && cd <film>
cp -R <skill-dir>/template/video ./video && cp -R <skill-dir>/template/audio ./audio && mkdir -p capture work
python3 -m venv .venv && .venv/bin/pip install numpy scipy pedalboard soundfile pyloudnorm pillow
(cd video && npm i && npx playwright install chromium)
```
`<skill-dir>` is this skill's base directory. Layout: `<film>/{video,audio,capture,work,.venv}`, with `BRIEF.md`, `STORYBOARD.md`, `INTAKE.md` and `BUILD_GUIDE.md` at `<film>/`.

## Phase 2 — Research & capture
All captures go to `video/public/` so scenes can `staticFile()` them.

Run the capture scripts from `video/` (that's where Playwright is installed).

1. **Website → brand + copy.**
   ```bash
   cd video && node <skill-dir>/scripts/capture-site.mjs https://example.com public/site --dark --pages=/,/customers
   ```
   - Writes 2× section screenshots, `brand.json` (CSS custom properties with sRGB hex, font families, most-used colours with hex, `<title>`, meta description), `copy.txt` (visible text in reading order), `links.json` and any inline SVG logos (`logo-*.svg`).
   - Read `copy.txt` fully. Positioning, pillars, proof and CTA usually live there.
   - Look at the screenshots to learn the visual language: palette, type, motifs (dashed lines, dot grids, photography, etc.).
2. **Product → 4K captures + element boxes.**
   - First explore each page:
     ```bash
     node <skill-dir>/scripts/capture-product.mjs --explore <url> ../work/explore
     ```
     This prints links, buttons, inputs and visible text.
   - Then write `../capture/shots.config.json` (format in the script header) and capture:
     ```bash
     node <skill-dir>/scripts/capture-product.mjs ../capture/shots.config.json public/shots
     ../.venv/bin/python <skill-dir>/scripts/contact-sheet.py public/shots ../capture/shots_sheet.jpg
     ../.venv/bin/python <skill-dir>/scripts/contact-sheet.py public/site ../capture/site_sheet.jpg --cols 4 --width 480
     ```
   - The contact sheets are what agents read first.
   - Every state is saved as a 3840×2160 PNG (2× DPR of a 1920×1080 viewport) plus `<name>.rects.json`. The rects file holds `{tag, kind, text, x, y, w, h}` for every text element, card and control, in 1920×1080 viewport coordinates. Scene builders use it to aim push-ins and focus rings precisely. Capture:
     - one state per story beat (overview, the "goal" input, plans/agents/progress, result/approval, proof views);
     - **a blank and a typed version** of any input you will "type" into. The typing animation becomes a pixel-exact left-to-right wipe between the two captures, so no font matching is needed;
     - tall pages as several scrolled states, not one huge image.
   - If the app hides content when the tab is hidden, the script forces `visibilityState=visible`.
3. **Reference videos** (the user's past videos, or films they like). Run from `<film>/`:
   ```bash
   bash <skill-dir>/scripts/analyze-reference.sh ref.mp4 work/ref      # WHISPER_MODEL=/path/ggml-base.en.bin for transcription
   ```
   - Writes 1 fps contact sheets (12 s per sheet), scene-cut times, `audio16k.wav` + `audio48.wav`, a transcript (if whisper-cpp is installed: VO or music-only?) and loudness.
   - `audio48.wav` is the tonal reference for `band-match.py` later.
   - Note what to *learn* (house style, motifs) and what to *beat* (length, pacing, missing product/proof/CTA).
4. **Proof check.** Trace every number you plan to show to a source URL or explicit user approval.

## Phase 3 — BRIEF.md
Copy `references/brief-template.md` to `<film>/BRIEF.md` and fill it with:
- deliverable specs;
- positioning (on-message / off-message phrases);
- the one story;
- the copy bank (verbatim site lines);
- proof with sources;
- the product capture inventory (file → what it shows);
- the brand system (hex values, fonts, motifs);
- reference-film learnings;
- technical constraints.

Every later agent reads this file. Be concrete: exact hex values, exact file names, exact numbers.

## Phase 4 — Storyboard + adversarial critique
1. Write `STORYBOARD.md` from `references/storyboard-template.md`. The default 60 s shape at 120 BPM is below; see the template for 30 s and 90 s shapes.

   | Time | Act | Content |
   |---|---|---|
   | 0–12 | Tension | Hook (the metric they're judged by) → stakes (why +1% matters) → the problem (where the win hides, why it's slow). A riser, then a 0.25 s breath of silence. |
   | 12–16 | Reveal | **Hard cut on the drop**: logo draws and fills, tagline. |
   | 16–42 | The loop, in the real product | 3–4 labelled steps (e.g. 01 learns your system → 02 starts from a goal → 03 explores in parallel → 04 ships what holds up). Each step has a caption band, real UI with push-ins/focus rings, and a rebuilt motion-graphic beat. |
   | 42–52 | Proof | Customer numbers counting up and landing on hits; then the compounding/speed line. |
   | 52–60 | Close | Emotional resolve line; end card (logo sting, tagline, URL, CTA button, footer line). Last 15 frames fade to black. |

   Every scene states:
   - exact copy (pill words in `[brackets]`);
   - exact asset files;
   - absolute hit times;
   - layout;
   - motion;
   - transition;
   - music cue.

   The file also contains the **hit list** (every sync point, in seconds), the **music plan**, and **global design notes**.
2. **Critique before building.** Run two independent critics in parallel (prompts in `references/agent-prompts.md`):
   - **Brand/truth:** is every line on-message and factual, the story single-threaded, the demo data kept out of headlines, and the closing line memorable?
   - **Craft/readability:** does it pass words-vs-seconds per caption, do section changes land on bar lines, do the captures actually show what each scene claims (open them), is it buildable, does the layout fit?

   Apply the fixes and lock the storyboard (v2/v3). Re-capture assets if the story changed (e.g. the typed goal text).

## Phase 5 — Scaffold the Remotion project
1. Brand the design system:
   - `video/src/design/tokens.ts`: palette from `brand.json`, type scale, eases.
   - `fonts.ts`: brand fonts via `@remotion/google-fonts`, or `@font-face` on files in `public/fonts`.
   - `logo.ts`: mark SVG path(s) + viewBox, for the draw-then-fill logo animation.
2. Write the scene windows into `video/scenes.json` (id, start, end, title, handoff), then generate the timeline, stubs and isolated entry points:
   ```bash
   cd video && node tools/scaffold.mjs        # (also runs on npm i) writes src/film.ts, src/timeline.ts, SNN.tsx stubs, scenes/index.ts, entries/SNN.tsx
   npx tsc --noEmit -p . && node tools/stills.mjs S01 0,30 0.5
   ```
3. Copy `references/build-guide.md` to `BUILD_GUIDE.md` at the project root, filled with this film's specifics. Builders read it.

**Isolation matters.** Each scene renders from its own entry (`src/entries/SNN.tsx`), so a half-written file in one scene never breaks another builder's renders.

## Phase 6 — Parallel build + score
- **Builders.** One builder per 2 adjacent scenes. A builder owns only `src/scenes/SNN.tsx` (+ `src/scenes/parts/SNN_*`), follows the storyboard verbatim, and verifies every hit frame with `node tools/stills.mjs SNN <frames> 0.5`.
- **Composer.** One composer runs in parallel (see Phase 7).
- **Review.** Then one adversarial art director per pair renders the scenes, critiques them against the storyboard and quality bar, and **fixes** directly.

Prompts are in `references/agent-prompts.md`. Orchestration:
- If the Workflow tool is available and the user opted into multi-agent orchestration, use the scripts in `references/workflows.md`.
- Otherwise spawn the builders as parallel `Agent` subagents in one message.
- Otherwise build sequentially yourself.

**Keep each agent task ≤ ~15–20 min and resumable** ("if your file already has real work, continue from it"). Long agents get interrupted, and file-based progress survives restarts.

Look at every builder's contact sheet as results arrive. Fix shared-primitive bugs centrally in `src/design/*` (keep the API stable).

## Phase 7 — Score
Default is an **original score**, composed to the hit list. Read `references/audio.md` first.
1. Export the hit list and sections to `audio/score.json`. Run, from `<film>/`:
   ```bash
   .venv/bin/python audio/compose.py
   ```
   - It renders `video/public/audio/score.wav`, masters it (−14 LUFS, ≤ −1 dBTP) and prints a verification report (loudness, true peak, placement error of every hit).
   - It also renders `audio/score_viz.png` (waveform, spectrogram, loudness, hit markers). Look at it.
2. **Tonal balance.** Synthesized mixes come out too bright and too thin in the low mids. Compare octave bands against a professionally mixed reference and correct the master EQ until each band is within ~±4 dB:
   ```bash
   .venv/bin/python <skill-dir>/scripts/band-match.py work/ref/audio48.wav video/public/audio/score.wav --ref-range 20 100 --ours-range 12 52
   ```
3. Alternatively, drop a licensed track at `public/audio/score.wav`. Keep the cut points on its bar lines, and note the licence.
4. Set `"audio": true` in `scenes.json` and re-run `node tools/scaffold.mjs`.

Placement is exact by construction. If the onset detector "misses" a soft tick inside a dense groove but reports 0.00 placement error, that is masking, not a sync bug.

## Phase 8 — Assemble, render, QA
```bash
cd video && ./tools/qa.sh <name>              # render + 1 fps contact sheet + loudness report
node tools/boundaries.mjs out/<name>.mp4      # frames just before/after every scene boundary → sheet
```
Check:
- **Contact sheet:** the whole arc reads at a glance.
- **Boundary sheet:** no double-exposed text, no blank or flash frames, no brightness collapse.
- **Full-res frames** at every UI push-in: key UI text is legible, the camera is aimed precisely, and no demo numbers are in focus.
- **Loudness report:** −14 ±0.5 LUFS, ≤ −1 dBTP, duration exact.

## Phase 9 — Fresh-eyes final review → fix → masters
Run two independent reviewers on the **rendered MP4** (not the code):
- **Story/brand/truth.**
- **Cross-scene craft:** caption band consistency, transitions, pacing dead spots, grading continuity, end card.

They report must-fix / should-fix items with timestamps. Apply fixes in parallel (one fixer per scene group) and re-render.

Iterate until both reviewers would sign off. Then:
```bash
npx remotion render Main out/<name>-4k.mp4 --scale=2 --codec=h264 --crf=18 --pixel-format=yuv420p --audio-codec=aac --audio-bitrate=320k
ffmpeg -ss <end-card-time> -i out/<name>.mp4 -frames:v 1 out/<name>-poster.png
```

## Phase 10 — Deliver
Send the 1080p file to the user. In the delivery note, state:
- what's in it (story beats);
- where everything lives;
- what you verified, with numbers (loudness, sync, review scores);
- what **they** must check:
  - listen to the score on speakers;
  - confirm customer-claim permissions;
  - confirm nothing private is on screen.

Write the project `README.md` from `template/PROJECT_README.md` (re-render commands, file map, how to swap music).

## Quality bar (the art-director checklist)
- **Focal point.** Every frame has one clear focal point and generous negative space; nothing touches the safe margin.
- **Copy.** Copy is verbatim from the storyboard. The pill highlight sweeps in, and punctuation after a pill sits tight (`[word].`).
- **Product windows.** Slight 3D tilt and a slow continuous dolly (never static). Push-ins ease over ≥ 1 s, with zoom ≤ ~2.2× of the capture's 1× viewport (sharpness limit at 2× DPR).
- **Rebuilt UI** (cards, race lanes, PR/diff, charts) matches the brand system and the product's real look. Status colours mean something (good / dimmed / failed).
- **Motion.** Eased entrances, small spring overshoot on pops, 2–4 frame staggers. Nothing moves linearly except slow drifts.
- **Hits land on beats**, and section changes land on bar lines.
- **Transitions:** dip by default, cross-dissolve only when backgrounds match, hard cut on the drop.
- **Grading continuity.** No sudden brightness collapse. The close should feel like release, brighter than the middle.
- **End card.** The full lockup (logo, tagline, URL, CTA) holds ≥ 2.4 s before the fade.

## Pitfalls (details in `references/pitfalls.md`)
- **Stitched stories.** Mixing unrelated demo projects into one loop: the goal, hypotheses, race, PR and result must all be the same metric.
- **Text over text in cross-dissolves.** Use the dip hand-off and a shared base backdrop.
- **Detached punctuation after pills.** The template's `Words` already handles `[word].`.
- **Agents reading dozens of 4K PNGs.** Slow. Give them contact sheets plus rects JSON instead.
- **Over-zoom.** Zooming past 2.2× makes 2× captures soft. Frame tighter in the capture instead.
- **Grade overcorrection.** Desaturating a warm painting to grey kills the mood. Check the grade at full resolution, not in thumbnails.
- **Unreadable logos.** Customer logos are often low-res PNGs. Render them small, tinted via `filter: brightness(0) invert(1)`.

## Files in this skill
- `references/intake.md`: the user questionnaire (required/optional, defaults).
- `references/brief-template.md`, `references/storyboard-template.md`: document templates with a worked example.
- `references/build-guide.md`: rules for scene builders (ownership, timing, toolkit, render loop, quality bar).
- `references/agent-prompts.md`: critic, builder, composer, art-director, final-review and fixer prompts.
- `references/workflows.md`: optional multi-agent Workflow scripts.
- `references/audio.md`: score composition, mastering, sync verification, tonal matching, licensed-track route.
- `references/review-checklists.md`: storyboard, scene and release checklists.
- `references/pitfalls.md`: everything that went wrong once, and the fix.
- `scripts/`:
  - `capture-site.mjs`, `capture-product.mjs`: Playwright capture tools.
  - `contact-sheet.py`: labelled image grids for agents.
  - `analyze-reference.sh`: reference-video analysis.
  - `band-match.py`: tonal balance vs a reference, plus EQ suggestions.
- `template/video`: Remotion project (design system, primitives, `Main.tsx` hand-off grammar, `scaffold.mjs`, `stills.mjs`, `mainframes.mjs`, `boundaries.mjs`, `qa.sh`).
- `template/audio`: `synth.py` (instrument kit), `compose.py` (arranger, mastering, verification, visualisation) and an example `score.json`.
- `template/PROJECT_README.md`: README for the delivered film project.
