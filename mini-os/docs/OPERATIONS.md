# mini-os v1.2.0 运维手册

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

补充说明：
- `SHUTDOWN_TIMEOUT_SECS` 是 v1.2.0 新增。它只管"排空在途请求"这一段，不限制服务运行时长。v1.1.0 曾把它错误地当成整个服务生命周期超时，v1.2.0 已修复。
- 数据库路径、监听地址等如未在表中列出，以实际启动参数 / 现有配置为准；未验证项不在此处臆测。

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

### 5.5 监控现状（诚实说明）

- **Prometheus 指标未接。** v1.2.0 没有 `/metrics` 端点，也没有 Prometheus 集成。
- 现阶段可用的观测手段就是 JSONL 日志 + `health` / `readyz` 两个探针。
- 如果要把 mini-os 接到 Prometheus，需要另做（未在 v1.2.0 范围内）。

---

## 6 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 备份报"目标已存在" | `backup --out` 指定的目标文件已存在，工具拒绝覆盖 | 换一个输出路径，或先移走/删掉已有文件再备 |
| 恢复被拒绝（exit 2） | 目标库已存在，且没加 `--force` | 确认要覆盖就加 `--force`；不确定就先手动备份 |
| 恢复报完整性校验失败（exit 3） | 备份文件 `integrity_check` 不过，文件可能损坏 | 换一个完好的备份；损坏的备份不要强行恢复 |
| 端口占用，服务起不来 | 监听端口已被别的进程占用 | 查占用进程（`ss -lntp` / `lsof -i`），停掉或换端口 |
| `/api/readyz` 返回 503 | DB 不可查（例如文件被移走、损坏、权限问题） | 检查 `DATABASE_PATH` 指向的库是否存在且可读写；必要时从备份恢复 |
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

---

## 附：验证过的数字速查

- 测试：`cargo test` 28 例全过（单元 4：log 3 + migrate 1；API 集成 16；失败注入 8）。
- 静态检查：`cargo clippy --all-targets` 零警告。
- 真实负载：`scripts/load_check.py` 300 文件顺序创建 0 失败，avg 74.93ms，max 138.97ms，30 个抽查内容一致。
- 探针：`/api/health` → 200 `{"status":"ok","version":"1.2.0"}`；`/api/readyz` → DB 可查 200 `{"status":"ready"}`，否则 503 `{"status":"not_ready"}`。
- 退出码：0 成功 / 2 参数错误 / 3 执行失败。
