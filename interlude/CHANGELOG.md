
# Changelog

本文件格式遵循 Keep a Changelog。

## [Unreleased]

### Added

- .bak 自动备份：`interlude-lint lint` 打开剧本前自动快照（时间戳后缀，保留最近 5 个、超出的删最旧）；新增 `restore` 子命令（`--list` 列出备份、`--index N` 恢复指定版本，恢复前自动备份当前工作文件）；备份/恢复事件记结构化日志（op=backup/restore，不含剧本正文）。
- 备份恢复测试 10 例（BackupTest）。
- 失败注入测试 7 例（FaultInjectionTest：目录/空文件 lint、备份丢失恢复、特殊文件名、负索引、同毫秒快照）。

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
