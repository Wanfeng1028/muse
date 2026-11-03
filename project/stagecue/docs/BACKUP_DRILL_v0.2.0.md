# 备份恢复演练记录 v0.2.0

> 日期：2026-10-15
> 方式：真实演练（非文档推演）。kotlinc 编译的真实服务端进程 + 真实 SQLite 文件。
> 结论：**通过**。演练中发现 1 个真 bug（排练开关未持久化，`Main.kt` 漏接 `settings`），已修复并重跑演练验证。

## 环境

- 服务端：`dev.stagecue.server.MainKt`（kotlinc 直接编译，Ktor CIO，端口 18080）
- 数据目录：`STAGECUE_DATA_DIR`（演练用临时目录，演练后保留 tar 包备查）
- 备份命令：`tar czf backup.tar.gz -C "$STAGECUE_DATA_DIR" .`（停服务后执行）

## 步骤与证据

| # | 步骤 | 操作 | 结果 |
|---|------|------|------|
| 1 | 干净启动 | 删空数据目录后启动 | `GET /api/show` 返回 5 条默认 cue；`GET /api/rehearsal` → `false`；`GET /metrics` 正常（含 6 个 stagecue_ 指标） |
| 2 | 模拟用户数据变更 | 停服务 → 写入 1 条新 cue（`cue-drill/演练验证cue`）+ `rehearsal=true` → 启动 | `/api/show` 6 条（含"演练验证cue"）；`/api/rehearsal` → `true` |
| 3 | 备份 | 停服务 → tar 打包数据目录 | `backup.tar.gz`（1596 字节） |
| 4 | 模拟灾难 | `rm -rf` 数据目录 | 目录不存在 |
| 5 | 恢复 | 重建目录 → 解包 | `stagecue.db`（45056 字节）恢复 |
| 6 | 重启校验 | 启动 → 三个端点核对 | `/api/show` 6 条且名字完全一致；`/api/rehearsal` → `true`；`/metrics` 正常 |
| 7 | 配置校验 | `STAGECUE_PORT=abc` 启动 | 进程 exit 1，stderr：`ConfigException: STAGECUE_PORT 必须是 1~65535 的整数，当前值：'abc'` |

## 演练中发现的问题

- **排练开关未持久化**：第一次演练 step 2 返回 `rehearsal: false`，但 sqlite3 直查库内为 `rehearsal|true`。根因：`Main.kt` 中 `SyncHub()` 未传入 `settings`（构造参数默认为 null），读链路恒为 false。单元测试未覆盖（测试直接构造 `SyncHub(settings=...)`）。已修复（`SyncHub(settings = settings)`），重跑演练 step 2/6 均为 `true`，关闭。
- tar 恢复时报 `Cannot change ownership`（root 打包、nobody 解包的环境问题），文件内容不受影响，不视为失败。

## 运维结论

- 备份必须在**停服务后**做（WAL 模式，在线热拷可能拿到不一致快照）。
- 恢复后 Flyway 自动校验（日志 `Schema "main" is up to date`），无需手动迁移。
- 恢复验证三板斧：`curl /api/show`（核条数与名字）、`curl /api/rehearsal`（核开关）、`curl /metrics`（核指标）。
