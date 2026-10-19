---
name: elsalvatore-video-editor
version: 1.0.0
description: 通过 ffmpeg、Remotion、Whisper 三大引擎完成视频剪辑、程序化生成与字幕转录的全流程视频处理助手。
---

# 视频编辑器

## 能力总览

本 skill 面向视频处理场景，由三个引擎协同完成工作：

- **ffmpeg** —— 处理已有素材：裁剪、压缩、拼接、缩放、变速、防抖、加水印、音频处理、导出 GIF/缩略图、加转场与字幕。
- **Remotion** —— 程序化生成新片段：标题卡、下三分之一信息条、片尾卡、多片段预告片、动态叠加层。
- **Whisper** —— 语音转写与字幕生成。

配套特性：
- 在 Apple Silicon 上优先启用 VideoToolbox 硬件编码（`h264_videotoolbox` / `hevc_videotoolbox`）。
- 支持从 `~/design-assets/color-palettes/` 读取主题色板并注入 Remotion 渲染。
- 内置主流平台发布预设（YouTube、Instagram、TikTok、Twitter/X 等）。
- Remotion 工作区做缓存复用，避免每次重复安装依赖。

---

## 触发场景

当用户表达以下任一意图时启用：

| 类别 | 关键词 |
|------|--------|
| 基础剪辑 | 裁剪、剪掉、截取、分割、缩短 |
| 压缩 | 压缩、减小体积、变小、优化体积 |
| 合并 | 拼接、合并、连接、缝合 |
| 尺寸 | 缩放、裁剪画面、补边、宽高比、竖屏、横屏、方形 |
| 速度 | 加速、减速、慢动作、延时、快进、倒放 |
| 防抖 | 防抖、抖动、稳定、画面晃动 |
| 转场 | 淡入淡出、交叉淡化、溶解、擦除、转场 |
| 字幕 | 字幕、SRT、转写、语音转文字 |
| 标题卡 | 标题卡、片头、开场、动态文字 |
| 下三分之一 | 下三分之一、姓名条、角标、人名条 |
| 片尾卡 | 片尾、结尾、结束页、致谢页 |
| 预告片 | 预告、宣传片、混剪、高光集锦 |
| 缩略图 | 缩略图、封面、抽帧、截图 |
| GIF | GIF、动图、循环图、表情包 |
| 水印 | 水印、logo 叠加、品牌标识 |
| 音频 | 音频、音量、响度归一、静音、淡入、淡出、混音、抽音轨 |
| 信息 | 信息、详情、时长、分辨率、编码、码率、元数据 |
| 流水线 | 流水线、批量、工作流、多步骤 |
| 平台 | YouTube、Instagram、TikTok、Twitter、Reels、Shorts |

---

## 命令一览

### 剪辑处理（ffmpeg）

| 命令 | 作用 | 示例 |
|------|------|------|
| `/trim` | 截取视频片段 | "把 video.mp4 从 0:30 截到 1:45" |
| `/compress` | 控制质量地压缩体积 | "压到 10MB 以内" |
| `/merge` | 多个片段拼成一个 | "把 clip1.mp4 和 clip2.mp4 加淡入淡出合并" |
| `/resize` | 改尺寸/宽高比、裁切或补边 | "改成 1080x1080 方形" |
| `/speed` | 加速、减速或倒放 | "2 倍速" 或 "0.5 倍慢动作" |
| `/stabilize` | 消除手持抖动（vidstab 两遍法） | "给 shaky.mp4 做防抖" |
| `/watermark` | 叠加图片或文字水印 | "右下角加 logo.png" |
| `/audio` | 音量、归一化、混音、淡入淡出、抽音轨、静音 | "音频响度归一化到 -14 LUFS" |
| `/thumbnail` | 抽单帧导出图片 | "在 0:15 处抽一帧" |
| `/gif` | 从片段生成动图 | "0:05 到 0:10 生成 320px 宽的 GIF" |
| `/extract` | 导出音频轨或字幕轨 | "把音频导成 mp3" |
| `/info` | 查看视频元数据与流信息 | "看下 video.mp4 的信息" |

