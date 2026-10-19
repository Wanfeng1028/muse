---
name: openmontage-remotion
version: "1.0.0"
description: 基于 React 的高级视频合成引擎，负责场景组装、参数化模板、动画叠加与数据驱动批量渲染，适用于从第三阶段起的最终渲染，简单剪辑则回退到 FFmpeg。
metadata:
  license: AGPL-3.0
---

# Remotion 合成引擎

## 何时使用

当任务涉及 React 驱动的场景拼接、可参数化模板、动态叠加层、转场效果或数据驱动的批量渲染时，从第三阶段开始就应选用 Remotion。若只是简单的裁剪、拼接和编码，直接用 FFmpeg 更合适。

## 与 Remotion Agent Skills 的区别

已安装的 agent skills（`.agents/skills/remotion-best-practices/`）教的是 Remotion API 的正确用法——导入方式、时间控制、动画约束、代码模式。而本文件讲的是 OpenMontage 如何调用 Remotion——哪些合成对应流水线的哪个阶段、产物如何流入、渲染如何触发。

## Remotion 优先路由

**只要 Remotion 可用，所有最终渲染默认走 Remotion。** 它能在一次 React 渲染中同时处理视频片段（通过 `<OffthreadVideo>`）、静态图片、动画场景、组件类型、转场和混合内容。

FFmpeg 是**后备方案**——仅在 Remotion 不可用，或简单独立操作不需要 React 渲染时使用。

| 场景 | 后端 | 原因 |
|------|------|------|
| 最终视频渲染（任意内容） | **Remotion** | 所有合成的默认选择 |
| 视频片段 + 动画静帧 + 文字卡 | **Remotion** | 一次渲染混合内容 |
| 带转场的纯视频剪辑 | **Remotion** | 原生 `<OffthreadVideo>` + 转场 |
| 动画图表/文字卡 | **Remotion** | 逐帧精确控制 |
| 数据驱动批量视频 | **Remotion** | Zod props + 参数化渲染 |
| 词级字幕（合成内） | **Remotion** | CaptionOverlay 支持词高亮，优于 SRT |
| 音频嵌入（旁白+音乐） | **Remotion** | 原生 `<Audio>` 支持音量/淡入淡出 |
| 简单裁剪、拼接 | FFmpeg | 即时完成，无 Node 依赖 |
| 独立字幕烧录（事后） | FFmpeg | 仅为已渲染视频追加字幕而不重渲 |
| 人脸增强、调色 | FFmpeg | 基于滤镜，确定性输出 |
| Remotion 不可用 | FFmpeg | 自动回退 |

**注意：** `render` 操作默认自动路由到 Remotion。只有当 Remotion 未安装，或 agent 显式调用 `operation='compose'` 执行独立操作时才选 FFmpeg。当没有现成合成覆盖所需布局（如自定义画中画、分屏）时，agent 可通过能力扩展协议即时编写 Remotion 合成。

## 支持的场景类型（Cut Types）

Explainer 合成支持以下 cut 类型：

| 类型 | 必需 Props | 最佳用途 |
|------|-----------|----------|
| `text_card` | `text` | 陈述、标题、结束语 |
| `stat_card` | `stat`，可选 `subtitle`、`accentColor` | 大数字、冲击性指标 |
| `hero_title` | `text`，可选 `heroSubtitle` | 开场标题、戏剧性揭幕 |
| `callout` | `text`，可选 `title`、`callout_type`（info/warning/tip/quote） | 提示、引用、重要说明 |
| `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` | 前后对比、A/B、对抗 |
| `bar_chart` | `chartData` [{label, value}]，可选 `title`、`chartAnimation` | 分类比较、排名 |
| `line_chart` | `chartSeries` [{label, data: [{x,y}]}]，可选 `title` | 趋势、时间序列、增长 |
| `pie_chart` | `chartData` [{label, value}]，可选 `donut`、`centerLabel` | 比例、构成分解 |
| `kpi_grid` | `chartData` [{label, value, prefix, suffix, change, icon}] | 仪表盘、增长指标 |
| `progress_bar` | `progress`（0-100），可选 `progressSegments` | 旅程可视化、完成度、堆叠指标 |
| `anime_scene` | `images`（1-4 路径），可选 `animation`、`particles`、`particleColor`、`particleCount`、`particleIntensity`、`vignette`、`lightingFrom`、`lightingTo` | 动漫/吉卜力风格场景，多图交叉淡化、镜头运动、粒子叠加 |

