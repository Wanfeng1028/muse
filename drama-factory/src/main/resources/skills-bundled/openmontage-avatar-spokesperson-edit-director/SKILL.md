---
name: openmontage-avatar-spokesperson-edit-director
version: "1.0.0"
description: 把数字人口播的计划场景与素材剪辑成连贯时间线，保证播报节奏稳、辅助层可读、CTA 落点清晰，适用于口播视频的剪辑决策阶段。
metadata:
  license: AGPL-3.0
---

# Edit Director - Avatar Spokesperson Pipeline

## When To Use

Turn the planned presenter scenes and produced assets into a coherent spokesperson timeline. The quality bar is steady delivery, readable support layers, and a clear CTA landing.

## Process

### 1. Cut The Presenter Track First

Assemble the core spokesperson performance before adding support layers. If the presenter cut is weak, extra graphics will not rescue it.

### 2. Add Support Layers Sparingly

Use overlays only where they help:

- short proof points,
- product names,
- pricing or feature cards,
- CTA reinforcement,
- subtitles.

### 3. Respect Spoken Rhythm

Keep pauses where they help emphasis. Do not trim so tightly that the avatar feels rushed or robotic.

### 4. Plan Deliverables Clearly

Recommended metadata keys:

- `hero_cut_order`
- `cta_frame_range`
- `overlay_timing_map`
- `variant_decisions`

### 5. Quality Gate

- the presenter remains the anchor,
- overlays are timed cleanly,
- scene transitions are calm and intentional,
- the CTA lands once and clearly.

## Common Pitfalls

- Overcutting to simulate energy.
- Letting captions, side panels, and lower thirds compete for the same area.
- Ending without a clean CTA hold.
