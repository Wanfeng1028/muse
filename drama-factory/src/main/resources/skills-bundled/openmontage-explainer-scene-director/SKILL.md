---
name: openmontage-explainer-scene-director
version: "1.0.0"
description: 把带时间戳的解说脚本转化为可视化分镜方案，规划每个镜头的画面类型、运动方式、转场与所需素材，适用于解说视频进入分镜规划阶段时使用。
metadata:
  license: AGPL-3.0
---

# 场景导演 — 解说管线

## 何时启用

你是生成式解说视频的场景规划者。手中已有一份 `script` 产物，包含带时间戳的段落与增强提示。你的职责是把文字稿转译成视觉方案：观众在每一秒看到什么、需要生成哪些素材、镜头之间如何衔接。

这是文字变成画面的环节。脚本再好，分镜规划失当也会产出令人费解的视频。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 脚本段落与提案包 |
| Playbook | 当前生效的风格手册 | 视觉语言、转场、运动规则 |
| 第 3 层 | `.agents/skills/flux-best-practices/`、`.agents/skills/beautiful-mermaid/`、`.agents/skills/manim-composer/` | 图像生成、图表、动画知识 |

## 流程

### 第一步：分析脚本

通读每一段，逐段记录：
- 这段在解释什么概念？
- 编剧埋下了哪些增强提示？
- 情绪节拍是什么？（好奇、揭示、强调、幽默、收束）
- 可用时长是多少？（end_seconds - start_seconds）

### 第二步：调研视觉方案

**用网络搜索**为本主题寻找视觉手法：

1. **头部创作者怎么可视化这个话题？** 检索 YouTube 封面、博客配图、会议幻灯片。
2. **哪些视觉隐喻有效？** 部分概念已有公认的图像表达（如神经网络用节点图、加密用锁与钥匙），直接用——观众一眼就懂。
3. **有什么新颖做法？** 有没有人没试过的角度？新鲜的可视化能让解说被记住。
4. **是否可行？** 把野心对齐到可用工具：`image_selector`（静态图）、`diagram_gen`（Mermaid 流程图/时序图）、`code_snippet`（带语法高亮的代码）、Remotion（动效、文字动画）、Manim（数学动画）。

若遇到现有技能都覆盖不了的可视化需求，用 **Skill Creator**（`skills/meta/skill-creator.md`）新建技能。

### 第三步：拆解为场景

把每段脚本拆成 1–3 个视觉场景，每个场景是一个独立的视觉时刻。

```json
{
  "id": "scene-3",
  "type": "diagram",
  "description": "Mermaid 流程图：query → encode → vector search → rank → return results。节点随旁白讲述逐步出现。",
  "start_seconds": 15,
  "end_seconds": 22,
  "script_section_id": "s3",
  "framing": "全屏图表，居中",
  "movement": "从左到右渐进揭示",
  "transition_in": "fade",
  "transition_out": "dissolve",
  "overlay_notes": "每个节点出现时同步标注",
  "required_assets": [
    {
      "type": "diagram",
      "description": "Mermaid 流程图：query → encode embedding → vector search (ANN) → rank by cosine similarity → return top-k results",
      "source": "generate"
    }
  ]
}
```

#### 渲染模板与场景类型

场景方案中 `scene_plan.scenes[].type` 的规范取值为 `talking_head`、`broll`、`animation`、`character_scene`、`diagram`、`text_card`、`transition`、`generated`、`screen_recording`。`hero_title`、`stat_card` 以及下方各类图表/卡片名称属于下游 Remotion 的 `cut.type` 模板，不是合法的场景类型。分镜阶段请按需选用 `text_card` 或 `animation`，并在场景描述里写明打算使用的渲染模板；剪辑阶段再把它转成 `cut.type`。

