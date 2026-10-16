# linkshort 运维手册

这份手册讲怎么把 linkshort 部署起来、日常怎么备份、升级、监控、排障。命令都可以直接复制改改就用。文中所有端口、路径、环境变量名以代码实际实现为准；仓库里 Makefile、Dockerfile 的具体内容如果和这里描述不一致，以仓库现有文件为准。

---

## 1. 部署

### 1.1 二进制直接跑

从源码构建：

```bash
go build -o bin/linkshort ./cmd/linkshort
```

构建产物在 `bin/linkshort`，直接运行：

```bash
./bin/linkshort
```

仓库里 Makefile 提供了常用目标，具体以仓库现有 Makefile 为准：

```bash
make build   # 构建
make run     # 运行
make test    # 跑测试
```

### 1.2 环境变量启动示例

```bash
export LINKSHORT_ADDR=":8080"
export LINKSHORT_DB="./data/linkshort.db"
export LINKSHORT_ADMIN_KEY="换成你自己的key"
export LINKSHORT_BASE_URL="https://short.example.com"
./bin/linkshort
```

不设 `LINKSHORT_ADMIN_KEY` 时，程序会自动生成一个 32 位 hex 并打印到日志，**重启会变**，生产环境一定要显式设置。

### 1.3 Docker 跑

Dockerfile 是多阶段构建，具体内容以仓库现有 Dockerfile 为准。构建和运行：

```bash
docker build -t linkshort:latest .
docker run -d \
  --name linkshort \
  -p 8080:8080 \
  -v /host/path/linkshort-data:/app/data \
  -e LINKSHORT_ADDR=":8080" \
  -e LINKSHORT_DB="/app/data/linkshort.db" \
  -e LINKSHORT_ADMIN_KEY="换成你自己的key" \
  -e LINKSHORT_BASE_URL="https://short.example.com" \
  linkshort:latest
```

**数据卷很重要**：SQLite 数据库文件默认在 `./data/linkshort.db`。容器里的文件系统是临时的，不把 DB 所在目录挂出来，容器一删数据就没了。上面把宿主机 `/host/path/linkshort-data` 挂到容器 `/app/data`，`LINKSHORT_DB` 指到挂载目录里的文件。

端口映射示例用 `8080:8080`，实际改成你想要的宿主机端口。

### 1.4 Compose 示例

```yaml
services:
  linkshort:
    image: linkshort:latest
    container_name: linkshort
    ports:
      - "8080:8080"          # 按实际改，左边是宿主机端口
    volumes:
      - ./linkshort-data:/app/data   # 把 DB 目录挂出来，别丢数据
    environment:
      LINKSHORT_ADDR: ":8080"
      LINKSHORT_DB: "/app/data/linkshort.db"
      LINKSHORT_ADMIN_KEY: "换成你自己的key"
      LINKSHORT_BASE_URL: "https://short.example.com"
      LINKSHORT_RATE_LIMIT_ENABLED: "true"
      LINKSHORT_RATE_LIMIT_RPS: "20"
      LINKSHORT_RATE_LIMIT_BURST: "40"
    restart: unless-stopped
```

---

## 2. 配置

