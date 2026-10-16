# mini-os v1.3.0 运维手册

> v1.3 新增：多用户与鉴权、访客只读分享。旧版单用户库可直接升级（迁移 003 自动执行，旧数据归属占位用户 legacy）。

本手册面向把 mini-os 跑在单机上的运维同学。所有命令与行为都对应 v1.2.0 的已验证事实，没验证过的会明确写"未验证"。

mini-os 是 Rust 单二进制服务，Web 框架 axum 0.7，存储用 rusqlite 0.32（bundled + backup feature）打底的 SQLite。默认数据放在一个 SQLite 文件里。

---

## 1 部署

### 1.1 docker-compose 一键部署

仓库根目录带 `docker-compose.yml`，里面已经配好：构建镜像、端口映射、数据卷、日志轮转（10m × 3）、资源限制（1 核 / 512M）。

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

说明：
- 日志轮转在 compose 层配置，单文件最大 10m，最多保留 3 个。
- 资源限制为 1 核 CPU / 512M 内存。
- **本机无 docker daemon，以上 compose 未实际运行验证**。请在目标机器上先跑一次 `docker compose up` 确认，再上生产。

### 1.2 二进制直接跑

Rust 单二进制，无需额外运行时依赖（SQLite 是 bundled 编译进去的）。

```bash
cargo build --release
./target/release/mini-os serve
```

`serve` 会按环境变量（见第 2 节）启动 HTTP 服务。默认监听地址与端口以你的环境变量为准。

### 1.3 systemd unit 示例文本

把下面内容存成 `/etc/systemd/system/mini-os.service`，按你的实际路径改 `WorkingDirectory`、`ExecStart`、`EnvironmentFile` 和用户。

```ini
[Unit]
Description=mini-os v1.2.0
After=network.target

[Service]
Type=simple
User=mini-os
WorkingDirectory=/opt/mini-os
EnvironmentFile=/opt/mini-os/.env
ExecStart=/opt/mini-os/mini-os serve
Restart=on-failure
RestartSec=3
# 优雅关闭：给排空阶段留出时间，kill 信号用 SIGTERM（默认即是）
KillSignal=SIGTERM
TimeoutStopSec=60
# 资源限制（对应 compose 的 1 核 / 512M）
CPUQuota=100%
MemoryMax=512M

[Install]
WantedBy=multi-user.target
```