| 渲染模板或场景类型 | 适用场景 | 可用工具 | 时长建议 |
|------|----------|---------|---------|
| `hero_title` | 开场标题、戏剧性揭示 | Remotion HeroTitle（主题驱动标题） | 3–5s |
| `stat_card` | 醒目数字、冲击性指标 | Remotion StatCard（大号数据 + 副标题） | 4–6s |
| `bar_chart` | 类别对比、排名 | Remotion BarChart（生长/滑入/弹出动画） | 5–7s |
| `line_chart` | 趋势、时间序列、增长曲线 | Remotion LineChart（描线/淡入，支持多序列） | 5–7s |
| `pie_chart` | 占比、拆分、分布 | Remotion PieChart（环形模式、中心标签、旋转/展开） | 5–7s |
| `kpi_grid` | 仪表盘、拉新指标、速览数据 | Remotion KPIGrid（2–4 列，计数/弹出/级联） | 5–7s |
| `comparison` | 前后对比、A/B、对照 | Remotion ComparisonCard（双值 + 分隔线） | 4–6s |
| `callout` | 专家引语、提示、警告、要点 | Remotion CalloutBox（info/warning/tip/quote） | 4–6s |
| `progress_bar` | 进程可视化、完成度、堆叠指标 | Remotion ProgressBar（填充/脉冲/步进） | 4–6s |
| `text_card` | 陈述、收尾信息、关键术语 | Remotion TextCard（居中，弹簧动画） | 3–5s |
| `animation` | 需要运动才能说明的概念（数据流、数学） | Remotion、Manim | 4–10s |
| `diagram` | 流程、架构、关系 | `diagram_gen`（Mermaid）、`image_selector` | 4–8s |
| `generated` | 插画、隐喻、写实图像 | `image_selector`（FLUX/GPT Image） | 3–6s |
| `talking_head` | AI 数字人出镜（若 HeyGen 可用） | HeyGen 工具 | 5–15s |
| `broll` | 背景交代、现实案例 | 素材库或生成片段 | 3–6s |
| `screen_recording` | 代码演示、界面走查 | 实录或模拟 | 5–15s |

**零密钥场景选择：** 当没有可用的图像/视频生成能力时，规划 `text_card`、`animation` 或 `diagram` 场景，并在每个描述中指明下游模板（`hero_title`、`stat_card`、图表、`comparison`、`callout` 或 `progress_bar`）。这些完全由 Remotion 组件渲染，零外部依赖。

### 第四步：套用视觉技法库

以下是解说视频中经过验证的模式，在场景描述中按名称引用：

**图解渐显（Diagram Reveal）**
图表逐步搭建——从空白开始，随旁白介绍逐个加入组件与标签。适合架构、流程、系统。
- 工具：Mermaid + Remotion 动画，或 FLUX 生成图
- 示例：“展示向量数据库架构。旁白说到‘嵌入’时加入编码器节点，说到‘检索’时加入索引。”

**类比可视化（Analogy Visualization）**
把抽象概念与它的现实类比并排呈现，分屏或左右对照。
- 工具：两侧都用 `image_selector`
- 示例：“左侧：真实的向量空间，散点分布。右侧：按主题归置图书的图书馆。”

**数据卡重击（Stat Card Punch）**
全屏数字配冲击动画（放大、轻微回弹）。使用 `stat_card` 类型，背景与强调色取自本视频的视觉识别。停留 4–5 秒。
- 工具：Remotion StatCard 组件
- 示例：stat="1ms"，subtitle="对比传统检索的 500ms"，accentColor="<theme_accent>"

**数据仪表盘序列（Data Dashboard Sequence）**
用一串数据可视化场景，以数字讲一个故事。先给 KPI 总览，再下钻到具体图表。用 section_title 覆盖层把相关数据归组。此模式无需任何外部工具。
- 工具：Remotion 图表组件（bar_chart、line_chart、pie_chart、kpi_grid）
- 示例：kpi_grid（4 个关键指标）→ bar_chart（拆分）→ line_chart（趋势）→ pie_chart（分布）
- 背景处理依据视觉识别选择：戏剧化/技术题材用暗色，亲和/教育题材用亮色，主题需要时用纹理或暖调。

**前后对照（Before/After Split）**
先呈现问题，再用 `comparison` 类型展示方案。对比卡以动画入场并排展示两个数值。
- 工具：Remotion ComparisonCard 组件
- 示例：leftLabel="Before"，leftValue="500ms"，rightLabel="After"，rightValue="1ms"

**时间轴推进（Timeline Progression）**
从左到右或从上到下呈现演进或流程步骤，随旁白讲述逐步出现。
- 工具：Remotion 动画元素或 Mermaid timeline
- 示例：“1990：关键词检索 → 2010：语义检索 → 2020：向量数据库 → 2024：多模态检索”

