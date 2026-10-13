# v2.4 发版对照报告（PRODUCTION_CHECKLIST）

对照仓库统一 `PRODUCTION_CHECKLIST` 的 6 节逐条核对。
状态取值：**通过** / **未通过**（转排期） / **不适用**（附理由）。

版本：v2.4
日期：2026-10-14

---

## 1. 可靠性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 健康检查端点 | 通过 | v2.1/v2.2 已落地，`/api/health` 可用。 |
| 优雅关闭 | 通过 | v2.1 已落地，关闭时等待在途请求与任务收敛。 |
| 熔断 | 通过 | v2.2 引入 Resilience4j 熔断。**限制：单实例内存级**，多实例部署时各实例状态独立，不共享熔断窗口。 |
| 限流 | 通过 | v2.2 引入 Resilience4j 限流。**限制同上：单实例内存级**。 |
| 降级策略文档化 | 未通过 | 转排期至**第 5 轮**。当前仅有熔断/限流的默认降级行为，缺少成文的降级预案与开关说明。 |
| 备份与恢复 | 通过 | 本轮交付 `scripts/backup.sh` / `scripts/restore.sh`，已真实跑通，详见「验证记录」。 |

## 2. 可观测性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 结构化日志 | 通过 | v2.2 已落地，JSON 结构化输出。 |
| request_id 贯穿 | 通过 | v2.2 已落地，请求链路可按 request_id 检索。 |
| 指标采集（Micrometer + Prometheus） | 通过 | 本轮交付，端点 `GET /actuator/prometheus`，无鉴权（`JwtAuthFilter` 只拦 `/api/**`）。 |
| 业务指标覆盖 | 通过 | 本轮交付 7 类业务指标，详见「验证记录」。Gauge 走 `@Scheduled(30s)` 刷新内存快照，**抓取时不打 DB**。 |
| 告警规则 | 通过 | 本轮交付 `prometheus/rules/drama-factory.yml`，含 4 条告警。 |
| 运维手册 | 通过 | 本轮交付 `docs/OPERATIONS.md`（部署/备份恢复/升级/日志轮转/监控告警/6 条故障排查/已知限制）。 |
| OpenAPI 文档 | 未通过 | 转排期至**第 4 轮**。 |

## 3. 数据与状态

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 数据库迁移（Flyway） | 通过 | v2.1 已落地，迁移脚本纳入版本管理。 |
| 提交幂等 | 通过 | v2.1 已落地。 |
| 备份可恢复（在线备份） | 通过 | 本轮交付，H2 `BACKUP TO` 在线备份 + `Restore` 恢复，真实跑通。 |
| 保留策略 | 通过 | `backup.sh` 保留最近 7 个备份。 |
| 敏感数据策略 | 未通过 | 转排期至**第 5 轮**。 |
| user 字段（多用户归属） | 未通过 | 转排期至**第 5 轮**。 |

## 4. 部署运维

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| Docker Compose | 通过 | v2.2 已落地。 |
| 升级流程 | 通过 | `docs/OPERATIONS.md` 含升级章节（含备份前置、迁移、回滚指引）。 |
| 日志轮转 | 通过 | `docs/OPERATIONS.md` 含日志轮转章节。 |
| 监控告警接入 | 通过 | 本轮交付 Prometheus 抓取配置 + 告警规则 + 手册告警章节。 |
| 依赖自动更新（Dependabot） | 未通过 | 转排期至**第 4 轮**。 |

## 5. 安全与健壮性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 鉴权（账号体系 + 过滤器） | 通过 | **前轮已落地**（`JwtAuthFilter` + `CookieAuthFilter` + 账号体系前端），本轮不重复做。 |
| 指标端点访问控制 | 不适用 | `/actuator/prometheus` 设计为无鉴权（`JwtAuthFilter` 只拦 `/api/**`），面向内网 Prometheus 抓取。**部署约束：不得将 8081 直接暴露到公网**，已写入 `OPERATIONS.md` 已知限制。 |
| 敏感数据策略 | 未通过 | 见第 3 节，转排期至**第 5 轮**。 |
| 单测覆盖率目标 | 未通过 | 转排期至**第 5 轮**。当前仅记录通过用例数（103/103），未设覆盖率门槛。 |

## 6. 可维护性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 版本变更记录（CHANGELOG） | 通过 | 本轮**初建** `CHANGELOG.md`，Keep a Changelog 风格，回填 v2 起历史。 |
| 运维文档 | 通过 | 本轮交付 `docs/OPERATIONS.md`。 |
| 发版对照报告 | 通过 | 本文件。 |
| OpenAPI | 未通过 | 见第 2 节，转排期至**第 4 轮**。 |
| 单测覆盖率目标 | 未通过 | 见第 5 节，转排期至**第 5 轮**。 |

---

## 未通过项排期汇总

| 项 | 排期 |
| --- | --- |
| OpenAPI | 第 4 轮 |
| Dependabot | 第 4 轮 |
| 敏感数据策略 | 第 5 轮 |
| 降级策略文档化 | 第 5 轮 |
| 单测覆盖率目标 | 第 5 轮 |
| user 字段 | 第 5 轮 |

---

## 验证记录

### 1. 单元/集成测试
- `mvn test`：**103/103 通过**。
- 含本轮新增 `MetricsEndpointTest` **3 例**。

### 2. 指标端点真实抓取
- 对 `GET http://localhost:8081/actuator/prometheus` 实际抓取，确认包含以下 7 类业务指标：
  1. `dramafactory_video_tasks_queued`（= PENDING + PROCESSING）
  2. `dramafactory_runs_by_status{status}`（8 个 `RunStatus` 小写标签）
  3. `dramafactory_runs_waiting_approval`
  4. `dramafactory_script_llm_calls_total{model,result}`
  5. `dramafactory_script_llm_duration_seconds{model}`
  6. `dramafactory_finalcut_builds_total{result}`
  7. `dramafactory_finalcut_build_duration_seconds`
- 确认 Gauge 由 `@Scheduled(30s)` 刷新内存快照，抓取路径不触发 DB 查询。

### 3. 备份 / 恢复真实跑通
- `scripts/backup.sh`：H2 `BACKUP TO` 在线备份 + `media/`、`settings/` 归档 + 生成 manifest + 保留最近 7 个，**已真实执行成功**。
- `scripts/restore.sh`：运行状态检查 → sha256 校验 → 恢复前快照 → H2 `Restore` → media/settings 恢复 → 冒烟检查，**已真实执行成功**。
- 恢复后校验：H2 `Restore` 完成后 **12 张表均可查询**，数据可读。

### 4. 告警规则
- `prometheus/rules/drama-factory.yml` YAML 语法已校验，4 条规则的 PromQL 经人工核对（Counter 用 rate/delta，Gauge 用直接比较/delta）。
