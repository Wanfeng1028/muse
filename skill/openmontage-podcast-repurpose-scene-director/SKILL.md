---
name: openmontage-podcast-repurpose-scene-director
version: "1.0.0"
description: 播客二次创作流水线中的场景导演技能，根据真实素材类型为每个交付物决定视觉处理方案，避免虚假丰富度，适用于规划分镜、布局与安全区。
metadata:
  license: AGPL-3.0
---

# 场景导演 · 播客二次创作流水线

## 何时使用

当需要依据素材的真实来源，决定每一份播客衍生交付物应该长什么样时，启用本技能。此阶段的核心职责是杜绝"假装丰富"，只选择诚实且有效的呈现方式。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | 校验产物结构 |
| 上游产物 | `state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 提供高光集合与素材真实信息 |
| 工具 | `frame_sampler` | 视频播客素材可选做画面抽检 |
| 手册 | 当前启用的风格手册 | 保持品牌一致性 |

## 流程

### 1. 为每个交付物选择匹配的处理方式

遵循"忠于来源"的优先级：

- 若存在视频播客素材，优先采用出镜人物主导的镜头；
- 若仅有音频，则采用声波图或引言卡布局；
- 若品牌资产有限，就让视觉系统保持简单、可复用。

```bash
# 抽检视频素材的画面，确认可用镜头
frame_sampler --input source_video.mp4 --interval 30 --output frames/
```
说明：按固定时间间隔抽取画面帧，便于判断镜头质量与人物构图。

### 2. 拒绝虚假复杂度

除非预算与工具确实支持，否则不要为一整集规划大量生成的选题美术。一个干净、带品牌的陪伴式版式，胜过噪声多却力不从心的伪制作。

### 3. 定义场景家族

可用的场景类型：

- `talking_head`：来源视频中的说话人镜头
- `text_card`：引言卡与章节卡
- `generated`：可选的选题美术
- `diagram`：少数需要图示说明的讨论
- `transition`：章节之间的转场

```json
{
  "scene_type": "text_card",
  "purpose": "quote",
  "layout": "speaker_attributed_quote"
}
```
说明：以结构化字段声明场景类型与用途，便于后续渲染阶段消费。

### 4. 用元数据承载布局策略

建议在 `scene_plan.metadata` 中使用的键：

- `deliverable_layouts`
- `speaker_card_rules`
- `quote_card_rules`
- `audiogram_rules`
- `full_episode_companion_rules`

### 5. 规划安全区与署名

每一种布局都必须清晰保留：

- 说话人署名
- 字幕区域
- 节目品牌元素
- 必要时的 CTA 或集数引用区域

### 6. 质量门

- 每个交付物的处理方式与真实素材匹配；
- 存在源视频时应使用视频，而不是藏在通用图形后面；
- 纯音频素材的视觉保持简单可读；
- 长版陪伴式视觉在可达成范围内。

## 常见陷阱

- 为纯音频节目规划以说话人镜头为中心的布局。
- 把每一段切片都做成同样的"波形加 logo"构图。
- 用生成图形去掩盖薄弱的编辑决策。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，展示摘要（Backlot 面板会渲染产物），
并**结束本轮回复**。不要在同一次回复里启动下一阶段。
审批按门独立生效——早先的"可以继续"不覆盖当前这道门。
