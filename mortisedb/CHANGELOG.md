# 变更日志

本文件记录 MortiseDB 的重要变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [1.5.0] - 2026-10-17

### 新增

- 冲突 Webhook 投递器（internal/notify/notify.go）：POST JSON，请求头 `X-Mortise-Event`、`X-Mortise-Signature`、`X-Mortise-Delivery-Id`；指数退避 1s→2s→4s+抖动，最多重试 `conflict_webhook_max_retries` 次，单次超时 `conflict_webhook_timeout`；投递失败只记日志+指标，永不阻塞主流程。
- 配置键（`mortise.yaml` 的 `notify.` 段）：`conflict_webhook_url`（为空则不启用）、`conflict_webhook_secret`（HMAC-SHA256 签名密钥）、`conflict_webhook_timeout`（默认 10s）、`conflict_webhook_max_retries`（默认 3）、`events`（默认 `["conflict.pending","conflict.resolved","conflict.resolved_auto"]`，可配子集）。
- 事件：`conflict.pending`（manual 模式冲突挂起）、`conflict.resolved`（`POST /api/conflicts/{id}/resolve` 手动解决）、`conflict.resolved_auto`（priority 自动裁决）。
- 埋点位置：sync 完成后（FireTableConflicts 回查本表本次冲突）、两路 CSV 导入（`POST /api/sources/{id}/import-csv` 的 handleImportCSV、`POST /api/import/csv` 的 handleImportCSVNew）、`POST /api/conflicts/{id}/resolve` 成功后。
- 指标：`mortisedb_conflict_webhook_deliveries_total{event,status}`（status=delivered|failed）。
- 签名格式：`X-Mortise-Signature` 为 `sha256=<hex>`，对请求体做 HMAC-SHA256（密钥即 `conflict_webhook_secret`）。

### 变更

- api.Version 1.4.0 → 1.5.0（server.go 第 29 行）。

### 测试

- `go test ./...` 全量通过（含 api 包 10.4s）。
- 新增 internal/api/webhook_notify_test.go（4 例：两路导入投递+签名校验、失败不阻塞导入、resolve 投递）、internal/notify/notify_test.go（M2a 投递器单测）。
- `go vet ./...` 全洁、`gofmt -l` 全洁；scripts/e2e.sh 扩展为 11 步全 PASS（新步骤 10：冲突 webhook——dead 端口投递失败不阻塞 409 导入、failed 指标可观测）。
- 真实冒烟（fake webhook 捕获）：签名用 secret 独立计算 HMAC 验签 MATCH。

### 已知限制

- 同秒边界可能多投（时间字符串秒级比较），接收端按 `delivery_id` 去重。
- pending 风暴下一事件一投递（设计裁决，不聚合）。
- 指标进程内计数，重启清零。

## [1.4.0] - 2026-10-17

### 新增

- 新端点 `POST /api/import/csv`（multipart）：`file`（必填）、`source`（必填）、`table`（可选，默认源的 `table`）、`primary_key`（可选，默认源的 `primary_key`）、`column_mapping`（可选，JSON 字符串如 `{"订单号":"order_id"}`）。
- 列映射：`column_mapping` 为 `{"CSV列名":"目标列名"}`；未映射列按原名直通；映射后列名必须非空、唯一、匹配 `^[A-Za-z_][A-Za-z0-9_]*$`，否则 400；主键列必须在映射后列集合中，否则 400。
- 真流式：文件内容落盘到 `<dbdir>/.import-tmp/` 临时文件（`os.CreateTemp`，处理完删除），不一次进内存；超 32MB → 413；边写边 sha256。
- 幂等：同 source + 文件 sha256 命中 `_m_imports` → `duplicate=true` 直接返回上次统计。
- 冲突策略集成：源 `sync.conflict=manual` 且主键已存在、行哈希不同、现有行来源与本源不同 → 不覆盖，写 `_m_conflicts`（`status=pending`），本批有挂起冲突时 HTTP 409 + 冲突数组；`priority` 按 `sync.priority` 源顺序自动裁决（`resolved_auto`）；同源更新直接覆盖并自动解决该 pk 的 pending。
- Web UI 新增"导入"页：选数据源、选 CSV 文件、目标表/主键（可选）、列映射 JSON（可选）、上传；结果展示 inserted/updated/unchanged/error_rows/错误列表；有挂起冲突时朱砂色提示并跳冲突页。

### 变更

- `api.Version` 1.3.0 → 1.4.0。

### 测试

- `internal/api/import_csv_v14_test.go`
- `scripts/e2e.sh` 回归

## [1.3.0] - 2026-10-16

### 新增

