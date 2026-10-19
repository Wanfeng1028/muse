---
name: openmontage-reviewer
version: "1.0.0"
description: 在每个管线阶段完成后、检查点之前执行质量把关，依据 CHAI 规则从准确性、完整性、建设性三个维度审查产物。适用于所有阶段的自我审查，确保最终视频值得观看。
metadata:
  license: AGPL-3.0
---

# 审查者（Reviewer）— 元技能

## 适用时机

任何管线阶段的工作完成后、打检查点之前。你是"工作完成"与"工作验收"之间的质量关卡。本技能用指令驱动的自审协议替代 Python reviewer 类。

每个阶段都必须审查，没有例外。审查质量决定最终视频是否值得观看。

## 批评质量（CHAI 规则）

> 发现不等于批评。发现指出问题；批评告诉下一阶段怎么修。CMU/哈佛 CHAI 研究（"Building a Precise Video Language with Human-AI Oversight"，arXiv 2604.21718v2）表明，从三个维度衡量的批评质量直接决定下游产出质量。每次审查都必须应用这三条。
>
> **准确。** 每条发现必须引用具体的产物字段、行号或可见素材帧。禁止臆造的批评——如果你指不出问题在哪，就是在猜。
>
> **完整。** 一次审查只抓到一个错误却漏掉第二个，比标记"需要再审一轮"继续更糟。如果发现一个严重问题，先扫完同类问题再返回。模式匹配：这个产物里同样的错误还可能藏在哪里？
>
> **建设性。** 每条"critical"发现必须提出具体修复方案，不能只指出问题。"字幕错了" → "字幕写的是'右边的人'；人实际在画面左侧。改为'画面左侧的人'。"如果提不出修复方案，标记为"investigation"而非"critical"。
>
> 去掉任何一条属性都会可测量地损害管线产出。审查者是瓶颈——必须严格。

## 协议

### 第一步：加载审查上下文

审查前收集：
1. 管线清单中本阶段的**审查焦点项**（`review_focus` 字段）
2. 管线清单中本阶段的**成功标准**（`success_criteria` 字段）
3. **活跃 playbook** 的质量规则
4. 本阶段产出的**产物**

### 第二步：Schema 校验

首先做不可协商的检查：
- 对照 JSON schema 校验产物（`schemas/artifacts/<name>.schema.json`）
- 如果 schema 校验失败，这是 **critical** 发现——立即修复，不得继续

### 第三步：对照焦点项审查

对清单中的每个 `review_focus` 项：
1. 针对该具体标准评估产物
2. 分配严重级别：
   - **critical** — 继续前必须修复。产物损坏、不完整或有严重错误。**按 CHAI 规则，每条 critical 发现必须附带 `proposed_fix`（具体替换文本、精确字段值或明确纠正动作）。没有修复方案的 critical 降级为 `investigation`。**
   - **suggestion** — 应该修复。显著提升质量但不阻塞进度。**suggestion 必须附带 `proposed_change` 描述如何改进。**
   - **nitpick** — 可以修复。锦上添花的小打磨。可独立存在，无需附带修改方案。
   - **investigation** — 真实关切但无法定位修复方案。留到下一轮处理，不阻塞。
3. 写出具体、可操作的发现（不要含糊）

**好的发现：**"第 3 节旁白 180 词配 10 秒窗口——即 1080 词/分钟，不可能念完。砍到 25 词。"
**差的发现：**"脚本可能太长了。"

### 第四步：对照 Playbook 交叉检查

如果有活跃的风格 playbook，验证：
- [ ] 色彩引用匹配 playbook 调色板
- [ ] 转场类型在 playbook 允许集合内
- [ ] 节奏规则被遵守（最小/最大时长）
- [ ] 素材描述包含 playbook 风格线索
- [ ] 质量规则未被违反

每项违规为 **suggestion** 级发现。

### 第四步 b：品味方向审查

如果存在 `proposal_packet.production_plan.taste_profile` 或活跃 playbook 的 `taste_profile`，验证：
- [ ] `design_read` 解释了简报、受众和交付承诺；不只是"现代/简洁/专业"
- [ ] `visual_variance`、`motion_intensity` 和 `information_density` 在场景布局、节奏、标注密度和素材提示中有所体现
- [ ] 当工坊级工作、AI 图片/视频、产品/品牌视觉或情绪板依赖视觉细微差别时，`reference_strategy` 已提供
- [ ] 列出的 `anti_patterns` 确实被避免
- [ ] 质量门控足够具体，下一阶段可以执行

