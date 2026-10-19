---
name: openmontage-clip-factory-compose-director
version: "1.0.0"
description: 逐条渲染每个片子和各平台变体，强调一致性、批处理韧性与部分失败的清晰上报；适用于剪辑工厂流水线在素材与剪辑确定后执行批量导出，运行时限定 Remotion 或 FFmpeg。
metadata:
  license: AGPL-3.0
---

# 合成总监（剪辑工厂流水线）

## 适用时机

逐条渲染每个片子和各平台变体。这里的关键行为是一致性、批处理韧性，以及对部分失败的清晰上报。

## 运行时路由（硬性约束——仅限 Remotion 或 FFmpeg）

本流水线在 HyperFrames 采纳计划中属于 Phase 1 延后项。`edit_decisions.render_runtime` 必须是 `"remotion"`（默认）或 `"ffmpeg"`（无合成的纯拼接任务）。HyperFrames 在此不是合法运行时——clip-factory 依赖 Remotion 的逐词字幕烧录，而 HyperFrames 的字幕对齐能力属于延后工作。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停止。重开 idea 阶段，把真实约束呈现给用户，并用一次 `render_runtime_selection` 决策把 `remotion` 锁定，其中记录 `hyperframes` 为 `rejected_because: "caption-burn parity deferred on clip-factory"`。
- 依据 AGENT_GUIDE.md 的“展示两种合成运行时（硬性规则）”：该约束不是跳过沟通的借口。用户仍应看到 HyperFrames 的存在以及它在此不可用的原因。
- 把 `proposal_packet` / `brief` 传给 `video_compose.execute()`，以便工具内的运行时切换检查端到端执行。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 剪辑决策与素材 |
| 工具 | `video_trimmer`、`video_compose`、`audio_mixer`、`color_grade` | 渲染管线 |
| 媒体档 | `lib/media_profiles.py` | 平台目标 |

## 流程

### 1. 把每个输出当作独立任务

一条片子分发到三个平台，就是三个渲染任务。要显式命名并分别跟踪。

### 2. 能共享的都共享

- 尽可能共用音频混音；
- 共用字幕样式；
- 共用叠加素材；
- 源素材需要时共用调色。

### 3. 软失败

若某条片子或某个平台变体失败：

- 明确记录；
- 继续完成批次其余部分；
- 不要因此阻断已成功的导出。

### 4. 每个输出都要验证

每次渲染检查：

- 时长正确；
- 分辨率 / 宽高比正确；
- 开头没有黑帧；
- 钩子按时出现；
- 字幕渲染正常；
- 音频存在且一致。

### 5. 使用渲染报告元数据

推荐的元数据键：

- `job_index`
- `failed_jobs`
- `shared_intermediates`
- `platform_groupings`

## 常见陷阱

- 任务本身互相独立，却无理由地串行渲染。
- 把某条片子失败当成中止整批的理由。
- 让某个平台变体悄悄用错构图或字幕区域。