全部通过环境变量配置，没有配置文件。

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `LINKSHORT_ADDR` | `:8080` | 监听地址，格式 `host:port`，`:8080` 表示所有网卡 8080 端口 |
| `LINKSHORT_DB` | `./data/linkshort.db` | SQLite 数据库文件路径 |
| `LINKSHORT_ADMIN_KEY` | 空 | 管理接口的 API Key。为空时程序自动生成 32 位 hex 并打印到日志，**重启会变**，生产环境必须显式设置 |
| `LINKSHORT_BASE_URL` | 空 | 短链拼接用的基础 URL。为空时用请求的 Host 拼 |
| `LINKSHORT_RATE_LIMIT_RPS` | `20` | 限流令牌桶每秒补充速率（v1.2 新增） |
| `LINKSHORT_RATE_LIMIT_BURST` | `40` | 限流令牌桶容量，允许的瞬时突发量（v1.2 新增） |
| `LINKSHORT_RATE_LIMIT_ENABLED` | `true` | 是否开启限流（v1.2 新增），`true`/`false` |
| `LINKSHORT_BURN_PURGE_AFTER_DESTROY` | `false` | burn 销毁后是否彻底删除行（v1.3 新增），`true`=销毁即删库+404，`false`=仅禁用+410 留档 |
| `LINKSHORT_PURGE_INTERVAL` | `24h` | 定时清理间隔（v1.5 新增），duration 格式如 `24h`/`90m`，解析失败回 `24h` |
| `LINKSHORT_PURGE_RETENTION_DAYS` | `7` | 已销毁 burn 链保留天数（v1.5 新增），`<0` 回 `7` |
| `LINKSHORT_BACKUP_DIR` | `./backups` | 备份目录（backup.sh 与 /api/backup/health 共用）（v1.6 新增） |
| `LINKSHORT_BACKUP_MAX_AGE_DAYS` | `7` | 备份过期阈值天数，超过判降级；`0`=不检查过期（v1.6 新增） |
| `LINKSHORT_ALERT_WEBHOOK_URL` | 空 | 告警 webhook：backup.sh 备份失败时 POST JSON 通知（v1.6 新增）；v1.10 起密码失败高告警复用该地址 |
| `LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD` | `10` | 密码失败高告警阈值：单个短链滑动窗口内密码失败达到该次数触发告警（v1.10 新增），`<=0` 回 `10` |
| `LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW` | `5m` | 密码失败滑动窗口时长（v1.10 新增），duration 格式，解析失败或 `<=0` 回 `5m` |


限流按 IP + API Key 两个维度分别做令牌桶；`/metrics`、`/api/health`、`/api/readyz` 三个路径免限流。

---

## 3. 备份与恢复

现在有 `scripts/backup.sh` 和 `scripts/restore.sh` 两个脚本，用法 `make backup` / `make restore BACKUP=...`。脚本行为：

1. 在线备份，用 sqlite3 `.backup`，不用停服。
2. 备份文件命名 `linkshort-YYYYmmdd-HHMMSS.db`。
3. 备份自带 `PRAGMA integrity_check` 校验；`--keep-days N` 默认 7 天，只删自己命名格式的旧文件。
4. 恢复默认拒绝执行，必须加 `--force`。
5. 恢复先 integrity_check 备份，现有 DB 先做 `.broken-<时间戳>` 快照，清 WAL/SHM，恢复后再次 integrity_check；支持 `--dry-run` 只打印步骤不动数据。

### 自动化演练实测（2026-10-15）

```
[backup] 源: /home/hatch/workspace/muse-build/linkshort-v13/smoke/smoke.db
[backup] 目标: .../backups/linkshort-20261014-234826.db
[backup] 使用 sqlite3 在线备份(.backup)...
[backup] 校验备份完整性(PRAGMA integrity_check)...
[backup] 完成: .../backups/linkshort-20261014-234826.db
[backup] 清理超过 7 天的备份...
[backup] 成功
```

```
$ ./scripts/restore.sh <备份>            → 拒绝，exit=3（"请先停服, 然后加 --force 重试"）
$ ./scripts/restore.sh <备份> --dry-run   → 只打印步骤，exit=0，未做任何修改
$ 停服 → rm smoke.db* → ./scripts/restore.sh <备份> --force → 备份校验通过 → 跳过快照(目标不存在) → 写入 → 恢复后校验通过 → 成功，exit=0
$ 重启后验证：/api/readyz 200；overview {"enabled_links":2,"links":3,"today_clicks":6,"total_clicks":6}；/smk-plain 302；/smk-burn1 410
```

数据库是单个 SQLite 文件（默认 `./data/linkshort.db`）。备份方式两种，任选，推荐在线 `.backup`。

### 3.1 在线备份（推荐，不用停服）

```bash
sqlite3 data/linkshort.db ".backup 'backup.db'"
```

`.backup` 是 SQLite 官方在线备份命令，运行中的库也能安全备份。按时间戳存一份更清晰：

```bash
sqlite3 data/linkshort.db ".backup 'backup-$(date +%Y%m%d-%H%M%S).db'"
```

### 3.2 文件拷贝备份

直接 `cp` 数据库文件。**必须在停服之后做**，或者确认没有写入时用 `.backup`，否则可能拷到不一致的中间状态。

```bash
# 先停掉 linkshort 进程，再执行
cp data/linkshort.db backup-$(date +%Y%m%d-%H%M%S).db
```

如果开了 WAL 模式，`data/` 下可能还有 `-wal`、`-shm` 文件，停服后拷贝主库文件即可（正常关闭会把 WAL 合并回主库）。

