# mini-os v1.2.0 发版对照报告

本报告按 PRODUCTION_CHECKLIST 七大节逐条给结论：通过 / 未通过 / 不适用，附理由。未通过项写排期或已知限制声明。

版本：1.2.0
形态：Rust 单二进制，axum 0.7 + rusqlite 0.32（bundled + backup feature）+ SQLite。

---

## 一、功能与接口

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 服务可启动、可提供 HTTP 接口 | 通过 | `mini-os serve` 启动，探针与 API 集成测试 16 例通过 |
| 存活探针 `/api/health` | 通过 | 返回 200 `{"status":"ok","version":"1.2.0"}`，version 取 Cargo.toml |
| 就绪探针 `/api/readyz` | 通过 | DB 真实可查 200 `{"status":"ready"}`，否则 503 `{"status":"not_ready"}` |
| CLI 子命令完整 | 通过 | `serve|backup|restore`，参数与退出码见运维手册 |
| 鉴权 | 未通过 | v1.2.0 无鉴权，属路线图项，见"遗留排期" |
| 限流 | 不适用（已声明） | 本地单用户场景声明，无限流，见"遗留排期" |
| 多用户 | 未通过 | 多用户未做，单实例 SQLite，见"遗留排期" |

---

## 二、数据与迁移

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 版本化迁移表 | 通过 | `schema_migrations` 表，001（建 `vfs_nodes`/`settings`）/ 002（增 `content_blob`/`mime_type` 列） |
| 迁移幂等 | 通过 | 失败注入用例覆盖迁移幂等 |
| 老库自动升级、数据保留 | 通过 | 老库（无迁移表）启动自动补齐，失败注入用例覆盖老库升级，数据保留 |
| 单实例 SQLite | 不适用（已声明） | 设计即单实例 SQLite，见"遗留排期" |

---

## 三、测试

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 单元测试 | 通过 | `cargo test` 单元 4 例（log 3 + migrate 1）全过 |
| API 集成测试 | 通过 | 16 例全过 |
| 失败注入测试 | 通过 | 8 例全过（损坏库 open 拒绝、业务表缺失时读写 500 不 panic、readyz 200/503 翻转、request_id 透传/生成、迁移幂等与老库升级） |
| 测试总数 | 通过 | 28/28 全过 |
| 静态检查 | 通过 | `cargo clippy --all-targets` 零警告 |
| 真实负载 | 通过 | 300 文件顺序创建 0 失败，avg 74.93ms，max 138.97ms，30 个抽查内容一致 |

---

## 四、备份与恢复

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 在线备份 | 通过 | `mini-os backup --db --out`（拒绝覆盖），`scripts/backup.sh`（保留最近 7 个）真实跑通 |
| 恢复 | 通过 | `restore --db --backup [--force]`：先 integrity_check，目标存在无 `--force` 拒绝 exit 2，覆盖前自动快照 `<db>.pre-restore-<epoch秒>.bak`，原子替换经 `<db>.tmp.<pid>` rename |
| 损坏备份拒绝 | 通过 | 损坏备份 restore exit 3，fault_drill 覆盖 |
| 备份→删库→恢复一致性 | 通过 | fault_drill 覆盖，数据一致 |
| 恢复前必停服务 | 通过（流程约定） | `restore.sh` 先提示停服务，运维手册明确要求 |

---

## 五、可观测性与日志

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 结构化日志 | 通过 | JSONL 写 stderr，访问字段 `ts/level/request_id/method/path/status/latency_ms` |
| 事件日志 | 通过 | `service_started/shutdown_signal_received/service_stopped/shutdown_timeout/backup_done/restore_done` |
| request_id 透传 | 通过 | `x-request-id` 透传（无则生成）并回写响应头 |
| 探针语义 | 通过 | health 存活、readyz 就绪，语义明确 |
| Prometheus 指标 | 未通过 | v1.2.0 未接 Prometheus，无 `/metrics`，属已知限制，见"遗留排期" |

---

## 六、运维与部署

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 优雅关闭 | 通过 | SIGTERM/Ctrl+C → 停止接受新连接 → 排空在途请求 → `service_stopped`，exit 0 |
| 关闭超时行为 | 通过 | `SHUTDOWN_TIMEOUT_SECS`（默认 30）只约束排空阶段，不掐正常服务，已回归验证 |
| 运维脚本 | 通过 | `backup.sh` / `restore.sh` / `load_check.py` / `fault_drill.sh` 均已真实跑通 |
| docker-compose 一键部署 | 未通过（未实跑） | `docker-compose.yml` 已配（build、端口、数据卷、日志轮转 10m×3、资源限制 1 核/512M），**本机无 docker daemon，未实际运行验证**，见"遗留排期" |
| 故障演练 | 通过 | `fault_drill.sh` 全项通过，结论 `FAULT DRILL PASS` |
| 运维手册 | 通过 | `docs/OPERATIONS.md` 覆盖部署/配置/备份恢复/升级/日志监控/排障/资源轮转/演练 |

---

## 七、发布与版本管理

| 检查项 | 结论 | 依据 / 理由 |
| --- | --- | --- |
| 版本号 | 通过 | 1.2.0，`/api/health` 的 version 取 Cargo.toml |
| 变更记录 | 通过 | CHANGELOG 增加 `[1.2.0] - 2026-10-16` |
| 配置样例同步 | 通过 | `.env.example` 增 `SHUTDOWN_TIMEOUT_SECS`，README 环境变量表与持久化说明同步 |
| Dependabot / CI 迁移 | 未通过 | Dependabot 待 gh token 补 workflow 权限后，随 CI 迁仓库根，见"遗留排期" |

---

## 结论

**可发版。**

支撑结论的关键事实：
- 测试 28/28 全过（单元 4 + API 集成 16 + 失败注入 8）。
- `cargo clippy --all-targets` 零警告。
- 失败注入 8 例覆盖损坏库、业务表缺失、探针翻转、request_id、迁移幂等与老库升级。
- 真实负载 300 文件 0 失败，avg 74.93ms / max 138.97ms，30 个抽查内容一致。
- 故障演练 `FAULT DRILL PASS`。
- 备份恢复真实跑通。
- 唯一未实跑项：docker-compose（本机无 docker daemon），已在文档与报告如实标注。

---

## 遗留排期

| 事项 | 类型 | 说明 / 排期 |
| --- | --- | --- |
| 多用户与鉴权 | 路线图 | v1.2.0 无鉴权、多用户未做；按路线图推进 |
| 限流 | 已知限制 | 本地单用户场景声明，无限流；后续按需补 |
| Prometheus 指标 | 已知限制 | 未接 `/metrics`，后续补 |
| Dependabot | 待办 | 等 gh token 补 workflow 权限后，随 CI 迁仓库根 |
| docker 镜像实跑验证 | 待办 | 本机无 daemon 未实跑；上生产前在目标机 `docker compose up` 验证一次 |
