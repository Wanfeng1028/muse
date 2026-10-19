---
name: openmontage-talking-head-idea-director
version: "1.0.0"
description: 口播视频流水线的创意阶段技能，负责探测原始素材、评估内容并产出 brief 产物，适用于已有真人讲话素材、需要确定内容定位与制作目标的起始环节。
metadata:
  license: AGPL-3.0
---

# 创意导演 — 口播流水线

## 何时使用

你正在启动一个口播视频项目，手上已有一段真人讲话的原始素材。你的职责是分析素材、理解其中内容，并产出一份 brief，凝练内容的本质与制作目标。

与解说流水线从选题出发不同，你从既有素材出发。brief 记录的是你手头有什么、以及最终视频应该长什么样。

## 运行时选择（强制 — 呈现约束，不要静默选择）

锁定 `render_runtime = "remotion"`（首选，使用 `TalkingHead` + `remotion_caption_burn`）或 `"ffmpeg"`（用于无合成的源素材拼接）。**本流水线第一阶段 HyperFrames 不是合法运行时** —— TalkingHead 合成与词级字幕烧录在 HyperFrames 上尚无对等实现。

依据 AGENT_GUIDE.md 中"必须同时呈现两种合成运行时（硬规则）"：不得静默默认 remotion。需告知用户："HyperFrames 可用，但口播依赖 Remotion 的 TalkingHead 合成，因此 remotion 是唯一可行的合成选择（或 ffmpeg 做粗剪）—— 是否继续？"并记录一条 `render_runtime_selection` 决策，把 hyperframes 列为被拒选项（`rejected_because: "TalkingHead + caption parity deferred on talking-head"`）。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/brief.schema.json` | 产物校验 |
| 输入 | 原始素材文件路径 | 源材料 |
| 工具 | `ffprobe`（shell 调用） | 素材元数据提取 |

## 流程

### 步骤 1：探测素材

用 ffprobe 提取元数据：

- 时长
- 分辨率
- 帧率
- 音轨数与编码
- 文件体积

由此了解手头素材的质量、长度与格式。

### 步骤 2：快速内容评估

通览素材（若 frame_sampler 可用则抽样帧）：

- 讲话者在谈什么主题？
- 原始素材多长？
- 目标平台是什么？（不明确时询问用户）
- 音频是否可用？有无底噪？

### 步骤 3：撰写 brief

创建 brief 产物，记录：

- **标题**：基于素材内容的描述性标题
- **钩子**：这段内容为何值得一看
- **要点**：素材覆盖的主要话题
- **语气**：匹配讲话者的真实语气（随意、专业、教学）
- **风格**：从素材、讲话者人设、受众与平台推导叠加与观感方向。`clean-professional` 是安全回退，不是每份口播 brief 的默认答案
- **目标平台**：发布渠道
- **目标时长**：可短于原始素材（经裁剪）

### 步骤 4：自评

| 标准 | 问题 |
|------|------|
| **准确** | brief 是否反映了素材真实内容？ |
| **完整** | 所有必填字段是否齐备？ |
| **平台契合** | 目标平台是否适合此内容？ |

### 步骤 5：提交

对照 schema 校验 brief，并通过 checkpoint 持久化。

---

## 关卡提醒（强制）

本阶段默认需要人工批准（`human_approval_default: true`）。审阅通过后：以 `status="awaiting_human"` 打 checkpoint，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一回复中启动下一阶段。批准按关卡独立生效 —— 之前说过的一句"继续"不覆盖本关卡。