### 程序化生成（Remotion）

| 命令 | 作用 | 示例 |
|------|------|------|
| `/title-card` | 带动画的标题卡，支持主题 | "标题卡：即将上线，wad 主题，缩放动画" |
| `/lower-third` | 动态姓名/职位信息条 | "下三分之一：John Doe，CEO，现代风格" |
| `/end-card` | 带 CTA 与社交信息的片尾卡 | "片尾卡：订阅！@handle，ea 主题" |
| `/teaser` | 多片段混剪，带转场与标题 | "用 clips/ 里的素材剪 30 秒预告片" |

### 语音转写（Whisper）

| 命令 | 作用 | 示例 |
|------|------|------|
| `/transcribe` | 从语音生成 SRT/VTT | "转写 interview.mp4" |
| `/add-captions` | 转写后把字幕烧录进画面 | "给 talk.mp4 加字幕" |

### 编排

| 命令 | 作用 | 示例 |
|------|------|------|
| `/pipeline` | 多步骤串联处理 | "裁剪、加标题卡、按 Instagram 压缩" |

---

## 工作流程

### 第 1 步：环境自检

```bash
which ffmpeg ffprobe && echo "ffmpeg: ok"
node --version && echo "node: ok"
which whisper && echo "whisper: ok" || echo "whisper: 未安装（字幕需手动提供 .srt）"
ffmpeg -encoders 2>/dev/null | grep videotoolbox && echo "hw accel: ok" || echo "hw accel: 不可用"
ffmpeg -filters 2>/dev/null | grep vidstab && echo "vidstab: ok" || echo "vidstab: 不可用（需带 libvidstab 重新编译 ffmpeg）"
```

若缺 ffmpeg：提示 `brew install ffmpeg`。
若缺 Node.js：提示从 https://nodejs.org 安装或 `brew install node`。
若缺 vidstab：提示重新安装带 vidstab 支持的 ffmpeg。

### 第 2 步：判定请求类型

| 用户意图 | 引擎 | 分支 |
|----------|------|------|
| 处理已有素材 | ffmpeg | 3a |
| 生成新视频内容 | Remotion | 3b |
| 音频处理 | ffmpeg 音频滤镜 | 3a |
| 查询信息 | ffprobe | 3a |
| 组合流程 | 两者编排 | 3c |
| 平台发布 | 尺寸+压缩预设 | 3a |
| 语音转写 | Whisper + ffmpeg | 3a |

### 第 3a 步：ffmpeg 分支

1. 若用户未给输入文件，先询问。
2. 用 ffprobe 检查素材：
   ```bash
   ffprobe -v quiet -print_format json -show_format -show_streams "<file>"
   ```
3. 检测硬件加速（macOS Apple Silicon）：
   ```bash
   ffmpeg -encoders 2>/dev/null | grep h264_videotoolbox
   # 可用则优先：-c:v h264_videotoolbox -b:v 5M
   # 回退：-c:v libx264 -crf 23 -preset medium
   ```
4. 输出文件防覆盖：
   ```bash
   OUTPUT="trimmed_video.mp4"
   COUNTER=2
   while [ -f "$OUTPUT" ]; do
     OUTPUT="trimmed_video_${COUNTER}.mp4"
     COUNTER=$((COUNTER + 1))
   done
   ```
5. 构造 ffmpeg 命令。
6. 用平实语言逐项解释每个参数含义。
7. 明确输出文件名（绝不覆盖源文件）。
8. 询问："可以执行了吗？"
9. 执行并校验：
   ```bash
   if [ $? -eq 0 ]; then
     echo "Success"
     ffprobe -v quiet -print_format json -show_format "$OUTPUT" | grep -E '"duration"|"size"'
   else
     echo "Error — 请查看上方 ffmpeg 输出"
   fi
   ```
