# openvids

openvids is an agent skill for making product-launch videos in the style of the Claude Code release videos: big type, a warm light and ink palette, one accent color, crisp UI recreations, and transitions that turn one object into the next. Your coding agent writes the film in [Remotion](https://www.remotion.dev), synthesizes the soundtrack in Python, and fans out the scenes, the sound, and the design passes to subagents.

![Poster frame from the example film](examples/droid-launch/poster.png)

The example in `examples/droid-launch` is a 75-second film about Factory's Droid. Eleven subagents built it, and it ends on a receipt that prints its own cost: 27.8M tokens and $36.16 at API list prices. Download the MP4 from the [v0.1.0 release](https://github.com/NDilanka/openvids/releases/tag/v0.1.0).

## Install

Clone the repo into your agent's skills directory.

```sh
# Droid (Factory)
git clone https://github.com/NDilanka/openvids ~/.factory/skills/openvids

# Claude Code
git clone https://github.com/NDilanka/openvids ~/.claude/skills/openvids
```

You need Node 24 or later, ffmpeg on your `PATH`, and Python 3.10 or later with `numpy` and `scipy`.

## Use

Ask your agent for a launch video:

```
Make a 60-second launch video for <product>. Clean, typographic, Claude Code launch style.
```

The agent follows `SKILL.md`:

1. It researches the facts and writes them to `FACTS.md` with sources.
2. It asks you for the length, aspect ratio, palette, and audio preferences.
3. It writes the storyboard and the timing contract (`src/timeline.ts` and `HANDOFF.md`).
4. It sends scene builders and a sound designer out in parallel.
5. An art director, polish designers, and a QA director refine the draft.
6. It renders and verifies the MP4 and gives you a caption for posting.

## What's inside

| Path | Contents |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `template/` | A brand-neutral Remotion starter with three demo scenes, the design system, and an example score |
| `audio/synth.py` | Sound primitives: keystrokes, modal bars, FM bells, glass, plucks, paper, printer, stamp, drone, reverb |
| `audio/render.py` | The score engine. It reads `timeline.json` and a score spec, then mixes, normalizes to -14 LUFS, and enforces silence windows |
| `scripts/` | `contact_sheet.py`, `check_boundaries.py`, `motion_scan.py`, `timeline_json.mjs`, `droid_usage.py` |
| `references/` | `storyboard.md`, `design-system.md`, `sound.md`, `briefs.md` (the subagent prompts) |
| `examples/droid-launch/` | The full source of the example film |

## How a film stays coherent

The scenes are built by different subagents in parallel, so the rules live in files that every subagent reads:

- `src/timeline.ts` fixes the frame of every visual event. The soundtrack reads the same cues through `public/timeline.json`, so the picture and the sound stay in sync.
- Each scene boundary is a shared component rendered with default props. The last frame of one scene and the first frame of the next are the same pixels. `scripts/check_boundaries.py` renders both and fails if they differ.
- `scripts/motion_scan.py` fails on any run of still frames longer than 12, except the holds you allow.

## Check a render

Run these from your film project. `<skillDir>` is where you cloned openvids.

```sh
python <skillDir>/scripts/contact_sheet.py out/film.mp4 out/sheets
python <skillDir>/scripts/check_boundaries.py .
python <skillDir>/scripts/motion_scan.py out/film.mp4 --allow <first>-<last>
```

## Run the template

```sh
cp -r ~/.factory/skills/openvids/template ~/my-film && cd ~/my-film
npm install
npm run timeline
python ~/.factory/skills/openvids/audio/render.py . audio/score.py
npm run render
```

## Notes

- `droid_usage.py` reads Droid session files from `~/.factory/sessions`. The prices in `scripts/prices.json` were list prices on 2026-10-04. Update them before you trust a cost.
- The rival bars in the example's benchmark scene carry no values, and their lengths are illustrative. Droid's 58.75% is from Factory's Terminal-Bench announcement of September 25, 2025. `references/storyboard.md` asks for a stricter rule in new films.
- `examples/droid-launch/audio/build.py` is the original one-off engine. `audio/scores/droid_launch.py` is the same score in the current format. Use `audio/render.py` for new films.
- The Factory logo and the Droid name in `examples/droid-launch` belong to Factory. They are here only to show a finished film. Replace them with your own brand.

## License

MIT