**图表动画：** `grow-up`、`slide-in`、`pop`（柱状）、`draw`、`fade-in`（折线）、`spin`、`expand`、`sequential`（饼图）、`count-up`、`pop`、`cascade`（KPI）

### Anime Scene — 多图交叉淡化 + 粒子

`anime_scene` 类型渲染 1-4 张图片，带平滑交叉淡化、电影级镜头运动和动态粒子叠加，从静帧营造动画错觉。

**镜头运动类型：** `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static`

**粒子类型：** `fireflies`（漂浮金色光点）、`petals`（飘落樱花）、`sparkles`（闪烁星光）、`mist`（飘移雾气）、`light-rays`（耶稣光）

**关键 prop：** `sceneDurationSeconds` 由 `SceneRenderer` 自动传入——这修复了一个 Remotion 关键陷阱：`useVideoConfig().durationInFrames` 返回的是整个合成的时长，而非场景 Sequence 的时长。

**多图交叉淡化数学：** 每张图占据等长的时间段。第 N 张的淡出与第 N+1 张的淡入重叠 `crossfadeDur`（约 1.2 秒），确保没有空白帧。每个场景生成 2-3 张同视觉体系的图片，但每个节拍变换镜头、主体和光照。相近的种子有助于创造微妙运动，而不会让整个序列塌缩为重复提示词。

**参考合成：** `remotion-composer/public/demo-props/mori-no-seishin.json` — 6 个动漫场景、30 秒，含粒子、光照、叠加和环境音乐。

**风格剧本：** `styles/anime-ghibli.yaml` — 吉卜力风格美学，含色板、排版、运动参数和 FLUX 提示词前缀。

**零密钥视频策略：** 当没有可用的图片或视频生成时，用这些组件类型构建完整视频。一个精心编排的 hero_title → kpi_grid → bar_chart → comparison → stat_card → text_card 序列，无需任何外部依赖即可产出精良的专业视频。

### 零密钥视频的验证公式

以下规则经系统性渲染测试得出，可产出电影级效果：

**1. 每个视频锁定一个背景体系。** 使用从剧本或自定义身份派生的统一背景处理，而不是把每个序列都塞进相同的深色仪表盘外观。这避免了刺眼的白↔暗闪烁转场，让图表颜色更突出。目标是视觉统一，而非强制深色主题。

**2. 扁平 props 格式。** 所有场景属性放在 cut 对象的顶层（如 `cut.text`、`cut.chartData`），不要嵌套在 `props` 键下。

**3. KPI Grid 数据规则：**
- `value` 必须是小的、人类可读的数字。组件自动格式化 ≥1M→"XM"，≥1K→"XK"。表示"8.1 Billion"用 `value: 8.1, suffix: " Billion"`。绝不要用原始巨大数字加后缀。
- `change` 必须是数字（如 `3.2`），不是字符串（不要写 `"+3.2%"`）。

**4. Comparison 和 Callout 主题化：**
- `comparison` 接受 `backgroundColor` 和 `color`（文字颜色）以适配深色主题。
- `callout` 接受 `backgroundColor`，同时设置容器和卡片背景。

**5. 叠加层增加精致感。**
- `section_title` 叠加层按叙事分组场景（"THE CRISIS"、"THE DATA"）。
- `stat_reveal` 叠加层在图表场景上漂浮戏剧性数字（如角落的"10x"）。