### 3.3 恢复步骤

1. 停掉 linkshort 进程（容器的话 `docker stop linkshort`）。
2. 把当前库挪走留个底：`mv data/linkshort.db data/linkshort.db.broken`。
3. 把备份拷回来：`cp backup-YYYYmmdd-HHMMSS.db data/linkshort.db`。
4. 确认文件权限和属主对（运行 linkshort 的用户能读写）。
5. 启动 linkshort，看日志有没有迁移或报错。
6. 验证：`curl http://127.0.0.1:8080/api/readyz` 返回 200，再抽查几条短链能跳。

### 3.4 备份频率建议

- 每天一次。
- 保留 7 天，更早的可以删掉。
- 备份文件放另一块盘或对象存储，别和数据库放同一个目录。

用 cron 每天跑一次的示例：

```bash
0 3 * * * sqlite3 /path/to/data/linkshort.db ".backup '/backup/linkshort-$(date +\%Y\%m\%d).db'" && find /backup -name 'linkshort-*.db' -mtime +7 -delete
```

---

### 3.5 burn 销毁后彻底删除（v1.3）

开关：环境变量 `LINKSHORT_BURN_PURGE_AFTER_DESTROY`，默认 `false`。

- `true`：burn 链首次访问 302 后，行被彻底 DELETE；visits 表通过外键 ON DELETE CASCADE 级联清掉访问日志。之后再访是 404（不是 410）。
- `false`：行为与 v1.2 完全一致——销毁后仅禁用，返回 410「链接已阅销毁」，数据留档。

数据影响：purge 开启后，该链接的 clicks 会从总览统计里消失，总点击/今日点击/Top 链接/Top Referer 都会跟着变。审计需求强的场景保持默认 `false`。

`GET /api/meta` 新增 `burn_purge_after_destroy` 字段，暴露当前开关状态。Prometheus 新增 `linkshort_burn_links_purged_total` 计数器。详情页 burn 链接显示对应文案："销毁后彻底删除" 或 "销毁后仅禁用、数据留档"。

### 3.6 密码保护（v1.4）

- 存储：密码只存 bcrypt 哈希（`links.password_hash`），服务端、日志、API 响应里永不见明文。忘记密码只能清除重设，无法找回。
- 备份：哈希随库文件一起备份，恢复后密码继续有效。注意备份文件本身含哈希，保管要求与数据库文件一致。
- 遗失处理：某条链密码遗失且无人记得 → 用管理 API `PATCH /api/links/{id}` 传 `{"password": ""}` 清除，链接变公开；或直接删链重建。
- 排障：用户报"密码总不对" → 先确认输的不是全角字符/首尾空格（门页按原样比对，不做 trim）；仍不行就清除重设。不要尝试从哈希反推。
- 限流：密码尝试走全局 IP 令牌桶（默认 20 RPS / burst 40），暴力猜解会被 429 挡掉；`linkshort_password_attempts_total{result="fail"}` 持续走高说明有人在猜。

### 3.7 定时清理已销毁 burn 链（v1.5）

后台 goroutine 按 `LINKSHORT_PURGE_INTERVAL` 轮询，删除 `burned_at` 早于"现在 − `LINKSHORT_PURGE_RETENTION_DAYS` 天"的已销毁 burn 链。`burned_at` 为 NULL 的历史行（v1.5 之前销毁的）跳过不删；visits 通过外键级联清除。

- 数据影响：被清理的链接 clicks 会从总览统计里消失（与 v1.3 的立即 purge 一致）。审计需求强就把保留天数设大（如 `365`），不要设 `0`。
- 排障：日志里搜 `[purge]` 看每轮清理结果；`linkshort_links_purged_total` 持续为 0 先查 `GET /api/meta` 的 `purge_interval` / `purge_retention_days` 是否符合预期，再看是否有 burn 链真的到了保留期。
- 与 v1.3 开关的关系：`LINKSHORT_BURN_PURGE_AFTER_DESTROY=true` 时销毁即删行，定时清理扫不到它们；默认 `false` 时才由定时清理兜底。

### 3.8 备份健康自检与失败告警（v1.6）

