# Toonflow Skills 重写收录质量复审报告

- 报告日期：2026-10-20
- 审计对象：skills-bundled 中 toonflow-canvas、toonflow-workflow、toonflow-v118workflow 三个 skill
- 审计性质：二阶段"3 组 skills 重写收录"质量复审
- 数据来源：2026-10-20 编排侧实测（difflib SequenceMatcher 相似度比对、字节统计、目录合规检查），非模型记忆

## 审计方法

- 相似度算法：difflib SequenceMatcher，比对上游 raw.githubusercontent.com/HBAI-Ltd/Toonflow-app/master/packages/skills/{canvas,workflow,v118workflow}/SKILL.md 与本地 skills-bundled 对应文件，双方均已 strip frontmatter。
- 数据源：上游 GitHub 仓库 HBAI-Ltd/Toonflow-app master 分支 packages/skills 下的三个 SKILL.md 原文，以及本地 skills-bundled 对应文件。
- 合规检查项：逐目录检查是否存在 LICENSE 文件。
- 合规检查项：核对上游仓库 LICENSE 许可类型与版权归属。
- 合规检查项：核对 _index.json 中 3 条目的 rewritten 字段与 rewriteNote 文本。
- 结构核查项：读取三个 SKILL.md 真实文件，记录标题层级结构。

## 核心发现

3 个 skill 与上游原文相似度 0.911–0.982，实质为近乎原文收录，_index.json 中 rewritten:true + rewriteNote"独立重写，未复制原文"的标注失实。

逐组实测数据如下：

- toonflow-canvas：本地 9040 字节 / 上游 8933 字节，相似度 0.982。
- toonflow-workflow：本地 35562 字节 / 上游 39217 字节，相似度 0.938。
- toonflow-v118workflow：本地 5063 字节 / 上游 4759 字节，相似度 0.911。

_index.json 现状：3 条目均为 rewritten:true，rewriteNote 均为"独立重写，未复制原文"（canvas 条目原文："改写自 HBAI-Ltd/Toonflow-app packages/skills/canvas：功能对齐，SKILL.md 为独立重写，未复制原文"）。

合规现状：3 个 skill 目录均无 LICENSE 文件；上游 Toonflow-app 为 MIT 许可（Copyright (c) 2026 HBAI-Ltd），已从上游抓取 LICENSE 全文待补入。

用户政策（2026-10-19 亲定）："能直接拿的直接拿，不能直接拿的抄 95%——dpsk 照功能重写我们自己的实现，不逐字复制"。据此政策，近乎原文收录本身在"能直接拿"范围内可接受，但必须如实标注来源与许可，不得标为"独立重写，未复制原文"。当前标注与实测相似度直接矛盾，属标注失实，须纠正。

## 合规处置（已执行）

1. 3 个目录补入上游 MIT LICENSE 全文（Copyright (c) 2026 HBAI-Ltd），与 SKILL_AUDIT_2026-10-19.md 问题 1 同口径处理。
2. _index.json 的 rewritten 改为 false，rewriteNote 改为"与上游原文相似度 91%-98%（2026-10-20 difflib 实测），按近乎原文收录，已补上游 MIT LICENSE"。
3. 后续真正独立重写完成并复测相似度达标后，再将 rewritten 改回 true。

## 内容质量复审

- 结构完整度：通过。toonflow-canvas 含"# 画布操作手册"及操作流程/读取画布/画布管理/节点与连线（含### 参数约束/连接规则）/调用节点函数/常见任务（含 5 个### 任务）/失败后的处理，章节齐全；toonflow-workflow 含"# Toonflow 画布制作工作流"及从哪里开始（含### Seedance 路由锁存 最高优先级入口规则/### Seedance 阶段硬隔离）、Seedance 提示词生成的内嵌执行核心、# PART A 执行规则、A0 输入判定（含 A0.1 剧情保真锁 最高优先级 及 6 个#### 子节）、A1 输出语言与资产命名（含 A1.1/A1.2/A1.2.1 Seedance 2.5 参考图片绑定/A1.3）、A2 全量节拍解析与顺序保持，章节齐全；toonflow-v118workflow 含"# v1.1.8 分集制作流程"及先定位进度与画布/主流程与确认关口/知识如何随流程使用/每一步如何确认/续作、修改与失败，章节齐全。
- 与上游功能对齐：通过。三组相似度 0.911–0.982，高相似度本身即功能对齐的直接证据，未发现偏离上游功能范围的改写。
- 术语一致性：通过。三个文件内部中文术语统一（画布、节点、连线、节拍、路由锁存、阶段硬隔离、剧情保真锁等用法前后一致）。
- 可执行性：未验证。未实际跑通画布工具调用，无法确认 SKILL.md 中描述的操作流程在运行时可用。