**6. 场景节奏：** 每场景 4-6 秒，45-50 秒视频用 8-10 个场景。给图表动画至少 4 秒完成。Hero title 只需 4 秒。

**7. 色板统一。** 选 4-5 个与主题相关的强调色，在图表、叠加和点缀中一致使用。柱状/饼图/折线场景使用相同的 chartColors 数组以保持视觉统一。

**参考合成：** 以 `remotion-composer/public/demo-props/climate-dashboard.json` 为黄金标准，其他 demo 文件提供额外模式。

### 渲染前验证（强制）

**渲染前始终运行 `composition_validator`。** 它能捕获：
- 缺失的素材文件（图片、音频），这些会导致渲染失败
- 旁白音频长于视频时长（音频被截断）
- 音乐短于视频（结尾静音）
- 无效的 cut 时间（out ≤ in）

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    "composition_path": "path/to/composition.json",
    "assets_root": "remotion-composer/public",
})
# 渲染前 result.data["valid"] 必须为 True
```

**音频时长对齐：**
- 生成 TTS 旁白后，工具返回 `audio_duration_seconds`。
- 若旁白超过视频时长：缩短脚本重新生成，或延长最后一个场景。
- 用 `tools.analysis.audio_probe.probe_duration(path)` 检查任意音频文件时长。
- 音乐应 ≥ 视频时长；播放器通过 `fadeOutSeconds` 处理淡出。

## 架构

```
remotion-composer/
├── src/
│   ├── Root.tsx              # 合成注册表
│   ├── compositions/         # 每种流水线类型一个文件
│   │   ├── Explainer.tsx     # 生成的 explainer 合成
│   │   ├── AnimatedScene.tsx # 单个动画场景
│   │   └── TitleCard.tsx     # 独立标题卡
│   ├── components/           # 可复用视觉构建块
│   │   ├── Caption.tsx       # 字幕渲染器
│   │   ├── DiagramOverlay.tsx
│   │   ├── ProgressBar.tsx
│   │   └── TransitionWrapper.tsx
│   └── styles/               # Tailwind + 剧本派生样式
├── public/                   # 静态素材（字体、LUT）
├── package.json
├── remotion.config.ts
└── tsconfig.json
```

## 流水线集成

### 产物到 Remotion Props 的映射

| OpenMontage 产物 | Remotion Prop | 映射到 |
|---------------------|---------------|---------|
| `scene_plan.json` → `scenes[]` | `scenes` prop | `<TransitionSeries>` 子元素 |
| `scene.type` | 组件选择器 | `talking_head` → `<Video>`，`diagram` → `<DiagramOverlay>` 等 |
| `scene.start_seconds` / `end_seconds` | `from` / `durationInFrames` | `fps * seconds` 转换 |
| `scene.transition_in` / `transition_out` | `<TransitionSeries.Transition>` | `fade`、`slide`、`wipe` |
| `asset_manifest.json` → assets | `assets` prop | `staticFile()` 或绝对路径 |
| `style_playbook` | `theme` prop | 颜色、字体、动画曲线 |
| `edit_decisions.json` → cuts | `cuts` prop | `<Series>` 配合裁剪后的 `<Video>` 段 |
| `media_profile` | 合成尺寸 | 从 profile 取 `width`、`height`、`fps` |

### 渲染调用

编排器通过 CLI 调用 Remotion 渲染：

```bash
# 标准渲染（合成名为 "Explainer"，无需指定入口）
npx remotion render Explainer \
  --props="public/demo-props/my-video.json" \
  --output=output/final.mp4 \
  --codec=h264 --crf=18

# 指定媒体 profile
npx remotion render Explainer \
  --width=1080 --height=1920 --fps=30 \
  --props="public/demo-props/my-video.json" \
  --output=output.mp4