启动与查看：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mini-os
sudo systemctl status mini-os
journalctl -u mini-os -f
```

注意：服务收到 SIGTERM（`systemctl stop` 默认发 SIGTERM）后会走优雅关闭，见第 5 节。

---

## 2 配置

配置通过环境变量注入。下面是 v1.2.0 支持的环境变量表。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `UPLOAD_MAX_BYTES` | `52428800`（50MB） | 单文件上传大小上限（字节） |
| `SHUTDOWN_TIMEOUT_SECS` | `30` | 优雅关闭排空阶段超时（秒）。只约束收到 SIGTERM/Ctrl+C 后的排空阶段，不掐正常服务（已回归验证） |
| `SESSION_TTL_SECS` | `604800`（7 天） | 登录 session 有效期（秒）；非法/≤0 回落默认值 |
| `MINIOS_LOGIN_RPS` | `1` | 登录限流每秒补充 token 数；非法值启动即报错退出（exit 2） |
| `MINIOS_LOGIN_BURST` | `5` | 登录限流桶容量（突发上限）；非法值启动即报错退出（exit 2） |

补充说明：
- `SHUTDOWN_TIMEOUT_SECS` 是 v1.2.0 新增。它只管"排空在途请求"这一段，不限制服务运行时长。v1.1.0 曾把它错误地当成整个服务生命周期超时，v1.2.0 已修复。
- 数据库路径、监听地址等如未在表中列出，以实际启动参数 / 现有配置为准；未验证项不在此处臆测。

多用户说明：首个注册的用户自动成为管理员；`users` 表存 argon2id 密码哈希（PHC 字符串），`sessions` 表只存 token 的 SHA-256（不明文存 token）；Cookie 名 `mini_os_session`（HttpOnly）。老库升级后旧数据归属不可登录的占位用户 `legacy`，首个注册用户登录后调 `POST /api/auth/migrate-legacy` 一次性领走（只能执行一次）。

---

## 3 备份与恢复

### 3.1 脚本用法

仓库 `scripts/` 下有两个脚本，均已真实跑通。

`backup.sh`（在线备份，保留最近 7 个）：

```bash
./scripts/backup.sh
```

- 在线备份，不需要停服务。
- 自动保留最近 7 个备份，更旧的会被清理。

`restore.sh`（恢复）：

```bash
./scripts/restore.sh <备份文件> [--force]
```

- 脚本会先提示你停服务。
- 不带 `--force` 时，若目标库已存在会拒绝恢复。
- 加 `--force` 才会覆盖目标库。

### 3.1.1 用户数据的备份覆盖
v1.3 的 `users`/`sessions`/`shares` 表与 `vfs_nodes.user_id` 列都在同一个 SQLite 文件里，`backup`/`restore` 整库操作自动覆盖，无需额外步骤。恢复后所有 session 保持有效（除非已过期）；如需强制所有用户重新登录，恢复后执行 `DELETE FROM sessions;`（sqlite3 CLI）。

### 3.2 保留策略

- `backup.sh` 默认保留最近 7 个备份。
- 需要更长保留期就自己再往外层归档（比如 rsync / 对象存储），脚本本身不负责异地归档。

### 3.3 手动 CLI 用法

不想用脚本，可以直接调二进制：

备份：

```bash
mini-os backup --db <数据库路径> --out <备份输出路径>
```

- 目标文件已存在时拒绝覆盖。

恢复：

```bash
mini-os restore --db <数据库路径> --backup <备份文件> [--force]
```

恢复的行为，按顺序：
1. 先对备份文件做 `integrity_check`。不通过就直接失败，退出码 3。
2. 目标库已存在且没给 `--force`，拒绝，退出码 2。
3. 覆盖前自动对原库做快照，文件名形如 `<db>.pre-restore-<epoch秒>.bak`。
4. 原子替换：先写 `<db>.tmp.<pid>`，再 rename 到位。

退出码约定：
- `0`：成功
- `2`：参数错误（例如目标存在且未加 `--force`）
- `3`：执行失败（例如完整性校验不过）

### 3.4 恢复前必停服务

**恢复前务必先停服务。** 恢复会替换数据库文件，服务在跑会拿到不一致的句柄。流程建议：

```bash
sudo systemctl stop mini-os
./scripts/restore.sh /path/to/backup.db --force
sudo systemctl start mini-os
```

脚本本身也会提示先停服务。

---

## 4 升级

### 4.1 版本化迁移

v1.2.0 引入 `schema_migrations` 表做版本化迁移，当前有两步：

- `001`：建 `vfs_nodes` / `settings` 表。
- `002`：新增 `content_blob` / `mime_type` 列。

迁移是幂等的，重复跑不会出问题。

### 4.2 老库自动升级

老库（没有迁移表的）在启动时会自动补齐迁移，**数据保留**。也就是说，把 v1.1.0 的库直接交给 v1.2.0 启动，服务会自动建 `schema_migrations` 并把缺的迁移补上，原有数据不丢。

### 4.3 回滚

回滚方式就是**用备份恢复**。升级前先备份：

```bash
./scripts/backup.sh
```

要回退到旧版本时：

```bash
sudo systemctl stop mini-os
./scripts/restore.sh <升级前的备份> --force
# 换回旧版二进制后启动
sudo systemctl start mini-os
```

注意：迁移是往前的，没做降级迁移。回滚靠的是恢复升级前的备份，不是反向跑迁移。

---

## 5 日志与监控

### 5.1 日志格式

日志是 JSONL，写到 stderr。每行一个 JSON 对象。

访问日志字段：
- `ts`：时间戳
- `level`：级别
- `request_id`：请求 ID
- `method`：HTTP 方法
- `path`：请求路径
- `status`：响应状态码
- `latency_ms`：耗时（毫秒）

事件日志里会出现这些事件名：
- `service_started`
- `shutdown_signal_received`
- `service_stopped`
- `shutdown_timeout`
- `backup_done`
- `restore_done`

### 5.2 request_id 用法

请求头 `x-request-id` 会透传：客户端带了就沿用，没带就自动生成一个，并回写到响应头。排查问题时，拿 `request_id` 在日志里 grep，能把一次请求相关的行串起来。

```bash
journalctl -u mini-os | grep '<request_id>'
```

### 5.3 health / readyz 语义

- `GET /api/health`：存活探针。返回 200，体为 `{"status":"ok","version":"1.2.0"}`。其中 `version` 取自 Cargo.toml。
- `GET /api/readyz`：就绪探针。DB 真实可查时返回 200 `{"status":"ready"}`；否则返回 503 `{"status":"not_ready"}`。

用法建议：存活探针用于判断进程要不要重启，就绪探针用于判断要不要往这个实例导流量。

### 5.4 优雅关闭与日志

收到 SIGTERM 或 Ctrl+C 后：
1. 停止接受新连接。
2. 排空在途请求。
3. 打 `service_stopped`，退出码 0。

`SHUTDOWN_TIMEOUT_SECS`（默认 30）只约束排空阶段，不掐正常服务。排空超时会打 `shutdown_timeout`。

### 5.5 Prometheus `/metrics`

`GET /metrics` 返回 Prometheus 文本格式（`Content-Type: text/plain; version=0.0.4`），手写 exposition、零第三方依赖，可直接被 Prometheus 抓取。

指标一览：

| 指标 | 类型 | 标签 | 说明 |
| --- | --- | --- | --- |
| `http_requests_total` | counter | `method`、`route`、`status` | 请求计数。`route` 取 axum MatchedPath（路由模板，如 `/api/fs/:id`），`status` 为响应状态码 |
| `http_request_duration_seconds` | histogram | `method`、`route` | 请求时长（秒）。桶：0.005/0.01/0.025/0.05/0.1/0.25/0.5/1/2.5/5/10，另有 `+Inf` 桶、`_sum`、`_count` |
| `vfs_ops_total` | counter | `op` | VFS 操作计数：`create`（POST /api/fs）、`update`（PUT /api/fs/{id}）、`delete`（DELETE）、`upload`（上传）、`download`（下载）、`read`（查询） |
| `ws_connections` | gauge | — | 当前 WebSocket 连接数 |
| `vfs_files_total` | gauge | — | VFS 中文件总数（DB 实时 `COUNT(*)`） |
| `vfs_bytes_total` | gauge | — | VFS 文件内容总字节数（DB 实时求和，BLOB 按字节、文本按 UTF-8 字节） |
| `shares_total` | gauge | `type` | 分享总数，按 `type`（`file`/`dir`）分组（DB 实时 `GROUP BY`） |

注意：

- `route` 用的是路由模板而非具体路径，`/api/s/abc123` 会记为 `/api/s/:token`，避免标签基数爆炸；取不到模板时记为 `unknown`（防御性，不应出现）。
- 静态文件兜底（`fallback_service`）的请求不经过指标中间件，不计入 `http_requests_total`；`/metrics` 自身会计入。
- 计数在响应返回后递增，因此一次 `/metrics` 抓取看到的是本次抓取之前的累计值。
- 三个 gauge 是抓取时实时查 DB 算的：文件量很大时每次抓取有一次全表 `COUNT/SUM` 开销，抓取间隔建议 ≥15s；DB 锁异常时 gauge 段跳过、`/metrics` 不 500。

Prometheus 抓取配置示例：

```yaml
scrape_configs:
  - job_name: 'mini-os'
    static_configs:
      - targets: ['127.0.0.1:8090']
    metrics_path: /metrics
    scrape_interval: 15s
