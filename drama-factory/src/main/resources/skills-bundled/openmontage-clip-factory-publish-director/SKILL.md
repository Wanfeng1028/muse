---
name: openmontage-clip-factory-publish-director
version: "1.0.0"
description: 剪辑工厂的发布导演技能，负责把片段批量打包为可落地的分发方案，按排序安排发布节奏、为每个平台定制文案，并保留片段目录与投放意图，适用于短视频批量投放与内容引擎搭建。
metadata:
  license: AGPL-3.0
---

# 发布导演 — 剪辑工厂流水线

## 适用场景

本阶段把片段批量打包成一份分发方案。目标不只是导出文件，而是搭出一个能持续运转的内容引擎。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/publish_log.schema.json` | 产出物校验 |
| 前置产出物 | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 输出结果、排序、目标 |
| Playbook | 当前生效的风格 playbook | 品牌调性 |

## 流程

### 1. 用最强片段打头阵

不要按时间顺序排期，要按排序排期。

首发片段通常应当是：

- 最强的钩子
- 最干净、最能独立成立的片段
- 与本批次目标最契合的片段

### 2. 按平台定制文案

每个平台都需要自己的语气与包装方式：

- TikTok / Reels：直接、快、钩子先行
- Shorts：可检索、贴合关键词
- LinkedIn：洞察导向、更职业化
- X：短促有力、便于表达观点

### 3. 把批量打包干净

按平台分组，并附上可直接粘贴的文字素材，而不仅仅是视频文件。

### 4. 保留批次真实信息

在 `publish_log.metadata` 中存储：

- `clip_catalog`
- `posting_order`
- `platform_copy_map`
- `schedule_notes`

### 5. 质量门

- 最强片段是否领先于整个投放节奏
- 文案是否为每个平台单独定制
- 导出文件夹是否无需额外整理即可使用
- 批次目录是否清晰地把排序、文件路径、发布意图关联起来

## 常见陷阱

- 把整批片段安排在同一天发。
- 所有平台共用一条文案。
- 渲染完成后丢失了排序/先后逻辑。

---

## 质量门提醒（强制）

本阶段需经人工审批（`human_approval_default: true`）。评审通过后：用 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产出物），然后**结束本轮**。不得在同一回复里启动下一阶段。审批按门独立生效——此前的“继续”不代表本门已通过。