```

**注意：** 不要指定 `src/index.ts` 作为入口——Remotion 自动发现合成。合成名是 `Explainer`（不是 `ExplainerVideo`）。

在 Python 中，当 `backend="remotion"` 时从 `video_compose.py` 通过 `subprocess` 调用。

### 媒体 Profile 映射

| OpenMontage Profile | Remotion 配置 |
|--------------------|---------------|
| `youtube_landscape` | `width: 1920, height: 1080, fps: 30` |
| `youtube_shorts` | `width: 1080, height: 1920, fps: 30` |
| `tiktok_vertical` | `width: 1080, height: 1920, fps: 30` |
| `instagram_reels` | `width: 1080, height: 1920, fps: 30` |
| `instagram_square` | `width: 1080, height: 1080, fps: 30` |
| `cinematic_wide` | `width: 2560, height: 1080, fps: 24` |

## 关键模式

### 场景计划到合成

`scene_plan.json` 中每个场景成为 `<TransitionSeries>` 的子元素：

```tsx
// 伪代码 — 实际组件在 remotion-composer/src/compositions/Explainer.tsx
const Explainer: React.FC<ExplainerProps> = ({ scenes, theme, assets }) => {
  return (
    <TransitionSeries>
      {scenes.map((scene, i) => (
        <React.Fragment key={scene.id}>
          {scene.transition_in && (
            <TransitionSeries.Transition
              presentation={mapTransition(scene.transition_in)}
              timing={timing({ durationInFrames: 15 })}
            />
          )}
          <TransitionSeries.Sequence durationInFrames={secondsToFrames(scene)}>
            <SceneRenderer scene={scene} theme={theme} assets={assets} />
          </TransitionSeries.Sequence>
        </React.Fragment>
      ))}
    </TransitionSeries>
  );
};
```

### 用 calculateMetadata 实现动态时长

当 TTS 音频决定视频长度（生成的 explainer）时，用 `calculateMetadata`：

```tsx
export const ExplainerVideo = {
  component: Explainer,
  calculateMetadata: async ({ props }) => {
    const totalDuration = props.scenes.reduce(
      (sum, s) => sum + (s.end_seconds - s.start_seconds), 0
    );
    return {
      durationInFrames: Math.ceil(totalDuration * props.fps),
      fps: props.fps,
      width: props.width,
      height: props.height,
    };
  },
};
```

### 风格剧本到主题

风格剧本（`skills/styles/`）定义视觉参数。映射到 Remotion 主题：

```tsx
// 从风格剧本 YAML 派生
const cleanProfessional = {
  background: "#FFFFFF",
  text: "#1A1A1A",
  accent: "#2563EB",
  fontFamily: "Inter",
  headingWeight: 600,
  transitionType: "fade",
  transitionDuration: 15, // 帧
  animationEasing: "easeInOutCubic",
};
```

### 音频分层

旁白 + 背景音乐 + 音效作为并行 `<Audio>` 组件。

**音乐偏移与循环：** `audio.music` 配置支持：
- `offsetSeconds` — 跳过安静前奏，从曲子有能量的部分开始。用 `tools/analysis/audio_energy.py` 自动寻找最佳偏移。
- `loop` — 音乐短于视频时循环。Remotion 原生支持。
- `fadeInSeconds` / `fadeOutSeconds` — 开头/结尾的平滑音量渐变。

```json
"audio": {
  "music": {
    "src": "project/music.mp3",
    "volume": 0.15,
    "offsetSeconds": 55,
    "loop": false,
    "fadeInSeconds": 2,
    "fadeOutSeconds": 3
  }
}
```

```tsx
<AbsoluteFill>
  <Audio src={narrationUrl} />
  <Audio src={musicUrl} volume={0.06} startFrom={offsetFrames} loop />
  {sfxCues.map(cue => (
    <Sequence key={cue.id} from={secondsToFrames(cue.time)}>
      <Audio src={cue.url} volume={cue.volume} />
    </Sequence>
  ))}
  {/* 视觉层 */}
