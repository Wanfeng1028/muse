---
name: openmontage-podcast-repurpose-publish-director
version: "1.0.0"
description: 播客二次创作的发布导演技能，负责为每条切片与伴随资产补齐回链节目的出处信息、按平台定制文案、安排发布顺序并写入交叉链接元数据，适用于播客衍生内容的发布打包阶段。
metadata:
  license: AGPL-3.0
---

# Publish Director - Podcast Repurpose Pipeline

## When To Use

Package podcast-derived clips and companion assets so that every short-form piece points back to the episode instead of drifting as an isolated fragment.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["compose"]["render_report"]`, `state.artifacts["idea"]["brief"]`, `state.artifacts["script"]["script"]` | Outputs, source truth, chapters |
| Playbook | Active style playbook | Brand voice |

## Process

### 1. Link Every Clip Back To The Episode

Each short-form asset should reference:

- show name,
- episode title or number,
- guest name where relevant,
- full episode destination.

### 2. Tailor The Copy

- Shorts / Reels / TikTok: hook-led and concise
- LinkedIn: insight-led and more contextual
- YouTube companion: chapter-rich and search-friendly

### 3. Sequence The Release

Recommended order:

1. strongest announcement clip
2. next-best insight clip
3. quote-led or guest-led follow-ups
4. remaining supporting clips

### 4. Store Cross-Linking Truth In Metadata

Recommended metadata keys:

- `episode_reference`
- `guest_tags`
- `posting_schedule`
- `clip_to_episode_map`

### 5. Quality Gate

- every clip points back to the episode,
- guest attribution is correct,
- copy matches the platform,
- the release order reflects actual clip strength.

## Common Pitfalls

- Publishing clips without clear episode references.
- Forgetting to tag or mention the guest when that audience matters.
- Reusing one caption style across every platform.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
