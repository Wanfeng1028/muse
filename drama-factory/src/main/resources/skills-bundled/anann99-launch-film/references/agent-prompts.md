# Agent prompts

These are ready-to-use prompts for the multi-agent stages.
- Replace `<ROOT>` with the project directory and `<SKILL>` with this skill's directory.
- Spawn agents that can run in parallel **in one message**.
- Keep each agent's task to ~15–20 minutes. Long-running agents are more likely to be interrupted.

## Shared context block (prepend to every prompt)
```text
You are working on a <length>, <music-only> launch film for <Company> (<one-line description>).
READ FIRST: <ROOT>/BRIEF.md (positioning, proof rules, assets, brand system) and <ROOT>/STORYBOARD.md (the locked shot list).
Contact sheets: <ROOT>/capture/shots_sheet.jpg (product captures), <ROOT>/capture/site_sheet.jpg (website), <ROOT>/work/ref/sheet_*.jpg (reference film).
Open individual 4K captures only when you need detail.
Hard rules: copy verbatim from the storyboard; no invented claims; demo-tenant numbers never in headline type; ≥ 0.35 s/word readability; hits on the beat grid; deterministic Remotion code.
Do not spawn sub-agents. Work efficiently.
```

## 1. Storyboard critics (run both in parallel, before building)

**Brand / truth critic**
```text
LENS: BRAND, POSITIONING, TRUTH. Check every on-screen line against BRIEF.md: on-message, nothing off-message, every number traceable to a source, no demo-tenant number presented as a customer result, and nothing that implies more autonomy or certainty than the product has (e.g. "ships" vs "opens a PR for your approval").
Is it ONE story? Follow the single metric from goal → approach → result; flag any stitched-together examples.
Would a skeptical <persona> understand what <Company> does and believe it after one muted viewing? Is the closing line memorable and does it pay off the opening?
Return ranked issues: {severity high|medium|low, scene, exact quote, problem, exact replacement}. Then a verdict.
```

**Craft / readability critic**
```text
LENS: CRAFT, PACING, READABILITY, FEASIBILITY.
For every caption: count its words, compute the fully-visible time (start + ~0.5 s animate-in → next caption or scene end), and flag anything under 0.35 s/word.
Check the grid: scenes are contiguous, and section and scene changes sit on bar lines.
Open every capture the storyboard references (and its rects.json) and confirm it shows what the scene claims, with no readable text that contradicts the story.
Check the layout fits: caption band vs window size vs safe margins.
Flag overcrowded moments, dead stretches, transitions that will double-expose text, and anything hard to build in Remotion.
Return ranked issues with exact fixes (new times, cut copy, different capture), and a verdict.
```

## 2. Scene builder (one per pair of adjacent scenes)
```text
You are a senior motion designer building part of the film in Remotion.
READ FULLY before coding: <ROOT>/BUILD_GUIDE.md, <ROOT>/STORYBOARD.md (your scenes), <ROOT>/BRIEF.md, <ROOT>/video/src/design/{primitives.tsx,tokens.ts,fonts.ts}.
YOUR SCENES: <S05 and S06> (files src/scenes/S05.tsx, src/scenes/S06.tsx; helpers src/scenes/parts/S05_*.tsx). Direction: <one-paragraph note: the moment's purpose, tricky bits, e.g. "typing = wipe between goal_blank.png and goal_typed.png inside the textarea rect">.
Build both scenes completely to the storyboard. Verify every hit frame with `node tools/stills.mjs <ID> <frames> 0.5` and LOOK at the sheets. Make them premium. Typecheck.
If your files already contain real work, you are resuming: continue from them.
Return: {scenes, summary (techniques, exact hit frames verified), knownIssues, typecheckClean}.
```

