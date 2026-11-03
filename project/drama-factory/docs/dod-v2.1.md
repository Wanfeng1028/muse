# drama-factory v2.1 发版对照报告（DoD 第 1 轮）

## 版本说明

v2.1 对应生产级 DoD 对照表的第 1 轮高优先级项，交付三项能力：

1. **提交幂等**：同一 shot 的 PENDING/PROCESSING 任务去重，重复提交返回 200（首次 201）。
2. **优雅关闭**：`server.shutdown=graceful` + 调度器 `await-termination` 30s + 轮询在途收尾钩子 25s。
3. **Flyway 版本化迁移**：引入 `V1__baseline.sql`，`ddl-auto` 由 `update` 改为 `validate`，`baseline-on-migrate=true` 兼容老库。

## 对照表（对照 PRODUCTION_CHECKLIST.md）

| 类别 | 条目 | 结论 | 说明 |
| --- | --- | --- | --- |
| 测试 | 测试金字塔（单元 + 集成） | 通过 | 20 例：原有 12 + 幂等 3 + Flyway 2 + 优雅关闭 3，覆盖关键路径 |
| 数据库 | 版本化迁移 | 通过 | Flyway `V1__baseline.sql`，`ddl-auto=validate`，`baseline-on-migrate=true` |
| 运行时 | 优雅关闭 | 通过 | `server.shutdown=graceful`；调度器 `await-termination: true` / 30s；`VideoTaskService` 轮询在途收尾钩子最多等 25s |
| 接口 | 提交幂等 | 通过 | 同 shot PENDING/PROCESSING 去重；重复提交 200，首次 201 |
| 可观测 | 健康检查 | 通过 | `/api/health` 已提供 |
| 安全/限流 | 限流 / 超时 / 熔断 | 未通过（有排期） | 第 2 轮：真实 provider 超时熔断、限流策略 |
| 交付 | Docker Compose | 未通过（有排期） | 第 2 轮 |
| 可观测 | 结构化日志 + request_id | 未通过（有排期） | 第 2 轮 |
| 可观测 | 指标与告警 | 未通过（有排期） | 第 3 轮 |
| 安全 | 鉴权 | 未通过（有排期） | 第 3 轮 |
| 数据库 | 备份与恢复 | 未通过（有排期） | 第 3 轮 |
| 运维 | 运维手册 | 未通过（有排期） | 第 3 轮 |
| 运行时 | 资源限制 / 日志轮转 | 未通过（有排期） | 第 4 轮 |
| 接口 | OpenAPI | 未通过（有排期） | 第 4 轮 |
| 交付 | CHANGELOG | 未通过（有排期） | 第 4 轮 |
| 交付 | Dependabot | 未通过（有排期） | 第 4 轮 |
| 安全 | 敏感数据策略 | 未通过（有排期） | 第 5 轮 |
| 运行时 | 降级策略 | 未通过（有排期） | 第 5 轮 |
| 测试 | 单测比例 | 未通过（有排期） | 第 5 轮 |
| 数据 | user 字段预留 | 未通过（有排期） | 第 5 轮 |

## 已知限制

1. **幂等实现**：当前为单实例 check-then-insert，非原子操作；高并发极端情况下仍可能产生重复插入，后续可考虑数据库唯一约束 + 乐观锁强化。
2. **Flyway 基线**：`V1__baseline.sql` 由 Hibernate 在 H2 2.2.224 上 `ddl-auto=create` 导出的当前 schema 整理而来（含引号、约束名、NOCHECK），去掉了 `CREATE USER` 行。老用户库首次升级走 `baseline-on-migrate` 做基线，不重跑 V1；新库完整执行 V1。
3. **优雅关闭时限**：轮询单轮上限 20 个任务，mock provider 下远小于 25s 收尾窗口。但 **agnes 真实 provider 下单任务耗时可能较长**，25s 收尾可能不够，超时熔断是第 2 轮 DoD 项，本轮不做。

## 验证记录（编排者实测，2026-10-13）

- `mvn test`：20/20 通过（原有 12 例 + 幂等 3 例 + Flyway 2 例 + 优雅关闭 3 例）。
- 真实服务冒烟（jar 包，H2 文件库，全新库）：
  - Flyway：启动日志确认 V1 执行；`flyway_schema_history` 表中 version=1（baseline）success=TRUE。
  - 提交幂等：建项目→剧集→分镜后，`POST /api/shots/1/video-tasks` 第一次返回 201（新任务 id=1），第二次返回 200（同一 id=1）；库中 `video_tasks` 只有 1 行。
  - 优雅关闭：SIGTERM 后日志出现"关闭收尾：无在途轮询任务，直接返回"，JPA 干净关闭，进程正常退出。
  - `/api/health` 返回 `{"status":"ok"}`。
- 备注：Flyway 启动时有一条 WARN（H2 2.2.224 高于 Flyway 10.10.0 测试过的 2.2.220），不影响迁移执行。
