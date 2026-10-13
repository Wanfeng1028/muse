# v2.2 发版对照报告（生产级 DoD 第 2 轮）

## 版本说明

- 版本号：v2.2
- 主题：生产级 DoD 第 2 轮 —— 结构化日志与请求全链路、超时熔断、提交接口限流、Docker Compose 一键部署
- 对应检查清单：`PRODUCTION_CHECKLIST.md`
- 参照基线：`docs/dod-v2.1.md`

本轮在 v2.1 的基础上补齐可观测性（结构化日志 + request_id 全链路）、稳定性（超时熔断 + 限流）
与交付形态（Docker Compose 一键部署 + 日志轮转 + 资源限制声明），并输出本发版对照报告。

## 对照表

| # | 检查项 | 结论 | 说明 |
|---|--------|------|------|
| 1 | 结构化日志 + request_id 全链路 | ✅ 通过 | `logback-spring.xml` 默认可读 pattern（含 MDC request_id），`SPRING_PROFILES_ACTIVE=json` 切换为 Logstash JSON（含 service 与 request_id 字段）；`RequestIdFilter` 透传/生成 `X-Request-Id` 并回写响应头；`ErrorResponse` 含 requestId；调度轮询使用 `poll-xxx` 前缀 request_id |
| 2 | 超时熔断（agnes provider） | ✅ 通过 | `ResilientVideoProvider`（bean 名 `agnesVideoProvider`）装饰 `agnesRawVideoProvider`；CircuitBreaker 实例 `agnes`（滑动窗口 10、最小调用 4、失败率阈值 50%、开路 60s）+ TimeLimiter 实例 `agnes`（90s 超时）；熔断打开抛 `ProviderCircuitOpenException`，由 `VideoTaskService` 指数退避重试接管 |
| 3 | 提交接口限流 | ✅ 通过 | `POST /api/shots/{shotId}/video-tasks` 与 `POST /api/episodes/{episodeId}/video-tasks/submit-all` 加 `@RateLimiter`（实例 `videoSubmit`：10 秒 10 次），超限立即 429 + `Retry-After: 10` |
| 4 | Docker Compose 一键部署 | ✅ 通过 | 新增 `compose.yml`，`docker compose up -d --build` 即可启动；`Dockerfile` 运行阶段加装 ffmpeg（mock 片段生成/成片剪辑）与 curl（健康检查） |
| 5 | 日志轮转 | ✅ 通过 | compose 中 `logging.driver: json-file`，`max-size: 10m`、`max-file: 3` |
| 6 | 资源限制声明 | ✅ 通过 | compose 中 `deploy.resources.limits`（cpus 2.0、memory 1G）与 `reservations.memory`（512M） |
| 7 | 指标与告警（Prometheus /metrics） | ❌ 未通过（有排期，第 3 轮） | 本轮未接入 Micrometer/Prometheus，无 `/actuator/prometheus` 指标暴露与告警规则 |
| 8 | 鉴权 | ❌ 未通过（有排期，第 3 轮） | 接口暂无鉴权，仅适用于内网/本机部署 |
| 9 | 备份与恢复 | ❌ 未通过（有排期，第 3 轮） | 未提供 H2 文件库与媒体目录的备份/恢复脚本与流程 |
| 10 | 运维手册 | ❌ 未通过（有排期，第 3 轮） | 未编写运维手册（排障、扩容、轮转、升级步骤） |
| 11 | OpenAPI | ❌ 未通过（有排期，第 4 轮） | 未接入 springdoc-openapi，无接口文档页面 |
| 12 | CHANGELOG | ❌ 未通过（有排期，第 4 轮） | 未维护 CHANGELOG 文件 |
| 13 | Dependabot | ❌ 未通过（有排期，第 4 轮） | 未启用依赖自动升级机器人 |
| 14 | 敏感数据策略 | ❌ 未通过（有排期，第 5 轮） | 未定义敏感数据（密钥、账号、媒体）的存储/脱敏/清理策略 |
| 15 | 降级策略文档化 | ❌ 未通过（有排期，第 5 轮） | 熔断/限流/重试的降级行为尚未形成文档化策略 |
| 16 | 单测比例 | ❌ 未通过（有排期，第 5 轮） | 未统计/设定单测覆盖率目标 |
| 17 | user 字段 | ❌ 未通过（有排期，第 5 轮） | 数据模型与日志暂未引入 user 字段（多用户归属） |

## 已知限制

- 熔断装饰器仅覆盖 agnes provider：mock provider 为本地生成，不涉及外部依赖，无需熔断。
- 限流为单实例内存级（Resilience4j RateLimiter 进程内计数），多实例部署需替换为分布式限流（如 Redis 令牌桶或网关层限流）。
- compose 健康检查依赖容器内 curl，已随镜像安装（`apt-get install curl`）；若自行裁剪镜像需保留 curl 或改用其他探活方式。
- 优雅关闭 25s 收尾窗口在 agnes 真实长任务场景下可能不够（与 v2.1 相同），后续需按最长任务耗时调整或引入任务续跑机制。

## 验证记录（编排者实测，2026-10-13）

- `mvn test`：26/26 通过（原有 20 例 + 新增 6 例：RequestIdFilterTest 3 例、ResilientVideoProviderTest 2 例、VideoTaskControllerRateLimitTest 1 例）。
- 真实 jar 冒烟（全新 H2 文件库，Flyway V1+V2 正常执行）：
  - request_id：`GET /api/health` 无头时响应头 `X-Request-Id` 自动生成 UUID；带头 `X-Request-Id: smoke-001` 时原样透传；`GET /api/video-tasks/999999` 返回 404，错误体含 `"requestId":"smoke-002"` 与请求头一致。
  - 可读日志：`[poll-58f99bf6]` 等 request_id 出现在 pattern 中；调度轮询提交任务打日志 `视频任务已提交：taskId=1，shotId=1，providerTaskId=mock-...`。
  - JSON 日志：`SPRING_PROFILES_ACTIVE=json` 启动后输出 Logstash JSON，含 `"service":"drama-factory"` 与 `"request_id":"poll-ba885452"` 字段。
  - 限流：建项目→剧集→分镜后，对 `POST /api/shots/1/video-tasks` 连发 11 次，前 10 次 201/200（第 2 次起幂等命中 200），第 11 次 429，响应体 `{"status":429,"error":"Too Many Requests","message":"视频任务提交过于频繁，请稍后再试",...,"requestId":"..."}` 且带 `Retry-After: 10` 头。
  - 熔断/超时：由 ResilientVideoProviderTest 单元测试覆盖（4 次失败后第 5 次抛 ProviderCircuitOpenException；poll 睡眠超 300ms 阈值抛超时异常）；真实 agnes 熔断需外部故障注入，本轮未做（排期：故障演练抽查）。
  - compose.yml：`python -c yaml.safe_load` 校验通过；本机无 docker，仅写未跑（与仓库既有 Dockerfile 策略一致）。
- 修复记录（本轮回喂 2 轮内解决）：
  1. dpsk 漏 `import com.dramafactory.model.Shot;`（ResilientVideoProvider 与其测试各一处），编排者补上。
  2. 熔断装饰器异常透出：初版把 resilience4j 已解包透出的原始 RuntimeException 又包成"agnes 调用失败"，经最小复现程序实证（TOP 即原始异常），改为 `catch (RuntimeException e) { throw e; }` 直接透传。
  3. RequestIdFilter 响应头写回：初版在 `filterChain.doFilter` 之后写头，MockMvc 测试能过但真实 Tomcat 可能已提交响应导致写头无效；改为在 chain 执行前写头，真机冒烟验证通过。
