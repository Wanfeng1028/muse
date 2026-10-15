# ledger 运维手册（v2.1）

本文档面向部署与运维 ledger 的工程师。ledger 是单用户本地记账应用，SQLite 单文件存储，无鉴权、无多实例能力。以下命令与环境变量均与代码实现一致。

## 1. 部署

### 1.1 Docker Compose 一键部署

在项目根目录（含 `docker-compose.yml` 与 `Dockerfile`）执行：

```
docker compose up -d --build
```

验证：

```
docker compose ps
curl -s http://127.0.0.1:8100/api/health
```

预期返回：

```
{"status":"ok","version":"2.1.0"}
```

停止与清理：

```
docker compose down          # 停止并删除容器，保留数据卷
docker compose down -v       # 连同数据卷一起删除（会丢失数据库与备份）
```

### 1.2 裸机部署

```
make install
make run
```

或不通过 Makefile，直接启动服务：

```
python -m ledger
```

`python -m ledger` 等价于 `python -m ledger serve`，默认启动 HTTP 服务。

### 1.3 端口与数据目录

- 默认监听 `127.0.0.1:8100`（裸机），容器内通过 `LEDGER_HOST=0.0.0.0` 对外暴露，端口映射为 `8100:8100`。
- 数据库默认路径 `data/ledger.db`（相对项目根）。容器内固定为 `/app/data/ledger.db`。
- 备份默认目录 `<项目根>/data/backups`。容器内固定为 `/app/data/backups`，与数据库同处 `ledger-data` 卷内。

## 2. 配置

环境变量共 5 个：

| 变量 | 默认值 | 说明 | 非法值行为 |
| --- | --- | --- | --- |
| `LEDGER_DB` | `data/ledger.db` | 数据库文件路径；相对路径相对项目根 | 路径不可写/目录不存在时启动或运行期报错 |
| `LEDGER_HOST` | `127.0.0.1` | 监听地址 | 地址非法时由 uvicorn 启动失败 |
| `LEDGER_PORT` | `8100` | 监听端口 | 非整数或端口被占用时启动失败 |
| `LEDGER_LOG_LEVEL` | `INFO` | 日志级别，取值 DEBUG/INFO/WARNING/ERROR/CRITICAL | 非法值启动 fail-fast |
| `LEDGER_BACKUP_DIR` | `<项目根>/data/backups` | 备份目录 | 目录不可写时备份命令失败 |

## 3. 备份与恢复

### 3.1 备份

```
make backup
make backup KEEP=14
```

等价 CLI：

```
python -m ledger backup
python -m ledger backup --dir /path/to/backups --keep 14
```

- 默认保留 7 个备份（`--keep` / `KEEP` 可覆盖）。
- 备份文件名格式：`ledger-YYYYMMDD-HHMMSS.db`（同秒多次备份加 `-N` 后缀）。
- 备份前对源库执行 `PRAGMA integrity_check`，校验失败则拒绝生成备份。

### 3.2 恢复

```
make restore FILE=data/backups/ledger-20250101-120000.db
```

等价 CLI：

```
python -m ledger restore data/backups/ledger-20250101-120000.db
python -m ledger restore data/backups/ledger-20250101-120000.db --dir /path/to/backups
```

- 恢复前会自动对当前库做一次安全快照，快照保留 30 个。
- 若待恢复文件自身 `integrity_check` 不通过，恢复被拒绝，当前库不受影响。

### 3.3 手动演练（备份 → 删库 → 恢复 → 验证）

以下命令在项目根目录执行。演练前请确认已有可用备份。

```
# 1) 备份当前库
make backup

# 2) 记录当前数据规模（用于恢复后对比）
python -m ledger serve &
SRV=$!
sleep 2
curl -s http://127.0.0.1:8100/api/metrics | grep ledger_transactions_total
kill $SRV

# 3) 模拟误删：删除数据库文件
rm -f data/ledger.db

# 4) 从最近一次备份恢复（文件名按实际替换）
ls -1 data/backups/
make restore FILE=data/backups/ledger-20250101-120000.db

# 5) 启动并验证数据
python -m ledger serve &
SRV=$!
sleep 2
curl -s http://127.0.0.1:8100/api/health
curl -s http://127.0.0.1:8100/api/ready
curl -s http://127.0.0.1:8100/api/metrics | grep ledger_transactions_total
kill $SRV
```

第 5 步中 `/api/health` 返回 `{"status":"ok","version":"2.1.0"}`、`/api/ready` 返回 `{"ready":true}`、`ledger_transactions_total` 与第 2 步一致，即恢复成功。

## 4. 升级