在提案阶段，缺失 `taste_profile` 对预设/低风险工作是 **suggestion**，对工坊级、产品/品牌、发布、主视觉或自定义 playbook 工作是 **critical**。在 scene_plan/edit/compose 阶段，除非违反已批准的交付承诺，否则刻度偏差视为 **suggestion**。

### 第五步：评估成功标准

对清单中的每个 `success_criteria` 项：
- 标准是否满足？（是/否/部分）
- 如果未满足，创建 **critical** 发现

### 第六步：做出决策

按严重级别统计发现：

| 场景 | 动作 |
|------|------|
| 0 个 critical，有 suggestion/nitpick | **通过** — 进入检查点。记录 suggestion 备查。 |
| 1+ 个 critical 发现 | **修订** — 修复所有 critical 发现，重新审查（最多 2 轮）。 |
| 2 轮修订后仍有 critical | **带警告通过** — 继续推进，记录未解决问题。永远不要无限阻塞。 |

### 第七步：记录审查

按以下结构组织审查：

```
## Review: [stage_name] — Round [N]

**Decision:** PASS / REVISE / PASS_WITH_WARNINGS

### Findings

1. [CRITICAL] 发现标题
   - Description: 问题是什么
   - Action: 修复什么
   - Status: pending / fixed / accepted / deferred

2. [SUGGESTION] 发现标题
   - Description: 哪里可以更好
   - Action: 如何改进
   - Status: pending / accepted / deferred

### Summary
- Critical: N (N fixed)
- Suggestions: N
- Nitpicks: N
- Playbook violations: N
- Success criteria met: N/M
```

## 核心原则

1. **具体，不含糊。**"钩子不够强"没有用。"钩子提出了问题但没有制造紧迫感——试试用 key_point #2 中令人惊讶的数据开头"才可操作。

2. **Critical 就是 Critical。** 不要夸大严重级别。缺失 schema 字段是 critical。略啰嗦的段落是 suggestion。逗号拼接是 nitpick。

3. **最多两轮。** 目标是交付，不是完美。两轮修订后带警告通过，继续推进。完美主义会杀死管线。

4. **审查产物，不审查过程。** 你检查的是输出，不是怎么产出的。如果简报有说服力，agent 用了不寻常的方法也无所谓。

5. **Playbook 是法律。** 如果 playbook 规定"屏幕上不超过 3 种颜色"，那不是建议——是约束。违规一律标记。

## 各阶段审查重点

| 阶段 | 最关键的事 |
|------|-----------|
| research | 来源多样性、声明可验证性、视觉参考质量 |
| proposal | 交付承诺清晰度、渲染器族和渲染运行时选择、音乐/语音方案、决策日志已启动 |
| idea | 钩子独特性、调研深度、角度多样性 |
| script | 时间精度、叙事弧线、增强线索密度 |
| scene_plan | 全覆盖、视觉多样性、素材可行性、幻灯片风险评分 |
| assets | 文件存在性、风格一致性、预算遵守 |
| edit | 时间线覆盖、音频同步、字幕存在、交付承诺合规 |
| compose | 可播放性、时长精度、音频质量、合成前校验通过 |
| publish | SEO 质量、元数据完整性、导出打包 |

## 参考对齐审查

当存在 VideoAnalysisBrief 时（参考驱动制作），在**每个阶段**运行。

### 检查项：

1. **依据检查：** 输出是否引用了 VideoAnalysisBrief 中的具体发现，还是在凭空编造？
   - 提案提到"快节奏"但参考的 pacing_style 是"slow_contemplative" → **CRITICAL**
   - 脚本声称参考有旁白但 VideoAnalysisBrief 显示无旁白 → **CRITICAL**

2. **差异化检查：** 每个概念/场景是否与参考有明确创意差异，还是照抄？
   - 提案是参考的碳拷贝（相同主题、相同结构、相同处理） → **CRITICAL**
   - 每个概念至少有一个元素必须与参考不同 → 弱则为 **SUGGESTION**
   - 简报中的创意差异化种子应反映在提案中

