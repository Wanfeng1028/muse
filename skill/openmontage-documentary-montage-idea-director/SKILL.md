---
name: openmontage-documentary-montage-idea-director
version: "1.0.0"
description: 纪录片蒙太奇流水线的创意导演技能，把用户需求转成主题 brief，锁定运行时并规划音乐、片尾字幕与旁白意图，用于启动整条流水线。
metadata:
  license: AGPL-3.0
---

# 创意导演 · 纪录片蒙太奇流水线

## 适用场景

你的任务是把用户 prompt 变成所有下游阶段都要读取的 brief 产物。在本流水线中，brief 就是**主题内核**：这支蒙太奇在讲什么、应该是什么感觉、跑多长。

## 运行时选择（强制——要呈现约束，不许静默决定）

锁定 `render_runtime = "remotion"`。**Phase 1 中 HyperFrames 在本流水线不是可用运行时**——documentary-montage 依赖 Remotion 的 `CinematicRenderer` 合成及其 ProRes-4444 alpha 片尾字幕叠加栈，两者在 HyperFrames 均无对等实现。

按 AGENT_GUIDE.md → “呈现两种合成运行时（硬规则）”：**不要**静默取默认值。要告诉用户：“你机器上另有 HyperFrames 可用作运行时，但 documentary-montage 依赖 Remotion 的 CinematicRenderer 与片尾叠加栈，因此这里 remotion 是唯一可行选项——可以继续吗？”随后在 `decision_log` 中记录一条 `render_runtime_selection` 决策，`options_considered` 中列出两种运行时，并给出 hyperframes 的 `rejected_because: "CinematicRenderer + end-tag overlay parity deferred on documentary-montage"`。

