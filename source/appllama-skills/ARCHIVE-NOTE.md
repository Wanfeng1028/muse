# ARCHIVE-NOTE — Appllama/appllama-skills

- 来源：https://github.com/Appllama/appllama-skills（X 帖子 @jaimintf 2026-10-27《reverse engineer any ios app.》中作者列出的第 1 项 "app design"）
- 归档日期：2026-10-27
- 上游 commit：dd5caae（main）
- 许可证：MIT（LICENSE 原件保留在本目录）
- 文件数：18（含本说明；无 >50MB 文件，无排除项）
- 内容：移动应用设计 skill 库，口号 "A builder, not just a researcher"——把头部赚钱 App 的真实界面、导航与模式转成原生品质的移动端屏幕。含 2 个 skill：
  - `skills/appllama-app-design-skill/`：对标真实 App 的屏幕构建，Apple HIG 保真、语义 token、反 AI 味、严格动效标准、模拟器全流程录制逐帧检查；附 references（image-assets / motion / native-controls / performance / simulator-loop）
  - `skills/appllama-usage/`：Appllama MCP（mcp.appllama.io）用法，研究真实头部 App 后再构建
  - 另有 `.claude-plugin/`、`.cursor-plugin/`、`.mcp.json`、`mcp.json` 插件配置
- 技能入库：2 个 skill 原文收进剧坊技能库（appllama-app-design-skill、appllama-usage），正文字节一致，LICENSE 已附；主索引与镜像同步更新。
- 与剧坊/BotsTalk 的关系：appllama-app-design-skill 的"模拟器录制逐帧检查 + 反 AI 味"与剧坊质量门思路同源，可作移动端 UI 评审参考；MCP 研究引擎本身不接入（需外部服务账号），故只归档 + 入库，不做集成。
- 注意：本目录已剔除上游 .git；内容为公开原文存档，许可证与出处保留。
