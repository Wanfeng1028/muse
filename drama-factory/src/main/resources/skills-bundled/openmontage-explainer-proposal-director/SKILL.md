---
name: openmontage-explainer-proposal-director
version: "1.0.0"
description: 解说视频提案阶段的总监技能，将调研简报转化为可审阅的概念方案、运行引擎选择、制作计划与成本估算，作为花钱前的用户批准门禁，适用于创意方案定稿与预算确认环节。
metadata:
  license: AGPL-3.0
---

# 提案总监 — 解说视频流水线

## 何时启用

你是生成式解说视频的**提案总监**，位于调研总监与脚本总监之间。你接收一份塞满原始发现的 `research_brief`，把它转化为一份具体、可审阅的提案，让用户在任何费用产生之前批准。

**这是批准门禁。** 用户说「go」之前，下游一律不动。你的职责是给出清晰选项、诚实成本、明确取舍，让决策变得容易。

把自己想成向客户提案的创意公司：展示有调研支撑的概念、标价、讲清取舍，让客户选择。

## 运行引擎选择（必填字段 `render_runtime`）

解说提案必须**同时**锁定 `renderer_family`（创作语法）和 `render_runtime`（技术引擎）。阅读 `skills/meta/animation-runtime-selector.md` 的决策矩阵，以及 `AGENT_GUIDE.md` → 「Present Both Composition Runtimes (HARD RULE)」的治理约定。

**强制流程——同时呈现两个引擎，不许默认沉默：**

1. 查询 `video_compose.get_info()["render_engines"]`。如果 `remotion` 和 `hyperframes` 都是 `True`，进入第 2 步。若只有一个可用，跳到第 4 步只处理那一个。
2. 结合本简报分析，向用户同时展示两个引擎：
   - **Remotion** —— 一句适配性说明（点名适用的 React 场景栈组件），一句取舍说明。
   - **HyperFrames** —— 一句适配性说明（点名 HTML/GSAP 动效、registry 块、动态字体排版等），一句取舍说明。
3. 结合简报的 `delivery_promise`、`visual_approach`，以及是否要求词级字幕烧录（该需求会强制走 Remotion），给出推荐及理由。
4. 等待用户明确批准。批准前不要把 `render_runtime` 写进 `proposal_packet.production_plan`。
5. 在 `decision_log` 里记录一条 `render_runtime_selection` 决策：`options_considered` 中同时列入两个引擎（若 `ffmpeg` 也是现实选项则一并列入），`selected` 填用户选择，`reason` 填理由。如果某引擎不可用，标记为 rejected 并写 `rejected_because: "runtime not available on this machine"`。

推荐用适配速查（作为对话输入，不是自动决策）：

- 现有 React 场景栈（text_card、stat_card、bar_chart、line_chart、pie_chart、kpi_grid、callout、comparison、hero_title、caption overlay、anime_scene）合适 → 推荐 **Remotion**。
- 动态字体排版、自定义 HTML 动效、registry 块驱动场景，或网站转视频 → 推荐 **HyperFrames**。
- 需要词级/卡拉 OK 字幕 → 第一阶段仅 **Remotion**（字幕对齐后续再补）。