- 自检：`GET /api/backup/health`（需 API Key）读 `$LINKSHORT_BACKUP_DIR/last-backup.json`（backup.sh 每次运行原子写入），返回最近备份时间、完整性校验结果、目录备份份数；无备份/上次失败/完整性未通过/超过 `LINKSHORT_BACKUP_MAX_AGE_DAYS` 天（默认 7）时 `status` 为 `degraded`，HTTP 状态码仍是 200。
- 告警：`backup.sh` 运行时失败（DB 不存在、备份失败、完整性校验失败等）且配了 `LINKSHORT_ALERT_WEBHOOK_URL` 时，POST JSON 到该 URL：`{"source":"linkshort","event":"backup_failed","host":"...","db_path":"...","backup_dir":"...","error":"...","time":"..."}`。curl 10 秒超时，通知失败不影响脚本退出码；URL 留空则不通知。参数用法错误（exit 2 那几处）不写 sidecar、不告警。
- 指标：`linkshort_backup_last_success_timestamp`（gauge）看最后一次成功备份是多久以前：`time() - linkshort_backup_last_success_timestamp > 86400` 即超过 1 天没成功备份；`linkshort_backup_health_status == 0` 即降级。告警规则示例见 5.3。
- 排障：health 一直 degraded 先看 `reason` 字段；`last-backup.json` 时间戳不动说明 cron 没跑起来或 backup.sh 没权限写目录。

### 3.9 备份恢复自动化演练（v1.7）

`scripts/backup-drill.sh` 一键跑完「备份 → 删库 → 恢复 → 一致性校验」全流程，失败非零退出；`make drill` 等价于无参调用。

用法：

```bash
./scripts/backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N] [-h|--help]
```

- `--addr 127.0.0.1:PORT`：演练服务监听地址，默认 `127.0.0.1:18080`；端口被占则报错退出。
- `--keep`：保留隔离工作区（不清理），结束时打印路径供排查。
- `--timeout N`：等待 `/api/readyz` 就绪的最长秒数，默认 `30`。
- `-h` / `--help`：显示帮助。

演练步骤：

1. `mktemp -d` 建隔离工作区，`trap EXIT` 清理（`--keep` 保留）。
2. 从仓库根 `go build` 演练用二进制。
3. 生成随机 admin key，探测 `--addr` 端口占用。
4. 以隔离 `LINKSHORT_DB` / `LINKSHORT_BACKUP_DIR` 启动服务，轮询 `/api/readyz`。
5. 建三条链：普通（`drill-plain`）、burn+purge（`drill-burn`）、限次（`drill-max`, `max_visits=2`）。
6. 访问造数据：`drill-plain`×3、`drill-max`×2、`drill-burn`×1（再访 404），记录 links 行数 / visits 行数 / clicks 总和为快照。
7. 跑 `scripts/backup.sh`，对备份文件 `PRAGMA integrity_check`，取最新备份路径。
8. 停服（超时则 `kill -9` 记 FAIL）。
9. `rm -f` 删库，模拟灾难。
10. 跑 `scripts/restore.sh <备份> --force`。
11. 重启服务，等 readyz。
12. 一致性校验：行数/点击数一致；`drill-plain` 302；`drill-max` 第 3 次 410；`drill-burn` 404；`GET /api/backup/health` 返回 `status=ok`（健康）而非 `degraded`。

退出码：

- `0`：演练通过。
- `2`：参数或依赖错误（缺 `sqlite3`/`go`/`curl`、端口占用、参数非法）。
- 其他非零：某步骤 FAIL（`[drill] FAIL <步骤名>: <原因>`）。

建议：

- 上线前跑一次，之后每月跑一次。
- cron 示例（每月 1 号 04:00）：

  ```bash
  0 4 1 * * cd /path/to/linkshort && ./scripts/backup-drill.sh >> /var/log/linkshort-drill.log 2>&1
  ```

- CI 定时任务里跑，作为备份可恢复性的持续验证。

注意：

- 演练全程在 `mktemp -d` 隔离目录进行，不碰生产的 `data/` 与 `backups/`。
- 需要排查时加 `--keep` 保留现场。
- 日志里 admin key 只经环境变量传给子进程，不落日志明文。

### 3.10 密码失败高告警（v1.10）

