# 93｜红猴子能力整合与主导演调度合同

## 目标与边界

本合同回答“哪些红猴子技能值得进入 Acheng、怎样进入才会 `1+1>2`”。它不是第二套导演规则，也不把外部技能的旧示例、固定题材、平台参数或质量口号直接复制到生产正文。唯一生产真值仍是 `production.json`、七个模块的权属表和本包已有 H3／资产／视效合同。

机器可读清单是 [data/red-monkey-integrations.json](../data/red-monkey-integrations.json)。清单中的每条记录都必须写清来源、状态、角色、触发、输入、输出、唯一 owner、写入范围、冲突策略和自检项。状态含义如下：

| 状态 | 运行时含义 |
|---|---|
| `internalized` | 机制已吸收进现有模块；不再平铺第二套同名真值源。 |
| `selective` | 只吸收能减少遗漏的局部做法，主模块字段与本地合同优先。 |
| `advisory` | 只返回分析或建议 patch，主导演决定是否采用。 |
| `guardrail` | 只做安全／边界门禁，不改创作字段。 |
| `maintenance_only` | 只在审计、打包或路由维护时使用。 |
| `superseded` | 已审查但当前体系更强或职责冲突，禁止自动调度。 |

## 已纳入的互补能力

### 生产支路增强

- **H3**：`h3-prompt-writing` 负责五种模式的字段顺序与语法；`model` 模块负责项目事实、逐镜独立上下文、对白和完整性。两者不是两个编译器。
- **GPT Image 2/2.5**：`im2-clean-image` 的材质—光路、信息密度、CHANGE／PRESERVE EXACTLY／REBUILD 和负向卫生进入 `assets`；`asset_plan`、身份版本、参考图职责仍由 `assets` 独占。
- **视效**：`cinematic-vfx-prompt-engine` 的 CREATE／OPTIMIZE／REINFORCE／PERSONALIZE、流体骨架、三通道和四相位进入 `effects`；`OPTIMIZE` 仍受冻结哈希和白名单保护。
- **巨构**：`colossal-scale-visual-director` 的治理轮廓、世界机制、决定性事件、独立尺度证据和反碎层级进入 `shots/effects`；不另建巨构镜头表。
- **运镜**：`camera-moves-whitebox` 的 132 条白模只作为当前 `data/camera-moves.json` 的来源和检索目录；最终 H3 只读展开后的运动语言，绝不把编号喂给模型。
- **场景设计**：`scene-concept-art-director` 只在明确需要场景美术、环境概念图、背景板、场景修复、多视图或 moodboard→场景转换时触发。它生成 `scene_art_direction.json`、独立图像提示词、上传映射和 QA；assets 负责最终采纳，场景支路不写生产字段，不把 moodboard 图自动升级为 STYLE_MOTHER。

### 顾问、门禁与维护层

- **prompt-library**：把用户给出的优秀提示词拆成角色、任务、知识、工作步骤、输出格式、约束六项，再把可迁移机制映射到 `acting_design`、`motion_profile`、`asset_card`、H3 段落或参考策略。它不能自动改系统文件或生产正文。
- **red-monkey-reasoning-kit**：复杂架构、外部技能融合或用户要求“复现这段优秀提示词”时按需启用。默认一项主方法，最多三项有明确输入输出依赖；永远不写剧本事实、ShotSpec、资产真值或 H3 正文。
- **Lobster asset-manager**：只借用便携命名、标签和索引元数据；`asset_plan` 的 ID、哈希、版本和 `UPLOAD.md` 权威不被替换。
- **Lobster security-baseline**：涉及私人参考图、外部上传、安装、删除或其他外部变更时做安全门禁；普通本地提示词编译不被误报为敏感操作。
- **Lobster self-reflection**：在最终回执中区分机器结构通过、人工未验和真实媒体未生成，允许降级声明，不允许把未知升级为通过。
- **Lobster anti-omission gate**：把 task-layer-executor 中有价值的反省略检查抽成一次无写入执行门禁，检查范围、最低完整单元、模型正文独立性、证据和未决传播；它不会启动旧 L1–L4 排程，也不改生产字段或降低提示词细节。
- **Lobster hot-memory**：只吸收热／暖／冷上下文的选择思想；以连续性账本和不可变项目归档替代自动七日删除，不能声称主机可强制用户指定的 token 阈值。
- **skill-audit、skill-foundry、pre-publish-security**：只在维护、路由评测和打包门禁使用，不在单次镜头生产中重写数据。

旧 `lobster-skills/ai-video-workflow`、旧 `cinematic-director-engine` 和 `lobster-skills/task-layer-executor` 的第二调度器仍标记 `superseded`；当前只保留 anti-omission gate 对其中反省略机制的受控抽取，工具链、质量词、L1–L4 排程和后台任务暗示继续禁用。

