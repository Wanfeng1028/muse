# 榫卯 MortiseDB

Airbyte/dbt 对个人太重，Metabase 只读不拼装——这是 NAS 玩家和小团队的本地数据拼装层。

榫卯是一块 Go 单二进制：纯 Go SQLite 驱动（modernc.org/sqlite，无 CGO），无需 Docker、无需 Python 环境、无需外接数据库。你写一份 YAML，把散落在 NAS 各处的 SQLite、CSV、JSON、本地目录声明成表，它负责推断 schema、统一类型、增量同步、按源优先级裁决冲突，再用类 SQL 视图把结果拼起来，Web 上直接看，也可以导出 CSV。所有数据落在本地一个 SQLite 文件里，能跟着 Git 走。

## 截图

![总览](docs/screenshots/overview.png)

首页总览：已声明表数量、上次同步时间、待处理冲突数、最近运行结果一览。

![同步](docs/screenshots/sync.png)

同步页：每个源的水位线位置、本次拉取行数、被哈希兜底捕获的变更记录。

![数据](docs/screenshots/data.png)

数据浏览：按表查看已同步内容，类型已统一，主键去重后的最终态。

![视图](docs/screenshots/views.png)

视图页：类 SQL 视图的运行结果，可保存、可定时、可一键导出 CSV。

## 3 步快速开始

```bash
# 1. 初始化：生成 mortise.yaml 骨架和本地数据文件
./mortisedb init

# 2. 按需编辑 mortise.yaml，声明你的数据源、主键、冲突策略
$EDITOR mortise.yaml

# 3. 同步一次，然后起服务（默认 :8421）
./mortisedb sync
./mortisedb serve
```

`serve` 启动后打开 `http://localhost:8421` 即是 Web UI。定时任务与运行历史在 UI 里配置，也可以用 `./mortisedb run --schedule` 挂后台。

## 为什么不用 Airbyte / dbt / Metabase

| 方案 | 定位 | 对个人的重 |
| --- | --- | --- |
| Airbyte | 企业级 ELT 平台，几百个 connector | 要 Docker Compose 一整套、要 Postgres 元数据库、要维护 worker，为一个 CSV 起一舰队 |
| dbt | 数仓内的 SQL 转换框架 | 假设你已经有数仓，转换逻辑绑在 warehouse 上，本地小文件不在它的视野里 |
| Metabase | BI 查询与可视化 | 只读不拼装，多源合并不归它管，且同样需要外接数据库 |

结论：这三件工具各自解决的是"团队已有数仓之后"的问题，而榫卯解决的是"还没有数仓、只有一堆本地文件"的问题——单二进制、单文件落盘、YAML 声明，正好够用。

## 架构

```mermaid
flowchart LR
    Y[mortise.yaml] --> C[connector: SQLite / CSV / JSON / 目录]
    C --> I[infer: schema 推断]
    I --> S[sync: 水位线 / 哈希 / 冲突]
    S --> D[(SQLite: _m_ 系统表)]
    D --> CLI[CLI]
    D --> API[HTTP API]
    API --> UI[Web UI]
```

系统表说明：`_m_tables` 记录已声明表的元信息与 schema 版本；`_m_watermarks` 保存每个源的 `updated_at` 水位线；`_m_conflicts` 存放按策略挂起、等待手动裁决的冲突行；`_m_runs` 是每次同步/视图运行的执行历史；`_m_views` 保存视图定义与导出记录。

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 存活探针 |
| GET | `/api/sources` | 数据源列表（含表结构与行数） |
| POST | `/api/sync` | 触发全量同步 |
| GET | `/api/runs` | 同步运行历史 |
| GET | `/api/conflicts` | 待处理冲突列表 |
| POST | `/api/conflicts/{id}/resolve` | 裁决冲突 |
| GET | `/api/tables` | 已同步表列表 |
| GET | `/api/tables/{name}/rows` | 查表数据 |
| GET | `/api/views` | 视图列表 |
| POST | `/api/views` | 新增视图 |
| DELETE | `/api/views/{name}` | 删除视图 |
| GET | `/api/views/{name}/rows` | 查视图数据 |
| POST | `/api/views/{name}/refresh` | 手动物化刷新 |
| POST | `/api/query` | 即席 SQL 查询 |
| POST | `/api/sources/{id}/import-csv` | CSV 增量导入（multipart `file` 字段；按主键 upsert；文件 sha256 幂等；逐行错误报告 `{line,reason}` 跳过继续；响应含 inserted/updated/unchanged/error_rows；v1.4 新增） |
| POST | `/api/import/csv` | CSV 增量导入 v2（multipart：`file`/`source` 必填，`table`/`primary_key`/`column_mapping` 可选；列映射；真流式 32MB 上限；冲突挂起时 409；v1.4 新增） |
| GET | `/metrics` | Prometheus 指标 |

## 配置示例

