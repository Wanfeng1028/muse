# MortiseDB 运维手册

本文档面向运维人员，覆盖日常巡检、故障处理、备份恢复与告警思路。

## 1. 服务启动与停止

### 启动

```bash
mortisedb serve --config /etc/mortise/mortise.yaml
```

服务启动后会：
1. 打开数据库（自动创建父目录、设置 WAL 模式）。
2. 执行 `Migrate()` 建内部系统表（`_m_runs`、`_m_conflicts`、`_m_views`、`_m_watermarks`）。
3. 启动调度器（按 `jobs` 配置周期性执行同步）。
4. 监听 `addr`（默认 `:8421`）。

### Docker Compose 一键部署

适合单机快速起服务，无需在宿主机装 Go 环境；镜像由仓库根目录 `Dockerfile` 多阶段构建（golang:1.23-alpine 编译 → alpine:3.20 运行），产物为 `/app/mortisedb`。

**前置准备**

- `./mortise.yaml`：从 `mortise.yaml.example` 复制后按需修改（数据源、jobs、addr 等）。若不存在，容器内不会有该文件，`serve` 会使用环境变量默认值（`MORTISE_ADDR=:8421`、`MORTISE_DB=/app/data/mortise.db`）。
- `./sources/`：放入你的数据源文件（以只读方式挂进容器 `/app/sources`）。
- `./data/`：无需手动创建，首次启动会自动生成；SQLite 数据库文件为 `./data/mortise.db`。

**启动与查看**

```bash
# 构建并后台启动
docker compose up -d --build

# 查看服务状态（含 health 列）
docker compose ps

# 跟随日志
docker compose logs -f mortisedb

# 停止（数据保留在 ./data 卷中，down 不会丢数据）
docker compose down
```

**升级**

改完代码或拉到新版本后，重新构建并重建容器：

```bash
docker compose up -d --build
```

注意：compose 会先 build 再 recreate，本编排为单副本，重建过程中会有秒级服务中断；对可用性要求高的场景请在外部做流量切换或改为多副本方案。

**Compose 专属排障**

```bash
# 查看容器健康状态（healthy / unhealthy / starting）
docker inspect mortisedb --format '{{.State.Health.Status}}'

# 查看最近一次健康检查的输出
docker inspect mortisedb --format '{{json .State.Health}}'
```

- 刚启动时若看到 `starting` 或 `unhealthy`，先确认是否仍在 `start_period`（15s）内；健康检查探针为 `wget -qO- http://127.0.0.1:8421/api/health`，服务未监听前会失败。
- 宿主机端口冲突：修改 `docker-compose.yml` 中 `ports` 映射，例如把 `"8421:8421"` 改为 `"18421:8421"`，再 `docker compose up -d`。
- `./data` 权限问题：容器内进程以 root 运行并写入 `/app/data`，宿主机对应目录需对当前用户可写（或提前 `chown`/`chmod`）；否则会出现数据库无法创建/写入的报错。
- 容器反复重启：先看 `docker compose logs mortisedb`，常见原因是 `mortise.yaml` 配置错误或数据源路径不存在。

**资源限制与日志**

`docker-compose.yml` 默认限制：

- `mem_limit: 512m`：容器内存上限，超出可能被 OOM kill。
- `cpus: 1.0`：CPU 配额（等价 1 核）。
- 日志轮转：`json-file` 驱动，`max-size: 10m`、`max-file: 3`，单文件最大 10MB、最多保留 3 个。

以上均按需调整；调大内存/CPU 前请确认宿主机余量，调小日志上限可降低磁盘占用。

### 停止

向进程发送 `SIGINT` 或 `SIGTERM`：

```bash
kill -TERM $(pidof mortisedb)
```

v1.1 起的优雅关闭顺序（每步都会结构化日志）：
1. **停止接收新请求**：`http.Server.Shutdown(ctx)` 最多等待 30 秒让在途请求完成。
2. **取消调度器**：`scheduler.Stop()` 会 cancel ctx 并 `wg.Wait()` 等待在途同步任务退出。注意：单次 `Sync` 不支持 ctx 中断，会等待当前表写完后退出循环。
3. **WAL checkpoint**：执行 `PRAGMA wal_checkpoint(TRUNCATE)`，失败只记录 warn。
4. **关闭数据库**：`store.Close()`。

