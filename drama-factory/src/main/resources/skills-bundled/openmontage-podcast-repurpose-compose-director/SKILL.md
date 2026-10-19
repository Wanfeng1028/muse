---
name: openmontage-podcast-repurpose-compose-director
version: "1.0.0"
description: 播客再加工流水线的合成渲染环节，以音频保真为最高优先级，仅允许 Remotion 或 FFmpeg 两种运行时。适用于把切片、金句片与长视频配套内容按平台规格渲染输出的场景。
metadata:
  license: AGPL-3.0
---

# 合成渲染统筹（播客再加工）

渲染播客衍生交付物时，音频保真度是第一优先级。画面是来衬托语音的，不能跟语音抢戏。

## 何时使用

当剪辑决策已定、素材齐备，需要按不同平台规格渲染出成片时，进入本环节。

## 运行时路由（硬约束——只用 Remotion 或 FFmpeg）

第一阶段暂缓 HyperFrames。`edit_decisions.render_runtime` 只能是 `"remotion"`（音频可视化、合成输出）或 `"ffmpeg"`（纯音频主导的切片导出）。HyperFrames 的字幕烧录对齐尚未实现，而播客产出依赖 Remotion 的词级字幕栈。

- 若 `edit_decisions.render_runtime == "hyperframes"`，立即停止。回到创意环节，把该约束告知用户。绝不允许静默改写运行时。
- 依据 AGENT_GUIDE.md 的“呈现两种合成运行时（硬性规则）”：要主动告诉用户 HyperFrames 的存在，以及它在本流水线为何不可用，而不是静默锁定 remotion。记录一条 `render_runtime_selection` 决策，注明 hyperframes `rejected_because: "caption-burn parity deferred on podcast-repurpose"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便检测端到端的运行时切换。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 校验产物结构 |
| 前置产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 输出规划与素材路径 |
| 工具 | `video_compose`、`audio_mixer` | 渲染与混音控制 |
| Playbook | 当前生效的风格手册 | 保持品牌一致性 |

## 处理流程

### 1. 先渲染价值最高的产出

优先顺序：

1. 短切片高光；
2. 金句主导的切片；
3. 可选的长视频配套内容。

这样最先拿到的是最可直接发布的素材。

### 2. 保住音质

- 避免不必要的重复编码；
- 保证语音清晰稳定；
- 配乐要克制，只在不妨碍语音时使用；
- 渲染完成后核对字幕同步。

### 3. 遵循平台画幅

- `9:16`：短视频社交平台；
- `1:1`：金句类或信息流安全画幅；
- `16:9`：YouTube 长视频配套。

### 4. 逐项验收每个交付物

- 时长正确；
- 画幅比例正确；
- 字幕可读；
- 讲者归属准确；
- 音频稳定；
- 品牌处理一致。

### 5. 用渲染报告元数据记录

建议的元数据键：

- `deliverable_groups`
- `audio_notes`
- `subtitle_checks`
- `failed_outputs`

## 常见坑

- 让视觉处理拖累了音质。
- 先把长配套视频渲染完，反而耽误了最要紧的切片。
- 忘记一个简单清晰的切片，胜过技术花哨但让人看不懂的切片。
