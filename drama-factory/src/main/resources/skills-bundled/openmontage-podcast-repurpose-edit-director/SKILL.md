---
name: openmontage-podcast-repurpose-edit-director
version: "1.0.0"
description: 播客再加工流水线的剪辑决策环节，为短视频切片与可选整集配套内容搭建时间线逻辑，音频始终是主体。适用于定义剪辑节奏、字幕与讲者呈现规则及金句停留时长的场景。
metadata:
  license: AGPL-3.0
---

# Edit Director - Podcast Repurpose Pipeline

## When To Use

This stage creates the actual timeline logic for short clips and any optional full-episode companion asset. The audio remains the primary content.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]`, `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]` | Assets, layouts, transcript timing |
| Playbook | Active style playbook | Motion and subtitle rules |

## Process

### 1. Build Clip Timelines Fast

For short-form clips:

- open on the hook,
- start captions immediately,
- make speaker attribution obvious,
- let the ending land cleanly.

### 2. Match The Edit To The Treatment

- source-video clips should emphasize speaker framing and reactions,
- audiogram clips should emphasize captions, speaker identity, and pacing,
- quote-led clips should preserve enough reading time after the line lands.

### 3. Keep Full-Episode Companion Simple

If producing one:

- use chapter cards,
- use limited recurring visual systems,
- do not force constant visual novelty if the assets are not there.

### 4. Use Metadata For Richer Timeline Notes

Recommended metadata keys:

- `clip_timelines`
- `quote_hold_times`
- `speaker_change_markers`
- `chapter_card_windows`

### 5. Quality Gate

- every short clip hooks quickly,
- captions and attribution are present,
- quote-led clips hold long enough to read,
- the long-form companion stays editorially honest and technically feasible.

## Common Pitfalls

- Building generic audiograms that ignore who is speaking.
- Ending quote clips as soon as the audio ends, before the text can be read.
- Turning a long-form companion into a weak imitation of a fully produced video podcast.
