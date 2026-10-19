---
name: openmontage-hybrid-idea-director
version: "1.0.0"
description: 混合管线创意导演技能，负责在真实源素材与生成型支撑素材结合的项目中确定锚定媒介、规划支撑层与交付组合，并在两种合成运行时之间做出选择。适用于访谈配图解、实拍配浮层、录屏配品牌图形等混合视频的创意立项阶段。
metadata:
  license: AGPL-3.0
---

# 混合管线创意导演

## 适用场景

当项目把真实源媒介与支撑视觉结合起来时使用本管线：访谈加图解、实拍加浮层、录屏加品牌图形，或是以源素材为主、穿插生成片段的剪辑。

混合并不是万能筐。你的首要任务，是明确什么保持主导地位。

## 运行时选择（强制 —— 必须同时呈现两个运行时）

在锁定制作方案之前，必须与用户共同决定 `render_runtime`。混合管线同时支持 Remotion 与 HyperFrames，二者都不作为自动默认。请遵循 AGENT_GUIDE.md → “Present Both Composition Runtimes (HARD RULE)” 中的契约：

1. 查询 `video_compose.get_info()["render_engines"]`。若 `remotion` 与 `hyperframes` 均为 `True`，向用户同时呈现两者，并结合本 brief 做分析：
   - **Remotion** —— 适合源素材主导、支撑层为 React 场景组件（图表、标注、文字卡）的情形。Remotion 可通过 `<OffthreadVideo>` 在一次合成中同时处理视频片段与 React 浮层。
   - **HyperFrames** —— 适合支撑层为 HTML/GSAP 原生（动态标注、registry 区块、排版浮层），且源素材以 `<video class="clip">` 内嵌的情形。
2. 结合锚定媒介与支撑层形态，推荐其中一个并给出理由。
3. 等待用户明确批准。
4. 将该选择记录进 `decision_log`，作为 `render_runtime_selection` 决策，且 `options_considered` 中必须同时包含两个运行时。

若两个运行时都可用，而 `options_considered` 中只列了一个，会被评审标记为 CRITICAL 问题。

## 参考输入

- `docs/hybrid-video-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/video-editing.md`

## 流程

### 1. 选择锚定媒介

确定叙事锚点：

- `talking_head`（人物出镜）
- `broll_footage`（B-roll 实拍）
- `screen_recording`（屏幕录制）
- `still_sequence`（静帧序列）
- `narration_led_graphics`（旁白驱动的图形）

### 2. 定义支撑层

可选的支撑层包括：

- 字幕
- 图解
- 代码可视化
- 数据卡
- 生成片段
- 旁白
- 音乐

每一个支撑层都应解决一个具体问题，而不是单纯装饰时间线。

### 3. 决定交付组合

常见输出：

- 主片（hero cut）
- 竖版剪辑
- 方形剪辑
- 分章版本
- 广告变体

### 4. 撰写 brief

推荐元数据键：

- `anchor_medium`
- `source_inventory`
- `support_layers`
- `deliverable_mix`
- `missing_capabilities`
- `fallback_policy`

### 5. 质量关口

- 锚定媒介明确无误；
- 支撑层理由充分；
- 交付组合与源素材清单匹配；
- 缺失能力被尽早暴露。

## 常见陷阱

- 不做主导媒介的界定就统统称为“混合”。
- 在理解源素材之前就规划支撑层。
- 把可选的生成片段当作必然可得。

---

## 关口提醒（具约束力）

本阶段以人工批准作为关口（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 面板会渲染 artifact），然后**结束本轮**。不要在同一次回复里启动下一阶段。
批准是按关口独立的——之前某一次的“继续”不覆盖本关口。