## 2. 日常巡检

### 健康检查

```bash
curl -s http://localhost:8421/api/health
# {"status":"ok","version":"1.1.0"}
```

### 查看最近同步

```bash
curl -s "http://localhost:8421/api/runs?limit=10" | jq
```

### 查看待处理冲突

```bash
curl -s "http://localhost:8421/api/conflicts?status=pending" | jq
```

### 查看系统状态（CLI）

```bash
mortisedb status --config /etc/mortise/mortise.yaml
```

## 3. 备份与恢复

### 3.1 备份

MortiseDB 使用 SQLite 的 `VACUUM INTO` 语法做在线一致性快照，无需停服。

```bash
# 默认输出到 ./backups/mortise-<UTC时间戳>.db
mortisedb backup --config /etc/mortise/mortise.yaml

# 指定输出路径
mortisedb backup --config /etc/mortise/mortise.yaml --output /var/backups/mortise-$(date -u +%Y%m%dT%H%M%SZ).db
```

输出示例：

```
备份完成:
  文件:    /var/backups/mortise-20261013T120000Z.db
  大小:    1048576 字节
  SHA256:  a1b2c3...
  耗时:    123ms
  元信息:  /var/backups/mortise-20261013T120000Z.db.meta.json
```

备份会同时生成 `<备份文件>.meta.json`，包含：
- `created_at`：备份创建时间（RFC3339 UTC）
- `source_db`：源数据库路径
- `size_bytes`：备份文件大小
- `sha256`：备份文件 SHA256 摘要
- `version`：备份格式版本（`1.1.0`）

### 3.2 cron 定时备份示例

```cron
# 每天凌晨 3 点备份，保留最近 14 份
0 3 * * * cd /var/lib/mortise && \
  mortisedb backup --config /etc/mortise/mortise.yaml \
    --output /var/backups/mortise-$(date -u +\%Y\%m\%dT\%H\%M\%SZ).db >> /var/log/mortise-backup.log 2>&1 && \
  find /var/backups -name 'mortise-*.db' -mtime +14 -delete
```

> 注意：cron 中的 `%` 需要转义为 `\%`。

### 3.3 恢复

```bash
# 目标库不存在时直接恢复
mortisedb restore --config /etc/mortise/mortise.yaml --from /var/backups/mortise-20261013T120000Z.db

# 目标库存在且非空时，必须加 --force
# 旧库会先被改名为 <目标>.bak-<时间戳> 留底，再原子替换
mortisedb restore --config /etc/mortise/mortise.yaml \
  --from /var/backups/mortise-20261013T120000Z.db --force
```

恢复流程：
1. `Verify` 备份文件：只读打开 + `PRAGMA integrity_check`（要求单行 `ok`）+ 检查 `_m_watermarks` 表存在。
2. 目标存在且非空且无 `--force` → 拒绝。
3. `--force` 时先将旧库改名为 `*.bak-<UTC时间戳>`。
4. 复制备份到 `<目标>.tmp-restore`，`os.Rename` 原子替换。

恢复完成后会打印用户表数与水位线条数作为一致性证据。

### 3.4 恢复演练步骤

每季度至少执行一次：

1. 选一台隔离机器，安装相同版本的 `mortisedb`。
2. 复制一份最新备份（`.db` + `.meta.json`）到该机器。
3. 校验备份文件 SHA256 与 `.meta.json` 中的一致：
   ```bash
   sha256sum /path/to/backup.db
   ```
4. 执行 `mortisedb restore` 到临时路径（不覆盖生产配置指向的库）。
5. 执行 `mortisedb status` 与 `mortisedb query` 抽查数据。
6. 记录演练时间、备份文件、恢复耗时、校验结果。

### 3.5 关键点

