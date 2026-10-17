# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法，版本号按 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.7.0] - 2026-10-17

### 新增

- **入队限流**：`internal/notify/limiter.go` 令牌桶（满桶启动）；`SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS`（默认 20，0=禁用）/`_BURST`（默认 40），非法启动 fail-fast；超限丢弃+计数+warn 日志（后台入队无 HTTP 上下文可 429）
- **投递熔断**：`internal/notify/circuit.go`，按 host 独立熔断（闭合→断开→半开→闭合，半开单探测）；`SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD`（默认 5）/`_OPEN_TIMEOUT_SEC`（默认 300）；与指数退避/手动重试正交
- **指标**：`sentinel_webhook_enqueue_rejected_total`、`sentinel_webhook_breaker_state{host}`（0/1/2）进 `/api/metrics`
- **告警**：`prometheus/rules/sentinel.yml` 8 条（新增 SentinelWebhookEnqueueRejected、SentinelWebhookBreakerOpen）
- **文档**：`docs/OPERATIONS.md` 第 12 章（限流熔断调参）；发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v0.7.md`

### 实测

- `go test` 190/190（含 -race 并发），`go vet` 全洁
- 真实冒烟：必失败 sink 下 2 次连续失败即熔断断开；10 死目标洪峰下限流拒绝 8 次；sink 恢复后半开探测成功、熔断闭合、投递 done

### 关闭排期

- v0.6 排期的入队限流、投递熔断已交付（§5 限流/超时/熔断：部分通过 → 通过）

### 已知限制

- Go 工具链 go1.23.4 过旧（46 个标准库漏洞根因），排期升级后复扫
- `incidents.html` 模拟数据债仍挂账

## [0.6.0] - 2026-10-17


### 新增

- **Prometheus 告警规则**：`prometheus/rules/sentinel.yml`，6 条（实例 down / 调度停滞 / 队列积压>50 / 投递失败率>20% / 检查失败激增 / 自身 API 5xx 率>5%），配套 `prometheus/prometheus.yml` 抓取示例（含 /api/metrics 鉴权说明）；`docs/OPERATIONS.md` 新增第 10 章（阈值依据、静默/值班建议）
- **队列积压指标**：`GET /api/metrics` 新增 gauge `sentinel_webhook_queue_backlog{status="pending"|"retrying"}`（`internal/metrics.RenderQueueBacklog` + handleMetrics 追加，DB 查询失败只记日志不中断抓取）
- **依赖漏洞扫描**：`scripts/depscan.sh`（go list 取模块 → OSV querybatch → govulncheck 优先；退出码 0/1/2；报告 `docs/dependency-scan-YYYYMMDD.json`）
- **真实负载验证**：`scripts/load_check.sh`（8 假目标 + webhook sink，采集检查延迟 p50/p99、事件正确性、故障时队列积压/排空；报告 `docs/load-test-YYYYMMDD.md`）
- **测试**：4 个新增（规则 YAML 回归 `prometheus/rules/sentinel_rules_test.go`、积压 gauge 精确输出、积压计数 pending+retrying）；`go test` 141/141 全过

### 实测

- depscan：23 个模块，OSV 3 个 + govulncheck 46 个 = 49 个漏洞（全在 Go 标准库 go1.23.4 与 x/mod、x/sys，无第三方业务依赖漏洞）
- load_check：40 轮检查，p50=6.0ms、p99=14.8ms；4 down 事件全对、无误报；webhook 4/4；积压峰值 2 并排空；73s
- fault-drill.sh：13/13（34s）

### 已知限制

- 46 个标准库漏洞源于工具链 go1.23.4 过旧，排期 v0.7 升级 Go 工具链后复扫
- 入队侧限流、投递侧熔断仍未做（v0.5 已排期），继续排期 v0.7
- `incidents.html` 模拟数据债（v0.4.0 记）仍挂账

## [Unreleased]

### 新增

- **短信告警通道（sms）**：`internal/notify/sms.go`，`SmsSender` 接口 + `MockSmsSender`（内存记录，演示/测试用）+ 阿里云短信 HTTP 实现（SendSms，HMAC-SHA1 签名，模板变量固定 `${msg}`）；失败重试一次（共 2 次）
- **通知目标可配短信**：`notify_channels` 支持 `sms`；监控项新增 `sms_phones` 字段（迁移 v8），目标级号码优先、全局 `SENTINEL_SMS_PHONES` 回退；手机号格式校验（大陆 11 位 / 国际 +E.164），非法返回 400
- **配置**：`SENTINEL_SMS_MODE`（mock/aliyun，默认 mock）、`SENTINEL_SMS_PHONES`、`SENTINEL_SMS_ACCESS_KEY_ID`、`SENTINEL_SMS_ACCESS_KEY_SECRET`、`SENTINEL_SMS_SIGN_NAME`、`SENTINEL_SMS_TEMPLATE_CODE`；aliyun 模式四项缺一启动即报错退出
- **文档**：`docs/ALERTING_CHANNELS.md`（四通道对比、短信配置 step-by-step、费用限流、故障排查）；`.env.example` 补齐短信变量
- **前端**：监控表单新增"短信告警"配置区（通知渠道多选 + 接收号码输入）

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
