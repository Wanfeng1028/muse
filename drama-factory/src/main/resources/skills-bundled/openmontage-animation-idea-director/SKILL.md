---
name: openmontage-animation-idea-director
version: "1.0.0"
description: 动画管线创意总监技能，用于确定动画模式、视觉路径与复用策略并产出创意简报，适用于运动图形、动态字体、图解说明、数学可视化和插画动画等以设计运动为核心的视频项目。
metadata:
  license: AGPL-3.0
---

# 动画管线 · 创意总监

## 何时启用

当视频的主要内容依靠精心设计的运动来承载时，走这条管线：运动图形、动态排版、图解主导的讲解片、数学可视化、插画式动画都归此类。

若项目本质上仍以实拍素材为主、仅叠加少量动效，应改用 `hybrid` 管线，不要在这里处理。

## 参考输入

- `docs/animation-best-practices.md`
- `skills/creative/animation-pipeline.md`
- `skills/creative/storytelling.md`
- `skills/creative/ink-theater.md` —— 用于手绘**水墨涂鸦**类简报：角色自行绘制并表演，或冷面机关讲解片（依赖 Ink Theater 引擎与 Ink Puppet 动捕，命令 `/ink-art`）。会走路或跳舞的棍状/铅笔角色属于 `character-animation` 管线。

## 流程

### 1. 判定动画模式

从下列主模式中选定一个：

- `diagrammatic`（图解型）
- `motion_graphics`（运动图形）
- `kinetic_type`（动态字体）
- `math_animation`（数学动画）
- `illustrative`（插画型）
- `mixed_animation`（混合动画）

### 2. 尽早敲定视觉路径

明确由哪些工具承担主要产出：

- `diagram_gen`
- `math_animate`
- `code_snippet`
- `image_selector`
- `video_selector` 或某个具体的视频供应商工具
- 源方提供的现成美术素材

若所选模式依赖当前不可用的工具，必须立刻在简报元数据里写清楚。

### 3. 制定复用策略

如果每个镜头都从零设计，动画成本会迅速失控。需提前定义：

- 反复出现的视觉母题；
- 版式体系；
- 转场家族；
- 字体层级。

### 4. 撰写创意简报

建议使用的元数据键：

- `animation_mode`
- `visual_path`
- `narration_strategy`
- `reuse_strategy`
- `timing_style`
- `blocked_capabilities`

### 5. 质量闸门

- 动画模式已明确写出；
- 视觉路径在现有条件下可实现；
- 项目已为复用而设计；
- 简报对缺失的工具如实说明。

## 常见坑

- 把所有动画当成同一个笼统品类处理。
- 为每一个镜头都规划一次性定制的视觉。
- 把缺失的工具路径一直拖到素材阶段才暴露。

---

## 闸门提醒（强制）

本阶段以人工审批为闸门（`human_approval_default: true`）。评审通过后：
用 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染该产物），然后**结束本轮对话**。不要在同一个回复里启动下一阶段。审批是按闸门独立的——此前的“继续”不覆盖本次闸门。