### 4.1 v1 → v2.1 自动迁移

迁移基于 SQLite 的 `PRAGMA user_version`，当前版本为 2。

- v1 老库（仅含 accounts / categories / transactions / budgets / recurring 五张表）在启动时自动补齐 4 张 v2 表：statement_templates、match_rules、statement_batches、statement_items。
- 无需任何手动操作，启动即完成迁移。

### 4.2 损坏库报错

数据库文件损坏时启动报错 `MigrationError`。此时不要继续启动服务，改用备份恢复：

```
make restore FILE=data/backups/ledger-20250101-120000.db
```

### 4.3 回滚

升级前先做一次备份，回滚即用该备份恢复：

```
make backup
# 升级并运行 v2.1
# 如需回滚：
make restore FILE=data/backups/ledger-<升级前时间戳>.db
```

注意：恢复的是数据库文件内容，若已用 v2.1 写入 v2 表数据，回滚到 v1 代码后这些表不会被 v1 使用。

## 5. 监控

### 5.1 指标（GET /api/metrics，Prometheus 文本格式）

| 指标 | 含义 |
| --- | --- |
| `ledger_statement_batches_total` | 累计导入的账单批次总数 |
| `ledger_statement_items_total{status}` | 按状态分组的账单条目数 |
| `ledger_detective_pending` | 侦探队列待认领条目数（statement_items 中 status='pending' 的行数） |
| `ledger_auto_match_rate` | 自动匹配率（各批次 auto_count/total_count 汇总） |
| `ledger_transactions_total` | 交易总数 |
| `ledger_accounts_total` | 未归档账户总数 |

就绪探测使用 `GET /api/ready`：数据库连通返回 200 `{"ready":true}`，不通返回 503。

### 5.2 日志格式

日志输出到 stderr，JSON Lines，每条一行：

```
{"ts":"2025-01-01T12:00:00.123456+00:00","level":"INFO","logger":"ledger.http","msg":"request","request_id":"3f2a9c1e8b7d","method":"GET","path":"/api/health","status_code":200,"duration_ms":1.87}
```

字段：`ts` / `level` / `logger` / `msg` / `request_id`（12 位 hex，无请求头时自动生成），中间件额外记录 `method` / `path` / `status_code` / `duration_ms`，并把 `request_id` 回写到响应头 `X-Request-Id`。

### 5.3 用 request_id 排障

先拿到响应头中的 request_id：

```
curl -s -D - http://127.0.0.1:8100/api/health -o /dev/null | grep -i x-request-id
```

再在日志中按该 id 检索（容器部署时）：

```
docker compose logs ledger | grep 3f2a9c1e8b7d
```

裸机部署时若日志重定向到文件，同样用 `grep <request_id> <logfile>`。

未处理异常会返回 500：

```
{"detail":"服务器内部错误","request_id":"3f2a9c1e8b7d"}
```

用返回体中的 `request_id` 去日志里定位对应堆栈。

## 6. 排障

**Q：启动报端口被占用。**
A：`LEDGER_PORT` 默认 8100。改端口或释放占用进程：

```
LEDGER_PORT=8200 python -m ledger
```

容器部署时改 `docker-compose.yml` 的 `ports` 与 `LEDGER_PORT`。

**Q：`LEDGER_LOG_LEVEL` 写错导致启动失败。**
A：非法值 fail-fast。取值只能是 DEBUG/INFO/WARNING/ERROR/CRITICAL，改正后重启。

**Q：启动报数据库损坏（MigrationError）。**
A：数据库文件损坏。用备份恢复：`make restore FILE=<备份文件>`。

**Q：磁盘满导致备份失败。**
A：备份在 `LEDGER_BACKUP_DIR`（默认 `data/backups`，容器内 `/app/data/backups`）。清理旧备份或扩容后重试。`--keep` / `KEEP` 控制保留数量，可调小。

**Q：CSV 导入返回 500。**
A：该问题已修复：解析期的 `csv.Error` 会被转换为逐行的 errors 结果返回，不再以 500 抛出。若仍见 500，用响应头 `X-Request-Id` 到日志中查堆栈。

**Q：依赖装不上。**
A：确认 Python 版本 ≥ 3.11（Docker 镜像为 3.12），使用干净虚拟环境重装：

```
python -m venv .venv
. .venv/bin/activate
make install
```

## 7. 已知限制

- 单用户本地应用，无鉴权，不要直接暴露到公网。
- SQLite 单文件存储，写入并发能力有限。
- 不支持多实例部署；同一数据库文件只能由一个进程写入。
- 无高可用与集群能力，备份/恢复是唯一的容灾手段。