10. 汇报输出路径、文件体积与时长。

输出命名约定：

| 命令 | 输出模式 |
|------|----------|
| 裁剪 | `trimmed_<文件名>` |
| 压缩 | `compressed_<文件名>` |
| 合并 | `merged_output.<ext>` |
| 缩放 | `resized_<文件名>` |
| 变速 | `speed_<倍数>x_<文件名>` |
| 防抖 | `stabilized_<文件名>` |
| 水印 | `watermarked_<文件名>` |
| 字幕 | `captioned_<文件名>` |
| 抽音轨 | `<名称>.mp3` |
| 音频修改 | `audio_<文件名>` |
| 抽字幕轨 | `<名称>.srt` |
| 缩略图 | `thumb_<名称>_<时间码>.jpg` |
| GIF | `<名称>.gif` |

### 第 3b 步：Remotion 分支

1. 确认已安装 Node.js。
2. 工作区缓存复用：
   ```bash
   WORKSPACE="/tmp/remotion-workspace"
   if [ -d "$WORKSPACE/node_modules" ]; then
     echo "复用已缓存的 Remotion 工作区"
   else
     echo "首次运行，创建 Remotion 工作区..."
     mkdir -p "$WORKSPACE"
     cp -r ~/project-templates/remotion-video/* "$WORKSPACE/"
     cd "$WORKSPACE" && npm install
   fi
   ```
3. 从 `~/design-assets/color-palettes/` 加载主题：
   ```bash
   # 用户指定主题（wad、bloghead、ea）时，读取对应 JSON 取色
   # 作为 inputProps 传给 Remotion 合成
   ```
4. 按需编写或更新合成源文件。
5. 可用合成组件：
   - `TitleCard` —— 带多种动画预设的标题卡
   - `LowerThird` —— 带强调色条的人名/职位条
   - `EndCard` —— 带 CTA、社交、logo 的片尾
   - `Teaser` —— 用 TransitionSeries 做的多片段混剪
6. 渲染：
   ```bash
   cd "$WORKSPACE"
   npx remotion render src/index.ts <CompositionId> /path/to/output.mp4 \
     --props='{"text":"标题","bg":"#09090B","fg":"#FFFFFF","accent":"#7C3AED"}'
   ```
7. 把产物拷贝到用户工作目录。
8. 汇报输出路径与时长。

### 第 3c 步：组合流水线

针对多步骤请求（如"做一支含标题卡、素材片段和片尾的预告片"）：

1. **规划** —— 执行前向用户描述每个步骤。
2. **生成** —— 先用 Remotion 产出需要的内容（标题卡、片尾卡）。
3. **处理** —— 用 ffmpeg 对源片段做裁剪/缩放。
4. **组装** —— 用 ffmpeg 带转场合并所有片段。
5. **收尾** —— 如指定了目标平台，按其预设压缩。
6. 在生成/处理/组装三个阶段之间分别与用户确认。

---

## ffmpeg 速查

### 无损裁剪
```bash
ffmpeg -ss <开始> -to <结束> -i input.mp4 -c copy trimmed_input.mp4
```

### 压缩 —— 网络通用（CRF 23）
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k compressed_input.mp4
```

### 压缩 —— 硬件加速（macOS）
```bash
ffmpeg -i input.mp4 -c:v h264_videotoolbox -b:v 5M -c:a aac -b:a 128k compressed_input.mp4
```

### 带淡入淡出的合并
```bash
# 两段素材在 offset = 第一段时长 - 1 处做 1 秒交叉淡化
ffmpeg -i clip1.mp4 -i clip2.mp4 \
  -filter_complex "[0][1]xfade=transition=fade:duration=1:offset=<offset>,format=yuv420p[v];[0:a][1:a]acrossfade=d=1[a]" \
  -map "[v]" -map "[a]" merged_output.mp4
