
# Changelog

本文件格式遵循 Keep a Changelog。

## [Unreleased]

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