```

排障：`curl -s localhost:8090/metrics | head` 应看到 `# HELP` / `# TYPE` 行；若某条业务线计数不动，先确认请求走的是 `/api/*` 路由而非静态文件。

### 5.6 目录分享运维

- 创建：`POST /api/shares` 传 `{"type":"dir","path":"/目录路径"}`（需登录，`path` 按登录用户解析，不存在 404、是文件 400、跨用户 404）。`file` 分享沿用 `{"nodeId":id}`（`type` 缺省即 `file`）。
- 访客浏览：`GET /api/share/list?token=...&path=`（`path` 为分享根下相对路径，缺省为根；返回 `{path, entries:[{name,kind,size,mtime}]}`，文件夹排前面）。访客下载：`GET /api/s/:token/download?path=相对路径`。
- 安全契约：分享整树只读；`path` 含 `..`/空段/控制字符一律 403；只能访问分享根子树内的节点；token 32 位随机 hex，DB 只存原文（无哈希），**泄露即获得只读访问**，请走 HTTPS。
- 生命周期：分享无过期时间、无撤销接口；删除源目录（或其祖先）时 `shares` 行级联删除，分享即失效——这是目前唯一的"撤销"方式。
- 数据：`shares.share_type`（迁移 004，`file`/`dir`，老数据默认为 `file`）；`GET /api/s/:token` 对目录分享返回 `kind:"folder"`、`size` 为整树文件字节数之和。
- 排障：访客 403 先看 `path` 是否含 `..`；404 先确认 token 有效且源目录未被删除；`GET /api/share/list` 对 `file` 分享返回 400（仅目录分享可浏览）。

---

