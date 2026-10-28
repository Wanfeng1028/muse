# DELETE /api/push/subscriptions 畸形 body 返回 400 对照报告

## 改动摘要
- 代码修改：`internal/api/push_subscription.go` 删除处理器收紧了 body 解析逻辑（非空非法 body 返回 400，不再回落 query），并补全了 `errors` 与 `io` 的 import；`parseIntDefault` 定义未作任何变更。
- 新增测试：创建 `internal/api/push_subscription_delete_malformed_test.go`，包含 `TestPushSubscriptionDeleteMalformed` 1 个测试函数及 5 个子用例（malformed-syntax、malformed-type、malformed-with-query、empty-with-query、empty-object-with-query）。
- 前端与 UI：无 Web UI 改动，前端 `webpush.js` 未改动，且当前发送的是合法 JSON。
- 配置与接口：无 schema 变更，无版本号变更。

## 验收结果
- 静态检查与格式化：`go vet ./internal/api/` 检查通过，改动文件的 `gofmt` 结果干净。
- 单元测试结果：新增的 5 个靶向测试用例（5/5）全部通过，既有的 DELETE 与 POST 测试全部通过。
- 真实环境冒烟：在 `127.0.0.1:18527` 隔离库环境中完成 6 项冒烟测试，全部通过（含建订阅返回 201、畸形语法返回 400、畸形+有效 query 返回 400 且订阅保留、空 body+query 删除返回 200、再查列表为空）；测试后服务已停止、端口已关闭、隔离库与冒烟二进制均已删除。
- 全局测试状态：全量 `go test ./...` 本轮未执行。

## 对照
### 可靠性
- 结论：通过
- 理由：改动精准修复了畸形 body 请求应返回 400 的缺陷，靶向测试 5/5 通过且既有测试全过，证明未破坏现有功能。

### 可观测性
- 结论：不适用
- 理由：简报事实中未提及任何关于日志、监控、指标埋点或错误响应体标准化的观测性改动记录。

### 数据与状态
- 结论：通过
- 理由：冒烟测试验证了畸形 body（含 query 情况）会拦截并返回 400，保证订阅数据未误删；空 body 正确处理删除逻辑，列表状态变更正确。

### 部署与运维
- 结论：通过
- 理由：冒烟测试完成后，已主动确认关闭端口（18527）、停止服务并清理隔离库与二进制，部署环境干净。

### 安全与健壮性
- 结论：通过
- 理由：通过收紧 DELETE 订阅的 body 解析逻辑，有效拒绝了畸形输入（400），提升了接口对垃圾数据的防御能力，且未影响其他端点的容错机制。

### 可维护性
- 结论：通过
- 理由：代码修改精简（只改删除处理器解析分支与 import），测试用例覆盖细致（5 个子用例），且未引入 schema 或版本号变更，降低了系统维护复杂度。

## 已知限制与下一轮
- 全量测试未覆盖：本轮未执行全量 `go test ./...`，暂无法全面评估对其他未知代码模块的潜在影响。
- 其他端点 body 容错口径未动：本轮只收紧 DELETE 订阅的 body 解析，其他端点的 body 容错口径未动。