```yaml
version: 1
database: ./mortise.db

sources:
  # 源 1：另一个 SQLite 文件，靠 updated_at 增量
  - name: notes_db
    type: sqlite
    path: /volume1/notes/notes.db
    table: notes
    primary_key: id
    incremental:
      column: updated_at
      fallback_hash: true
    conflict: priority

  # 源 2：CSV 导出，没有更新时间戳，纯哈希兜底
  - name: finance_csv
    type: csv
    path: /volume1/finance/ledger.csv
    table: ledger
    primary_key: entry_id
    infer:
      sample_rows: 500
      types:
        amount: decimal
        date: datetime

  # 源 3：本地目录，文件名与 mtime 映射成列
  - name: media_dir
    type: directory
    path: /volume1/media
    table: media_files
    primary_key: rel_path
    columns:
      rel_path: text
      size: integer
      mtime: datetime
    recursive: true

conflict:
  strategy: priority          # priority | manual | soft_delete
  priority: [notes_db, finance_csv, media_dir]
  soft_delete:
    mark_column: _m_deleted
    retention_days: 30

views:
  - name: recent_spend
    sql: |
      SELECT l.date, l.amount, n.title
      FROM ledger l
      LEFT JOIN notes n ON n.id = l.note_id
      WHERE l.date >= date('now', '-30 day')
```

## 可观测性

### `/metrics`

MortiseDB v1.1 起暴露 Prometheus text exposition 格式的 `/metrics` 端点：

```bash
curl -s http://localhost:8421/metrics | head -40
```

关键指标：

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `mortise_build_info{version}` | Gauge | 构建版本，值恒为 1 |
| `mortise_sync_rows_total{source,table,op}` | Counter | 同步行数，op ∈ inserted/updated/deleted/skipped/conflicts |
| `mortise_sync_runs_total{job,status}` | Counter | 同步运行次数，status ∈ ok/error |
| `mortise_sync_last_duration_seconds{source}` | Gauge | 最近一次同步耗时 |
| `mortise_view_duration_seconds_{count,sum}{view}` | Summary | 视图执行耗时 |
| `mortise_view_last_duration_seconds{view}` | Gauge | 最近一次视图耗时 |
| `mortise_view_refresh_total{view,status}` | Counter | 物化视图刷新次数，status ∈ ok/error |
| `mortise_view_refresh_duration_seconds_{count,sum}{view}` | Summary | 物化视图刷新耗时 |
| `mortise_view_last_refresh_rows{view}` | Gauge | 物化视图上次刷新行数 |

| `mortise_watermark_lag_seconds{source,table}` | Gauge | 水位线滞后秒数（抓取时实时计算） |
| `mortise_conflicts_pending` | Gauge | 待处理冲突数（抓取时查询） |
| `mortise_conflicts_total` | Counter | 累计冲突数 |
| `mortise_http_requests_total{method,route,status}` | Counter | HTTP 请求总数 |
| `mortise_http_request_duration_seconds_{count,sum}{method,route}` | Summary | HTTP 请求耗时 |
| `mortise_db_size_bytes` | Gauge | 数据库文件大小 |
| `mortise_uptime_seconds` | Gauge | 进程运行秒数 |

示例输出（节选）：

```
# HELP mortise_sync_rows_total 同步行数（按源/表/操作分类）
# TYPE mortise_sync_rows_total counter
mortise_sync_rows_total{source="orders_csv",table="orders",op="inserted"} 5
mortise_sync_rows_total{source="orders_csv",table="orders",op="skipped"} 0
...
```

> `TBD(实测填)`：编排者可在目标机器上 `curl` 后把真实输出片段贴到此处。

## 视图自动注册

`mortise.yaml` 的 `views` 段声明的视图，会在 `mortisedb sync` 与 `serve` 启动时自动注册进 `_m_views`（幂等，可重复运行）：

```bash
./mortisedb sync
# 视图自动注册: 新增 2，更新 0，清理 0

# 随时手动触发
./mortisedb views sync
./mortisedb views list
```

规则：YAML 里改了 SQL/描述 → 自动更新；删掉某条声明 → 自动清理；你在 CLI（`views add`）或 Web/API 里手工建的视图标为 `manual`，永远不会被清理。注意注册时不做 SQL 试运行（表可能还没同步出来），跑视图时才会真正校验。

## 物化视图

![物化视图](docs/screenshots/views-materialized.png)

查询量大的视图可以声明物化，把结果落成 `_mv_<视图名>` 表，查询时直接读表：

```yaml
views:
  - name: monthly_sales
    sql: SELECT ...
    materialize:
      enabled: true
      refresh: on_sync   # on_sync | manual | interval:30m
```

刷新策略：`on_sync`（默认，每次 `sync` 后自动刷新）、`manual`（仅手动）、`interval:<时长>`（超期才刷新）。手动触发：

```bash
./mortisedb views refresh monthly_sales
# 已刷新视图 monthly_sales，写入 1280 行
curl -s -X POST http://localhost:8421/api/views/monthly_sales/refresh
```

刷新是全量事务（`DROP` + `CREATE TABLE AS`），失败回滚旧表不受影响；YAML 里取消 `materialize` 块后下次 sync 自动删掉物化表。视图页会显示物化标记与上次刷新时间，可一键刷新。

## 备份与恢复


### 备份

