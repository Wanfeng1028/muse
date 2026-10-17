# 哨兵 Sentinel 运维手册

面向部署和日常维护。命令都在仓库根目录执行。

## 1. 部署

### 1.1 Docker Compose 一键部署（推荐）

```bash
cp .env.example .env
# 生成 token 填进 .env 的 SENTINEL_API_TOKEN
openssl rand -hex 32
docker compose up -d
```

打开 `http://<服务器IP>:8200` 即可。数据落在 `sentinel-data` 卷，备份落在 `sentinel-backups` 卷。

查看日志：

```bash
docker compose logs -f sentinel
```

停止 / 重启：

```bash
docker compose stop
docker compose restart
```

### 1.2 二进制直跑

```bash
make build
export SENTINEL_API_TOKEN=$(openssl rand -hex 32)
export SENTINEL_HOST=127.0.0.1
./bin/sentinel
```

前台运行，Ctrl+C 优雅关闭。生产环境建议配 systemd 或 supervisor 托管。

## 2. 配置说明

所有配置都走环境变量，启动时会做一次校验（端口范围、并发数、token 非空等），不合法直接退出并打印原因。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SENTINEL_DB` | `data/sentinel.db` | SQLite 数据库路径 |
| `SENTINEL_HOST` | `0.0.0.0` | 监听地址 |
| `SENTINEL_PORT` | `8200` | 监听端口 |
| `SENTINEL_WEBHOOK_URL` | 空 | 告警 webhook，留空只写日志 |
| `SENTINEL_API_TOKEN` | 空（必填） | API 鉴权 token，`openssl rand -hex 32` 生成 |
| `SENTINEL_LOG_LEVEL` | `info` | debug / info / warn / error |
| `SENTINEL_BACKUP_DIR` | `backups` | 备份输出目录 |
| `SENTINEL_BACKUP_KEEP` | `7` | 保留备份份数 |
| `SENTINEL_BACKUP_INTERVAL_H` | `24` | 自动备份间隔（小时） |
| `SENTINEL_CHECK_CONCURRENCY` | `8` | 单次调度最大并发检查数 |
| `SENTINEL_CHECK_RETRY_MAX` | `3` | 检查失败重试次数（指数退避） |
| `SENTINEL_TICK_SEC` | `10` | 调度 tick 间隔（秒） |
| `SENTINEL_NOTIFY_CHANNELS` | `webhook` | 全局默认告警渠道，逗号分隔：webhook / smtp / wecom |
| `SENTINEL_SMTP_HOST` | 空 | SMTP 服务器地址，空表示关闭邮件渠道 |
| `SENTINEL_SMTP_PORT` | `25` | SMTP 端口（465 自动用 SMTPS，587/25 按需 STARTTLS） |
| `SENTINEL_SMTP_USERNAME` | 空 | SMTP 鉴权用户名，空表示不鉴权 |
| `SENTINEL_SMTP_PASSWORD` | 空 | SMTP 鉴权密码 |
| `SENTINEL_SMTP_FROM` | 空 | 发件人地址 |
| `SENTINEL_SMTP_TO` | 空 | 收件人地址，逗号分隔多个 |
| `SENTINEL_WECOM_WEBHOOK_URL` | 空 | 企业微信群机器人 webhook，空表示关闭该渠道 |
| `SENTINEL_WECOM_MENTION_ALL` | `false` | 是否 @全体成员（true/false） |

## 3. 备份与恢复

### 3.1 自动备份策略

进程启动后会按 `SENTINEL_BACKUP_INTERVAL_H` 周期自动备份，写入 `SENTINEL_BACKUP_DIR`，文件名带时间戳，例如 `sentinel-20261013-030000.db`。超过 `SENTINEL_BACKUP_KEEP` 份的旧备份会被删除（按修改时间）。

### 3.2 手动备份

```bash
# 直接拷 SQLite 文件即可，先停服务更稳
docker compose stop
docker compose cp sentinel:/app/data/sentinel.db ./sentinel-backup.db
docker compose start
```

### 3.3 一键恢复

进程支持 `-restore` 参数：

```bash
# 二进制
./bin/sentinel -restore backups/sentinel-20261013-030000.db

# Docker
docker compose stop
docker compose run --rm sentinel -restore /app/backups/sentinel-20261013-030000.db
docker compose start
```

实测步骤（供核对）：

1. 记下当前监控数：`sqlite3 data/sentinel.db "select count(*) from monitors;"`
2. 触发一次备份，确认文件生成。
3. 新增一个监控项，确认数量 +1。
4. 执行 `-restore` 指向刚才的备份。
5. 重新查询数量，回到步骤 1 的数字。
6. 打开 UI 确认监控项列表与备份时间点一致。

## 4. 升级

### 4.1 流程

```bash
# 1. 先备份（重要）
docker compose exec sentinel /app/sentinel -restore 不会用到，直接拷文件更保险
docker compose cp sentinel:/app/data/sentinel.db ./pre-upgrade.db