- 备份期间服务可正常读写（`VACUUM INTO` 只持读锁）。
- 备份文件与元信息必须**一起保存**，恢复时以 `.db` 为准，元信息用于审计。
- `restore` 到非空目标时旧库留底文件会累积，需纳入清理策略。

## 4. 可观测性（/metrics）

### 4.1 抓取

```bash
curl -s http://localhost:8421/metrics
```

响应为 Prometheus text exposition 格式（`text/plain; version=0.0.4`）。抓取时会实时计算水位线滞后、待处理冲突数与数据库文件大小。

### 4.2 本地告警思路

最简单的方式：cron 定时抓取 `/metrics`，检测 `mortise_conflicts_pending > 0` 即发送告警（可接 `mail`、`curl` webhook 等）。

```bash
# 每 5 分钟检查一次
*/5 * * * * curl -s http://localhost:8421/metrics | \
  awk '/^mortise_conflicts_pending / { if ($2 > 0) exit 1 }' || \
  echo "MortiseDB 存在待处理冲突" | mail -s "[告警] MortiseDB 冲突待处理" ops@example.com
```

其他可关注的指标：
- `mortise_watermark_lag_seconds`：水位线滞后秒数，持续增长说明源端同步滞后。
- `mortise_sync_runs_total{status="error"}`：同步失败累计次数，短时间内快速增长需排查。
- `mortise_db_size_bytes`：库大小趋势，异常增长需检查是否有大批量数据灌入。

## 5. 物化视图

### 5.1 声明方式

在 `mortise.yaml` 的视图条目下加 `materialize` 块：

```yaml
views:
  - name: monthly_sales
    sql: SELECT ...
    materialize:
      enabled: true
      refresh: on_sync   # on_sync | manual | interval:30m
```

`enabled: true` 要求视图名为合法标识符（`^[A-Za-z_][A-Za-z0-9_]*$`），物化表名为 `_mv_<视图名>`。

### 5.2 刷新策略

- `on_sync`（默认）：每次 `mortisedb sync` 成功后自动刷新。
- `manual`：仅手动触发（CLI / API），sync 时跳过。
- `interval:<时长>`（如 `interval:30m`、`interval:6h`）：距上次刷新超过该时长才刷新，否则跳过；从未刷新的视为到期。

YAML 里改策略或取消 `materialize` 块，下次 sync 自动生效；取消物化会 `DROP TABLE` 删掉旧物化表。

### 5.3 手动刷新

```bash
# CLI
mortisedb views refresh --config /etc/mortise/mortise.yaml monthly_sales
# 已刷新视图 monthly_sales，写入 1280 行

# API
curl -s -X POST http://localhost:8421/api/views/monthly_sales/refresh
# {"name":"monthly_sales","rows":1280,"duration_ms":42}
```

### 5.4 监控指标

- `mortise_view_refresh_total{view,status}`：刷新次数，status ∈ ok/error。
- `mortise_view_refresh_duration_seconds{view}`：刷新耗时分布。
- `mortise_view_last_refresh_rows{view}`：上次刷新写入行数。

### 5.5 注意事项

- 物化刷新是**全量**的：事务内 `DROP TABLE` + `CREATE TABLE AS`，失败回滚，旧物化表不受影响；但大视图刷新期间 sync 会变慢。
- `views list` 会显示物化标记、刷新策略与上次刷新时间；Web UI 视图页同样可见，并可一键刷新。

## 6. 常见故障


### 6.1 服务启动失败：端口占用


检查 `addr` 是否被占用：

```bash
ss -ltnp | grep 8421
```

### 6.2 同步失败：源文件不存在


日志会输出结构化错误，含 `source` 与 `error` 字段。检查 `mortise.yaml` 中 `path` 是否正确。

### 6.3 冲突积压

```bash
# 查看待处理冲突
mortisedb query --config /etc/mortise/mortise.yaml \
  "SELECT id, table_name, pk, source_a, source_b, created_at FROM _m_conflicts WHERE status='pending'"
```

