# second-brain 运维手册

本文档面向部署、运维 second-brain 服务的人，讲清楚怎么启动、怎么配推送、重试和死信怎么看、数据怎么备份、出问题先查哪里。所有内容对应仓库真实行为，照着做即可。

## 部署与启动

模块路径 `github.com/Wanfeng1028/muse/second-brain`，服务入口在 `cmd/server`。

构建：

```bash
go build -o second-brain ./cmd/server
```

开发或临时运行：

```bash
go run ./cmd/server
```

配置全部走环境变量，没有配置文件。至少确认下面两项：

- 数据库位置：默认 `data/second-brain.db`，用 `SB_DB` 改路径。目录要先存在，否则启动会失败。
- 推送开关：`SB_PUSH_ENABLED` 默认 `false`，为 false 时推送相关的配置校验会跳过，服务照常起，但不会真的推送。

优雅关闭：服务支持收到终止信号后优雅关闭，正在处理的请求会走完再退出。用 `Ctrl+C` 或 `kill`（SIGTERM）都行，别用 `kill -9`，否则可能留下未落盘的写入。

## 推送配置

所有推送参数都用环境变量传，密钥（SMTP 密码、Webhook SECRET、VAPID 私钥）只走环境变量，不要写进代码或提交到仓库。

| 变量 | 默认值 | 说明与约束 |
| --- | --- | --- |
| `SB_PUSH_ENABLED` | `false` | 总开关，false 时跳过推送相关校验 |
| `SB_PUSH_TIME` | `08:30` | 每日推送时间 |
| `SB_PUSH_TZ` | `Asia/Shanghai` | 推送时间所用时区 |
| `SB_SMTP_HOST` | 无 | SMTP 服务器地址 |
| `SB_SMTP_PORT` | 无 | SMTP 端口 |
| `SB_SMTP_USER` | 无 | SMTP 用户名 |
| `SB_SMTP_PASS` | 无 | SMTP 密码，密钥，只走环境变量 |
| `SB_SMTP_FROM` | 无 | 发件人地址 |
| `SB_SMTP_TLS` | 无 | 是否启用 TLS |
| `SB_MAIL_TO` | 无 | 收件人地址 |
| `SB_WEBHOOK_URL` | 无 | Webhook 接收地址 |
| `SB_WEBHOOK_SECRET` | 无 | Webhook 签名密钥，只走环境变量 |
| `SB_VAPID_PUBLIC_KEY` | 无 | WebPush 公钥 |
| `SB_VAPID_PRIVATE_KEY` | 无 | WebPush 私钥，密钥，只走环境变量 |
| `SB_VAPID_SUBJECT` | 无 | WebPush 主题（一般是 mailto 或 URL） |
| `SB_PUSH_MAX_RETRIES` | `3` | v0.11 新增，最大重试次数，取值上限 10 |
| `SB_PUSH_RETRY_BASE_MS` | `1000` | v0.11 新增，退避基数，单位毫秒 |

## 发送重试（v0.11+）

v0.11 起，SMTP 和 Webhook 的发送器在 `BuildSenders` 出口统一套了指数退避包装器，也就是这两类通道的每次发送都会自动重试。WebPush 是逐订阅单独重试的。

哪些错误会重试：

- 网络错误、连接错误
- HTTP 429
- HTTP 5xx

哪些错误不重试：

- 鉴权失败（认证被拒）
- 其他 4xx
- 订阅失效（410 / 404），这类走订阅清理流程，不做重试

退避算法：第 `attempt` 次重试的等待时间为 `base * 2^attempt`，再叠加 ±25% 的抖动，单次等待上限 30 秒。`base` 就是 `SB_PUSH_RETRY_BASE_MS`，默认 1000 毫秒；重试次数上限是 `SB_PUSH_MAX_RETRIES`，默认 3，最大可以调到 10。

怎么调：

