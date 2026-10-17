# MortiseDB v1.5 发版对照报告

**结论：可发版。** 本版交付「冲突 Webhook 通知」：在 sync 完成回查、两路 CSV 导入、手动解决冲突三类埋点上一事件一投递地推送 HMAC-SHA256 签名的冲突事件，指数退避重试、失败只记日志与指标、永不阻塞主流程。测试数字：`go test ./...` 全量通过（含 api 包 10.4s），新增 internal/api/webhook_notify_test.go（4 例）与 internal/notify/notify_test.go（M2a 投递器单测），`go vet ./...` 全洁、`gofmt -l` 全洁，scripts/e2e.sh 扩展为 11 步全 PASS，真实冒烟验签 MATCH。

## 1. 可靠性

- 全量测试：`go test ./...` 全量通过（含 api 包 10.4s）。**通过**
- 失败路径覆盖（失败不阻塞）：新增 internal/api/webhook_notify_test.go 4 例覆盖两路导入投递+签名校验、失败不阻塞导入、resolve 投递；scripts/e2e.sh 新步骤 10 验证 dead 端口投递失败不阻塞 409 导入。**通过**
- 错误处理：投递失败只记日志+指标，永不阻塞同步/导入/解决主流程。**通过**
- 数据库迁移：不适用（本版无 schema 变更）。**不适用**

## 2. 可观测性

- 日志继承：沿用既有日志设施，投递失败记录日志。**通过**
- 新指标：`mortisedb_conflict_webhook_deliveries_total{event,status}`（event=事件名，status=delivered|failed），进程内计数、重启清零；已写入 OPERATIONS.md §4.2。**通过**

## 3. 数据与状态

- 无 schema 变更。**通过**
- 密钥走配置文件不落库：`conflict_webhook_secret` 仅存于 `mortise.yaml` 的 `notify.` 段，不落库。**通过**

## 4. 部署与运维

- OPERATIONS.md 新增 §8「冲突 Webhook 通知」（配置/触发时机/请求格式/失败语义/排查），原 §8 版本历史顺延为 §9。**通过**
- 配置示例：mortise.yaml.example 提供 `notify.` 段示例（`conflict_webhook_url` / `conflict_webhook_secret` / `conflict_webhook_timeout` / `conflict_webhook_max_retries` / `events`）。**通过**

## 5. 安全与健壮性

- HMAC 签名：请求头 `X-Mortise-Signature` 为 `sha256=<hex>`，对请求体做 HMAC-SHA256（密钥即 `conflict_webhook_secret`）；冒烟用 secret 独立计算 HMAC 验签 MATCH。**通过**
- 密钥保管提醒：`conflict_webhook_secret` 为签名密钥，示例中写 `your-webhook-secret`，实际部署需妥善保管、勿入库勿入日志。**通过**
- 投递失败隔离：指数退避 1s→2s→4s+抖动、最多 `conflict_webhook_max_retries` 次、单次超时 `conflict_webhook_timeout`，失败不阻塞主流程。**通过**
- 鉴权：不适用（本地单用户）。**不适用**

## 6. 可维护性

- API 契约无变更（本版仅新增出站 webhook 通知，未改动既有入站 API）。**通过**
- 文档同步：OPERATIONS.md（§4.2 指标、新增 §8）、docs/CONFLICT_WEBHOOK.md（设计注记 M1）、CHANGELOG.md（1.5.0 节）。**通过**
- 技术债（已知限制三条）：同秒边界可能多投（delivery_id 去重）；pending 风暴下一事件一投递（设计裁决，不聚合）；指标进程内计数重启清零。**已知限制**

## 7. 本轮交付清单

| 批次 | 交付内容 | 测试数字 |
| --- | --- | --- |
| M1 | 设计注记 docs/CONFLICT_WEBHOOK.md（经编排侧审查通过后才实现） | — |
| M2a | 投递器 internal/notify/notify.go | internal/notify/notify_test.go 单测 |
| M2b | 配置 `notify.conflict_webhook_*` 与 `events` | — |
| M2c | 埋点：sync 完成回查、两路 CSV 导入、resolve 成功 | — |
| M3 | 测试 + e2e | internal/api/webhook_notify_test.go 4 例；scripts/e2e.sh 11 步全 PASS；`go test ./...` 全量通过（含 api 包 10.4s）、`go vet ./...` 全洁、`gofmt -l` 全洁 |
| M4 | 冒烟 + 文档 | 冒烟验签 MATCH；/metrics 显示 `mortisedb_conflict_webhook_deliveries_total{event="conflict.pending",status="delivered"} 1` |

## 8. 已知限制

- 同秒边界可能多投（时间字符串秒级比较），接收端按 `delivery_id` 去重。**已知限制**
- pending 风暴下一事件一投递（设计裁决，不聚合）。**已知限制**
- 指标进程内计数，重启清零。**已知限制**

过程注记：M3 首批 e2e.sh PATCH 把 `conflict_webhook_secret` 写成 `<redacted>` 被打回重做；测试文件 import 路径编造（缺 `github.com/Wanfeng1028/muse/` 前缀）已修正；签名断言格式误写 `sha256-` 已按设计注记修正为 `sha256=`。