```

### 缩放 / 裁剪 / 补边
```bash
# 指定尺寸（-1 表示保持宽高比）
ffmpeg -i input.mp4 -vf "scale=1920:1080" resized_input.mp4
ffmpeg -i input.mp4 -vf "scale=1080:-1" resized_input.mp4

# 居中裁成方形
ffmpeg -i input.mp4 -vf "crop=min(iw\,ih):min(iw\,ih)" cropped_input.mp4

# 补边到目标比例（加黑边）
ffmpeg -i input.mp4 -vf "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:black" padded_input.mp4
```

### 变速
```bash
# 2 倍速（画面+音频）
ffmpeg -i input.mp4 -vf "setpts=0.5*PTS" -af "atempo=2.0" speed_2x_input.mp4

# 0.5 倍慢动作
ffmpeg -i input.mp4 -vf "setpts=2.0*PTS" -af "atempo=0.5" speed_0.5x_input.mp4

# 4 倍速（atempo 上限 2.0，需串联）
ffmpeg -i input.mp4 -vf "setpts=0.25*PTS" -af "atempo=2.0,atempo=2.0" speed_4x_input.mp4

# 倒放
ffmpeg -i input.mp4 -vf "reverse" -af "areverse" reversed_input.mp4
```

### 水印叠加
```bash
# 右下角带内边距
ffmpeg -i input.mp4 -i logo.png \
  -filter_complex "overlay=W-w-20:H-h-20" watermarked_input.mp4

# 左上角
ffmpeg -i input.mp4 -i logo.png \
  -filter_complex "overlay=20:20" watermarked_input.mp4

# 居中半透明
ffmpeg -i input.mp4 -i logo.png \
  -filter_complex "[1]format=rgba,colorchannelmixer=aa=0.3[wm];[0][wm]overlay=(W-w)/2:(H-h)/2" watermarked_input.mp4

# 文字水印
ffmpeg -i input.mp4 \
  -vf "drawtext=text='My Brand':fontsize=24:fontcolor=white@0.5:x=W-tw-20:y=H-th-20" watermarked_input.mp4
```

### 视频防抖（vidstab 两遍法）
```bash
# 第一遍：分析运动轨迹
ffmpeg -i shaky.mp4 -vf vidstabdetect=shakiness=10:accuracy=15 -f null -

# 第二遍：套用稳定变换
ffmpeg -i shaky.mp4 -vf vidstabtransform=smoothing=30:input=transforms.trf stabilized_shaky.mp4
```

### 音频处理
```bash
# 调整音量
ffmpeg -i input.mp4 -af "volume=1.5" audio_input.mp4

# 响度归一化（广播标准 -14 LUFS）
ffmpeg -i input.mp4 -af "loudnorm=I=-14:TP=-1:LRA=11" audio_input.mp4

# 混合两条音轨
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex "[0:a]volume=1.0[a1];[1:a]volume=0.3[a2];[a1][a2]amix=inputs=2:duration=first[a]" \
  -map 0:v -map "[a]" audio_input.mp4

# 淡入淡出（3 秒淡入、3 秒淡出）
ffmpeg -i input.mp4 -af "afade=t=in:ss=0:d=3,afade=t=out:st=<结束-3>:d=3" audio_input.mp4

# 静音
ffmpeg -i input.mp4 -an muted_input.mp4

# 替换音轨
ffmpeg -i input.mp4 -i newtrack.mp3 -c:v copy -map 0:v:0 -map 1:a:0 replaced_audio_input.mp4
```

### 生成 GIF（两遍调色板保质量）
```bash
# 第一遍：生成调色板
ffmpeg -ss <开始> -t <时长> -i input.mp4 \
  -vf "fps=15,scale=320:-1:flags=lanczos,palettegen" palette.png

