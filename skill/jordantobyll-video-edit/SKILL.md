---
name: jordantobyll-video-edit
description: Edit talking-head video by stripping silences with a neural VAD pass, inserting a fast 3D "swivel" teaser near the start, and doing basic FFmpeg trims/splices/speed changes. Use when the user asks to remove dead air, create jump cuts, add a video teaser transition, or perform simple cutting/concatenation on a video file.
version: "1.0.0"
author: playhouse
license: MIT
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Video Edit (jordantobyll-video-edit)

## Purpose

This skill bundles three related command-line tools that together turn a raw
talking-head recording into a tight, polished clip:

1. **Silence removal** — detects speech with a neural voice-activity detector
   and cuts out everything else, producing automatic jump cuts.
2. **3D swivel teaser** — splices a short, sped-up, rotating preview of the
   later part of the video into the opening seconds, while the original audio
   keeps playing underneath.
3. **Basic editing** — a general-purpose FFmpeg helper for trimming,
   concatenating, and adjusting playback speed.

Each tool is a standalone Python script that shells out to `ffmpeg`/`ffprobe`.
They can be chained or used independently.

## Scripts

| Script | Role |
|--------|------|
| `scripts/jump_cut_vad_singlepass.py` | Voice-activity silence removal in a single encoding pass |
| `scripts/insert_3d_transition.py` | Insert the rotating "swivel" teaser at a chosen timestamp |
| `scripts/simple_video_edit.py` | Trim / concat / change speed with FFmpeg |

## Quick Start

```bash
# 1. Strip silences
python3 scripts/jump_cut_vad_singlepass.py input.mp4 .tmp/edited.mp4

# 2. Insert the 3D swivel teaser
python3 scripts/insert_3d_transition.py .tmp/edited.mp4 output.mp4 --bg-image .tmp/bg.png

# Chained
python3 scripts/jump_cut_vad_singlepass.py input.mp4 .tmp/edited.mp4 \
  && python3 scripts/insert_3d_transition.py .tmp/edited.mp4 output.mp4 --bg-image .tmp/bg.png
```

## Tool 1 — Jump Cut via VAD (`jump_cut_vad_singlepass.py`)

### What it does

1. Pulls the audio track out of the input as 16 kHz mono WAV.
2. Runs the Silero neural VAD over that WAV to get speech spans.
3. Post-processes those spans: merges nearby ones, pads them, and
   optionally forces the first span to begin at 0:00.
4. Builds one `filter_complex` graph that trims every kept span and
   concatenates them in a single FFmpeg pass (no per-segment files).
5. Encodes H.265. On macOS the hardware encoder `hevc_videotoolbox` is used
   at 17 Mbps / 30 fps; otherwise `libx265` at CRF 18. Audio is AAC 192 kbps,
   and the `hvc1` tag is set so QuickTime plays the result.

### CLI

| Flag | Default | Meaning |
|------|---------|---------|
| `--min-silence` | 0.5 | Minimum silence length (s) the VAD must see before a cut is made |
| `--min-speech` | 0.25 | Minimum speech span (s) kept by the VAD |
| `--padding` | 100 | Milliseconds of padding retained around each speech span |
| `--merge-gap` | 0.3 | Speech spans closer than this (s) get merged |
| `--keep-start` / `--no-keep-start` | keep | Force the first kept span to start at 0:00 |

### Typical tuning

- Cuts feel too tight → `--padding 200`
- Not enough removed → `--min-silence 1.0`
- Removing too much → `--min-speech 0.1`

## Tool 2 — 3D Swivel Teaser (`insert_3d_transition.py`)

### What it does

1. Reads the video's duration and geometry with `ffprobe`.
2. Computes the playback rate needed so that content from `--teaser-start`
   to the end fits inside `--duration` seconds. Rate is capped at 100×.
3. Extracts the frames for the teaser at 60 fps.
4. Renders them with the Remotion "Pan3D" composition (in the bundled
   `video_effects` project) which applies a rotating 3D swivel effect over
   a background image or solid color.
5. Splits the source video into `[0, insert_at]`, the teaser, and
   `[insert_at+duration, end]`, concatenates them, and re-attaches the
   original audio track.

### CLI

| Flag | Default | Meaning |
|------|---------|---------|
| `--insert-at` | 3 | Seconds into the video where the teaser is spliced in |
| `--duration` | 5 | Length of the teaser in seconds |
| `--teaser-start` | 60 | Source timestamp the teaser content is sampled from |
| `--bg-color` | `#2d3436` | Solid background color for the 3D stage |
| `--bg-image` | — | Background image to use instead of a solid color |

### Resulting timeline

```
Video: [0 → insert_at] [swivel teaser @ high speed] [insert_at+duration → end]
Audio: original audio runs continuously for the whole runtime
```

## Tool 3 — Basic Editing (`simple_video_edit.py`)

### What it does

Wraps common FFmpeg operations behind a simple CLI:

- `trim` — keep only `[start, end]`
- `concat` — join two or more files in order
- `speed` — change playback rate (audio is time-stretched to match)
- `trim-concat` — the combination operation used internally by tool 1

Output codec is chosen automatically: `h264_videotoolbox` on macOS with
`libx264` fallback, and `libx264` everywhere else. Audio is AAC.

### CLI

| Flag | Meaning |
|------|---------|
| `--op {trim,concat,speed,trim-concat}` | Which operation to perform |
| `--input FILE` | Primary input (for `concat`, repeatable) |
| `--output FILE` | Output path |
| `--start`, `--end` | Bounds for `trim` (seconds) |
| `--rate` | Playback multiplier for `speed` |
| `--segments` | JSON list of `[start, end]` pairs for `trim-concat` |

## Performance reference (≈49 min 4K source)

- VAD pass + encode: ~8 min
- Swivel teaser render: ~3 min
- Combined: ~11 min

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Cuts feel abrupt | Increase `--padding` |
| Not enough silence removed | Raise `--min-silence` |
| Speech being dropped | Lower `--min-speech` |
| QuickTime refuses to play | Verify `hvc1` tag is present (script sets it by default) |
| Swivel shows blank frames | Make sure enough frames were extracted — 5 s at 60 fps = 300 frames |

## Dependencies

```bash
pip install torch          # Silero VAD
pip install remotion       # only if you render the swivel locally (via npm)
brew install ffmpeg node   # macOS
cd video_effects && npm install
```

## Source notice

Functionality in this skill is inspired by
https://github.com/jordantobyll/video-editing-skills. The prose, scripts,
and structure here are an independent rewrite and are not copies of the
original repository's files.
