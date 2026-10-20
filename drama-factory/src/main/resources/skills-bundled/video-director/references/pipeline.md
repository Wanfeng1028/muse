# Pipeline: project structure, timing, builders, assets

Contents
1. Where the film lives
2. Project structure
3. The timeline is the single source of truth
4. Theme, motion and format libraries
5. Parallel building with sub-agents
6. Asset sourcing and licences
7. Multi-session state
8. Official Remotion file map

---

## 1. Where the film lives

- Inside the product repo as `video/`: its own pnpm package (own `pnpm-workspace.yaml`), excluded from the host app's
  tsconfig and lint, so the app's build never sees it. Start from `assets/project-template/`.
- Licensed music and renders stay out of git: `public/audio/music/` and `out/` are gitignored; the music URL and licence
  go in the README.
- `CREATIVE.md` (from `assets/CREATIVE.template.md`) holds the brief, script, storyboard, locked edit table, sound plan,
  quality bar and decision log. `README.md` holds rebuild-from-scratch commands, review tools, where things live, and the
  honesty and licence notes. `facts.md` holds every on-screen number with its source.
- Always work in a git branch or worktree for a new film.

## 2. Project structure

```
video/
  CREATIVE.md  README.md  facts.md
  remotion.config.ts          jpeg frames q95; angle GL renderer
  src/index.ts                registerRoot
  src/Root.tsx                one shared component registered per format (Wide, Tall, …); <Still> per poster;
                              duration computed from data; variant (voice, language) as a Zod input prop
  src/Main.tsx                assembly: each scene a SceneSlot (<Sequence premountFor> gated by its timeline span);
                              captions layer; poster on frame 0; public/audio/mix-<variant>.wav when present, draft
                              audio otherwise
  src/data/                   fps.ts (the one FPS), types.ts, music.ts, vo.ts (SCRIPT + generated timings), timeline.ts
                              (per-variant timeline, anchors, overrides, gap check), sfx.ts, captions.ts
  src/lib/                    motion.ts, seam.ts, beat.ts, format.ts, clock.tsx (useTimeline context), assets.ts
  src/theme/                  tokens.ts (from the product's design source), fonts.ts
  src/brand/                  the product's real components rebuilt for frame-driven animation
  src/components/             Captions, KineticWords, KenBurns, BrandMark, DraftAudio, …
  src/scenes/                 one file per scene; a folder for complex scenes; Poster.tsx
  public/                     audio/{music, vo/<variant>, mix-<variant>.wav}, sfx/, img/{raw, cut, check}, fonts/
  tools/                      export_cues.ts (cues.json for sound-design's mix.py), export_script.ts (script.json for voice-direction's vo_record.py)
  out/                        renders, review sheets, stems, cues.json (gitignored)
```

Start: `cp -R ~/.claude/skills/video-director/assets/project-template <repo>/video && cd <repo>/video && pnpm install &&
pnpm studio`. Before any recording, VO timings are estimated from the script at ~2.6 words/s, so the film is fully timed
and captioned from day one; `vo_build.py --ts src/data/vo.generated.ts` replaces the estimates line by line. Wide and
Tall are active; Square and 4:5 are defined in `FORMATS` and switched on when needed. The template's `README.md` explains
how timing flows from data to scenes, captions, cues and the mix.

The generic scripts live in the skill (`~/.claude/skills/video-director/scripts/`) and are called from the project root;
copy one into `tools/` only when the film needs a modified version.

## 3. The timeline is the single source of truth

- All timing lives in seconds in `src/data/`. Scenes, captions, the SFX cue export and the offline mixer read the same
  helpers, so picture and sound cannot drift. A separately hand-timed audio track always drifts.
- Refer to time by name, never by number: `wordAt("l03", "Respira")`, `phrase.p2`, `voEnd("l06")`.
- Anchor a key word to a downbeat: `voStart.l04 = phrase.p2 − wordStartInLine("l04", "Brand")`.
- Variants (voice, language) are override maps on top of the reference timing, selected by an input prop
  (`--props='{"voice":"b"}'`); Node tools read the same choice from an env var.
