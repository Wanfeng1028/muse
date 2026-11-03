---
name: product-launch-film
description: >-
  Use when the user wants a short (30-60 s) launch, promo or explainer video for their own software
  product, repo, CLI, library or app, built as code (Remotion/React) from the real product, with
  narration, original music and SFX, and iterated on their feedback. Covers research, story, real
  output capture, visual direction, Remotion build, layout checks, ElevenLabs voice-over, mixing,
  -16 LUFS mastering and review. Not for live-action editing or generic stock-footage ads.
---

# Product launch film (code-rendered)

Goal: a 40-60 s, 1920×1080 @ 60 fps film that looks hand-made, shows only what the product
really does, and does not read as AI slop.

Files in this skill:
- `templates/remotion-starter/`: a pinned Remotion project with a theme, copy, layout checker,
  contrast checker, stills/audit, VO, music and mastering scripts. Copy it, don't build from scratch.
- `references/checklist.md`: the anti-slop and review checklist. Run it before every delivery.
- `references/case-studies.md`: what went wrong and what fixed it on two real projects. Read it once.
- `references/heli/`, `references/connectra/`: real concept docs, narration scripts, on-screen copy
  and layout checkers from those films, as worked examples.

## 1. Understand the product before designing anything
1. Read the real source: README, docs, CLI commands (`--help` of every subcommand), UI code and
   styles, skills/config dirs, releases and changelog. If there is a live website, read its copy, CSS
   and mock panels.
2. Find the ONE idea that makes users' lives easier: a daily pain it removes. That is usually not the
   most technical feature. Security and governance are usually a supporting beat, not the story.
   (Heli v1 was "agents can't push without a grant". The owner rejected it: "Heli is not just
   push-blocking". v2 became "switch AI CLIs, keep the task thread".)
3. Take the owner's description of what the product is *for*. If they correct the concept, their
   correction beats your reading of the code.
4. Write a features-shown table: each feature, the file/function/command it comes from, and whether you
   ran it. Flag anything you could not run or verify. Never invent features, metrics, star counts,
   customers, or capabilities the product lacks. Show real behavior honestly. For example, if calls go
   one device at a time, show a fast cascade, not a "broadcast".

## 2. Story first
1. Write one tagline before any visuals, e.g. "Switch tools. Keep the thread." Use it as the climax
   title and on the end card.
2. 6-8 scenes, one beat each: pain → set up once → the core moment → breadth (any tool / anyone) →
   proof/trust → close (wordmark, tagline, install command or URL).
3. Use a concrete, relatable scenario (a dev on Monday vs Tuesday; one person with ten machines)
   instead of abstract claims.
4. One idea per frame, few elements, big confident headlines, holds long enough to read. If a frame
   needs a paragraph, it's two frames or none. (Heli v1 S2/S4 were rejected as "too dense".)

## 3. Capture real output
- Run the actual CLI/app in a throwaway sandbox: temp `HOME`, scratch project, copy of the repo. Never
  run it against the user's real config. Capture stdout/stderr and hook JSON verbatim into
  `docs/captures/`. Put on-screen strings in one `copy.ts`, with a comment saying where each came from.
- Only the demo repo/data may be fictional. Say so in the concept doc. Localise sandbox paths
  (`/private/tmp/x/shop` → `~/code/shop`) and nothing else. Mark omissions with "…" and call excerpts
  excerpts.
- Rebuild UI as React components faithful to the product's real UI: layout, spacing, icons, status
  chips, dialogs, real light/dark tokens from its stylesheet. Faithful beats decorative. Third-party
  tools (agents, IDEs, phones) get generic panes with their name as plain text, not their logos.

## 4. Visual direction
- Pick a mood distinct from the user's other films. Derive palette, type and icons from the product's
  own brand, hero image or app theme (Heli v2: cobalt from the repo hero image; Connectra: the app's
  violet).
- **Default to light.** Dark terminal-on-black reads as AI slop unless the brand itself is dark. Both
  dark first cuts (Connectra v1/v2, Heli v1) were rejected on sight. Light, editorial, cool or warm
  paper, generous space.
- **No dark code blocks inside light UI.** Use light terminal/editor surfaces: white panel, quiet header
  strip, ink text, tinted highlights.
- Remove slop tells: pill/badge overload, glow, decorative gradients, uniform card grids, nested boxes
  and borders, fake metrics, emoji, gratuitous checkmarks, "✨", stacked status chips, bouncy springs on
  everything, and centered everything.
- Apply Jakub Krehel's UI skills (https://jakub.kr/skills, github.com/jakubkrehel/skills; install them
  separately, they are not vendored here). Key rules: nested radius = inner + padding, shadow rings
  instead of borders, one filled primary button per panel, spacing over dividers, tabular numbers,
  weight ≥ 400 below 18 px, `text-wrap: balance` on titles.
