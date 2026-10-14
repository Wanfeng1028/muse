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

限流按 IP + API Key 两个维度分别做令牌桶；`/metrics`、`/api/health`、`/api/readyz` 三个路径免限流。

---

## 3. 备份与恢复

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
- `linkshort_process_start_time_seconds`：进程启动时间戳（秒），可用来算运行时长、检测重启。

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
