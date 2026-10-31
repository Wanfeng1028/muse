# mini-os v1.19.18 生产级对照报告

## 结论
可发版（本轮范围）。

## 改动范围
- `src/config.rs` 新增 4 个 `pub` 纯解析函数：`parse_port_raw`（缺省 `8090`，`u16`）、`parse_upload_max_bytes_raw`（缺省 `50 * 1024 * 1024`，`u64`）、`parse_shutdown_timeout_secs_raw`（缺省 `30`，`u64`）、`parse_session_ttl_secs_raw`（缺省 `604800`，`u64` 且 `0` 非法）。
- `Config::from_env` 对上述 4 项非法值改为 `eprintln("配置错误：...")` + `exit(2)`，与 `MINIOS_SESSION_SLIDING`、登录限流、分享限流、`MINIOS_TERM_OUTPUT_LIMIT`、`MINIOS_BACKUP_CODE_RETENTION_DAYS` 的 fail-fast 口径一致。
- 此前 `PORT` 超 `u16`、`UPLOAD_MAX_BYTES` 非数字、`SHUTDOWN_TIMEOUT_SECS` 负数、`SESSION_TTL_SECS` 为 `0` 均静默回默认值，现一律启动报错。
- 合法边界不变：`PORT` 的 `0` 与 `65535`、`UPLOAD_MAX_BYTES` 的 `0`、`SHUTDOWN_TIMEOUT_SECS` 的 `0` 此前本就接受，本轮不扩范围。
- 版本由 `1.19.17` 升为 `1.19.18`（`Cargo.toml` 与 `Cargo.lock` 同步）。

## 测试与冒烟实测数字
- 新增 `tests/config_env_strict_test.rs`：4 个测试函数 4/4 通过。
- `tests/config_deep.rs` 改写旧静默回落测试为 `from_env_strict_parsers_reject_unparseable_numbers`（直接驱动纯解析函数断言 `Err`，因 `from_env` 本身会 `exit(2)`）：10/10 通过。
- lib 内 config 单元测试（`term_output_limit` 三项）：3/3 通过。
- `cargo fmt --all --check` 干净。
- `cargo clippy --lib` 有 8 个告警，均不在本轮改动文件（`config.rs` 与两个测试目标无归属告警），属既存基线，本轮未扩范围修复。
- 真实服务冒烟（18571 端口、隔离库；冒烟后服务已按端口查到的 PID 定向 kill、端口复查已关、冒烟库已删）：
  - `PORT=abc` 启动 `exit 2`，末行：`配置错误：PORT 必须是 0 到 65535 之间的整数，当前值：abc`
  - `SESSION_TTL_SECS=0` 启动 `exit 2`，末行：`配置错误：SESSION_TTL_SECS 必须是正整数，当前值：0`
  - `UPLOAD_MAX_BYTES=abc` 启动 `exit 2`，末行：`配置错误：UPLOAD_MAX_BYTES 必须是整数，当前值：abc`
  - `SHUTDOWN_TIMEOUT_SECS=-1` 启动 `exit 2`，末行：`配置错误：SHUTDOWN_TIMEOUT_SECS 必须是整数，当前值：-1`
  - 合法配置起服后 `GET /api/health` 返回 `{"status":"ok","version":"1.19.18"}`；`POST /api/auth/register` 返回 `id 2`、`username smokeuser`、`isAdmin true`、`role admin`；`GET /api/readyz` 返回 `{"status":"ready"}`。

## 已知限制
- 本轮未跑全量 `cargo test`（只跑了靶向测试与 lib 内 config 单元测试）。
- `DATABASE_PATH`、`STATIC_DIR` 缺失仍用默认值，不在本轮收紧范围。
- 无数据库迁移、无新增端点、无新增依赖、无 UI 改动，视觉验收不适用。

## 批次诚实记录
- B1 代码稿首行含一段推理外泄文本与围栏标记，编排剥离后 8 个 PATCH 锚定逐一核对唯一后一次应用成功。
- B2 测试稿一次通过，但编排侧首版应用器对“新文件空 OLD”解析失败（未落盘），改用按行解析的应用器后 3 个 PATCH 一次应用成功。
- 两处测试文件的长 import 行经 rustfmt 折行后 fmt 检查干净。

## Definition of Done 对照
| 条目 | 状态 | 理由 |
| --- | --- | --- |
| 代码改动完成 | 通过 | `src/config.rs` 新增 4 个纯解析函数并改 `from_env` 为 fail-fast；`Cargo.toml`/`Cargo.lock` 同步至 `1.19.18` |
| 靶向测试通过 | 通过 | `config_env_strict_test.rs` 4/4；`config_deep.rs` 10/10；lib config 单元测试 3/3 |
| `cargo fmt --all --check` | 通过 | 干净 |
| `cargo clippy --lib` | 不适用 | 本轮改动文件无归属告警；既存基线 8 个告警未扩范围修复，不作为发版阻断项（本轮范围） |
| 真实服务冒烟 | 通过 | 18571 端口隔离库实测 4 个非法配置各 `exit 2` 且末行文案逐字一致；合法配置起服后 `/api/health`、`/api/auth/register`、`/api/readyz` 返回符合预期；事后定向 kill、端口复查已关、冒烟库已删 |
| 运维文档同步 | 通过 | `docs/OPERATIONS.md` 已对 `UPLOAD_MAX_BYTES`、`SHUTDOWN_TIMEOUT_SECS`、`SESSION_TTL_SECS` 补充 fail-fast 口径 |
| 变更日志同步 | 通过 | `CHANGELOG.md` 新增 `## [1.19.18] - 2026-11-01` 节 |
| 已知限制披露 | 通过 | 本报告“已知限制”一节已如实列出未跑全量测试、`DATABASE_PATH`/`STATIC_DIR` 未收紧、无迁移/端点/依赖/UI 改动 |
| 批次诚实记录 | 通过 | 本报告“批次诚实记录”一节已如实记录 B1/B2 过程与 rustfmt 折行事实 |
