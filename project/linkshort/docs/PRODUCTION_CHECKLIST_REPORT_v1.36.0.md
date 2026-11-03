# linkshort v1.36.0 生产就绪检查清单报告

本轮仅收紧 `GET /api/stats/geo.csv` 的 `link_id` 参数校验，无破坏性变更，不改变现有合法调用行为。

## 可靠性

非法 `link_id`（非整数字符串）在查询前拦截，返回 400，避免静默按全局 0 导出错误数据。缺省或空串仍默认 0，负数仍钳制为 0，既有合法行为保持不变。

## 可观测性

非法 `link_id` 返回明确 HTTP 400 与 JSON 错误体 `{"error": "link_id 非法"}`，便于调用方与监控快速定位参数问题，不再静默成功但内容不符预期。

## 数据与状态

无数据库迁移，无新增外部依赖，无持久化状态变更。仅修改 `handleExportGeoCSV` 中的参数解析逻辑，不影响现有数据读写。

## 部署运维

无新增端点，无 UI 改动，无配置变更。视觉验收不适用。现有部署流程不变，升级仅需替换二进制或镜像。

## 安全与健壮性

`link_id` 校验与 v1.34.0 的 geo JSON 端点同款，消除两个端点间口径漂移，提升参数处理一致性与健壮性。

## 可维护性

CHANGELOG 顶条已同步为 v1.36.0，明确记录本次变更范围与行为。`days` 参数口径锁定（非数字回落 30、仅 7/30 有效），本轮不触碰，避免未来误改。

## 测试与冒烟

- 新增 `internal/handler/stats_geo_csv_linkid_validation_test.go`，函数名 TestStatsGeoCSVLinkIDValidation，覆盖 7 例：`link_id=abc`、`1.5`、`1x` 返回 400 且体含“link_id 非法”；不带参数、`link_id=-5`、`link_id=1` 返回 200；`days=abc` 返回 200。
- 既有 geo/geo.csv 测试不受影响（HeaderAndRowCount、NoData_HeaderOnly、DaysInvalid_FallsBackTo30、geo JSON link_id 校验均通过）；全量 `go test ./...` 14 包全过；`go vet` 全洁；改动文件 `gofmt` 全洁。
- 真实服务冒烟（18484 端口 `:memory:` 库）：无 key 返回 401；`link_id=abc`、`1.5`、`1x` 均返回错误体逐字为 `{"error": "link_id 非法"}`；`link_id=-5` 与不带参数均返回 200 且体为 CSV 表头；`days=abc` 返回 200；冒烟后服务已停、端口已关、冒烟二进制已删。

## 结论

靶向范围测试通过，全量 14 包测试通过，生产就绪检查清单通过。
