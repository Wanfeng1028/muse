# Contributing to Cinematic Director Skill

Thanks for considering a contribution. This skill grows horizontally — more director lenses, more tool adapters, more genre playbooks, more failure codes — without changing the shape of the main pipeline. This guide shows how to add each kind of contribution and what to check before opening a PR.

> [中文版本](#中文)

---

## What this skill is (and is not)

This is a **prompt skill**, not application code. The deliverables are markdown files a Claude-family agent loads at runtime. There is no build step and no traditional test runner — `evals/evals.json` is the behavior contract.

Design goals:

- Keep `SKILL.md` a single coherent pipeline and keep it **lean**. It is always in context, so depth lives in `references/` and gets loaded on demand. New capability slots in as a step, mode, style, adapter, or reference — never as a parallel skill.
- Keep every claim **actionable and specific**. Numbers where numbers exist: focal lengths in mm, lighting ratios, seconds, degrees, shot counts, average shot lengths.
- Keep style modules **descriptive of methods**, not derivative of specific films. The copyright rule is non-negotiable.
- Keep additions cheap: a new director is one file plus a few registrations; a new tool adapter is one block in one file.

## Project layout

```text
SKILL.md                                  # Main pipeline: 13 steps, modes A-J, routing table
references/
  cinematic-language.md                   # Shot functions, sizes, angles, moves, lenses, focus,
                                          #   continuity geometry, coverage, composition, aspect/format
  blocking-and-staging.md                 # Staging geometry, proxemics, notation, AI motion reliability
  lighting-and-color.md                   # Setups, ratios, motivation, time of day, palettes, grading
  sound-and-dialogue.md                   # Sound layers, dialogue for AI video, music brief, VO
  editing-and-assembly.md                 # Pacing math, cut motivation, transition engineering, timeline
  genre-playbooks.md                      # Per-genre directorial defaults
  product-and-macro.md                    # Product, packshot, cosmetics, food, macro
  prompt-lexicon.md                       # Verb banks, replacement table, negatives, EN/中文 terms
  failure-modes.md                        # Coded diagnosis manual F1-F19, cost ladder, three-strike rule
  ai-video-tool-adapters.md               # Video model control surfaces and prompt shapes S1-S4
  image-model-adapters.md                 # Image model surfaces, character/location consistency
  continuity-bible.md                     # Character/location/prop/shot state schemas + worked example
  production-workflow.md                  # Operating loop, difficulty rubric, versioning, handoff
  director_styles/
    README.md                             # Style index + module structure + how-to-add
    NN_<slug>.md                          # One file per director (01-20)
    example_comparisons.md                # One scene under several lenses, side by side
assets/
  beat-sheet-template.md                  # Mode B
  director-book-template.md               # Mode C
  shot-plan-template.md                   # Mode D
  keyframe-prompt-template.md             # Mode E
  video-prompt-template.md                # Mode F
  sound-plan-template.md                  # Mode H
  edit-timeline-template.md               # Mode I
  qc-checklist.md                         # Mode J
evals/
  evals.json                              # Behavior contract
  run.md                                  # How to run the suite and score a result
```

## The pipeline and mode contracts

Two numbering schemes are referenced across many files. Changing either is a breaking change that requires a sweep.

Pipeline steps: 1 Intake and scope · 2 Script and subtext · 3 Beat map · 4 Style lens · 5 Director's book · 6 Blocking and staging · 7 Shot list and coverage · 8 Keyframe strategy · 9 Tool adapter selection · 10 AI video prompt construction · 11 Sound and dialogue · 12 Edit and assembly · 13 QC and repair.

Output modes: A Director Analysis · B Beat Sheet · C Director's Book · D Shot Plan · E Keyframe Prompt Pack · F Video Motion Prompt Pack · G Continuity Bible · H Sound & Dialogue Plan · I Edit & Assembly Plan · J QC & Repair.

Failure codes F1–F19 are defined in `references/failure-modes.md`, which is their sole owner — no other file carries a parallel copy of the taxonomy. Prompt shapes S1–S4 are defined in `references/ai-video-tool-adapters.md`.

Reserved prefixes, so an id in a note is never ambiguous: `S` = prompt shapes only. `F` = failure codes only. `P`/`G`/`Q` = the three QC gates in `assets/qc-checklist.md`. `SH` = shot ids in worked examples. `L` = rungs on the cost ladder. Do not reuse a letter for a second numbering scheme.

### Single-owner concepts

Where two files could reasonably cover the same thing, one owns it and the rest link. Duplicated content drifts; several v2 fixes were exactly this. The owners:

| Concept | Owner |
|---|---|
| Identity string spec (word budget, rules, examples) | `references/continuity-bible.md` |
| Lighting ratios, and the lit-side-to-shadow-side convention | `references/lighting-and-color.md` |
| The 30° rule and all continuity geometry | `references/cinematic-language.md` |
| The shot-size ladder (six rungs) | `references/cinematic-language.md` |
| Clip duration strategy | `references/ai-video-tool-adapters.md` |
| Generation handles and trim | `references/editing-and-assembly.md` |
| Retry and attempt economics | `references/production-workflow.md` |
| Sound layer levels and definitions | `references/sound-and-dialogue.md` |
| The F-code taxonomy | `references/failure-modes.md` |
| The motion budget | `references/ai-video-tool-adapters.md` |
| Prompt wording — verb banks, replacement table, negatives | `references/prompt-lexicon.md` |

Negative prompts name **instances**, never categories, everywhere in the skill. "No modern objects" is unresolvable by a generator and is the documented mechanism behind F8 — name the things instead.

## How to add a new director-style overlay

A director style is a coherent lens applied at Step 4, overriding defaults at Steps 5, 7, and 10.

1. **Create the file** at `references/director_styles/NN_<slug>.md` with the next available `NN`. Match the v2 section order exactly:

   ```markdown
   ---
   name: <slug>
   title: <中文名>导演风格 Skill
   description: <one line; includes the do-not-copy warning>
   ---

   # <中文名>导演风格 Skill

   ## 一句话镜头 / Lens in one line
   ## 适用场景
   ## 反例：这不是什么 / What this lens is NOT
   ## 核心风格关键词
   ## 叙事方法
   ## 镜头语言
   ## 灯光与色彩
   ## 剪辑节奏
   ## 声音与音乐
   ## 人物与表演
   ## 风格参数 / Style parameters
   ## 可迁移拍摄清单
   ## 提示词模板 / Prompt templates
   ## 落地示例 / Worked example
   ```

2. **Fill the two sections that do the real work.**
   - `反例 / What this lens is NOT` names the two or three adjacent styles this director gets confused with and states the *mechanical* difference, not an evaluative one. Reference other modules by number. If your 反例 section could be pasted into a different director's file unchanged, it is not finished.
   - `风格参数 / Style parameters` is a YAML block the main skill reads directly. Fill every field. See any existing module for the schema — lens kit in mm, camera prefer/avoid/motion budget/height, shot size bias, composition, lighting, palette, editing, sound, performance, aspect bias, AI video guidance, negative prompt additions. If two modules end up with near-identical parameters, one of them is not a distinct lens.

3. **Use the shared control scene** in `落地示例`: a person stands at a closed apartment door holding something they intend to give away, hesitates, and leaves without knocking. Every module directs the same scene so the library can be read as a set of answers to one question. Do not substitute your own scene.

4. **Register the style** in four places:
   - `references/director_styles/README.md` — add a table row.
   - `SKILL.md` frontmatter `description:` — append the director to the parenthetical list.
   - `SKILL.md` intake schema `director_style:` enum and Step 4 "Available:" line.
   - Top-level `README.md` — add a row to both the EN and 中文 tables and to the repo-structure tree.

5. **Add an eval case** in `evals/evals.json` proving the overlay changes camera, palette, pacing, or sound versus the unstyled baseline, plus a copyright-safety assertion.

6. **Run CI locally if you can**: `npx markdownlint-cli2 "**/*.md"` and `lychee --offline "**/*.md"`.

### Copyright safety

Style modules describe **high-level methods only**. Do not include specific shot descriptions, character names, lines of dialogue, or plot beats from real films, or imagery so particular to one film that it reads as a paraphrase. Test: if a sentence would not apply equally to several works in that director's body of work, it is too specific. The statement this rule enforces — what the modules do and do not license — is [README.md § Usage rule and disclaimer](README.md#usage-rule-and-disclaimer); it is not a term of `LICENSE`, which is unmodified MIT.

## How to add a new AI video tool adapter

Adapters live in `references/ai-video-tool-adapters.md`. Before writing one, check whether the tool is already covered by the capability-first routing — the file is organized around control surfaces and four prompt shapes (S1 motion-only, S2 full-description, S3 keyframe-pair, S4 multi-shot timestamped), so a tool with no unusual surface may need only a matrix column.

If it needs its own block, append:

```markdown
## <Tool>-style adapter

Best for: <2-3 capabilities the tool actually controls well>.
Control surfaces: <which of the matrix rows it exposes>.

Prompt priorities:
1. <what the model leans on most>

Template:
\`\`\`text
<minimal prompt skeleton>
\`\`\`

Tool-specific rules: <dialogue syntax, reference binding, language preference, duration behavior>.
Typical failure and fix: <the one thing that goes wrong most, and the change that fixes it>.
```

Also add a column to the control-surface matrix — and a row, if the tool exposes a control surface the matrix does not list yet. **Do not state version numbers, prices, or exact hard limits as fact** — vendors change them constantly. Write in capability classes and hedge ("where supported", "if the UI exposes", "verify against current docs").

If the tool changes the pipeline globally (for example, reliable long single-shot generation, which argues for fewer and longer shots), add a line to `SKILL.md` "Intake and defaults".

Image models follow the same pattern in `references/image-model-adapters.md`.

## How to add a new genre playbook

Append a block to `references/genre-playbooks.md` using the same fixed field set as the existing genres — dramatic engine, audience contract, camera default, lens bias, movement bias, lighting default, palette, average shot length, sound default, blocking bias, pacing signature, the classic mistake, the AI-specific risk and mitigation, and a seed prompt line. Keeping the fields fixed is what makes the blocks diffable. Add a row to the cross-genre comparison table.

## How to add a new failure code

Failure codes are referenced from `assets/qc-checklist.md` and `SKILL.md`, so they are append-only. Add `F20` and up to `references/failure-modes.md` with all four blocks: symptom in the user's own words, root causes ranked by likelihood with the mechanism, fixes ranked by position on the cost ladder, and a before/after prompt pair. Then add the row to the symptom-to-code index, the triage tree, and the prevention map — all three live in the same file, which is the point.

## How to add a new output mode

Only if it is genuinely distinct from A–J:

1. Add `### Mode K — <Name>` to the mode table and the routing table in `SKILL.md`.
2. Add a template in `assets/<name>-template.md` if it needs a scaffold.
3. Add at least one eval case that triggers it.

Do not add a mode that is a stylistic variant of an existing one — adjust the existing mode instead.

## How to add an eval case

`evals/evals.json` is a flat JSON file. Each case:

```json
{
  "id": "short-kebab-case",
  "mode": "D",
  "loads": ["references/cinematic-language.md"],
  "prompt": "What the user types",
  "expected_output": "Plain-English description of what a good response looks like",
  "assertions": [
    "Specific, checkable claim about the response"
  ]
}
```

Assertions should be **observable** in the output text (never about hidden reasoning), **specific** ("uses one dominant camera movement" beats "looks cinematic"), and **decoupled** from each other. Four to six per case. Style-overlay cases always include a copyright-safety assertion. How to run the suite and score a result is documented in `evals/run.md`.

## Style conventions

- **Compact prose-heavy markdown.** Bullets directly under a heading are fine; no blank line required around every heading, list, or fence. `.markdownlint.json` is calibrated for this.
- **Actionable or cut.** Every sentence must change a decision. "Use dramatic lighting" is a defect; "key at 45° camera-left, 4:1 ratio, motivated by a single desk lamp, named as the source in the prompt" is the standard.
- **Worked examples are mandatory** in any section that teaches a technique. A placeholder-only skeleton is incomplete.
- **Before/after pairs beat rules** wherever a prompt technique is being taught.
- **Language.** `SKILL.md`, top-level `README.md`, `LICENSE`, `CHANGELOG.md`, this file, and all non-style `references/` and `assets/` files are English, with inline 中文 glosses for craft terms where a Chinese-speaking user needs them and bilingual templates for Chinese-UI tools. Director style files are Chinese-primary with English YAML keys and a bilingual one-line lens. The top-level README carries a full EN + 中文 mirror.
- **No emoji.** **No marketing language.** "Cinematic, dramatic, masterpiece, 8K" is the failure mode this skill argues against — it appears in these docs only as an example of what to avoid.
- **No invented tool facts.** Capability classes and hedged claims only.

## Pull request checklist

- [ ] CI is green (markdownlint + links workflows)
- [ ] New director: registered in all four places + `风格参数` block filled + shared control scene used + new eval case
- [ ] New tool adapter: block added, matrix column added, no unhedged version/price/limit claims
- [ ] Pipeline or mode change: `SKILL.md` step numbers still 1..13 and modes still A..J across every file that references them, `README.md` architecture diagram updated, `CHANGELOG.md` Unreleased section updated
- [ ] Eval suite run per `evals/run.md`, with new or changed cases passing
- [ ] Every relative link resolves (CI runs lychee offline)
- [ ] No specific shots, dialogue, characters, or plots from real films
- [ ] Bilingual README tables stay in sync

## Reporting issues

Issues live at <https://github.com/wuwangzhang1216/DirectorSKILL/issues>. Useful issue types:

- "The skill produces X when I expect Y" — include the prompt and the problematic output
- "Style overlay for director X is too generic or too derivative" — say what is off
- "Tool adapter for X is outdated" — link the tool's current documentation
- "Failure code F<n> misdiagnoses my case" — include the prompt, the clip description, and what actually fixed it

---

<a id="中文"></a>

# 贡献指南（中文）

感谢你考虑贡献。本 skill 设计为横向扩展——更多导演风格镜头、更多工具适配器、更多类型片手册、更多失败代码——而不改变主流水线的形状。

## 这个 skill 是什么（不是什么）

这是一个 **prompt skill**，不是应用代码。交付物是 markdown 文件，由 Claude 系列 agent 在运行时加载。没有构建步骤，`evals/evals.json` 是行为契约。

设计目标：

- 保持 `SKILL.md` 是单一一致的流水线，并且**保持精简**。它始终占据上下文，所以深度内容放在 `references/` 里按需加载。
- 每条主张都必须**可执行、够具体**。能给数字的地方给数字：焦距毫米数、光比、秒数、角度、镜头数、平均镜头长度。
- 风格模块只描述**方法**，不衍生自具体影片。版权规则不可妥协。
- 保持添加成本低：新导演 = 一个文件加几处注册；新工具适配器 = 一个文件里加一段。

## 两套编号契约

流水线 13 步：1 需求梳理 · 2 剧本与潜文本 · 3 节拍图 · 4 导演风格镜头 · 5 导演书 · 6 走位与调度 · 7 分镜与覆盖 · 8 关键帧策略 · 9 工具适配器选择 · 10 AI 视频提示词构造 · 11 声音与对白 · 12 剪辑与合成 · 13 QC 与修复。

输出模式 A–J：A 导演分析 · B 节拍表 · C 导演书 · D 分镜方案 · E 关键帧提示词包 · F 视频动作提示词包 · G 连贯性圣经 · H 声音与对白方案 · I 剪辑与合成方案 · J QC 与修复。

失败代码 F1–F19 定义在 `references/failure-modes.md`，该文件是唯一所有者，其他文件只引用代码并给链接，不得复制一份分类表；提示词形态 S1–S4 定义在 `references/ai-video-tool-adapters.md`。改动任一编号都是破坏性变更，需要全库同步。

保留前缀，保证任何编号在笔记里都不产生歧义：`S` 仅用于提示词形态，`F` 仅用于失败代码，`P`/`G`/`Q` 是 `assets/qc-checklist.md` 的三道闸，`SH` 是示例中的镜头号，`L` 是成本阶梯的层级。不要让一个字母承担第二套编号。

单一所有者：身份串（`references/continuity-bible.md`）、光比与"亮面比暗面"约定（`references/lighting-and-color.md`）、30 度规则、连贯性几何与六级景别阶梯（`references/cinematic-language.md`）、单条时长策略与运动预算（`references/ai-video-tool-adapters.md`）、留头留尾（`references/editing-and-assembly.md`）、重试经济学（`references/production-workflow.md`）、声音层级（`references/sound-and-dialogue.md`）、F 代码分类（`references/failure-modes.md`）、提示词措辞——动词库、替换表、负面词（`references/prompt-lexicon.md`）。其他文件一律给链接，不要复述——复述必然漂移。

负面提示词一律点名**具体物件**，不写类别。"no modern objects" 是生成模型无法解析的类别，也正是 F8 的成因机制——把东西一个个说出来。

## 如何添加新的导演风格模块

1. 在 `references/director_styles/` 下新建 `NN_<slug>.md`，严格沿用 v2 的 14 节结构（见上方英文段或任一现有模块）。
2. 认真写两个关键小节：`反例：这不是什么` 要指名两三个容易混淆的相邻风格并说明**机制上**的差别（引用其他模块编号），`风格参数` 的 YAML 必须逐字段填满。如果两个模块的参数几乎一样，说明其中一个不是独立镜头。
3. `落地示例` 必须使用统一对照场景：一个人拿着打算送出的东西站在关着的公寓门前，犹豫，然后没有敲门就离开。不要换场景。
4. 登记 4 处：风格索引 README、`SKILL.md` frontmatter description、`SKILL.md` 的 enum 与 Step 4 列表、顶层 README 的中英表和结构树。
5. 加 eval 用例，验证 overlay 切实改变了镜头/色彩/节奏/声音，并包含版权安全断言。
6. 本地跑 `npx markdownlint-cli2 "**/*.md"` 和 `lychee --offline "**/*.md"`。

### 版权安全

只描述**高层方法**。不要出现具体镜头、角色名、台词、剧情节拍。判据：如果一句话不能同样适用于该导演的若干部作品，它就太具体了。这条规则背后的声明——风格模块授权什么、不授权什么——见 [README.md 的"使用规则与免责声明"](README.md#使用规则与免责声明)；它不是 `LICENSE` 的条款，`LICENSE` 是未经修改的 MIT。

## 如何添加新的 AI 视频工具适配器

先看现有的能力优先路由是否已覆盖——该文件按控制面和四种提示词形态（S1 纯运动 / S2 全描述 / S3 首尾帧 / S4 多镜头时间戳）组织，没有特殊控制面的工具可能只需在能力矩阵加一列；若它带来矩阵还没有的控制面，再加一行。确实需要独立段落时，按现有格式追加：擅长点、控制面、提示词优先级、模板、工具特定规则、典型失败与修复。

**不要把版本号、价格、精确上限当作事实写死**——厂商改得很勤。用能力类别描述，并加上"以官方最新文档为准"的限定。图像模型同理，写在 `references/image-model-adapters.md`。

## 如何添加类型片手册 / 失败代码 / 输出模式

- 类型片：在 `references/genre-playbooks.md` 追加一块，字段集与现有类型完全一致，并在对比表加一行。
- 失败代码：只增不改，从 F20 起，四个区块齐全（症状、成因排序、按成本阶梯排序的修复、前后提示词对照），并同步到症状索引和 QC 表。
- 输出模式：只有在与 A–J 真正不同时才新增 Mode K，并加模板和 eval 用例。已有模式的风格变体请直接改已有模式。

## 风格规范

- 紧凑散文式 markdown；每句话都要能改变一个决策，否则删掉。
- 教技术的小节必须带**已填好的**示例；只有占位符的骨架算未完成。
- 教提示词技巧的地方优先给**前后对照**。
- 语言：`SKILL.md`、顶层 README、LICENSE、CHANGELOG、本文件，以及全部非风格的 `references/` 与 `assets/` 用英文，craft 术语内联中文注释，中文 UI 工具给双语模板；导演风格文件保持中文为主、YAML 键为英文、一句话镜头双语；顶层 README 双语镜像。
- 不用 emoji，不用营销语言，不编造工具事实。

## PR 检查清单

- [ ] CI 全绿（markdownlint + links）
- [ ] 加导演 = 4 处登记 + `风格参数` 填满 + 使用统一对照场景 + 新 eval 用例
- [ ] 加工具适配器 = 段落 + 矩阵列 + 无未加限定的版本/价格/上限声明
- [ ] 改流水线或模式 = 全库步骤号仍是 1..13、模式仍是 A..J，README 架构图与 CHANGELOG 同步
- [ ] 按 `evals/run.md` 跑过 eval 套件，新增/改动的用例通过
- [ ] 所有相对链接可解析（CI 跑 lychee offline）
- [ ] 没有任何具体镜头/台词/角色/剧情出现在风格模块里
- [ ] 双语 README 表保持一致

## 报 issue

issue 见 <https://github.com/wuwangzhang1216/DirectorSKILL/issues> 。常见类型：输出与预期不符（附 prompt 和输出）、某导演模块太泛或太像抄、某工具适配器过时（附官方文档链接）、某失败代码误诊（附 prompt、片子描述、实际有效的修复）。