- 对方服务偶发抽风、想多给几次机会：调大 `SB_PUSH_MAX_RETRIES`。
- 不想等太久、想更快失败：调小 `SB_PUSH_MAX_RETRIES`，或调小 `SB_PUSH_RETRY_BASE_MS`。
- 注意退避是指数增长且有 30 秒上限，重试次数调大后总耗时主要花在后面几次。

测试通道不重试：`POST /api/push/test` 是单次发送，不走重试逻辑。用它验证配置通不通时，一次失败就是失败，不会自动重试。

## 死信处理

死信指重试次数耗尽后仍然失败的推送记录。这类记录写在 `push_log` 表，`status` 为 `failed_permanent`，`detail` 字段格式是 `重试耗尽: <最后错误>`，超过 200 rune 会被截断。死信是幂等的：同一 `date`、`channel`、`user_id` 只会有一条记录。

查询最近的死信：

```sql
SELECT date, channel, user_id, detail, created_at
FROM push_log
WHERE status='failed_permanent'
ORDER BY id DESC
LIMIT 20;
```

也可以直接调接口看：`GET /api/push/history`，死信会出现在返回结果里。

常见死信原因对照：

| detail 里出现的线索 | 可能原因 | 怎么处理 |
| --- | --- | --- |
| 连接失败 / 超时 | 网络不通、防火墙拦截 | 查本机到目标服务的网络、代理和防火墙规则 |
| 认证被拒 | 鉴权失败 | 注意：鉴权失败是不可重试错误，不会走重试耗尽流程，它记的是普通 `failed` 而不是 `failed_permanent`。核对账号密码是否正确 |
| 5xx / 429 重试耗尽 | 对方服务过载或限流 | 属于对方服务问题，隔天一般自动恢复；持续出现就联系对方 |
| webhook 4xx | 请求本身被接收端拒绝 | 检查 `SB_WEBHOOK_URL` 是否正确、接收端参数与签名要求是否变化 |

## 备份与恢复

数据库是 SQLite，默认在 `data/second-brain.db`，用 `SB_DB` 改过就按改后的路径来。

最简单的方式是直接拷 db 文件。服务支持优雅关闭，热拷之前建议先停服务，或者用 SQLite 自带的在线备份：

```bash
# 停服务后直接拷
cp data/second-brain.db data/second-brain.db.bak

# 不停服务，用 sqlite3 在线备份
sqlite3 data/second-brain.db ".backup 'data/second-brain.db.bak'"
```

恢复步骤：

1. 停掉服务（用 SIGTERM 或 `Ctrl+C`，等它优雅退出）。
2. 把备份文件拷回 db 路径，覆盖当前文件：
   ```bash
   cp data/second-brain.db.bak data/second-brain.db
   ```
3. 重新启动服务。

注意 `push_log` 上有唯一索引 `(date, channel, user_id)`，恢复旧备份等于回退到那个时间点的数据，之后产生的推送记录会丢，按需决定是否接受。

## 常见排障

推送没收到，按这个顺序查：

1. 先看 `push_log` 状态。查对应 `date`、`channel`、`user_id` 的记录，看 `status`：
   - `failed_permanent`：进了死信，按上一节对照表排查。
   - `failed`：普通失败，多半是不可重试错误（比如鉴权失败），看 `detail`。
   - 没有记录：说明根本没触发发送，检查 `SB_PUSH_ENABLED` 是否为 `true`、`SB_PUSH_TIME` 和 `SB_PUSH_TZ` 是否设对。
2. 再看服务日志。日志里能看到重试过程和每次的具体错误，比 `detail` 里的最后一条错误更全。
3. 最后用 `POST /api/push/test` 单发验证。它不重试，一次就能确认配置到底通不通，适合快速定位是配置问题还是对端问题。
## 日志与 request_id 追踪

### 输出与级别

