---
name: openmontage-talking-head-asset-director
version: "1.0.0"
description: 为口播视频生成字幕、音频、背景音乐与叠加图形等配套素材，并汇总为素材清单。适用于已有分镜方案与脚本、需要批量产出并校验支撑素材的口播制作阶段。
metadata:
  license: AGPL-3.0
---

# 素材导演 — 口播流水线

## 适用场景

当你手上已有分镜方案（scene plan）和脚本时，本阶段负责为该口播视频产出全部辅助素材：字幕文件、抽取并处理的音轨、叠加图形（图表、文字卡、数据揭示），以及必要的补充视觉素材。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 校验产物结构 |
| 前置产物 | 分镜方案、脚本 | 决定要生成哪些素材 |
| 工具 | `subtitle_gen`、`audio_mixer` | 字幕与音频生成 |
| 工具 | `image_selector`（可选） | 叠加层所用图库图片 |
| 工具 | `pixabay_music`（可选） | 免版税背景音乐 |

## 流程

### 第 0 步：主场景样片（强制）

在批量生成素材之前必须先做这件事：

1. 找出整支视频里视觉最重要的那个主场景
2. 只为该场景产出一份样例素材（字幕样式、叠加层或背景任选其一）
3. 呈现给用户，并说明大意：“这是全片最关键场景的视觉方向，是否符合你的预期？确认后我会沿用这套风格产出其余素材。”
4. 等待用户确认后再进入批量生成

这一步的目的是规避代价最高的失误：一口气按错误方向生成十几份素材。

### 第 1 步：生成字幕

基于脚本阶段得到的转写数据制作：

- 带逐词时间轴的 SRT 或 ASS 字幕文件
- 按当前风格手册设定字体、字号、颜色、位置

若分镜方案里带有 `corrections` 字典，需把它传给 `subtitle_gen`：

```
# 传入转写片段与纠错词典，限定每行词数并指定输出路径
subtitle_gen.execute({
    "segments": <transcript_segments>,
    "corrections": {"cloud": "Claude"},
    "max_words_per_line": 5,
    "output_path": "<project>/assets/subtitles/subtitles.srt"
})
```

### 第 2 步：抽取并处理音频

- 从原始素材中分离音轨
- 视情况降噪（借助 `audio_mixer`）
- 对音量做归一化

### 第 3 步：获取背景音乐

若分镜方案要求配背景音乐：

1. **先查本地 pixabay 音乐库**——寻找与目标情绪吻合的已下载 MP3
2. **调用 `pixabay_music` 工具**——用分镜方案里的情绪/曲风关键词检索
3. **对选中的曲子跑 `audio_energy` 分析**——找出最佳起播偏移，跳过开头安静段

把音乐路径、偏移量、是否需要循环等信息记录进素材清单。

### 第 4 步：生成叠加素材

若分镜方案里含叠加场景（来自场景导演的“观看并提议”环节），需要为每一处生成对应素材。

**交由 Remotion 渲染的叠加层**（图表、对比、KPI 网格、数据卡）：

为每个叠加层编写一段 composition JSON。这些最终由合成导演渲染。每个叠加层需要：

```json
{
  "overlay_id": "overlay_1",
  "remotion_cut": {
    "id": "term-agentic-ai",
    "type": "callout",
    "text": "智能体：能自主朝目标行动的软件",
    "in_seconds": 0,
    "out_seconds": 4,
    "backgroundColor": "<theme_background>",
    "accentColor": "<theme_accent>",
    "icon": "💡"
  },
  "overlay_timestamp": 22.0,
  "position": "lower_third"
}
```

**叠加类型 → Remotion cut 映射：**

| 分镜叠加 | Remotion `type` | 必填属性 |
|----------|-----------------|----------|
| 术语定义 | `callout` | `text`、`icon`（可选） |
| 数据/数字 | `stat_card` | `stat`（数值）、`text`（标签） |
| 对比 | `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` |
| 柱状图 | `bar_chart` | `chartData`（`{label, value}` 数组） |
| 饼图 | `pie_chart` | `chartData`（`{label, value}` 数组） |
| 折线图 | `line_chart` | `chartSeries`（`{name, data: number[]}` 数组） |
| KPI 面板 | `kpi_grid` | `chartData`（`{label, value}` 数组）——数值宜小并带后缀，如 "2.4M" |
| 进度指示 | `progress_bar` | `progress`（0-100）、`text` |
| 章节标题 | `hero_title` | `text`、`subtitle`（可选） |
| 引用/提示 | `callout` | `text`、`icon` |
| 下三分之一 | `text_card` | `text` |

**Remotion AnimatedBackground：**

Explainer composition 现含一个 `AnimatedBackground` 组件，能渲染动态渐变网格、漂浮光斑与细网格纹样，观感远胜纯色背景。

