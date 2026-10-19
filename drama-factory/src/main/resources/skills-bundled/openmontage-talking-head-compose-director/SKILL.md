---
name: openmontage-talking-head-compose-director
version: "1.0.0"
description: 按剪辑决策渲染口播成片：套用增强链、烧录字幕与叠加层、混音并编码到目标平台规格。适用于素材与剪辑方案齐备、需要产出可交付成片并完成质检的合成阶段。
metadata:
  license: AGPL-3.0
---

# 合成导演 — 口播流水线

## 适用场景

当你已拿到剪辑决策与素材清单时，本阶段负责渲染最终口播视频：套用增强链、烧录字幕、混合音频，并编码到目标规格。

## 运行时路由（硬性约束——只能用 Remotion 或 FFmpeg）

第一阶段暂缓支持 HyperFrames。`edit_decisions.render_runtime` 只能是 `"remotion"`（首选，走 `TalkingHead` composition + `remotion_caption_burn`）或 `"ffmpeg"`（用于无 composition 的素材拼接）。

- 若 `edit_decisions.render_runtime == "hyperframes"`，立即停下，重开创意阶段并暴露该约束。悄悄改写属于治理违规。
- 依 AGENT_GUIDE.md 的“呈现两种合成运行时（硬规则）”：流水线的约束不能省去沟通环节。要向用户说明 HyperFrames 存在但不适用于本流程，并记录一条 `render_runtime_selection` 决策，写明 hyperframes `rejected_because: "TalkingHead + caption parity deferred on talking-head"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()` 以做运行时切换检测。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 校验产物 |
| 前置产物 | 剪辑决策、素材清单 | 渲染输入 |
| 工具 | `video_compose`、`audio_mixer` | 渲染 |
| 媒体规格 | `lib/media_profiles.py` | 输出格式 |

## 流程

### 第 0 步：预检

正式渲染前先校验输入，把后期修改代价高的问题提前抓出来。

1. **静音检测**——以 mark 模式跑 `silence_cutter`：
   ```
   # mark 模式只标记不删除，便于先看清静音分布
   silence_cutter.execute({
       "input_path": "<raw_footage>",
       "mode": "mark",
       "silence_threshold_db": -35,
       "min_silence_duration": 0.5
   })
   ```
   - 列出所有超过 0.5 秒的空档及其时间戳
   - 若静音总时长超过 5 秒，**建议先剪再继续**。冗长静音既费渲染时间，也会在成片里留下死段

2. **ASR 置信度检查**——扫描逐词转写：
   - 标出概率低于 0.7 的词
   - 附时间戳列出，方便用户核对
   - 常见误识别：专有名词、品牌名、领域术语

3. **按常见 ASR 错误模式自动构建纠错词典**：
   ```python
   corrections = {
       # 金融场景里易混的缩写
       "DMI": "EMI",
       "AMI": "EMI",
       # 品牌名常见错拼
       "open montage": "OpenMontage",
       "remotion": "Remotion",
       # 被 ASR 拆开的数字
       "4 -5": "4-5",
       "10 -15": "10-15",
   }
   ```
   结合视频主题扩充领域专属纠错项，应用前先把词典交给用户过目。

4. **绿幕标记**——检查场景导演第 0 步是否标记了绿/蓝幕素材。若有，注明需要走第 3c 步（绿幕合成）。

### 第 1 步：运行增强链

按以下顺序处理，工具可用时**每一步都要尝试**，无理由不得跳过。

1. **面部增强**——套用 `talking_head_standard` 预设
2. **眼部增强**——去黑眼圈 + 提亮眼周
3. **调色**——套用某个 profile
4. **音频增强**——降噪、归一化

**眼部增强**——面部增强之后总要尝试，对网络摄像头或手机素材效果明显：
```
# 去黑眼圈并提亮眼周，强度保持轻微
eye_enhance.execute({
    "input_path": "<face_enhanced_video>",
    "output_path": "<project>/assets/video/eye_enhanced.mp4",
    "operations": ["dark_circles", "brighten_eyes"],
    "dark_circle_intensity": 0.4,       # 0-1，轻微更好
    "eye_brighten_intensity": 0.3,
})
```
**注意：**强度保持低位（0.2-0.5）。过度处理会让眼睛失真。若工具失败（如未装 MediaPipe），记录降级方案并沿用面部增强后的视频。

