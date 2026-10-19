---
name: openmontage-screen-demo-compose-director
version: "1.0.0"
description: 渲染屏幕演示最终输出，确保UI可读、节奏有意图、成片匹配目标平台规格。适用于编辑决策完成后、需要按锁定运行时合成最终视频的阶段。
metadata:
  license: AGPL-3.0
---

# 合成总监 — 屏幕演示流水线

## 何时使用

渲染屏幕演示的最终输出。质量标准很简洁：界面必须可读，节奏必须感觉有意图，成片必须匹配计划中的平台规格。

## 运行时路由（强制的第一步）

首先读取 `edit_decisions.render_runtime`。屏幕演示合成根据演示形态使用三种不同运行时：

- **`render_runtime="remotion"` 配合 `TerminalScene`** — 合成终端/CLI/安装流程的首选路径。参见 `.agents/skills/synthetic-screen-recording/`。
- **`render_runtime="remotion"`**（其他场景）— 用于混合屏幕录制 + 动画叠加。
- **`render_runtime="hyperframes"`** — 用于自定义合成 HTML 界面演示，CSS + GSAP 可自然表达 UI。阅读 `skills/core/hyperframes.md`。渲染前 `hyperframes lint` 和 `hyperframes validate` 必须都通过。
- **`render_runtime="ffmpeg"`** — 用于简单裁剪/拼接真实屏幕录制，无需合成。

运行时之间的静默切换是严重的治理违规。如果锁定的运行时不可用，按 AGENT_GUIDE.md 上报，不得擅自替换。

**将 `proposal_packet` 传给 `video_compose.execute()`**，让工具能直接确认提案阶段锁定的运行时与 `edit_decisions` 中的一致。不传的话，工具内的切换检查会被跳过，你只能完全依赖审核技能来捕捉偏差。

## 前置条件

| 层级 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | 工件校验 |
| 前置工件 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 决定渲染内容 |
| 工具 | `video_compose`、`audio_mixer`、`video_trimmer` | 渲染能力 |
| 手册 | 当前激活的风格手册 | 质量目标 |

## 流程

### 1. 可读性优先的渲染

优先使用最简单可靠的渲染链路：

- 裁剪并调速源素材
- 合成叠加与字幕
- 仅在必要时混音
- 以适合文字密集内容的码率编码

### 2. 务实地选择输出规格

| 平台 | 宽高比 | 分辨率 | 备注 |
|----------|--------------|------------|-------|
| YouTube / 文档 | `16:9` | 1920x1080 或更高 | 密集 UI 最安全的默认选项 |
| LinkedIn 信息流 | `1:1` | 1080x1080 | 竖屏太挤时的良好折中 |
| Shorts / Reels / TikTok | `9:16` | 1080x1920 | 仅在裁切方案确实可读时使用 |

如果源素材是 4K 且文字很小，在实际可行时保持更高分辨率。

### 3. 按正确顺序合成

1. 应用裁剪和速度变更
2. 应用裁切与构图策略
3. 放置遮罩和叠加
4. 烧录字幕
5. 混音
6. 以保留文字的设置编码

使用锐利缩放，避免激进压缩。编码质量下降时，屏幕文字是观众最先注意到的问题。

### 4. 保持音频诚实

- 保留原始语音清晰度
- 不要过度压缩
- 静音或简化加速后的无用噪音
- 音乐使用要克制，甚至不用

### 5. 验证每一份输出

**文件检查：**
- [ ] 输出文件存在且为合法 MP4 容器
- [ ] 时长在有效目标 ±5% 以内
- [ ] 分辨率匹配所选规格

**视觉抽查：**
- [ ] 采样帧中文字锐利可读
- [ ] 裁切过渡足够流畅可跟随
- [ ] 标注叠加出现和消失干净
- [ ] 模糊遮罩完全覆盖敏感数据
- [ ] 无黑帧或时序故障
- [ ] 字幕不遮挡关键 UI

**音频抽查：**
- [ ] 旁白/配音清晰且音量一致
- [ ] 如使用音乐，不与语音竞争
- [ ] 速度边界处无明显音频故障
- [ ] 无削波或失真

将重要发现记录在：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.variant_notes`

## 常见陷阱

- 渲染出技术上导出成功但实际不可读的 `9:16` 版本。
- 用通用低码率社交默认值编码屏幕文字。
- 让装饰性背景或留白过度压缩可用 UI 区域。
