# OpenMontage 架构分析报告

> 调研对象：calesthio/OpenMontage（开源 agentic 视频生产系统，Python，AGPL-3.0）
> 调研目的：为 drama-factory（Java 21 + Spring Boot「AI 短剧工坊」，Harness 形态）提供架构借鉴
> 调研方式：基于一手源码与设计文档（PROJECT_CONTEXT.md、lib/、tools/、pipeline_defs/）的架构级解读

---

## 1. 项目速览

### 1.1 定位

OpenMontage 是一个**指令驱动（Instruction-Driven / Agent-First）**的开源 AI 视频生产平台。其核心哲学是：

- **智能体即智能本体**：Python 只承担「工具」与「持久化」两类职责，编排、创意决策、评审、阶段跃迁全部写在指令（YAML manifest + Markdown skill）里，由 agent 阅读理解并执行。
- **没有 Python 编排器、没有 Python 评审器、没有 Python handler**。执行链路是：agent 读 pipeline manifest（YAML）→ 读 stage director skill（MD）→ 调用 Python BaseTool → 用 meta skill 自审 → 调用 checkpoint 工具落盘 → 交人类审批。
- **能力优先的工具设计（Capability-First）**：每一类能力暴露一个「选择器工具 + 若干具体 provider 工具」，例如 TTS 侧有 `tts_selector` 作为路由器，下面挂 `elevenlabs_tts` / `google_tts` / `openai_tts` / `piper_tts`；视频侧有 `video_selector` 挂 `heygen_video` / `wan_video` / `hunyuan_video` / `ltx_video_local` / `ltx_video_modal` / `cogvideo_video`。

### 1.2 十二条 Pipeline

`pipeline_defs/` 下共有 12 份 YAML manifest，按类型划分：

| Pipeline | 类型 | 用途 |
|---|---|---|
| `talking-head` | Footage-based | 真人出镜口播 |
| `animated-explainer` | AI-generated | 全 AI 生成的解说视频 |
| `screen-demo` | Screen-recording | 屏幕录制 / 产品演示 |
| `clip-factory` | Short-form batch | 短视频批量切片 |
| `podcast-repurpose` | Podcast | 播客再加工 |
| `cinematic` | Cinematic edit | 电影化剪辑 |
| `animation` | Animation-first | 动画优先 |
| `character-animation` | Local rigged | 本地骨骼角色动画 |
| `hybrid` | Source-plus-support | 实拍 + 生成混合 |
| `avatar-spokesperson` | Avatar presenter | 数字人播报 |
| `localization-dub` | Localization | 本地化配音 |
| `framework-smoke` | Test harness | 框架冒烟测试 |

主状态机为：`idea → script → scene_plan → assets → edit → compose → publish`。注意 `animated-explainer` 在此基础上向前插入 `research` 与 `proposal` 两个 pre-production 阶段，形成「研究—提案—制作」的三段式。

### 1.3 52 个工具的分类

工具按**能力包**（capability package）组织在 `tools/` 下，每个工具继承 `tools/base_tool.py` 的 `BaseTool`：

- `tools/audio/` — TTS、音乐、音频混合
- `tools/video/` — 视频生成、拼接（`video_stitch`）、合成（`video_compose` / `hyperframes_compose`）
- `tools/enhancement/` — 画质增强、超分
- `tools/analysis/` — 视频分析（`video_analyzer`）、转写（`transcript_fetcher`）、场景检测（`scene_detect`）、抽帧（`frame_sampler`）
- `tools/graphics/` — Three.js 世界构建、GLTF 资产目录、Atlas 3D、fal.ai 3D、Blender 世界
- `tools/avatar/` — 数字人、口型同步
- `tools/subtitle/` — 字幕

每个工具都要在 contract 里声明 `name / version / tier / capability / provider / supports / fallback_tools / agent_skills` 等字段，并实现 `execute()` 返回 `ToolResult`。

### 1.4 Skill 三层知识架构

```
Layer 1: tools/tool_registry.py   → "有哪些工具"（运行时能力、状态、成本）
Layer 2: skills/                  → "OpenMontage 怎么用这些工具"（项目约定）
Layer 3: .agents/skills/          → "这项技术本身怎么工作"（通用 API 规则，skills.sh）
```