## 补强建议

1. 真正独立重写时先改 workflow 的 PART A 规则表述，将该节从上游句式彻底改写为自有实现描述，作为拉低整体相似度的首要切入点。
2. 给 canvas 补 references/videoProduction.md 真实存在性校验，确保 SKILL.md 引用的附属文件在包内实际存在且路径正确。
3. v118workflow 补版本迁移说明，交代 v1.1.8 相对上游版本的差异与迁移注意点，避免使用者直接套用上游旧流程。

## DoD 小结

- 许可证合规：通过（已补 LICENSE）。3 个目录均已补入上游 MIT LICENSE 全文。
- 标注真实性：通过（已纠正）。_index.json 的 rewritten 已改为 false，rewriteNote 已改为如实描述相似度与许可状态。
- 独立重写：未通过（相似度 0.91+，排期重做）。三组实测相似度 0.911–0.982，不满足"独立重写"定义，需排期重做后复测。
- 功能验证：未验证。未实际跑通画布工具调用，可执行性待运行时验证。
- 内容质量复审（结构完整度）：通过。
- 内容质量复审（与上游功能对齐）：通过。
- 内容质量复审（术语一致性）：通过。
- 内容质量复审（可执行性）：未验证。
- 补强建议跟踪：不适用（建议项已列出，待排期执行）。

## 2026-10-22 增补：重写可行性验证与 references 附属文件补齐

### 一、TD-001 独立重写可行性验证（2026-10-22）

执行方：助理编排 + step193plan 模型，共 5 次尝试。

1. toonflow-canvas 全文重写：difflib 相似度 0.8929，且输出含"略"占位符（有丢内容嫌疑），拒收。
2. toonflow-canvas 加严重写（加"不许连续 6 字相同、表格重写"等硬约束）：模型调用 274 秒后返回空输出，失败。
3. toonflow-workflow 头部切片重写：相似度 0.8759，拒收。
4. toonflow-v118workflow 重写：模型陷入"改为：## 主流程与确认关口"无限重复循环，输出 3 万字符垃圾，拒收。
5. toonflow-v118workflow 换"全新撰写"框架重写：相似度 0.8768，且 6 个章节丢了 5 个（标题改得无法对应），拒收。

**结论**：现有免费模型对这类 API 手册型文档做相似度 <0.5 的独立重写不可达，实测下限约 0.87-0.89；强行压相似度只会损伤文档质量（丢章节、造占位符、循环）。

**处置**：保留 rewritten=false + 上游 MIT LICENSE 的诚实标注状态（该状态本身符合 2026-10-19 用户政策"能直接拿的直接拿"，合规）；独立重写继续排期，待更强模型或人工介入后再做。

### 二、references 附属文件补齐

实测发现三个 skill 的 SKILL.md 引用的 references/*.md 附属文件在包内全部缺失：toonflow-canvas 缺 1 个（videoProduction.md）、toonflow-workflow 缺 8 个（含 methods/ 下 4 个）、toonflow-v118workflow 缺 22 个（含 knowledge/ 下 7 个），共 31 个。

已按用户"直接抄"政策（2026-10-20：skill/文档存原件）从上游 HBAI-Ltd/Toonflow-app 原样补入各 skill 的 references/ 目录。

补入后复测：workflow 15 处引用 0 悬空、v118workflow 26 处引用 0 悬空、canvas 5 处引用剩 2 处悬空（../script/references/assetGuide.md 与 productionGuide.md，这两处在上游原文里就悬空，上游没有 script 这个 skill，属上游继承问题）。

新增回归测试 SkillReferenceIntegrityTest.java（src/test/java/com/dramafactory/service/skill/）锁定三 skill 的引用完整性，2 处上游悬空链接在测试中列为已知例外。

### 三、DoD 小结更新

- **许可证合规**：通过（维持）。
- **标注真实性**：通过（维持）。
- **独立重写**：未通过，2026-10-22 已验证不可达，继续排期（待更强模型/人工）。
- **附属文件完整性**：通过（31 个文件已补齐 + 回归测试锁定）。
- **上游继承悬空链接**：2 处，已记录为例外。