---
name: openmontage-hybrid-edit-director
version: "1.0.0"
description: 混合剪辑流水线的分层剪辑设计环节，负责为以原始素材为主、支撑元素为辅的视频制定剪辑逻辑，适用于需要先锁定锚点剪辑再逐层叠加辅助内容的项目。
metadata:
  license: AGPL-3.0
---

# 剪辑统筹（混合流水线）

## 适用时机

本环节为"原始素材为主、支撑元素为辅"的视频设计分层剪辑逻辑。顺序至关重要：先锁定锚点剪辑，再叠加支撑层。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | 校验产物合法性 |
| 上游产物 | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 原始与支撑素材、时间线意图 |
| Playbook | 当前启用的风格手册 | 字体与动效一致性 |

## 流程

### 1. 先锁定锚点剪辑

观众应当在支撑叠加出现之前就能看懂故事。锚点剪辑本身不成立的话，再多的支撑层也救不回来。

### 2. 按优先级顺序叠加支撑

典型顺序：

1. 字幕；
2. 说话人或上下文标签；
3. 图示或数据卡片；
4. 可选插片；
5. CTA 元素。

### 3. 保护可读性

同一时刻不要堆叠过多支撑层。若字幕、标签、图表与叠加互相打架，就做减法。

### 4. 用元数据记录分层逻辑

推荐的元数据键：

- `anchor_cut_notes`
- `layer_order`
- `overlay_windows`
- `variant_edit_rules`

### 5. 质量门

- 锚点剪辑单独成立；
- 支撑层起到澄清作用而非干扰；
- 移动端可读性过关；
- 各变体保持一致。

## 常见陷阱

- 试图用额外图形去补救一个本就不成立的剪辑。
- 让支撑层与原片抢戏。
- 把每个平台变体做成一套独立的剪辑哲学。