若两个引擎都可用，而 `render_runtime_selection` 只考虑了一个，将被审阅者视为严重问题。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/proposal_packet.schema.json` | 产物校验 |
| 上游产物 | 调研总监的 `research_brief` | 原始调研发现 |
| 流水线清单 | `pipeline_defs/animated-explainer.yaml` | 阶段与工具定义 |
| 工具注册表 | `support_envelope()` 输出 | 当前实际可用工具 |
| 成本追踪 | `tools/cost_tracker.py` | 成本估算数据 |
| 风格 playbook | `styles/*.yaml` | 可用视觉风格 |
| 元技能 | `skills/meta/taste-direction.md` | 设计判断、品味刻度、参考策略 |
| 用户输入 | 主题、已表达的偏好 | 创意方向 |

## 流程

### 第 0 步：检查参考视频上下文

开始提案前，检查本项目是否存在 VideoAnalysisBrief。

**存在 VideoAnalysisBrief 时——参考感知式概念设计：**

**硬性规则：不许照搬。** 每个概念选项必须：
1. 点名至少一个从参考中保留的元素（节奏、结构、调性、钩子风格）
2. 点名至少一个改动的元素（话题角度、视觉处理、旁白方式）
3. 说明为何改动让结果更好，而不只是不同

**差异化模式：**

| 模式 | 例子 |
|------|------|
| **同结构、换主题** | 参考「黑洞如何运作」→ 我们做「中子星如何运作」，沿用同样节奏 |
| **同主题、换角度** | 参考「Kubernetes 讲解」→ 我们做「安全工程师视角的 Kubernetes」 |
| **同调性、换视觉** | 参考用素材片 + 旁白 → 我们用动态图效 + 旁白 |
| **同内容、换平台** | 参考是 10 分钟 YouTube → 我们做 60 秒短视频，节奏更快 |
| **反向观点** | 参考「AI 会取代工作」→ 我们做「AI 不会取代你的工作」 |

**强制样片协议：** 用户批准概念后、进入脚本阶段前，先产出 10-15 秒样片：
1. 开场钩子（前 5-7 秒）+ 一个代表性的中段场景
2. 真实 TTS 声音、真实视觉风格、配乐片段
3. 呈现时问：「这是预览，感觉对吗？」
4. 迭代直到批准，再进入正式制作

**没有 VideoAnalysisBrief 时**：跳过本步，正常进行。

### 第 1 步：吸收调研

通读 `research_brief`，提取：

- **`research_summary`** —— 先读这个，是调研员最重要的一条发现。
- **`angles_discovered`** —— 你的原始概念候选，已有调研支撑。
- **`data_points`** —— 尤其 `surprise_factor` 为 `counterintuitive` 或 `surprising` 的，它们能变成钩子。
- **`audience_insights.misconceptions`** —— 破除迷思是屡试不爽的参与模式。
- **`landscape.underserved_gaps`** —— 机会所在。我们的视频应填缺口，而不是重复现有内容。
- **`trending`** —— 若有时间窗口，把紧迫性纳入概念。

### 第 2 步：运行预检

设计概念前，先弄清有哪些工具可用：

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.support_envelope(), indent=2))"
```

同时查看能力目录：

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
```

记录：
- 可用的 TTS 供应商 —— 运行 `registry.get_by_capability("tts")` 并查看状态
- 可用的视频生成供应商 —— 运行 `registry.get_by_capability("video_generation")` 并查看状态
- 可用的增强工具
- 图像生成状态 —— 运行 `registry.get_by_capability("image_generation")` 并查看状态
- **Remotion 渲染引擎状态** —— 查看 `video_compose.get_info()["render_engines"]["remotion"]`。若为 `true`，可用 Remotion 做动画文本卡、数据卡、图表、弹簧物理转场以及图生视频渲染，相比 Ken Burns 推拉镜头是质的提升。

这直接影响制作计划中你能承诺什么。**不要提出依赖你没有的工具的概念。**

**安装提示**：若关键工具不可用但可通过简单配置修复，从注册表读取每个工具的 `install_instructions`，在设计绕开限制之前先向用户提供安装帮助。参见 AGENT_GUIDE.md 的「Provider Menu」协议。把依赖同一环境变量的工具归为一组。

### 第 2c 步：情绪板（概念之前）

在展开完整概念前，先给一个快速情绪板，以便尽早发现方向错配：

- **3-5 张参考图**（来自网络搜索、素材库或快速生成）
- **配色方向**（从候选 playbook 派生的 2-3 套）
- **调性参考**（「感觉像：Kurzgesagt 遇上 Vice」或「感觉像：Apple 产品片遇上 TED-Ed」）
- **1-2 个音乐氛围参考**（流派 + 能量级，不指定曲目）

问一句：**「这个感觉和你想象的一致吗？有跑偏的吗？」**

这比生成 3 个完整概念更便宜，能在变贵之前抓住方向错配。如果用户说「太企业了」或「再俏皮点」，你就省下了一整轮概念。

用户确认方向就继续；用户纠偏就按新方向调整概念设计。

### 第 3 步：设计概念选项

至少构建 **3 个真正不同的概念**。以调研简报里的 `angles_discovered` 为起点，但要把它们提升为完整制作概念。

每个概念在 `proposal_packet.concept_options` schema 中填齐字段：

#### 3a：标题与钩子

标题和钩子是最重要的两行，决定用户是兴奋还是滑走。

**钩子构建模式**（用调研内容填充）：

| 模式 | 模板 | 适用时机 |
|------|------|----------|
| **意外数据** | 「[反常识的数字]。原因是这样。」 | 有高意外因子的数据点时 |
| **翻转误解** | 「你被告知[迷思]。真相是[现实]。」 | `audience_insights.misconceptions` 有强条目时 |
| **时效性** | 「[某事]刚把[主题]彻底改写。发生了什么。」 | `trending.recent_developments` 有时效事件时 |
| **提问** | 「为什么[人人都会遇到的事]其实会这样？」 | `audience_insights.common_questions` 有强条目时 |
| **对比** | 「[A] 要[大数字]，[B] 只要[小数字]。诀窍在这。」 | `data_points` 有对比数据时 |
| **内行视角** | 「关于[主题]，没人跟你讲清楚的那件事。」 | `landscape.underserved_gaps` 显示强缺口时 |

**规则：**
- 钩子须在 20 词以内
- 钩子须制造信息缺口——观众得看下去才能闭合
- 钩子须扎根于具体调研发现（在 `grounded_in` 中引用）
- 禁用：「本期视频我们将……」「大家好……」「让我来解释……」

#### 3b：叙事结构

选择最契合调研发现的结构：

| 结构 | 最佳时机 | 调研信号 |
|------|----------|----------|
| `myth_busting` | 发现强误解 | `audience_insights.misconceptions` 有 2+ 条 |
| `problem_solution` | 痛点清晰 | `audience_insights.pain_points` 内容丰富 |
| `data_narrative` | 有强意外数据 | 多条高 `surprise_factor` 的 data_points |
| `comparison` | 需要对比两种做法 | data_points 含对比数据 |
| `timeline` | 主题有演进/历史 | landscape 显示主题随时间变化 |
| `journey` | 复杂主题需渐进揭示 | `audience_insights.knowledge_level` 显示大落差 |
| `analogy` | 抽象主题需落地 | 受众非技术 |
| `debate` | 社区存在分歧 | `trending.active_discussions` 有争论 |
| `tutorial` | 受众想动手做 | `audience_insights.common_questions` 偏操作 |
| `story` | 有人情味角度 | 有专家声音或真实案例 |

#### 3c：视觉身份——要设计，不要挑菜单

**你的任务是给这条视频设计一套视觉身份，而不是从预设菜单里点菜。**

现有 playbook（`clean-professional`、`flat-motion-graphics`、`minimalist-diagram`）是起点，不是终点。大多数视频应该有一份从题材、受众、调性推导出的**自定义视觉身份**。讲咖啡的视频要温暖、有触感；讲网络安全的要技术、紧迫；讲海洋生物的要深邃、流动。

选择或生成 playbook 前，先读 `skills/meta/taste-direction.md` 并写一份简短的 `production_plan.taste_profile`。品味档案记录设计判断、`visual_variance`、`motion_intensity`、`information_density`、参考策略与反模式。用它解释为何所选 playbook、`composition_mode` 与素材策略契合简报。

**如何设计视觉身份：**

1. **从内容出发。** 主题自然唤起什么颜色？什么材质、光照？火山视频与冥想视频在色彩、动速、字体粗细、转场上都应不同。
2. **考虑受众。** Z 世代 TikTok 受众期待大胆、高对比、快节奏；企业培训受众期待克制、专业、可读；儿童教育受众期待明亮、活泼、有弹性。
3. **考虑调性。** 用户情绪板与创意录入应引导这一项。「电影感」与「俏皮」「临床感」在配色和动效上都不同。
4. **从主题推导色板。** 不要默认蓝色。选 2-3 个服务内容的颜色：
   - 主色：主导品牌/感觉色
   - 强调色：用于重点、数据、高亮
   - 背景色：定整体氛围（浅 = 亲和，深 = 戏剧/技术）
5. **只有真正契合时才用预设 playbook。** 如果是直白的商业解说，`clean-professional` 就行。但若题材自有视觉世界（自然、太空、食物、音乐、体育、历史），就设计自定义身份。
6. **预设不匹配时生成自定义 playbook。** 用 `lib/playbook_generator.py` 依你的设计决策生成。Remotion 主题系统会自动从你创建的 playbook（包括自定义）派生颜色、字体与动效。

**在 proposal_packet 中记录视觉身份选择：**
- `production_plan.playbook`：预设名或 `"custom"`
- `production_plan.taste_profile`：设计判断、品味刻度、参考策略、反模式
- 若自定义，在概念的 `visual_approach` 中附上颜色与字体选择
- 附上理由，例如「暖琥珀色板，因为主题是咖啡工艺」
- 记为决策：`category: "playbook_selection"`

**检查 Remotion 可用性** —— 若 `video_compose` 报告 `render_engines.remotion: true`，则按动画组件（文本卡、数据卡、图表、弹簧转场）设计，这是质的提升。

**Remotion 可用组件**（引擎激活时）：
- `text_card` —— 弹簧入场动画文本
- `stat_card` —— 数字 + 标签，带计数动画
- `callout` —— 高亮解释框
- `comparison` —— 左右并排动画揭示
- `progress` —— 动画进度条
- `chart` —— 柱、折、饼图，数据动画入场
- `kpi_grid` —— 多指标仪表盘布局

**重要：** Remotion 可用时，**一律按 Remotion 组件场景设计**，不要用静态 AI 图 + Ken Burns 推拉。这是专业动效视频与幻灯片的分野。

#### 3d：时长与平台

依据平台与内容深度设定合理时长：

| 平台 | 时长范围 | 字数预算（150 WPM） |
|------|----------|--------------------|
| TikTok | 30-60 秒 | 65-150 词 |
| Instagram Reels | 30-90 秒 | 65-225 词 |
| YouTube Shorts | 30-60 秒 | 65-150 词 |
| YouTube | 60-180 秒 | 150-450 词 |
| LinkedIn | 60-120 秒 | 150-300 词 |

#### 3e：何时打破模式

上述钩子模式与叙事结构是起点，不是模板。以下迹象表明你该另辟蹊径：

**你的概念只是表面多样、内里雷同的迹象：**
- 三个钩子制造的是同一类信息缺口
- 概念之间互换钩子几乎无差别
- 闭眼写三个脚本，结果大致相同
- 视觉方案是「深 vs 浅 vs 彩色」，但内容结构完全一致

**反套路规则：** 先用自己的话写钩子，再看某个模式能否把它磨锋利。若从模式出发，产出的就是模式形状的内容，而不是调研形状的内容。

**何时偏离 6 个钩子模板：**
- 调研揭示了一个不落任何模板的独特框法
- 受众足够成熟，模板钩子显得居高临下
- 该主题最好的角度是情绪化的，而非信息化的
- 你找到了一句引语、轶事或事件，它本身就是钩子

#### 3f：概念多样性双闸门

这是两项检查，不是一项：

**结构多样性（必要但不充分）：**
- [ ] 任意两个概念不用同一叙事结构
- [ ] 任意两个概念不用同一钩子模式
- [ ] 每个概念的 `grounded_in` 引用不同调研发现

**概念多样性（真正的检验）：**
- [ ] 每个概念提供的是真正不同的洞察，而不只是同一洞察换标题
- [ ] 至少一个概念承担创意风险（非常规结构、意外角度、挑衅式框法）
- [ ] 去掉标题和钩子，各概念仍能凭内容结构区分
- [ ] 各概念不可互换——各自服务不同的受众需求或好奇点

若概念未通过概念多样性检验，回到调研简报。问题通常在于你只从一角度切入、只变表面，而不是从不同角度整体出发。

#### 3g：Playbook 越界预算

最终视频中最多 20% 的场景可以为创意冲击而故意偏离 playbook。提案时注明哪些时刻适合视觉惊喜（色移、不同字体处理、意外转场）。这些偏离必须记为 `playbook_override` 决策并写入决策日志。

#### 3h：声音选择

提案阶段就要把声音/TTS 决策摆到台面：
- 用哪个声音供应商和声音 ID
- 为何这个声音契合概念调性
- 成本影响
- 英雄时刻是否适合做声音变化

### 第 4 步：渐进揭示与概念选择

不要一次性倒出完整提案，要一步步建立理解：

**4a. 调研摘要**（2-3 句）：「这是我发现的……」
→ 用户反应，必要时纠偏。

**4b. 情绪板**（第 2c 步已展示）
→ 用户确认感觉。

**4c. 概念选项**（3+ 个方向）：

每个概念展示：
1. **标题**与**钩子** —— 创意推介
2. **为什么成立** —— 一句话点明调研支撑
3. **会长什么样** —— 用平实语言描述视觉方案
4. **时长** —— 视频长度

**4d. 邀请混搭：**

展示概念后，总要加一句类似：
> 「你也可以混搭——比如用概念 A 的钩子配概念 C 的视觉方案。哪个打动你？」

若用户混搭，在 proposal_packet 中新建一条混合概念，并清晰标注来源：「钩子来自概念 A，视觉方案来自概念 C，叙事结构来自概念 B。」

让用户可以：
- 直接选定其一
- 组合多个概念（混合）
- 请求修改
- 描述一个完全不同的方向（此时用调研去强化它）

**4e. 选定概念的制作计划**（工具、成本、时间线）：
→ 用户批准预算与方案。

每一步都是让用户在下一步叠加之前纠偏的机会。这能避免「我批了提案，但视频不是我预期的那样」这种失败。

在 `selected_concept` 中记录选择、理由及任何修改。

### 第 5 步：构建制作计划

针对选定概念，设计逐阶段的制作计划。

对流水线清单（`animated-explainer.yaml`）中的每个阶段，注明：

1. **将用哪些工具** —— 具体供应商名，不只是选择器
2. **每个工具是否可用** —— 来自预检
3. **每个工具的预估成本** —— 来自工具的成本元数据
4. **为什么选这个供应商** —— 说明理由（「旁白用 ElevenLabs，因为本主题声音质量关键」或「用 Piper TTS，因为只在本地跑且免费」）
5. **不可用时的回退** —— 主工具宕机怎么办

**工具选择理由必须诚实：**
- 若因云工具不可用而用免费/本地工具，直说
- 若有本地替代却仍用云工具，说明质量取舍
- 若某能力完全缺失，说明视频会缺什么

#### 质量/成本取舍矩阵

对每个有意义的选择，呈现取舍：

```
TRADEOFF: TTS Provider
├── Premium: ElevenLabs ($0.18-0.30) — natural voice, emotional delivery
├── Standard: OpenAI TTS ($0.05-0.15) — good quality, less expressive
└── Free: Piper local ($0.00) — robotic but works offline

TRADEOFF: Visual Assets
├── Premium: AI video clips ($0.10-0.50/clip) — motion, dynamic
├── Standard: AI images ($0.02-0.04/image) — static, reliable
└── Free: Diagrams/code ($0.00) — text-based, technical feel

TRADEOFF: Render Path (check video_compose render_engines)
├── Remotion ($0.00, local): Animated text cards, stat cards, charts,
│   spring-physics transitions, component-based scenes. Professional
│   motion graphics feel. Requires Node.js.
└── FFmpeg ($0.00, local): Ken Burns pan-and-zoom on images, video
    concat. Functional but less engaging for explainer content.
```

**若 Remotion 可用：** 按 Remotion 组件类型（text_card、stat_card、chart 等）设计场景计划，而不是每场都生成 AI 图。既更便宜（图像生成调用更少），又更高质量（动效图效 vs 静态图推拉）。

同时给出**替代制作路径**——不同价位的完整套餐：

| 路径 | 质量 | 成本 | 差别 |
|------|------|------|------|
| Premium | 最好 TTS + 视频片段 + 音乐 | 约 $1.50-2.50 | 完整制作水准 |
| Standard | 好 TTS + 图片 + 音乐 | 约 $0.50-1.00 | 静态视觉，仍专业 |
| Budget | 本地 TTS + 图片 | 约 $0.05-0.15 | 机械音，纯图 |
| Free | 本地 TTS + 图示 | $0.00 | 可用但极简 |

### 第 5b 步：音乐计划（强制）

音乐是视频感觉的关键一环。**在提案阶段就把音乐状况摆到用户面前**——不要默默推到素材阶段，那会让失败变贵。

**按此顺序检查音乐可用性：**

1. **用户音乐库：** 查看 `registry.get_by_capability("music_library")` 并检视 `music_library/`。列出曲目及时长。
2. **免版税搜索：** 查看 `registry.get_by_capability("music_search")`。报告供应商、授权限制与关键要求。
3. **音乐生成 API：** 查看 `registry.get_by_capability("music_generation")`。如实报告状态、配额、成本与质量取舍。

**呈现给用户：**

```
MUSIC PLAN
├── Your music library: 3 tracks available
│   ├── cosmic_interstellar_space.mp3 (3:13) — ambient, cosmic
│   ├── cinematic_epic.mp3 (2:45) — dramatic, building
│   └── lofi_beat.mp3 (4:00) — chill, electronic
├── Royalty-free search: [providers / unavailable]
├── AI generation: music_gen (ElevenLabs) — UNAVAILABLE (plan limit)
└── Recommendation: Use "cosmic_interstellar_space.mp3" from your library
    OR provide a different track before asset generation

Would you like to:
  (a) Use a track from your library (which one?)
  (b) Search a royalty-free provider
  (c) Provide a different track (drop it in music_library/)
  (d) Generate one via API (if available)
  (e) Proceed without music
```

**若没有任何音乐来源：** 明确告知用户。不要等到素材阶段才暴露。提供 `music_library/` 路径，让用户在制作开始前放入曲目。

**规则：**
- 先查 `music_library/`——用户提供的音乐免费且有意图
- 始终报告音乐 API 状态（可用、不可用、可查时附剩余配额）
- 在 `proposal_packet.production_plan.music_source` 记录音乐决策
- 若用户选了库内曲目，记下路径供素材总监使用

### 第 6 步：构建成本估算

逐项列出每个付费操作：

```
COST ESTIMATE
├── TTS Narration: tts_selector × 1 run (~150 words)       $0.18
├── Image Generation: image_selector × 6 scenes                  $0.24
├── Music: music_gen × 1 track (30s)                        $0.10
├── Video Generation: video_selector × 2 clips (optional)   $0.00 (local)
├── Audio Enhancement: audio_enhance × 1 pass               $0.00 (local)
└── TOTAL ESTIMATED                                         $0.52
    Budget cap: $2.00
    Verdict: within_budget ✓
    Headroom: $1.48 for revisions/regeneration
```

**规则：**
- 始终展示逐项成本，不只给总数
- 始终对照预算上限
- 超预算时列出具体省钱选项（例如「换更便宜的 TTS 供应商：省 $0.18」——通过注册表查各供应商的 `estimate_cost`）
- 附上余量说明——应留一些预算给返工

### 第 7 步：组装批准门禁

批准区是用户拍板的地方。把它呈现为一个清晰的决策点：

```
────────────────────────────────────────
PROPOSAL READY FOR APPROVAL

Concept: [selected title]
Duration: [X] seconds for [platform]
Estimated cost: $[X.XX] of $[budget] budget
Production path: [premium/standard/budget/free]

Proceed? (approve / approve with changes / reject)
────────────────────────────────────────
```

在产物中设 `approval.status: "pending"`。由 EP 或用户更新为 `approved` 后流水线才继续。

**关键规则：** 没有明确批准，流水线绝不能越过本阶段。这是最后一个免费出口。之后一切都要花钱花时间。

### 第 8 步：提交

将 `proposal_packet` 产物按 `schemas/artifacts/proposal_packet.schema.json` 校验并提交。

## 如何衔接下游

| 下游阶段 | 从 proposal_packet 取什么 |
|----------|--------------------------|
| 脚本总监 | `selected_concept`（title、hook、key_points、core_message、tone、narrative_structure）+ research_brief 数据点 |
| 场景总监 | `selected_concept.visual_approach` + `production_plan.playbook` |
| 素材总监 | `production_plan.stages[assets].tools`——明确知道用哪些供应商 |
| 执行制片 | `cost_estimate`——初始化预算追踪 |
| 全部阶段 | `approval.approved_budget_usd`——硬性花费上限 |

proposal_packet 中的 `selected_concept` 实质取代了旧的 `brief` 产物——但它有调研支撑，且附带明确制作计划。

## 常见坑

- **概念无调研支撑**：每个概念的 `why_this_works` 必须引用具体调研发现。「这是个热门话题」不算支撑。「Cloudflare Radar 显示 13.5% 的 DNS 查询打到 1.1.1.1，与 Google DNS 主导的常见认知相反」才算。
- **藏成本**：透明。ElevenLabs 要 $0.30 就说 $0.30。不要抹零或漏项。诚实换来信任。
- **过度承诺工具可用性**：若预检只显示 Piper TTS 可用，就别设计依赖表演性声音的概念。围绕约束设计。
- **同一概念三个版本**：「Kubernetes 讲解」「理解 Kubernetes」「Kubernetes 指南」不是三个概念，是一个概念三个标题。结构多样性意味着不同叙事结构、不同钩子、不同受众。
- **跳过批准门禁**：这正是前期制作的意义。没有捷径。
- **不展示替代方案**：用户应始终看到至少两条不同价位的制作路径，让他们做知情选择。

## 示例：完整提案流程

### 输入：关于「DNS 如何运作」的 research_brief

**概念 1：「200 毫秒之旅」（data_driven）**
- 钩子：「你访问的每个网站，都始于一场横跨互联网的 200 毫秒寻宝。」
- 结构：journey —— 逐步跟随一次 DNS 查询
- 视觉：自定义信号地图身份——午夜背景、电光路径轨迹、数据包流动语言
- 时长：90 秒（YouTube）
- 支撑：递归解析耗时数据、受众对多步流程的认知落差
- 为什么成立：多数观众以为 DNS 是瞬时且单一的。展示真实旅程就是那个「原来如此」的时刻。

**概念 2：「你的 ISP 什么都知道」（contrarian）**
- 钩子：「你的网络提供商记录了你访问的每个网站。这套四十年前的系统让它成为可能。」
- 结构：myth_busting —— 挑战「隐私浏览 = 隐私」的信念
- 视觉：自定义监控黑色电影身份——低对比、隐私警示强调色、克制字体
- 时长：75 秒（YouTube）
- 支撑：DNS 隐私误解（受众调研）、DoH 趋势信号
- 为什么成立：隐私带情绪。HTTPS = 完全隐私的误解很普遍。

**概念 3：「互联网的电话簿」（analogy）**
- 钩子：「DNS 是一本 1983 年设计的电话簿，不知为何仍在支撑现代互联网。」
- 结构：analogy —— 以电话簿隐喻串起历史演进
- 视觉：自定义复古系统身份——米白纸底、档案字体、当下节拍用霓虹现代色对比
- 时长：60 秒（LinkedIn）
- 支撑：受众对 DNS 年龄的认知盲区、格局缺口（未发现历史角度）
- 为什么成立：对非技术受众最简单的入口。「四十年后仍能用」这个角度本身就意外。

**制作计划（选定概念 1，Remotion 可用）：**
```
script   → no tools, no cost
scene    → no tools, no cost — design 4 Remotion component scenes + 4 AI image scenes
assets   → tts_selector ($0.22), image_selector × 4 ($0.16), music_gen ($0.10)
edit     → no tools, no cost
compose  → video_compose/Remotion render (free) — animated text cards, stat cards,
           spring transitions, image scenes with animation. NOT Ken Burns.
publish  → no tools, no cost
TOTAL: $0.48 of $2.00 budget (saved $0.16 by using Remotion components instead of
       generating images for text/data scenes)
```

**制作计划（选定概念 1，仅 FFmpeg）：**
```
script   → no tools, no cost
scene    → no tools, no cost
assets   → tts_selector ($0.22), image_selector × 8 ($0.32), music_gen ($0.10)
edit     → no tools, no cost
compose  → video_compose/FFmpeg (free) — Ken Burns pan-and-zoom on images
publish  → no tools, no cost
TOTAL: $0.64 of $2.00 budget
```

**替代路径：**
- Premium（Remotion）：最好可用 TTS + 4 张 AI 图 + 4 个 Remotion 动画场景 = $0.48
- Standard：中档 TTS + 图片 = $0.40
- Free：本地 TTS + 仅 Remotion 组件场景 = $0.00（无图片，纯动效图）

## 遇到不会的情况

若遇到你不确定的生成技术、供应商行为或提示词模式：

1. **上网搜**当前最佳实践——模型和 API 变化频繁，训练数据可能过期
2. **查 `.agents/skills/`** 里已有的 Layer 3 知识（供应商专属提示词指南、API 模式）
3. **若都不奏效**，在 `projects/<项目名>/skills/<名称>.md` 写一份项目级技能，记录你的学习
4. **在技能中引用来源 URL**，让知识可追溯
5. **记入决策日志**：`category: "capability_extension"`，`subject: "learned technique: <名称>"`

以下情况尤其重要：
- **视频生成提示词** —— 模型对特定词汇的反应随版本变化
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同且持续演进
- **音频供应商怪癖** —— 声音克隆、音乐生成、TTS 各有模型专属最佳实践
- **Remotion 组件模式** —— 框架演进中不断出现新的合成技巧

不要依赖过期知识。有疑问，先搜。

---

## 门禁提醒（强制）

本阶段以人工批准为门禁（`human_approval_default: true`）。审阅通过后：
以 `status="awaiting_human"` 打 checkpoint，展示摘要（Backlot 看板会渲染产物），然后**结束本轮回复**。不要在同一个回复里启动下一阶段。
批准是按门禁逐次生效的——之前的「继续吧」不覆盖本门禁。
