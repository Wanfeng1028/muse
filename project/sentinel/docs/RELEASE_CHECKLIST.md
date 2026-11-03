# v0.2.0 发版对照报告

版本：v0.2.0
日期：2026-10-13
范围：生产级改造 + 站点健康档案 / 月度 SLA / 公开状态页
对照方式：按生产级 checklist 六章逐条核对，标注 [通过] / [未通过] / [不适用]。

## 一、可观测性

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| 结构化日志 | [通过] | 全量走 slog JSON，字段固定 time/level/msg，业务字段按需附加上去。 |
| request_id | [通过] | 每个 HTTP 请求进入中间件生成 request_id，贯穿到 handler 和下游日志。 |
| /healthz 存活探针 | [通过] | 进程存活即 200，无外部依赖。 |
| /readyz 就绪探针 | [通过] | DB Ping，异常返回 503（当前仅检查 DB 连通性）。 |
| Prometheus /api/metrics | [通过] | 暴露 sentinel_checks_total、sentinel_check_failures_total、sentinel_check_retries_total、sentinel_webhooks_sent_total、sentinel_webhook_failures_total、sentinel_http_requests_total{method,path,status}。 |
| 优雅关闭 | [通过] | 收到 SIGINT/SIGTERM 后停止接受新请求，等待 inflight 检查完成，超时兜底退出。 |

## 二、正确性与测试

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| 测试金字塔 | [通过] | 单元测试覆盖调度、重试、SLA 计算；集成测试覆盖 HTTP 路由和 DB 迁移。 |
| 失败注入测试 | [通过] | 构造连接超时（sleep 3s vs timeout 1s）、连接拒绝（关闭端口）、HTTP 500（验证不重试）、TCP 正常，验证重试次数与退避行为。 |
| 重试退避 | [通过] | 指数退避 500ms<<attempt（上限 8s），次数由 SENTINEL_CHECK_RETRY_MAX 控制（0~5）；仅 transport 失败重试，状态码不符不重试。 |

## 三、数据与迁移

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| DB 迁移版本化 | [通过] | schema_migrations 表记录版本，v1（原始三表）→v2（tenants/users/status_pages + monitors 加 tenant_id/is_public 列），幂等，db.Open 内自动执行。 |
| 备份恢复 | [通过] | 自动备份 + `-restore` 一键恢复，已按 OPERATIONS.md 第 3.3 节实测跑通。 |

## 四、安全与多用户

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| API token 鉴权 | [通过] | Bearer token 校验，401 走统一响应。 |
| tenant / user | [通过] | v2 引入 tenants 表与 users 表（id/tenant_id/name/token_hash/created_at）；monitors 按 tenant_id 隔离；API Token 经 sha256 比对。 |
| 输入校验 | [通过] | 请求体 JSON 解析后逐字段校验（必填、范围、枚举），非法直接 400。 |

## 五、运行与配置

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| 配置环境变量化 | [通过] | 全部走 env，启动时集中校验，不合法直接退出。 |
| 启动校验 | [通过] | 端口范围、并发数上限、token 非空、备份间隔正数等，逐项检查。 |
| 限流（目标检查间隔 + 并发上限 + inflight） | [通过] | 每个 monitor 有独立检查间隔；全局并发由 SENTINEL_CHECK_CONCURRENCY 限制；同一 monitor 用 inflight 标记去重。 |
| docker-compose | [通过] | 一键起，端口 8200，数据卷、备份卷、资源限制、日志轮转全部配好。 |
| 运维手册 | [通过] | docs/OPERATIONS.md 覆盖部署、配置、备份恢复、升级、可观测性、token、排障、资源。 |
| CHANGELOG | [通过] | CHANGELOG.md 记录 v0.2.0 全部变更。 |

## 六、已知限制

1. **分布式多实例未支持。** 当前用 SQLite，单实例部署。多副本会因共享文件写冲突损坏数据。需要水平扩展的话得换 PostgreSQL 并加实例间协调，不在本版本范围。
2. **Webhook 仅重试 3 次。** 告警推送失败时最多重试 3 次（指数退避），仍失败就放弃并只写日志，不做持久化队列重投。对端长时间不可用时会丢告警。

以上两条会作为 v0.3.0 的候选工作项跟踪。