- **Layer 1** 是运行时事实层：工具在注册表里登记自己的名字、能力、provider、状态（available / degraded / unavailable）、估算成本、历史成功率、延迟 p50 等。它是评分引擎的数据源。
- **Layer 2** 是项目约定层：`skills/core/`、`skills/creative/`、`skills/meta/`、`skills/pipelines/` 下的 Markdown 文件，告诉 agent「在这个项目里，这类任务该怎么做、边界在哪」。例如 `skills/core/hyperframes.md` 讲清楚何时该选 HyperFrames 而不是 Remotion。
- **Layer 3** 是技术事实层：`.agents/skills/` 下是 vendored 的第三方技术 skill（如 `hyperframes*/`、`threejs-world-generation/`），描述该技术本身的通用规则。工具的 `agent_skills[]` 字段是 Layer 1 → Layer 3 的桥：从工具跳到「它依赖的技术怎么用」。

---

## 2. 模块清单（lib/ 及各核心模块职责）

| 模块 | 一句话职责 |
|---|---|
| `lib/scoring.py` | Provider 与 production path 的多维度加权评分引擎，用可解释的 7 维评分替代「首个可用 provider」的粗糙选择。 |
| `lib/slideshow_risk.py` | 在 6 个维度上给视频计划打「像幻灯片」的风险分（0–5，越低越好），并给出 strong / acceptable / revise / fail 四档判决。 |
| `lib/delivery_promise.py` | 在选 provider 前先把「这条片子承诺交付什么」分类并锁定，防止静默从 motion-led 降级为 still-led。 |
| `lib/verify_scene_pacing.py` | 用与前端帧计算一致的方式追踪 TerminalScene 的步骤时间线，断言「每条旁白 cue 附近都有可见动作」以及「步骤不溢出、不空转」。 |
| `lib/checkpoint.py` | Checkpoint 的写入/读取工具，供 agent 在每个阶段落盘状态与产物。 |
| `lib/pipeline_loader.py` | Pipeline manifest 的加载器与辅助函数（把 YAML 解析成 agent 可消费的结构）。 |
| `lib/config_model.py` | 运行时配置的 Pydantic 模型（含 `BudgetMode` 枚举等）。 |
| `lib/media_profiles.py` | 平台专属渲染 profile（分辨率、码率、宽高比等）。 |
| `lib/hyperframes_style_bridge.py` | 把 playbook 映射成 HyperFrames workspace 的 CSS 自定义属性与 `DESIGN.md`。 |
| `tools/cost_tracker.py` | 预算治理核心：estimate → reserve → reconcile 三段式，落盘 `cost_log.json`，支持 warn / cap / observe 模式与单笔审批阈值。 |
| `tools/tool_registry.py` | 工具发现与报告：扫描 `tools/` 下所有 BaseTool 子类，对外提供工具清单与状态，是评分引擎的输入源。 |
| `tools/base_tool.py` | 所有工具的契约基类（ToolContract），规定 contract 字段与 `execute()` 语义。 |
| `styles/playbook_loader.py` | Style playbook 的加载、校验与设计智能（配色 / 字体 / 无障碍）。 |
| `schemas/artifacts/` | 规范产物（canonical artifacts）的 JSON schema：`brief`、`script`、`scene_plan`、`asset_manifest`、`edit_decisions`、`render_report`、`publish_log` 等。 |
| `schemas/styles/playbook.schema.json` | Playbook schema v2，含 chart_palette、scale_system、weight_matrix、color_rules 等设计 token。 |
| `pipeline_defs/` | 12 份 pipeline manifest YAML。 |
| `skills/` | Layer 2 知识：`core/`、`creative/`、`meta/`、`pipelines/`。 |
| `.agents/skills/` | Layer 3 知识：vendored 的通用技术 skill。 |
| `tests/qa/` | 逐工具输出质量校验脚本。 |
| `tests/contracts/` | Pipeline manifest 与工具的契约测试。 |

---

## 3. Pipeline 机制

### 3.1 YAML manifest 的顶层字段

一份 pipeline manifest（以 `pipeline_defs/animated-explainer.yaml` 为例）顶层字段包括：

