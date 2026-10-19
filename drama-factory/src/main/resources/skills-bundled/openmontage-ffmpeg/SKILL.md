---
name: openmontage-ffmpeg
version: "1.0.0"
description: 汇总剧坊中所有基于 FFmpeg 的音视频处理工具与关键参数：剪切拼接、字幕烧录、混音、响度、美颜与调色链、降噪。适用于无需 AI 推理的成片加工与平台化交付。
metadata:
  license: AGPL-3.0
---

# FFmpeg 技能

## 适用场景

凡是不需要 AI 推理的音视频处理，都走 FFmpeg 支撑的工具：剪切、裁切、变速、拼接、抽音、混音、字幕烧录、叠加合成、编码、美颜、调色、音频清理。

## 使用 FFmpeg 的工具

### 主流水线

| 工具 | 能力 |
|------|------|
| `video_trimmer` | 剪切、裁切、变速、片段拼接 |
| `video_compose` | 完整合成：剪切 + 字幕 + 叠加 + 编码 |
| `audio_mixer` | 语音/音乐/音效混合、闪避、淡入淡出、抽音 |
| `frame_sampler` | 从视频抽取代表性帧 |

### 增强层

| 工具 | 能力 | 关键预设 |
|------|------|----------|
| `face_enhance` | 磨皮、锐化、暖/冷色调 | `talking_head_standard`、`soft_skin`、`sharpen` |
| `color_grade` | 带强度控制的电影感调色 | `cinematic_warm`、`cinematic_cool`、`moody_dark` |
| `audio_enhance` | 降噪、响度归一、均衡 | `clean_speech`、`voice_clarity`、`podcast` |

## 关键模式

### 增强链顺序

按以下顺序应用增强，避免滤镜相互干扰：

1. 字幕先做——直接烧进基础视频
2. 美颜——磨皮/锐化在未调色的画面上效果最佳
3. 调色——在已完成美颜的画面之上加风格
4. 音频增强——与画面独立，放最后

每一步都是可选项，工具不可用时自动跳过。

### 无损与重编码

- 只做剪切或拼接、不改动画面时，用 `-c copy` 复制编码流：瞬时完成且无损。
- 需要加滤镜（变速、字幕、叠加、缩放）时必须重编码，例如 `-c:v libx264`。
- 默认 CRF 为 23；若输出即为最终交付，用 18–20 提升画质。

### 字幕烧录

- 逐词简单字幕优先用 SRT。
- `force_style` 中的 ASS 颜色要写全格式：`&H00FFFFFF`，不能写成 `&HFFFFFF`。
- subtitles 滤镜里 Windows 路径必须转义（写 `C\:` 而非 `C:`）。
- 竖屏：`font_size: 18`、每行最多 3 词、`margin_v: 50`。
- 横屏：`font_size: 22`、每行最多 6 词、`margin_v: 40`。

### 音频增强目标

| 平台 | 目标 LUFS | 响度范围 |
|------|-----------|----------|
| 社媒（TikTok、Reels） | -14 LUFS | 5–7 LU |
| YouTube | -14 至 -16 LUFS | 7–11 LU |
| 播客 | -16 LUFS | 7–11 LU |
| 广播 | -24 LUFS | 7 LU |

`clean_speech` 预设瞄准 -16 LUFS、11 LU 范围，适合 YouTube 与社媒。

### 调色强度

- `intensity: 0.85`——口播人物上使用 `cinematic_warm` 的推荐默认值
- `intensity: 0.5`——非常轻微，几乎察觉不到
- `intensity: 1.0`——满效果，某些素材上会显得处理过度

### 音频闪避

- 用 `sidechaincompress`，把语音作为触发信号，在对话期间压低音乐。
- 常用参数：threshold=0.02、ratio=9、attack=200ms、release=500ms。

### 拼接

- 同编码片段用 concat 解复用器：`-f concat -safe 0`。
- 编码不同或分辨率不同的片段，先统一重编码。

## 质量检查清单

- [ ] 输出在桌面端与移动端播放均无瑕疵
- [ ] 处理之后音画保持同步
- [ ] 字幕位于画面底部 20% 区域内，绝不遮挡人脸
- [ ] 音频响度符合目标平台区间
- [ ] 增强肉眼可见但自然——肤色健康，不发橙
- [ ] 剪切点处无爆音、无静音断档
- [ ] 文件体积对目标平台而言合理
