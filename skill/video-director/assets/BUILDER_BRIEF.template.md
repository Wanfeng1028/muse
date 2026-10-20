# BRIEF: scene builder <AGENT_NAME> for <FILM_NAME>

Fill every <...> before sending. One builder owns one contiguous range of scenes. The orchestrator owns the core.

## Where

- Workdir (absolute): <ABSOLUTE_PATH>/video. Run every command from here.
- Read first: `CREATIVE.md` (sections 1, 2, 5 for your beats, 6), `README.md`, `src/data/timeline.ts`,
  `src/lib/{motion,seam,format}.ts`, `src/theme/tokens.ts`, and every official Remotion skill file in full, not a
  selection: load `remotion-best-practices`, list every `.md` under its base directory and read each one to its last
  line (video-director `SKILL.md`, Step 0).
- Your scenes: <scene ids>, film time <start>-<end> s (frames <a>-<b> at <fps> fps).
- Style frames approved at G3: <paths>. Build dresses this layout; it never redraws it.

## File rules

- Write ONLY: <src/scenes/X.tsx, src/scenes/x/*>. New helpers go inside your own files, prefixed with your scene
  name.
- Never edit: `src/data/*`, `src/theme/*`, `src/lib/*`, `src/Main.tsx`, `src/Root.tsx`, `tools/*`, `package.json`,
  other builders' scenes. Need a new time ref, token, helper, package or a timeline change? Stop and send a request
  to the orchestrator with the exact change and why.
- Pure function of the frame: `useTime()` / `useTimeline()`, `sp`, `tw`, `seeded`. Never `Math.random`, `Date`,
  timers, CSS transitions or animations.
- Times by name only (`t.wordAt("l04", "detail")`, `t.scene("proof").start`, `phrase.p2`); no magic seconds.
- Colours, sizes, fonts and easings from tokens and `motion.ts`; sizes multiplied by `u`; layouts via `pick()`
  for every active format.
- Media through `@remotion/media` / `CanvasImage` with `premountFor={fps}` (fps from `useVideoConfig()`).
- Scratch output only in `out/<AGENT_NAME>/`. Do not start Remotion Studio and do not run full renders (one heavy
  render at a time on the machine; the orchestrator owns Studio and masters).

## Acceptance bar (numbers)

- Every element named in CREATIVE.md section 5 for your beats is present, with its verbatim copy.
- Reveals land on their VO word: start within 0 to +2 frames of the word's start, never before it.
- Each element finishes animating and stays readable >= 1.5 s (product film) or as the storyboard says.
- Seams: your first frame enters mid-flight in the film's direction (<LEFT>) with a carrier visible from the cut
  frame; your last frames exit still moving; no blank frame on either side.
- Springs: damping ratio >= 0.72 (`springs.settle|snappy|heavy`); `playful` only if the brief declares it.
  Entrances ease out, exits ease in; no linear position easing; every `interpolate` clamped; scale tweens
  perceptual.
- Stagger <= 0.5 s per beat, in importance order. No idle breathing or floating on content.
- Layout: key text >= 80 px (scaled) from the sides, >= 100 px from top and bottom; nothing critical in the Tall
  bottom 18%; headline >= 84 px and supporting text >= 44 px at 1080 width; nothing overlaps the captions band
  when captions are visible.
- If you match a reference: position and size error <= 1-2% of frame, cut frames 0 off.
- Sound: every animated event you build (entrance, landing, press, cascade step, draw, counter, seam) has an SFX cue
  row in your report, timed by name like the animation: `{kind|file, at: <timeline expression>, gain, note?, role?}`.
  Gains 0.3 to 0.6, hero hits up to 1; tick runs and typing `role: "texture"`. An event you leave silent gets a reason.
- `npx tsc --noEmit` passes. No console errors in a still render.

## Honesty rules

- Copy is true for the product. Numbers only from `facts.md`; mock UI numbers read as examples.
- Real screens are captures or faithful rebuilds of captures; never invent UI, features or results.
- No real people's likeness unless the brief provides it with consent; no implied partnerships or logos you were
  not given. Never reuse a reference film's music, voice or footage.
- Report what you did not finish. Never claim a match or a fix you have not looked at.

## Method

1. Measure before building: read the timeline values for your range (word times, scene spans) and the style
   frame sizes. Write them down in your report.
2. Build the static layout for each format first; check it with stills at a held frame.
3. Add motion; verify with frame strips around every entrance, seam and fast move:
   `bash ~/.claude/skills/video-director/scripts/strip.sh <Comp> <start_s> <end_s> out/<AGENT_NAME>/strip.png --fps <fps>`
   and contact sheets of chosen seconds:
   `uv run ~/.claude/skills/video-director/scripts/stills.py <Comp> out/<AGENT_NAME>/sheet.png <t1> <t2> ... --fps <fps>`
   (add `--props '{"variant":"alt"}'` for another variant; check each script's `--help`).
4. Look at every PNG you render (open it). Fix, re-render, look again. A frame you did not view is unverified.
5. Check all active formats (Wide and Tall at least) and the first and last 15 frames of your range.

## Report (your final message)

| Scene | Frames | Status (DONE / ROUGH / BLOCKED) | Verified with (paths of stills/strips viewed) | Residual issues | Requests to orchestrator |
|---|---|---|---|---|---|

Plus: SFX cue rows for every animated event (the orchestrator merges them into `src/data/sfx.ts`), measurements you
used, any deviation from the storyboard and why, and exact files written.