- `name`：pipeline 标识符（如 `animated-explainer`）。
- `version`：manifest 版本（如 `"2.0"`）。
- `description`：人类可读描述。
- `category`：分类（如 `generated`）。
- `stability`：稳定性等级（如 `production`）。
- `default_checkpoint_policy`：默认 checkpoint 策略（如 `guided`）。
- `reference_input`：是否支持参考视频输入，含 `supported`、`analysis_depth`、`analysis_tools`（列出 `video_analyzer` / `transcript_fetcher` / `video_downloader` / `scene_detect` / `frame_sampler`）。
- `extensions`：扩展开关（`custom_scripts` / `custom_playbooks` / `custom_skills` / `custom_tools`）。
- `required_skills`：本 pipeline 依赖的所有 skill 路径列表（含各 stage director + meta skill）。
- `orchestration`：编排配置，含 `mode`（如 `executive-producer`）、`skill`、`budget_default_usd`、`max_revisions_per_stage`、`max_send_backs`、`max_wall_time_minutes`。
- `compatible_playbooks`：`recommended` / `also_works` / `custom_allowed`。
- `stages`：stage 数组，见下。

### 3.2 Stage 的字段

每个 stage 是一个对象，关键字段：

- `name`：阶段名（research / proposal / script / scene_plan / assets / edit / compose / publish）。
- `skill`：本阶段该读的 director skill 路径（如 `pipelines/explainer/script-director`）。
- `required_artifacts_in` / `optional_artifacts_in`：进入本阶段前必须/可选已存在的产物。
- `produces`：本阶段产出的产物列表（如 `script`、`decision_log`）。
- `tools_available`：本阶段 agent 可调用的工具白名单。
- `required_tools` / `optional_tools`：更细的工具约束。
- `checkpoint_required`：是否必须落盘 checkpoint。
- `human_approval_default`：是否默认需要人类审批。
- `review_focus`：评审关注点清单（自然语言条目，给 reviewer skill 用）。
- `success_criteria`：可判定的成功标准（如「schema 合法且至少 3 个 concept_options」）。
- `sub_stages`：子阶段（如 proposal 下有 `sample` 子阶段，条件 `video_analysis_brief_exists` 才触发，用于生成 10–15 秒预览片段）。

### 3.3 执行语义

Agent 的执行循环是：

1. **读 manifest**：agent 拿到 pipeline YAML，理解 stages 顺序、每阶段产出、可用工具、审批门。
2. **读 stage skill**：进入某 stage 时，加载该 stage 的 director skill（Markdown），学习「怎么做这一步」。
3. **调工具**：只在 `tools_available` 白名单内调用 Python BaseTool，工具返回 `ToolResult`。
4. **自检**：用 `skills/meta/reviewer.md` 对产物做 advisory 评审，最多 2 轮；对照 `success_criteria` 与 `review_focus`。
5. **Checkpoint**：调用 `lib/checkpoint.py` 把产物与状态落盘。
6. **人工审批**：若 `human_approval_default: true`，暂停并等待人类确认；确认后进入下一 stage。

三要素（stage / checkpoint / approval）在语义上的分工是：**stage 定义「做什么、产出什么、能用什么工具」；checkpoint 定义「什么时候落盘、状态怎么持久化」；approval 定义「哪些 stage 必须人类点头才能继续」**。三者正交，可以自由组合。

---

## 4. Provider 抽象与评分

### 4.1 tool_registry 的发现机制

`tools/tool_registry.py` 负责扫描 `tools/` 下所有继承 `BaseTool` 的类，收集它们的 contract 信息，形成一份运行时可查询的工具清单。Agent 不直接 import 具体工具，而是通过注册表发现「当前有哪些工具、什么状态、什么能力」。这带来两个好处：新增 provider 无需改动编排逻辑；工具的健康状态（available / degraded / unavailable）成为评分输入。

### 4.2 七个评分维度

`lib/scoring.py` 的 `ProviderScore` 定义了 7 个 0–1 维度，加权求和得到 `weighted_score`：