# 2. 拉新版本重建
git pull
docker compose build
docker compose up -d
```

启动时自动跑迁移。当前 DB schema 版本记录在 `schema_version` 表。

### 4.2 DB 迁移 v1 → v2 说明

- v1：monitors / checks / incidents 基础表。
- v2：新增 `users`、`status_pages` 表，`monitors` 增加 `is_public` 列，`checks` 增加索引。迁移是幂等的，重复启动不会重复加列。

### 4.3 回滚策略

回滚到旧版本前，用升级前的备份文件恢复：

```bash
docker compose stop
docker compose run --rm sentinel -restore /app/data/pre-upgrade.db
# 切回旧镜像
git checkout <旧 tag>
docker compose up -d
```

注意：新版本写入的新字段在旧版本里会被忽略，不会报错；但迁移本身不做自动回退，回滚靠备份。

## 5. 可观测性

### 5.1 健康探针

- `GET /healthz`：进程存活探针，只要进程在就返回 200。
- `GET /readyz`：就绪探针，检查数据库连接和调度器状态，正常返回 200，异常返回 503。

K8s 用法：

```yaml
livenessProbe:  { httpGet: { path: /healthz, port: 8200 } }
readinessProbe: { httpGet: { path: /readyz,  port: 8200 } }
```

### 5.2 Prometheus 指标

`GET /api/metrics`（Prometheus 文本格式）暴露：

- `sentinel_checks_total`：累计检查次数（counter）
- `sentinel_check_failures_total`：累计检查失败次数（counter）
- `sentinel_check_retries_total`：累计检查重试次数（counter）
- `sentinel_webhooks_sent_total`：累计 webhook 发送次数（counter）
- `sentinel_webhook_failures_total`：累计 webhook 投递失败次数（counter）
- `sentinel_webhook_queue_backlog{status="pending"|"retrying"}`：webhook 队列积压（gauge，v0.6 新增，pending+retrying 即队列积压）
- `sentinel_http_requests_total{method,path,status}`：HTTP 请求计数（counter）

说明：

- `/api/metrics` 需要 API Token 鉴权（`Authorization: Bearer <token>`），抓取配置须带 authorization，否则返回 401。
- 历史文档中的 `sentinel_monitors_total`、`sentinel_check_duration_seconds`（耗时直方图）、`sentinel_incidents_open` 等指标并不存在，属旧版文档写错，本次一并订正。

抓取配置示例见 `prometheus/prometheus.yml`（含 authorization 示例）。

```

### 5.3 结构化日志

日志走 slog JSON 格式，每条请求带 `request_id`，方便串联。示例：

```json
{"time":"2026-10-13T10:00:00Z","level":"INFO","msg":"check done","monitor_id":1,"status":"up","request_id":"a1b2c3"}
```

日志级别通过 `SENTINEL_LOG_LEVEL` 控制。排查问题时调成 `debug`。

## 6. API Token 管理

### 6.1 生成

```bash
openssl rand -hex 32
```

写入 `.env` 的 `SENTINEL_API_TOKEN`，重启服务生效。

### 6.2 使用

```bash
curl -H "Authorization: Bearer $SENTINEL_API_TOKEN" http://localhost:8200/api/monitors
```

前端从 `sessionStorage.getItem('sentinel_token')` 读取，缺失时弹出输入框。

### 6.3 更换

改 `.env` 后 `docker compose up -d`。旧 token 立即失效。所有客户端需要同步更新。

### 6.4 users 表

v2 引入 `users` 表，字段：`id`、`username`、`token_hash`、`created_at`。当前实现里主 token 仍走环境变量；`users` 表用于后续多用户/多 token 场景，暂时保留。

## 7. 常见故障排查

### 7.1 401 Unauthorized

- 检查请求头 `Authorization: Bearer <token>` 是否带上。
- 检查 `.env` 的 token 是否被改过、是否重启生效。
- 前端场景检查 `sessionStorage` 里的 token 是否过期或写错。

### 7.2 端口占用

```
bind: address already in use
```

查谁占了：

```bash
lsof -i :8200
# 或
ss -lntp | grep 8200
```

改 `.env` 的 `SENTINEL_PORT`，或杀掉占用进程。

### 7.3 磁盘满

