# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法，版本号按 [SemVer](https://semver.org/lang/zh-CN/)。

## [v0.4.0] - 2026-10-16

### 新增

- **Webhook 持久化投递队列**：告警产生时只做 SQLite 入队（`webhook_deliveries` 表，迁移 v5），后台 worker 每 15 秒扫一次到期任务，按指数退避（基数 60 秒，`base*2^(attempt-1)+jitter`）重投；状态 pending（待投递）/retrying（重试中）/done（已送达）/failed（已失败）；默认最多投 8 次，失败自动标 failed，不再丢告警
- **投递队列管理 API**：`GET /api/alerts/deliveries`（按 status/monitor_id/limit 查）、`POST /api/alerts/deliveries/{id}/retry`（手动重投，仅 failed/retrying 可重试）
- **投递队列控制台页** `/deliveries`：状态筛选、尝试次数/下次重试/最近错误一览，失败的可一键手动重投
- **配置**：`SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS`（默认 8）、`SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC`（默认 60）、`SENTINEL_WEBHOOK_QUEUE_TICK_SEC`（默认 15）

### 变更

- webhook 渠道改为异步投递：告警产生时只入队，不再阻塞等待投递结果；smtp/企业微信渠道仍同步发送
- 同一告警事件重复入队自动去重（按 monitor+url+event+payload）

### 已知限制

- v0.2.0 的"Webhook 仅重试 3 次，失败后只写日志，不做持久化队列重投"已解决，删除该条
- 分布式多实例未支持，仅单实例部署（SQLite，worker 单实例运行）

## [v0.3.0] - 2026-10-16
### 新增

- **状态页主题**：每个状态页可配浅色/深色/自定义主色（`accent_color` #rrggbb），存 DB（迁移 v3，老库自动补列）；`GET /api/status/{slug}` 透出主题；公开页按主题渲染，访客可用页面上的切换器预览浅色/深色/跟随站点
- **订阅通知**：公开状态页支持访客邮箱订阅（`status_subscriptions` 表，迁移 v4）；订阅需点击确认邮件里的 token 链接（防滥用），退订走 token 链接；monitor 发生 down/recovered 事件时扇出邮件给已确认订阅者（同一邮箱多页去重）
- **配置**：`SENTINEL_PUBLIC_URL`（可选）作为订阅邮件中确认/退订链接的基地址，为空用相对路径
- **API**：`PUT /api/status-pages/{id}/theme`、`POST /api/status/{slug}/subscribe`、`GET /api/status/{slug}/confirm`、`GET /api/status/{slug}/unsubscribe`、`POST /api/status/{slug}/unsubscribe`

## [v0.2.0] - 2026-10-13

### 生产级改造

- **结构化日志**：全量切到 `slog`，JSON 输出，字段固定，业务字段按需附加。
- **request_id**：HTTP 中间件为每个请求生成 request_id，贯穿 handler 和下游日志。
- **健康探针**：新增 `/healthz`（存活）和 `/readyz`（就绪，检查 DB 和调度器）。
- **优雅关闭**：收到 SIGINT/SIGTERM 后停收新请求，等 inflight 检查完成再退，带超时兜底。
- **Prometheus 指标**：新增 `/api/metrics`，暴露 monitors_total、checks_total、check_duration_seconds、check_failures_total、incidents_open、http_requests_total。
- **DB 迁移版本化**：引入 `schema_version` 表，v1→v2 幂等迁移，启动自动执行。v2 新增 `users`、`status_pages` 表，`monitors` 增加 `is_public` 列。
- **检查重试**：失败按指数退避重试，带 jitter，上限由 `SENTINEL_CHECK_RETRY_MAX` 控制。
- **失败注入测试**：覆盖 DNS 失败、连接超时、非 2xx 响应、DB 写失败等路径。
- **配置启动校验**：所有环境变量集中校验，不合法直接退出并打印原因。
- **API Token 鉴权**：`Authorization: Bearer <token>` 校验，401 统一响应。
- **tenant / user**：v2 引入 `users` 表（id/username/token_hash/created_at），为多用户场景预留。
- **自动备份 + 一键恢复**：按周期自动备份，保留 N 份；新增 `-restore` 参数，恢复流程已实测。
- **docker-compose**：一键部署，端口 8200，数据卷、备份卷、资源限制（1 CPU / 512MB）、日志轮转全部配好。
- **OPERATIONS.md**：运维手册，覆盖部署、配置、备份恢复、升级、可观测性、token 管理、排障、资源限制。

### 灵魂功能

- **站点健康档案** `/profile?id=N`：7/30 天可用性、延迟 p50/p95/p99、30 天每日可用性柱状图、月度 SLA，一页看全。
- **月度 SLA**：`GET /api/monitors/{id}/sla?month=YYYY-MM`，返回可用性、检查数、宕机事件数、总宕机时长、SLA 目标 99.9%、是否达标。
- **公开状态页** `/status/{slug}`：对外展示，无需登录，展示各 monitor 状态、30 天可用性、最近检查时间。配套 `POST /api/status-pages`、`GET /api/status-pages`、`POST /api/status-pages/auto` 三个接口。

### 已知限制

- 分布式多实例未支持，仅单实例部署（SQLite）。
- Webhook 仅重试 3 次，失败后只写日志，不做持久化队列重投。