- **Contrast:** every text colour meets WCAG AA (≥ 4.5:1, ≥ 3:1 only for display text ≥ 24 px) on
  *every* surface it sits on. Make labels darker than feels necessary. Connectra's ink3 went from 3.2:1
  to 6.3:1 after "labels are too faint". Keep colours in `palette.ts` and run `npm run check:contrast`.
- **Typography:** a real pairing, e.g. Schibsted Grotesk + JetBrains Mono, or the product's own fonts.
  Load them via `@remotion/google-fonts`. **Disable ligatures in all code text**
  (`fontVariantLigatures: 'none'` and `fontFeatureSettings: '"calt" 0, "liga" 0'`). Otherwise `->`,
  `!=`, `>=` and `--` turn into glyphs and the "real output" stops being real.
- **No overlaps, ever:** not between blocks, not mid-animation, not with titles. Prefer slides and
  crossfades over things flying across each other.

## 5. Build (Remotion)
- Start from `templates/remotion-starter`: one component per scene, `theme.ts`/`palette.ts`, `copy.ts`
  for all text, `timeline.ts` for absolute scene frames, `layout.ts` for every positioned block.
  Register the full film, a muted picture-only composition and one composition per scene.
- **Keep old versions:** a new cut is a new folder (`src/v2/`) and new compositions. Never overwrite a
  version the user has seen. Commit each version.
- **Pin Remotion to 4.0.530** (all `remotion` / `@remotion/*` packages at the exact same version, no
  `^`). 4.0.531's `@remotion/cli` shipped an empty `dist/render-queue/queue.js` that broke the Studio.
  Bump deliberately and test `studio`, `render` and `stills` before trusting a new version.
- **Render PNG frames to yuv420p H.264:** `Config.setVideoImageFormat('png')` plus
  `--pixel-format=yuv420p --crf=18`. JPEG frames give full-range `yuvj420p`, which some players and
  uploaders show washed out.
- **Layout checker** (`npm run check:layout`): pure geometry, no rendering. Every block is inside the safe
  area, no two blocks in a scene are closer than `MIN_GAP`, every monospace line fits its block (JetBrains
  Mono advance = 0.6 em), titles fit (estimate ~0.56 em per char for grotesks), and no pane's content is
  taller than its view. For radial/isometric layouts, also check spokes, labels and morph in-betweens
  (see `references/connectra/check-fleet.ts`). Run it on every change; it catches what eyes miss.
- **Stills + audit:** `npm run stills` (named review frames at full size) and `npm run audit` (every
  15 frames plus mid-animation extras, half size, ~200-300 JPGs). Tile them into contact sheets
  (`ffmpeg -pattern_type glob -i 'out/audit/*.jpg' -vf scale=384:-1,tile=6x8 sheet-%02d.jpg`) and look
  at every sheet for overlaps, cropping, blank or half-empty frames, and text that appears before the
  voice says it.
- Fonts load from Google Fonts at render time (network needed). Node ≥ 22.18 runs the `.ts` check
  scripts directly; keep them free of `.tsx` imports.
