---
name: openmontage-character-animation-research-director
version: "1.0.0"
description: 角色动画流水线的研究导演技能，负责用真实参考与当下技法为角色动画计划奠定基础，适用于角色动画项目的参考分析与可行性调研阶段。
metadata:
  license: AGPL-3.0
---

# 角色动画流水线 · 研究导演

## 目标

用真实参考与当下技法为角色动画计划奠定基础。针对参考视频，从 `video_analysis_brief` 入手：内容、节奏、运动分类、关键帧、色彩与制作复杂度。

## 流程

1. 识别参考实际使用的是什么：
   - 骨架式本地动画
   - 逐帧传统动画
   - 视频生成
   - 静帧位移
   - 混合技法
2. 调研 3–5 个相关案例或技法。
3. 区分流水线可本地复现的部分，与需要人工绘制、视频生成或更大资产库的部分。
4. 记录可复用的动画原语：
   - 行走循环
   - 眨眼
   - 转头
   - 伸手
   - 扇翅
   - 挤压/拉伸
   - 镜头平移/视差
   - 粒子/天气

## 输出指引

`research_brief` 应包含：

- `character_animation_fit`：高/中/低
- `reference_motion_type`
- `required_character_actions`
- `rig_complexity`
- `manual_asset_risks`
- `local_runtime_candidates`

## 质量标准

当参考为手绘或逐帧动画时，必须明确指出。用户仍可选择本地骨架的灵感式风格，但提案不得暗示自动骨架能带来与传统动画完全一致的质量。
