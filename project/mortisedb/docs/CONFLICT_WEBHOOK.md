# 冲突 Webhook 通知设计注记

## 1. 背景与目标

痛点：冲突挂起与自动裁决只落在 `_m_conflicts` 表与 `mortise_conflicts_pending` 指标上，外部系统只能靠轮询感知，延迟高、上下文缺失。

目标：在冲突状态变更时，向配置的 URL 推送带签名的 JSON 通知，使下游能实时收到 `conflict.pending`、`conflict.resolved_auto`、`conflict.resolved` 三类事件及冲突行快照。

非目标：

- 不做通用事件总线，只覆盖上述三类冲突事件。
- 不做 webhook 管理 UI，配置只经 `notify` 段 YAML 提供。

## 2. 触发时机

投递一律在事务提交 / HTTP 成功响应之后异步触发，绝不持锁，绝不阻塞同步与解决流程。

### 2.1 冲突挂起 pending

- sync 引擎跨源冲突判定处（`sync.go`，条件为跨源 `existSource != sc.Name` 且行哈希不同）：
  - `cfg.Sync.Conflict == "priority"` 且本源优先级低：`RecordConflict(Status "pending")`，`ts.Conflicts++`。
  - `cfg.Sync.Conflict == "manual"`：`RecordConflict(Status "pending")`，`ts.Conflicts++`。
  - default 分支：按 priority 处理，其中低优先级挂起路径同上。
- CSV 增量导入 `import_csv.go` 的 `decideUpsert` 返回 `"conflict"` 处（语义与 `sync.go` 一致，带 `*store.Conflict`）。

以上各处在事务内 `RecordConflict` 落库；事务提交成功后，`sync.go` / `import_csv.go` 调用 `FireTableConflicts(st, 表名, 本次开始时间)` 回查该表本次新增的冲突并异步投递 `conflict.pending`（实现为按表+时间窗口扫描，而非逐条直投，效果等价）。

### 2.2 自动裁决 resolved_auto

- `sync.go`：`cfg.Sync.Conflict == "priority"` 且本源优先级高，`UpsertRow` 覆盖并 `RecordConflict(Status "resolved_auto")`。
- `sync.go`：同源内容变化，`UpsertRow` 直接更新并 `ResolveConflictsByPK(tx, ti.Name, pk, "resolved_auto")`。
- `import_csv.go`：`decideUpsert` 返回 `"updated"` 且其中含同源更新，`ResolveConflictsByPK(..., "resolved_auto")`。

以上各处状态落库后，同样在事务提交成功后经 `FireTableConflicts` 回查投递 `conflict.resolved_auto`（`resolved_auto` 的判定窗口为 `ResolvedAt >= since`，`ResolvedAt` 为空时回退用 `CreatedAt`）。

### 2.3 人工解决 resolved

- `server.go` `handleResolveConflict`：`POST /api/conflicts/{id}/resolve` 成功后调 `ResolveConflict(id, "resolved")`。

在 HTTP 成功响应之后投递 `conflict.resolved`。实现上是先 `writeJSON` 返回 200，再 `NotifyAsync(EventResolved, 回查到的冲突行)`；回查失败只记日志，不影响已返回的响应。

## 3. payload 契约

顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event` | string | 枚举 `conflict.pending` \| `conflict.resolved_auto` \| `conflict.resolved` |
| `occurred_at` | string | RFC3339 时间戳 |
| `mortise_version` | string | 版本号 |
| `delivery_id` | string | 每次投递唯一 |
| `conflict` | object | `_m_conflicts` 行快照 |

`conflict` 对象字段（对应 `store.Conflict`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int64 | 冲突 id |
| `table_name` | string | 表名 |
| `pk` | string | 主键 |
| `source_a` | string | 源 A |
| `source_b` | string | 源 B |
| `row_json` | string | 挑战方行 JSON 字符串原样透传 |
| `status` | string | 冲突状态 |
| `created_at` | string | 创建时间 |
| `resolved_at` | string | 解决时间 |

完整示例：

```json
{
  "event": "conflict.pending",
  "occurred_at": "2025-01-02T03:04:05Z",
  "mortise_version": "1.5.0",
  "delivery_id": "b7f3c2e1-4a9d-4c8b-9f0e-2d1a6b5c7e8f",
  "conflict": {
    "id": 42,
    "table_name": "users",
    "pk": "1001",
    "source_a": "mysql_main",
    "source_b": "pg_replica",
    "row_json": "{\"id\":1001,\"name\":\"alice\"}",
    "status": "pending",
    "created_at": "2025-01-02T03:04:05Z",
    "resolved_at": ""
  }
}
```

## 4. 签名

- 算法：HMAC-SHA256。
- 密钥：配置项 `conflict_webhook_secret`。
- 签名对象：请求原始 body 字节。
- 签名头：`X-Mortise-Signature: sha256=<hex>`。
- 附带头：`X-Mortise-Event`、`X-Mortise-Delivery-Id`。
- 密钥绝不打日志，绝不进 `/metrics`。

## 5. 配置

`notify` 段 YAML 示例：

```yaml
notify:
  conflict_webhook_url: "https://example.com/mortise/conflict"
  conflict_webhook_secret: "change-me"
  conflict_webhook_timeout: "10s"
  conflict_webhook_max_retries: 3
  conflict_events:
    - conflict.pending
    - conflict.resolved_auto
    - conflict.resolved
```

字段与校验规则：

- `conflict_webhook_url`：空表示功能关闭。
- `conflict_webhook_secret`：`conflict_webhook_url` 非空时必填，否则启动校验报错。
- `conflict_webhook_timeout`：默认 `10s`，格式为 Go duration。
- `conflict_webhook_max_retries`：默认 `3`。
- `conflict_events`：订阅事件列表，默认三个事件全订阅。

环境变量覆盖：现有环境变量覆盖为 `MORTISE_DB`、`MORTISE_ADDR`；`notify` 段本版不支持环境变量覆盖。

## 6. 重试策略

- 指数退避：1s → 2s → 4s（+抖动）。
- 最多 `conflict_webhook_max_retries` 次重试，即最多 1 + `conflict_webhook_max_retries` 次投递。
- 单次请求超时为 `conflict_webhook_timeout`。
- 3xx 不跟随跳转，视为失败。
- 4xx（除 429）不重试，直接记 dropped。
- 429、5xx、网络错误、超时可重试。

## 7. 失败语义

通知失败（全部重试用尽仍失败，或未配置 URL）绝不阻塞同步、import、解决流程。

失败只记日志：Error 级，带 `delivery_id` 与 `event`，不带密钥与 body 全文。

失败只记指标：`mortisedb_conflict_webhook_deliveries_total{event,status}`，其中 `status ∈ delivered | failed | dropped`；`dropped` 表示未配置 URL、事件未订阅、4xx 不可重试。

## 8. 与现有 OPERATIONS.md §4.2 的关系

现有 cron 轮询 `mortise_conflicts_pending` 告警思路保留；webhook 是推送补充，不是替代。

## 9. 待协调员审查的开放问题

1. pending 风暴时是否聚合节流：突发导入会逐条产生 `conflict.pending`，是否合并为批量投递，还是保持一事件一投递。
2. `conflict.resolved_auto` 是否默认订阅：自动裁决量大，默认全订阅会放大投递量，是否改为默认不订阅由使用者显式开启。
3. secret 轮换方式：`conflict_webhook_secret` 目前为单值，轮换期间是否需要双密钥并存以平滑切换。
4. 退避抖动幅度与上限：1s → 2s → 4s 之上的抖动范围是否需要配置化。