## 前置依赖

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/brief.schema.json` | 产物校验 |
| 用户输入 | 对话历史 | 原始诉求 |
| 元技能 | `skills/meta/reviewer.md` | 自检环节 |

## 流程

### 1. 提炼主题之问

纪录片蒙太奇回答的是一个用户说不成句的问题。你要用**一行**把它命名出来。

好的主题之问：

- “回家是什么感觉？”
- “20 世纪是如何想象未来的？”
- “凌晨四点的城市在发生什么？”
- “地球上所有脚印加在一起是什么样？”

差的主题之问（过抽象或过具体）：

- “一支关于城市的视频”（过抽象——没有感觉）
- “一支包含 8 个指定月亮镜头的蒙太奇”（过具体——那是分镜表不是主题）

### 2. 固定调性

从固定清单里选**一个**情绪语域，写下来。下游一切都以此为准。

本流水线常见语域：

- **挽歌式**——长停留、低饱和、慢切（失去、记忆、故乡）
- **紧迫式**——短切、硬同步、运动感强（危机、城市、此刻）
- **虔敬式**——庄重、对称、有耐心（自然、仪式、尺度）
- **反讽式**——讽刺性并置、踩荒诞点切（消费文化、政治、中世纪乐观主义）
- **梦幻式**——慢叠化、重复母题、非线性（童年、哀伤、记忆）

### 3. 定时长与结构

时长决定节拍上限。

| 时长 | 节拍 | 用途 |
|------|------|------|
| 30–45s | 8–12 切 | 社媒/短视频——一种感觉，无弧线 |
| 60–90s | 15–25 切 | 标准短片——带转折的迷你弧 |
| 2–3 分 | 30–50 切 | 正式随笔蒙太奇——可做三幕弧 |

结构选项：

- **单图扩展**——一个念头，多角度呈现（适合 60s 以内的挽歌式作品）
- **前后对照**——前半建立，后半翻转（适合反讽或紧迫语域）
- **三幕**——铺陈 → 转折 → 释放（Adam Curtis 招式，需 >90s）
- **清单/目录**——“所有曾经……”式结构，无弧线，纯累积（适合虔敬或挽歌语域）

### 4. 记录音乐意图（强制）

纪录片蒙太奇与音乐床不可分割。**本流水线音乐为强制项。** 唯一豁免是用户明确选择退出（例如“不要音乐，我要静音”），且必须记为 `music_plan.source = "none"` 并附 `music_plan.opt_out_reason` 字段。

创意阶段觉得“纯粹”的静音设计，到合成阶段常看起来像一堆废片。别指望静音能自证价值。用户没提音乐，就**默认他们想要**，并选：

- 用户自带曲目（路径写入 `music_plan.source_path`）
- 音乐库选曲（查 `registry.get_by_capability("music_library")` 并列曲目）
- 免版税检索（查 `registry.get_by_capability("music_search")`，报告提供方与授权）
- 生成（写明工具与带语域的 prompt seed）
- 明确退出（`source: "none"` + `opt_out_reason`）

在宣布无源可用前，还要查 `registry.get_by_capability("music_generation")`。**若无音乐源可用，必须警示用户。** 不要静默推迟——那会在素材阶段变成昂贵的意外。

### 5. 记录片尾字幕意图（强制）

每支纪录片蒙太奇都以一句哲学性的片尾字幕收束——一句短而抽象、给全片以意义的文字。它以 Remotion 片尾卡渲染（“发光下划线字幕”语域：粗字重、字距拉开、下划线动画）。

**默认模式为 `"overlay"`**——字幕淡入到正片最后几秒画面之上，像是影片的一部分，而非末尾另贴的一张卡。另一选项是 `"concat"`，即在正片后追加独立黑卡。仅当用户明确要求分离式标题卡，或最后画面视觉过于嘈杂不便叠字时才用 concat。

**片尾字幕为强制项。** 唯一豁免是用户明确退出，记为 `end_tag_plan: null` 并附 `end_tag_opt_out_reason`。

在 brief 阶段就要提出片尾字幕：写 3 个方案并推荐一个。预期结构：

```json
{
  "end_tag_plan": {
    "text": "WE BUILT BOTH WITH THE SAME HANDS.",
    "palette": "warm_ivory_on_black",
    "duration_seconds": 5.5,
    "render_engine": "remotion",
    "component": "EndTag",
    "mode": "overlay"
  }
}
```

字段说明：

- `text`——3–9 个词。是论点，不是总结。
- `palette`——`"cool_offwhite_on_black"` 或 `"warm_ivory_on_black"`。
- `duration_seconds`——字幕总屏上时长（淡入+停留+淡出）。5–8s 最佳。
- `render_engine`——恒为 `"remotion"`。
- `component`——恒为 `"EndTag"`。
- `mode`——`"overlay"`（默认）或 `"concat"`。
  - **overlay**：字幕渲染为带 alpha 的 ProRes 4444，经 FFmpeg overlay 滤镜合成到正片末段；字幕淡入出现在最后 N 秒实拍画面之上；正片自身淡出与字幕淡出需对齐。
  - **concat**：字幕渲染为不透明 MP4，经 FFmpeg concat 追加在正片后；总时长 = 正片 + 字幕。

### 6. 记录旁白意图（可选）

与音乐、片尾字幕不同，旁白是**可选**的。若画面+音乐+片尾字幕已能承载语域，无旁白完全可行。若使用旁白，写明 TTS 提供方与音色。无旁白时也要显式记录 `narration: "none"`，不要留空。

### 7. 落盘 brief

brief 至少包含以下字段：

```json
{
  "topic": "A minute in the rain",
  "thematic_question": "What does rain show you about a city?",
  "tone": "elegiac",
  "duration_seconds": 90,
  "shape": "list",
  "sources_allowed": ["pexels", "pixabay_video", "coverr", "mixkit", "archive_org", "nara", "nasa"],
  "generated_clips_allowed": false,
  "narration": "none",
  "music_plan": {
    "source": "generated",
    "provider": "elevenlabs",
    "prompt_seed": "slow ambient drone in A minor, no percussion, 60s sustained swell, Max Richter register"
  },
  "end_tag_plan": {
    "text": "THE CITY KEEPS ITS OWN VIGIL.",
    "palette": "cool_offwhite_on_black",
    "duration_seconds": 5.5,
    "render_engine": "remotion",
    "component": "EndTag"
  },
  "era_mix": "any",
  "target_platform": "social_short"
}
```

`era_mix` 是纪录片专属字段：`"modern"` 偏向 Pexels，`"vintage"` 偏向 Archive.org Prelinger，`"any"` 交由分镜导演按槽位自行决定。

### 8. 质量门

- 主题之问为**一句话**。
- 调性为固定清单中的**单一**语域。
- 时长与结构为具体数值/枚举值。
- `music_plan` 存在，且要么给出真实来源，要么为 `source: "none"` + `opt_out_reason`（用户明确决定）。
- `end_tag_plan` 存在，且要么 `text` 非空，要么为 `null` 并附 `end_tag_opt_out_reason`（用户明确决定）。
- 来源列表非空，且至少一个请求来源在预检暴露的 `corpus_builder.source_provider_menu` 中为 `available`。

## 常见陷阱

- 同时声明多个主题（“它关于城市、又关于科技、又关于失去”）。只选一个，其余成为下游联想。
- 直接跳到分镜表。brief 管的是**意义**，镜头是下一步。
- 忽略时长。45s 配 50 切是眩晕，3 分钟配 12 切是幻灯片。
- 忘了问音乐。用户通常是有想法的。
- 假定静音能自证价值。它不会。除非用户明说不要，音乐为强制项。
- 因为“画面自己会说话”而跳过片尾字幕。画面不会——片尾字幕就是论点。每次都要提。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一个回复里启动下一阶段。审批按门独立——早先的“继续”不覆盖本门。
