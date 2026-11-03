---
name: openmontage-animation-edit-director
version: "1.0.0"
description: 动画管线的剪辑决策阶段，把场景规划转成达到动态分镜水准的剪辑方案，核心产出是时间设计。适用于需要为关键揭示留出停顿、为次级元素安排错位入场、并保证动效服务于层级的动画项目。
metadata:
  license: AGPL-3.0
---

# Edit Director - Animation Pipeline

## When To Use

This stage turns the scene plan into an animatic-grade edit plan. Timing is the product.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]`, `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]` | Assets, timing plan, and beats |
| Playbook | Active style playbook | Motion and typography rules |

## Process

### 1. Protect Hold Time

After key reveals, plan enough time for the viewer to process the frame. Do not stack every scene edge to edge with motion.

### 2. Stagger Secondary Elements

Primary element first, supporting elements second. The edit decisions should reinforce hierarchy.

### 3. Keep Motion Meaningful

Motion should signal:

- emphasis,
- transition,
- transformation,
- contrast.

### 4. Use Metadata For Timing Detail

Recommended metadata keys:

- `hold_windows`
- `stagger_rules`
- `transition_map`
- `scene_timing_notes`

### 5. Quality Gate

- key information has enough dwell time,
- movement clarifies hierarchy,
- transitions stay consistent,
- the edit remains readable on the target platform.

## Common Pitfalls

- Overcrowding the timeline with continuous motion.
- Revealing all elements at once.
- Letting stylistic motion reduce readability.
