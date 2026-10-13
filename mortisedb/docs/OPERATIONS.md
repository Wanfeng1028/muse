mkdir -p /backup/mortisedb/$(date +%F)
sqlite3 data/mortise.db ".backup '/backup/mortisedb/$(date +%F)/mortise.db'"
cp mortise.yaml /backup/mortisedb/$(date +%F)/mortise.yaml

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

## 5. 常见故障

### 5.1 服务启动失败：端口占用

检查 `addr` 是否被占用：

```bash
ss -ltnp | grep 8421
```

### 5.2 同步失败：源文件不存在

日志会输出结构化错误，含 `source` 与 `error` 字段。检查 `mortise.yaml` 中 `path` 是否正确。

### 5.3 冲突积压

```bash
# 查看待处理冲突
mortisedb query --config /etc/mortise/mortise.yaml \
  "SELECT id, table_name, pk, source_a, source_b, created_at FROM _m_conflicts WHERE status='pending'"
```

处理方式：
- 通过 Web UI 或 `POST /api/conflicts/{id}/resolve` 逐条解决。
- 或调整 `sync.priority` 让优先级更高的源自动胜出。

## 6. 版本历史

- **1.1.0**：新增 `/metrics`、`backup`/`restore` 子命令、优雅关闭补强（HTTP 超时 + WAL checkpoint + 在途等待）、10 万行负载验证。
- **0.1.0**：首个可用版本（多源同步、冲突策略、视图、调度、Web UI）。
