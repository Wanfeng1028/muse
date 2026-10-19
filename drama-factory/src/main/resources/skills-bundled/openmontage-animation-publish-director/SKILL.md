---
name: openmontage-animation-publish-director
version: "1.0.0"
description: 动画管线发布总监技能，负责按实际动画模式与视觉体系包装元数据、缩略图概念与平台版本，适用于成片渲染完成后的发布打包与多平台分发环节。
metadata:
  license: AGPL-3.0
---

# 动画管线 · 发布总监

## 何时启用

对动画成片进行打包，使元数据、缩略图概念和平台呈现方式都真实反映项目的视觉体系。

## 前置条件

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/publish_log.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]`、`state.artifacts["script"]["script"]` | 最终输出与主题框定 |
| 剧本 | 当前生效的风格剧本 | 视觉命名一致性 |

## 流程

### 1. 让包装匹配动画模式

示例：

- 图解密集的视频应呈现结构化、易读的包装；
- 动态排版作品应围绕强文案做包装；
- 插画式动画应围绕主视觉做包装。

### 2. 保留视觉体系的真实性

在 `publish_log.metadata` 中保存：

- `animation_mode`
- `hero_frame_notes`
- `thumbnail_concept`
- `platform_notes`

### 3. 质量闸门

- 元数据契合实际动画模式；
- 缩略图概念与最终视觉体系一致；
- 导出按用途和平台清晰标注；
- 打包结果无需额外手工处理即可使用。

## 常见坑

- 写与动画风格无关的通用元数据。
- 缩略图概念与最终画面脱节。
- 混用平台版本却不做清晰标注。

---

## 闸门提醒（强制）

本阶段以人工审批为闸门（`human_approval_default: true`）。评审通过后：
用 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染该产物），然后**结束本轮对话**。不要在同一个回复里启动下一阶段。审批是按闸门独立的——此前的“继续”不覆盖本次闸门。