```bash
mortisedb backup --config /etc/mortise/mortise.yaml \
  --output /var/backups/mortise-$(date -u +%Y%m%dT%H%M%SZ).db
```

输出文件、大小、SHA256、耗时，并生成 `<备份>.meta.json`。

### 恢复

```bash
# 目标不存在
mortisedb restore --config /etc/mortise/mortise.yaml --from /var/backups/mortise-xxx.db

# 目标存在且非空：需 --force，旧库改名 .bak-<时间戳> 留底
mortisedb restore --config /etc/mortise/mortise.yaml --from /var/backups/mortise-xxx.db --force
```

### 演练结论

`TBD(实测填)`：建议每季度在隔离机器上按 `docs/OPERATIONS.md` §3.4 执行一次恢复演练，记录恢复耗时与数据一致性抽查结果。

## 负载验证

`scripts/loadtest.sh` 生成三源各 10 万行数据（CSV / JSON / SQLite）与 `mortise-load.yaml`：

```bash
bash scripts/loadtest.sh ./loadtest-work
cd ./loadtest-work
/usr/bin/time -v mortisedb sync --config mortise-load.yaml
/usr/bin/time -v mortisedb query --config mortise-load.yaml "SELECT COUNT(*) FROM v_load_join"
```

结果（2026-10-13 实测，2 vCPU 弱 VM，详见 `docs/LOADTEST.md`）：

| 阶段 | 耗时 | 峰值内存 |
| --- | --- | --- |
| 三源全量同步（30 万行） | 265.89s（约 1128 行/秒） | 162 MB |
| 跨源 JOIN 视图查询（10 万行） | 452ms | — |

> 优化前后对比：逐行自动提交约 38 行/秒 → 批量事务（`sync.batch_size` 默认 5000）约 1128 行/秒，约 30 倍。

## 端到端验证

`scripts/e2e.sh` 是一键端到端编排（bash + curl，无额外依赖）：

```bash
bash scripts/e2e.sh ./e2e-work
```

它用一份真实感的茶叶小店数据（10 行订单 CSV + 8 个会员 JSON）走完：写 YAML → `sync`（断言视图自动注册 `新增 2`）→ `views list`（断言两个视图名）→ 全行查询（断言 10 行）→ 改 YAML（断言 `新增 1，更新 1`）→ 删声明（断言 `清理 1` 且 `views list` 不再含它）→ 起 `serve` 调 `/api/views` → CSV 导出（断言 10 行数据且含"龙井"）→ 物化演练（`on_sync` 自动刷新断言 `刷新 1，跳过 1`、`_mv_v_order_detail` 10 行、`views refresh` 手动刷新、`POST /api/views/{name}/refresh`）。本轮实测 `E2E PASS`。


## 一键部署

```bash
docker compose up -d --build
docker compose ps        # 看 health 列
docker compose logs -f mortisedb
```

compose 文件含健康检查（`wget` 探 `/api/health`）、资源限制（512m 内存 / 1 核）与日志轮转（10m×3）。数据落在 `./data/mortise.db`，`down` 不丢。升级/排障见 `docs/OPERATIONS.md` §1。

## 路线图

### v1.1（已交付）

- ✅ `/metrics` Prometheus 端点（13 个指标，手写 exposition，无新依赖）。
- ✅ `backup` / `restore` 子命令（`VACUUM INTO` 在线一致性快照 + 元信息）。
- ✅ 优雅关闭补强（HTTP 超时 + 在途等待 + WAL checkpoint）。
- ✅ 10 万行负载验证支撑（`scripts/loadtest.sh` + `docs/LOADTEST.md` 实测：30 万行 265.89s，跨源 JOIN 10 万行 452ms）。
- ✅ 同步批量事务（`sync.batch_size` 默认 5000：`dbtx` 接口 + 每批提交/出错回滚；约 38 行/秒 → 约 1128 行/秒）。
- ✅ `request_id` 与结构化日志维持通过。

### v1.2（已交付）

- ✅ YAML 声明视图自动注册（`sync`/`serve`/`views sync` 幂等注册 + 更新 + 清理；`_m_views.origin` 区分 yaml/manual，老库自动迁移）。
- ✅ 端到端编排脚本 `scripts/e2e.sh`（真实数据 + 断言，实测 E2E PASS）。
- ✅ docker-compose 一键部署强化（健康检查 + 资源限制 + 日志轮转；`docs/OPERATIONS.md` 补部署/升级/排障）。

### v1.3（已交付）

- ✅ 物化视图 + 刷新策略（`materialize: {enabled, refresh}`：on_sync/manual/interval；`views.Refresh` 事务全量刷新 + `views.RefreshDue` 策略调度；sync 自动刷新/CLI 手动/API 触发；Web UI 物化标记 + 一键刷新；`_m_views` 4 列扩展与老库迁移；3 个新指标；e2e 第 9 步物化演练 E2E PASS）。
- ✅ 发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v1.3.0.md`。

### 后续版本

- ⬜ HTTP / WebDAV 数据源连接器。
- ⬜ 冲突批量操作。
- ⬜ 单文件加密。


## License

MIT License

数据留在你自己的盘上，工具只做它该做的那一步。
