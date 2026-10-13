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

- `sentinel_monitors_total`：监控项总数
- `sentinel_checks_total{status="up|down"}`：累计检查次数
- `sentinel_check_duration_seconds`：检查耗时直方图
- `sentinel_check_failures_total`：累计失败次数
- `sentinel_incidents_open`：当前未恢复事件数
- `sentinel_http_requests_total{path,code}`：HTTP 请求计数

抓取配置示例：

```yaml
scrape_configs:
  - job_name: sentinel
    static_configs:
      - targets: ['sentinel:8200']
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
