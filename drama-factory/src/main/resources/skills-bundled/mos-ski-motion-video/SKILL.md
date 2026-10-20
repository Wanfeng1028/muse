---
name: mos-ski-motion-video
description: Motion Video. Make product presentations, launch reels, feature demos and event promos as motion graphics rendered from code (Remotion), from a Figma design link, a product URL or a brief. House style is simple, punchy "jitter" motion (on-twos timing, snaps, montage bursts) or calm premium. Use when the user asks for a motion video, product video, launch video, showreel, animated explainer, motion ad, or "animate this Figma".
---

# Motion Video

Builds motion graphics in code: Remotion + the motion library in `engine/src/motion/lib.ts`
(springs, tracks, the jitter kit), `figmaKit.tsx` (animate real design screens), ffmpeg, and
real sound samples (with synthesized fallbacks). Everything is a pure function
of time, so every frame can be rendered, checked and fixed on its own.

`SKILL` = this skill's folder. `M` = `.motion/venv/bin/python SKILL/scripts/motion.py`. Run
commands from the user's project folder (Remotion commands from inside `studio/`).

## Setup (first time in a project)
- If `studio/src/motion/` or `.motion/venv` is missing, run `bash SKILL/scripts/setup.sh`
  (add `--beats` to also install librosa for measuring a music track). It creates `studio/` (a
  Remotion project with the motion engine and an example reel), `references/`, `demos/`, `work/`,
  `output/`, `sfx/` and `music/`.
- Check it works: `npx remotion still src/index.ts Reel-wide ../work/test.png --frame=60 --scale=0.33`
  (in `studio/`), then look at the PNG.

