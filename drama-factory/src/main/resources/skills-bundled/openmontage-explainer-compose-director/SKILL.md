---
name: openmontage-explainer-compose-director
version: "1.0.0"
description: 解说视频合成导演技能，依据剪辑决策与资产清单渲染成片，处理运行时路由、音频嵌入、词级字幕烧录与多平台编码，适用于生成式视频流水线的最终渲染与后期校验阶段。
metadata:
  license: AGPL-3.0
---

# 合成导演 — 解说流水线

## 适用时机

你负责生成式解说视频的合成。手上有含完整剪辑时间线的 `edit_decisions` 和含全部文件路径的 `asset_manifest`。任务是把成片渲染出来：拼接画面、叠加音频、烧录字幕、编码到目标格式。

这是视频成为可播放文件前的最后技术阶段，一切在此汇合。

## 运行时路由（强制第一步）

先读 `edit_decisions.render_runtime`。它在提案阶段锁定，不得静默更改。本技能后续步骤（Remotion public/ 暂存、词级字幕烧录等）都假设 `render_runtime="remotion"`，这是数据驱动解说的默认值。

- **`render_runtime="hyperframes"`** —— HTML/CSS/GSAP 渲染。不要走下面的 Remotion 专属步骤，改为读 `skills/core/hyperframes.md`、`.agents/skills/hyperframes/SKILL.md`、`.agents/skills/hyperframes-cli/SKILL.md`。原样把 edit_decisions 传给 `video_compose` —— 它会委派给 `hyperframes_compose`，在 `projects/<name>/hyperframes/` 下生成工作区，跑 `lint → validate → render`，返回 MP4。lint 与 validate 都必须通过才能渲染；迭代期对比度可延后，但最终交付不行。
- **`render_runtime="ffmpeg"`** —— 简单拼接/裁剪。直接调 `video_compose`；此运行时被显式锁定时它不会自动升级到 Remotion。
- **运行时不可用** —— 按 AGENT_GUIDE.md > “Escalate Blockers Explicitly” 明确上报阻塞，取得用户批准（在 decision_log 记为 `render_runtime_selection` 决策）后再切换。

`final_review.checks.promise_preservation.render_runtime_used` 必须等于实际使用的运行时；除非有获批决策授权切换，`runtime_swap_detected` 必须为 `false`。

**把 `proposal_packet` 传给 `video_compose.execute()`**，这样工具内的切换检测才能真正触发。不传的话 `runtime_swap_check` 会被报成 `skipped`，你只能靠审阅技能的跨产物比对。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 决定渲染什么 |
| Playbook | 当前生效的风格 playbook | 质量目标 |
| 工具 | `video_compose`、`audio_mixer` | 渲染能力 |
| 媒体档 | `lib/media_profiles.py` | 输出格式规格（分辨率、编码、码率） |

## 流程

### 第 1 步：选择渲染策略

依据剪辑决策挑选渲染方式：

**Remotion 渲染**（默认 —— 除非明确覆盖，一律用它）：

- 动画文字卡、数据卡、图表场景
- 复杂转场（morph、zoom、ken-burns）
- 程序化动态图形
- 音频嵌入（旁白 + 音乐，带淡入淡出/音量）
- 通过 CaptionOverlay 组件实现词级字幕
- 最适合：所有解说视频，无论图基还是动画密集型

**FFmpeg 管线**（兜底 —— 仅当 Remotion 不可用）：

- 静态图加 Ken Burns
- 音频叠层
- SRT 字幕烧录
- 最适合：没装 Node.js/Remotion 的环境

**重要：用 Remotion 时，以下全部走 Remotion，不走 FFmpeg：**

- 音频（旁白 + 音乐）→ Remotion 的 `audio` prop，不用外部 `audio_mixer`
- 字幕 → Remotion 的 `captions` prop（词级），不用 FFmpeg 烧 SRT
- 文字叠层（CTA、标题）→ Remotion 的 `text_card` cut 类型，不用 AI 生成图像

