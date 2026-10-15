# ledger v2.1 发版对照报告

结论：**可发版**。v2.0 报告第 7 节 7 项排期全部关闭；测试 119/119 通过；ruff 全洁；真实冒烟全链路（建账→交易→metrics→备份→删库→恢复→数据一致）通过。

## 1. 可靠性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 未处理异常兜底 500 | 通过 | `logging.py` 的 `RequestIdMiddleware` 直接返回 `{"detail":"服务器内部错误","request_id":"..."}`；因 FastAPI 0.143 会把 `@app.exception_handler(Exception)` 转给 ServerErrorMiddleware 并在响应后 re-raise，故不走异常处理器。失败注入测试覆盖。 |
| 优雅关闭 | 通过 | lifespan shutdown dispose engine。 |
| 失败注入 | 通过 | `tests/test_failure_injection.py` 4 例：DB 锁定→500 带 request_id；坏 CSV→200 不崩服务；磁盘满→BackupError 无残留；metrics DB 故障→500。 |
| 就绪探针 | 通过 | `GET /api/ready`，DB 通 200 / 不通 503。 |

## 2. 可观测性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 结构化日志 | 通过 | `logging.py`，stderr JSON Lines（ts/level/logger/msg/request_id），`JsonFormatter` 单行 JSON；测试 6 例。 |
| request_id 全链路 | 通过 | `RequestIdMiddleware` 注入并回写 `X-Request-Id` 响应头。 |
| 日志级别配置 | 通过 | `LEDGER_LOG_LEVEL`，非法值启动 fail-fast。 |
| Prometheus 指标 | 通过 | `routers/metrics.py`，6 指标：ledger_statement_batches_total / ledger_statement_items_total{status} / ledger_detective_pending / ledger_auto_match_rate / ledger_transactions_total / ledger_accounts_total；测试 5 例。 |

## 3. 数据与状态

| 项 | 结论 | 说明 |
| --- | --- | --- |
| DB 迁移版本化 | 通过 | `migrations.py`，`PRAGMA user_version=2`，v2 DDL 从 models 编译生成；`init_db()` 改走 `run_migrations`；测试 3 例。 |
| 老库升级 | 通过 | v1 老库启动自动补 4 张 v2 表，损坏库启动报 `MigrationError`。 |
| 备份完整性 | 通过 | `backup.py` integrity_check，坏备份拒绝恢复。 |
| 恢复安全性 | 通过 | 恢复前自动安全快照；同秒备份 `-N` 后缀；keep 修剪。测试 4 例。 |

## 4. 部署与运维

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 一键部署 | 通过 | `docker-compose.yml`：healthcheck / 资源限制 / 日志轮转 / named volume。 |
| 运维手册 | 通过 | `docs/OPERATIONS.md`。 |
| 备份恢复入口 | 通过 | `python -m ledger backup\|restore`；`make backup [KEEP=N]` / `make restore FILE=`。 |

## 5. 安全与健壮性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 坏输入不崩服务 | 通过 | 坏 CSV（随机二进制）的 `csv.Error` 改为 errors 行收集返回 200。 |
| 磁盘满处理 | 通过 | 备份写入失败改为 `BackupError` 并清理半成品。 |
| 基础鉴权 | 不适用 | 本地单用户，README 已声明。 |
| 限流/超时/熔断 | 不适用 | 本地单进程无外部调用。 |

## 6. 可维护性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 测试规模 | 通过 | 97 → 119 例全过。 |
| 静态检查 | 通过 | ruff 全洁。 |
| 真实冒烟 | 通过 | 建账→交易→metrics→备份→删库→恢复→数据一致，全链路通过。 |

## 7. 本轮修复的真 bug（4 个）

1. `python -m ledger serve` 启动崩溃：`args.dir` 在 serve 子命令不存在（冒烟测试抓出）。
2. 坏 CSV 的 `csv.Error` 抛 500：改为 errors 行收集返回 200（失败注入测试抓出）。
3. 备份 `integrity_check` 对损坏文件抛裸 `sqlite3.DatabaseError`：改为 `BackupError`（失败注入测试抓出）。
4. 备份写入失败（磁盘满）抛裸 `OSError` 且留半成品：改为 `BackupError` 并清理。

## 8. 已知限制与后续

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 单用户无鉴权 | 已知限制 | 单用户本地应用，README 已声明。 |
| Dependabot | 未通过 | 等 gh token 补 workflow 权限后迁仓库根。 |
| 多用户设计 | 未通过 | 未做。 |
