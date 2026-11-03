# 生产级 Checklist 对照报告：delivery limit 范围校验收紧

## 1. 改动概述
- 改动文件：`internal/handlers/delivery.go` 的 `handleListDeliveries`。
- 改动内容：删除 `limit` 小于 1 时置 1、大于 1000 时置 1000 的钳制逻辑；改为 `limit` 小于 1 或大于 1000 时返回 400，文案“limit 参数非法”。
- 未改动项：缺省 `limit=100`、非数字 `limit` 返回 400、`status` 白名单与文案、`monitor_id` 校验、Store 调用、响应体 `items/total`。

## 2. 测试证据
- 定向测试：`go test ./internal/handlers/ -run 'TestListDeliveriesDeep'` 全绿，包含新用例 `TestListDeliveriesDeepLimitOutOfRangeLow` 与 `TestListDeliveriesDeepLimitOutOfRangeHigh` 各 2 次 400 请求日志。
- 全包测试：`go test ./internal/handlers/ -count=1` 通过，结果 `ok`，耗时 11.185s。
- 静态检查：`go vet ./internal/handlers/` 全洁。
- 格式检查：gofmt 改动两文件全洁；另有 6 个既有文件未格式化，与本轮无关。
- 构建验证：`go build ./...` 通过。

## 3. 审查摘要
- open-code-review 委派审查：preview 的 reviewable 文件共 2 个。
- `delivery.go` 已审，无 High/Critical finding。
- `docseek/eval/run_eval_v09_parallel.py` 为并行工人文件，本轮跳过并注明原因。
- 测试文件按 OCR 默认规则排除，已由编排者人工复核 diff 并以测试执行验证。

## 4. 已知限制
- 未做真实服务冒烟。
- 未跑除 `handlers` 外的其他包测试。
- Store 层 `ListDeliveries` 自身钳制保留作防御，未改动。
- 仓库内静态前端 `deliveries.html` 只发 `limit=100`，不受影响。

## 5. 未变更清单
- 缺省 `limit=100` 行为未变。
- 非数字 `limit` 返回 400 未变。
- `status` 白名单与文案未变。
- `monitor_id` 校验未变。
- Store 调用与响应体 `items/total` 未变。
- Store 层 `ListDeliveries` 自身钳制保留。
- 静态前端 `deliveries.html` 未变。
- 无 schema 变更。
- 无版本号升级。
- 0.33.5 版“未变更”中“delivery limit 的 clamp 保持为 200 契约”一句自本轮起作废。

## 6. 发版对照
| 检查项 | 结果 | 理由 |
| --- | --- | --- |
| 代码改动明确 | 通过 | 仅改动 `limit` 钳制逻辑，未改其他行为 |
| 单元测试通过 | 通过 | 定向测试全绿，全包测试 ok，11.185s |
| 静态检查通过 | 通过 | `go vet ./internal/handlers/` 全洁 |
| 格式检查通过 | 通过 | 改动两文件 gofmt 全洁 |
| 构建通过 | 通过 | `go build ./...` 通过 |
| 代码审查通过 | 通过 | `delivery.go` 无 High/Critical finding |
| 视觉验收 | 不适用 | 无 UI 变更 |
| 未通过项 | 无 | 已知限制单独列出，不算未通过 |