| 维度 | 权重 | 含义 |
|---|---|---|
| `task_fit` | 0.30 | 该 provider 是否最契合当前资产类别（用 intent 与 best_for 的关键词重叠度算，含同义词扩展）。 |
| `output_quality` | 0.20 | 对当前 brief 的预期保真度（优先用历史 quality_score，否则用 stability + tier 推算）。 |
| `control` | 0.15 | 参考图 / 风格可指导程度（按 supports 里的 controlnet / reference_image / style_transfer 等加权）。 |
| `reliability` | 0.15 | 运行时置信度（优先历史成功率，否则按 available/degraded 与 production/experimental 分级）。 |
| `cost_efficiency` | 0.10 | 每美元换来的质量（免费=1.0，超预算=0.0）。 |
| `latency` | 0.05 | 交付时延可接受度（优先实测 p50，否则按 runtime 类别 local/hybrid/api 推）。 |
| `continuity` | 0.05 | 与已锁定决策的一致性（同 provider=0.9，不同=0.4）。 |

除了 7 维加权，评分函数还包含若干**上下文惩罚/奖励**：motion_required 但工具只能出图时 `task_fit *= 0.2`；偏好生成视觉但工具是 stock 时降权；reference-conditioning 与 image-editing 场景下有 supports 则加分、无则降权；cinematic 意图下命中 3+ 个 premium feature（native_audio / multi_shot / camera_direction / lip_sync / cinematic_quality）则加分。

同文件还定义了 `ProductionPathScore`（8 维：delivery_fit / quality_fit / capability_confidence / fallback_integrity / budget_fit / speed_fit / controllability / consistency_fit），用于对「整条生产路径」而非单个 provider 打分。

### 4.3 decision log / cost snapshot 的作用

- **decision log**：`proposal` stage 的 `produces` 里包含 `decision_log`。它记录「为什么选了这个 concept、这条路径、这些 provider」，让每个选择都可追溯、可解释，而不是「因为它可用」。这与评分引擎的 `explain()` 设计一致——每个选择都应能被讲清楚。
- **cost snapshot**：`tools/cost_tracker.py` 的 `cost_snapshot()` 返回 `{total_spent_usd, total_reserved_usd, budget_remaining_usd}` 三个数，供编排层随时查询预算水位，用于决策「还能不能继续调用付费工具」。它与 estimate/reserve/reconcile 三段式配合：先估算、再预留、执行后对账。

---

## 5. Skill 格式

### 5.1 skills/ 目录布局

- `skills/core/` — 项目级核心约定（如 `hyperframes.md` 讲何时选 HyperFrames vs Remotion）。
- `skills/creative/` — 创意方法（叙事、节奏、风格）。
- `skills/meta/` — 元能力：`reviewer.md`（评审）、`checkpoint-protocol.md`（checkpoint 协议）、`skill-creator.md`（创建新 skill）、`animation-runtime-selector.md`、`voice-performance-director.md`。
- `skills/pipelines/<pipeline>/` — 每个 pipeline 的 7 个 stage director skill（idea 到 publish，实际命名如 `executive-producer` / `research-director` / `proposal-director` / `script-director` / `scene-director` / `asset-director` / `edit-director` / `compose-director` / `publish-director`）。

### 5.2 frontmatter 字段

Skill 是 Markdown 文件，顶部有 YAML frontmatter。结合 manifest 的 `required_skills` 引用方式与 `skills/INDEX.md` 的角色，frontmatter 至少包含：

- `name`：skill 标识（与 manifest 中引用路径对应）。
- `description`：一句话说明。
- `layer`：属于 Layer 2 还是 Layer 3。
- `category`：core / creative / meta / pipelines。
- `applies_to`：适用的 pipeline 或 stage。
- `agent_skills`：本 skill 关联的 Layer 3 skill 引用（工具侧 `agent_skills[]` 与之呼应）。
- `version`：版本号。

> 说明：字段清单依据 `skills/INDEX.md` 的索引结构、manifest 的 `required_skills` 引用语义、以及 `PROJECT_CONTEXT.md` 对「Layer 2 是项目约定、Layer 3 是技术规则」的界定综合得出；本报告不逐字复述其 frontmatter 文本。

### 5.3 director skill 与 reviewer skill 的区别

- **Director skill**（`skills/pipelines/<pipeline>/<stage>-director.md`）：面向**执行**。告诉 agent 在这个 stage 里「怎么做」——输入产物是什么、产出什么、可用工具怎么组合、成功标准是什么。它是**建设性**的、**阶段专属**的。
- **Reviewer skill**（`skills/meta/reviewer.md`）：面向**审查**。它是**meta 级**、**跨阶段通用**的，对任意产物做 advisory 评审，**最多 2 轮**，不阻塞、只建议。它不产出成品，只产出「是否达标、差在哪」的判断，供 agent 决定是否 send-back。

