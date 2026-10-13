# drama-factory v2 生产级 DoD 对照报告

## 1. 可靠性

- **测试金字塔** — 通过（11 例覆盖单元+集成+全链路 E2E，从建项目到看板断言都跑通了，但单元测试比例偏低，主要靠集成测试兜底）。
- **失败注入** — 通过（mock 视频提供者的 failNext 路径已被测试覆盖，能验证重试与最终 FAILED 落库）。
- **错误处理策略** — 未通过（指数退避重试 max-attempts=8 已实现且可配，状态机不允许非法跃迁；但 submit 未做重复检查，重复提交同一 Shot 会重复建任务，无幂等；降级策略目前只有"失败即 FAILED"，没有备用 provider 切换）。
- **数据库迁移版本化** — 未通过（H2 ddl-auto=update 会自动改表结构，生产环境换库或改字段时不可控、不可回滚，没有 Flyway/Liquibase）。
- **健康检查端点** — 通过（`GET /api/health` 返回 {"status":"ok"}，容器可探活；未用 Actuator，指标类探针暂无）。
- **优雅关闭** — 未通过（没配 server.shutdown=graceful，也没处理正在轮询中的 VideoTask 收尾，重启可能丢在途任务状态）。

## 2. 可观测性

- **结构化日志** — 未通过（当前是 Spring 默认文本日志，没有 JSON 格式，日志采集和检索不好做）。
- **request_id 全链路** — 未通过（没有 MDC 注入 traceId/requestId，一次请求跨服务/跨线程的日志串不起来）。
- **关键指标** — 未通过（没有 Micrometer/Prometheus，请求量、延迟、错误率、队列积压都看不到，只能靠翻日志）。
- **告警规则** — 未通过（没有告警通道，任务连续失败、队列堆积、ffmpeg 报错都只能人工发现）。

## 3. 数据与状态

- **自动备份+一键恢复** — 未通过（H2 文件库没有定时备份脚本，也没有恢复流程文档，数据丢了只能重来）。
- **敏感数据策略** — 未通过（agnes 真实实现的 API Key 目前靠环境变量，但没有脱敏日志、没有加密存储约定）。
- **配置与密钥分离** — 通过（drama.video.provider / poll-interval-ms / max-attempts / storage / ffmpeg / ffprobe 全部环境变量化，密钥不落代码库）。
- **数据模型 user 预留** — 未通过（Shot/VideoTask/FinalCut 等 v2 实体均无 user 字段，接入鉴权/多用户时需要改表结构）。

## 4. 部署与运维

- **Docker Compose 一键部署** — 未通过（只有 Dockerfile 多阶段构建，没有 compose 文件，起服务还得手敲 docker run）。
- **滚动更新说明** — 未通过（没有副本、没有 readiness 探针，滚动更新无从谈起，只能停机重启）。
- **资源限制/日志轮转/数据卷** — 未通过（容器没设 CPU/内存上限，日志没轮转策略，H2 数据卷没在编排里声明）。
- **运维手册** — 未通过（备份/恢复/升级/常见故障四块都没写，新人接手只能读代码）。

## 5. 安全与健壮性

- **输入校验** — 通过（Bean Validation 已用在请求 DTO 上，景别、时长、提示词长度等有基本约束）。
- **防注入** — 通过（全部走 JPA 参数化查询，没有拼 SQL 的地方）。
- **鉴权** — 未通过（当前完全无鉴权，控制台和 API 谁都能调，已在文档里声明为已知限制）。
- **依赖更新机制** — 未通过（没有 Dependabot/Renovate，Spring Boot 3.3.5 和 ffmpeg 相关依赖升级靠人盯）。
- **限流/超时/熔断** — 未通过（没有对视频提供者调用设超时和熔断，agnes 挂了会把轮询线程拖死；API 也没限流）。

## 6. 可维护性

- **模块边界** — 通过（shot / videotask / finalcut / console 分包清晰，VideoProvider 接口把 mock 和 agnes 隔开，换实现不动上层）。
- **CHANGELOG** — 未通过（没有 CHANGELOG.md，v2 加了什么只能看 commit）。
- **API 契约** — 未通过（没有 OpenAPI/Swagger，接口靠读 Controller，前端联调容易对不上）。
- **代码与文档同步** — 未通过（README 只覆盖启动，管线流程、状态机、配置项说明散落在代码注释里）。

## 7. 未通过项排期表

| 条目 | 严重度 | 计划 | 预计轮次 |
| --- | --- | --- | --- |
| 提交幂等（同一 Shot 重复提交去重） | 高 | submit 前检查该 Shot 是否已有 PENDING/PROCESSING 任务 | 第 1 轮 |
| 优雅关闭 | 高 | 配 server.shutdown=graceful + 在途任务收尾钩子 | 第 1 轮 |
| 数据库迁移版本化 | 高 | 引入 Flyway，把 ddl-auto 改为 validate | 第 1 轮 |
| 限流/超时/熔断 | 高 | VideoProvider 调用加超时+Resilience4j 熔断 | 第 2 轮 |
| Docker Compose 一键部署 | 高 | 写 compose 文件，声明数据卷和依赖 | 第 2 轮 |
| 结构化日志 + request_id | 中 | logback JSON encoder + MDC 过滤器 | 第 2 轮 |
| 关键指标 + 告警 | 中 | Micrometer + Prometheus，配失败率/积压告警 | 第 3 轮 |
| 鉴权 | 中 | 加最简 API Key 或 Spring Security 基础认证 | 第 3 轮 |
| 自动备份+一键恢复 | 中 | H2 定时导出脚本 + 恢复文档 | 第 3 轮 |
| 运维手册 | 中 | 写备份/恢复/升级/常见故障四节 | 第 3 轮 |
| 资源限制/日志轮转/数据卷 | 中 | compose 里补 limits、log rotation、volumes | 第 4 轮 |
| API 契约（OpenAPI） | 低 | 加 springdoc-openapi | 第 4 轮 |
| CHANGELOG | 低 | 建 CHANGELOG.md，按版本记录 | 第 4 轮 |
| 依赖更新机制 | 低 | 开 Dependabot | 第 4 轮 |
| 代码与文档同步 | 低 | 补 README 管线/状态机/配置说明 | 第 4 轮 |
| 敏感数据策略 | 低 | 日志脱敏 + 密钥存储约定 | 第 5 轮 |
| 降级策略（备用 provider） | 低 | 失败时可切备用 provider | 第 5 轮 |
| 单元测试比例提升 | 低 | 补 Shot/VideoTask 状态机单测 | 第 5 轮 |
| 数据模型 user 预留 | 低 | Shot/VideoTask/FinalCut 等 v2 实体加 user 字段 | 第 5 轮 |
| CI workflow 迁根目录 | 低 | token 补 workflow 权限后迁移 | 第 5 轮 |
