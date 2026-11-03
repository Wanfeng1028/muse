---
name: rohanratwani-explainer-video
description: Make motion-design explainer videos (YouTube long-form 16:9, or Shorts 9:16) from a topic. Research brief with sources, narration written as beats, animated HTML + GSAP scenes rendered to MP4 with HyperFrames, optional AI voice (Kokoro, local and free) or the user's own voice, with every animation retimed to the voice. Use when the user asks for an explainer video, an animated explainer, a YouTube video or Short that explains a concept, or a video like the ones made with this skill.
---

# explainer-video-opus-5.5: explainer videos, timed to the voice

Every animation is keyed to a **beat** (one line of narration), never to raw seconds. Silent
builds time beats at reading pace; voiced builds use the measured voice clips, and every scene
stretches to fit. That one idea is what lets a video be rebuilt for a new voice without
touching a single animation.

## First run (once per machine)
1. Find or make a workspace (the folder where the user's videos live). If the current project
   has no `engine/core.mjs`, run `node <this skill's folder>/engine/init.mjs <workspace>`.
2. `node engine/doctor.mjs` from the workspace. Fix every MISS before going on. Voice items are
   optional: without them the video is built silent, timed at reading pace.
3. On Windows, HyperFrames needs Developer Mode on (or an admin shell) or video renders fail with
   `EPERM ... symlink`.

## Making an episode, in order. Stop at the two checkpoints.
1. **Research** (`reference/research.md`). Write `videos/<slug>/brief.md`: every claim that will be
   said or shown, one per row, with a source link. Anything made up for illustration goes under
   "Illustrative". Pick an angle the existing videos on the topic miss.
2. **Beats.** `node engine/new.mjs <slug>` copies the template. Replace its beats: one sentence or
   two per beat, grouped into chapters, each with a `v:` note of what is on screen. Write the
   last line first. Run `node build.mjs` and show the user `script.md`.
   **Checkpoint 1: the user approves the script before you build scenes.**
3. **Scenes** (`reference/scenes.md`). One `scene()` per idea, every tween at `T()`, `E()`, `F()` or
   `Wd()` of a beat. Rebuild, then `cd edit && npx --yes hyperframes lint` until 0 errors.
4. **Critique loop** (`reference/critique.md`). Snapshot the start and end of every beat, read the
   contact sheets, score, fix the worst three, repeat until everything scores 8+.
5. **Voice** (`reference/voice.md`): Kokoro, or the user reads `read-aloud.md` in one take.
   `node build.mjs --voice <name>` retimes everything. Re-run the critique loop on the voiced cut.
6. **Render + mix + check.** Render silent to a NEW filename, mix the voice, loudnorm to -14 LUFS,
   mux with `-c copy`. Check the file's timestamp, duration, and loudness.
   **Checkpoint 2: the user watches the render before anything is called done.**
7. **Package** (`reference/publish.md`): title, description with chapters, `captions.srt`, thumbnail.
   Never upload or post anything yourself. The user publishes.

## Rules that are not optional
- **Facts only from `brief.md`.** If it is not in the table, it is not in the video.
- **Never a blank frame.** The first frame of every beat already shows something; counters stay
  hidden until they start counting, or "0%" sits on screen looking like a fact.
- **Readable on a phone:** mono labels 1cqw (19px at 1080p) or larger, body text 1.3cqw or larger.
- **Writing:** short sentences, plain words, contractions fine. No em dashes on screen or in
  narration. Read every beat aloud in your head: if it sounds like a textbook, rewrite it.
- **Render to a new filename every time** (`-v2`, `-v3`). Overwriting a file that is open
  somewhere can fail silently on Windows while the CLI still exits 0.

## Formats
- 16:9 long-form: the default. The template and `examples/rag-vs-graphrag` show it.
- 9:16 Shorts: `reference/shorts.md`, example `examples/chatgpt-dots-short`.

## Files
- `engine/core.mjs`: beat timing (`timeBeats`), subtitles, page shell, chrome (chapter chip,
  progress rail, subtitles), motion helpers (`land rise fade exit draw type count`).
- `engine/tts.py`, `align.py`, `mix.py`, `loudnorm.py`: voice pipeline. `read-aloud.mjs`,
  `split-take.py`: the user's own voice.
- `templates/episode/`: the starting point (a short video, about 35 seconds, about this engine).
- `examples/`: three real episodes to copy patterns from (flow diagrams, knowledge graphs,
  counters, typed text, comparison cards, Shorts layout).
- `reference/`: research, scenes, critique, voice, shorts, publish.
