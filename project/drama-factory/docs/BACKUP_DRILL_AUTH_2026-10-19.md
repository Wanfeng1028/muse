# auth-service 备份恢复演练记录（2026-10-19）

## 环境

- 执行时间：2026-10-19
- 执行批次：W3-drama
- 环境类型：非生产隔离环境
- 演练对象：auth-service（预构建 jar：`auth-service/target/auth-service-1.0.0.jar`）
- 服务端口：18082
- 鉴权配置：`AUTH_JWT_SECRET` 为演练专用 dummy 值
- 数据目录：隔离 scratch 目录（`./data/auth`）

## 步骤与证据

1. **启动服务并完成注册/登录**：启动服务，注册用户 drill@example.com（首个注册用户自动为 ADMIN），登录返回 200 并拿到 token。
2. **停止服务并执行备份**：停止服务，执行 `scripts/backup-auth.sh`（`APP_HOME=隔离目录`）；检测到服务未运行，走离线模式，使用 H2 Shell（`h2-2.2.224.jar`）执行 `BACKUP TO`，产物为 `backups/auth/auth-service-20261019-044949.tar.gz`，`manifest.txt` 含 sha256。
3. **模拟数据丢失**：执行 `mv data data.lost`。
4. **执行恢复**：执行 `scripts/restore-auth.sh <备份包>`；manifest sha256 校验通过；当前库不存在故跳过恢复前快照；执行恢复；恢复后完整性校验（`SELECT COUNT(*) FROM users`）通过。
5. **重启并验证**：重启服务（本 VM 上冷启动约 109 秒），登录 drill@example.com 成功，`GET /api/auth/me` 返回正确用户（id=1, email=drill@example.com, nickname=drill, role=ADMIN）。

## 结论

PASS。备份 → 丢数 → 恢复 → 重启 → 登录全链路真实走通。

## 备注

演练脚本原设的 120 秒启动等待在本 VM 上偏紧（冷启动 109 秒），后续演练注意放宽。
```
=== PATCH: docs/OPERATIONS-AUTH.md ===
```diff
--- a/docs/OPERATIONS-AUTH.md
+++ b/docs/OPERATIONS-AUTH.md
@@
-演练建议**：每月至少一次在非生产环境执行完整备份 + 恢复演练。
+演练建议**：每月至少一次在非生产环境执行完整备份 + 恢复演练。 演练记录：docs/BACKUP_DRILL_AUTH_2026-10-19.md（2026-10-19 首次演练通过）。