- 服务日志为 JSON，打到 **stdout**（`docker logs` / journald / 重定向文件均可收）。
- 级别由 `SB_LOG_LEVEL` 控制：`debug` / `info` / `warn` / `error`，大小写不敏感；不设或写错都按 `info` 跑。
- 想临时看更细的日志不用重启改代码：`SB_LOG_LEVEL=debug` 启动即可。

### request_id 全链路追踪

每个 HTTP 请求都有一个 `request_id`：

1. 客户端请求头带 `X-Request-ID` → 原样透传；不带 → 服务端生成 32 位随机串。
2. 响应头 `X-Request-ID` 回写，调用方拿到 ID 就能查链路。
3. 请求结束记一条 `msg="http.request"` 的日志，字段：`request_id`、`method`、`path`、`status`、`latency_ms`（毫秒）；`status>=500` 时这条日志是 ERROR 级别。
4. 所有错误响应体都带 `request_id`：
   `{"error": "note not found", "request_id": "9f3a1c..."}`。

关键业务日志的 `msg` 约定：`note.created`（建笔记）、`review.graded`（复习评分）、
`store.note_created`、`store.review_recorded`、`push.tick_result`（定时推送结果）、
`server.*`（启动/关闭流程）。字段里一律带 `request_id`（后台定时任务除外，它没有请求上下文）。

### 常用排查命令

```bash
# 按 request_id 捞出一条请求的全部日志
docker logs second-brain 2>&1 | grep '"request_id":"<id>"'

# 看所有 5xx 请求
docker logs second-brain 2>&1 | grep '"http.request"' | grep '"level":"ERROR"'

# 看慢请求（latency_ms 大的排前面，需 jq）
docker logs second-brain 2>&1 | grep '"http.request"' | jq -s 'sort_by(.latency_ms) | reverse | .[0:10]'

# 只看某用户的建笔记操作
docker logs second-brain 2>&1 | grep '"note.created"' | grep '"user":"alice"'
```

### 日志轮转建议

- docker 部署：`--log-opt max-size=50m --log-opt max-file=5`。
- systemd：`SystemMaxUse=` / `journald` 按发行版默认即可，JSON 行日志可直接 `journalctl -u second-brain -o cat | grep ...`。
- 日志不含密码、密钥明文（推送设置接口返回已脱敏；VAPID 私钥只走环境变量）。

## 指标（v0.12+）

- 开关与鉴权：SB_METRICS_ENABLED（默认 true）、SB_METRICS_TOKEN（为空则 /metrics 无需鉴权；非空时需 Authorization: Bearer <token>，否则 401）。
- 抓取：GET /metrics，Prometheus 文本格式；Prometheus 配置示例 scrape_interval 15s。
- 指标表：http_requests_total{method,route,status}、http_request_duration_seconds{method,route}（histogram，buckets 0.005~10）、push_sent_total{channel,status}（status 含 sent/failed/failed_permanent/skipped）、reviews_graded_total{grade}、notes_total、reviews_due（默认用户的今日到期数）。
- 注意：/metrics 自身不被 metrics 中间件记录；429 拒绝会被计数。

## API 限流（v0.12+）

- 双维度 token bucket：key = clientIP + 用户（X-User/CurrentUser）；读桶与写桶独立，写操作指 POST/PUT/DELETE/PATCH。
- 变量：SB_RATE_LIMIT_ENABLED（默认 true）、SB_RATE_LIMIT_RPS（默认 20）、SB_RATE_LIMIT_BURST（默认 40）、SB_RATE_LIMIT_WRITE_RPS（默认 5）、SB_RATE_LIMIT_WRITE_BURST（默认 10）。
- 超限：429 + Retry-After 秒头 + JSON {"error":"rate limit exceeded","request_id":"..."}。
- 非法值启动 fail-fast：SB_RATE_LIMIT_RPS / SB_RATE_LIMIT_WRITE_RPS 设了但不是数字，或任一限流参数 <=0，服务直接 log.Fatalf 拒绝启动。
- 调优建议：日常 20/40 够用；被爬虫打时调小 RPS；内网可信调用可 SB_RATE_LIMIT_ENABLED=false 关掉。

