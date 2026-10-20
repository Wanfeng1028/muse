# product-launch-film

An agent skill for making **short, code-rendered launch films for software products** (30-60 s, 1080p60),
built in Remotion from the real product: real CLI output, rebuilt real UI, a conversational
ElevenLabs narration, original music/SFX, and a -16 LUFS master. The method and the lessons come from
real projects (Connectra v1→v4, Heli-Harness v1→v2), including the feedback that shaped them: dark themes
read as AI slop, dense frames get rejected, and the story is the daily pain removed, not the most
technical feature.

It works with any agent that reads `SKILL.md` skills (Claude Code, Codex, Cursor, and others).

**Example output:** the [Heli-Harness launch film](https://github.com/KJ-AIML/heli-harness/releases/download/v0.10.4/heli-harness-launch.mp4)
(57 s, MP4), made with this skill. See its concept doc in [`references/heli/concept-v2.md`](references/heli/concept-v2.md).

## What's inside

```
SKILL.md                     the method: research → story → capture → look → build → sound → review
references/
  checklist.md               anti-slop + review checklist (run before every delivery)
  case-studies.md            Connectra v1→v4 and Heli v1→v2 feedback loops
  heli/                      concept docs v1/v2, narration scripts, on-screen copy, layout checker
  connectra/                 concept notes (v1-v4), narration scripts v3/v4, copy, fleet overlap checker
templates/remotion-starter/  pinned Remotion 4.0.530 project: theme/palette, copy, timeline, layout,
                             one example scene, Root, stills/audit, layout + contrast checkers,
                             VO tools (ElevenLabs TTS + STT check, prosody, cleanup), music/SFX synth,
                             loudness master
```

## Install as a skill

Copy the whole folder (or symlink it) so that `SKILL.md` sits at `<skills-dir>/product-launch-film/SKILL.md`:

```bash
git clone https://github.com/KJ-AIML/product-launch-film.git ~/src/product-launch-film

# Claude Code (user-level)
mkdir -p ~/.claude/skills && ln -s ~/src/product-launch-film ~/.claude/skills/product-launch-film

# Codex / Cursor / other Agent Skills tools (user-level, vendor-neutral)
mkdir -p ~/.agents/skills && cp -R ~/src/product-launch-film ~/.agents/skills/product-launch-film

# Or per project (committed with the repo)
mkdir -p .agents/skills && cp -R ~/src/product-launch-film .agents/skills/product-launch-film
```

Other places tools look: `~/.codex/skills/` (Codex), and `.cursor/skills/` / `~/.cursor/skills/` (Cursor;
it also reads `.claude/skills` and `.codex/skills`). Some tools ignore symlinks. If the skill doesn't show
up, copy instead of linking and restart the agent session.

## Quick start

Ask your agent something like *"make a 50-second launch film for this repo"*; the skill triggers on that.
Or start by hand:

```bash
cp -R ~/src/product-launch-film/templates/remotion-starter ./launch-film
cd launch-film
npm install
npm run studio            # preview
npm run check             # typecheck + layout geometry + WCAG AA contrast
npm run stills && npm run audit
npm run render            # -> out/film.mp4 (PNG frames → h264 yuv420p, AAC, mastered to -16 LUFS)
```

Then follow `SKILL.md`: read the product, write the tagline, capture real output in a sandbox, fill
`docs/concept.md`, build one scene per beat, add narration and music, and review with
`references/checklist.md`.

Requirements: Node ≥ 22.18, and network access at render time (Google Fonts, plus a one-time Chrome
Headless Shell download). For narration: an ElevenLabs API key in `ELEVENLABS_API_KEY`, kept in the
environment and never committed, plus a full `ffmpeg` for VO cleanup. For the music synth: Python 3 with numpy.

## Design rules: Jakub Krehel's skills

The visual polish rules (concentric radii, shadow rings over borders, one primary action, spacing over
dividers, contrast, typography) come from Jakub Krehel's UI skills. They are **not vendored** here.
Install them from the source:

- https://jakub.kr/skills
- https://github.com/jakubkrehel/skills

## Licences

This repo is MIT (see `LICENSE`). Things you bring in have their own terms. Remotion is free for
individuals and companies of up to 3 people; larger companies need a company licence
(https://remotion.dev/license). Free-tier ElevenLabs voices require attribution and are not licensed for
commercial use. Google Fonts are mostly SIL OFL.

The files under `references/heli` and `references/connectra` are worked examples from those projects.
They are included for method, not as reusable brand assets.