## 6 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 备份报"目标已存在" | `backup --out` 指定的目标文件已存在，工具拒绝覆盖 | 换一个输出路径，或先移走/删掉已有文件再备 |
| 恢复被拒绝（exit 2） | 目标库已存在，且没加 `--force` | 确认要覆盖就加 `--force`；不确定就先手动备份 |
| 恢复报完整性校验失败（exit 3） | 备份文件 `integrity_check` 不过，文件可能损坏 | 换一个完好的备份；损坏的备份不要强行恢复 |
| 端口占用，服务起不来 | 监听端口已被别的进程占用 | 查占用进程（`ss -lntp` / `lsof -i`），停掉或换端口 |
| `/api/readyz` 返回 503 | DB 不可查（例如文件被移走、损坏、权限问题） | 检查 `DATABASE_PATH` 指向的库是否存在且可读写；必要时从备份恢复 |
| 登录后频繁跳回登录页 | session 过期（`SESSION_TTL_SECS`）或 sessions 表被清空 | 重新登录；检查 `SESSION_TTL_SECS` 配置 |
| `/api/*` 返回 401 `{"error":"未登录"}` | Cookie 丢失/过期（跨域或隐私模式） | 确认同源访问、Cookie 未被拦截；重新登录 |
| 启动 panic"无法绑定监听地址" | 监听地址绑定失败（端口被占、地址不可用等） | 确认端口空闲、监听地址正确，再重启 |

排障时优先看 JSONL 日志，用 `request_id` 串请求，用事件名（`service_started` / `backup_done` / `restore_done` 等）定位阶段。

---

## 7 资源限制与日志轮转

### 7.1 compose 里的值

`docker-compose.yml` 已配置：
- 资源限制：1 核 CPU / 512M 内存。
- 日志轮转：单文件 10m，最多 3 个。

（再次提醒：本机无 docker daemon，compose 未实跑验证。）

### 7.2 二进制部署建议

直接跑二进制时，用 systemd 做资源限制（见 1.3 的 `CPUQuota` / `MemoryMax`），日志轮转交给 logrotate。

`/etc/logrotate.d/mini-os` 示例文本（按实际日志路径改）：

```
/var/log/mini-os/*.log {
    daily
    rotate 3
    size 10M
    missingok
    notifempty
    compress
    copytruncate
}
```

说明：mini-os 日志写 stderr，systemd 场景下通常由 journald 接管；若你把 stderr 重定向到文件，就用上面的 logrotate 规则轮转。

---

## 8 故障演练

### 8.1 fault_drill.sh 覆盖项

`scripts/fault_drill.sh` 已真实跑通，覆盖：

- `kill -9` 后重启，数据不丢。
- 备份 → 删库 → 恢复，数据一致。
- 损坏的备份做 `restore`，exit 3 拒绝。
- SIGTERM 优雅关闭，exit 0。
- 超时不掐正常服务回归（验证 `SHUTDOWN_TIMEOUT_SECS` 只约束排空阶段）。

### 8.2 上次演练结论

上次演练结论：`FAULT DRILL PASS`。

### 8.3 建议频率

建议每季度跑一次 `scripts/fault_drill.sh`，覆盖升级、配置变更、宿主变更之后。演练前先确认已有可用备份。

## 9 登录限流调参

登录限流只挂在 `POST /api/auth/login` 上，`GET /api/health`、`GET /api/readyz`、`/metrics` 不限流。

### 9.1 两个旋钮

- `MINIOS_LOGIN_RPS`：每秒补充 token 数，默认 `1`。
- `MINIOS_LOGIN_BURST`：桶容量（突发上限），默认 `5`。

含义（默认值）：一台 mini-os 默认允许每 IP/每账号突发 5 次登录尝试，之后按每秒 1 次回补。

非法值（解析失败、≤0、NaN、无穷大）会在启动时由 stderr 点名变量并 `exit(2)`，服务不起（fail-fast）；未设置则用默认值。

### 9.2 双维度

IP 桶 + 账号（username）桶，任一耗尽即 429。IP 提取优先级：`X-Forwarded-For` 首项 → `X-Real-IP` → `ConnectInfo` → `"unknown"`。

### 9.3 调参建议（建议，非强制）

- 面向公网且被扫爆破时调小（如 `BURST=3 RPS=0.2`）。
- 内网可信环境可放宽。
- `BURST` 至少留 3，给用户连续输错 2 次留余地。

### 9.4 反向代理部署

务必透传 `X-Forwarded-For`。否则所有客户端挤在同一个 `"unknown"` IP 桶里互相牵连（已验证的默认行为，如实写）。

### 9.5 429 契约

响应头 `Retry-After: <整数秒>`，JSON 体 `{"error": "登录尝试过于频繁，请 <N> 秒后重试", "retry_after": <N>}`。

