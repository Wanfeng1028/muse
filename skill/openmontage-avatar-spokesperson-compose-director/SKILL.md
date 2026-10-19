---
name: openmontage-avatar-spokesperson-compose-director
version: "1.0.0"
description: 负责数字人口播流水线的最终渲染，把控播报形象稳定、语音清晰、字幕与辅助卡片不遮挡人物，适用于需要交付成品口播视频的合成阶段。
metadata:
  license: AGPL-3.0
---

# 合成总监 · 数字人口播流水线

## 适用时机

渲染最终的数字人口播成品。标准很朴素：播报形象稳定、语音清晰、字幕与辅助卡片不挤占画面。

## 运行时路由（硬约束 —— 仅限 Remotion）

第一阶段 HyperFrames 缺席。`edit_decisions.render_runtime` 必须是 `"remotion"`。本流水线依赖 Remotion 的 `TalkingHead` 合成与 `remotion_caption_burn`，两者在第一阶段都没有 HyperFrames 对等实现。

- 如果 `edit_decisions.render_runtime == "hyperframes"`，停下。回到创意阶段并说明约束。静默改写属于治理违规。
- 依据 AGENT_GUIDE.md 的"Present Both Composition Runtimes (HARD RULE)"：锁定 remotion 不等于可以跳过与用户的沟通。用户有权知道 HyperFrames 作为一个运行时的存在，以及为什么它不适用于数字人口播。记录一条 `render_runtime_selection` 决策，其中 hyperframes 的 `rejected_because: "TalkingHead + caption parity deferred on avatar-spokesperson"`。
- 将 `proposal_packet`/`brief` 传入 `video_compose.execute()`，用于工具内的运行时切换检测。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 校验渲染报告 |
| 上游产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 待渲染的内容 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`audio_enhance` | 渲染与音频收尾 |
| Playbook | 当前激活的风格手册 | 排版与布局规范 |

## 处理流程

### 1. 先渲染主片

优先产出一条有力的主版本，再考虑衍生版。合成内容：

- 播报视频；
- 字幕；
- 角标；
- CTA 卡片；
- 混音后的旁白。

### 2. 保持画面干净

字幕与 CTA 的位置在本流水线比花哨转场更重要。脸部与嘴部区域不能有任何遮挡。

### 3. 校验口型时机与音频

如果数字人走的是口型同步或音频驱动的说话头，需检查：

- 口型时机；
- 面部伪影；
- 长段落的漂移；
- 语音清晰度。

### 4. 逐一校验每份输出

重要发现记录在：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.variant_notes`

### 5. 质量门

- 输出文件有效；
- 语音清晰；
- 字幕保持可读；
- 播报形象视觉上稳定。

## 常见陷阱

- 让字幕盖住下巴或嘴部区域。
- 长时口型同步渲染不做抽样检查就交付。
- 衍生裁切版本把播报人物或 CTA 裁掉了。
