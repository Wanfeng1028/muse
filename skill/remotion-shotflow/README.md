**English** | [简体中文](README.zh-CN.md)

# ShotFlow for Remotion

Turn reference footage into clear motion: continuous objects, readable UI, and sound cues with traceable timing.

An installable Agent Skill with **8 shot recipes, 10 source references, and 3 local analysis tools** for product videos, interface animation, and focused shot studies. Skill instructions and reference notes are primarily in Chinese. This repository does not include a runnable Remotion app or a ready-made video template.

## What it covers

| Shot recipe | What it helps communicate |
|---|---|
| Gather and arrange cards | Bring several pieces of content into one workspace |
| Expand an input into a window | Turn a request into a complete interface |
| Move the camera for reading | Guide attention to the next detail and pause on the result |
| Connect and expand nodes | Grow one connection into a complete workflow |
| Carry geometry between shapes | Link states through a shared line, center, or direction |
| Expand a button to fill the frame | Use an interaction to enter the next scene |
| Isometric processing stations | Follow an object through several workflow stages |
| Rotate words in a fixed sentence | Present different capabilities within a stable structure |

The [shot library](references/shot-library.md) includes source observations, suitable uses, implementation suggestions, failure signs, and checks. The skill also covers shot planning, object identity, frame-based timing, sound evidence, and render review.

## Source references

The [reference catalog](references/reference-catalog.md) links to 10 original posts and records useful time ranges, written observations, and historical audio measurements. Follow a source link to inspect the shot you want to study.

**Original videos, screenshots, brand assets, music, full research caches, and authors' project files are not bundled.** No media download or research directory is required to use the recipes. For a precise reconstruction or a claim about a sound, inspect the material available for your current task.

The study records date from September 27, 2026; links and media versions may change. Visual time ranges locate a shot, rather than establish exact frame values. Signal peaks and periodicity estimates are candidates, not listening-confirmed beats or sound effects. The study did not confirm that the original works were made in Remotion. Use the methods with your own content and suitable assets.

## Install in Codex

The repository root is the skill directory; `SKILL.md` needs no extra nesting. For a user-level installation on macOS or Linux:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/JudgePeach/remotion-shotflow.git \
  "$HOME/.agents/skills/remotion-shotflow"
```

For a project-level installation, place the complete repository at `<project>/.agents/skills/remotion-shotflow/`. On Windows, use `.agents/skills/remotion-shotflow/` under your user directory. Check any existing installation first to avoid overwriting local edits or installing duplicate copies.

Codex supports user-level `~/.agents/skills` and project-level `.agents/skills`. New skills are normally discovered automatically; restart the client if the skill does not appear. See the [official skills documentation](https://learn.chatgpt.com/docs/build-skills). Other Agent Skills-compatible clients may use their own installation paths; they have not been individually verified here.

The written workflows need no Python or FFmpeg. When writing Remotion code, use the available official `remotion-best-practices` skill and your project's pinned Remotion version. This skill adds motion design guidance; official API rules remain authoritative.

## Try it

```text
Use $remotion-shotflow to make a 15-second introduction to my product UI.
Show “import content → organize automatically → review the result.”
Start with a preview in Remotion Studio.
```

```text
Use $remotion-shotflow to study 7.6–10 seconds of the Washu reference.
Give me a shot plan only: use my own four content cards to gather,
enter an input area, and settle into an orderly layout.
```

```text
Use $remotion-shotflow to check my local video and music.
Keep measured signal candidates, listening-confirmed beats,
and newly designed sound cues clearly distinguished.
```

You can request a plan, a single-shot study, or changes to an existing project. Preview video changes first; render or export the final video when explicitly requested. The [8-second shot plan](assets/shot-plan.example.md) and [cue sheet](assets/cue-sheet.example.json) are original practice examples. Their example sound files are not included.

## Optional local tools

The scripts read explicitly supplied local files and write to a specified output. They do not download media, upload data, install dependencies, or alter source media. FFmpeg input protocols are restricted to local `file,pipe`.

| Tool | Purpose | Dependencies |
|---|---|---|
| [sample_frames.py](scripts/sample_frames.py) | Sample the nearest decoded frame by actual PTS and build labeled contact sheets | Python, Pillow, FFmpeg / FFprobe |
| [analyze_audio.py](scripts/analyze_audio.py) | Check original channels, signal onsets, periodicity candidates, and timing origins | Python, NumPy, SciPy, FFmpeg / FFprobe; Matplotlib for plots |
| [compile_cues.py](scripts/compile_cues.py) | Map a sound's internal anchor to composition frames | Python standard library |

Use **Python 3.11+**. Install Python packages in a virtual environment. Install FFmpeg / FFprobe separately and make them available on `PATH`.

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Optional, for audio plots only
python -m pip install -r requirements-plot.txt
```

Run from the repository directory:

```bash
# Compile the example timing; this does not check or require sound files
python scripts/compile_cues.py \
  --input assets/cue-sheet.example.json --out output/cue-frames.json

# Sample a video you supply
python scripts/sample_frames.py \
  --input /path/to/reference.mp4 --out output/frames-01 \
  --start 1 --end 3 --step 0.2

# Generate audio candidates for subsequent listening and visual review
python scripts/analyze_audio.py \
  --input /path/to/reference.mp4 --out output/audio-01
```

Media tools require a new output directory; cue compilation refuses to overwrite an existing file by default. An audio analysis exit code of zero does not confirm beats: check the JSON `status`. Candidate cues are rejected by default; `--include-candidates` permits a draft while preserving their candidate status. Generated reports contain local input paths, so inspect metadata before sharing them.

See the guides for [frame sampling](references/frame-sampling-cli.md), [audio analysis](references/audio-analysis-cli.md), [sound synchronization](references/audio-sync.md), and [review](references/render-qa.md). The media tools read the complete input and are intended for short references. Plan segments and explicit time mappings before analyzing longer footage.

## Validation and contributions

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests generate their own media in temporary directories to check timing, channel state, candidate labels, input protection, and refusal to overwrite outputs. They do not download third-party footage. Media tests need the dependencies listed above and skip when those dependencies are unavailable. GitHub Actions is configured for Ubuntu with Python 3.11 and 3.13; check the Actions runs for actual results. Windows has not been validated.

Contributions are welcome: documented shot observations, small tool improvements, and clearer instructions. See [CONTRIBUTING.md](CONTRIBUTING.md) for evidence requirements and reproducible bug reports.

## License and attribution

The skill instructions, analysis scripts, and original examples in this repository are released under the [MIT License](LICENSE). Third-party works, trademarks, brand assets, audio, and separately installed dependencies retain their own rights and licenses; MIT does not grant rights to those materials. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for source and distribution details.

This is a community skill, with no official affiliation with Remotion, OpenAI, or the authors of the reference works.
