---
name: openmontage-podcast-repurpose-idea-director
version: "1.0.0"
description: 播客二次创作的创意导演技能，负责判定源素材形态与可行性、选定交付物组合与比例、明确平台差异并产出带播客专属元数据的创作简报，适用于播客切片与衍生资产立项阶段。
metadata:
  license: AGPL-3.0
---

# 创意导演 — 播客二次创作流水线

## 适用场景

当源素材是一集播客（纯音频或视频播客），且用户希望得到切片、社交资产或伴随长视频方案时，启用本流水线。

你的首要职责是：基于**实际存在的**素材，判断哪些产出是可行的。

## 运行时选择（强制——必须把约束摆到台面上，不许默默替用户决定）

锁定 `render_runtime = "remotion"`（声波图与合成类产出）或 `"ffmpeg"`（纯音频主导的切片导出）。**在第一阶段，HyperFrames 不是本流水线的合法运行时**——播客类产出依赖 Remotion 的逐词字幕链路，HyperFrames 尚无对等能力。

按 AGENT_GUIDE.md 中“必须同时呈现两种合成运行时（硬性规则）”的要求，把这一约束明确告知用户，例如：“你机器上装有 HyperFrames，但 podcast-repurpose 依赖 Remotion 的字幕烧录，因此这里 remotion 是唯一可行选项”。同时记录一条 `render_runtime_selection` 决策，其中 hyperframes 的 `rejected_because` 填 `"caption-burn parity deferred on podcast-repurpose"`。

## 参考输入

- `docs/podcast-repurposing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## 工作流程

### 1. 判定源素材类别

记录源素材模式：

- `audio_only`（纯音频）
- `video_podcast`（视频播客）
- `hybrid`（音频加静帧、封面图、嘉宾照片）

同时记录对话形态：

- solo（独白）
- interview（访谈）
- panel（圆桌）
- narrative / produced show（叙事/精编节目）

### 2. 选择与实际情况相符的交付物

默认交付物应当是当前素材与工具条件下可实现的。

安全选项：

- 短视频高光切片
- 声波图型或字幕主导型切片
- 金句主导型切片
- 至多一个整集伴随长视频版式

除非源视频、品牌素材与可选图像确实齐备，否则不要假设可以做出高制作规格的整集 YouTube 方案。

### 3. 设定合理的交付物配比

典型起点：

- `3-5` 条高光切片
- 若节目有强金句，`1-3` 个金句主导型资产
- 若源素材撑得住，可加一个可选的长视频伴随产出

### 4. 尊重平台差异

- `9:16` 用于 Shorts、Reels、TikTok
- `1:1` 用于 LinkedIn 及更稳妥的信息流复用
- `16:9` 用于 YouTube 伴随视频

若源素材是纯音频，必须在简报中写明这一点。下游阶段不应规划根本不存在的“出镜说话人”视频。

### 5. 构建简报

用 `brief.metadata` 承载更丰富的播客专属契约字段：

- `source_mode`
- `show_name`
- `episode_title`
- `episode_number`
- `speakers`
- `conversation_format`
- `deliverable_mix`
- `brand_assets_available`
- `full_episode_companion_feasible`

### 6. 质量闸门

- 交付物配比与实际源素材相符，
- 切片数量相对节目时长是现实的，
- 简报中写明视觉走向是源素材主导、金句主导还是声波图主导，
- 长视频野心要与现有素材规模匹配。

## 常见陷阱

- 把纯音频源与视频播客源当成同一个制作问题。
- 从一集内容偏弱的节目里规划过多交付物。
- 在没有相应素材的情况下，承诺做视觉丰富的整集精编。

---

## 闸门提醒（具有约束力）

本阶段默认需要人工审批（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染该交付物），然后**结束本轮回复**。不要在同一次回复里启动下一阶段。审批是按闸门逐一进行的——早先某次“可以继续”不覆盖本闸门。
