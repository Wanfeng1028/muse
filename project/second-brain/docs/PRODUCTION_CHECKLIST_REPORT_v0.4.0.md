# 发版对照报告：second-brain v0.4.0

- 版本：v0.4.0
- 日期：2026-10-16
- 结论：可发版。推送主链路、幂等、脱敏、测试与冒烟都已验证；多实例重复推送未做防护，列为排期项。

## 1. 可靠性

- [通过] 调度器 30 秒 tick，到点触发 `RunPush`，可 `Stop`，main.go 在优雅关闭时调用。
- [通过] 单通道失败不影响另一通道，SMTP 挂了 Webhook 仍会发。
- [通过] 幂等有保障：同一天同一通道只成功推送一次，靠 `push_log` 唯一索引加 `HasPushed` 检查。
- [通过] 空队列也能正常出消息，主题为「（今日无待复习）」。
- [未通过] 多实例部署会重复推送，未做分布式锁或单实例选举，排期处理。
- [未通过] 没有自动重试队列，SMTP 发送失败只按次记录，等次日或手动测试重发；已在文档声明为已知限制。

## 2. 可观测性

- [通过] `push_log` 记录 date、channel、status（sent/failed/skipped）、detail，冲突时更新。
- [通过] `GET /api/push/history` 可查看推送历史。
- [通过] 单个通道失败会写 failed，另一个通道成功会写 sent，状态可区分。
- [通过] 冒烟时确认调度器真实触发后 `push_log` 记 sent。
- [不适用] 未引入指标、链路追踪，当前单用户规模不需要。

## 3. 数据与状态

- [通过] 新增 `push_settings` 表，key/value 存页面可改的非密钥配置。
- [通过] 新增 `push_log` 表，`ON CONFLICT` 更新，配合唯一索引支撑幂等。
- [通过] `GET /api/push/settings` 合并 env 默认与 DB 覆盖，绝不返回密码、secret 明文。
- [通过] `PUT /api/push/settings` 只接受白名单字段，body 含 `password` 或 `secret` 直接 400。
- [通过] `POST /api/push/test` 用 3 条假数据真实发送，不写 `push_log`，不会污染幂等状态。

## 4. 部署与运维

- [通过] 推送启用时启动做配置校验，失败 fail-fast；未启用时跳过校验。
- [通过] `SB_PUSH_TIME` 默认 08:30，`SB_PUSH_TZ` 默认 Asia/Shanghai，`SB_SMTP_PORT` 默认 587，`SB_SMTP_TLS` 默认 true。
- [通过] main.go 在推送启用时启动调度器，优雅关闭时 `Stop`。
- [未通过] 多实例部署无单实例保证，需要外部保证只有一个实例跑调度；已列为排期项。
- [通过] 真实冒烟：webhook 接收桩收到 `X-Event`、`X-Signature` 与完整 payload；调度器按配置时间真实触发；`/api/push/test` 真实发出。

## 5. 安全与健壮性

- [通过] Webhook 带 `X-Signature: sha256=<hex(hmac-sha256(secret, body))>`，接收端可验签，集成测试已验。
- [通过] SMTP 密码与 webhook 密钥只走环境变量，页面不填，接口不返回明文。
- [通过] 标题与摘要做 HTML 转义，单元测试覆盖 XSS 场景。
- [通过] `PUT /api/push/settings` 对非法 time 返回 400，对 body 含 password 返回 400。
- [未通过] SMTP 明文模式（`SB_SMTP_TLS=false`）没有传输加密，仅建议内网使用；已在文档声明。
- [通过] Webhook 非 2xx、超时、SMTP 不可达都有单元测试覆盖。

## 6. 可维护性

- [通过] `internal/notify` 与 `internal/push` 分包清晰，`Sender` 接口便于扩展通道。
- [通过] `BuildDigestMessage`、`NextPushTime` 是纯函数，单测好写。
- [通过] 全量 104 通过，v0.3.0 时 68，新增 36，覆盖单元、调度、api 集成。
- [通过] fake SMTP 服务器自研最小实现，走完 EHLO→DATA→QUIT 真实收信，不引外部依赖。
- [通过] Web UI 有推送设置页与推送历史表，截图在 `docs/screenshots/push-settings.png`。

## 7. 已知限制与排期

- [未通过] 多实例重复推送未防护，排期：引入单实例保证或分布式锁。
- [未通过] 无自动重试队列，声明为已知限制：失败按次记录，可等次日或手动测试重发。
- [未通过] SMTP 明文模式仅内网，文档声明；如需公网使用应强制 STARTTLS。
- [未通过] SMTP 密码与 webhook 密钥只能走环境变量，页面不可配，声明为已知限制。
- [不适用] 单用户，无多租户，当前版本不做。
