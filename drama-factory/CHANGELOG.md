# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，
版本号使用项目内版本（`v2.x`）。

## [v2.9] - 2026-10-14

### Added
- AuthProxyController 可测性重构（生产级补强第 8 轮）：构造器内写死的 HttpClient 改为构造器注入（新增包可见重载供测试，原 public 构造器委托 + `@Autowired` 显式标记）；默认客户端配置（connectTimeout 5s、Redirect.NEVER）零变更。
- AuthProxyControllerTest 新建 20 例：T1~T10（透传/query/hop-by-hop 过滤/df_at cookie 补 Authorization/头优先于 cookie/refresh 401 与 body 替换/GET noBody/上游 500 透传/尾斜杠）+ T11~T20（login token 剥离写 cookie/expiresIn 缺失默认 3600/非 JSON 转 502/400 原样透传/oauth 回调剥离/logout 清 cookie/logout 500 透传/send 抛 IOException/InterruptedException/读 body 抛 IOException）；上游用 JDK HttpServer 绑 `::1` 随机端口。
- 分支覆盖冲 55% 达成：全量分支 52.7%→57.3%、行 71.0%→73.6%；AuthProxyController 单类分支 0%→79.5%、行 97.8%、方法 100%；测试总数 336→356 全绿。
- 覆盖率门禁收紧：LINE 0.65→0.70、BRANCH 0.45→0.55（棘轮，只升不降）。

### Docs
- 新增 docs/dod-v2.9.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.10 路线。

## [v2.8] - 2026-10-14

### Added
- 分支覆盖冲 45%（生产级补强第 7 轮）：新增 104 例测试，总数 232→336，`mvn -o verify` 全绿；行覆盖 58.5%→71.0%、分支 37.5%→52.7%。
- 覆盖率门禁收紧：JaCoCo check 新增 BRANCH 0.45；LINE 0.55→0.65（棘轮，只升不降）。
- LlmScriptServiceTest 8→34：validate() 9 例、parseScenes() 12 例、buildUserContent() 5 例（含捕获 body 断言 user 文本的 CapturingLlmScriptService）。
- RunServiceTest 15→33：planPreview() 12 例、createRun/pause/resume 6 例。
- ScriptSplitterServiceTest 15→35：parse/strip 6 例、replaceShots() 14 例。
- RunExecutorTest 10→36：advanceRun 与各 step 异常分支 13 例、QC 自动门/checkVideoStep/finalize 13 例（含 @TempDir 真实文件 QC 通过用例）。
- ProviderServiceProbeTest 新建 14 例：testConnection() 10 例（模块/名称匹配/鉴权失败透传/checkedAt 格式）、maskKey() 4 例。

### Docs
- 新增 docs/dod-v2.8.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.9 路线。

## [v2.7] - 2026-10-14


### Added
- stats() 多用户口径：ProjectService.stats() / RunService.stats() 按当前用户隔离（ownerId；开放模式全 local，行为与旧全局口径一致）；DramaProjectRepository 新增 countByOwnerId；RunService 构造器新增 CurrentUser/DramaProjectRepository 注入；@Operation 文案同步；API 路径与响应字段零变更。
- LlmTransport 可测性重构：ProxySpec + parseProxy/resolveProxy/toHttpHost/buildRequestConfig/buildPost 纯函数 + HttpExecutor 函数式 seam；4 参数编排逻辑（含预先代理认证）零变更。
- 测试 40 例：LlmTransportTest 17（代理纯函数/请求构建/状态码与异常契约/密码不泄露）、MockVideoProviderTest 6、RunExecutorTest 10（Mockito 编排：审批门/异常→FAILED/VIDEO 跨 tick/finalize 汇总/tick 吞异常）、StatsIsolationTest 2（MockMvc 多用户隔离）、CameraMoveTest 5。
- 覆盖率门禁收紧：JaCoCo minimum 0.51→0.55；实测行覆盖 51.3%→58.5%、分支 31.0%→37.5%。

### Changed
- CameraMove.fromLabel：非法非空标签由返回 null 改为抛 IllegalArgumentException（与 ShotSize.fromLabel 一致）；null/空白仍返回 null。parseShotsJson 路径非法运镜现在报错而非静默 null 落库。

### Docs
- 新增 docs/dod-v2.7.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.8 路线。

## [v2.6] - 2026-10-14