表现：写日志失败、备份失败、SQLite 报 `database or disk is full`。

排查：

```bash
df -h
docker system df
du -sh /var/lib/docker/volumes/sentinel-*
```

处理：清理旧备份（调小 `SENTINEL_BACKUP_KEEP`）、清理 docker 悬空镜像、扩大磁盘。

### 7.4 Webhook 不通

- 用 curl 手动打一遍 webhook 地址，确认对端可达。
- 检查网络出口是否被防火墙拦。
- 检查 URL 是否带多余空格。
- 服务端日志里搜 `webhook` 关键字，会打印失败原因和重试次数。
- 邮件没收到：确认 `SENTINEL_SMTP_HOST/PORT` 可达、发件人/收件人正确；日志搜 `SMTP` 看失败原因；465 端口走 SMTPS，25/587 依赖服务端 STARTTLS。
- 企业微信没收到：用 curl 手动 POST 一条 markdown 消息到 webhook URL；日志搜 `企业微信` 看 errcode；`SENTINEL_WECOM_MENTION_ALL=true` 时正文会带 @all。

### 7.5 SQLite locked

```
database is locked
```

原因：并发写太多。当前实现已做单写者串行化，一般不会出现。若出现：

- 确认没有第二个进程在操作同一个 db 文件。
- 检查是否有外部工具（sqlite3 命令行、备份脚本）长时间持有写锁。
- 用 `PRAGMA journal_mode=WAL;` 提升并发读性能（默认已启用）。

## 8. 资源与限制

- Compose 里限制单实例 1 CPU、512MB 内存，超过会被 cgroup 掐。
- 日志走 `json-file` 驱动，单文件 10MB，最多 5 个，合计上限约 50MB。
- 检查并发上限由 `SENTINEL_CHECK_CONCURRENCY` 控制，同时有 inflight 去重，防止同一个监控项被重复调度。
- 单实例部署。多实例分布式不在当前支持范围，多副本会写坏 SQLite。

## 9. 多渠道告警配置

sentinel 支持三种告警渠道：webhook（原有）、邮件（SMTP）、企业微信群机器人（markdown 消息）。

### 9.1 全局配置

- `SENTINEL_NOTIFY_CHANNELS`：全局默认渠道，逗号分隔，如 `webhook,smtp,wecom`；默认 `webhook`。
- 邮件渠道配 `SENTINEL_SMTP_*`（host 为空则该渠道自动跳过，不报错）。
- 企业微信渠道配 `SENTINEL_WECOM_WEBHOOK_URL`（为空则跳过）；`SENTINEL_WECOM_MENTION_ALL=true` 可 @全体成员。

### 9.2 目标级配置

创建/更新监控时可传 `notify_channels` 字段（逗号分隔，如 `"smtp,wecom"`），只给该目标开指定渠道；留空则继承全局默认。响应 JSON 中同样返回 `notify_channels`（已按小写归一化）。

### 9.3 发送策略

- 状态翻转（down / recovered）时按渠道逐个发送，一个渠道失败不影响其他渠道。
- 每个渠道最多重试 3 次，退避 1s、2s、4s；最终失败记服务端日志（搜 `SMTP` / `企业微信` / `Webhook` 关键字）。
- SMTP：465 端口自动用 SMTPS；25/587 端口服务端支持 STARTTLS 则自动升级；用户名为空则不鉴权。
- 企业微信：服务端返回 errcode 非 0 视为失败并重试。

### 9.4 冒烟验证