</AbsoluteFill>
```

### 成本追踪

Remotion 渲染消耗 CPU 但 API 成本为 $0。通过 cost_tracker 追踪：
- `estimate`：基于合成时长 × 分辨率档位
- `reserve`：0（无 API 开销）
- `reconcile`：墙钟渲染时间用于基准测试

## 关键约束

- **禁止 CSS 动画和过渡** — 它们渲染不正确。所有运动用 `useCurrentFrame()` + `interpolate()`。
- **禁止 Tailwind 动画类** — `animate-*` 类会破坏逐帧渲染。静态 Tailwind 工具类没问题。
- **始终 clamp interpolate()** — 使用 `extrapolateLeft: 'clamp', extrapolateRight: 'clamp'` 防止值超出端点。
- **`useVideoConfig().durationInFrames` 返回合成时长而非 Sequence 时长** — 这是 Remotion 头号陷阱。如果合成是 31 秒（930 帧）而某场景的 `<Sequence>` 是 5 秒（150 帧），在该场景内 `durationInFrames` 仍返回 930。任何直接使用 `durationInFrames` 的交叉淡化、镜头运动或时间逻辑都会严重出错。**修复：** 从父组件传入 `sceneDurationSeconds` 作为 prop，在组件内计算 `effectiveDuration = Math.round(sceneDurationSeconds * fps)`。`AnimeScene` 组件实现了此模式。
- **需要 Node.js 18+** — 最低系统要求中列为可选，推荐配置中为必需。
- **串行渲染，不要并行** — 除非机器有足够内存。每次渲染都会启动一个 Chromium 实例。

## 渲染后验证协议（所有流水线）

**每次 Remotion 渲染在呈现给用户前必须验证。** 此协议适用于所有流水线，不仅是 explainer。各流水线的 compose-director 可以扩展但不得跳过任何步骤。

**步骤 1：探测输出文件（门禁 — 阻塞所有其他步骤）：**
```bash
ffprobe -v quiet -print_format json -show_format -show_streams rendered_video.mp4
```
验证全部：
- [ ] 视频流存在且分辨率、FPS 正确
- [ ] **音频流存在** — 若缺失，立即停止，修复音频配置，重新渲染
- [ ] 时长在目标的 ±5% 内
- [ ] 文件大小合理（非 0 字节，非可疑地小）

**若音频流缺失，不要继续。** 这意味着旁白/音乐未被嵌入。最常见原因：音频源在外部混合但从未传入 Remotion 的 `audio` prop。修复：将 `audio.narration` 和 `audio.music` 添加到合成 props 并重新渲染。

**步骤 2：提取审查帧** 在场景中点处，逐一目视检查。

**步骤 3：转录渲染视频的音频** 使用 WhisperX/transcriber 工具。
- 若返回 0 词 → 音频虽有流但静音 → 调查
- 若词数 < 脚本的 80% → 音频被截断 → 调查
- 对比最后转录词与最后脚本词

**步骤 4：呈现结构化审查** 给用户，包含文件统计、音频验证结果、视觉发现和字幕状态，然后才宣布视频完成。

## 质量检查清单

- [ ] 合成时长等于场景时长之和减去转场重叠
- [ ] 所有 `staticFile()` 引用解析到存在的素材
- [ ] 转场不截断内容（计时中考虑重叠）
- [ ] **渲染输出中存在音频流**（ffprobe 确认 codec_type: "audio"）
- [ ] **旁白词数通过转录验证**（不能仅从 props 假设）
- [ ] 音频层与视觉场景同步
- [ ] 字幕渲染正确（优先 Remotion CaptionOverlay 而非 FFmpeg SRT）
- [ ] 主题颜色匹配当前风格剧本
- [ ] 输出分辨率和 FPS 匹配目标媒体 profile
- [ ] 渲染完成无 Chromium 超时错误
- [ ] 最终输出在目标平台播放正常
- [ ] 含文字场景（CTA、标题）使用 Remotion text_card，而非带文字的 AI 生成图片
