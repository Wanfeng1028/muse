---
name: openmontage-subtitle-sync
version: "1.0.0"
description: 将转录数据转换为精确计时的字幕文件，覆盖计时策略、格式化与可读性，适用于竖屏和横屏视频的字幕生成与烧录。
metadata:
  license: AGPL-3.0
---

# 字幕同步

## 何时使用

用 `subtitle_gen` 工具把转录数据（来自 `transcriber`）转换成计时正确的字幕文件。本技能涵盖计时策略、格式化和可读性，竖屏和横屏视频均适用。

## 工具

| 工具 | 能力 |
|------|-----------|
| `subtitle_gen` | 从词级时间戳生成 SRT、VTT 或 caption JSON |

## 输出格式

| 格式 | 扩展名 | 用途 |
|--------|-----------|----------|
| SRT | `.srt` | 通用——兼容 FFmpeg、播放器、YouTube 上传 |
| VTT | `.vtt` | Web 原生——HTML5 视频、浏览器播放 |
| Caption JSON | `.caption.json` | 程序化——为自定义渲染器提供词级数据 |

## 按格式的 Cue 长度

### 竖屏短视频（TikTok、Reels、Shorts）

- **每条 cue 最多 3-4 个词** — 屏幕窄，文字必须足够大才可读
- **每行最多 20 个字符** — 防止在窄屏上换行
- 字幕是**强制的**（大多数观众静音观看）

### 横屏标准（YouTube、web）

- **每条 cue 最多 6-8 个词** — 宽屏容纳更多文字
- **每行最多 42 个字符** — 标准广播限制

### 通用规则

- 普通观众阅读速度约 15 字符/秒
- 最短显示时间：每条 cue 0.5 秒
- 最长显示时间：每条 cue 5 秒

## 烧录样式（ASS force_style）

通过 `video_compose` 烧录字幕时，以下参数作为 ASS `force_style` 传入。使用正确的 ASS 颜色格式：`&HAABBGGRR`（不是十六进制 RGB）。

### 竖屏视频（1080x1920）

```
font: Arial
font_size: 18
bold: true
primary_color: &H00FFFFFF      # 白色（ASS 格式：alpha=00, BGR=FFFFFF）
outline_color: &H00000000      # 黑色
outline_width: 3               # 粗描边以保证在多变背景上的可读性
shadow: 2
margin_v: 50                   # 距底边像素
alignment: 2                   # 底部居中
```

### 横屏视频（1920x1080）

```
font: Arial
font_size: 22
bold: true
primary_color: &H00FFFFFF
outline_color: &H00000000
outline_width: 2
shadow: 1
margin_v: 40
alignment: 2
```

### 常见错误

- **颜色格式错误：** `&HFFFFFF` 会破坏定位。始终使用完整 8 字符 `&H00FFFFFF`。
- **竖屏字体过大：** `font_size: 28` 会填满 9:16 画面的中央。最大用 18。
- **竖屏每条 cue 词太多：** 5+ 个词会创建多行块遮住人脸。
- **MarginV 过大：** 超过 200 的值会把文字推出屏幕。多数情况保持在 100 以下。

## 计时最佳实践

### 与语音对齐

- cue 开始必须匹配词的起始（不能在说话者开口前）
- cue 结束应在最后一个词后延伸约 200ms 以便舒适阅读
- 绝不让 cue 延续到下一个说话者的回合

### 词边界分组

`subtitle_gen` 工具在分组词时遵守 `max_words_per_cue` 和 `max_chars_per_line`。当词时间戳不可用时，回退到段级计时并均匀分布。

## 质量检查清单

- [ ] 每个说出的词都出现在字幕 cue 中
- [ ] 没有 cue 超过目标格式的字符限制
- [ ] 字幕位于画面底部 20% — 绝不遮挡人脸
- [ ] 文字在移动端原生分辨率下可读
- [ ] 计时匹配语音 — 无过早或过晚的 cue
- [ ] cue 之间不重叠
- [ ] 描边/阴影在所有背景上提供足够对比度
