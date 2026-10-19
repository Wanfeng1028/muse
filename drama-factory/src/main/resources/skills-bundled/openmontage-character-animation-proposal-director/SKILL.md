---
name: openmontage-character-animation-proposal-director
version: "1.0.0"
description: 角色动画流水线的提案导演技能，负责向用户呈现角色动画概念方案，如实说明本地骨架动画、复用策略、成本与运行时选择，适用于角色动画项目立项与方案确认阶段。
metadata:
  license: AGPL-3.0
---

# 角色动画流水线 · 提案导演

## 目标

呈现角色动画概念方案，并且对**本地骨架动画**、**复用**、**成本**以及**运行时选择**保持诚实。

## 提案必备要素

每个方案选项必须包含：

- 角色与角色定位
- 视觉风格
- 动作复杂度
- 骨架复用策略
- 样片计划
- 音频架构
- 音乐计划
- 渲染运行时选项
- 成本估算
- 诚实的局限说明

## 运行时选择

推荐运行时之前，先阅读 `skills/meta/animation-runtime-selector.md`。

当 Remotion 与 HyperFrames 均可用时：

- **Remotion**：适合最终合成需要确定性的 React 渲染视频、字幕、音频、场景 JSON 与最终 MP4 治理的场景。
- **HyperFrames**：适合角色场景以 HTML/SVG/GSAP 为主、能受益于 Web 原生编写、lint、validate 与 registry 块的情形。
- **FFmpeg**：仅用于后处理。**不得**把 FFmpeg 选作角色表演的主运行时。

推荐其中一种之前，必须把 Remotion 与 HyperFrames 两者都呈现给用户。在决策日志中以 `render_runtime_selection` 记录考虑过的替代方案，包含接受或拒绝 `hyperframes` 的理由。锁定 `render_runtime` 前需等待用户批准。

## 样片优先规则

在全面投产之前，先提出一个 10–15 秒样片，其中包含：

- 一个主要角色
- 一次表情变化
- 一次身体动作
- 一种镜头或背景处理
- 一个音频/音乐提示（如相关）

该样片获批之前，不得批量生成全部资产。

## 成本诚实

本地骨架动画在渲染期便宜，但在编写复杂度上昂贵。需要分项报告：

- 资产生成成本
- TTS/音乐成本
- 本地渲染成本
- 人工复杂度风险

---

## 闸门提醒（强制）

本阶段以人工批准为闸门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不得在同一回复中启动下一阶段。批准是逐闸门生效的——早先的“可以继续”不覆盖本闸门。