### 第 1b 步：变速（如有需求）

用户想快放或慢放时用 `video_trimmer`：
```
# speed 操作按倍数调整整段视频时长
video_trimmer.execute({
    "operation": "speed",
    "input_path": "<enhanced_video>",
    "output_path": "<project>/assets/video/speed_adjusted.mp4",
    "speed_factor": 1.25    # 0.5x（慢）、1.25x、1.5x、2x（快）
})
```

常见倍率：

| 倍率 | 用途 |
|------|------|
| `0.5` | 慢动作，营造戏剧感 |
| `1.0` | 原速不变 |
| `1.25` | 略快——节奏更紧但听感自然 |
| `1.5` | 明显加快——适合回顾或浓缩内容 |
| `2.0` | 双倍速——延时效果 |

变速应在增强之后、重构图之前执行。

### 第 2 步：自动重构图（若目标平台需要）

目标平台要求不同画幅（如 Instagram Reels 需 9:16）时用 `auto_reframe`：

```
# 自动跟踪人脸并保持主讲居中，平滑镜头移动
auto_reframe.execute({
    "input_path": "<enhanced_video>",
    "output_path": "<project>/renders/reframed.mp4",
    "target_aspect": "portrait",       # Reels/TikTok/Shorts 用 9:16
    "smoothing_window": 15,            # 平滑镜头移动
    "face_padding": 0.4,              # 人脸周围留 40% 边距
})
```

**画幅预设：**

| 预设 | 比例 | 平台 |
|------|------|------|
| `portrait` | 9:16 | Instagram Reels、TikTok、YouTube Shorts |
| `square` | 1:1 | Instagram 信息流 |
| `landscape` | 16:9 | YouTube、LinkedIn |
| `vertical_4_5` | 4:5 | Instagram 竖版帖 |

工具会自动做人脸检测并让讲者居中；未装 MediaPipe 时退化为居中裁剪。

**注意：**重构图要在面部增强与调色之后、烧录字幕之前执行，因为字幕需要按最终画幅定位。

### 第 2b 步：构建 ASR 纠错词典

烧字幕前，扫描转写文本找可能的误识别，常见有：

- 产品/品牌名："cloud" → "Claude"、"co-pilot" → "Copilot"、"remotion" → "Remotion"
- 技术术语："pythonic" 被听成 "pathonic"、"API" 被听成 "a pie"
- 讲者姓名或公司名
- 领域专属行话

构建纠错词典：
```python
corrections = {
    "cloud": "Claude",
    "co pilot": "Copilot",
    "open montage": "OpenMontage",
}
```

把该词典同时传给 `subtitle_gen`（若生成 SRT）与 `remotion_caption_burn`（若用 Remotion 字幕）。哪怕一处都不用改，也要显式传一个空字典 `{}`，以表明已核查过。

### 第 3 步：烧录字幕

**始终使用 Remotion 的 TikTok 式字幕**（逐词高亮）。这是默认且首选的方式。除非 Remotion 完全不可用，否则不要退回 FFmpeg ASS 字幕。

**Remotion 字幕要求：**

- **自动探测视频尺寸**——不要硬编码宽高。用 `visual_qa` probe 或 ffprobe 取真实尺寸再传给渲染
- **按实际时长设置 `--frames`**——由 probe 计算：`frames = duration_seconds * fps`，绝不用写死的帧数
- 逐词高亮，高亮色用 `highlight_color`
- 字幕放在画面底部，避开人脸

```
# 烧录逐词高亮字幕，并传入纠错词典与样式参数
remotion_caption_burn.execute({
    "input_path": "<reframed_or_enhanced_video>",
    "output_path": "<project>/assets/video/captioned.mp4",
    "segments": <transcript_segments_from_asset_manifest>,
    "corrections": {"cloud": "Claude", "co-pilot": "Copilot"},
    "words_per_page": 4,
    "font_size": 52,
    "highlight_color": "<theme_accent>",
})
```

