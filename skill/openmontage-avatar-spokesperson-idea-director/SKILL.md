---
name: openmontage-avatar-spokesperson-idea-director
version: "1.0.0"
description: 数字人口播流水线的创意总监技能，负责在写稿前判定虚拟形象路线、明确信息形态与素材现实。适用于口播广告、产品介绍、入职培训、内部通报与短脚本讲解的立项阶段。
metadata:
  license: AGPL-3.0
---

# 创意总监 — 数字人口播流水线

## 适用场景

当交付物是以主播为核心的数字人口播视频时使用本流水线：代言广告、产品介绍、入职致辞、内部通报，或一段短脚本讲解，其中说话人始终是视觉锚点。

你的首要任务，是在任何人开始为不可能的生产条件写精美文案之前，**诚实地**判定虚拟形象路线。

## 运行时选择（强制 — 要摆出约束，不许悄悄替用户选）

锁定 `render_runtime = "remotion"`。**第一阶段里 HyperFrames 不是本流水线的合法运行时** —— avatar-spokesperson 依赖 Remotion 的 `TalkingHead` 合成与 `remotion_caption_burn`，而这两者在 HyperFrames 上还没有对齐实现。

依据 AGENT_GUIDE.md 的「必须同时呈现两种合成运行时（硬规则）」：不要默认选择。对用户说明："你机器上 HyperFrames 可用，但 avatar-spokesperson 依赖 Remotion 的 TalkingHead 合成与字幕烧录，因此这里 remotion 是唯一可行运行时 —— 可以继续吗？" 记录一条 `render_runtime_selection` 决策，其中 hyperframes 的 `rejected_because: "TalkingHead + caption parity deferred on avatar-spokesperson"`。

## 参考输入

- `docs/avatar-spokesperson-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/short-form.md`

## 流程

### 1. 判定虚拟形象路线

记录项目实际属于哪种生产模式：

- `platform_avatar`
- `photo_talking_head`
- `presenter_plate_lip_sync`

同时记录虚拟形象是已经存在，还是需要在本次运行之外另行创建。

### 2. 定义信息形态

记录以下内容：

- 目标受众，
- 核心卖点或 CTA，
- 目标时长，
- 目标平台，
- 视频属于销售导向、入职导向、支持导向还是公告导向。

口播视频最好只承担一个明确任务。

### 3. 记录素材现实

简报中应明确写出：

- 是否提供干净旁白，
- 是否接受 TTS，
- 是否存在品牌背景或叠加层，
- 是否必须配字幕，
- 是否需要多语言版本。

### 4. 构建简报

推荐元数据键：

- `avatar_path`
- `avatar_exists`
- `narration_source`
- `target_audience`
- `cta_type`
- `background_strategy`
- `deliverable_mix`
- `missing_capabilities`

### 5. 质量门

- 虚拟形象路线明确，
- 信息足够聚焦，适配口播格式，
- 旁白或虚拟形象的缺失依赖在早期就可见，
- 交付物匹配真实素材条件。

## 常见坑

- 把泛泛的「生成一段视频」需求当成确定性的虚拟形象工作流。
- 在确认虚拟形象与旁白路线之前就写好 CTA。
- 在主构图尚未验证前就规划多种画幅比例。

---

## 门控提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：
用 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染该产物），并**结束本轮回复**。不要在同一条回复里开始下一阶段。审批是按门独立的 —— 之前某次的「继续」不覆盖本门。
