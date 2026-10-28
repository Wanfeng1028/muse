# 发版对照报告：短信记录接口参数范围收紧（v0.33.1）

## 变更

- `GET /api/sms/log`：limit 小于 1 或大于 1000 返回 400；offset 小于 0 返回 400。缺省仍 limit=50、offset=0。
- 仅改 `internal/handlers/handlers.go` 的 `handleSMSLogAPI`；新增 `internal/handlers/sms_log_range_validation_test.go`；CHANGELOG 记 [0.33.1]。
- 无 schema 变更、无新环境变量、无 UI 改动。

## 对照（按仓库统一 Definition of Done）

- 可靠性：通过。新增测试 7 子用例全绿；handlers 全包通过；失败路径复用既有 `writeErr` 文案；Store 层改写逻辑保留作防御。
- 可观测性：通过。400 响应沿用既有 error 字段（limit/offset 参数非法），无需新指标。
- 数据与状态：通过。无 schema 变更；冒烟用隔离库，未写仓库 data/backups。
- 部署与运维：通过。无新配置；Docker/Compose 与运维手册无需改动。
- 安全与健壮性：通过。本次即输入校验收紧；鉴权中间件未动，冒烟复核无鉴权 401。
- 可维护性：通过。CHANGELOG 已记；行为变更点与未改口径的对照（统计 days 钳制、投递 limit 钳制有既有测试锁定为 200，本轮不改）已写入 CHANGELOG。
- 视觉验收：不适用。无 UI 改动。
- 全量测试：通过。`go test ./...` 16 包全绿（notify 包 238.6 秒为既存最慢包），exit=0。

## 已知限制

- 本轮只收紧短信记录接口一处；其他接口的钳制行为凡有既有测试锁定的，一律维持原合同，未做统一收口。
- 全量测试结论待后台任务返回后补记；commit 前须以该日志为准。
