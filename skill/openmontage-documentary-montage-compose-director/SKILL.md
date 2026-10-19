---
name: openmontage-documentary-montage-compose-director
version: "1.0.0"
description: 把纪录片蒙太奇的剪辑决策渲染成成片，统一画布、套用 LUT 调色、一次性完成混音与片尾卡合成，适用于时间线锁定后的合成阶段。
metadata:
  license: AGPL-3.0
---

# 合成总监 · 纪录片蒙太奇流水线

## 适用时机

时间线已经存在。每个切点的入出点已定，转场已选，配乐床已锁定。接下来要渲染成片，并施加"调性平滑"处理（统一裁切 + LUT + 混音），让年代混杂的语料看起来像同一部片子。

产出是单个 mp4 加上一份 `render_report` 产物。

## 运行时路由（硬性约束）

本流水线当前强制要求 `render_runtime="remotion"`。片尾卡栈（ProRes 4444 叠加合成到最终画面，或 concat 回退）依赖 Remotion 的 `CinematicRenderer` 组合及其保留 alpha 的渲染路径。HyperFrames 的片尾卡对等能力明确属于 Wave 3 / 延后工作（见 `skills/core/hyperframes.md` → "What stays Remotion-only in Phase 1"）。

- 若 `edit_decisions.render_runtime` 不是 `remotion`，立刻停下。这是严重的治理违规。把冲突上报用户，把决策退回提案阶段重新锁定 `render_runtime="remotion"`，在 decision_log 记录一条 `render_runtime_selection` 更正，然后恢复。
- 绝不悄悄改写 edit_decisions 里的 render_runtime 继续。纪录片承诺（运动主导、情绪驱动、统一调色）由 Remotion 栈承载，而那正是用户批准的东西。
- 把 `proposal_packet` 传给 `video_compose.execute()`，让工具内的 `runtime_swap_detected` 检查主动确认运行时全程保持 `remotion`。本流水线上该检查显示 `skipped` 说明你忘了传提案产物。