3. **承诺保持：** 用户说喜欢的参考元素是否仍存在于输出中？
   - 用户说"我喜欢这个节奏"但 scene_plan 的场景长度翻倍 → **SUGGESTION**
   - 用户说"保持钩子风格"但脚本用了不同钩子 → **SUGGESTION**

4. **费用对齐：** 费用估算是否仍准确，还是范围蔓延了？
   - 实际支出超过估算 >30% 且未经用户重新批准 → **CRITICAL**
   - 在已批准提案之外新增了素材 → **SUGGESTION**

### 严重级别：
- 关于参考视频的事实错误：**CRITICAL**
- 无差异化的碳拷贝：**CRITICAL**
- 弱差异化（仅表面改动）：**SUGGESTION**
- 用户偏好未被遵守：**SUGGESTION**
- 费用偏差 >30%：**CRITICAL**

## 幻灯片风险审查

在 **scene_plan** 和 **edit** 阶段运行。使用 `lib/slideshow_risk.py` 计算评分。

### scene_plan 阶段：
1. 计算 `score_slideshow_risk(scenes, renderer_family=renderer_family)`
2. 如果判定为 **"fail"**（平均 ≥ 4.0）：**CRITICAL** — 场景计划必须修改后才能继续
3. 如果判定为 **"revise"**（平均 ≥ 3.0）：**SUGGESTION** — 标记得分 ≥ 3.5 的具体维度
4. 如果判定为 **"strong"** 或 **"acceptable"**：在审查摘要中记录，无需发现

### edit 阶段：
1. 用完整 edit_decisions 重新计算：`score_slideshow_risk(scenes, edit_decisions, renderer_family)`
2. 相同阈值适用——如果 edit 阶段使情况恶化（评分高于 scene_plan），标记

### 各维度标记内容：
| 维度 | 得分 ≥ 3.0 时的说明 |
|------|---------------------|
| repetition | "X 个场景使用相同布局/景别——变化视觉语法" |
| decorative_visuals | "X 个场景没有明确目的（无 information_role 或 shot_intent）" |
| weak_motion | "有镜头运动但缺乏叙事依据" |
| weak_shot_intent | "X 个场景缺少 shot_intent——这个画面为什么存在？" |
| typography_overreliance | "X% 的场景是文字/数据卡——视频感觉像动画幻灯片" |
| unsupported_cinematic_claims | "声称电影感但缺少主视觉时刻/灯光/运动" |

## 决策日志审查

在提案之后的**每个阶段**运行。决策日志（`schemas/artifacts/decision_log.schema.json`）是累积审计轨迹。

### 检查项：
1. **存在性**：检查点是否引用了 `decision_log_ref`？提案阶段后仍未引用，标记为 **SUGGESTION**。
2. **覆盖度**：每个重大选择是否都有条目？必须记录的决策：
   - 提供商选择（哪个图片/视频/音频工具及原因）
   - 风格/playbook 选择
   - 音乐曲目选择
   - 语音选择
   - 渲染器族选择
   - 任何回退或降级（如动态 → 静态）
3. **质量**：每条决策应包含：
   - 至少 2 个 `options_considered`（不只是选中的那个）
   - 非套话的 `reason`（"最佳选项"不是理由）
   - 正确的 `confidence`（0.0–1.0）——如果全是 1.0 则标记（不现实）
4. **用户可见性**：标记 `user_visible: true` 的决策应该是用户真正关心的（不是内部路由）

### 严重级别：
- 提案后缺失决策日志：**SUGGESTION**（首次），**CRITICAL**（edit 阶段仍缺失）
- 只考虑了 1 个选项的决策：**SUGGESTION** — "记录被拒绝的替代方案以供审计"
- 所有决策置信度都是 1.0：**SUGGESTION** — "置信度不现实——至少提供商选择涉及权衡"

## 创意差异化审查

在 **scene_plan** 和 **edit** 阶段运行。防止"每条视频看起来都一样"的失败模式。

### 检查项：
1. **变化检查**（仅 scene_plan）：使用 `lib/variation_checker.py` → `check_scene_variation(scenes)`。
   - 判定为 "poor"（评分 ≤ 2）：**CRITICAL** — "场景计划缺乏多样性：[列出违规]"
   - 判定为 "fair"（评分 ≤ 3）：**SUGGESTION** — 记录检查器给出的具体建议