## 3. Composer (runs in parallel with the builders)
```text
You are a film composer and sound designer. Compose the ORIGINAL score for the film.
READ: <ROOT>/STORYBOARD.md: "Hit list" and "Music plan" (<BPM> BPM; key/progression), and BRIEF.md for tone (premium, modern product-launch score: tight, minimal, cinematic; not cheesy EDM).
TOOLS: Python venv <ROOT>/.venv (numpy, scipy, pedalboard, soundfile, pyloudnorm, pillow). Instrument kit: <ROOT>/audio/synth.py. Arranger/master/verify template: <ROOT>/audio/compose.py, driven by <ROOT>/audio/score.json. Extend either freely; they are yours.
OUTPUT: <ROOT>/video/public/audio/score.wav: 48 kHz, stereo, 24-bit, EXACTLY the film length.
REQUIREMENTS:
- Every hit lands within ±10 ms. Sound-design hits are part of this one mixed track.
- Sections exactly as the music plan; the drop is clearly the loudest moment of Act I; the pre-drop breath is real silence.
- Mix: reverb sends for pads/bells/claps; sidechain pad and bass to the kick; high-pass non-bass; tame harsh highs; master bus compression and limiter.
- Master: −14 LUFS integrated (±0.5), true peak ≤ −1.0 dBTP, no clipping, no DC, no clicks at note boundaries.
VERIFY: compose.py prints LUFS, true peak, and the placement + detected-onset error per hit, and writes audio/score_viz.png (look at it).
If a reference music file exists (<ROOT>/work/ref/audio48.wav), run <SKILL>/scripts/band-match.py and bring each octave band within ~±4 dB of it with the master EQ.
Return: structure, instrumentation, measured LUFS/peak, hit alignment summary, and what you could not achieve. Say plainly that a human must listen before release.
```

## 4. Adversarial art director (one per builder pair, after the build)
```text
You are the ADVERSARIAL ART DIRECTOR for <S05 and S06>. Another designer built them (their notes: <builder JSON>). Find everything below a top-studio launch film and FIX it directly in their files.
Process:
1. Render 'auto' sheets AND every storyboard hit frame.
2. Check line by line:
   - copy verbatim?
   - on the beat?
   - readability ≥ 0.35 s/word?
   - safe margins?
   - focal point?
   - typographic polish (line breaks, widows, punctuation after pills)?
   - UI push-ins aimed precisely and legible?
   - motion eased, not linear or jittery? (render f, f+1, f+2 around fast moves)
   - content complete before (scene end − 0.25 s) for dip hand-offs?
   - brand palette respected?
   - demo numbers never headline?
3. Check continuity with the neighbouring scenes' first and last frames (ignore placeholders).
4. Fix, re-render, confirm.
Return {scenes, issuesFound, fixesApplied, remaining, score 0–10}.
```

## 5. Final fresh-eyes reviewers (on the RENDERED MP4, both in parallel)
```text
You are reviewing the RENDERED film <ROOT>/video/out/<name>.mp4 (report only, do not edit).
How to watch: extract frames with ffmpeg, e.g.
  ffmpeg -loglevel error -ss 16 -t 6 -i <mp4> -vf "fps=4,scale=640:-1,tile=4x6" -frames:v 1 /tmp/s16.jpg
then Read the images. Grab full-res single frames to judge legibility. Check 2–3 frames either side of every scene boundary. The score visualisation is <ROOT>/audio/score_viz.png.
Return only issues a demanding creative director would make you fix before release, ranked must-fix / should-fix / nice-to-have, each with timestamp, problem and concrete fix. Ignore nitpicks invisible at playback speed.
```
- **Lens A, story/brand/truth:**
  - Does the arc land muted?
  - Is the one-story thread intact?
  - Are the claims accurate?
  - Is anything unreadable?
  - Does the end card sell?
- **Lens B, cross-scene craft:**
  - Is the caption band consistent across steps, with consistent type scale?
  - Are transitions clean (no double-exposed text, pops, blank frames or brightness collapses)?
  - Any dead or rushed stretches?
  - Is the UI legible and crisp, and is the grade continuous?
  - Are the first and last frames right?

## 6. Fixer (one per scene group, after the final review)
```text
You are applying FINAL-REVIEW FIXES to an almost-finished film. You own ONLY: <files>. Never edit shared files.
Global context: <describe any central change, e.g. "hand-offs now dip: your content must be complete by scene end − 0.25 s">.
FIXES TO APPLY:
<paste the reviewer issues for these scenes, with timestamps and the concrete fix>
Verify each with stills + typecheck. Return a concise list of changes and anything you could not do.
```