```bash
# 起一个本地 fake SMTP 收信（示例用 python，监听 127.0.0.1:1025）
export SENTINEL_SMTP_HOST=127.0.0.1 SENTINEL_SMTP_PORT=1025
export SENTINEL_SMTP_FROM=sentinel@example.com SENTINEL_SMTP_TO=ops@example.com
export SENTINEL_NOTIFY_CHANNELS=smtp
# 另开终端用 httptest/本地服务模拟企业微信 webhook 后再加 wecom

## 10. 告警规则与值班（v0.6 新增）

### 10.1 规则一览

| 规则名 | 级别 | 阈值 | 持续时间 | 含义 |
| --- | --- | --- | --- | --- |
| SentinelInstanceDown | critical | `up{job="sentinel"} == 0` | for 2m | Prometheus 抓不到 sentinel |
| SentinelChecksStalled | warning | `up{job="sentinel"} == 1 and increase(sentinel_checks_total[15m]) == 0` | for 15m | 进程活着但 15 分钟无任何检查 |
| SentinelWebhookQueueBacklogHigh | warning | `sum(sentinel_webhook_queue_backlog) > 50` | for 10m | webhook 队列积压超 50 |
| SentinelWebhookFailureRateHigh | warning | `rate(sentinel_webhook_failures_total[10m]) / rate(sentinel_webhooks_sent_total[10m]) > 0.2` | for 10m | 10 分钟投递失败率超 20% |
| SentinelCheckFailuresSpike | warning | `increase(sentinel_check_failures_total[15m]) > 20` | for 15m | 15 分钟检查失败激增超 20 次 |
| SentinelAPI5xxRateHigh | warning | `sum(rate(sentinel_http_requests_total{status=~"5.."}[5m])) / sum(rate(sentinel_http_requests_total[5m])) > 0.05` | for 5m | sentinel 自身 API 的 5xx 率超 5% |

每条规则的 `annotations.description` 都写了"先查什么"排查步骤。

### 10.2 阈值依据

- 积压 50：默认退避基数 60s、最多 8 次，50 条积压意味着投递能力持续跟不上产生速度，再涨就有丢失风险。
- 失败率 20%：偶发抖动容忍线，持续 10 分钟超 20% 说明下游大面积不可用。
- 失败激增 20 次/15min：单目标按 60s 间隔检查，15 分钟 20 次≈多个目标同时 down 或出口故障。
- 5xx 率 5%：API 自身错误预算。
- 实例 down 2m：抓取间隔 15s，2 分钟确认非抖动。
- 调度停滞 15m：检查间隔通常 ≤60s，15 分钟零增长必有问题。

### 10.3 Prometheus 接入

- `prometheus/` 目录结构：`prometheus.yml` + `rules/sentinel.yml`。
- job 名必须叫 `sentinel`。
- `metrics_path` 必须是 `/api/metrics`。
- `authorization` 必须配 Bearer token（`/api/metrics` 要鉴权，不配会 401 并误报 SentinelInstanceDown）。
- SentinelChecksStalled 的零监控误报前提：零监控部署会持续误报，需删除/禁用该规则。

### 10.4 静默与值班建议

- critical（SentinelInstanceDown）：立即响应，不静默。
- warning：工作时间处理；已知下游 webhook 维护时可对 SentinelWebhookFailureRateHigh / BacklogHigh 做 2 小时静默；批量目标计划内停机前先对 SentinelCheckFailuresSpike 静默。
- 值班看到告警先看规则 annotations.description 里的"先查什么"。

## 11. 运维脚本（v0.6 新增）

### 11.1 scripts/depscan.sh

- 用途：扫描模块依赖漏洞（OSV + govulncheck）。
- 用法：`bash scripts/depscan.sh`。
- 退出码：0=无漏洞 / 1=发现漏洞 / 2=环境缺失。
- 报告路径：`docs/dependency-scan-YYYYMMDD.json`。
- 实测（2026-10-17）：扫描 23 个模块；OSV 查出 3 个（golang.org/x/mod@v0.16.0 的 GO-2026-6179/GO-2026-6180、golang.org/x/sys@v0.22.0 的 GO-2026-5024）；govulncheck 查出 46 个（全部在 Go 标准库，工具链 go1.23.4 太旧所致，第三方模块无漏洞）；报告 `docs/dependency-scan-20261017.json`。
- 环境备注：本机到 api.osv.dev 的 POST 会被出站链路拦截超时，脚本已做降级（OSV 失败不致命，走 govulncheck）。
- 建议每月跑一次，或接入 cron。

### 11.2 scripts/load_check.sh

- 用途：真实负载验证（假目标 + webhook sink，采集检查延迟、事件正确性、队列积压与排空）。
- 用法：`bash scripts/load_check.sh`。
- 退出码：0=全过 / 1=断言失败 / 2=环境缺失。
- 报告路径：`docs/load-test-YYYYMMDD.md`。
- 实测（2026-10-17）：全过。8 个假目标，检查 40 轮，延迟 p50=6.0ms、p99=14.8ms，ok=100%；kill 4 个目标→4 条 down 事件全对、存活目标无误报、webhook 送达 4/4；再停 webhook sink 并 kill 2 个目标→积压峰值 2，sink 恢复后排空成功；总耗时 73s。报告 `docs/load-test-20261017.md`。
- 注意：`/api/metrics` 需带 Bearer token。

```

## 12. 入队限流与投递熔断调参（v0.7 新增）

## 13. 短信告警运维（v0.9 新增）

短信通道的完整运维手册见 docs/OPERATIONS_SMS.md（环境变量/腾讯云前置条件/排障 SQL/成本与限流/回滚步骤），本章不再重复。

### 12.1 环境变量一览