## Read first
`reference/style-study.md` (how to watch the user's `references/`), `reference/motion-language.md` (the jitter kit + product patterns: the core of this skill),
`reference/patterns.md` (what strong reference pieces do), `reference/craft.md` (render contract,
brief templates, shot-list gate, critique loop), and `reference/figma.md` (when there's a Figma
link). If the project has a brand file (`brand/brand.md` or similar), read it too.

## Pipeline (`work/<name>/`)
1. **Brief.** Collect: product + Figma link or URL, the goal (launch, feature, ad, event),
   duration (default 20s), formats (default 16:9 + 9:16), energy (**jitter** by default, or calm
   premium), CTA, music (file, synthesize, or none), voiceover (none, supplied, or generated; which
   voice), and **the problem in the customer's words**. Check `references/` and `demos/`. Ask only
   for what's missing; propose defaults. If `references/` is empty, ask for 5–10 clips of the
   motion the user wants (from Pinterest, Instagram, X, ...) before planning.
2. **Style study.** Watch every clip in `references/` and write `work/<name>/style.md`
   (`style-study.md`). This sets pace, type behaviour and moves for the whole film.
3. **Assets.** Follow `figma.md` (Figma MCP → tokens + exported layers in
   `studio/public/<name>/figma/`), one named Figma frame per scene that shows the product. Copy the
   user's `demos/` recordings (Jitter, After Effects, Rive, Canva, Figma prototype captures) into
   `studio/public/<name>/demos/` and note each one's flow and length. List the assets, tokens and
   recordings found, and **map every product scene to a frame or recording**. A scene with no
   source is a question for the user, never something to design.
4. **Script.** Write `work/<name>/script.md` on the arc **problem → solution → demo → CTA**
   (roughly 15% / 15% / 55% / 15% of the runtime): the pain in the customer's words, the product
   named as the answer, the demo told through real screens and recordings, one CTA. One short line
   per beat; if there's a voiceover, this is the VO script. Show the script and a 3–5 line summary
   of `style.md` together, and wait for an OK.
   **Voiceover** (if any), right after the OK so shots are timed to it: use the user's recording,
   or generate one line per beat with the TTS they have (a service, or a local model such as
   Kokoro: `af_heart`, `af_bella`, `am_michael`, `am_adam`, `bf_emma`, `bm_george`, ...).
   **Rotate voices:** read `work/voices.md`, pick a different gender or accent from the last video
   unless the user named one, match it to the audience, and append `<date> <name> <voice>`. Save
   `work/<name>/vo.wav` and the line timings; the shot list fits the VO, not the other way round.
5. **Beat grid.** With a track: `M beats music/track.wav > work/<name>/beats.json`. Without one:
   `gridFromBpm(120, dur)` in code. If the measured BPM is half or double what you hear, fix it
   before planning.
6. **Shot list → gate.** Write `work/<name>/shotlist.md` from `SKILL/templates/shotlist.md`
   (act, time on the beat grid, what's on screen, its source frame or recording, pattern from
   `motion-language.md` or `style.md`, text, SFX). Show it to the user and wait for an OK.
7. **Build.** One composition file per film in `studio/src/motion/<Name>.tsx`, modelled on
   `ExampleReel.tsx`: shots as `{from, to, draw(s)}`, all motion from `lib.ts`, product UI from
   the real screens via `figmaKit.tsx` (`Crop`, `Field`, `Option`, `Press`, `Cursor`), the design's
   tokens for colour, type and radius, layout in `unit(format)`. Demo recordings play with
   `<OffthreadVideo>` from `public/<name>/demos/`, trimmed and cropped to the step being shown,
   and can carry the same cursor, press and zoom overlays as the Figma screens. Register each
   format in `register.tsx` (ids like `<Name>-wide`, `<Name>-vertical`).
8. **Critique loop.** Stills per beat + a fast-action strip + a phone-size sheet; score; fix the 3
   worst; repeat until everything is 8+ (`craft.md`). At least 3 rounds. Look at the frames
   every time, compare them against the reference sheets, and run the slop check (hard rules)
   on every round.
9. **Sound.** Prefer **real samples**: licensed SFX in `sfx/<type>.wav` (any type name works:
   `pop`, `click`, `sent`, `ding`, `whoosh`, `typing`, `shutter`, `riser`, `glitch`, `cash`, ...) and
   a licensed or generated bed in `music/`. The built-in synthesized sounds are only a fallback for
   drafts; if `sfx/` is empty, tell the user and suggest adding a sample pack. Keep it **sparse**:
   about 6–8 effects per 15s, on clicks, sends, marks and the outro only. Write
   `work/<name>/events.json` (see `SKILL/templates/events.example.json`), then `M sfx
   work/<name>/events.json <dur> work/<name> --samples sfx` (add `--music calm|energetic` only for
   a draft bed when there's no track). Vary the music between videos.
10. **Render + mix.** In `studio/`: `npx remotion render src/index.ts <Id>-<format>
   ../work/<name>/<format>.mp4`. Then `M mix work/<name>/<format>.mp4 output/<name>_<format>.mp4
   --music music/<track>.wav --sfx work/<name>/sfx.wav` (music-led: music −20, SFX −22,
   two-pass loudnorm to −14 LUFS, video re-encoded to yuv420p bt709). Add `--voice vo.wav` if
   there's a voiceover; the music ducks under it. `M qa output/<name>_<format>.mp4` to confirm.
11. **Deliver.** `output/<name>_<format>.mp4` per format, a poster frame (`npx remotion still …
   --frame=<best>` → `output/<name>_poster.png`), a contact sheet (`M sheet`), and a short note:
   what's in it, what to confirm, and the next improvement.

## Hard rules
- **Never design from scratch.** Every product screen comes from the user's Figma (MCP or a link
  to the exact frame), their `demos/` recordings, or a capture of the live product. No invented
  layouts, components, illustrations or "inspired by" mockups. If a scene has no source, stop and
  ask which frame or recording shows it.
- **No slop.** Banned: sparkles ✨ and star bursts, emoji, glowing orbs and blobs, AI-picked icons,
  stock "magic" gradients, robot or brain imagery for AI, lens flares. **No icons at all** unless
  they come from the user's Figma or icon set, used exactly as supplied. Typography, real UI and
  motion carry the film. Check every critique round for these and cut anything that slipped in.
- **Story arc:** problem → solution → demo → CTA, every film. No feature lists without a problem.
- **Use the real screens, never redraw the product.** Export Figma frames at 2× (or capture the
  live product at 2×), crop cards and regions in code with `Crop`, and animate on top: live text
  typed into real inputs (covering the placeholder), selection states redrawn exactly over the real
  options, presses and cursor clicks on real buttons. Rebuilt "lookalike" UI reads as AI slop.
  Never invent screens or features.
- Keep out of shot: personal data, real customers' details, and screens with outdated branding.
  Typed demo values use neutral, fictional data.
- **Copying a reference's storyboard**: same beats, same timing, same scale and motion. Swap in
  the brand's own content, and end on the brand's own outro.
- Pure function of time: no timers, no CSS transitions, no `Math.random` (use `rng`)
- One display face + one UI face (from the design), one accent colour
- Jitter goes on type, stickers and transitions; body UI text stays crisp and steady
- Banned: centred title on a gradient as the main idea, everything fading in, corner labels or
  frame borders, glows on UI chrome, generic particle bursts
- Don't copy reference pieces' logos, characters or footage. Copy the grammar.