2. **Playbook 对齐**：活跃 playbook 是否适合此内容？
   - 电影感预告片用"clean-professional"主题 → 标记不匹配
   - 教育解说用"anime-ghibli"主题且用户未要求 → 标记

3. **镜头语言完整性**（scene_plan）：
   - 每个场景至少应有 `shot_size` 和 `shot_intent`
   - 主视觉时刻应有完整 shot_language（全部 6 个字段）
   - shot_language 为空的场景标记为 **SUGGESTION**

4. **渲染器族匹配**（edit 阶段）：
   - edit_decisions 中的 `renderer_family` 是否与提案时设置的一致？
   - 无决策日志记录原因就变更 → **CRITICAL**

5. **渲染运行时匹配**（edit 和 compose 阶段）：
   - edit_decisions 中的 `render_runtime` 必须匹配 proposal_packet.production_plan.render_runtime
   - 无 decision_log 中的 `render_runtime_selection` 决策就变更 → **CRITICAL**
   - compose 阶段 `final_review.checks.promise_preservation.runtime_swap_detected` 必须为 `false`。若为 `true` 且无已批准的 `render_runtime_selection` 决策 → **CRITICAL**
   - compose 时运行时不可用不是静默切换的借口——正确做法是升级、获批准、记录决策，再运行。

6. **运行时选择展示了两个选项**（提案阶段，强制）：
   - 查询 `video_compose.get_info()["render_engines"]`。如果 `remotion` 和 `hyperframes` 都显示 `True`，`decision_log` 中的 `render_runtime_selection` 决策必须在 `options_considered` 中包含两个运行时。
   - 两个运行时都可用时，`options_considered` 只列一个 → **CRITICAL**。Agent 静默默认了；用户未被展示替代方案。重新打开提案阶段，展示两者。
   - 如果只有一个运行时可用，`options_considered` 仍须列出不可用的那个并附 `rejected_because: "runtime not available on this machine"`——否则审计轨迹丢失了"选择是受限的而非自主的"这一事实。
   - 按 AGENT_GUIDE.md > "Present Both Composition Runtimes (HARD RULE)"：管线建议的"默认"运行时不是跳过与用户对话的许可证。

## 交付承诺审查

在 **edit** 和 **compose** 阶段运行。使用 `lib/delivery_promise.py`。

### edit 阶段：
1. 从提案包或 edit_decisions 元数据中提取交付承诺
2. 对解析后的剪辑列表运行 `promise.validate_cuts(cuts)`
3. 如果 `valid` 为 False：**CRITICAL** — "交付承诺违规：[违规列表]"
4. 检查 `motion_ratio`：运动主导的承诺如果运动剪辑 < 50%，即使技术上有效也要标记

### compose 阶段：
1. video_compose.py 中的 `_pre_compose_validation()` 自动执行此检查
2. 审查应验证校验未被绕过（检查渲染报告中的警告）
3. 如果运动主导的承诺在低运动比下渲染成功，标记为 **SUGGESTION**

## 源素材理解审查

当存在用户提供的媒体文件时，在 **research** 和 **proposal** 阶段运行。

### 检查项：
1. **存在性**：如果项目收到了用户提供的文件，是否存在 `source_media_review` 产物？
   - 有用户媒体但无 `source_media_review`：**CRITICAL** — "用户提供了媒体但 agent 在规划前未检查。先运行 `lib/source_media_review.review_source_media()`。"
2. **实际检查**：每个文件条目是否有 `reviewed: true` 和非空 `technical_probe`？
   - 缺少 `reviewed` 或 `technical_probe` 为空：**CRITICAL** — "source_media_review 声称已审查但无探测数据。文件未被实际检查。"
3. **规划反映**：`planning_implications` 是否出现在提案的制作计划中？
   - 如果识别出质量风险（如低分辨率、单声道音频）但提案未提及：**SUGGESTION** — "源素材存在质量风险，提案未涉及。"
4. **内容准确性**：计划是否依赖源素材实际不包含的内容？
   - 如计划假设有采访对话但 transcript_summary 显示无语音：**CRITICAL** — "计划假设有对话但源素材不含语音。"