## 告警规则（v0.13+）

规则文件在 `prometheus/rules/second-brain.yml`，group 名 `second-brain-alerts`，每 30 秒评估一次。所有规则都带 `summary`、`description`、`runbook_url`，`runbook_url` 指回本节。规则里只用服务真实暴露的指标：`http_requests_total`、`http_request_duration_seconds`、`push_sent_total`、`reviews_graded_total`、`notes_total`、`reviews_due`、`up`。

### 规则说明和阈值

- SecondBrainHigh5xxRate（warning，for 5m）：5 分钟窗口里 5xx 响应占比超过 5%。服务端错误变多，先看接口日志。
- SecondBrainPushFailureRate（warning，for 15m）：15 分钟窗口里推送失败（`failed` 加 `failed_permanent`）占比超过 20%。推送渠道或凭据有问题。
- SecondBrainHighP99Latency（warning，for 5m）：5 分钟窗口 HTTP 请求 P99 延迟超过 1 秒。请求变慢，先定位是哪个 route。
- SecondBrainRateLimitedSurge（warning，for 5m）：429 拒绝速率超过 5/s。疑似被刷或被爬虫打，看来源再决定要不要调小限流阈值。
- SecondBrainDeadLetterSurge（warning，for 0m）：1 小时内 `failed_permanent` 增量大于 0。永久失败不自动重试，有死信立刻看。
- SecondBrainInstanceDown（critical，for 5m）：`up{job="second-brain"} == 0` 持续 5 分钟。实例抓不到指标，服务可能挂了。

### Prometheus 抓取配置示例

```yaml
scrape_configs:
  - job_name: second-brain
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets:
          - "second-brain:8080"
```

注意 `/metrics` 自身请求不会被计入 `http_requests_total`，所以抓取不会污染告警用的请求量。

### Alertmanager 接入三步

1. 在 Prometheus 配置里指向 Alertmanager 地址，例如 `alerting: alertmanagers: - static_configs: - targets: ["alertmanager:9093"]`，并加载规则文件 `rule_files: - /etc/prometheus/rules/second-brain.yml`。
2. 在 Alertmanager 配置里加一个 receiver（webhook、邮件或企微/钉钉机器人），把 `route.default_receiver` 指过去。
3. 重启 Prometheus 和 Alertmanager，在 Prometheus 的 Alerts 页面确认规则已加载，再手动触发一次（比如停掉实例）验证通知能到。

### 收到告警后的排查步骤

- 5xx 占比高：看服务日志里最近的 500 堆栈，对照「限流与拒绝」和接口排障节，确认是自身 panic、下游依赖还是数据问题。
- 推送失败率高：看推送渠道返回码，对照推送相关排障节，检查凭据是否过期、网络出口是否通。
- P99 延迟高：先按 route 拆开看哪个接口慢，再对照「限流与拒绝」判断是不是被限流排队导致；没有 DB 慢查询专用指标，这条规则同时用来代理慢请求，必要时直接查数据库侧日志。
- 429 速率高：看访问来源 IP 和 UA，对照「限流与拒绝」节，决定是调小 SB_RATE_LIMIT_RPS 还是加白名单。
- 出现死信：找到 `failed_permanent` 对应的推送目标和报错，确认地址和凭据后手动补发。
- 实例抓不到指标：确认进程是否还在、端口是否监听、`/metrics` 是否能本地访问，再看启动日志有没有 fail-fast 退出。

### 诚实声明

当前没有数据库慢查询的专用指标。慢请求问题统一用 SecondBrainHighP99Latency（P99 延迟）这条规则代理，它能告诉你"变慢了"，但没法直接告诉你是哪条 SQL 慢，定位到具体查询还得去数据库侧看日志或慢查询记录。
