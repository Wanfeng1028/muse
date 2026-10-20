# Film project template (video-director)

A minimal, product-neutral Remotion 4 project that a new film starts from: one shared composition rendered as
16:9 `Wide` (1920x1080) and 9:16 `Tall` (1080x1920), poster stills, word-synced captions, a seconds-based
timeline that drives picture, captions, SFX cues and the offline mix, and placeholder scenes (hook, body, end
card, poster) with honest placeholder copy.

Scripts referred to below live in three skills: `$VD` = `~/.claude/skills/video-director/scripts` (review, QA, masters),
`$SD` = `~/.claude/skills/sound-design/scripts` (music, foley, mix, loudness), `$VOICE` =
`~/.claude/skills/voice-direction/scripts` (record, gate and build voiceover). Run everything from this folder.

## Start a film

```bash
cp -R ~/.claude/skills/video-director/assets/project-template <product-repo>/video
cd <product-repo>/video && pnpm install
cp ~/.claude/skills/video-director/assets/CREATIVE.template.md CREATIVE.md   # brief to decision log
pnpm studio                                                                # one Studio, owned by the orchestrator
```

This folder is its own pnpm package (own `pnpm-workspace.yaml`, own lockfile). Inside a host app, keep it out of
the host's TypeScript and lint: add `"video"` to `exclude` in the host `tsconfig.json` and `video/**` to the
ESLint ignores. Add `/video/node_modules`, `/video/out` to the host `.gitignore` if it does not read this one.