- Long renders on a remote/agent shell: keep the render in the foreground with a long timeout. Agent
  shells often kill background jobs when the call returns. Check that the log is still growing.

## 6. Sound
- **Narration script:** conversational and punchy, not script-reading. Contractions, short phrases, a
  little attitude, second person ("You start a fix in Claude Code. Two tries, no luck."). ~2.3-2.7
  words/s. Each line must finish inside its scene with ~0.3 s of air. Fit the timeline to the measured
  takes, not the other way round.
- **Voice:** audition 3-4 expressive voices on 1-2 representative lines, not the whole script. Use
  `eleven_v4` (or v3) with audio tags (`[casual]`, `[confident]`, `[warm, confident]`), stability ~0.4,
  similarity 0.75, speaker boost, and request stitching (`previous_text`/`next_text`) so lines sound
  like one read. Generate 2-3 takes per line and pick per line.
- **Pronunciation check:** run every take back through speech-to-text (ElevenLabs `scribe_v1`;
  `scripts/vo/vo.py --stt`). If STT mishears the product name ("Heli" → "Healy"), rewrite the line so
  the name comes with context ("Heli-Harness") or drop it. Respellings are unreliable.
- **Prosody numbers when you can't listen:** `scripts/vo/prosody.py` reports pitch spread, loudness
  movement and words/s per take. Flat takes (pitch SD < ~2 st) sound read. Still tell the user nobody
  has listened yet.
- **VO cleanup:** `scripts/vo/process-vo.sh` does a high-pass, gentle compression and a soft limit. It
  lowers the crest ~3 dB so the master limiter barely works. It needs a full ffmpeg (Remotion's bundled
  one lacks `alimiter`).
- **Music + SFX:** original synthesis (`scripts/make-audio.py`, numpy only) or clearly licensed tracks;
  record the source in CREDITS.md. Change the chord on scene cuts. Hold back under the proof beat,
  resolve on the close. Use subtle SFX (tick, thread, deny, allow, bloom, air) only on on-screen events,
  each tied to a frame in `CUES`.
- **Mix:** music bed ~0.34, ducked to ~0.085 under speech (≈ -12 dB; 12-frame down, 24-frame up). Speech
  should sit 9-14 dB above the bed. Expose stem switches (`--props='{"vo":false}'`) for checking.
- **Master:** `scripts/master-audio.mjs` measures EBU R128, applies one static gain to -16 LUFS integrated,
  then a transparent look-ahead limiter (sample ceiling -2.3 dB). It re-measures and trims, stream-copies
  the picture and muxes AAC. Targets: I = -16 ±0.5 LUFS, true peak ≤ -1.5 dBTP (aim ≤ -2). If the
  limiter is active on more than ~10% of samples, fix the mix instead.
- **Licences:** a free-tier ElevenLabs voice means attribution ("Narration voice: ElevenLabs" on the end
  card) and no commercial use. Say that in the delivery. Remotion is free for individuals and companies
  of up to 3 people; larger companies need a company licence (remotion.dev/license). Keep API keys in the environment only. Never
  print them, write them into files, or copy them between machines.

## 7. Review and iterate
1. Before showing anything, review your own stills and audit sheets critically and iterate at least once.
   Run `references/checklist.md`.
2. Verify the file: `ffprobe` duration, 1920×1080, 60 fps, `yuv420p`, AAC; loudness via `ebur128`.
3. Deliver: the MP4, 3-10 key stills, the tagline and story, a per-scene summary, the narration text,
   the features-shown table with sources, and honest notes. The notes cover what's unverified, what's
   fictional, weak spots, characters/credits used, and licence limits.
4. Take feedback literally, axis by axis (voice, story, colour, density, specific components). Keep what
   they liked exactly as it was (Heli v2 kept the voice, delivery style and pacing and changed
   everything else). Make the next cut a new composition.