- An automated gap check: consecutive VO lines leave ≥ 0.15 s between them; in-product audio sits inside a pause.
- Absolute anchoring beats chaining: `<Series>` auto-chaining lets drift compound across a film.
- Clock by film type: music-led films take their length from the music edit (computed in data); voice-led explainers
  take scene lengths from the VO (`calculateMetadata` with the audio durations, or `ceil(audio + padding)`).
- One FPS constant shared by Root and every helper; components read fps from `useVideoConfig()`; scripts take `--fps`.
- Seconds → frames in one place (`toFrames(s) = Math.round(s * fps)`).

## 4. Theme, motion and format libraries

- `tokens.ts`: colours, type roles, radii, spacing, easings, spring presets. Never inline a hex value or an easing in a
  component. Replace the template's placeholders with tokens quoted from the product's design source.
- `fonts.ts`: load fonts before render (`delayRender` until the FontFace resolves, or `@remotion/google-fonts`).
- `motion.ts`: spring presets (ζ ≥ 0.72 by default; `motion.md` §3), clamped tweens in seconds, seeded random.
- `beat.ts`: beat kick and camera pulse from the music grid.
- `format.ts`: `useFormat()` returns the design unit `u = min(w, h) / 1080` and a `tall` flag; layouts reflow per format.
- `seam.ts`: velocity-matched exit and entry helpers (`motion.md` §8).
- Helpers that every builder would otherwise reinvent belong in core from day one: fit text to a box, colour mixing,
  keyframe tables, the cursor.

## 5. Parallel building with sub-agents

- The orchestrator builds the shared core first (timeline, tokens, motion lib, format helper, Main with placeholder
  scenes) and starts Studio. Only then does it fan out.
- Up to ~6 short scenes, building inline is faster than fanning out (measured 9 min vs 21 min). Beyond that, give each
  builder 2 to 3 scenes in one wave.
- Each builder owns its scene files only and never edits core files (timeline, theme, Main, tools); core changes go
  back to the orchestrator as requests. Brief with `assets/BUILDER_BRIEF.template.md`: workdir, owned files, preview
  command, acceptance bar with numbers, honesty rules, method (measure, build, verify with stills and strips, never
  claim a match without looking), report table.
- Each agent writes review output into its own `out/review/<agent>/`.
- Seam handoffs between scenes owned by different builders are written in the storyboard (exact position, scale,
  opacity, direction and speed at the cut).
- Audio can be its own agent from the start.
- One heavy render at a time on the machine (`render_masters.sh` takes a lock). Never run transcription or heavy ffmpeg
  jobs in parallel. Delete superseded renders; keep the current and previous ones.
- Typical pace: a 3-builder film with a side audio task took about 2 hours from brief to v2.
- Probe-render shared systems (camera states, icons, the motion lib) on one sheet before dispatching builders: one
  10-minute probe caught two errors that would have scrapped three groups' work. Any helper the brief names must exist in
  core (four builders once wrote four different versions of one helper). Defaults follow the rule, so style doesn't depend
  on whether a parameter was passed.
- One heavy job per agent (5 to 7 shots, or QC of one chapter). Agents that have read many images fail about 30% of the
  time on a second heavy job. Run parallel agents in waves of about 4. QC agents append findings as they go; check disk
  before re-dispatching a "dead" agent; spot-check self-reports against frames.
- Ambiguous feedback: confirm what it refers to first. If the wrong element changed, revert cleanly instead of patching on
  top. One change per commit. Break a reference film into a technique list with an adopt or drop decision per item.
- Record what you didn't do: every "this film doesn't do X" goes into the decision log with its reason, or into an
  "Unfinished" list with the blocker, so unfinished work is never reframed as a design choice.
- Rewrite on-screen copy after picture lock, against the final shots. Taglines name the feature and the concrete benefit,
  not an abstract metaphor.