### 第 2 步：音频获取（旁白、音乐、字幕）

渲染前先向用户呈现音频选项并取得偏好。

**向用户呈现：**

> **本视频的音频设置：**
>
> **旁白：** 我可以用 OpenAI TTS（`gpt-4o-mini-tts` —— $0.015/分钟，6 种音色，支持声音指导）生成 TTS 旁白。你想要哪种音色和语气？我会根据视频主题提议一个，或你自选：
> - `onyx` —— 低沉、权威（纪录片、科技）
> - `echo` —— 共鸣、未来感（产品广告、科幻）
> - `nova` —— 明亮、有活力（欢快、解说）
> - `fable` —— 温暖、叙事（故事、教育）
> - `shimmer` —— 表现力强、温暖（自然、生活方式）
> - `alloy` —— 中性、平衡（通用）
>
> **音乐：** 我可以自动从 Pixabay 找免版税背景音乐（无需密钥）。若有 `FREESOUND_API_KEY`，还能搜 Freesound 作备份。
>
> **字幕：** 我会对最终旁白用 WhisperX 转写生成词级字幕，通过 Remotion captions 烧进视频。
>
> 要我按推荐继续，还是调整什么？

**用户确认后：**

1. **写带时长预算的旁白脚本**（见场景导演第 4b 步）：
   - 从 cuts 计算视频时长
   - 按视频时长 85-90% 预算
   - 纪录片 2.0-2.5 词/秒，活力型 2.5-3.0
   - 生成 TTS 前先核字数

2. **生成 TTS 旁白：**

   ```python
   from tools.audio.openai_tts import OpenAITTS
   result = OpenAITTS().execute({
       'text': narration_script,
       'voice': '<user-chosen or agent-recommended>',
       'instructions': '<voice direction matching video tone>',
       'output_path': 'path/to/narration.mp3',
   })
   # 关键：核对 result.data['audio_duration_seconds'] 与视频时长
   # 旁白超出视频 >1s 就缩短脚本重新生成
   ```

3. **下载背景音乐：**

   ```python
   from tools.audio.pixabay_music import PixabayMusic
   result = PixabayMusic().execute({
       'query': '<mood/genre matching video topic>',
       'min_duration': video_duration_seconds,
       'max_duration': 300,
       'output_path': 'path/to/music.mp3',
   })
   ```

4. **用 WhisperX 生成字幕：**

   ```python
   from tools.analysis.transcriber import Transcriber
   result = Transcriber().execute({
       'input_path': 'path/to/narration.mp3',
       'model_size': 'base',
       'language': 'en',
   })
   # 把 word_timestamps 转成 Remotion caption 格式：
   # [{ "word": "Hello", "startMs": 0, "endMs": 340 }, ...]
   ```

5. **组装带音频配置的 composition JSON：**

   ```json
   {
     "audio": {
       "narration": { "src": "path/to/narration.mp3", "volume": 1 },
       "music": { "src": "path/to/music.mp3", "volume": 0.1, "fadeInSeconds": 2, "fadeOutSeconds": 3 }
     },
     "captions": [ ... word-level captions from WhisperX ... ]
   }
   ```

### 第 3 步：准备渲染输入

对剪辑决策里的每个 cut：

1. 核对该源资产在声明路径存在
2. 检查资产尺寸/时长是否符合预期
3. 准备变换参数（缩放、位置、裁剪）

音频方面：

1. 用 `audio_probe` 核对旁白时长在视频时长内
2. 核对音乐时长覆盖视频时长
3. 从剪辑决策准备闪避参数

### 第 3 步（续）：确定输出档

从 brief 产物读目标平台，映射到媒体档：