前端 login.html 收到 429 时显示"试得太频繁，N 秒后重试"倒计时，倒计时期间提交按钮 disabled。

### 9.6 监控与排障

- 计数器 `auth_ops_total{op="login_ratelimited"}` 记录被限流次数（`op` 维度已有 register/login/logout/migrate_legacy/share_create）。
- 排障时结合 request_id 日志定位。

---

## 附：验证过的数字速查

- 测试：`cargo test` 28 例全过（单元 4：log 3 + migrate 1；API 集成 16；失败注入 8）。
- 静态检查：`cargo clippy --all-targets` 零警告。
- 真实负载：`scripts/load_check.py` 300 文件顺序创建 0 失败，avg 74.93ms，max 138.97ms，30 个抽查内容一致。
- 探针：`/api/health` → 200 `{"status":"ok","version":"1.2.0"}`；`/api/readyz` → DB 可查 200 `{"status":"ready"}`，否则 503 `{"status":"not_ready"}`。
- 退出码：0 成功 / 2 参数错误 / 3 执行失败。
- v1.3（2026-10-16 验收实测）：`cargo test` 65/65 全过——lib 15（auth 4 + metrics 6 + migrate 2 + log 3 既有）、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、share_test 6；`cargo clippy --all-targets -- -D warnings` 零警告；`cargo fmt --check` 通过；迁移 003 幂等（migrate::tests::migrations_are_idempotent + migration_003_preserves_legacy_data 均过，老库升级冒烟验证通过）。
- 已知限制：无登录限流；仅文件分享；密码策略仅最小长度。

## 告警规则（v1.7+）

规则文件在 `prometheus/rules/mini-os-example.yml`，Prometheus 启动时用 `rule_files` 引进去即可。下面 9 条规则覆盖分享接口探测、403 突增、实例存活、抓取目标存活等场景。

| 规则名 | 含义 | severity |
| --- | --- | --- |
| `MiniOSInstanceDown` | mini-os 实例抓不到了（`up == 0`） | critical |
| `MiniOSHighErrorRate` | HTTP 5xx 占比过高 | critical |
| `MiniOSHighLatency` | 请求延迟过高 | warning |
| `MiniOSShareNotFoundSurge` | 分享 token 枚举探测（`/api/s/:token` 404 占比 > 30%） | warning |
| `MiniOSShareForbiddenSurge` | 分享读三路由 403 占比 > 20%，疑似扫路径穿越 | warning |
| `MiniOSMetricsScrapeFailed` | Prometheus 里没有 mini-os 抓取目标，监控失明 | critical |
| `MiniOSDiskSpaceLow` | 磁盘空间不足 | warning |
| `MiniOSHighMemoryUsage` | 内存占用过高 | warning |
| `MiniOSCertExpiringSoon` | 证书快过期 | warning |

Prometheus 引用规则文件的配置片段：

```yaml
rule_files:
  - /etc/prometheus/rules/mini-os-example.yml
```

### 收到 MiniOSShareForbiddenSurge 后怎么查

1. 先确认告警不是误报：打开 Prometheus 查 `sum(rate(http_requests_total{route=~"/api/s/:token|/api/s/:token/download|/api/share/list",status="403"}[5m])) by (route)`，看是哪个路由在涨。
2. 看日志里 403 的请求路径和来源 IP，mini-os 对非法路径段会返回 403“非法路径”，如果路径里带 `..`、`%2e%2e` 之类的就是有人在扫路径穿越。
3. 看是不是单个 IP 或单个 UA 在刷，是的话先在网关或反代层封掉。
4. 如果来源很分散、量又大，说明是被批量扫描，考虑在网关层加通用规则拦路径穿越，再回来把阈值调高一点。
5. 确认是正常客户端拼错路径导致的，就把这些客户端修掉，或者把规则的分母加最小请求量条件，减少低基数误报。

### 收到 MiniOSMetricsScrapeFailed 后怎么查

1. 先打开 Prometheus 的 Targets 页面，搜 `mini-os`，确认是不是真的没有这个 job 的目标。
2. 没有的话，检查 `prometheus.yml` 里 `scrape_configs` 的 job 名是不是写成别的了，或者这段配置是不是被谁删了。
3. 改完配置记得 reload 或重启 Prometheus，再回 Targets 页面确认目标回来了。
4. 如果配置没问题但目标还是没有，检查 mini-os 的 `/metrics` 端口是不是没起、防火墙是不是挡了。
5. 这条告警意味着监控对 mini-os 完全失明，处理期间 mini-os 的其他告警都别太当真，先把它修好。