- **物化视图（Materialized Views）+ 刷新策略**：`views` 声明新增 `materialize: {enabled, refresh}`，`refresh` ∈ `on_sync`（默认，每次 sync 后刷新）/ `manual`（仅手动）/ `interval:<时长>`（如 `interval:30m`，超期才刷新）。
  - `views.Refresh`：事务内 `DROP TABLE IF EXISTS` + `CREATE TABLE _mv_<name> AS <视图SQL>` 全量刷新，失败回滚旧表不受影响，返回写入行数。
  - `views.RefreshDue`：按 YAML 策略刷新到期视图；YAML 取消物化声明时自动 `DROP TABLE` 删旧物化表。
  - `mortisedb sync` 成功后自动按策略刷新，打印 `物化视图刷新: 刷新 N，跳过 M`；`mortisedb views refresh <名称>` 手动触发；`POST /api/views/{name}/refresh` 返回行数与耗时；`views list` 新增物化/刷新策略/上次刷新列；Web UI 视图页显示物化标记与上次刷新时间、可一键刷新。
  - `_m_views` 新增 `materialized` / `refresh_policy` / `last_refresh_at` / `last_refresh_rows` 列，老库 `Migrate()` 幂等补列；物化表命名 `_mv_<视图名>`（启用物化要求视图名为合法标识符）。
  - 新指标：`mortise_view_refresh_total{view,status}`、`mortise_view_refresh_duration_seconds{view}`、`mortise_view_last_refresh_rows{view}`。
  - `scripts/e2e.sh` 新增第 9 步物化演练（on_sync 自动刷新/跳过断言、`_mv_` 表行数断言、manual 手动刷新、API 刷新），实测 E2E PASS。

### 修复

- `RecordViewRefresh` 时间格式：原 SQLite `datetime('now')`（`2026-10-16 17:45:00` 空格格式）导致 `RefreshDue` 的 RFC3339 解析永远失败、`interval` 策略每次误判为到期；改为 Go 侧 `time.Now().UTC().Format(time.RFC3339)` 写入。

### 变更

- `api.Version` 由 `1.2.0` 升级为 `1.3.0`。
- `docs/OPERATIONS.md` 新增 §5 物化视图（声明/策略/手动刷新/指标/注意事项），原 §5/§6 顺延为 §6/§7。

## [1.2.0] - 2026-10-15


### 新增

- **YAML 声明视图自动注册**：`views.SyncFromConfig`——`mortisedb sync` / `serve` 启动时把 `mortise.yaml` 的 `views` 段幂等注册进 `_m_views`（新增/更新计数打印），YAML 改名/改 SQL 自动更新，删声明自动清理；`mortisedb views sync` 可手动触发。
  - `_m_views` 新增 `origin` 列（`yaml`/`manual`，老库 `Migrate()` 自动补列回填 `manual`）：手工 `views add` 与 API 创建的视图永不参与清理。
  - 注册时不做 SQL 试运行（目标表可能尚未同步），合法性由运行时与 `views add` 的试运行兜底。
- **端到端编排脚本** `scripts/e2e.sh`：茶叶小店真实感数据（10 行订单 CSV + 8 会员 JSON）→ 写 YAML → sync → views list 断言 → 行数断言 → YAML 改/删演练（更新/清理计数断言）→ 起 serve 调 `/api/views` → CSV 导出断言 10 行；本轮实测 E2E PASS。
- **docker-compose 一键部署强化**：健康检查（busybox wget 探 `/api/health`，失败仅标记 unhealthy）、资源限制（`mem_limit: 512m`、`cpus: 1.0`）、日志轮转（json-file 10m×3）；`docs/OPERATIONS.md` 新增 compose 部署/升级/排障节。

### 变更

- `api.Version` 由 `1.1.0` 升级为 `1.2.0`。
- `docs/OPERATIONS.md`：删除文件顶部事故残留的裸 shell 命令三行；版本历史追加 1.2.0。
- `docs/LOADTEST.md` §7：视图自动注册已知限制已解除（v1.2 落地）。

## [1.1.0] - 2026-10-13

### 新增

- **`/metrics` Prometheus 端点**：手写 text exposition（`text/plain; version=0.0.4`，仅标准库，无新依赖）。
  - 指标清单：
    - `mortise_build_info{version="1.1.0"}` = 1
    - `mortise_sync_rows_total{source,table,op}`，op ∈ inserted/updated/deleted/skipped/conflicts
    - `mortise_sync_runs_total{job,status}`，status ∈ ok/error
    - `mortise_sync_last_duration_seconds{source}`
    - `mortise_view_duration_seconds_count{view}` / `mortise_view_duration_seconds_sum{view}`
    - `mortise_view_last_duration_seconds{view}`
    - `mortise_watermark_lag_seconds{source,table}`（抓取时实时计算）
    - `mortise_conflicts_pending`（抓取时查询）、`mortise_conflicts_total`
    - `mortise_http_requests_total{method,route,status}`、`mortise_http_request_duration_seconds_sum/count{method,route}`
    - `mortise_db_size_bytes`（抓取时 `os.Stat`）、`mortise_uptime_seconds`
  - 埋点位置：sync 层累加 `rows_total` 与 `runs_total`；API 层 `handleViewRows`/`handleQuery` 计时（view label 分别为视图名与 `adhoc`）；`store.RecordConflict` 直接递增 `conflicts_total`。