Then, in order (the gates are in the skill's SKILL.md):

1. **Brand.** Replace `src/theme/tokens.ts` and `src/theme/fonts.ts` from the product's design source, and
   `src/components/BrandMark.tsx` with the real logo. Every placeholder value is marked.
2. **Script.** Write the lines in `src/data/vo.ts` (`SCRIPT`; delivery tags and phonetics in `SPOKEN`). With no
   recording yet, word timings are estimated at 2.6 words/s, so the whole film already times out and captions run.
3. **Grid.** Set `MUSIC` in `src/data/music.ts` from `$SD/music_analyze.py` (bpm, first downbeat, key, edit
   segments). The template ships with no track (`file: null`): the 120 BPM grid still paces the cut.
4. **Timeline.** Place lines and scenes in `src/data/timeline.ts` by name, anchoring key words to downbeats.
5. **Scenes.** One file per scene in `src/scenes/`, registered as a `<SceneSlot>` in `src/Main.tsx`.
6. **VO.** `pnpm script` writes `out/script.json`; record with `$VOICE/vo_record.py`, build with
   `$VOICE/vo_build.py picks.json --out public/audio/vo/<variant> --ts src/data/vo-<variant>.generated.ts`, then
   register the generated module in `GENERATED` in `src/data/vo.ts`.
7. **Sound.** `pnpm cues` (gap check included), then `uv run $SD/mix.py out/cues-main.json --out public/audio/mix-main.wav --json`
   (the report's `sfx_audibility` must pass: every event sound heard over voice and music).
8. **Review and masters.** `$VD/stills.py`, `$VD/strip.sh`, `$VD/render_masters.sh`, `$VD/qa_video.py`.

## How timing flows

```
src/data/music.ts   grid: bar(), beat(), phrase.p1 ...        src/data/vo.ts   SCRIPT + generated word timings
            \                                                   /
             +----> src/data/timeline.ts  timeline(variant) <--+
                    voStart (anchored to downbeats), voEnd(), wordAt(), scenes, diegetic, duration, checkGaps()
                         |                |                    |                        |
                   src/scenes/*     data/captions.ts      data/sfx.ts          Root.tsx (duration via
                   useTimeline()    pages from words      sfxCues(t)           calculateMetadata)
                   useTime()             |                    |
                         |          Captions.tsx      tools/export_cues.ts -> out/cues-<variant>.json
                         |                                      |
                         +----- Main.tsx  <--  public/audio/mix-<variant>.wav  <--  $SD/mix.py
```

- All times are **film seconds**. Refer to them by name (`t.wordAt("l03", "change")`, `phrase.p1`,
  `t.voEnd("l05")`), never by number. Scenes, captions, SFX and the mixer read the same object, so sound and
  picture cannot drift.
- `useTime()` returns film seconds even inside a scene `<Sequence>` (the slot passes its frame offset).
- **fps** is defined once in `src/data/fps.ts`. Root registers every composition with it; inside components read
  `fps` from `useVideoConfig()`; data helpers take it as a parameter defaulting to `FPS`.
- **Variants** (voices or languages) are listed in `VARIANTS`. Pick one with `--props='{"variant":"alt"}'` or in
  the Studio sidebar (Zod schema); Node tools read `VARIANT=alt`. Per-variant nudges go in `VARIANT_OVERRIDES`.
  Duration follows the variant's timeline.
- **Gap check**: consecutive spoken lines need at least 0.15 s between them, product sounds must sit inside a
  pause, nothing may run past the end. `pnpm cues` prints PASS/FAIL and exits 1 on failure.
- **Audio**: when `public/audio/mix-<variant>.wav` exists, Main plays only that file. Otherwise it plays a draft
  (music segments with an in-component duck, VO files and `public/sfx/<kind>.wav` that exist). Drafts are for
  previews; masters always use the offline mix (loudness, band-split ducking, peak-aligned SFX).

## Where things live

| Path | What |
|---|---|
| `src/Root.tsx` | `FORMATS` (Wide, Tall active; Square 1:1 and Feed 4:5 ready, flip `active`), one composition and one poster `<Still>` per format, duration from data |
| `src/Main.tsx` | Assembly: `<SceneSlot>` per scene (gated `<Sequence premountFor>`, seam on the content wrapper, background underneath), captions, poster on frame 0, audio |
| `src/data/` | `fps`, `music` (grid, segments), `vo` (script, variants, generated timings), `timeline`, `sfx`, `captions`, `types` |
| `src/lib/motion.ts` | `useTime`, spring presets (damping ratio >= 0.72 except opt-in `playful`), `sp`, `tw`, `twScale` (perceptual), `ease`, `seeded` |
| `src/lib/seam.ts` | Velocity-matched hard cut: exit accelerates out, entry starts at the same speed; one direction per film |
| `src/lib/beat.ts` | `beatKick`, `cameraPulse` (only with a track) |
| `src/lib/format.ts` | `useFormat()` (u = min(w,h)/1080, kind, safe insets) and `pick()` per format |
| `src/components/` | `Captions`, `KineticWords` (masked rise, 55 ms stagger), `KenBurns`, `Placeholder`, `BrandMark`, `DraftAudio` |
| `src/scenes/` | `Hook`, `Scene` (placeholder body), `EndCard`, `Poster` (frame 0 and the poster stills) |
| `tools/export_cues.ts` | Cue sheet for `mix.py` (contract: `$SD/lib_audio/cues_model.py`) plus the gap check |
| `tools/export_script.ts` | `out/script.json` for `vo_record.py` |
| `public/` | `audio/music/` (gitignored, licensed), `audio/vo/<variant>/`, `audio/mix-<variant>.wav` (gitignored), `sfx/`, `fonts/`, `img/` |

## Commands

```bash
pnpm studio                     # preview
pnpm typecheck                  # tsc --noEmit (src and tools)
pnpm compositions               # list compositions
pnpm cues                       # out/cues-main.json + gap check (VARIANT=alt pnpm cues for another variant)
pnpm script                     # out/script.json for vo_record.py
npx remotion still src/index.ts Wide out/review/hook.png --frame=45
npx remotion still src/index.ts PosterTall out/review/poster-tall.png
```

## Rules this template already follows

- Frame 0 is the poster: chat apps use it as the thumbnail. Keep its centre clear for the play button.
- Every format is re-laid out with `pick()`, never cropped. Tall keeps the bottom 18% for platform UI.
- No `Math.random`, no CSS transitions: everything is a function of the frame.
- Scene content rides the seam in from the cut frame (a carrier); its own entrances start after the seam settles
  or move in the seam's direction.
- Captions hide where kinetic type already says the same words (`captionHiddenSpans`).
- Placeholder copy is instructional, never fake product claims. Every on-screen number needs a source in
  `facts.md`.