**缩放聚焦（Zoom and Focus）**
先给出系统全景，再放大到某个组件细讲，建立空间语境。
- 工具：Remotion 对生成图做缩放动画
- 示例：“展示完整系统架构。放大到‘嵌入模型’组件。”

**代码走查（Code Walkthrough）**
展示带语法高亮的代码，随旁白高亮具体行，可做打字或渐进揭示。
- 工具：`code_snippet` 工具 + Remotion
- 示例：“Python 代码：`results = collection.query(embedding, n_results=5)`。旁白说到‘向量’时高亮 `embedding` 参数。”

### 第四步之补充 b：带时长预算撰写旁白

若视频含旁白，脚本**必须**按视频时长来写。

**时长预算公式：**
1. 由场景时间点推算视频总长（最后一个 cut 的 `out_seconds`）。
2. 旁白目标占视频时长的 **85–90%**，给开场与收尾留呼吸空间。
3. 词数预算：纪录片风格含自然停顿按 **2.0–2.5 词/秒**；快节奏风格按 **2.5–3.0 词/秒**。
4. 示例：53s 视频 → 旁白目标 45–48s → 纪录片风格最多 90–120 词，快节奏最多 112–144 词。

**逐场景词数预算：**
- 按各场景时长比例分配词数。
- 5s 场景约 10–12 词，6s 场景约 12–15 词。
- 场景切换之间留 0.5–1s 静默，给画面呼吸。

**校验（TTS 生成前必做）：**
- [ ] 总词数符合目标时长预算
- [ ] 没有任何场景的旁白超出其时间槽
- [ ] 开场与收尾场景旁白简短（让画面说话）

**TTS 生成之后：**
- TTS 工具会返回 `audio_duration_seconds`，与视频时长比对。
- 若旁白超出视频时长 1s 以上，要么删改脚本重新生成，要么延长视频收尾场景。
- 渲染前务必运行 `composition_validator`，自动捕获不匹配。

### 第四步之补充 c：五要素场景方案清单

> 每个场景都必须写明全部五个要素。对于图表、数据图与 Remotion 原生场景，“主体”可对应被前景化的数据元素，“相机”可标 N/A——但必须**显式**标注（例如 `"camera": "N/A — Remotion native scene, no virtual camera"`）。静默省略是最常见的失败模式，会导致模型输出不可预测、提示词脆弱、评审反复返工。
>
> 1. **主体** — 类型 + 关键视觉属性；若为多个，说明如何区分。图表场景中即被前景化的数据元素（被强调的节点、柱、KPI）。生成图像中即被描绘的人/物/概念。
> 2. **主体运动** — 按时间顺序的动作；动画图表中即节点/边/数值出现或变化的顺序。
> 3. **场景** — 覆盖层（单独列出！）+ 视角 + 环境 + 时段 + 场景动态。Remotion 场景中“环境”对应背景处理 + 主题。
> 4. **空间构图** — 景别 + 画面位置 + 景深（前/中/后）+ 相对机位高度；以及这些如何**变化**。静态 Remotion 场景要记录布局网格与占据视觉中心的元素。
> 5. **相机** — 播放速度 → 镜头畸变 → 高度 → 角度 → 对焦/景深 → 稳定性 → 运动。原生 Remotion 场景标 N/A；`generated`/`broll`/`image_animation` 场景须完整写明。
>
> 原语词汇参见 `skills/creative/video-gen-prompting.md`。

> **覆盖层提醒。** 覆盖层（标题、字幕、HUD、水印、画框图形、下三分之一、section_title 条、stat_reveal 芯片、hero_title 覆盖层、供应商芯片）**不属于**场景的前/中/后景深轴。请在场景元数据（`overlays: [...]`）中单独列出内容与位置。切勿把覆盖层描述成“位于前景”——这会同时误导下游工具与任何重新分析成片的视频理解模型。

### 第五步：对照风格手册校验

风格手册约束你的视觉选择：