- 场景背景应使用当前主题背景色，让 AnimatedBackground 与叠加卡片视觉统一
- 不要随手用纯色做背景——交给 AnimatedBackground 与主题决定
- 抠绿幕素材时，用 AnimatedBackground 作为替换背景（见合成导演第 3c 步）

**组件约束：**

| 组件 | 最小宽度 | 720px 竖屏可用？ | 数值类型 |
|------|----------|------------------|----------|
| comparison | 900px | 否 → 改用两个 stat_card | 字符串 |
| kpi_grid | 720px | 是 | 仅限纯数值（不可 "15+"） |
| bar_chart | 500px | 是 | 数值 |
| stat_card | 300px | 是 | 字符串可 |
| callout | 400px | 是 | 字符串 |
| hero_title | 400px | 是 | 字符串 |
| line_chart | 500px | 是 | 数值 |
| progress_bar | 600px | 是 | 数值 |
| stat_reveal | 300px | 是 | 字符串可 |

关键规则：

- `comparison` 需要 900px 以上宽度；在 720px 竖屏下请换成两个依次出现的 `stat_card`
- `kpi_grid` 的值必须是纯数字（如 `4.8`、`73`、`2400`）。写成 `"15+"`、`"$4.8B"`、`"2.4M"` 这类带格式的字符串会引发渲染错误，改用 `stat_card` 承载
- 选组件前先确认目标画幅宽度，竖屏（720px）排除 `comparison`

**叠加配色规则**——叠加层的背景色、强调色与文字色都从选定的风格手册或自定义视觉身份推导。只有素材/题材需要时才用深色卡片；明亮的编辑风谈话视频完全可以用浅色卡片，只要对比足够。

**简单文字叠加层**（若上 Remotion 太重）：

用 FFmpeg 或 PIL 生成 PNG，存放在 `<project>/assets/overlays/overlay_<id>.png`。

### 第 5 步：构建素材清单

把生成的素材以路径、类型、工具引用形式记录：

```json
{
  "subtitles": {
    "path": "assets/subtitles/subtitles.srt",
    "format": "srt",
    "word_count": 208
  },
  "music": {
    "path": "assets/audio/bg_music.mp3",
    "offset_seconds": 3.5,
    "needs_loop": true
  },
  "overlays": [
    {
      "overlay_id": "overlay_1",
      "type": "callout",
      "timestamp": 22.0,
      "duration": 4.0,
      "remotion_cut": { ... },
      "position": "lower_third"
    }
  ],
  "transcript_segments": "assets/audio/transcript.json"
}
```

### 第 6 步：自检

| 检查项 | 自问 |
|--------|------|
| **字幕** | 字幕文件存在且与语音时间轴吻合吗？ |
| **音频** | 音轨是否干净且做过归一化？ |
| **音乐** | 是否为确定最佳偏移而对音乐跑过 audio_energy？ |
| **叠加层** | 分镜方案里每个叠加层都有对应素材吗？ |
| **叠加内容** | 叠加层里的数据与讲者实际所说一致吗？ |
| **文件** | 所有素材路径都指向真实存在的文件吗？ |

### 第 7 步：提交

按 schema 校验 asset_manifest，并通过 checkpoint 持久化。

### 制作中途的事实核验

生成素材时若遇到不确定的地方：

- 用 `web_search` 核对拍摄对象的视觉真实性（例如这栋楼到底长什么样？）
- 生成插画前先用 `web_search` 找参考图
- 在决策日志中留痕：`category="visual_accuracy_check"`

视觉准确度很重要。脚本提到具体地点、人物或物件时，先核实其真实样貌再生成图像，不要依赖模型训练数据——它可能出错或过时。

## 遇到不会做的事怎么办

若碰到拿不准的生成手法、供应商行为或提示模式：

1. **联网检索**当下最佳实践——模型与 API 变动频繁，智能体的训练知识可能已过期
2. **查阅 `.agents/skills/`** 中已有的 Layer 3 知识（各供应商的提示指南、API 范式）
3. **若以上都无解**，在 `projects/<project-name>/skills/<name.md>` 写一份项目级技能文档记录所学
4. **附上来源 URL**，让知识可溯源
5. **记入决策日志**：`category: "capability_extension"`，`subject: "learned technique: <name>"`

以下情形尤其需要这样做：

- **视频生成提示**——模型对不同版本词汇的反应各不相同
- **图像模型参数**——FLUX、GPT Image、Imagen 的最佳设置各有差异且持续演变
- **音频供应商怪癖**——声音克隆、音乐生成、TTS 各有模型专属的最佳实践
- **Remotion 组件模式**——框架演进过程中会涌现新的 composition 技巧

不要依赖过期知识，拿不准就先搜。

---

## 关卡提醒（强制）

本阶段设有人工审批关卡（`human_approval_default: true`）。审核通过后：以 `status="awaiting_human"` 打 checkpoint，展示摘要（Backlot 面板会渲染产物），然后**结束本轮**。不要在同一条回复里启动下一阶段。审批按关卡独立计算——早先某次的“继续”不覆盖本关。
