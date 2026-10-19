---
name: openmontage-localization-dub-idea-director
version: "1.0.0"
description: 本地化配音流水线的创意/需求定义技能，用于在已有源视频时明确目标语言、交付形态（字幕/配音/对口型）与术语审核要求，产出可执行的本地化简报并设置人工审批门。
metadata:
  license: AGPL-3.0
---

# 创意导演 — 本地化配音流水线

## 何时使用

当用户已有源视频，希望得到翻译后的交付物时启用本流水线：包括字幕、配音音轨，或一种乃至多种目标语言的本地化成片。

你的首要职责是判断究竟需要哪一种本地化，因为"只上字幕""只配旁白""连口型一起配"是三种性质完全不同的工作。

## 运行环境选择（强制 — 要说明约束，不许默默选定）

将 `render_runtime` 锁定为 `"remotion"`（需要逐语言字幕烧录 / 对口型的合成型交付）或 `"ffmpeg"`（仅在源片上烧字幕、不做任何合成）。**在 Phase 1 中 HyperFrames 不是本流水线的合法运行时**——本地化依赖 Remotion 的字幕能力栈，而"配音+对口型"还依赖 Remotion 的 TalkingHead 管线。

依据 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：不要默默默认选择 remotion。要明确告知用户："HyperFrames 是可用的，但 localization-dub 依赖 Remotion 的字幕 + TalkingHead 对等能力，Phase 1 尚未具备——remotion 是唯一可行选项"。同时记录一条 `render_runtime_selection` 决策，注明 hyperframes 的 `rejected_because: "caption + lip-sync parity deferred on localization-dub"`。

## 参考输入

- `docs/localization-dubbing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## 流程

### 1. 界定本地化范围

需采集：

- 源语言；
- 目标语言；
- 审核责任人；
- 是否需要术语审核或法务审核；
- 用户要的是字幕、配音音轨、对口型，还是混合方案。

### 2. 归类源片形态

记录源片模式：

- `single_speaker`
- `multi_speaker`
- `voiceover_led`
- `speaker_led_on_camera`

同时记录画面文字或动态图形是否需要人工替换或遮挡处理。

### 3. 挑选与实际相符的交付物

可能的交付物：

- 仅字幕包；
- 无对口型的配音成片；
- 带对口型的本地化成片；
- 逐语言导出包。

### 4. 编写简报

建议的元数据字段：

- `source_language`
- `target_languages`
- `deliverable_mode_map`
- `glossary_terms`
- `protected_terms`
- `review_requirements`
- `timing_risks`

### 5. 质量门

- 本地化范围已明确；
- 目标产出切实可行；
- 术语表与审核要求已记录；
- 由说话人数或可见嘴部带来的风险升高已显式呈现。

## 常见坑

- 把所有翻译需求都当成配音需求。
- 等到音频生成之后才想起术语控制。
- 在视觉上难以处理的源片上承诺对口型却不预先警示。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染该产物），并**结束本轮回复**。不要在同一条回复中启动下一阶段。审批是逐门独立的——之前某次的"可以继续"不覆盖本门。