| 手册字段 | 对场景的影响 |
|----------------|-------------|
| `visual_language.color_palette` | 所有生成图与图表必须使用这些颜色 |
| `visual_language.composition` | 构图规则（三分法、居中等等） |
| `motion.transitions` | 允许的转场类型（如 `gentle-fade`、`soft-dissolve`） |
| `motion.animation_style` | 动画质感（如 `ease-in-out, organic curves`） |
| `motion.pacing_rules` | 最短停留时间（如“定场镜头至少停留 2s”） |
| `asset_generation.image_prompt_prefix` | 提炼为一句简短的视觉锚点，不要逐字粘进所有提示词 |
| `asset_generation.consistency_anchors` | 所有图像间必须保持一致的东西（色板、光照、风格） |

**提交前清单：**
- [ ] 每个场景都使用与手册兼容的转场
- [ ] 所有 required_asset 描述都包含手册中的风格线索
- [ ] 没有任何场景违反节奏规则（最短/最长时长）
- [ ] 图像描述引用了本视频真实的视觉识别，而不只是一个预设名

### 第六步：核对覆盖度与多样性

**覆盖度检查：**
- [ ] 场景覆盖整段脚本时长（首场景从 0s 开始，末场景结束于 total_duration）
- [ ] 每段脚本至少对应一个场景
- [ ] 场景之间无超过 1s 的空隙（除非是有意的停顿）
- [ ] 脚本中所有增强提示都被某个场景或 required_asset 承接

**多样性检查：**
- [ ] 同类场景连续不超过 3 个
- [ ] 全片至少使用 3 种不同场景类型
- [ ] 视觉节奏在高信息密度场景（图表、动画）与呼吸场景（文字卡、生成图）之间交替

**可行性检查：**
- [ ] 每个 `source: "generate"` 的 `required_asset` 都能用现有工具完成
- [ ] 图表描述足够具体，可直接生成 Mermaid 语法
- [ ] 图像描述足够具体，可做 FLUX/GPT Image 提示词工程
- [ ] 没有任何场景依赖工具注册表之外的工具

### 第七步：自评

打分（1–5）：

| 维度 | 问题 |
|-----------|------|
| **视觉叙事** | 每个场景是否推进理解，而非单纯装饰？ |
| **脚本对齐** | 每个场景是否匹配旁白此刻在讲的内容？ |
| **技法多样性** | 是否用了多种视觉技法，而非只一种？ |
| **手册忠实度** | 每个场景看上去是否属于同一支视频？ |
| **素材可行性** | 每个 required_asset 是否都能用现有工具生成？ |
| **节奏** | 视觉节律是否自然？高信息场景与呼吸空间是否平衡？ |

任一维度低于 3 分则返工。

### 第八步：提交

将 `scene_plan_json` 按规范场景方案 schema 校验，通过检查点协议持久化，并附上阶段评审。解说管线没有单独的提交函数。

## 常见陷阱

- **一段一个场景**：脚本段落常覆盖多个概念。10 秒的段落可能需要 2–3 个视觉场景，否则画面停滞乏味。
- **忽视增强提示**：编剧在 `enhancement_cues` 里埋了视觉意图，别无视——那代表编剧的视觉设想。
- **动画野心过大**：“数据中心的写实 3D 飞越”用现有工具做不出来。保持可执行。
- **没有转场策略**：随机转场显得混乱。按手册的转场规则统一处理，特殊转场只留给主题切换。
- **required_assets 含糊**：“一张关于数据库的图”对提示词工程毫无用处。“等距插画：向量数据库，嵌入向量悬浮在三维空间，使用手册的蓝绿色板”才可执行。
- **预设思维**：只写“做成扁平动效”远远不够。规划者必须说明本视频的动效**为何与众不同**。
- **动态概念配静态画面**：旁白在讲过程或变化，画面就该动。用动画或渐进揭示，别用静态图。
- **含精确文字的 CTA/收尾屏用 `generated` 类型**：AI 图像模型会瞎编文字——错的公司名、拼错的词、错的电话。任何含逐字文字的场面（CTA、商家信息、联系方式、法律声明）**必须**用 `type: "text_card"`，由 Remotion 精确渲染文字。文字准确性重要的场景，绝不规划为 `generated` 图。

---

## 关卡提醒（强制）

本阶段以人工审批为关卡（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一个回复里启动下一阶段。审批按关卡生效——早前的“继续”不覆盖本关卡。