**仅在 Remotion 完全不可用时退而求其次：**用 `video_compose` 的 `burn_subtitles` 操作，并提醒用户此模式下没有逐词高亮。

**关键：9:16 竖版视频的字幕定位（仅限 FFmpeg 降级路径）。**
字幕必须落在画面底部 20% 内。以 1920 高为例，即 `MarginV=160` 或更大。FFmpeg 默认把字幕放中间，会挡住人脸，必须覆盖。

竖版口播的 FFmpeg 字幕样式串：
```
"FontName=Arial,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,MarginV=160,Alignment=2"
```

**绝不**使用默认字幕位置，**绝不**把字幕放画面中部或上半部。视觉质检时若发现字幕压在脸上，必须重新渲染并修正位置。

### 第 3b 步：烧录叠加图形（若分镜方案含叠加层）

若分镜方案含叠加场景（文字卡、数据卡、图表、对比、提示框），把它们与字幕一并传给 `remotion_caption_burn`。**字幕与叠加层在同一次 Remotion 渲染里完成**，无需额外的 FFmpeg 合成。

**原理：**TalkingHead Remotion composition 渲染三层：

1. **视频**（底层）——口播画面
2. **叠加层**（中层）——定位好的图表、数据、提示，带淡入淡出
3. **字幕**（顶层）——逐词高亮，始终可见

**把第 3 步与 3b 合并为一次 `remotion_caption_burn` 调用：**
```
remotion_caption_burn.execute({
    "input_path": "<reframed_or_enhanced_video>",
    "output_path": "<project>/assets/video/captioned.mp4",
    "segments": <transcript_segments>,
    "corrections": {"cloud": "Claude"},
    "words_per_page": 4,
    "font_size": 52,
    "highlight_color": "<theme_accent>",
    "overlays": [
        {
            "id": "term-agentic-ai",
            "type": "callout",
            "text": "智能体：能自主朝目标行动的软件",
            "callout_type": "info",
            "in_seconds": 22.0,
            "out_seconds": 26.0,
            "position": "lower_third",
            "backgroundColor": "<theme_background>",
            "accentColor": "<theme_accent>"
        },
        {
            "id": "stat-market-size",
            "type": "stat_card",
            "stat": "$4.8B",
            "subtitle": "全球 AI 智能体市场（2026）",
            "in_seconds": 35.0,
            "out_seconds": 39.0,
            "position": "upper_third",
            "accentColor": "<theme_secondary_accent>"
        },
        {
            "id": "chart-growth",
            "type": "bar_chart",
            "chartData": [
                {"label": "2023", "value": 1.2},
                {"label": "2024", "value": 2.1},
                {"label": "2025", "value": 3.5},
                {"label": "2026", "value": 4.8}
            ],
            "title": "AI 智能体市场规模（十亿美元）",
            "in_seconds": 40.0,
            "out_seconds": 45.0,
            "position": "lower_third",
            "chartColors": ["<theme_accent>", "<theme_secondary_accent>", "<theme_tertiary_accent>", "<theme_supporting_accent>"]
        }
    ]
})
```

**叠加层位置选项：**

- `lower_third` → 底部区域，位于字幕上方（默认，对多数叠加最稳妥）
- `upper_third` → 顶部区域（讲者居中或偏下时适合放数据）
- `left_panel` → 画面左侧 45%（与讲者并排）
- `right_panel` → 画面右侧 45%
- `full_overlay` → 带深色底的全屏（慎用，最多 1-2 秒）

**叠加类型 → 必填属性**（同素材导演的映射）：

| 类型 | 必填属性 |
|------|----------|
| `text_card` | `text` |
| `stat_card` | `stat`、`subtitle`（可选） |
| `callout` | `text`、`callout_type`（info/warning/tip/quote） |
| `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` |
| `bar_chart` | `chartData`（`{label, value}` 数组） |
| `line_chart` | `chartSeries`（`{name, data: number[]}` 数组） |
| `pie_chart` | `chartData`（`{label, value}` 数组） |
| `kpi_grid` | `chartData`（`{label, value}` 数组） |
| `hero_title` | `text`、`subtitle`（可选） |
| `section_title` | `text`、`subtitle`（可选） |
| `stat_reveal` | `text`（数据）、`subtitle`（标签） |

