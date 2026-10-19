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