5. **无臆造内容**：Agent 不得仅凭文件名推断不支持的内容。如果 `content_summary` 写"采访素材"但探测只显示 3 秒无声视频，标记为 **CRITICAL**。

### 严重级别：
- 用户文件存在时缺失 `source_media_review`：提案阶段 **CRITICAL**
- 未审查的文件（无探测）：**CRITICAL**
- 计划未反映质量风险：**SUGGESTION**
- 计划假设源中不存在的内容：**CRITICAL**

## 最终自审审查

在 **compose** 和 **publish** 阶段运行。确保 agent 审查了实际渲染输出。

### compose 阶段：
1. **存在性**：`render_report` 旁边是否有 `final_review` 产物？
   - 缺失：**CRITICAL** — "compose 产出了 render_report 但没有 final_review。Agent 必须在呈现前检查渲染输出。"
2. **状态检查**：`final_review.status` 是什么？
   - `pass` → OK，继续
   - `revise` → Agent 应在呈现前修复问题。如果管线仍继续：**CRITICAL** — "自审发现需要修订的问题但 agent 仍然呈现了。"
   - `fail` → 管线不得继续。如果继续了：**CRITICAL**
3. **检查完整性**：全部 5 项必需检查必须有数据：
   - `technical_probe` 必须显示有效容器和合理时长/分辨率
   - `visual_spotcheck` 必须有 `frames_sampled >= 4`
   - `audio_spotcheck` 必须报告旁白/音乐存在情况
   - `promise_preservation` 必须确认 `delivery_promise_honored`
   - `subtitle_check` 必须报告存在/缺失
   - 任何检查数据缺失：**SUGGESTION** — "自审检查 [X] 数据不完整"
4. **承诺保持**：如果 `promise_preservation.silent_downgrade_detected` 为 true：**CRITICAL** — "自审检测到从运动主导到静态主导的静默降级。"

### publish 阶段：
1. 验证 `final_review` 作为必需产物被传递
2. 如果 `final_review.status` 不是 `pass`：**CRITICAL** — "自审未通过不得发布"
3. 如果 `final_review.issues_found` 非空且 `recommended_action` 不是 `present_to_user`：**SUGGESTION** — "自审发现问题；发布前确认已解决"

## 合成创作模式审查

模板化→工坊级的反转（`AGENT_GUIDE.md` → "Composition Authoring Mode" + `skills/meta/bespoke-composition.md`）是治理，不是建议。审查者是执行点：没有这些检查，下一个 agent 会悄悄退回标准剪辑 schema，每条视频又开始看起来一样。

### 提案阶段：
1. `decision_log` 必须包含 `composition_mode` 决策，`options_considered: ["templated","atelier"]` 和与简报挂钩的真实原因的 `selected` 值。
   - 完全缺失 `composition_mode` 决策：**CRITICAL** — "提案缺少 composition_mode 选择。工坊级 vs 模板化是强制展示的决策（参见 AGENT_GUIDE.md → Composition Authoring Mode）。"
   - 只考虑一个选项的决策：**CRITICAL** — "composition_mode 决策未展示模板化和工坊级两个替代方案。"
2. 对于**主视觉工作**（简报标记为营销/发布/品牌片/有质量门槛的解说/任何质量即目的的单次交付）且 `selected == "templated"`：**CRITICAL** — "主视觉简报锁定了 composition_mode='templated'。按原则默认是工坊级；模板化需要在 `decision_log.<entry>.reason` 中有明确理由（如本地化变体、批量、限时草稿）。" 仅当理由字段指明受认可的例外时才抑制。
3. 如果 `composition_mode == "atelier"` 且 `proposal_packet` 缺少 `art_direction` 声明（调色板、字体、运动、签名装置）：**CRITICAL** — "工坊级提案缺少艺术方向承诺。按 `skills/meta/bespoke-composition.md` 第 1 步，艺术方向必须在编写场景*之前*写下来。"