## 6. Asset sourcing and licences

- **Real product first**: the product's own UI, voice, illustrations, logo and copy beat stand-ins.
- **Images**: Unsplash (its API can return 401; picsum.photos serves the same licence), Pexels by ID, 3dicons (CC0).
  Always build a contact sheet and look before using one.
- **Generated images**: the image-generation skill (locked style suffix, cast sheet, cutouts, review).
- **Generated video clips** (text/image-to-video models): expect artefacts in about a third of clips (logos, text, style
  drift), keep clips short (≤ 8 s), prompt per scene with a negative prompt, never trust their text.
- **Logos**: svgl.app API, simple-icons as fallback; trademark use only to refer, never to imply partnership.
- **Icons**: one real icon set (Phosphor, Lucide). No emoji, no empty placeholder squares.
- **Music and SFX**: the sound-design skill.
- **Fonts**: the product's own, shipped as files or Google Fonts.
- **Licence ledger** in the README: each music track and SFX source with its licence and URL, which people are generated,
  which assets are real product assets. Licensed music stays out of git.

## 7. Multi-session state

For films that span sessions, keep a `project.json` (or a section in CREATIVE.md) with the phase (planning → assets →
review → audio → editing → rendering → complete), per-scene status, open review issues and a session log. On resume,
reconcile it with what is on disk before continuing. Long-running jobs print progress lines so stuck work is visible.

## 8. Official Remotion file map

Skills live in `~/.claude/skills/`. Every file below (and every other Markdown file in the Remotion skills) is read in
full at Step 0 of `SKILL.md`, whatever the task. This table is a map for finding a topic again, not a reading list.

| Topic | File |
|---|---|
| New project or composition | `remotion-create/SKILL.md`, `video-layout.md`, `tailwind.md` |
| Markup rules, media components | `remotion-markup/SKILL.md` |
| Timing, easing, interpolate, spring | `remotion-markup/timing.md`, `timing-props.md`, `sequencing.md` |
| Multi-scene films | `remotion-markup/multi-scene-video.md`, `connected-compositions.md` |
| Transitions, overlays | `remotion-markup/transitions.md`, `light-leaks.md` |
| Effects, shaders, motion blur | `remotion-markup/effects.md`, `html-in-canvas.md`, `motion-blur.md` |
| 3D | `remotion-markup/3d.md` |
| Text highlights, measuring | `remotion-markup/text-highlights.md`, `measuring-text.md`, `measuring-dom-nodes.md` |
| Fonts | `remotion-markup/google-fonts.md`, `local-fonts.md` |
| Images, GIFs, Lottie | `remotion-markup/images.md`, `gifs.md`, `lottie.md` |
| Audio, voiceover, SFX, visualisation | `remotion-markup/audio.md`, `voiceover.md`, `sfx.md`, `audio-visualization.md` |
| Video embedding, editing, cropping | `remotion-markup/embedding-videos.md`, `video-editing.md`, `cropping.md` |
| Silence detection, FFmpeg | `remotion-markup/silence-detection.md`, `ffmpeg.md` |
| Duration and props from data | `remotion-markup/calculate-metadata.md`, `parameters.md`, `compositions.md` |
| Studio editing structure | `remotion-interactivity/SKILL.md` |
| Captions | `remotion-captions/SKILL.md`, `transcribe-captions.md`, `display-captions.md`, `import-srt-captions.md` |
| Rendering, transparent video | `remotion-render/SKILL.md`, `transparent-videos.md` |
| Studio | `remotion-studio/SKILL.md` |
| Maps | `remotion-maps/SKILL.md` |
| Player, Lambda, SaaS | `remotion-saas/SKILL.md` |
| Current docs lookup | `remotion-docs/SKILL.md` |
| Upgrading Remotion and the skills | `remotion-upgrade/SKILL.md` |

Install packages with `npx remotion add <pkg>` so versions match.
