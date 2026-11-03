# 存档笔记：elayadesign/ai-design-skills

- 它是什么：给 AI 编程工具（Claude Code、Cursor、Codex、Windsurf 等）用的设计 skill 合集；每个 skill 一个自包含文件夹，内含标准 SKILL.md（YAML frontmatter 的 name/description 齐全）。
- 包含的 skill（2 个）：
  - `landing-page-design`：从零搭建高转化落地页的完整系统——需求访谈、页面结构、转化文案、SEO，以及排版、间距、圆角、背景、Hero 布局、图标与动效的严格视觉规则。内容现实主义与动效思路改编自 Leonxlnx/taste-skill（MIT，详见该 SKILL.md 末尾 Credits）。
  - `design-to-motion`：把静态设计（Figma 帧、看板、卡片、应用界面）还原为像素级精确的 HTML 复刻并做成循环展示动画（空状态载入→每个视觉元素演绎其故事→无缝循环），导出 MP4 与 GIF。部分通用动效规则改编自 emilkowalski/skills、Owl-Listener/designer-skills、dylantarre/animation-principles（均为 MIT，详见该 SKILL.md 末尾 Credits）。
- 上游版本：commit a2735a3eaf092eaaffb6dc17df25de33ef3bd048（2026-10-26）；star 6402、fork 458（GitHub API 2026-10-26 实测）。
- 许可证：MIT（LICENSE 原件保留，Copyright (c) 2026 Elaya；README 称无需署名）。
- 存了什么：本目录为整仓原件（LICENSE、README.md、.gitignore、skills/ 下 2 个 SKILL.md，共 5 个文件，约 224KB，无单个 >50MB 文件、无排除项）。
- 技能库收录：2 个 skill 全部按原件收录（SKILL.md 逐字节一致，sha256 已核对；frontmatter 自带 name/description，无需修补），目录名加 elayadesign- 前缀，双落点（drama-factory/src/main/resources/skills-bundled/ 与 skill/ 镜像），双索引登记（id：elayadesign-landing-page-design、elayadesign-design-to-motion，rewritten=false，license=MIT），每目录附上游 LICENSE 全文。收录后主索引 1373 → 1375、镜像索引 1361 → 1363。
- 备注（既存差异，与本轮无关）：收录前主索引（1373）与镜像索引（1361）已有 12 条差额——12 个 drama-skills-short-drama-* 条目只在主索引，未同步进镜像；本轮未动这 12 条。
- 另：README 提到的 elayadesign/redesign-skill（升级现有站点）是独立仓库，不在本仓内，本轮未收录。