一句话：director 负责「做对」，reviewer 负责「看出没做对」，checkpoint-protocol 负责「什么时候把状态钉住」。

---

## 6. 校验规则体系

### 6.1 pre-compose validation gate（合成前门）

在进入 compose 之前，系统要过一道**合成前校验门**，检查项包括：

- `slideshow_risk` 6 维度评分是否在可接受范围（verdict 不能是 fail）。
- `delivery_promise.validate_cuts(edit_decisions.cuts)` 是否通过——motion_ratio 是否达到该 promise_type 的 `min_motion_ratio`，非 motion 剪辑是否超出 `still_fallback_allowed` 限制。
- `edit_decisions.render_runtime` 是否与 `proposal_packet` 一致——**静默切换渲染运行时是 CRITICAL 级治理违规**。
- 若 `render_runtime='hyperframes'`，则 `hyperframes lint` 与 `hyperframes validate` 必须通过。
- 场景计划是否覆盖完整脚本时长、无缺口。

### 6.2 post-render self-review（渲染后门）

在渲染完成后、publish 之前，agent 用 meta skill 做自审，检查项包括：

- 输出文件存在且可播放（过 ffprobe）。
- 时长在目标 ±5% 内。
- 音频清晰，旁白与音乐平衡。
- `render_report` schema 合法。
- 与 `review_focus` 逐条对照。

两道门形成「合成前静态校验 + 渲染后动态校验」的双重保险。

### 6.3 slideshow_risk 的 6 个维度

`lib/slideshow_risk.py` 从 6 个维度给「像幻灯片」的风险打分，每维 0–5，**越低越好**，取平均后判决：

| 维度 | 含义 |
|---|---|
| `repetition` | 场景类型、描述、景别是否高度重复。 |
| `decorative_visuals` | 场景是「装饰」还是「传达」（有无 information_role / narrative_role / shot_intent）。 |
| `weak_motion` | 有运镜但缺乏叙事目的（有 camera_movement 却无 shot_intent）。 |
| `weak_shot_intent` | 镜头意图覆盖率低，多数镜头无明确理由。 |
| `typography_overreliance` | text_card / stat_card / kpi_grid 类场景占比过高，视频像动画幻灯片。 |
| `unsupported_cinematic_claims` | 自称 cinematic 但缺 hero_moment、缺运镜、缺灯光定义。 |

判决阈值：`< 2.0` strong；`< 3.0` acceptable；`< 4.0` revise；`>= 4.0` fail（**不应进入 compose**）。

### 6.4 delivery_promise 的语义

`delivery_promise` 是「这条片子承诺交付什么」的**显式分类 + 锁定**。核心动机：**防止最致命的失败模式——静默从 motion-led 降级为 still-led 而用户毫不知情**。它定义 8 种 `PromiseType`：motion_led / source_led / data_explainer / teacher_explainer / screen_demo / avatar_presenter / hybrid / localization。每种类型有对应规则：

- `still_fallback_allowed`：是否允许静帧兜底。
- `requires_video_generation`：是否必须真实视频生成。
- `min_motion_ratio`：真实运动剪辑的最低占比。

`validate_cuts()` 的关键设计是：**只有 video / animation / avatar 类剪辑算「真实运动」；Remotion 组件场景（text_card / chart / kpi_grid 等）属于「动画幻灯片」，有转场但不是真实运动**。若 motion_ratio 低于阈值且无 `approved_fallback='still_led'` 审批，则判违规、必须停下问人，而不是悄悄替换。

### 6.5 source_media_review 的作用

`source_media_review` 针对**用户提供的源素材**做前置审查。其价值在于：在选 provider、写脚本之前，先摸清「手上有什么」——素材的分辨率、时长、音轨、画质、可用片段，从而让 `delivery_promise` 的分类有事实依据（例如 `has_footage=true` 会触发 `source_led` 倾向），让后续的 scene_plan 与 asset_manifest 不至于凭空规划出无法用现有素材兑现的场景。它是「承诺—能力」对齐链条的第一环。

---

## 7. 对 drama-factory 的借鉴清单

以下每条均以**自有话重新表述设计思想**，并给出 drama-factory（Java 21 + Spring Boot，Harness 形态）的落地方式。