**注意：**做过变速后，叠加层时间戳需重算：`adjusted_time = original_time / speed_factor`。

**降级方案（无 Remotion）：**Remotion 不可用时 `remotion_caption_burn` 只退化为 FFmpeg 字幕，叠加层不会渲染——需明确告知用户叠加层依赖 Remotion。

### 第 3c 步：绿幕合成（若为绿幕素材）

若素材是绿/蓝幕（场景导演第 0 步已检出），按以下流程：

1. **运行 `green_screen_processor`** 抠掉绿/蓝幕：
   ```
   # auto 模式自动判断绿幕还是蓝幕并选用相应键控
   green_screen_processor.execute({
       "input_path": "<enhanced_video>",
       "output_path": "<project>/assets/video/greenscreen_removed.mp4",
       "method": "auto"
   })
   ```

2. **用 Explainer composition 渲染 Remotion 动态背景**：
   ```
   # 渲染含渐变网格、漂浮光斑、细网格的动态背景，别用纯色 #0F172A
   npx remotion render src/index.ts Explainer --props='{"duration":VIDEO_DURATION}' --output=<project>/assets/video/animated_bg.mp4
   ```
   AnimatedBackground 提供带漂浮光斑和细网格的专业渐变网格，远胜纯色。

3. **运行 `green_screen_composite`** 把讲者叠到动态背景上：
   ```
   # 默认 news_anchor 布局：讲者居中偏下，背景铺满
   green_screen_composite.execute({
       "foreground_path": "<greenscreen_removed_video>",
       "background_path": "<animated_bg>",
       "output_path": "<project>/assets/video/composited.mp4",
       "layout": "news_anchor"
   })
   ```
   默认布局为 `news_anchor`（讲者居中偏下，背景铺满）。按第 0 步检出的讲者位置调整布局。

4. **用 Remotion TalkingHead composition 烧字幕**（不用 FFmpeg ASS）：
   ```
   # 对合成后的视频烧录逐词高亮字幕与叠加层
   remotion_caption_burn.execute({
       "input_path": "<composited_video>",
       "output_path": "<project>/assets/video/captioned.mp4",
       "segments": <transcript_segments>,
       "corrections": <corrections_dict>,
       "words_per_page": 4,
       "font_size": 52,
        "highlight_color": "<theme_accent>",
       "overlays": <overlay_list_from_scene_plan>
   })
   ```

5. **混入背景音乐**（压低至 15% 音量垫在语音下）：
   ```
   # duck 操作在有人声时自动压低背景音乐音量
   audio_mixer.execute({
       "operation": "duck",
       "video_path": "<captioned_video>",
       "music_path": "<bg_music>",
       "music_volume": 0.15,
       "output_path": "<project>/assets/video/with_music.mp4"
   })
   ```

6. **按目标平台规格做最终编码**（见下方第 6 步）。

### 第 3d 步：构建展示卡（若为多片段合集）

若成片是含展示片段的多片段合集，对每个展示片段用 `showcase_card`：
```
# 生成带标题与说明的 9:16 加黑边卡片
showcase_card.execute({
    "input_path": "<showcase_video>",
    "output_path": "<project>/assets/video/sc_<name>.mp4",
    "title": "VIDEO TITLE",
    "subtitle": "Description | Style | Cost: $0.15",
    "background_color": "0x0A0F1A",
})
```
这会产出带排版文字的 9:16 加黑边卡片。

### 第 4 步：多片段拼接（如适用）

若成片含多个片段（如口播 + 展示片段），用 `video_stitch`：
```
# 按顺序拼接片段，片段间加过渡
video_stitch.execute({
    "operation": "stitch",
    "clips": ["intro.mp4", "showcase1.mp4", ..., "outro.mp4"],
    "output_path": "<project>/renders/assembled.mp4",
    "transition": "crossfade",         # 或 "fade" 走黑场
    "transition_duration": 0.5,
})
```
**过渡选择建议：**

- `crossfade`（交叉溶解）：口播与展示之间平滑过渡
- `fade`（走黑场）：展示片段之间短暂黑场
- 可混用：口播→展示用 `crossfade`，展示之间用 `fade`