- 机制：`internal/passalert.Tracker` 按 slug 做滑动窗口计数，窗口 `LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW`（默认 5m），窗口内失败达到 `LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD`（默认 10）时触发一次；只在从阈值下方跨越到阈值及以上的那次触发，持续超阈值不重复触发，计数回落到阈值下方后重新布防。
- 触发后三件事：打 warn 日志（含 slug、窗口内失败次数、阈值）；指标 `linkshort_password_fail_alerts_total` +1；若配了 `LINKSHORT_ALERT_WEBHOOK_URL` 则异步 POST JSON：`{"source":"linkshort","event":"password_fail_alert","host":"...","slug":"...","fail_count":N,"window_seconds":300,"threshold":10,"time":"..."}`，HTTP 10 秒超时，通知失败只记日志不影响主流程；URL 留空则不通知。
- 与限流的关系：密码尝试先走全局 IP 令牌桶（429 挡掉的不计入本告警，只统计真正打到密码校验的失败）。
- 排障：告警触发后先查日志里的 slug，再看该 slug 的 `linkshort_password_attempts_total{result="fail"}` 速率；误报就调大阈值/窗口。

## 4. 升级




### 4.1 迁移机制

数据库用 SQLite，靠 `PRAGMA user_version` 做版本化迁移，启动时自动执行。老库从 v1 升到 v2 时会自动 `ALTER TABLE` 加上 `max_visits`、`burn` 两列，**已有数据保留**，不需要手动改库。升级只需要换二进制然后启动。

### 4.2 升级步骤

1. 停服：
   ```bash
   # 二进制方式：给进程发 SIGTERM，或前台 Ctrl+C
   # 容器方式：
   docker stop linkshort
   ```
2. 备份（见第 3 节）：
   ```bash
   sqlite3 data/linkshort.db ".backup 'backup-before-upgrade-$(date +%Y%m%d-%H%M%S).db'"
   ```
3. 换二进制：把新版本 `bin/linkshort` 替换旧的；容器方式重新 `docker build` 后 `docker run`。
4. 启动。
5. 看日志确认迁移成功、没有报错：
   ```bash
   # 二进制前台跑的话直接看输出；容器方式：
   docker logs linkshort
   ```
6. 验证：`curl http://127.0.0.1:8080/api/readyz` 返回 200。

优雅退出：进程监听 SIGINT/SIGTERM，收到信号后最多等 10 秒处理完在途请求再退出。停服时给够这点时间，别用 `kill -9`。

### 4.3 回滚

1. 停服。
2. 把旧版二进制换回来。
3. 用升级前那份备份恢复数据库（见 3.3）。**注意**：新版本可能已经写过新列，回滚到旧版本时旧版本不认识这些列，用备份恢复到升级前状态最稳。
4. 启动，验证 `/api/readyz`。

---

## 5. 监控

### 5.1 Prometheus scrape 配置

```yaml
scrape_configs:
  - job_name: linkshort
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["127.0.0.1:8080"]   # 按实际地址改
```

`/metrics` 不走鉴权，可以直接抓。

### 5.2 可用指标

- `linkshort_http_requests_total{method,route,status}`：按方法、路由、状态码统计的 HTTP 请求数。
- `linkshort_redirects_total{outcome}`：跳转结果，`outcome` 取值 `ok` / `gone` / `not_found` / `error`。
- `linkshort_burn_links_burned_total`：burn 类型链接被销毁的累计数。
- `linkshort_rate_limit_rejected_total`：被限流拒绝的累计数。
- `linkshort_password_fail_alerts_total`：密码失败高告警触发次数（v1.10 新增）。
- `linkshort_process_start_time_seconds`：进程启动时间戳（秒），可用来算运行时长、检测重启。
- `linkshort_links_purged_total`：定时清理删除的已销毁 burn 短链累计数（v1.5 新增）。
- `linkshort_backup_last_success_timestamp`：最近一次备份成功的 unix 秒时间戳，0 表示尚无成功备份（v1.6 新增）。
- `linkshort_backup_health_status`：备份健康状态，1 健康 / 0 降级（v1.6 新增）。

### 5.3 告警规则建议

阈值按你的业务量和习惯调整，下面只给表达式思路，不写死数值。

**就绪探针失败**（DB 连不上或挂了）：

```yaml
- alert: LinkshortNotReady
  expr: up{job="linkshort"} == 0
  for: 1m
  # 阈值和持续时间按业务调整
```

或者直接对 `/api/readyz` 做黑盒探测，返回 503 就告警。

**5xx 比例升高**：