| 平台 | 档 | 分辨率 | 说明 |
|----------|---------|-----------|-------|
| YouTube | `youtube_landscape` | 1920x1080 | 多数解说默认 |
| TikTok/Reels | `tiktok` | 1080x1920 | 竖屏，需重构图 |
| Twitter/X | `twitter_landscape` | 1280x720 | 较短格式 |
| LinkedIn | `linkedin` | 1920x1080 | 职场语境 |

用 `ffmpeg_output_args(get_profile(name))` 取精确编码参数。

### 第 4 步：渲染视频

调用 `video_compose`：

```
{
  "operation": "render",
  "edit_decisions": <edit_decisions artifact>,
  "asset_manifest": <asset_manifest artifact>,
  "output_profile": "youtube_landscape",
  "output_path": "renders/output.mp4",
  "options": {
    "subtitle_burn": true,
    "audio_normalize": true,
    "two_pass_encode": true
  }
}
```

若用 Remotion 处理动画段：

1. 从剪辑决策生成 Remotion composition 数据
2. 对动画段调 `video_compose` 的 `operation: "remotion_render"`
3. 用 FFmpeg 把 Remotion 输出与其余段拼起来

**零密钥 Remotion 渲染（纯组件视频）：**
当所有场景都是 Remotion 组件类型（hero_title、stat_card、bar_chart、line_chart、pie_chart、kpi_grid、comparison、callout、progress_bar、text_card），把整片作为单个 Remotion composition 用 Explainer 入口渲染。无需 FFmpeg 拼接。edit_decisions 的 cuts 数组直接映射到 Remotion props。见 `skills/core/remotion.md` 的成熟公式 —— 尤其是视觉一致性的全深色背景规则。

### 第 5 步：音频后期处理

**Remotion 路径（默认）：** 完全跳过外部音频混音。Remotion 通过 `<Audio>` 组件原生处理所有音频。在 composition props 里传音频源：

```json
{
  "audio": {
    "narration": { "src": "project/narration.mp3", "volume": 1.0 },
    "music": { "src": "project/music.mp3", "volume": 0.12, "fadeInSeconds": 1.5, "fadeOutSeconds": 2.5 }
  }
}
```

Remotion 一次渲染音频和视频 —— 无需外部混流。用 Remotion 渲染时**不要**用 `audio_mixer` 做闪避/混音。

**FFmpeg 兜底（仅当 Remotion 不可用）：**
调 `audio_mixer` 工具：

1. 按顺序叠放旁白段
2. 按 playbook 音量混入背景音乐
3. 应用闪避（旁白时音乐下沉）
4. 归一化整体音频电平
5. 输出最终混音轨
`video_compose` 会把它与视频混流。

### 第 5b 步：生成字幕（强制）

所有解说内容都必须有字幕。从旁白音频生成 —— 不要跳过。

**Remotion 路径（默认 —— 用 Remotion 渲染时）：**

1. **转写**整段旁白，用 `transcriber` 工具（whisperx）：

   ```python
   from tools.analysis.transcriber import Transcriber
   result = Transcriber().execute({
       'input_path': 'projects/<project>/assets/audio/narration_full.mp3',
       'model_size': 'base',
       'language': 'en',
       'output_dir': 'projects/<project>/assets/audio'
   })
   # result.data 含带词级时间戳的 segments
   ```

2. **转成 Remotion WordCaption 格式**（不是 SRT）：

   ```python
   captions = []
   for segment in result.data['segments']:
       for word_info in segment.get('words', []):
           captions.append({
               'word': word_info['word'],
               'startMs': int(word_info['start'] * 1000),
               'endMs': int(word_info['end'] * 1000),
           })
   ```

3. **把 captions 加进 composition props** —— 与 `cuts`、`audio` 并列：

   ```json
   {
     "cuts": [...],
     "audio": {...},
     "captions": [
       { "word": "Root", "startMs": 120, "endMs": 340 },
       { "word": "canals", "startMs": 340, "endMs": 680 }
     ]
   }
   ```

   Remotion 的 CaptionOverlay 会把这些渲染成逐词高亮字幕，用主题的 `captionHighlightColor` 与 `captionBackgroundColor`。这优于 FFmpeg 烧 SRT，因为它产生与旁白同步的动画词级高亮。

