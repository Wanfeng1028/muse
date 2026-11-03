# ARCHIVE-NOTE — expo/skills

- 来源：https://github.com/expo/skills（X 帖子 @jaimintf 2026-10-27《reverse engineer any ios app.》中作者列出的第 2 项 "best practices"）
- 归档日期：2026-10-27
- 上游 commit：8a0dc4f（main）
- 许可证：MIT（LICENSE 原件保留在本目录；plugins/expo/LICENSE 与根 LICENSE 内容一致）
- 文件数：184（含本说明；无 >50MB 文件，无排除项）
- 内容：Expo 官方 skill 库，覆盖 Expo 项目与 Expo Application Services（EAS）全流程。含 25 个 skill：
  - `plugins/expo/skills/`（23 个）：eas-app-stores、eas-hosting、eas-observe、eas-simulator、eas-update、eas-update-insights、eas-workflows、expo-animation、expo-app-clip、expo-brownfield、expo-data-fetching、expo-design-system、expo-dev-client、expo-dom、expo-examples、expo-module、expo-native-ui、expo-overview、expo-project-structure、expo-router、expo-ui、expo-upgrade、expo-web-to-native
  - `plugins/expo-experiments/skills/`（1 个）：expo-migrate-module
  - `.claude/skills/`（1 个）：expo-skill-eval（含 scripts 评估 harness）
  - 另有插件配置（marketplace.json、plugin.json、mcp.json）、AGENTS.md、CLAUDE.md、CONTRIBUTING.md
- 技能入库：25 个 skill 原文收进剧坊技能库（id 前缀 expo-），正文字节一致，LICENSE 已附；主索引与镜像同步更新。
- 与剧坊/BotsTalk 的关系：Expo/React Native 是移动端落地路线之一，expo-design-system、expo-native-ui、expo-animation 与剧坊"代码渲染 + 动效"方向可对照参考；本轮只归档 + 入库，不接入 Expo 构建链（剧坊主栈是 Java + Web，不硬塞）。
- 注意：`eval-harness/` 是上游 git submodule（指向 expo/eval-experiments），clone 时未初始化，本目录中为空目录，仅保留占位；内容为公开原文存档，许可证与出处保留；本目录已剔除上游 .git。