### 第 5 步：混合音频

用 `audio_mixer` 铺背景音乐：

**多片段合集**——用 `segmented_music` 只在口播段落播音乐：
```
# 仅在指定时间段播放背景音乐并加淡入淡出
audio_mixer.execute({
    "operation": "segmented_music",
    "video_path": "<assembled_video>",
    "music_path": "<bg_music>",
    "music_volume": 0.20,
    "segments": [
        {"start": 0, "end": 17.0},       # 开场语音
        {"start": 167.0, "end": 175.0}    # 收尾语音
    ],
    "fade_duration": 0.5,
    "output_path": "<project>/renders/final.mp4",
})
```

**单段口播**——用 `duck` 或 `full_mix`：

- 将原音轨与背景音乐叠加
- 有音乐时施加压低处理
- 对最终电平做归一化

### 第 6 步：最终编码——强制

**不得跳过。**不做最终编码，输出文件会过大，且可能在目标平台上无法正常播放。

用 `video_compose` 的 `encode` 操作：

- 套用目标媒体规格（youtube_landscape、tiktok、instagram_reels 等）
- 两遍编码以保证画质

**目标文件大小：**

| 平台 | 最长时长 | 目标体积 |
|------|----------|----------|
| Instagram Reels | 90 秒 | < 50 MB |
| TikTok | 10 分钟 | < 100 MB |
| YouTube Shorts | 60 秒 | < 40 MB |
| YouTube | 不限 | < 25 MB/分钟 |

若超出目标，降低码率重新编码。一条 66 秒的 Instagram Reel 若到 76 MB 就不可接受——应压到 30 MB 以内。

```
# 按 instagram_reels 规格编码，指定音视频码率
video_compose.execute({
    "operation": "encode",
    "input_path": "<mixed_video>",
    "output_path": "<project>/renders/final.mp4",
    "media_profile": "instagram_reels",
    "video_bitrate": "4M",
    "audio_bitrate": "192k",
})
```

### 第 7 步：视觉质检

宣布完成前用 `visual_qa` 校验：
```
# 在若干时间点抽帧用于人工核查
visual_qa.execute({
    "operation": "review",
    "input_path": "<final_video>",
    "timestamps": [3.0, 10.0, 25.0, 50.0, 100.0, 170.0],
})
```
然后**逐张查看抽出的帧**，确认：

- 字幕可见且位于底部（未压在脸上）
- 面部增强已生效（肤质平滑而非过度磨皮）
- 过渡干净（切换点无异常）
- 展示卡文字清晰可读

再做 probe 校验：
```
# 校验分辨率、音轨与像素格式是否符合预期
visual_qa.execute({
    "operation": "probe",
    "input_path": "<final_video>",
    "expected": {
        "width": 1080, "height": 1920,
        "has_audio": true,
        "pixel_format": "yuv420p"
    },
})
```

并检查音量电平：
```
# 抽点读取音频电平，确认音乐位置正确
visual_qa.execute({
    "operation": "audio_levels",
    "input_path": "<final_video>",
    "timestamps": [5.0, 50.0, 170.0],
})
```
要确认：口播段音量高于展示段（说明音乐铺放位置正确）。

### 第 8 步：构建渲染报告

记录输出信息：路径、格式、分辨率、时长、文件体积、质检结果。

### 第 9 步：自检

| 检查项 | 自问 |
|--------|------|
| **可播放性** | 视频能无错播放吗？ |
| **画质** | 增强是否处理得当？ |
| **构图** | 若做过重构图——人脸居中吗？有无重要内容被裁掉？ |
| **音频** | 语音清晰且电平均衡吗？音乐只在预期段落出现吗？ |
| **字幕** | 字幕在底部可见吗？没挡脸吗？逐词高亮生效吗？ |
| **过渡** | 过渡干净吗？类型用对了吗（crossfade 还是 fadeblack）？ |
| **展示卡** | 展示卡黑边正确、文字清晰可读吗？ |

### 第 10 步：提交

按 schema 校验 render_report，并通过 checkpoint 持久化。