### 7.1 Pipeline YAML 模板

**借什么思想**：把一条创作流水线声明成一份可读的 YAML——顶层声明身份、编排参数、预算、兼容风格、依赖 skill；每个 stage 声明「读什么产物、产出什么产物、能用哪些工具、是否要 checkpoint、是否要人工审批、评审关注什么、成功标准是什么」。

**我们怎么实现**：在 drama-factory 里定义 `pipeline-defs/*.yaml`，用 Spring Boot 的 `@ConfigurationProperties` 把 YAML 绑定成 `PipelineDefinition` record；stage 用 `StageDefinition` record 承载；用 Jackson + JSON Schema 做加载期校验，schema 放 `schemas/pipeline_manifest.schema.json`。Run 启动时先加载并校验 manifest，再交给 Harness 执行。

### 7.2 Provider 路由评分

**借什么思想**：不要「谁先注册谁先用」，而是用**多维加权评分 + 上下文修正**让每个 provider 选择都可解释、可复现。核心维度：任务契合、输出质量、可控性、可靠性、性价比、时延、连续性；再加场景修正（需要运动却只能出图 → 重罚；需要参考图但无相关支持 → 降权；cinematic 意图命中多个高级特性 → 加分）。

**我们怎么实现**：在 `drama-factory-provider` 模块写 `ProviderScoringService`，用 `ProviderScore` record + `weightedScore()` 方法；评分维度与权重做成配置（放 `application.yaml` 的 `provider.scoring.weights`）；每个 `ProviderAdapter` 暴露 `capabilities()` 返回 supports 映射；`rankProviders(taskContext)` 返回排序列表并附 `explain()` 文本，写入 `decision_log`。

### 7.3 计费台账

**借什么思想**：预算治理用 **estimate → reserve → reconcile** 三段式，配合 reserve_pct 保留金、单笔审批阈值、首次付费工具审批、warn/cap/observe 三种模式；随时能出 cost_snapshot。

**我们怎么实现**：在 `drama-factory-billing` 模块写 `CostLedger`（Spring `@Service`，`@Transactional`），用 JPA 实体 `CostEntry`（status: ESTIMATED / RESERVED / COMPLETED / FAILED / REFUNDED）；`reserve()` 在 cap 模式抛 `BudgetExceededException`，在 warn 模式打 warning 标记；每次 Run 结束输出 `cost_snapshot` 到 Run 报告；用 Spring 事件发布 `BudgetThresholdReached` 供 Harness 暂停。

### 7.4 节奏校验

**借什么思想**：用与前端帧计算一致的方式追踪时间线，断言「每条旁白 cue 附近都有可见动作」，并检查步骤不溢出场景、不长时间空转。

**我们怎么实现**：在 `drama-factory-verify` 模块写 `ScenePacingVerifier`，输入 `SceneSteps` 与 `narrationCues`（时间戳+描述），输出 `PacingReport`；用 `DurationCalculator` 按 fps 逐帧累加，容忍度做成配置；校验失败时抛 `PacingViolationException`，由 Harness 决定是 send-back 还是 fail。集成到 compose 前的 validation gate。

### 7.5 质量门（slideshow 风险 + 交付承诺 + 双门校验）

**借什么思想**：合成前用「像不像幻灯片」的 6 维风险分 + 「承诺交付什么」的 motion_ratio 校验做静态门；渲染后用「可播放/时长/音画」做动态门；两道门之间不允许静默降级——任何降级必须显式审批。

**我们怎么实现**：在 `drama-factory-quality` 模块写 `SlideshowRiskScorer`（6 维，0–5，四档判决）与 `DeliveryPromiseValidator`（8 种 promise_type + min_motion_ratio + still_fallback 规则）；在 Harness 的 `PreComposeGate` 与 `PostRenderGate` 两个 `RunStage` 里调用；违规时把 `violations` 写进 `Run.report` 并触发 `ApprovalRequiredException`，由 Harness 暂停 Run 等人工介入。

### 7.6 三要素编排模型（stage / checkpoint / approval）

**借什么思想**：把「做什么」（stage）、「何时钉住状态」（checkpoint）、「谁点头才能继续」（approval）三件事正交拆开，让任意 pipeline 都能自由组合。

