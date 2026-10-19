---
name: openmontage-hybrid-compose-director
version: "1.0.0"
description: 混合剪辑流水线的最终合成环节，负责把原始素材、支撑图形与音频统一渲染成各平台输出，适用于需要在多版本导出中保持画面与声音一致性的收尾阶段。
metadata:
  license: AGPL-3.0
---

# 合成统筹（混合流水线）

## 适用时机

把混合项目渲染成最终成品，确保原始媒体、支撑图形与音频在所有输出中都保持一致。

## 运行时路由（强制第一步）

先读 `edit_decisions.render_runtime`。混合项目通常沿用 Remotion，因为原始素材加 React 支撑叠加可以在一次渲染中干净合成：

- **`render_runtime="remotion"`** —— 默认选项。原始素材走 `<OffthreadVideo>`，支撑图形作为 React 组件，一次渲染完成。
- **`render_runtime="hyperframes"`** —— 仅当支撑层是 HTML/GSAP 原生实现时选用（例如动态文字标注、注册表区块）。原始素材仍可用 `<video class="clip">` 引入，但会失去部分 Remotion 组件能力。参见 `skills/core/hyperframes.md`。
- **`render_runtime="ffmpeg"`** —— 本流水线中很少见，意味着没有生成式支撑层。

静默替换运行时属于严重治理违规。遇到阻塞必须按 AGENT_GUIDE.md 上报，不得擅自替代。

**调用 `video_compose.execute()` 时传入 `proposal_packet`**，这样工具内置的替换检测会直接针对提案执行，而不是被标记为 `skipped`。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 校验产物合法性 |
| 上游产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 剪辑逻辑与支撑素材 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`video_trimmer`、`color_grade`、`audio_enhance` | 最终合成与打磨 |
| Playbook | 当前启用的风格手册 | 输出一致性 |

## 流程

### 1. 检查素材与支撑的平衡

最终成片看起来仍应是以原始素材为主、支撑为辅的作品，而不是几套无关系统拼凑成的拼贴画。

### 2. 校验各变体完整性

针对每一个输出变体，逐项检查：

- 裁切安全区；
- 文字安全区；
- 字幕可读性；
- 音频一致性。

### 3. 保持音频统一

原始对白、旁白、音乐与音效应融为一个整体混音，而不是各层互相抢空间。

### 4. 用元数据记录渲染信息

推荐的元数据键：

- `variant_outputs`
- `balance_checks`
- `subtitle_checks`
- `audio_notes`

## 常见陷阱

- 主版本剪辑没问题，平台变体却崩了。
- 支撑图形在竖版导出中被裁掉。
- 原始段落与生成段落之间响度漂移。
