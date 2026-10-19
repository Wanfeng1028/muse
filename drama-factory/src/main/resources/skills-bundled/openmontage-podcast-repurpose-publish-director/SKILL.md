---
name: openmontage-podcast-repurpose-publish-director
version: "1.0.0"
description: 播客二次创作的发布导演技能，负责为每条切片与伴随资产补齐回链节目的出处信息、按平台定制文案、安排发布顺序并写入交叉链接元数据，适用于播客衍生内容的发布打包阶段。
metadata:
  license: AGPL-3.0
---

# 发布导演 — 播客二次创作流水线

## 适用场景

把由播客衍生的切片与伴随资产打包妥当，让每一条短视频都指回原节目，而不是变成漂在外面的孤立碎片。

## 前置条件

| 层级 | 资源 | 作用 |
|------|------|------|
| Schema | `schemas/artifacts/publish_log.schema.json` | 交付物校验 |
| 上游交付物 | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 成片输出、源信息真相、章节 |
| 手册 | 当前启用的风格手册 | 品牌口吻 |

## 工作流程

### 1. 让每条切片都回链到节目

每个短视频资产都应当带上：

- 节目名称，
- 单集标题或期号，
- 相关情况下的嘉宾姓名，
- 完整节目的落地地址。

### 2. 按平台定制文案

- Shorts / Reels / TikTok：钩子先行、言简意赅
- LinkedIn：洞见先行、上下文更充分
- YouTube 伴随视频：章节丰富、利于搜索

### 3. 安排发布顺序

推荐次序：

1. 最强的那条预告型切片
2. 次强的洞见型切片
3. 金句主导或嘉宾主导的跟进内容
4. 其余支撑性切片

### 4. 把交叉链接的真相写进元数据

建议的元数据键：

- `episode_reference`
- `guest_tags`
- `posting_schedule`
- `clip_to_episode_map`

### 5. 质量闸门

- 每条切片都指回节目，
- 嘉宾署名正确，
- 文案与平台调性匹配，
- 发布顺序反映了切片的真实强弱。

## 常见陷阱

- 发布切片时不带清晰的节目出处。
- 当嘉宾受众很重要时，忘了打标签或提及嘉宾。
- 所有平台复用同一套字幕风格。

---

## 闸门提醒（具有约束力）

本阶段默认需要人工审批（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染该交付物），然后**结束本轮回复**。不要在同一次回复里启动下一阶段。审批是按闸门逐一进行的——早先某次“可以继续”不覆盖本闸门。