```promql
sum(rate(linkshort_http_requests_total{status=~"5.."}[5m]))
  /
sum(rate(linkshort_http_requests_total[5m]))
```

比例超过多少、持续多久告警，按业务调整。

**限流拒绝突增**：

```promql
rate(linkshort_rate_limit_rejected_total[5m])
```

对比平时基线，明显抬头说明要么被刷，要么正常流量涨了需要调参（见第 7 节）。

**密码失败走高**（v1.10，规则文件 `prometheus/rules/linkshort.yml`）：

```promql
sum(rate(linkshort_password_attempts_total{result="fail"}[5m])) > 0.2
```

持续 2 分钟触发 `LinkshortPasswordFailRateHigh`（warning）；应用内滑动窗口触发的 `linkshort_password_fail_alerts_total` 增长对应 `LinkshortPasswordFailAlertFired`（critical）。阈值按业务调整。

**burn 计数异常**：

```promql
rate(linkshort_burn_links_burned_total[5m])
```

burn 链接是阅后即焚，正常量应该跟业务预期一致；突然猛涨可能是被扫或者有异常访问，结合日志看。

**进程重启检测**：

```promql
changes(linkshort_process_start_time_seconds[10m]) > 0
```

按业务调整告警频率。

**备份相关**（v1.6 新增指标）：

```promql
time() - linkshort_backup_last_success_timestamp > 86400
```

超过 1 天没有成功备份就告警，时长按备份频率调整（每天备份一次就设 86400 秒）。

```promql
linkshort_backup_health_status == 0
```

备份健康降级（无备份/上次失败/完整性未通过/备份过期）。

---

## 6. 排障

| 现象 | 可能原因 | 查什么 |
| --- | --- | --- |
| 返回 401 | API Key 不对或没带 | 请求头里的 key 是否和 `LINKSHORT_ADMIN_KEY` 一致；没设这个变量时程序启动日志里打印的自动生成 key，重启会变，确认用的是当前进程那个 |
| 返回 429 | 被限流 | 看响应头 `Retry-After: 1`，等 1 秒重试；确认是正常流量涨了还是被刷；需要的话调大 `LINKSHORT_RATE_LIMIT_RPS` / `LINKSHORT_RATE_LIMIT_BURST`（见第 7 节） |
| `/api/readyz` 返回 503 | DB ping 不通 | DB 文件权限对不对（运行用户能读写）；磁盘是不是满了；DB 文件是不是被删了；看进程日志 |
| 跳转返回 500 | 数据库故障 | 看日志里的 `request_id`，用它在日志里定位这次请求的详细报错；查 DB 文件是否可写、磁盘是否满 |
| CSV 导入有 skipped | 部分行数据不合法 | 看导入接口返回的 `errors` 数组，里面有每行跳过原因，逐条修数据后重导 |

访问日志里 IP 只存 sha256 的前 16 位 hex，不是明文，这是设计如此，排障时对不上真实 IP 属正常。

---

## 7. 限流调参

三个变量配合：

- `LINKSHORT_RATE_LIMIT_ENABLED`：总开关，默认 `true`。调试或压测时可以临时关掉。
- `LINKSHORT_RATE_LIMIT_RPS`：每秒补充多少令牌，决定长期平均速率，默认 `20`。
- `LINKSHORT_RATE_LIMIT_BURST`：桶容量，决定能扛多大的瞬时突发，默认 `40`。

限流按 IP + API Key 两个维度分别算，任一个超了就 429。`/metrics`、`/api/health`、`/api/readyz` 不参与限流。

什么时候调大：

- 正常业务流量被误伤，日志或指标里 `linkshort_rate_limit_rejected_total` 在业务高峰明显上涨，但没发现异常来源。
- 客户端批量调用（比如脚本批量建链）量大且合法。

什么时候调小：

- 被刷、被扫，`rate_limit_rejected_total` 突增同时请求来源集中。
- 想压一压资源占用。

调参思路：

- 想放宽长期速率，加 `RPS`。
- 想扛更大的瞬时尖峰但平均速率不变，加 `BURST`。
- `BURST` 一般设成 `RPS` 的 1.5～3 倍比较顺手，具体按业务调整。
- 改完环境变量要重启进程生效。

不确定设多少就先按默认跑，观察 `linkshort_rate_limit_rejected_total` 和真实业务量再动。
