
# Changelog

本文件格式遵循 Keep a Changelog。

## [Unreleased]

### Added
- 多对局聚合复盘：`AggregateAnalyzer` 跨 session 聚合常用路径 TopN / 抉择点分布 / 流失点；`AggregateMarkdown` 输出 Markdown 聚合报告；CLI `replay --aggregate`（多日志输入、`--out`，与 `--script` 互斥）；`AggregateAnalyzerTest` 新增测试。

- 玩家路径热力分析：`HeatmapAnalyzer` 对多份对局日志做 choice 节点访问频次聚合与流失点（高跳出 choice）识别；`HeatmapJson` 输出 JSON 报告（node_id/visits/drop_rate）；`HeatmapText` 渲染人类可读文本报告（Top 热门路径 / Top 流失点表格）；CLI 新增 `heatmap` 子命令（多日志输入、`--format text|json`、`--out`）。
- 热力分析测试 16 例（HeatmapTest 8 / HeatmapTextTest 8：空日志/单路径/环路/流失识别/阈值过滤/CLI）。
- 桌面端「热力分析」面板：`HeatmapPanel`（目录选择→`HeatmapLoader` 纯逻辑加载→Top 热门路径/节点热力/流失点展示，沿用 App 墨纸暖色视觉）；数据加载逻辑抽到 `replay.HeatmapLoader`（无 Compose 依赖，可直编单测），`HeatmapLoaderTest` 5 例。


- .bak 自动备份：`interlude-lint lint` 打开剧本前自动快照（时间戳后缀，保留最近 5 个、超出的删最旧）；新增 `restore` 子命令（`--list` 列出备份、`--index N` 恢复指定版本，恢复前自动备份当前工作文件）；备份/恢复事件记结构化日志（op=backup/restore，不含剧本正文）。
- 备份恢复测试 10 例（BackupTest）。
- 失败注入测试 7 例（FaultInjectionTest：目录/空文件 lint、备份丢失恢复、特殊文件名、负索引、同毫秒快照）。
- 失败注入测试套件 v1.3（FaultInjectionTest 扩至 19 例：损坏/截断剧本行号定位、不可读文件 exit 语义、tmpfs 磁盘满模拟、损坏备份拒绝恢复、10 万行性能回归、并发 lint 备份不互踩）。
- `lint` 对目录/特殊文件输入先校验类型再报错，不再先尝试 snapshot（修技术债）。

### Fixed

- `BackupManager.restore` 读取损坏备份失败时抛 IllegalArgumentException（CLI 返回 exit 2），不再让原始 IOException 崩出，且绝不覆盖原文件。

### Known limitations

- 桌面 UI 截图验收待正常 GUI 环境。
- Gradle daemon 在本沙箱不可用，验证走直编流程。

## [1.4] - 2026-10-16

### Added
- 复盘模式（replay）：对局事件模型（发言/进入场景/选择/投票/出局/关键标注/结束 7 种事件，选择事件记录"没选的路" alternatives）。
- 对局日志 JSON 解析器（手写递归下降，零依赖；错误定位到 events[i]）。
- 复盘报告分析器：抉择点提取 + 剧本场景富化（行号+原文引用）+ 引用缺失场景记 warnings 不崩 + 投票按轮分组 + 玩家统计（投出/被投/出局轮次）+ MVP 评选输入。
- Markdown 复盘报告生成器：时间线 / 抉择点复盘（含"没走的路"）/ 投票与出局 / MVP 评选表 / 关键标注 / 对局结果。
- CLI `replay` 子命令（`--script` 关联剧本做富化、`--out` 写文件，退出码 0/2）。
- 示例对局日志 `src/main/resources/replays/sample-session.json`（示例剧本真实走法 demo-001）。
- 复盘测试 47 例（SessionLogTest 16 / ReplayAnalyzerTest 16 / ReplayMarkdownTest 9 / ReplayCliTest 6）。

### Fixed
- 复盘 warnings 产生顺序：改为严格按事件时间线顺序（之前抉择点警告先于 SceneEnter 警告）。

### Known limitations
- 桌面 UI 截图验收待正常 GUI 环境。
- Gradle daemon 在本沙箱不可用，验证走直编流程。

## [1.1] - 2026-10-15

### Added

- 统一日志门面 `com.interlude.log`，人读 / JSON 双格式，输出到 stderr，带 `--log-level` 开关。
- 命令行校验工具 `interlude-lint`，退出码 0 / 1 / 2，报告支持 text / json。
- Report 报告格式化器。
- 端到端测试，覆盖示例剧本全链路 4 例。
- 运维手册 `docs/OPS.md`。
- `.github/dependabot.yml`，gradle 依赖每周检查。

### Changed

- 测试总数 28 / 28。

### Known limitations

- 桌面 UI 截图验收待正常 GUI 环境。
- Gradle daemon 在本沙箱不可用，验证走直编流程。

## [1] - 2026-10-13

### Added

- 叙事 DSL 解析器，行号精确报错。
- 5 条校验规则。
- 可视化分支图布局算法。
- 本地化文本抽取与回填。
- Compose 桌面 UI。
- 示例剧本 `src/main/resources/scripts/sample.interlude`。