### scene_plan / edit 阶段（当 composition_mode == "atelier" 时）：
1. `edit_decisions.composition_mode` 必须等于 `"atelier"`，且 `edit_decisions.bespoke.{entry, composition_id, art_direction}` 必须全部设置。
   - 缺少 `entry`/`composition_id` 中任一项：**CRITICAL** — "工坊级合成契约不完整；渲染将被 `_render_via_atelier` 拒绝。"
   - 缺少 `art_direction`：**CRITICAL** — "工坊级无艺术方向声明；审查者无法评估独特性。"
2. `edit_decisions.cuts` 中出现任何标准 `cut.type` 场景类型（`text_card`、`stat_card`、`bar_chart`、`kpi_grid`、`callout`、`comparison`、`hero_title`、`terminal_scene`、`anime_scene`、`progress_bar`、`pie_chart`、`line_chart`）：**CRITICAL** — "工坊级作品引用了标准 cut.type {name}。手工编写场景；标准注册表是机制法典，不是零件箱（`skills/meta/bespoke-composition.md`）。"

### compose 阶段（当 composition_mode == "atelier" 时）：
1. compose 阶段的 `final_review.checks.atelier` 块必须存在。缺失：**CRITICAL** — "工坊级渲染跳过了原则检查——`_render_via_atelier` 返回时没有 `atelier` 检查；排查工具接线。"
2. 如果 `final_review.checks.atelier.stock_reuse_detected == true`：**CRITICAL** — "工坊级项目内导入了标准注册表（{offending_imports[0].file} → {offending_imports[0].import}）。手工编写场景；不要从标准 src/ 导入。"
3. 如果 `final_review.checks.atelier.art_direction_declared == false`：**CRITICAL** — "工坊级渲染无艺术方向声明。重新渲染前设置 `edit_decisions.bespoke.art_direction`。"
4. **场景独特性——无主视觉组件脊柱（强制记录）。** 每个场景采样一帧代表帧（如每个 `props.sections[i]` 的中间窗口），在审查记录中回答：
   - *每个场景是否有独特的主要视觉主体？* 如果两个或更多场景共享主要视觉（同一个主元素仅换字幕——不离开的蜡烛、每一拍都出现的浏览器框、作为脚手架的评分环）：**CRITICAL** — "检测到主视觉组件脊柱：场景 {ids} 共享主要视觉主体。按 `skills/meta/bespoke-composition.md` 第 1.5 步，每个场景必须有自己的构图；签名装置属于一个高潮节拍，不是脚手架。重新规划受影响场景。"
   - *`art_direction` 中命名的签名装置是否至少在一个节拍中出现？*（否 ⇒ CRITICAL，重新编写或更新声明以匹配实际构建的内容）
   - *签名装置是否出现在**大多数**节拍中？*（是 ⇒ CRITICAL——见上方主视觉组件脊柱；签名应该是稀缺的）
   此检查不能静默跳过；缺少逐场景清单记录本身就是 **CRITICAL**（"scene_distinctness 清单未记录"）。
5. **字幕/屏幕文字去重（强制检查）。** 将活跃字幕文本与同一时间窗口内渲染的任何屏幕文字比较：
   - 如果内容相同（字幕重复了场景标题/旁白已在朗读的标题）：**CRITICAL** — "字幕在 {t}s 重复屏幕文字（'{text}'）。每条作品决定一次：字幕是增加意义（数字、名称、翻译）还是无障碍字幕；不要对同一行两者都做。要么清除这些场景的 `captions=[]`，要么移除冗余的屏幕 SerifLine。"
6. **独特性审查（人工判断，强制）。** 批准渲染前，审查者必须在审查记录中明确回答：
   - *"这条视频可能是其他任何产品的视频吗？"*（是 ⇒ CRITICAL，重新编写艺术方向）
   - *"它的视觉语言是否复用了我之前作品的外观？"*（是 ⇒ CRITICAL，重新编写）
   独特性是工具无法自动化的品味判断领域；审查者未回答此问题本身就是 **CRITICAL** 发现（"distinctness review 未记录"）。

### publish 阶段（当 composition_mode == "atelier" 时）：
1. 上述全部六项工坊级 compose 阶段检查（`atelier` 块存在性、stock_reuse、art_direction_declared、scene_distinctness、字幕/文字去重、人工独特性审查）必须在审查记录中显示 `resolved`。任何未解决：**CRITICAL** — "工坊级作品存在未解决的原则或独特性发现，不得发布。"