# 第二遍：套用调色板生成 GIF
ffmpeg -ss <开始> -t <时长> -i input.mp4 -i palette.png \
  -filter_complex "[0:v]fps=15,scale=320:-1:flags=lanczos[v];[v][1:v]paletteuse" output.gif

# 清理临时文件
rm palette.png
```

### 抽缩略图
```bash
# 指定时间点抽单帧
ffmpeg -ss <时间戳> -i input.mp4 -frames:v 1 -q:v 2 thumb_input_<时间戳>.jpg

# 抽 4x4 网格缩略图
ffmpeg -i input.mp4 -vf "fps=1/<间隔>,scale=320:-1,tile=4x4" thumb_grid_input.jpg
```

### 烧录 .srt 字幕
```bash
ffmpeg -i input.mp4 -vf "subtitles=captions.srt:force_style='FontSize=24,PrimaryColour=&H00FFFFFF'" captioned_input.mp4
```

### 抽取音频
```bash
ffmpeg -i input.mp4 -vn -c:a libmp3lame -q:a 2 output.mp3
```

### 查看视频信息
```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
```

---

## Remotion 速查

### 缓存工作区初始化
```bash
WORKSPACE="/tmp/remotion-workspace"
if [ ! -d "$WORKSPACE/node_modules" ]; then
  cp -r ~/project-templates/remotion-video/* "$WORKSPACE/"
  cd "$WORKSPACE" && npm install
fi
```

### TitleCard 合成
```tsx
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig, Img } from 'remotion';

type Animation = 'fade' | 'slide-up' | 'slide-down' | 'zoom' | 'typewriter' | 'glitch' | 'blur-in';

export const TitleCard: React.FC<{
  text: string;
  subtitle?: string;
  bg?: string;
  fg?: string;
  accent?: string;
  animation?: Animation;
  logo?: string;
}> = ({ text, subtitle, bg = '#09090B', fg = '#FFFFFF', accent = '#7C3AED', animation = 'fade', logo }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({ frame, fps, config: { damping: 200 } });

  return (
    <AbsoluteFill style={{ background: bg, justifyContent: 'center', alignItems: 'center' }}>
      {logo && <Img src={logo} style={{ width: 120, marginBottom: 24, opacity: progress }} />}
      <h1 style={{ color: fg, fontSize: 80, opacity: progress }}>{text}</h1>
      {subtitle && <p style={{ color: accent, fontSize: 36, opacity: progress }}>{subtitle}</p>}
    </AbsoluteFill>
  );
};
```

### LowerThird 合成
```tsx
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';

export const LowerThird: React.FC<{
  name: string;
  title?: string;
  accent?: string;
  style?: 'modern' | 'minimal' | 'broadcast';
}> = ({ name, title, accent = '#7C3AED', style = 'modern' }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: 'clamp' });
  const exit = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });
  const opacity = Math.min(enter, exit);
  const translateX = interpolate(enter, [0, 1], [-300, 0]);

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', padding: 60 }}>
      <div style={{
        transform: `translateX(${translateX}px)`,
        opacity,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}>
        <div style={{ width: 4, height: 60, background: accent, borderRadius: 2 }} />
        <div>
          <div style={{ color: '#fff', fontSize: 32, fontWeight: 700 }}>{name}</div>
          {title && <div style={{ color: '#ccc', fontSize: 22 }}>{title}</div>}
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

### EndCard 合成
```tsx
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig, Img } from 'remotion';

export const EndCard: React.FC<{
  text: string;
  subtitle?: string;
  url?: string;
  social?: string;
  logo?: string;
  bg?: string;
  fg?: string;
  accent?: string;
}> = ({ text, subtitle, url, social, logo, bg = '#09090B', fg = '#FFFFFF', accent = '#7C3AED' }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = (delay: number) => spring({ frame: Math.max(0, frame - delay), fps, config: { damping: 12 } });

  return (
    <AbsoluteFill style={{
      background: `linear-gradient(135deg, ${bg}, ${accent}22)`,
      justifyContent: 'center',
      alignItems: 'center',
      gap: 20,
    }}>
      {logo && <Img src={logo} style={{ width: 80, transform: `scale(${s(0)})` }} />}
      <h1 style={{ color: fg, fontSize: 64, opacity: s(5) }}>{text}</h1>
      {subtitle && <p style={{ color: `${fg}CC`, fontSize: 28, opacity: s(10) }}>{subtitle}</p>}
      {url && <p style={{ color: accent, fontSize: 22, opacity: s(15) }}>{url}</p>}
      {social && <p style={{ color: `${fg}99`, fontSize: 20, opacity: s(20) }}>{social}</p>}
    </AbsoluteFill>
  );
};
```

### 用 TransitionSeries 做预告片
```tsx
import { AbsoluteFill, Video, staticFile } from 'remotion';
import { TransitionSeries, linearTiming, fade } from '@remotion/transitions';

export const Teaser: React.FC<{
  title: string;
  clips: string[];
  theme?: { bg: string; fg: string; accent: string };
}> = ({ title, clips, theme }) => (
  <AbsoluteFill>
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={90}>
        <TitleCard text={title} bg={theme?.bg} fg={theme?.fg} accent={theme?.accent} />
      </TransitionSeries.Sequence>
      {clips.map((clip, i) => (
        <>
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: 15 })}
          />
          <TransitionSeries.Sequence durationInFrames={120}>
            <Video src={staticFile(clip)} />
          </TransitionSeries.Sequence>
        </>
      ))}
    </TransitionSeries>
  </AbsoluteFill>
);
```

### 主题 Props 用法
```tsx
// 渲染时通过 --props 传入主题色：
// npx remotion render src/index.ts TitleCard output.mp4 --props='{"text":"Hello","bg":"#09090B","fg":"#FFFFFF","accent":"#7C3AED"}'

// 或从主题文件读取：
import { themes } from './utils/themes';
const t = themes['wad']; // { primary: '#7C3AED', bg: '#09090B', accent: '#EC4899' }
```

### 动画预设
```tsx
// TitleCard 支持的动画：
// 'fade'       - 透明度弹簧过渡
// 'slide-up'   - 从下方滑入并渐显
// 'slide-down' - 从上方滑入并渐显
// 'zoom'       - 从 0.5 放大到 1.0
// 'typewriter' - 逐字显现
// 'glitch'     - 随机偏移闪烁
// 'blur-in'    - 由模糊溶解到清晰
```

---

## 主题系统

主题以 JSON 形式存放于 `~/design-assets/color-palettes/`，读取后作为 props 传给 Remotion 合成。

### 可用主题

| 主题 | ID | 主色 | 背景 | 强调色 | 来源文件 |
|------|----|------|------|--------|----------|
| WiesbadenAfterDark | `wad` | `#7C3AED` | `#09090B` | `#EC4899` | `wad-dark-theme.json` |
| Bloghead | `bloghead` | `#3B82F6` | `#0F172A` | `#F59E0B` | `bloghead-theme.json` |
| EA Solutions | `ea` | `#8B5CF6` | `#0A0A1A` | `#EC4899` | `ea-solutions-theme.json` |

### 主题使用方式

用户指定主题名时：
1. 从 `~/design-assets/color-palettes/` 读取对应 JSON。
2. 取 `colors.brand.primary`、`colors.background.primary`（或 `.dark`）、`colors.brand.secondary` 作为强调色。
3. 作为 `bg`、`fg`、`accent` 传给 Remotion 合成。
4. 未指定时默认使用 WAD 深色主题。

---

## 平台发布预设

| 平台 | 尺寸 | 宽高比 | 最长时长 | 编码 | 码率 | 备注 |
|------|------|--------|----------|------|------|------|
| YouTube | 1920x1080 | 16:9 | 无限制 | H.264 | 8-12 Mbps | CRF 18-23 |
| YouTube Shorts | 1080x1920 | 9:16 | 60s | H.264 | 5-8 Mbps | 竖屏 |
| Instagram Feed | 1080x1080 | 1:1 | 60s | H.264 | 3.5 Mbps | 方形 |
| Instagram Reels | 1080x1920 | 9:16 | 90s | H.264 | 5-8 Mbps | 竖屏 |
| Instagram Story | 1080x1920 | 9:16 | 15s | H.264 | 5 Mbps | 竖屏 |
| TikTok | 1080x1920 | 9:16 | 10m | H.264 | 5-8 Mbps | 竖屏 |
| Twitter/X | 1280x720 | 16:9 | 140s | H.264 | 5 Mbps | 上限 512MB |
| LinkedIn | 1920x1080 | 16:9 | 10m | H.264 | 5-8 Mbps | 职场向 |
| Facebook Feed | 1280x720 | 16:9 | 240m | H.264 | 4-8 Mbps | 兼容广 |
| Facebook Reels | 1080x1920 | 9:16 | 90s | H.264 | 5-8 Mbps | 竖屏 |
| 通用网络 | 1920x1080 | 16:9 | 无限制 | H.264 | CRF 23 | 平衡质量与体积 |
| 网络小体积 | 1280x720 | 16:9 | 无限制 | H.264 | CRF 28 | 体积更小 |

### 平台预设命令
```bash
# YouTube 优化
ffmpeg -i input.mp4 -c:v libx264 -crf 20 -preset slow -c:a aac -b:a 192k -movflags +faststart youtube_input.mp4

# Instagram 方形（居中裁剪+压缩）
ffmpeg -i input.mp4 -vf "crop=min(iw\,ih):min(iw\,ih),scale=1080:1080" -c:v libx264 -crf 23 -c:a aac -b:a 128k instagram_input.mp4

# Instagram/TikTok 竖屏（必要时补边）
ffmpeg -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" -c:v libx264 -crf 23 -c:a aac -b:a 128k vertical_input.mp4

# Twitter 优化（上限 512MB、140s）
ffmpeg -i input.mp4 -vf "scale=1280:720" -c:v libx264 -crf 24 -preset medium -c:a aac -b:a 128k -t 140 twitter_input.mp4

# 网络优化（faststart 便于流播）
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart web_input.mp4
```

---

## 与其他能力的协同

| MCP / Skill | 协同方式 |
|-------------|----------|
| **Blender MCP** | 生成 3D 动画片头、logo 或特效，再合入视频 |
| **Playwright MCP** | 抓取浏览器截图或录屏，用于产品演示视频 |
| **Gemini MCP** | 分析长视频转写文本，给出剪辑建议（场景切分、高光片段） |
| **Social Media skill** | 为发布视频生成社交文案与描述 |
| **Storyboard Manager skill** | 剪辑前先规划分镜与镜头列表 |
| **Web Asset Generator skill** | 制作视频缩略图、社交卡片与宣传图 |

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `No such file or directory` | 输入路径不对 | 用 `ls` 核对路径 |
| `Invalid data found` | 文件损坏或格式不支持 | 用 `ffprobe` 检查，再用 `-c:v libx264` 重编码 |
| `Encoder not found` | 缺少编码器（如 `h264_videotoolbox`） | 回退到 `libx264` |
| `Filter vidstabdetect not found` | ffmpeg 未编译 vidstab | 重装带 vidstab 支持的 ffmpeg |
| `Output file already exists` | 文件名冲突 | 采用防覆盖逻辑（追加计数） |
| Remotion 渲染内存溢出 | 视频过长或分辨率过高 | 降低分辨率或拆成多段 |
| Whisper 模型下载失败 | 网络问题 | 重试或改用 `--model tiny` 减小下载量 |
```