- **`backup` / `restore` 子命令**：
  - `mortisedb backup [--config PATH] [--output PATH]`：使用 SQLite `VACUUM INTO` 做在线一致性快照，输出文件/大小/SHA256/耗时，同时生成 `<备份>.meta.json`。
  - `mortisedb restore --from <文件> [--config PATH] [--force]`：先 `Verify`（只读打开 + `PRAGMA integrity_check` + 检查 `_m_watermarks` 表），目标非空且无 `--force` 拒绝，`--force` 时旧库改名为 `*.bak-<时间戳>` 留底再原子替换。
- **优雅关闭补强**：
  - `http.Server` 增加 `ReadHeaderTimeout=10s`、`ReadTimeout=30s`、`WriteTimeout=60s`、`IdleTimeout=120s`。
  - 关闭流程结构化日志化：停新请求 → `Shutdown(30s)` → `scheduler.Stop()` 等待在途同步 → `PRAGMA wal_checkpoint(TRUNCATE)`（失败仅 warn）→ `st.Close()`。
- **10 万行负载验证支撑**：`scripts/loadtest.sh` 生成 CSV/JSON/SQLite 三源各 10 万行 + `mortise-load.yaml`（含跨源 JOIN 视图 `v_load_join`），脚本只生成与自检，手动计时见 `docs/LOADTEST.md`。
- **同步批量事务**：`syncOneTable` 行循环包进事务，每 `sync.batch_size`（默认 5000）行提交一次；出错 Rollback；水位线仍在最终 Commit 成功后写回。实测 2 vCPU VM 上 30 万行 265.89s（约 1128 行/秒），相对逐行自动提交（约 38 行/秒）约 30 倍提升；跨源 JOIN 10 万行 452ms。详见 `docs/LOADTEST.md`。

### 变更

- `api.Version` 由 `0.1.0` 升级为 `1.1.0`。

## [0.1.0] - 2026-01-01

首个可用版本。功能范围以源码实际为准：

### 连接器

- YAML 声明式配置，支持 `sqlite` / `csv` / `json` / `dir` 四种数据源。
- 每个源通过 `primary_key` 指定主键；`sqlite` 通过 `tables` 映射 `source/target/primary_key`。
- schema 推断：CSV 采样推断列类型，JSON 按值类型推断，SQLite 读取 `PRAGMA table_info` 声明类型。
- 类型统一为 `INTEGER` / `REAL` / `TEXT` / `DATETIME` / `BOOLEAN` 五种。

### 增量同步

- `incremental: hash`（默认）：基于行内容 sha256 做全量比对。
- `incremental: "column:<列名>"`：按列水位线增量拉取，水位线存储在 `_m_watermarks`。
- 全量模式下通过对比源端主键集合检测删除，软删除写入 `_m_deleted=1`。

### 冲突策略

- `sync.conflict: priority`：按 `sync.priority` 列表判定胜出方，落败方记为 `pending`，胜出方记 `resolved_auto`。
- `sync.conflict: manual`：跨源冲突一律 `pending`，交由人工处理。
- 冲突写入 `_m_conflicts`，字段 `source_a`（现有方）、`source_b`（挑战方）。
- 本源重写同一主键时，自动将该主键的 `pending` 冲突标记为 `resolved_auto`。

### 查询视图

- 视图定义保存于 `_m_views`（名称、SQL、描述、创建时间）。
- 支持保存、列出、运行、删除视图。
- 运行视图支持导出 CSV（`GET /api/views/{name}/rows?format=csv`）。

### 调度

- 按 `jobs` 配置的 `interval` 周期执行同步。
- 运行历史写入 `_m_runs`（新增/更新/删除/冲突/错误）。
- Job 名自动带源名后缀（`<job>:<source>`），方便按源查询上次同步时间。

### CLI

`mortisedb` 提供六个子命令：`init` / `sync` / `query` / `views` / `serve` / `status`。

### Web UI

五页（go:embed 内嵌静态资源）：首页、表浏览、视图、冲突、运行记录。

### 生产级基础

- `Migrate()` 建立系统表（`_m_runs` / `_m_conflicts` / `_m_views` / `_m_watermarks`）。
- 结构化 JSON 日志 + `request_id` 中间件。
- `GET /api/health` 健康检查。

## [Unreleased]

### 后续版本

- HTTP / WebDAV 数据源连接器。
- 视图物化（物化视图 + 刷新策略）。
- 冲突批量操作。
- 单文件加密。
