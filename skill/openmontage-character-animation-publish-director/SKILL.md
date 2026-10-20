---
name: openmontage-character-animation-publish-director
version: "1.0.0"
description: 角色动画流水线的发布导演技能，负责为最终角色动画交付物打包诚实的元数据并设计以角色为主的封面缩略图概念，适用于角色动画成片发布与交付阶段。
metadata:
  license: AGPL-3.0
---

# Publish Director - Character Animation Pipeline

## Goal

Package the final character-animation deliverable with honest metadata and a
strong character-forward thumbnail concept.

## Requirements

- Mention the actual visual treatment: local rigged character animation,
  procedural effects, Remotion/HyperFrames render, or mixed.
- Pick a poster frame where the main character's emotion is readable.
- If the output is a sample, label it as a sample.
- If the final is inspired by a reference, describe the inspiration without
  claiming duplication.

## Output

Produce `publish_log` with:

- final video path,
- thumbnail/poster-frame notes,
- title ideas,
- description,
- platform-specific export notes,
- limitations or follow-up recommendations.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