**FFmpeg 兜底（仅当 Remotion 不可用）：**

Remotion 不可用则退回 SRT 生成 + FFmpeg 烧录：

```python
from tools.subtitle.subtitle_gen import SubtitleGen
SubtitleGen().execute({
    'segments': transcription_data['segments'],
    'format': 'srt',
    'output_path': 'projects/<project>/assets/subtitles.srt',
    'max_words_per_cue': 8,
    'max_chars_per_line': 42
})
# 再用 video_compose operation='burn_subtitles' 烧录
```

**最终交付必须带字幕** —— 或 Remotion captions 或 FFmpeg 烧录。

### 第 5c 步：渲染前校验（强制）

**渲染前必跑 composition 校验器。** 它能在浪费渲染时间前抓出问题。

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    'composition_path': 'path/to/composition.json',
    'assets_root': 'remotion-composer/public',
})
# 进入渲染前 result.data['valid'] 必须为 True
# 为 False：先修报告的错误（缺资产、音画不匹配等）
```

常见抓出项：

- 旁白音频长于视频（会被截断）
- 缺图像/音频文件（渲染会失败）
- 音乐短于视频（末尾静音）

**不要跳过这一步。** 校验失败就修问题再校验，然后才渲染。

### 第 6 步：渲染后自审（强制 —— 所有子步必做）

渲染后，agent 必须在呈现给用户前**审查自己的输出**。这能抓出校验器看不到的问题（视觉质量、音画同步、字幕可读性）。

**关键：必须完成 6a 到 6e 全部子步，一个都不能跳。最常见的 agent 失误是做了 6a（抽帧）和 6c（视觉）却跳过 6b（音频转写）—— 那会漏掉完全没音频之类的灾难性问题。**

**6a. 探测渲染文件（最先 —— 其余检查的门禁）：**

```bash
ffprobe -v quiet -print_format json -show_format -show_streams rendered_video.mp4
```

核对：

- 视频流存在（codec_type: "video"）且分辨率正确
- **音频流存在（codec_type: "audio"）** —— 没有音频流就立刻停下修
- 时长在目标 ±5% 内
- 文件大小合理（非 0 字节）

**音频流缺失即说明渲染没嵌入音频。不要继续把视频呈现给用户。修好音频配置重新渲染。**

**6b. 抽取审查帧：**

```python
from tools.analysis.frame_sampler import FrameSampler
midpoints = [(cut['in_seconds'] + cut['out_seconds']) / 2 for cut in cuts]
FrameSampler().execute({
    'input_path': 'path/to/rendered_video.mp4',
    'strategy': 'timestamps',
    'timestamps': midpoints,
    'output_dir': 'path/to/review-frames',
    'format': 'png',
})
```

**6c. 转写渲染后的音频（强制 —— 不要跳）：**

```python
from tools.analysis.transcriber import Transcriber
result = Transcriber().execute({
    'input_path': 'path/to/rendered_video.mp4',
    'model_size': 'base',
    'language': 'en',
    'output_dir': 'path/to/review-frames',
})
# 返回 0 词：音频静音/缺失 —— 停下修
# 词数 < 脚本词数的 80%：音频被截断 —— 排查
```

**6d. 视觉检查 —— 逐帧看：**

- 背景色/渐变是否符合意图？（警惕深色主题视频出现白背景）
- 图像渲染正确吗？（非空白、非拉伸）
- 字幕/说明可见且间距合理吗？
- 叠层（章节标题、数据揭示）位置对吗？
- 开场画面视觉够强吗？（社交媒体缩略图很重要）
- CTA/收尾画面文字正确吗？（图像里 AI 生成的文字经常幻觉 —— 必须精确的文字用 Remotion text_card）

**6e. 音频检查 —— 把转写稿与脚本比对：**

- 旁白是否完整？（把转写最后一个词与脚本最后一个词比对）
- 末尾有词被截断吗？（旁白超出视频时长）
- 时序对齐 —— 旁白段大致对应其预期场景吗？
- 背景音乐可听见吗？（转写器可能抓不到音乐，但 ffprobe 能确认音频流）

**6f. 汇总并向用户呈现审查结果：**

> **“[视频标题]” 渲染后审查：**
>
> **文件：** [时长]s，[分辨率]，[文件大小] —— 音频流：[存在/缺失]
> **音频：** [完整/在 Xs 处截断] —— 从渲染输出转写出 [N]/[M] 词
> **画面：** [检查 N 个场景] —— [问题或“全部场景渲染正常”]
> **字幕：** [Remotion CaptionOverlay / FFmpeg SRT / 缺失] —— [词级高亮工作/有问题]
> **发现问题：** [列出问题及严重程度]
>
> **建议：** [需要修什么，若有]
>
> 要我修这些问题重渲染，还是可以定稿了？

**只有用户批准后（或 agent 发现零问题），视频才算定稿。**

### 第 6 步（旧）：文件与内容校验

**文件校验：**

- [ ] 输出文件在声明路径存在
- [ ] 文件大小合理（非 0 字节、非可疑地小）
- [ ] 文件是合法容器（ffprobe 通过）

**内容校验：**

- [ ] 时长在目标 ±5% 内
- [ ] 分辨率符合所选档
- [ ] 音频声道存在（立体声）
- [ ] 无音频削波或 > 1s 的静音间隙

**质量检查（由上面的自审覆盖）：**

- [ ] 视觉：所有场景帧已检查
- [ ] 音频：完整转写已核对
- [ ] 字幕：可见且时序正确

### 第 7 步：构建渲染报告

```json
{
  "version": "1.0",
  "outputs": [
    {
      "path": "renders/output.mp4",
      "format": "mp4",
      "codec": "h264",
      "resolution": "1920x1080",
      "fps": 30,
      "duration_seconds": 62.4,
      "file_size_mb": 45.2,
      "audio_codec": "aac",
      "audio_channels": 2,
      "render_strategy": "ffmpeg",
      "render_time_seconds": 180
    }
  ],
  "render_summary": {
    "total_cuts_rendered": 12,
    "subtitles_burned": true,
    "audio_tracks_mixed": 3,
    "target_duration_seconds": 60,
    "actual_duration_seconds": 62.4
  }
}
```

### 第 8 步：自评

打分（1-5）：

| 维度 | 问题 |
|-----------|----------|
| **可播放性** | 视频在标准播放器里无错播放吗？ |
| **时长准确度** | 实际时长在目标 ±5% 内吗？ |
| **音频质量** | 旁白清晰、音乐平衡、无削波吗？ |
| **画面质量** | 图像锐利、转场平滑、无伪影吗？ |
| **字幕准确度** | 字幕存在、可读、同步吗？ |

任一项低于 3 分，排查并重渲染。

### 第 9 步：提交

对 render_report 做 schema 校验，并通过 checkpoint 持久化。

## 常见坑

- **资产文件缺失**：开渲染前永远核对每个被引用的文件存在。渲染中途缺文件浪费时间。
- **音频同步漂移**：旁白段间的累积计时误差导致音画失步。用绝对时间戳，不用相对偏移。
- **字幕编码**：把字幕烧进视频（硬字幕）以获得最大兼容性。社交媒体别依赖软字幕。
- **单遍编码**：同文件大小下两遍编码质量更好，值得多花的渲染时间。
- **忽略媒体档**：YouTube 与 TikTok 要求差别很大。永远先查目标档。
