---
name: openmontage-localization-dub-compose-director
version: "1.0.0"
description: 负责本地化配音流水线的渲染合成阶段，按语言逐套输出成片并校验可懂度、时序与版本标注，适用于多语言版本交付场景。
metadata:
  license: AGPL-3.0
---

# 合成总监 · 本地化配音流水线

## 何时使用本阶段

用于渲染本地化产出。质量标准是可懂度、时序一致性，以及每套语言包都具备清晰的版本标注。

## 运行时路由（硬性约束：仅限 Remotion 或 FFmpeg）

第一阶段暂缓支持 HyperFrames。`edit_decisions.render_runtime` 必须是 `"remotion"` 或 `"ffmpeg"`。本地化依赖 Remotion 的字幕栈（按语言烧录字幕），并在带唇形同步的配音场景下依赖 Remotion 的 TalkingHead 流水线。HyperFrames 在第一阶段对这两项都没有对等能力。

- 如果 `edit_decisions.render_runtime == "hyperframes"`，立即停止。回到创意阶段重新处理，并把该约束明确告知——不要悄悄改写运行时。
- 按 AGENT_GUIDE.md 中「Present Both Composition Runtimes（硬性规则）」的要求：流水线的约束不能跳过这段沟通。要把约束摆给用户看，让他们知道 HyperFrames 存在但在本场景不可用。写一条 `render_runtime_selection` 决策，附上 hyperframes 的 `rejected_because: "caption + lip-sync parity deferred on localization-dub"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便检测端到端的运行时替换。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 校验产出物结构 |
| 前置产出 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 提供按语言区分的渲染指令 |
| 工具 | `video_compose`、`audio_mixer`、`video_trimmer`、`audio_enhance` | 完成最终渲染与音频收尾 |
| Playbook | 当前启用的风格手册 | 约束字幕位置与输出质量 |

## 流程

### 1. 按语言逐一渲染

把每种目标语言视为独立的交付套件。命名与输出目录都要写清楚，不要含糊。

### 2. 预期时序会发生变化

需要预留处理空间的情况包括：

- 字幕重新折行；
- 配音音频时长漂移；
- CTA 停留时间变长；
- 可选的裁剪或补拍覆盖段落。

### 3. 每种语言都要验证

把关键发现记录到：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.locale_notes`

检查项：

- 可懂度；
- 字幕是否适配；
- 是否有明显不同步；
- 版本标注是否正确。

### 4. 质量门

- 每种语言都有对应输出；
- 配音与字幕的时序可以接受；
- 标注与文件名没有歧义；
- 警告信息被完整保留。

## 常见陷阱

- 把各语言都当成时序完全一致来渲染。
- 翻译后忘记重新检查字幕行长。
- 输出命名掩盖了语言或处理模式。
