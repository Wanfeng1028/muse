---
name: openmontage-cinematic-edit-director
version: "1.0.0"
description: 将节拍图转化为有节奏的电影感时间线，以情绪和克制为核心；适用于预告片、品牌片等需要精确剪辑节奏的电影感项目。
metadata:
  license: AGPL-3.0
---

# 电影感流程 · 剪辑总监

## 何时启用

本阶段将节拍图转化为有节奏的电影感时间线。节奏和克制比特效数量更重要。

## 前置条件

| 层级 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 素材、主角帧、节拍图 |
| Playbook | 当前风格 playbook | 排版与转场一致性 |

## 流程

### 1. 先按情绪剪辑

剪切应遵循：

- 情感强调，
- 揭示时机，
- 音乐转折，
- 视觉对比。

不要仅针对信息密度优化。

### 2. 保护强力时刻

如果某个画面、台词或手势正在发挥作用，让它存在。不要用额外插入镜头过度覆盖它。

### 3. 用声音推动剪辑

氛围音、冲击音、静音和音乐变化应帮助在场景间创造动力。

### 4. 使用元数据记录时间逻辑

推荐元数据键：

- `beat_timing`
- `audio_turns`
- `title_card_windows`
- `reframe_notes`

### 5. 质量门禁

- 情感弧线完整，
- 揭示清晰落地，
- 标题卡稀疏且时机有意图，
- 强力时刻未被覆盖素材掩埋。

## 常见陷阱

- 过度剪辑情感素材。
- 默认使用速度斜坡或花哨转场。
- 让标题卡取代剪辑清晰度。
