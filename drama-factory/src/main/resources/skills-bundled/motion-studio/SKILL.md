---
name: motion-studio
description: Make motion-graphics films in code, from short reels, promos, article trailers and launch films to long narrated YouTube explainers with rigged human figures, with a live scrub-and-annotate preview, licensed music cut to the beat, recorded foley, and a blind-read gate that proves the film still makes its source's point. Use whenever the user wants to turn an article, essay, newsletter or Substack post, inbox or notes digest, idea, product or brand into an animated video, reel, short, teaser, trailer or motion graphic; when they ask to preview, iterate on, re-time, re-score, review or fix a film made this way; or say things like "make this into a video", "animate this", "motion design", "storyboard this", "Remotion-style video", "make a YouTube explainer", "narrated video", "upload to YouTube". Not for editing camera footage or screen recordings.
---

# motion-studio

Films are one HTML file where every style is a pure function of time (`window.seek(t)`), rendered frame by frame in headless Chrome and encoded with ffmpeg. The skill adds the craft around that: a thesis contract, music measured and cut on bars, recorded sound on measured peaks, a live preview the user can annotate, and a blind read before anything ships.

## Non-negotiables (each one cost a film to learn)

- **The source's point survives.** Write the thesis and its argument chain at the top of the storyboard; every cut answers to it. One film was beautiful and had lost its article's argument through cuts that were each reasonable alone.
- **The blind read is the ship gate.** A reader who never saw the source states the thesis from stills and on-screen text. If it doesn't match the contract, the film isn't done.
- **Recorded, licensed sound only.** A real track cut on its bars, real foley on measured peaks. No synthesized beeps.
- **Variety by construction.** Read the film ledger first; don't reuse the previous film's signature move, track or sound palette.
- **Every frame is a pure function of t.** No CSS transitions, timers or state between frames; that is what makes stills, motion blur and scrubbing possible.

## Setup

`S=${CLAUDE_SKILL_DIR}/scripts/studio.py`. Run `python3 $S config` first: it prints the films folder, audio library, ledger and house-notes paths from `~/.motion-studio.json` (and creates the ledger if missing). **If a house-notes file exists, read it before anything else**: it carries the owner's style, standing rules, gates, and which models play reviewer. Needs Python 3.10+ with `playwright numpy scipy`, Google Chrome, and ffmpeg.

## Commands

| Step | Command |
|---|---|
| scaffold | `python3 $S new <slug> [--format 4x5\|9x16\|16x9] --bpm <exact catalog bpm> --bars <n> --title "..."` |
| stills | `python3 $S stills <film> --bars` (one per bar, at 0.72 of it) or `python3 $S stills <film> 12.4 12.45 12.5` |
| preview | `python3 $S serve <film> --launch`, then the Browser pane's `preview_start` with name `motion-studio` |
| notes | `python3 $S notes <film>` · close one: `--resolve 3 --reply "slowed the push to 0.7x"` |
| music | `python3 $S library` (bpm, duration, sections) · `search music house` · `fetch music <id>` (also measures) · `measure mixkit-<id>` |
| sfx | `python3 $S search sfx footsteps` · `fetch sfx <id>` · `fetch kenney impact-sounds` |
| sound | edit the film's `sound.py`, then `python3 $S mix <film>` |
| renders | `python3 $S draft <film>` (half-res, fast) · `python3 $S final <film>` (motion blur, muxes the mix, runs verify) |
| checks | `python3 $S verify <film>` · `python3 $S blindpack <film>` (`--redo` rebuilds the latest round if no reader has seen it) |

## Workflow

1. **Config, house notes, ledger, source.** Read the source in full (fetch articles; read every inbox item) and save it under the film's `sources/`.
2. **Contract.** Fill the top of `storyboard.md`: thesis, argument chain, screen/time budget, "about X, not Y". → `references/contract-and-story.md`
3. **Three variants, pick one.** Beat sheets for three different structures; pick and say why in one line (ask the user only if they're steering live).
4. **Music first.** `library`/`search`/`fetch`; choose a track whose sections fit the chain (drop on the turn, breakdown under the quiet part, return on the punchline). The film runs at the track's catalog bpm, exactly (e.g. 129.999). → `references/sound.md`
5. **Scaffold and build.** `new`, then `film.html` with the kit: one `K.scene()` per chain step, captions from the source's own words, in-scene text registered with `K.label()`. → `references/motion-vocabulary.md`, `references/formats.md`
6. **Stills before motion.** `stills --bars`, look; then 0.05 s stills around every transition. Fix before rendering anything long. → `references/review.md`
7. **Preview with the user.** `serve --launch` + `preview_start`. They scrub, play with sound and pin notes; read `notes`, fix, `--resolve` each with what changed. The page hot-reloads.
8. **Sound.** Write `sound.py` (music segments, beds, cues on the picture's events), then `mix`.
9. **Draft, then final.** `draft` and read its per-beat contact sheet; `final` must pass verify.
10. **Blind read.** `blindpack`, dispatch one or two fresh readers who see only the packet, compare their thesis to the contract, fix what they couldn't read, repeat with a new packet and new readers. → `references/panel.md`
11. **Panel on request** (or a first cut of a new kind of film): a motion-design reviewer, a creative-director reviewer and an advisor. → `references/panel.md`
12. **Deliver.** Send the final file to the user; append the ledger row; record "as built" and the blind-read verdicts in the storyboard. Don't post or publish anything: that's the user's call.

## Long-form narrated films (YouTube explainers)

When the film is narrated and longer than about a minute, use `scripts/longform.py` instead of `studio.py new`: the narration sets the clock, scenes are built from `script.json` segments, beats land on spoken words, figures act scenes out, music is picked per chapter mood, and `check` measures dead air before anyone watches. The workflow, script format and scene types are in `references/longform.md`; figures in `references/figures.md`; the critic pass in `references/critic.md`. `longform.py share` builds a streaming page for sending a draft as a private artifact link. Uploads go through `scripts/youtube.py` and default to private; never publish publicly without the user's explicit go-ahead. Extra dependency for word timing: `pip install pocketsphinx`.

To pick topics, `scripts/trends.py` finds TikTok and YouTube videos that broke out against their own creator's median views, from free sources only. It picks topics; it never downloads footage. → `references/trends.md`

## Where things live

- The skill (read-only once installed): `scripts/` (studio.py, kit.js, figure.js, render.py, verify.py, preview.py + preview.html, audio.py, beats.py, longform.py, panelqa.py, gemini.py, align.py, youtube.py, trends.py), `assets/templates/`, `references/` (+ `references/prompts/`).
- Shared data (paths from `config`): the audio library with `catalog.json`, the film ledger, optional house notes.
- One folder per film: `film.html`, `kit.js` and `audio.py` (vendored copies, so films never break on a skill update), `storyboard.md`, `sound.py`, `sources/`, `review/`, `out/`, `notes.json`.

## When something breaks

`references/review.md` lists every trap hit so far (shell globbing, literal characters, clipped descenders, captions too wide, a preview that won't launch from an unattended session, and more). Check it before debugging from scratch.
