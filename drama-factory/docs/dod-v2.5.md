# DoD 对照报告 —— v2.5（生产级补强第 4 轮）

本轮目标：OpenAPI 文档 + Dependabot + 运维手册实质补齐。
本文逐条核对 6 大项状态，末尾附未通过项排期与验证记录。

---

## 1. 可靠性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 优雅关闭 | 通过 | v2.1 起启用 `server.shutdown: graceful`，本轮未改动。 |
| 熔断 / 超时 / 限流 | 通过 | Resilience4j 2.4.0 内存级实现，v2.2 起生效，本轮未改动。 |
| 视频任务状态机健壮性 | 通过 | `max-attempts=8` + 轮询间隔可配，v2 起沿用。 |
| 单实例集群化 | 未通过 | 熔断/限流内存级，多实例各自为政；排期第 5 轮讨论。 |

## 2. 可观测性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| Prometheus 指标端点 | 通过 | v2.4 起 `GET /actuator/prometheus`，7 类业务指标 + JVM 指标。 |
| 告警规则 | 通过 | `prometheus/rules/drama-factory.yml` 4 条规则，v2.4 交付。 |
| 结构化日志 | 通过 | `SPRING_PROFILES_ACTIVE=json` 切 Logstash JSON，含 `request_id`。 |
| OpenAPI 文档 | **通过** | 本轮新增 springdoc-openapi 2.6.0，`GET /v3/api-docs` 与 `/swagger-ui.html` 可用；v2.4 时为未通过。 |

## 3. 数据与状态

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| Flyway 版本化迁移 | 通过 | v2.1 起启用，`baseline-on-migrate: true` 兼容老库。 |
| H2 在线备份 | 通过 | `scripts/backup.sh` 走 `BACKUP TO`，v2.4 交付。 |
| 恢复流程 | 通过 | `scripts/restore.sh` 带 sha256 校验 + 恢复前快照，v2.4 交付。 |
| 敏感数据策略（密钥轮换、日志脱敏） | 未通过 | 目前只有 `AUTH_JWT_SECRET` 一个密钥入口，无轮换机制；日志里 LLM 请求体未做脱敏；排期第 5 轮。 |

## 4. 部署运维

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| Docker Compose 一键部署 | 通过 | `compose.yml`，v2.2 交付。 |
| 备份脚本 | 通过 | `scripts/backup.sh`，`BACKUP_KEEP` 默认 7。 |
| 恢复脚本 | 通过 | `scripts/restore.sh`，v2.4 交付。 |
| 运维手册 | **通过** | 本轮实质补齐：`docs/OPERATIONS.md` 从 v2.4 的 12 行 stub 扩为完整手册（部署/配置/备份恢复/升级/日志/监控告警/API 文档/故障排查/已知限制）。 |
| 依赖自动更新 | **通过（配置就位）** | 本轮新增 `drama-factory/.github/dependabot.yml`，maven / github-actions / docker 三条，每周一跑。**未完全生效**：GitHub 只认仓库根 `.github/dependabot.yml`，待 token 补齐 workflow 权限后随 CI 一起迁移才真正接通。 |
| 降级策略文档 | 未通过 | 目前只有 `agnes` → `mock` 这一条降级路径写在手册 8.5 与 9 里，没有独立的降级策略文档；排期第 5 轮。 |

## 5. 安全与健壮性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| JWT 鉴权 | 通过 | `JwtAuthFilter` 拦 `/api/**`，`AUTH_JWT_SECRET` 空则开放模式。 |
| Actuator 端点无鉴权 | 通过（有约束） | `/actuator/prometheus` 不在 `/api/**` 前缀下，默认无鉴权；手册第 6、9 节明确写了不要直接暴露公网。 |
| API 文档端点无鉴权 | 通过（有约束） | `/v3/api-docs`、`/swagger-ui/**` 同上，手册第 7、9 节写明部署约束。 |
| 密钥轮换机制 | 未通过 | 无。排期第 5 轮。 |
| 单测覆盖率目标 | 未通过 | 目前无覆盖率门禁，无明确目标值；排期第 5 轮。 |

## 6. 可维护性

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| CHANGELOG | 通过 | v2.4 起维护，本轮补 v2.5 条目。 |
| DoD 对照报告 | 通过 | v2.4 起维护，本轮新增 `docs/dod-v2.5.md`。 |
| 依赖版本锁死 | 通过 | springdoc 显式写 2.6.0（Boot BOM 不管此构件）；其余走 Boot BOM。 |
| 依赖自动更新 | **通过** | 同部署运维项，Dependabot 三条。 |
| user 字段（谁触发的操作） | 未通过 | 目前所有写操作无操作者信息；排期第 5 轮。 |

---

## 未通过项排期汇总

| 项 | 排期 | 备注 |
| --- | --- | --- |
| 敏感数据策略（密钥轮换 / 日志脱敏） | 第 5 轮 | 需要定密钥管理方案 + 日志脱敏白名单。 |
| 降级策略文档 | 第 5 轮 | 独立成文，覆盖 agnes → mock 之外的其它降级点。 |
| 单测覆盖率目标 | 第 5 轮 | 定目标值 + 加门禁。 |
| user 字段 | 第 5 轮 | 从 JWT claims 提取操作者写入写操作记录。 |

其余项本轮均通过。

---

## 验证记录

- `mvn test`：**105/105 通过**（v2.4 的 103 例 + 本轮新增 `OpenApiDocsTest` 2 例；离线构建，`./mvnw -s ~/workspace/muse-build/m2-settings-noproxy.xml -o test`）。
- `GET /v3/api-docs` 真实服务抓取：200，`openapi: 3.0.1`，`info.title: Drama Factory API`，`paths` 共 59 个，抽查含 `/api/projects`、`/api/runs`、`/api/episodes/{id}/generate-script`。
- `GET /swagger-ui/index.html` 真实服务抓取：200，`content-type: text/html`；首屏截图已由编排者亲眼验收（分组列表完整、无报错空白）。
- Dependabot：`drama-factory/.github/dependabot.yml`（maven / github-actions / docker，每周一 Asia/Shanghai）。**生效条件**：GitHub 只认仓库根 `.github/dependabot.yml`，本文件待 gh token 补齐 workflow 权限后，随 CI 配置一起迁往仓库根才实际生效；迁移前不算真正接通。

*最后更新：v2.5（2026-10-14）*