| 变量 | 默认 | 合法范围 | 说明 |
| --- | --- | --- | --- |
| `SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS` | `20` | `0` 或 `0.1`~`10000` | 入队令牌桶速率（每秒）。`0` = 禁用限流；非零须在 `0.1`~`10000`，否则启动 fail-fast。 |
| `SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST` | `40` | `1`~`100000` | 入队令牌桶容量（突发额度），非法启动 fail-fast。 |
| `SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD` | `5` | `1`~`100` | 连续失败达该值即断开下游熔断器，非法启动 fail-fast。 |
| `SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC` | `300` | `10`~`86400` | 断开持续多久后转半开（秒），非法启动 fail-fast。 |

### 12.2 限流：什么时候调

- 默认 `20` rps / `40` burst 够不够：单实例下告警产生速度平时远低于此；故障风暴（几十个目标同时 down）时可能打满。
- 被限流的表现：`sentinel_webhook_enqueue_rejected_total` 增长 + 日志 warn "webhook 入队被限流拒绝"；被拒绝的告警直接丢弃，不会进队列——这是有损的，调参前先确认是真洪峰还是误告警。
- 调参建议：先看 10 分钟拒绝量的峰值，RPS 按"峰值×1.5"给，BURST 按"RPS×2"给；RPS 设 `0` 可彻底禁用（不推荐生产环境禁用）。
- 为什么超限是丢弃而不是排队/429：入队发生在调度器后台 goroutine，没有 HTTP 请求上下文可返回 429；无限排队会把 SQLite 撑爆，丢弃+计数+告警是诚实的有损策略。

### 12.3 熔断：什么时候调

- 默认连续 `5` 次失败断开、断开 `300` 秒后半开探测。
- 下游 webhook 本来就慢/偶发 500：阈值 `5` 可能偏小，可调到 `8`~`10`；超时 `300` 秒偏保守，内网下游可调到 `60`~`120`。
- 半开探测一次只放一个请求，探测成功自动闭合，无需人工干预；用 `sentinel_webhook_breaker_state{host}` 看各下游状态。
- 熔断与指数退避/手动重试的关系：正交。退避决定"失败后何时再试"，熔断决定"下游已死时是否还打它"；手动重试（`/api/alerts/deliveries/{id}/retry`）不受熔断影响，照样把记录打回 pending（但 worker 仍会跳过熔断中的下游）。

### 12.4 观测与排障

- 看限流：`sentinel_webhook_enqueue_rejected_total` 的 increase；告警 `SentinelWebhookEnqueueRejected`。
- 看熔断：`sentinel_webhook_breaker_state` 按 host 拆；告警 `SentinelWebhookBreakerOpen`。
- 启动 fail-fast：四个变量任一非法，进程启动即中文报错退出（exit 1），先修环境变量再起服务。

## 13. 短信通道运维

短信 v2 支持双 provider：aliyun 和 tencent，用 SMSMode 切换，默认走 mock。每次发送由 dispatch 自动记录，结果分 sent 和 failed，provider 名记 aliyun、tencent 或 mock。记录落在 sms_log 表（db migration v9），用 GET /api/sms/log 查，页面上看 /sms-log。

相关环境变量：

- SENTINEL_SMS_MODE：通道模式，可选 mock、aliyun、tencent，默认 mock。
- SENTINEL_SMS_PHONES：接收短信的号码列表。
- 阿里云：SENTINEL_SMS_ACCESS_KEY_ID、SENTINEL_SMS_SECRET、SENTINEL_SMS_SIGN_NAME、SENTINEL_SMS_TEMPLATE_CODE。
- 腾讯云：SENTINEL_SMS_TENCENT_SECRET_ID、SENTINEL_SMS_TENCENT_SECRET_KEY、SENTINEL_SMS_TENCENT_SDK_APP_ID、SENTINEL_SMS_TENCENT_SIGN_NAME、SENTINEL_SMS_TENCENT_TEMPLATE_ID、SENTINEL_SMS_TENCENT_REGION（默认 ap-guangzhou）。

上线检查单：签名和模板先在服务商后台过审；env 配齐；先用 SMSMode=mock 跑一轮，看 /sms-log 里有记录且内容对，再切 aliyun 或 tencent；用真实号码先发一条 down 演练。

费用与防刷：短信按条计费，70 字内一条；只给 down、recovered 这类事件开短信，别全量事件都开；号码配错会导致重复发送，先在 mock 模式看记录。

排障：发不出去先查 /sms-log 的 error 列；腾讯云报签名错误对一下服务器时间（NTP）；阿里云 Code 不是 OK 看 Message；余额不足两个服务商都会在 error 里写清楚。