### Added
- 多用户地基：`DramaProject.ownerId`（JWT sub；开放模式回退 `local`）+ Flyway `V6__owner_id.sql`（老数据回填 `local`，列 NOT NULL）+ `config/CurrentUser` + 项目 API 全链路归属隔离（越权访问 403 `ForbiddenException`）；`ProjectResponse` 新增 `ownerId` 字段。
- 日志脱敏：新增 `util/SecretMasker`（纯函数）+ 11 例单测；`docs/SECURITY_DATA.md`（敏感数据清单/存储策略/日志脱敏/删除策略/缺口排期；经 grep 全量审计确认无直接打印密钥的日志）。
- 降级策略：新增 `docs/DEGRADATION.md`（6 子系统降级矩阵；ffmpeg 缺失与 auth-service 不可达诚实标注为"当前无降级"，不虚构）。
- 覆盖率门禁：JaCoCo 0.8.12 接入 pom（prepare-agent/report/check），`mvn verify` 强制行覆盖 ≥51%（实测 51.3%，基线 49.6%）；新增 `docs/COVERAGE.md`（目标/口径/基线/缺口表/v2.7 路线）。
- 测试：新增 36 例——`ProjectOwnerIsolationTest`（3）、`SecretMaskerTest`（11）、`ScriptSplitterServiceTest`（15，含一次行为不变重构抽出 `parseShotsJson` 可测缝）、`EpisodeStatusFlowServiceTest`（7）。

### Docs
- 新增 `docs/dod-v2.6.md` 发版对照报告；`docs/SECURITY_DATA.md`、`docs/DEGRADATION.md`、`docs/COVERAGE.md`。

## [v2.5] - 2026-10-14

### Added
- OpenAPI 文档：springdoc-openapi 2.6.0（Boot 3.3.x 官方兼容版本），GET /v3/api-docs（JSON/YAML）与 /swagger-ui.html，全部 Controller 补 @Tag/@Operation（注：注解在 v2.5 同轮另一批交付，此处先记条目）。
- 依赖自动更新：新增 .github/dependabot.yml（maven / github-actions / docker，每周一）。
- 运维手册实质补齐：docs/OPERATIONS.md 由 stub 补成完整手册（部署/配置/备份恢复/升级/日志/监控告警/API 文档/故障排查/已知限制）。
- 测试：新增 OpenApiDocsTest（/v3/api-docs 实质断言 + swagger-ui 可达）。

### Docs
- 新增 docs/dod-v2.5.md 发版对照报告。

## [v2.4] - 2026-10-14

### Added
- 指标采集：接入 Micrometer + Prometheus，暴露 `GET /actuator/prometheus`（无鉴权，`JwtAuthFilter` 仅拦 `/api/**`）。
- 业务指标：新增 7 类业务指标——`dramafactory_video_tasks_queued`、`dramafactory_runs_by_status{status}`（8 个 `RunStatus` 小写标签）、`dramafactory_runs_waiting_approval`、`dramafactory_script_llm_calls_total{model,result}`、`dramafactory_script_llm_duration_seconds{model}`、`dramafactory_finalcut_builds_total{result}`、`dramafactory_finalcut_build_duration_seconds`。Gauge 由 `@Scheduled(30s)` 刷新内存快照，抓取时不打 DB。
- 告警：新增 `prometheus/rules/drama-factory.yml`，含 `DramaFactoryHighErrorRate`（critical）、`DramaFactoryVideoQueueBacklog`、`DramaFactoryApprovalStuck`、`DramaFactoryRunFailures`（warning）。
- 抓取配置：新增 `prometheus/prometheus.yml` 示例（job `drama-factory`，15s 间隔，指向 `localhost:8081/actuator/prometheus`）。
- 备份恢复：新增 `scripts/backup.sh`（H2 `BACKUP TO` 在线备份 + `media/`、`settings/` 归档 + manifest + 保留最近 7 个）与 `scripts/restore.sh`（运行检查 → sha256 校验 → 恢复前快照 → H2 `Restore` → media/settings 恢复 → 冒烟），均已真实跑通。
- 运维手册：新增 `docs/OPERATIONS.md`（部署/备份恢复/升级/日志轮转/监控告警/6 条故障排查/已知限制）。
- 测试：新增 `MetricsEndpointTest` 3 例。

### Docs
- 初建 `CHANGELOG.md`，回填 v2 至 v2.3 历史。
- 新增 `docs/dod-v2.4.md` 发版对照报告。

## [v2.3] - 历史版本

### Added
- AI 编剧引擎：接入 DeepSeek-V4-Flash 真实模型调用。

## [v2.2] - 历史版本

### Added
- 结构化日志输出。
- request_id 贯穿请求链路，便于按 ID 检索。
- 接入 Resilience4j 熔断与限流（单实例内存级）。
- 新增 Docker Compose 部署配置。

## [v2.1] - 历史版本

### Added
- 接入 Flyway 数据库迁移。
- 提交幂等支持。
- 优雅关闭。

## [v2] - 历史版本

### Added
- 短剧生产管线：分镜、视频任务状态机、ffmpeg 剪辑。
- 生产看板。
