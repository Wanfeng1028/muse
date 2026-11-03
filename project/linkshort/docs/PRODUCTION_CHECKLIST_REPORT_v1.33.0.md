# linkshort v1.33.0 发版对照报告

## 改动摘要

本版仅涉及一个改动点：`GET /api/stats/hourly` 的 `days` 参数由 `parseIntDefault` 改为显式解析。

- 缺省或空串：默认 30。
- 非整数（如 `abc`、`1.5`）：返回 400，错误体逐字为 `{"error": "days 非法"}`。
- 合法整数但不在 1、7、30 中（如 `2`）：仍回落 30，返回 200。
- 改动范围仅限 `handleStatsHourly`。
- `geo`、`geo.csv` 的 `days` 口径与 `parseIntDefault` 一字未动。
- `docs.html` 与 `README` 均无 hourly 参数行，本轮不动。
- CHANGELOG 新增 `[v1.33.0]` 一节。
- linkshort 无代码内版本号，版本只记于 CHANGELOG 与本报告。

## 验收范围

| 验收项 | 范围与结果 |
| --- | --- |
| 靶向测试 | 新增 `internal/handler/stats_hourly_days_validation_test.go`（`TestStatsHourlyDaysValidation` 6 例）全绿；与既有 hourly/geo 边界测试合跑通过；`go vet` 全洁；改动文件 `gofmt` 全洁（handler 包内另有既存 gofmt 漂移文件，本轮未动）。 |
| 全量测试 | `go test ./... -count=1`，14 包全部通过（handler 包 17.114 秒）。 |
| 真实服务冒烟 | 18481 端口、`:memory:` 隔离库、X-API-Key 鉴权。`days=abc` 与 `1.5` 均 400 且错误体逐字为 `{"error": "days 非法"}`；不带 `days` 返回 200 且 `days=30`；`days=2` 返回 200 且 `days=30`；`days=7` 返回 200 且 `days=7`；无 key 返回 401；冒烟后服务已停、端口复查已关、冒烟二进制已删。 |
| UI视觉验收 | 本轮无 UI 改动，只改 API 参数校验，无页面结构或样式变化，视觉验收不适用。 |

## 对照表

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 可靠性 | 通过。参数非法路径由静默回落改为显式 400，行为边界明确且可预期。 | 靶向 6 例全绿；`days=abc`、`1.5` 冒烟均 400 且错误体逐字一致；`go test ./... -count=1` 14 包全通过。 |
| 可观测性 | 通过。非法入参有稳定、逐字可断言的错误体，便于日志与告警匹配。 | 冒烟实测错误体为 `{"error": "days 非法"}`；`days=2` 回落 30、`days=7` 生效，返回体 `days` 字段可核对。 |
| 数据 | 通过。本轮不改数据模型、不改查询口径，仅前置参数校验。 | `geo`、`geo.csv` 的 `days` 口径与 `parseIntDefault` 一字未动；仅改 `handleStatsHourly`；隔离 `:memory:` 库冒烟，无持久化副作用。 |
| 部署运维 | 通过。无新增配置项、无迁移、无端口与依赖变更。 | 冒烟在 18481 端口以 `:memory:` 隔离库完成，X-API-Key 鉴权生效；冒烟后服务已停、端口复查已关、冒烟二进制已删。 |
| 安全 | 通过。鉴权行为未变，非法输入不再进入业务计算路径。 | 无 key 冒烟返回 401；`days` 非整数返回 400，合法整数收敛至 1/7/30 三档，其余回落 30。 |
| 可维护性 | 通过。校验逻辑集中且测试随改动落地，代码规范检查通过。 | 新增 `stats_hourly_days_validation_test.go` 与既有 hourly/geo 边界测试合跑通过；`go vet` 全洁；改动文件 `gofmt` 全洁；CHANGELOG 新增 `[v1.33.0]`；版本仅记 CHANGELOG 与本报告。 |