处理方式：
- 通过 Web UI 或 `POST /api/conflicts/{id}/resolve` 逐条解决。
- 或调整 `sync.priority` 让优先级更高的源自动胜出。

## 7. CSV 增量导入

### 7.1 端点与字段

新端点 `POST /api/import/csv`（multipart 上传）。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 要导入的 CSV 文件 |
| `source` | 是 | 源名 |
| `table` | 否 | 目标表，默认取源的 `table` |
| `primary_key` | 否 | 主键列，默认取源的 `primary_key` |
| `column_mapping` | 否 | JSON 字符串，形如 `{"订单号":"order_id"}` |

旧端点 `POST /api/sources/{id}/import-csv` 保留，行为兼容，内部已走流式实现。

### 7.2 列映射

`column_mapping` 是 `{"CSV列名":"目标列名"}` 形式的 JSON。没写进映射的列，按 CSV 里的原名直通。映射后的列名必须非空、唯一，并且匹配 `^[A-Za-z_][A-Za-z0-9_]*$`，否则返回 400。主键列必须在映射后的列集合里，否则返回 400。

### 7.3 错误码

| 错误码 | 场景 |
| --- | --- |
| 400 | 非法映射 JSON / 非法目标列名 / 缺主键 / 空文件 / 表头问题 / 缺 source |
| 404 | 源不存在 |
| 409 | 本批有冲突挂起 |
| 413 | 文件超过 32MB |

### 7.4 流式与 32MB 限制

文件内容落盘到 `<dbdir>/.import-tmp/` 临时文件（用 `os.CreateTemp` 创建，处理完删除），不会一次读进内存。文件超过 32MB 返回 413。写盘时边写边算 sha256。

### 7.5 幂等

同一个 source 加同一个文件 sha256，如果命中 `_m_imports`，直接返回 `duplicate=true` 和上次的统计，不再重复导入。

### 7.6 增量语义

按主键 upsert，只写变更行（用行哈希比对）。响应字段：`total_rows/inserted/updated/unchanged/error_rows/errors[]/errors_truncated/file_hash`。逐行错误记成 `{line,reason}`，覆盖列数不符、主键为空、坏引号行三类。错误列表上限 100 条，遇到坏行跳过继续处理。

### 7.7 冲突挂起处理流程

冲突策略与 sync 一致。当源 `sync.conflict=manual`，且主键已存在、行哈希不同、现有行来源与本源不同时，不覆盖，写 `_m_conflicts`（`source_a` 是现有方来源名、`source_b` 是挑战方来源名、`row_json` 是挑战方行数据 JSON、`status` 为 `pending`）。本批有挂起冲突时返回 HTTP 409 加冲突数组（与 `GET /api/conflicts` 同形状）。`priority` 按 `sync.priority` 源顺序自动裁决，胜出方覆盖并记 `resolved_auto`。同源更新直接覆盖，并自动解决该 pk 的 pending。

处理流程：

1. 收到 409 后查 `GET /api/conflicts`。
2. 在 Web UI 冲突页处理，或调 `POST /api/conflicts/{id}/resolve` 裁决。

### 7.8 Web UI

新增"导入"页：选数据源、选 CSV 文件、填目标表/主键（可选）、填列映射 JSON（可选）、上传。结果展示 inserted/updated/unchanged/error_rows 和错误列表。有挂起冲突时用朱砂色提示，并跳冲突页。

## 8. 版本历史


- **1.4.0**：CSV 增量导入 API（`POST /api/import/csv`：列映射/真流式/冲突策略集成/409；Web UI 导入页）。
- **1.2.0**：YAML 声明视图自动注册（sync/serve/views sync 幂等注册+清理，_m_views 新增 origin 列）、e2e 编排脚本（scripts/e2e.sh）、docker-compose 一键部署（健康检查+资源限制+日志轮转）。
- **1.1.0**：新增 `/metrics`、`backup`/`restore` 子命令、优雅关闭补强（HTTP 超时 + WAL checkpoint + 在途等待）、10 万行负载验证。
- **0.1.0**：首个可用版本（多源同步、冲突策略、视图、调度、Web UI）。