## 主导演调度顺序

调度器先选一个生产模块，再根据输入特征追加零个或多个整合步骤。整合步骤只能是 `formatter`、`advisory`、`reference_catalog`、`analysis`、`decision_support`、`safety_gate`、`claim_audit`、`context_advisor` 或维护角色；它们不改变七个模块的唯一写入者。

| 请求情形 | 主模块 | 自动整合 | 返回物 |
|---|---|---|---|
| 分镜／Previs | `shots` | camera-moves；有 `colossal` 时追加 colossal | 语义化运镜与尺度证据建议 |
| 资产图／关键帧 | `assets` | im2-clean-image；需要归档时追加 asset-manager | 独立 GPT Image 提示词、参考图清单、清洁检查 |
| 场景美术／环境概念／背景板 | `assets` | scene-concept-art-director；有私人参考时追加 security-baseline | scene-art 合同、独立场景提示词、多视图连续性、QA 与 unresolved |
| VFX／巨构动作 | `effects` | cinematic-vfx；有巨物特征时追加 colossal | 仅属 `vfx`／`scale_proofs` 的证据 patch |
| H3 视频 | `model` | h3-prompt-writing；有私人上传时追加 security-baseline | 可直接提交的逐段正文与上传清单 |
| 用户提供优秀提示词 | 当前目标模块 | prompt-library；结构冲突再追加 reasoning-kit | 分析和字段映射，不直接覆盖正文 |
| 复杂架构／融合冲突 | `director` | reasoning-kit；必要时 skill-audit | 决策回执和被采用／拒绝的理由 |
| 最终审计／打包 | `continuity`／维护 | self-reflection；按请求追加 skill-audit、skill-foundry、pre-publish-security | 诚实性、路由或发布门禁报告 |

默认自动发现仍开启；整合步骤不是宿主必须注册的独立全局 skill。用户可在请求中写 `prompt-audit`、`reasoning-review`、`external_upload`、`colossal` 等特征，调度器也可从 stage 和已存在字段推断必要支路。`superseded` 记录永不自动进入计划。

## 输入、输出与冲突裁决

1. 整合前先验证主模块输入；缺失角色、场景、状态、真实参考或动作结果时返回 `NEEDS_DIRECTOR_REVISION`，不让顾问支路替用户编造。每次阶段交付还必须通过 anti-omission gate；它只能阻塞或要求补全，不能替代专业模块正文。
2. 整合层返回 evidence、建议或所属字段的 patch；主导演按 `module-registry.json` 合并一次。整合层不能整段替换 `shots`、`asset_cards`、`segments` 或 `production.json`。
3. 同一字段只有一个最终 owner。相邻职责只做一次前后复核：摄影看表演可见性，表演看景别适配，动作看 VFX 接触，VFX 看遮挡，资产看编译身份，编译看上传绑定。
4. 冲突按“用户本轮明确修订 → 已确认剧本与对白 → 已批准视觉事实 → ShotSpec → 本包规范 → 外部技法建议”裁决。采用与拒绝都写入决策回执，不能悄悄混合。
5. 任何“优化”不得借字数、审美或模型偏好删掉决定性事件；若 H3 容量不足，减冗余、合法拆段或回导演，不把冲突伪装成完成。

## 自检与失败传播

每条整合记录的 `self_check` 必须在回包中有证据。主导演在合并前执行：

- **边界检查**：没有内部代号、未解析参考标签、过期资产版本或外部技能的固定平台词进入最终正文。
- **单 owner 检查**：整合步骤没有 `write_paths`；若未来新增写入能力，必须先在模块注册表登记唯一路径。
- **因果检查**：表演、动作、VFX、尺度和光路仍能从触发事实推到可见结果。
- **交付检查**：资产 `.image.txt` 只含可直接粘贴的正文，名称索引保持干净；H3 `.h3.txt` 保持模式字段顺序，并附真实上传清单。
- **诚实性检查**：结构 PASS 不等于图片、视频或音频已生成；外部参考缺失、真实媒体未生成和未人工验收必须保留 `execution_gate`。

失败沿所属字段返回，不在整合层之间循环重写。最多一次有证据的局部修正；第二次仍冲突就回主导演决定或阻塞该阶段。

## 不应融合的能力

本包不把红猴子仓库中与影视生产无关的情绪管理、日报、EntroCamp 行为准则、通用 agent 自维护和宿主级任务调度硬编码进导演链。它们会扩大触发面、引入第二套记忆／调度真值或消耗上下文，和“主导演唯一写入者”相冲突。需要这些能力时由宿主单独调用，不改变本包生产合同。
