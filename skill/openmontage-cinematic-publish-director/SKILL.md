---
name: openmontage-cinematic-publish-director
version: "1.0.0"
description: 对影视化成品及其衍生版本进行发布打包，区分主版本与各切条用途、撰写与基调匹配的元数据并保留剪辑真相，适用于预告片或品牌片交付前的发布准备。
metadata:
  license: AGPL-3.0
---

# 发布总监 — 影视化流水线

## 何时使用

打包影视化成品及各种切条，让主版本保持清晰、分发意图一目了然。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]`、`state.artifacts["script"]["script"]` | 最终输出与节拍图 |
| 手册 | 当前启用的风格手册 | 基调与命名一致性 |

## 流程

### 1. 区分主版本与衍生版本

典型交付物：

- 主预告片或品牌片；
- 先导切条；
- 社交切条；
- 海报帧或缩略图概念。

### 2. 元数据与基调对齐

包装应反映真实情绪：

- 戏剧化；
- 高级感；
- 神秘；
- 沉思；
- 紧迫。

### 3. 保留剪辑真相

在 `publish_log.metadata` 中记录：

- `hero_output`
- `derivative_outputs`
- `poster_frame_notes`
- `distribution_notes`

### 4. 质量门

- 主版本导出有明确标识；
- 衍生导出按用途标注；
- 元数据与基调相符；
- 打包结果无需手动清理即可使用。

## 常见坑

- 先导片与主片输出命名不清、混作一团。
- 元数据写得千篇一律，忽略情绪。
- 把各种切条视为可互换。

---

## 门禁提醒（约束）

本阶段以人工确认为门禁（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一轮回复里启动下一阶段。
门禁按次生效——此前的一次"继续"不覆盖本次门禁。
