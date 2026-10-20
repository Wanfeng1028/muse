---
name: openmontage-character-animation-script-director
version: "1.0.0"
description: 将角色动画剧本写成可用姿态表演的节拍，而非单纯旁白，锁定音频架构并输出带元数据的 script 产物，适用于绑定角色动画的编剧阶段。
metadata:
  license: AGPL-3.0
---

# Script Director - Character Animation Pipeline

## Goal

Write scripts as performable animation beats, not just narration.

## Process

1. Lock audio architecture:
   - music-only,
   - narrator,
   - character dialogue,
   - narrator plus character sounds/dialogue.
2. Break the story into beats that can be acted with poses.
3. For each beat, state what changes visually:
   - emotion,
   - gaze,
   - body pose,
   - prop interaction,
   - camera,
   - environment.

## Writing Rules

- Prefer short visual beats with readable holds.
- Avoid action that needs many unique hand-drawn poses unless approved.
- Dialogue should be short enough for mouth-shape approximation.
- Silent/music-led scenes need stronger physical acting notes.

## Output Notes

In the `script` artifact metadata, include:

- `audio_architecture`,
- `character_beats`,
- `required_emotions`,
- `required_actions`.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
