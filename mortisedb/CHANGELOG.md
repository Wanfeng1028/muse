# 变更日志

本文件记录 MortiseDB 的重要变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
