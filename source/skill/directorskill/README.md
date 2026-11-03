# Cinematic Director Skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Claude Skill](https://img.shields.io/badge/Claude_Skill-cinematic--director-blue)
![Version](https://img.shields.io/badge/version-2.1.0-green)
[![markdownlint](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/markdownlint.yml/badge.svg)](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/markdownlint.yml)
[![links](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/links.yml/badge.svg)](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/links.yml)

A Claude Code / Claude Agent skill that turns a script, a paragraph of prose, or a single keyframe into a complete production plan — beats, director's book, blocking, shot list with coverage, keyframe prompts, image-to-video motion prompts, a sound plan, an edit timeline, a continuity bible, and a coded QC repair loop. Optionally apply one of twenty director-style lenses as a coherent overlay across the entire pass.

> [中文版本](#中文版本)

---

## Why this exists

Most "cinematic" AI prompts are adjective soup — *cinematic, dramatic, masterpiece, 8K*. They don't tell a model where the camera is, what the body is doing, where the action ends, or which anchors must not drift. The result is the slideshow look: pretty stills that wander between shots.

This skill replaces adjective soup with **directorial reasoning**:

- **A shot is a story decision**, not a style descriptor. If you can't say what the audience now understands that they didn't a second ago, the shot gets cut.
- **Blocking comes before framing.** Camera placement follows what bodies do in space. A well-blocked scene reads even shot flat.
- **The keyframe is the control point.** A video model mostly re-animates what the still already decided. Fixing the still is cheaper than retrying the video.
- **Continuity is engineered**, not hoped for. Identity strings, light direction, screen direction, and era locks are written once and repeated verbatim.
- **Failures get diagnosed, not re-rolled.** Nineteen coded failure modes, each with its mechanism, its ranked causes, and the cheapest fix that addresses it.
- **Style is a lens**, not a costume. Choosing Kubrick means wide-angle one-point perspective pressing people into architecture — not "add a zoom."

## What's new in 2.0

v1 knew the vocabulary of directing. v2 knows the craft behind it.

| | v1.2 | v2.0 |
|---|---|---|
| Pipeline | 10 steps | 13 steps — adds intake/scope, sound & dialogue, edit & assembly |
| Output modes | 6 | 10 — adds beat sheet, director's book, sound plan, edit plan |
| Reference files | 4 | 13 |
| Director lenses | 14 | 20 |
| Templates | 4 | 8, all with filled worked examples |
| Context strategy | load everything | routing table — depth moved behind it, so `SKILL.md` loads one file set per request instead of all of them |
| Tool handling | six named adapters | capability-first routing + four prompt shapes + twelve adapter families |
| Failure handling | a checklist | coded manual F1–F19, cost ladder, three-strike rule |

Also new: lens and focal-length psychology, lighting ratios, continuity geometry (axis of action, the 30° rule, screen direction, eyeline match) with the AI-specific problem that a video model has no idea where the last shot put the camera, a staging-geometry library, per-genre playbooks, a controlled prompt lexicon with an EN↔中文 term table, and the operational side — shot difficulty scoring, retry budgets, versioning, and handoff.

See [CHANGELOG.md](CHANGELOG.md) for the full list. The step renumbering (10→13) and mode renumbering (A–F→A–J) are breaking changes.

## Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│  SKILL.md — always loaded, routes everything                           │
│                                                                        │
│    routing table:  request type → output mode → files to load          │
│    hard rules · intake schema · defaults · self-check                  │
│                                                                        │
│    1  Intake & scope           8  Keyframe strategy                    │
│    2  Script & subtext         9  Tool adapter selection               │
│    3  Beat map                10  AI video prompt construction         │
│    4  Style lens (optional)   11  Sound & dialogue plan                │
│    5  Director's book         12  Edit & assembly plan                 │
│    6  Blocking & staging      13  QC & repair loop                     │
│    7  Shot list & coverage                                             │
└────────────────────────────────────────────────────────────────────────┘
                    │ loads on demand, never all at once
        ┌───────────┴────────────────────────────────┐
        ▼                                            ▼
┌───────────────────────────────┐      ┌─────────────────────────────┐
│ references/                   │      │ assets/  (fill-in templates)│
│   craft                       │      │   beat-sheet          Mode B│
│     cinematic-language        │      │   director-book       Mode C│
│     blocking-and-staging      │      │   shot-plan           Mode D│
│     lighting-and-color        │      │   keyframe-prompt     Mode E│
│     sound-and-dialogue        │      │   video-prompt        Mode F│
│     editing-and-assembly      │      │   sound-plan          Mode H│
│     genre-playbooks           │      │   edit-timeline       Mode I│
│     product-and-macro         │      │   qc-checklist        Mode J│
│   generation                  │      └─────────────────────────────┘
│     prompt-lexicon            │
│     ai-video-tool-adapters    │
│     image-model-adapters      │      ┌─────────────────────────────┐
│     failure-modes             │      │ evals/evals.json            │
│   production                  │      │   behavior contract         │
│     continuity-bible   Mode G │      └─────────────────────────────┘
│     production-workflow       │
│   director_styles/  20 lenses │
└───────────────────────────────┘
```

**One skill, optional style overlay.** `SKILL.md` is always the entry point. When the user names a director, Step 4 loads exactly one style file, and its `风格参数` YAML block overrides defaults at Steps 5, 7, 8, and 10. Style files are reference modules — they are *not* separately registered skills, so the host agent never has to disambiguate.

## Installation

Skill files live in `~/.claude/skills/<skill-name>/` (user-level) or `.claude/skills/<skill-name>/` (project-level). The folder name must match the `name:` field in `SKILL.md` (`cinematic-director`).

```bash
git clone https://github.com/wuwangzhang1216/DirectorSKILL.git ~/.claude/skills/cinematic-director
```

```bash
git clone https://github.com/wuwangzhang1216/DirectorSKILL.git .claude/skills/cinematic-director
```

Reload Claude Code (or your host agent) and the skill becomes available.

## Updating

An install is a git checkout, so update it in place:

```bash
cd ~/.claude/skills/cinematic-director && git pull
```

Check which version you are running — `metadata.version` in the installed `SKILL.md` frontmatter:

```bash
grep -A2 '^metadata:' ~/.claude/skills/cinematic-director/SKILL.md
```

2.0.0 renamed and extended the output-mode letters (A–F became A–J) and the pipeline steps (10 became 13). An older checkout answers with the old letters, so a mode this README documents — H, I, J — looks as though the skill simply does not have it. That symptom means you are on 1.x. Pull, then reload the host agent.

## Quick start

### Plain directorial pass

```text
You: Turn this into a 4-shot AI video plan for Runway, 16:9.
     "A courier hesitates outside a Republican-era Shanghai apartment door
      before knocking, then slips an envelope under it and walks away."
```

Produces: beat map → director's book with invariant clauses → shot list (story function, size, lens, angle, camera, blocking start→motion→end, light direction, continuity anchors, risk) → Runway-shaped motion prompts → QC notes.

### With a director-style overlay

```text
You: Same scene, but direct it in the style of Wong Kar-wai.
```

Step 4 loads `references/director_styles/09_wong_kar_wai.md` and its parameter block overrides the defaults: handheld in narrow corridors, neon practicals, frame-within-frame through doorways, a step-printed beat on the slip-and-leave, voice-over from the courier, a shorter average shot length. Same four shots, a different film.

### Repairing a failed clip

```text
You: My generation looks like a slideshow — character barely moves, rain is
     frozen. Diagnose and rewrite this prompt: [paste prompt]
```

Runs the triage tree, names the failure code and its mechanism, then applies the cheapest fix on the cost ladder that actually addresses it — and tells you when the answer is to re-plan the shot rather than rewrite the prompt again.

### Cutting what you already generated

```text
You: I have 8 clips. Two don't match. Give me an edit plan.
```

Mode I: a timeline with in/out points, trim handles, transitions built from paired last/first frames, a continuous audio bed under the whole sequence, and the specific fix-in-edit patch for the two that don't match.

## Director style overlays

| # | Director | Lens in one line |
|---|---|---|
| 01 | Steven Spielberg 斯皮尔伯格 | Emotional mainstream narrative, family stakes, awe via reaction-before-reveal |
| 02 | Alfred Hitchcock 希区柯克 | Suspense via shared knowledge, voyeurism, mistaken identity |
| 03 | Stanley Kubrick 库布里克 | Wide-angle one-point perspective, central symmetry, cold formalism |
| 04 | Akira Kurosawa 黑泽明 | Epic ensemble, humanism, weather as drama, dynamic action space |
| 05 | Martin Scorsese 斯科塞斯 | Urban energy, guilt, voice-over, kinetic camera, moral fall |
| 06 | Federico Fellini 费里尼 | Dream logic, circus parade, autobiographical fantasy |
| 07 | Ingmar Bergman 伯格曼 | Interior psychological drama, face close-ups, existential silence |
| 08 | Andrei Tarkovsky 塔可夫斯基 | Poetic time, long takes, water and fire, spiritual search |
| 09 | Wong Kar-wai 王家卫 | Urban loneliness, missed connections, neon, fragmented memory |
| 10 | Christopher Nolan 诺兰 | High-concept structure, time puzzles, large-format practical spectacle |
| 11 | Denis Villeneuve 维伦纽瓦 | Monumental scale, mist, geometric symmetry, low-rumble silence |
| 12 | David Fincher 芬奇 | Surgical control, teal-amber palette, procedural investigation, restrained dread |
| 13 | Nicolas Winding Refn 雷弗恩 | Neon color blocks, symmetric ritual framing, slow gaze, sudden violence |
| 14 | Bi Gan 毕赣 | Misty SW-China small towns, ultra-long take, dream-memory loops, poetic voice-over |
| 15 | Zhang Yimou 张艺谋 | Saturated single-color fields, mass choreography as image, folk-ritual iconography |
| 16 | Hou Hsiao-hsien 侯孝贤 | Static distant long take, doorway depth, real-time duration, ellipsis |
| 17 | Park Chan-wook 朴赞郁 | Baroque revenge, improbable camera geometry, ironic beauty over cruelty |
| 18 | Terrence Malick 泰伦斯·马力克 | Available light, wandering wide handheld at magic hour, whispered voice-over |
| 19 | Michael Mann 迈克尔·曼 | Urban night as a cold luminous field, professional competence, loneliness as architecture |
| 20 | Coen Brothers 科恩兄弟 | Deadpan geometric dark comedy, wide low-mounted moves, fate as a flat joke |

Each module carries a bilingual one-line lens, a `反例 / What this lens is NOT` section naming the adjacent styles it gets confused with and the *mechanical* difference, a machine-readable `风格参数` YAML block (lens kit in mm, allowed and forbidden camera moves, motion budget, key ratio, palette, average shot length, sound policy, negative-prompt additions), three prompt templates, and a worked example. Every module directs the **same** control scene, so the twenty read as twenty answers to one question. Index and structure: [references/director_styles/README.md](references/director_styles/README.md).

**See it in action.** [`references/director_styles/example_comparisons.md`](references/director_styles/example_comparisons.md) renders one scene under several lenses back to back — the fastest way to feel what an overlay actually changes.

## Tool adapters

The pipeline writes directorial intent; Step 9 reshapes it for the target model. v2 leads with **capability-first routing** so the file survives vendor churn: identify which control surfaces a tool exposes, then pick one of four prompt shapes — **S1** motion-only, **S2** full-description, **S3** keyframe-pair, **S4** multi-shot timestamped.

Video model families covered in [`references/ai-video-tool-adapters.md`](references/ai-video-tool-adapters.md): Runway, Veo, Kling 可灵, Luma, Sora-class, Hailuo/MiniMax, Pika, Vidu, Midjourney Video, 即梦/Dreamina/Seedance, 万相 Wanxiang, and open-source/ComfyUI-class models.

Image model families covered in [`references/image-model-adapters.md`](references/image-model-adapters.md): Midjourney, Flux, Nano Banana/Gemini-image class, Seedream/即梦 image, Qwen-Image, SDXL + ControlNet, Ideogram, Recraft — plus the character and location consistency playbooks that make keyframes hold across a scene.

Both files describe **capability classes**, not live feature lists. Vendors change limits constantly; verify against current docs.

## Output modes

| Mode | Name | Use when |
|---|---|---|
| A | Director Analysis | Interpretation, subtext, direction rules |
| B | Beat Sheet | Structure before shots |
| C | Director's Book | The rules that govern the whole piece |
| D | Shot Plan | Shot list, storyboard plan, shooting table |
| E | Keyframe Prompt Pack | Stills, first/last frames, panels, character sheets |
| F | Video Motion Prompt Pack | Assets exist, motion prompts needed |
| G | Continuity Bible | Recurring characters, locations, multi-scene work |
| H | Sound & Dialogue Plan | Sound design, music, dialogue, voice-over |
| I | Edit & Assembly Plan | Cutting generated clips into a sequence |
| J | QC & Repair | Something failed or looks wrong |

Modes combine. A full production pass is A→B→C→D→E→F→H→I with G underneath and J at the end.

## Repository structure

```text
cinematic-director/
├── SKILL.md                              # Main pipeline: 13 steps, modes A-J, routing table
├── README.md                             # This file
├── CONTRIBUTING.md                       # How to add directors / adapters / genres / failure codes
├── CHANGELOG.md                          # Release history
├── LICENSE                               # MIT
├── references/
│   ├── cinematic-language.md             # Shot grammar, lenses, focus, continuity geometry, coverage, format
│   ├── blocking-and-staging.md           # Staging geometry, proxemics, notation, AI motion reliability
│   ├── lighting-and-color.md             # Setups, ratios, practicals, time of day, palettes, grading
│   ├── sound-and-dialogue.md             # Sound layers, dialogue for AI video, music brief, VO
│   ├── editing-and-assembly.md           # Pacing math, cut motivation, transition engineering, timeline
│   ├── genre-playbooks.md                # Per-genre directorial defaults
│   ├── product-and-macro.md              # Product, packshot, cosmetics, food, macro
│   ├── prompt-lexicon.md                 # Verb banks, replacement table, negatives, EN/中文 terms
│   ├── failure-modes.md                  # Coded manual F1-F19, cost ladder, three-strike rule
│   ├── ai-video-tool-adapters.md         # Video model surfaces, prompt shapes S1-S4
│   ├── image-model-adapters.md           # Image model surfaces, character/location consistency
│   ├── continuity-bible.md               # Character/location/prop/shot schemas + worked example
│   ├── production-workflow.md            # Operating loop, difficulty rubric, versioning, handoff
│   └── director_styles/                  # 20 style overlays + index + comparisons
├── assets/
│   ├── beat-sheet-template.md            # Mode B
│   ├── director-book-template.md         # Mode C
│   ├── shot-plan-template.md             # Mode D
│   ├── keyframe-prompt-template.md       # Mode E
│   ├── video-prompt-template.md          # Mode F
│   ├── sound-plan-template.md            # Mode H
│   ├── edit-timeline-template.md         # Mode I
│   └── qc-checklist.md                   # Mode J
└── evals/
    ├── evals.json                        # Behavior contract
    └── run.md                            # How to run the suite and score a result
```

## Extending

- **Add a director**: `references/director_styles/NN_<slug>.md` using the v2 section structure, with a filled `风格参数` block and the shared control scene; then register in four places.
- **Add a video or image tool**: append an adapter block plus a matrix column. No `SKILL.md` change needed unless the tool shifts a global default.
- **Add a genre**: append a block to `references/genre-playbooks.md` using the same fixed field set, plus a row in the comparison table.
- **Add a failure code**: F-codes are append-only; add F20+ with symptom, ranked causes, cost-ordered fixes, and a before/after pair.
- **Add an output mode**: only if genuinely distinct from A–J.
- **Add an eval**: append a case to `evals/evals.json`.

Full contributor guide: [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage rule and disclaimer

The director-style modules describe **high-level methods** — narrative tendencies, camera grammar, lighting logic, editing rhythm, sound, performance, transferable checklists. They are **not** licensed to copy specific shots, dialogue, characters, plots, or any other copyrighted expression from any director's actual films. Use them as lenses that inform original work.

Tool adapters describe **capability classes** observed at the time of writing. AI video and image platforms change limits, parameters, and features constantly — always verify against the vendor's current documentation before relying on a specific behavior.

## License

MIT — see [LICENSE](LICENSE). That file is unmodified MIT text with no appended terms, so the `license: MIT` declaration in `SKILL.md` resolves to exactly what the file grants.

The MIT grant covers the skill files. The usage rule above is not a licence condition; it states what the style modules do and do not license. Copyright in any real film stays with its rights holders, and nothing here conveys an interest in it. That rule governs *how* you apply the directorial knowledge with respect to existing films, which is a separate concern from software licensing.

---

<a id="中文版本"></a>

# Cinematic Director Skill（中文版本）

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Skill](https://img.shields.io/badge/Claude_Skill-cinematic--director-blue)
![版本](https://img.shields.io/badge/version-2.1.0-green)
[![lint](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/markdownlint.yml/badge.svg)](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/markdownlint.yml)
[![link check](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/links.yml/badge.svg)](https://github.com/wuwangzhang1216/DirectorSKILL/actions/workflows/links.yml)

一个 Claude Code / Claude Agent skill：把剧本、一段散文或一张关键帧，转化为完整的制作方案——节拍表、导演书、走位、含覆盖策略的分镜表、关键帧提示词、图生视频动作提示词、声音方案、剪辑时间线、连贯性圣经，以及带编码的 QC 修复流程。可叠加 20 位导演风格中的任意一位，作为贯穿全流程的统一镜头。

## 为什么需要它

大多数"电影感"AI 提示词只是形容词堆砌——*cinematic、dramatic、masterpiece、8K*。它们不告诉模型镜头在哪、身体在做什么、动作终点在哪、哪些锚点不能漂移。结果就是 PPT 感：每张静帧都好看，镜头之间却在游走。

本 skill 把形容词堆砌替换为**导演式推理**：

- **镜头是叙事决策**。说不出"观众此刻比一秒前多懂了什么"，这个镜头就删掉。
- **走位先于构图**。摄影机位置取决于身体在空间中的动作；走位对了，平拍也能读懂。
- **关键帧才是控制点**。视频模型基本上是在重新驱动静帧已经决定的一切。修静帧比重跑视频便宜得多。
- **连贯性是设计出来的**。身份串、光位、画面方向、年代锁定写一次，然后逐字复用。
- **失败要诊断，不要重摇**。19 个编码失败模式，每个都有机制、按概率排序的成因和成本最低的有效修复。
- **风格是镜头，不是外套**。选库布里克意味着用广角单点透视把人压进建筑——不是"多加个推镜"。

## 2.0 有什么新东西

v1 掌握的是导演的词汇，v2 掌握的是词汇背后的手艺。

| | v1.2 | v2.0 |
|---|---|---|
| 流水线 | 10 步 | 13 步——新增需求梳理、声音与对白、剪辑与合成 |
| 输出模式 | 6 种 | 10 种——新增节拍表、导演书、声音方案、剪辑方案 |
| 参考文件 | 4 个 | 13 个 |
| 导演风格 | 14 位 | 20 位 |
| 模板 | 4 个 | 8 个，全部带已填好的实例 |
| 上下文策略 | 全量加载 | 路由表——深度内容移到路由表之后，`SKILL.md` 每次只加载一个请求需要的文件集，而不是全部 |
| 工具处理 | 6 个具名适配器 | 能力优先路由 + 4 种提示词形态 + 12 个适配器家族 |
| 失败处理 | 一张清单 | 编码手册 F1–F19、成本阶梯、三振规则 |

另外新增：焦距心理学、光比、连贯性几何（动作轴线、30 度规则、画面方向、视线匹配）以及"视频模型根本不知道上一镜机位在哪"这个 AI 专属难题的解法、调度几何库、类型片手册、受控提示词词库（含中英术语对照表），以及运营侧内容——镜头难度评分、重试预算、版本管理和交付包。

完整列表见 [CHANGELOG.md](CHANGELOG.md)。步骤重编号（10→13）与模式重编号（A–F→A–J）是破坏性变更。

## 架构

```text
┌────────────────────────────────────────────────────────────────────────┐
│  SKILL.md — 始终在上下文里，负责路由分发                                 │
│                                                                        │
│    路由表：需求类型 → 输出模式 → 该加载哪些文件                          │
│    硬规则 · 输入 schema · 默认值 · 自检清单                              │
│                                                                        │
│    1  需求梳理与范围        8  关键帧策略                                │
│    2  剧本与潜文本          9  工具适配器选择                            │
│    3  节拍图               10  AI 视频提示词构造                         │
│    4  导演风格镜头（可选）  11  声音与对白方案                            │
│    5  导演书               12  剪辑与合成方案                            │
│    6  走位与调度           13  QC 与修复                                 │
│    7  分镜表与覆盖策略                                                   │
└────────────────────────────────────────────────────────────────────────┘
                    │ 按需加载，绝不一次全读
        ┌───────────┴────────────────────────────────┐
        ▼                                            ▼
┌───────────────────────────────┐      ┌─────────────────────────────┐
│ references/                   │      │ assets/   可填写模板         │
│   手艺                        │      │   节拍表            Mode B  │
│     cinematic-language        │      │   导演书            Mode C  │
│     blocking-and-staging      │      │   分镜表            Mode D  │
│     lighting-and-color        │      │   关键帧提示词      Mode E  │
│     sound-and-dialogue        │      │   视频提示词        Mode F  │
│     editing-and-assembly      │      │   声音方案          Mode H  │
│     genre-playbooks           │      │   剪辑时间线        Mode I  │
│     product-and-macro         │      │   QC 清单           Mode J  │
│   生成                        │      └─────────────────────────────┘
│     prompt-lexicon            │
│     ai-video-tool-adapters    │
│     image-model-adapters      │      ┌─────────────────────────────┐
│     failure-modes             │      │ evals/evals.json            │
│   制作                        │      │   行为契约                   │
│     continuity-bible   Mode G │      └─────────────────────────────┘
│     production-workflow       │
│   director_styles/  20 位导演 │
└───────────────────────────────┘
```

**一个 skill，可选风格叠加。** `SKILL.md` 始终是入口。用户点名导演时，Step 4 只加载一个风格文件，其 `风格参数` YAML 块覆盖 Step 5 / 7 / 8 / 10 的默认值。风格文件是参考模块——它们*不会*被宿主 agent 单独注册为 skill，不会产生歧义。

## 安装

skill 文件放在 `~/.claude/skills/<skill-name>/`（用户级）或 `.claude/skills/<skill-name>/`（项目级）。文件夹名必须与 `SKILL.md` 的 `name:` 一致（`cinematic-director`）。

```bash
git clone https://github.com/wuwangzhang1216/DirectorSKILL.git ~/.claude/skills/cinematic-director
```

```bash
git clone https://github.com/wuwangzhang1216/DirectorSKILL.git .claude/skills/cinematic-director
```

重新加载 Claude Code（或你的宿主 agent）即可触发。

## 更新

安装本身就是一个 git 检出，原地更新即可：

```bash
cd ~/.claude/skills/cinematic-director && git pull
```

查看当前跑的是哪个版本——已安装 `SKILL.md` frontmatter 里的 `metadata.version`：

```bash
grep -A2 '^metadata:' ~/.claude/skills/cinematic-director/SKILL.md
```

2.0.0 重命名并扩展了输出模式字母（A–F 变成 A–J）和流水线步骤（10 步变成 13 步）。旧检出只会用旧字母作答，于是本 README 写着的模式——H、I、J——看起来就像这个 skill 根本没有。出现这个症状就说明你还在 1.x：pull 一次，再重新加载宿主 agent。

## 快速开始

### 纯导演式流程

```text
你：把这段做成 Runway 的 4 镜头 AI 视频方案，16:9。
    "民国上海，一个信差在一户公寓门口犹豫，敲了一下门，又把信封从门缝塞进去，转身离开。"
```

输出：节拍图 → 含不变量条款的导演书 → 分镜表（叙事功能、景别、焦距、角度、镜头运动、起-动-止走位、光位、连贯性锚点、风险）→ Runway 形态的动作提示词 → QC 注记。

### 叠加导演风格

```text
你：同一场戏，用王家卫的风格来拍。
```

Step 4 加载 `references/director_styles/09_wong_kar_wai.md`，用它的参数块覆盖默认值：狭窄走廊的手持、霓虹实用光源、门框构成的画中画、塞信离开这一拍的抽格慢动作、信差的独白、更短的平均镜头长度。同样 4 个镜头，另一部电影。

### 修复失败的生成

```text
你：我生成的片子像 PPT——人物几乎不动，雨是静止的。诊断并重写这条提示词：[粘贴提示词]
```

先跑分诊树，指出失败编码和具体机制，再沿成本阶梯用最便宜且真正对症的修复——并且会在正确答案是"重排这个镜头"而不是"再改一次提示词"时直接说出来。

### 把已经生成的素材剪起来

```text
你：我有 8 段素材，其中两段接不上。给我一个剪辑方案。
```

Mode I：带出入点、留头留尾、由配对首尾帧构造的转场、贯穿整段的连续声床的时间线，以及那两段接不上的素材的具体补救方案。

## 导演风格清单

| # | 导演 | 一句话风格 |
|---|---|---|
| 01 | Steven Spielberg 斯皮尔伯格 | 情感驱动的经典商业叙事，家庭羁绊，先反应再揭示的奇观 |
| 02 | Alfred Hitchcock 希区柯克 | 信息差悬念、窥视、误认、控制式揭露 |
| 03 | Stanley Kubrick 库布里克 | 广角单点透视、中央对称、冷峻形式 |
| 04 | Akira Kurosawa 黑泽明 | 史诗群像、人道主义、把天气当戏剧、动态动作空间 |
| 05 | Martin Scorsese 斯科塞斯 | 都市能量、罪感、旁白、动感摄影、道德坠落 |
| 06 | Federico Fellini 费里尼 | 梦境逻辑、马戏巡游、自传性幻想 |
| 07 | Ingmar Bergman 伯格曼 | 室内心理剧、脸部特写、存在主义沉默 |
| 08 | Andrei Tarkovsky 塔可夫斯基 | 诗意时间、长镜头、水与火、精神探索 |
| 09 | Wong Kar-wai 王家卫 | 都市孤独、错过、霓虹、碎片记忆、旁白 |
| 10 | Christopher Nolan 诺兰 | 高概念结构、时间谜题、大画幅实拍奇观 |
| 11 | Denis Villeneuve 维伦纽瓦 | 宏大尺度、雾霭、几何对称、低频轰鸣的寂静 |
| 12 | David Fincher 芬奇 | 外科手术级控制、青绿琥珀调色、程序化调查、克制式恐惧 |
| 13 | Nicolas Winding Refn 雷弗恩 | 霓虹色块、对称仪式构图、缓慢凝视、突发暴力 |
| 14 | Bi Gan 毕赣 | 西南雾镇、超长长镜头、梦境记忆循环、诗歌旁白 |
| 15 | Zhang Yimou 张艺谋 | 高饱和单色场、群体调度成为图像、民俗仪式符号 |
| 16 | Hou Hsiao-hsien 侯孝贤 | 固定机位远观长镜头、门框纵深、真实时长、省略胜于交代 |
| 17 | Park Chan-wook 朴赞郁 | 巴洛克式复仇、不可能的机位几何、以美写残酷 |
| 18 | Terrence Malick 泰伦斯·马力克 | 自然光、魔幻时刻的广角游移手持、耳语旁白、联想式蒙太奇 |
| 19 | Michael Mann 迈克尔·曼 | 都市夜景作为冷光场、专业者的能力与孤独、以建筑写寂寞 |
| 20 | Coen Brothers 科恩兄弟 | 冷面几何黑色喜剧、广角低机位运动、命运作为一个平淡的笑话 |

每个模块都带一句话双语镜头、`反例：这不是什么`（点名容易混淆的相邻风格并说明**机制上**的差别）、可被程序读取的 `风格参数` YAML 块（镜头包毫米数、允许与禁止的机位运动、运动预算、光比、色板、平均镜头长度、声音策略、负面词补充）、三段提示词模板和一个落地示例。所有模块都执导**同一个**对照场景，于是这 20 个文件读起来就是同一个问题的 20 种答案。索引与结构见 [references/director_styles/README.md](references/director_styles/README.md)。

**看实际效果**：[`references/director_styles/example_comparisons.md`](references/director_styles/example_comparisons.md) 把同一场戏用多个镜头连续处理一遍，是感受 overlay 到底改变了什么最快的方式。

## 工具适配器

流水线产出的是导演意图，Step 9 把它整形成目标模型的输入。v2 以**能力优先路由**开头，这样文件不会被厂商迭代冲垮：先确认工具暴露了哪些控制面，再从四种提示词形态里选一种——**S1** 纯运动、**S2** 全描述、**S3** 首尾帧、**S4** 多镜头时间戳。

[`references/ai-video-tool-adapters.md`](references/ai-video-tool-adapters.md) 覆盖的视频模型家族：Runway、Veo、可灵 Kling、Luma、Sora 类、海螺 MiniMax、Pika、Vidu、Midjourney Video、即梦/Dreamina/Seedance、万相 Wanxiang，以及开源/ComfyUI 类模型。

[`references/image-model-adapters.md`](references/image-model-adapters.md) 覆盖的图像模型家族：Midjourney、Flux、Nano Banana / Gemini 图像类、Seedream / 即梦图像、Qwen-Image、SDXL + ControlNet、Ideogram、Recraft——以及让关键帧在一整场戏里保持住的人物与场景一致性方法论。

两个文件描述的都是**能力类别**，不是实时功能清单。厂商改参数极频繁，落地前请以官方最新文档为准。

## 输出模式

| 模式 | 名称 | 何时使用 |
|---|---|---|
| A | 导演分析 | 解读、潜文本、导演规则 |
| B | 节拍表 | 先立结构，再拆镜头 |
| C | 导演书 | 统辖全片的规则集 |
| D | 分镜方案 | 分镜表、故事板计划、拍摄表 |
| E | 关键帧提示词包 | 静帧、首尾帧、故事板格、人物设定图 |
| F | 视频动作提示词包 | 素材已有，需要动作提示词 |
| G | 连贯性圣经 | 反复出现的人物、场景、跨场戏 |
| H | 声音与对白方案 | 声音设计、音乐、对白、旁白 |
| I | 剪辑与合成方案 | 把生成的素材剪成序列 |
| J | QC 与修复 | 出了问题或看着不对 |

模式可组合。完整制作流程通常是 A→B→C→D→E→F→H→I，G 在底下贯穿，J 收尾。

## 扩展方式

- **加导演**：新建 `references/director_styles/NN_<slug>.md`，沿用 v2 结构，填满 `风格参数`，使用统一对照场景，然后在 4 处登记。
- **加视频/图像工具**：追加一段适配器加一列能力矩阵。除非该工具改变了全局默认值，否则不用动 `SKILL.md`。
- **加类型片**：在 `references/genre-playbooks.md` 追加一块，字段集与现有类型一致，并在对比表加一行。
- **加失败代码**：F 编码只增不改，从 F20 起，四个区块齐全。
- **加输出模式**：只有真正区别于 A–J 时才加。
- **加 eval**：在 `evals/evals.json` 追加用例。

完整贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 使用规则与免责声明

导演风格模块描述的是**高层方法**——叙事倾向、镜头语法、灯光逻辑、剪辑节奏、声音、表演、可迁移清单。它们**不授权**复制任何导演真实电影中的具体镜头、台词、角色、剧情或其他受版权保护的表达。请把它们当作镜头来启发原创作品。

工具适配器描述的是写作当时观察到的**能力类别**。AI 视频与图像平台的限制、参数、功能变动频繁，落地前请以厂商最新文档为准。

## 许可证

MIT，见 [LICENSE](LICENSE)。该文件是未经修改的 MIT 原文，没有附加条款，因此 `SKILL.md` 里 `license: MIT` 的声明与文件实际授予的权利完全一致。

MIT 授权覆盖 skill 文件本身。上方"使用规则"不是附加的许可条款，它陈述的是风格模块授权什么、不授权什么：任何真实电影的版权仍归其权利人所有，本仓库不转让其中任何权益。该规则约束的是*如何*把这些导演知识应用到已有电影上，是与软件许可分开的另一个问题。