## 前置依赖

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/render_report.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["edit"]["edit_decisions"]` | 切点、转场、音乐、元数据提示 |
| 前置产物 | `state.artifacts["assets"]["asset_manifest"]` | 文件路径、时长、提供方 |
| 工具 | `video_compose`（Remotion 优先 + FFmpeg 回退） | 主渲染引擎 |
| 工具 | `audio_mixer` | 音乐淡入淡出、静音窗、L-cut |
| 工具（可选） | `color_grade` | 跨年代片段的统一 LUT |
| 工具（可选） | `video_trimmer`、`video_stitch` | 需要时的底层辅助 |

## 心智模型

多数流水线把合成当作无聊的导出步骤。对纪录片蒙太奇来说它是创作步骤：最后一次让调色与混音把来源迥异的素材调和成一部作品的环节。

有三件事只能在这里发生：

1. **统一画幅与黑边。** Pexels 1920x1080、Prelinger 640x480 4:3、NASA 1280x720 都要落在同一张画布上。
2. **统一调色。** 整条时间线套同一个 LUT，1962 年的家庭录像才能与 2023 年的厨房画面并置而不跳脱。
3. **混音。** 音乐电平、静音窗、L-cut 环境声延续、最终淡出——手持时间线一次性做完。

## 流程

### 0. 硬性要求检查

读 `brief` 与 `edit_decisions.metadata`，确认是否有硬性要求。若 brief 说了"无旁白"而剪辑里莫名出现旁白轨，停下询问。不要在契约违规之上继续渲染。

同时确认 `edit_decisions.renderer_family` 锁定为 `documentary-montage`，且所选渲染引擎保持该决策。按本仓库治理模型，`video_compose` 在 `operation="render"` 时 Remotion 优先，即使素材主导的作品也一样。

- Remotion 可用：走常规 `render` 路径，保持已批准的渲染器家族。
- Remotion 不可用：不要悄悄降级到 FFmpeg。上报引擎变更，获得批准后再走低层 FFmpeg 路径。

### 1. 确定画布

读 `brief.target_platform`：

| 目标 | 画布 | 黑边 |
|------|------|------|
| `social_short`（Instagram/TikTok） | 1080x1920（9:16） | 上下裁切；每条片段居中对齐 |
| `youtube` / `generic` | 1920x1080（16:9） | 无；可选 2.35:1 上下黑边营造电影感 |
| `linkedin` | 1920x1080（16:9） | 无 |

时间线中每条片段都必须缩放/裁切到该画布。`social_short` 通常意味着对 16:9 素材做中心裁切。`youtube` 若采用 2.35:1 电影黑边，则在 1920x1080 画布上下各补 140px 黑边。

在 `render_report.metadata.canvas` 与 `render_report.metadata.letterbox` 中记录该决定。

### 2. 为 `video_compose` 构建拼接计划

剪辑产物给出带入出点、转场与源 asset_id 的切点列表。遍历 asset_manifest，把每个 asset_id 解析为真实文件路径，再构建渲染计划。

对这种流水线，最干净的路径是：

```python
video_compose.execute({
    "operation": "render",
    "output_path": "projects/<name>/renders/final.mp4",
    "edit_decisions": edit_decisions_with_renderer_family,
    "asset_manifest": asset_manifest,
})
```
该调用把剪辑决策与素材清单交给渲染引擎，输出成片 mp4。

具体字段名以渲染时 `video_compose` 的实时 schema 为准——写调用前先查工具的 `agent_skills`（如有）。不要臆造参数。

`edit_decisions_with_renderer_family` 指保留 `renderer_family = "documentary-montage"` 原样的常规剪辑产物。

### 3. 用 LUT 统一调色，不逐条处理

读 `edit_decisions.metadata.grade_profile`，映射到 LUT 文件：

| 档位 | LUT | 适用 |
|------|-----|------|
| `warm_film_100` | 复古胶片暖调，轻微提亮 | 挽歌、梦幻 |
| `cool_archive_60` | 冷高光，压暗黑位 | 紧迫、戏谑 |
| `neutral_doc_20` | 近乎无色的中性平衡 | 庄严 |
| `bleach_bypass_80` | 去饱和，高对比 | 戏谑、纪录片式冷峻 |

档位不在样式库中时，用 `neutral_doc_20` 并在 `warnings` 中记录。不要尝试自动调色——LUT 才是调性平滑处理的核心。

在合成层面施加 LUT，不要逐条处理。一个 LUT，一条时间线，一个统一外观。这才是让 1962 年的 Prelinger 片段与 2023 年的 Pexels 片段像同一部片子的关键。

### 4. 在合成阶段一次性混音

剪辑产物已经定好了音量、淡入淡出、静音窗与 L-cut 音效层。你的工作是忠实执行：

- 配乐床音量取 `edit_decisions.audio.music.volume`（默认 0.7）。
- 按 `fade_in_seconds` 淡入，按 `fade_out_seconds` 淡出。
- 静音窗：窗内降到 0.0，之后带 0.2s 延迟恢复。
- L-cut 音效层：以 0.5-0.7 音量混入，位于音乐之下。
- 除非 `edit_decisions.audio.narration` 中明确存在，否则不加旁白。

**音乐是强制项。** 若剪辑中没有音乐条目，查 brief：

- `brief.metadata.music_plan.source == "none"` 且带 `opt_out_reason` → 用户明确选择退出。静音渲染，并在 `render_report.warnings` 中记录。
- 其他情况 → 停下。这是契约违规。渲染前上报用户。音乐强制类 brief 出现静音渲染，是本流水线最响亮的失败模式。

不要为了"填补空白"加环境噪声。

### 4b. 用 Remotion 渲染片尾卡

片尾卡通过 Remotion **单独**渲染，与 FFmpeg 主体分离。这样两个渲染引擎（FFmpeg 处理素材，Remotion 处理排版）界限清晰。合成方式取决于 `brief.metadata.end_tag_plan.mode`。

读 `brief.metadata.end_tag_plan`：

```json
{
  "text": "WE BUILT BOTH WITH THE SAME HANDS.",
  "palette": "warm_ivory_on_black",
  "duration_seconds": 5.5,
  "render_engine": "remotion",
  "component": "EndTag",
  "mode": "overlay"
}
```
上例描述片尾卡文案、配色、时长、渲染引擎、组件名与合成模式。

#### 路径 A —— overlay 模式（默认）

文字淡入叠在主体素材的最后几个镜头上。这是默认方式，效果更电影化——排版出现在实拍画面上，而不是切到黑卡。

执行：

1. 用 FFmpeg 合成主体（切点 + LUT + 音乐 + 静音窗），保存为 `projects/<name>/renders/body.mp4`。记下主体 fps。
2. 计算 `durationInFrames = round(duration_seconds × body_fps)`。
3. 用 Remotion CLI 渲染带 alpha 的片尾卡：
   ```bash
   npx remotion render src/index.tsx EndTagOverlay \
     projects/<name>/renders/end_tag_overlay.mov \
     --codec=prores --prores-profile=4444 \
     --pixel-format=yuva444p10le --image-format=png \
     --props='{"text":"...","palette":"...","overlay":true,
               "fadeInSeconds":1.0,"holdSeconds":3.0,"fadeOutSeconds":1.5}'
   ```
   该命令用 `EndTagOverlay` 组合以 overlay 模式渲染 ProRes 4444 MOV，带真实 alpha 通道，画布须与主体一致。
4. 计算叠加偏移：
   - 若 `edit_decisions.end_tag.offset_seconds` 存在则使用。
   - 否则自动计算：`offset = body_duration - tag_duration`，使片尾卡的淡出与主体收尾淡出对齐。
5. 用 FFmpeg 的 `-itsoffset` 做 overlay 合成：
   ```bash
   ffmpeg -y \
     -i body.mp4 \
     -itsoffset {offset} -i end_tag_overlay.mov \
     -filter_complex "[0:v][1:v]overlay=0:0:format=auto:eof_action=pass[v]" \
     -map "[v]" -map "0:a" \
     -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
     -c:a aac -b:a 192k \
     projects/<name>/renders/final.mp4
   ```
   该命令把带 alpha 的片尾卡叠加到主体视频上并输出最终 mp4；`eof_action=pass` 让主体在叠加层结束后继续，淡入淡出由叠加层自身的 alpha 负责。

验证：从叠加区域抽一帧（如 `offset + 2s`），确认文字显示在画面上而非黑底。若显示黑底，说明 alpha 通道丢失——用 `--image-format=png` 重渲。

#### 路径 B —— concat 模式

经典尾卡：主体之后追加不透明黑卡。仅当 `end_tag_plan.mode == "concat"` 时使用。

执行：

1. 按上文合成主体。
2. 渲染不透明 MP4 片尾卡：
   ```bash
   npx remotion render src/index.tsx EndTag \
     projects/<name>/renders/end_tag.mp4 \
     --props='{"text":"...","palette":"...","durationInFrames":132}'
   ```
   该命令以 `EndTag` 组合渲染不透明片尾卡 mp4；5.5 秒 @ 24fps 即 132 帧，画布须与主体一致。
3. 拼接主体与片尾卡：
   ```bash
   ffmpeg -f concat -safe 0 -i list.txt -c copy final.mp4
   ```
   该命令按列表无损拼接主体与片尾卡；编解码不匹配时改为重编码。

#### 两种模式共同规则

**片尾卡是强制项。** 唯一跳过方式是用户显式选择退出，记录为 `end_tag_plan: null` 并附 `end_tag_opt_out_reason`。若 brief 有片尾卡计划而你跳过了，属于契约违规。停下并上报，然后再定稿。

在 `render_report` 中记录：

- `end_tag_rendered: true | false`
- `end_tag_mode: "overlay" | "concat"`
- `end_tag_path: "projects/<name>/renders/end_tag_overlay.mov"`（concat 模式为 `.mp4`）
- `end_tag_offset_seconds: <number>`（仅 overlay 模式）
- `end_tag_text: "..."`（审计用）

若 brief 说"无音乐"，剪辑里也确无音乐条目且 `music_plan.source == "none"` 带选择退出理由，则静音渲染。不要为了"填补空白"加环境噪声。

### 5. 按纪录片规格渲染

推荐编码设置：

| 字段 | 值 | 理由 |
|------|-----|------|
| 编解码 | `libx264`（H.264） | 通用、体积小 |
| 像素格式 | `yuv420p` | 通用兼容 |
| CRF | `18` | 成片视觉无损 |
| 帧率 | `24` | 电影感。不要把 24 升到 30。 |
| 音频编解码 | `aac` | 通用 |
| 音频码率 | `192k` | 对配乐床友好 |

若源片段是 30fps 而画布是 24fps，让渲染管线均匀丢帧——不要混合。对混合来源素材做运动插值效果很差。

### 6. 渲染后验证

渲染成功后，实际探测输出文件并检查：

- **时长。** 应等于 `sum(out - in for cut in cuts) + 淡入淡出`，误差 ±0.5s。
- **分辨率。** 应与画布一致。
- **音频存在性。** 计划中有音乐则输出必须有音频流；计划为静音则确认无音频。
- **首尾帧。** 打开文件，跳到 0s 与 duration-0.1s。首帧应为淡入；末帧应为（或正在淡向）黑场。
- **静音窗。** 跳到静音窗起点，波形上音量应明显下降。

把验证结果记入 `render_report.verification_notes`。

### 7. 输出 render_report

```json
{
  "version": "1.0",
  "outputs": [
    {
      "path": "projects/<name>/renders/final.mp4",
      "format": "mp4",
      "codec": "h264",
      "audio_codec": "aac",
      "resolution": "1920x1080",
      "fps": 24,
      "duration_seconds": 89.8,
      "file_size_bytes": 18234112,
      "platform_target": "youtube"
    }
  ],
  "render_time_seconds": 42.3,
  "warnings": [],
  "verification_notes": [
    "Duration within +0.2s of planned",
    "First frame is black fade-in as specified",
    "Silence window 54-56s confirmed (music -60dB)",
    "Last frame fades to black at 89.0s"
  ],
  "render_grammar": "documentary-montage",
  "metadata": {
    "pipeline": "documentary-montage",
    "canvas": { "width": 1920, "height": 1080 },
    "letterbox": "2.35:1",
    "lut": "warm_film_100",
    "music_present": true
  }
}
```
上例给出输出文件属性、渲染耗时、警告、验证备注与元数据（画布、黑边、LUT、音乐有无）。

### 8. 质量门

- 输出文件存在且可播放。
- 时长与 `brief.duration_seconds`（含主体与片尾卡）误差在 ±1s 内。
- 分辨率与 `target_platform` 画布一致。
- LUT 已施加（或记录了警告）。
- **音乐存在**，除非 `brief.metadata.music_plan.source == "none"` 且有显式选择退出理由。
- **片尾卡已渲染并拼接**，除非 `brief.metadata.end_tag_plan` 为 null 且有显式选择退出理由。那种情况下最终 mp4 的末帧必须是片尾卡。
- 首帧与末帧已验证。
- 静音窗（如有）已在波形上验证。
- 无旁白，除非 brief 批准。
- `render_report.warnings` 列出每一处替换。
- `render_report.metadata.music_mixed = true` 且 `render_report.metadata.end_tag_rendered = true`（或记录了显式选择退出）。

## 常见坑

- **让年代混杂的片段未经调色直接渲染。** 成片会像一叠网图 PPT。LUT 不可省。
- **为了匹配画布做放大而非加黑边。** Prelinger 640x480 放大到 1920x1080 会明显像素化且不对。居中加黑边，或把方形裁切作为设计选择拥抱它。
- **为"填补空白"加旁白或环境音效。** 重大变更，需要用户批准。
- **逐条调色。** 整片一个 LUT。不要尝试逐条平衡——耗时十倍，调性反而更不一致。
- **悄悄降级到 FFmpeg。** 若 Remotion 受阻而你不声不响改走 FFmpeg，你改动了已批准的渲染路径。停下，先上报降级再渲染。
- **在渲染时覆盖剪辑决策。** 如果发现自己在渲染调用里调音量、淡入淡出或裁剪，你是在合成阶段做剪辑。回到剪辑阶段修正决策、重新输出产物，再渲染。
- **跳过验证。** 一次"成功"却静音、淡出错误或裁掉最后一个关键镜头的渲染，比失败更糟。打开文件看。

## 渲染失败时

若 `video_compose` 返回错误：

1. 按决策沟通契约判定错误类别（鉴权 / 提供方 / 工具缺陷 / 计划质量）。
2. 若是路径错误，逐条校验 asset manifest 中 asset_id → 路径的解析。一个缺失文件就会让整次渲染失败。
3. 若是编解码错误，输入片段可能用了冷门封装（Archive.org 有时提供 Matroska）。先用 `video_trimmer` 把每个输入归一化为 mp4/h264。
4. 若是内存或超时错误，把渲染拆成两半，最后用 `video_stitch` 合并。
5. 切换到低保真路径前先上报用户。本流水线以素材为主导，没有生成静帧的兜底方案。