**我们怎么实现**：Harness 用 `RunStage` 接口统一 stage；`CheckpointWriter` 在 stage 结束时落盘 `RunCheckpoint` 到数据库 + 对象存储；`ApprovalPolicy` 枚举（NONE / OPTIONAL / REQUIRED）挂在 stage 定义上；`RunOrchestrator` 读 manifest 顺序执行，遇到 REQUIRED 就挂起 Run 状态为 `AWAITING_APPROVAL`，通过 REST/WebSocket 通知前端。

### 7.7 三层知识架构

**借什么思想**：把知识分三层——运行时事实（工具注册表）、项目约定（怎么写）、技术规则（技术本身怎么用），用 `agent_skills[]` 做桥接。

**我们怎么实现**：Layer 1 用 Spring 的 `ProviderRegistry`（`@Component` 自动收集所有 `ProviderAdapter` bean）；Layer 2 放 `prompts/skills/` 下的 Markdown（core / creative / meta / pipelines）；Layer 3 放 `prompts/tech-skills/`；Provider 的 `agentSkills()` 返回 Layer 3 引用列表。Harness 组装 prompt 时按「manifest → stage skill → 工具 agent_skills」顺序拼接。

### 7.8 参考输入与产物契约

**借什么思想**：pipeline 可声明 `reference_input`（参考视频）并挂一组分析工具；所有中间产物（brief / script / scene_plan / asset_manifest / edit_decisions / render_report / publish_log）都有 JSON schema，跨 stage 传递的是 schema 合法的产物，而非散乱数据。

**我们怎么实现**：在 `drama-factory-core` 定义 `Artifact` 接口与各 record；用 `ArtifactValidator` 对每个产物跑 JSON Schema 校验；`reference_input` 做成 `ReferenceAnalysisService`，复用分析类工具；产物统一存 `RunArtifact` 表，字段含 `runId / stage / type / payload(JSONB) / schemaVersion`。

### 7.9 决策日志

**借什么思想**：每个关键选择（选哪条路径、哪个 provider、哪个 runtime）都要写进可追溯的 decision log，配合评分引擎的 `explain()`，让「为什么这么选」有据可查。

**我们怎么实现**：在 `drama-factory-core` 写 `DecisionLogService`，每次 provider 选择、runtime 选择、promise 分类都追加一条 `DecisionEntry`（时间、决策点、候选、评分、最终选择、理由）；与 `Run` 关联，前端可查看「本次 Run 的决策链」。

### 7.10 承诺锁定与静默降级防护

**借什么思想**：在制作前就把「承诺交付什么」显式分类并锁定；若执行阶段无法兑现，必须停下问人，绝不静默替换。

**我们怎么实现**：`DeliveryPromise` record 在 proposal 阶段生成并写入 `Run.promise`；在 compose 前用 `DeliveryPromiseValidator` 对照 `edit_decisions.cuts` 校验；若 motion_ratio 不达标且无 `approvedFallback`，则 `RunOrchestrator` 抛 `ApprovalRequiredException`，Run 挂起等人工确认。

---

## 8. 许可证合规声明

OpenMontage（calesthio/OpenMontage）采用 **AGPL-3.0** 许可证发布。AGPL-3.0 是强 copyleft 许可证，对通过网络提供服务的使用方式有传染性约束。

本报告的立场与承诺：

1. **本轮仅做架构分析**，不输出 OpenMontage 的源码或文档的逐字大段引用。报告中出现的引用均为短句（< 40 字）并注明出处文件，符合合理使用边界。
2. 报告中所有「可借鉴点」均以**自有语言重新表述设计思想**，未复制其 YAML、Python 代码或 Markdown 文本。
3. **drama-factory 集成时只借思想、用自有实现重写**：任何从 OpenMontage 借鉴的机制（pipeline manifest 结构、评分维度、计费台账、节奏校验、质量门等）都将在 Java 21 + Spring Boot 技术栈下用自研代码实现，**不逐字复制其代码文本进仓库**。
4. 若未来需要直接使用 OpenMontage 的代码或二进制，将先做法务评估，确认 AGPL-3.0 的传染范围（尤其是网络服务条款）与 drama-factory 的分发方式是否兼容；在评估通过前不引入其代码。
5. 本报告本身是分析性文档，不构成对 OpenMontage 代码的再分发。

---

*报告完*