# InkOS 存档与集成笔记（2026-10-24）

## 它是什么

- **InkOS**（Narcooo/inkos）：Story Creation AI Agent——面向长短篇小说、剧本剧作、互动影游、IP 内容与多语言翻译的创作智能体系统，支持 Studio / TUI / CLI 三种交互。
- 技术栈：TypeScript pnpm monorepo（packages/cli、packages/core、packages/studio），Node ≥ 22.16；v2.0.0 开发状态（统一 Pi Agent Harness + 专业创作内核）。
- 规模：10,494 star / 1,929 fork（2026-10-24 经 gh 实测）；上游活跃（存档前一日仍在推送）。
- 存档版本：上游 commit `56aa33b0`（fix(docs): point KK MCP links to the live connection guide）。
- **许可证：AGPL-3.0-only**（LICENSE 原件随仓存档）。

## 存档内容

- 整仓原件复制（不含 .git）：**793 个文件、约 19MB**，与上游文件清单逐名比对一致。
- 无单个 >50MB 文件，**无排除项**；LICENSE、README（中/英/日）等文档原件齐全。
- 云盘另存正式存档包一份：`inkos-source-20261024.tar.gz`（Google Drive「02项目/Muse」文件夹）。

## 本轮集成（已落地）

InkOS 在 `packages/core/skills/` 内置 20 个专业 Skill（标准 SKILL.md + references），与剧坊（drama-factory）的短剧/剧本/分镜生产直接相关，已按原件收录进剧坊官方技能库：

- 落点：`drama-factory/src/main/resources/skills-bundled/`（整文件夹原件；另按技能库合规惯例在每个文件夹内附上游 LICENSE 全文，合规测试 SkillLicenseComplianceTest 要求非重写 skill 必须自带 LICENSE）+ `_index.json` 登记；`muse-repo/skill/` 镜像同步。技能库总数 1282 → **1302**；技能相关测试 34/34 全绿（SkillRegistry / IndexDeepR2 / SkillInstallService / LicenseCompliance / ReferenceIntegrity / OpenmontageIngest）。
- 登记口径：license=AGPL-3.0、source=Narcooo/inkos、rewritten=false（原件未改）。
- 与剧坊最相关的几个：`inkos-script-writing`（小说/大纲→可演剧本、竖屏短剧）、`inkos-storyboard`（叙事文本→可拍可生图分镜）、`inkos-story-review`（审稿）、`inkos-story-deslop`（去 AI 味）、`inkos-interactive-film`、`inkos-short-writing`、`inkos-story-import`（拆稿导入）、`inkos-translation`；其余长篇/同人/番外/续写/仿写/市场研究/Play 世界/封面等一并收录。
- 仓根 `skills/SKILL.md` 是供外部 Agent 调用 InkOS CLI 的封装 skill，属工具封装而非内容技能，本轮未收录进技能库（原件随整仓存档保留）。

## 本轮不集成（及理由）

- InkOS 的 Pi Agent Harness、Studio、CLI 本体是 TypeScript 实现，剧坊为 Java/Spring Boot 栈，整仓移植不成立、也不符合「只借功能与信息架构」的既定纪律；本轮只收录可直接复用的 Skill 原件。
- 留作后续候选的设计借鉴（只记结论，未动代码）：
  1. **安全章节工作区**：正文/状态/伏笔先在工作区校验再原子提交，避免「状态推进、正文未落盘」——可对照剧坊的 Run/分集落盘一致性。
  2. **剧情多线推演（forecast）**：写下一章前生成 2–5 条隔离分支供横向比较，采纳只落候选计划不改正史——可借鉴到剧坊的剧本/分镜方案对比。
  3. **统一检索层**：故事记忆/材料库/Skill 参考共用 SQLite FTS5 BM25 投影、原文为权威源、索引可重建——与剧坊提示词库/素材检索方向一致。
  4. **上下文分层**：protected / compressible 分层组织长篇上下文，防长书失控。
