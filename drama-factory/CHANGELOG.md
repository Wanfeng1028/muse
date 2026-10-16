# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，
版本号使用项目内版本（`v2.x`）。

## [Unreleased]

### Added

- v2.30「OpenAPI 接口分组 + 依赖治理」（DoD 第 4 轮排期）：
  - OpenApiConfig.java 新增 4 个分组 Bean：runs（运行管理）、videos（视频生产）、scripts（剧本与内容）、admin（系统管理），分组文档地址是 /v3/api-docs/{group}，用 @Order(1~4) 把顺序钉死。
  - OpenApiDocsTest.java 新增 2 个测试：四组文档都能打开（200 且 openapi 以 3. 开头）；每组关键路径都对得上（runs 有 /api/runs；videos 有 /api/video-tasks/{taskId}；scripts 有 /api/projects；admin 有 /api/health）。
  - 22 个 controller 把缺的 @Tag/@Operation/@Parameter/@ApiResponse 注解补齐了，已有的不动，只补缺的；@Parameter 用的是 io.swagger.v3.oas.annotations.Parameter。
  - README.md 加了「API 文档」章节，写了 /v3/api-docs、/swagger-ui.html、四组文档地址表、鉴权说明和公网暴露提醒。
  - .github/dependabot.yml 里 maven 条目加了 reviewers ["Wanfeng1028"]；加了 ignore 规则，org.springdoc:* 的 >=3 大版本不升（springdoc 2.7+ 要 Spring 6.2，本项目 Spring Boot 3.3.5 是 Spring 6.1.x）；头注释写清了为啥钉死。
  - 新增 docs/DEPENDENCY_POLICY.md，写了依赖更新节奏（Dependabot 每周一，PR 上限 5，合入前 mvn -o test 全绿）、扫描与抽查、紧急漏洞响应流程（高危 24 小时内出修复分支）、高危依赖清单维护，附录 A 是真实直接依赖清单（13 项，mvn -o dependency:list 实测），附录 B 说明 springdoc 为啥钉死 2.6.0。
- v2.29「testFullPipeline flaky 根因歼灭 + E2E 加固」（根因：ffmpeg 瞬时失败 × 三处生产代码缺口）：
  - `FfmpegService.FfmpegException` 增加瞬时/永久分类（`isTransient()`）：超时、非零退出码（含 137/143）、ffprobe 失败等为瞬时；`无法启动命令`（二进制缺失）、参数编程错误为永久；旧构造器默认瞬时（保守策略）。`run()` 增加慢命令 warn（>30s）。
  - `FinalCutService`：concat/burn-subtitles/probe-duration 三步对瞬时失败有界重试（默认 3 次，退避 2000ms×attempt），永久失败直接 FAILED；配置 `drama.ffmpeg.retry-attempts` / `drama.ffmpeg.retry-backoff-ms`（env `FFMPEG_RETRY_ATTEMPTS`/`FFMPEG_RETRY_BACKOFF_MS`）。
  - `VideoTaskService`：`processDueTasks` 单飞保护（重叠调用跳过，防对真实 provider 重复提交）；`failOrRetry` 对非瞬时 FfmpegException 直接标记 FAILED（`[永久失败，不再重试]`），不再空转指数退避。
  - 指标：`dramafactory_ffmpeg_retries_total{operation,kind,result}`、`dramafactory_video_poll_skipped_total`。
  - 测试 8 批：`FfmpegExceptionClassificationTest`、`FinalCutFfmpegRetryTest`、`FinalCutRealFfmpegRetryTest`（真实 ffmpeg）、`ProcessDueTasksSingleFlightTest`、`VideoTaskFailFastTest`、`VideoPipelineResilienceE2eTest`（E2E 韧性）、`FfmpegRetryMetricsTest`、`FfmpegServiceTest` 补强（probe/extractPoster）。
  - 脚本：`scripts/verify-flaky-fix.sh`（回归验证）、`scripts/ffmpeg-chaos-drill.sh`（故障演练：kill -9 ffmpeg 后任务经重试恢复）。
- 发版对照报告：`docs/dod-v2.29.md`。

### Docs
- 新增 `docs/FFMPEG_RELIABILITY.md`（可靠性设计注记：分类表/重试矩阵/排障/告警）；`docs/OPERATIONS.md` 新增 8.7/8.8（ffmpeg 排障/单飞说明/告警示例）；`docs/DEGRADATION.md` ffmpeg 小节更新；README 增加可靠性小节。

## [v2.26] - 2026-10-16

### Added
- 账号体系 P0#3「auth-service 生产级补强」（dod-v2.25 排期第 1、3 项）：
  - Flyway 版本化迁移：`auth-service` 接入 `flyway-core`，`ddl-auto: update`→`validate`，`V1__baseline.sql` 由真实 Hibernate DDL 逐字导出（三表 + 真实 FK 约束名），`baseline-on-migrate: true` 兼容老库；`AuthFlywayMigrationTest` 2 例。
  - 指标：`actuator` + `micrometer-registry-prometheus`，`/actuator/prometheus`（无鉴权，靠网络隔离）；`AuthMetrics`（注册/登录/刷新/OAuth 回调 Counter + 用户数/活跃会话 Gauge 快照，`@Scheduled(30s)`）；`prometheus/rules/auth-service.yml` 3 条告警（5xx 错误率/实例宕机/登录失败激增）。
  - 备份恢复：`scripts/backup-auth.sh`（在线/离线双模式）+ `scripts/restore-auth.sh`（停服检查/manifest sha256/恢复前快照/完整性校验）+ `docs/OPERATIONS-AUTH.md` 运维手册。
  - 应用内在线备份端点：`POST /api/auth/admin/backup`（ADMIN 专用，`BackupService` 经 `JdbcTemplate` 执行 `BACKUP TO`，路径服务端生成防穿越）；修复 H2 嵌入式独占文件锁导致独立进程无法在线备份的真问题（主服务 `backup.sh` 同样受影响）。
- 测试：auth-service 全量 25 例通过（16 旧 + 2 Flyway + 4 指标 + 3 备份端点）。
- 发版对照报告：`docs/dod-v2.26.md`。

### Docs
- 新增 `docs/OPERATIONS-AUTH.md`（auth-service 运维手册）；`docs/dod-v2.26.md` 发版对照报告。

### Added
- AI MV 模式 v1：`POST /api/mv`（创建）/ `{id}/lyrics`（DeepSeek 作词）/ `{id}/compose`（BYOK 作曲）/ `{id}/storyboard`（分镜）/ `{id}/render`（wan2.5+ffmpeg 合成）/ `{id}/status`（轮询）/ `{id}/video` / `{id}/audio`；Run 类型新增 MV（作词→作曲→分镜→视频生成→剪辑→质检 6 步骤进时间线）；AgentType 新增 LYRICS/COMPOSE；AceStepMusicProvider（开源作曲渠道 BYOK）；mv.html 5 步创作页（深浅主题）；作曲渠道调研 docs/mv-music-providers.md。

## [v1.0] - 2026-10-14

### Added
- BYOK 真实生成调用（v1.0 最后一块）：`POST /api/byok/generate`（IMAGE/MUSIC/AVATAR 三模块，服务端阻塞轮询后落盘，返回本地 URL）+ `GET /api/byok/file/{module}/{filename}`（防路径穿越）。
- DashScope 万相文生图：`wan2.5-t2i-preview`，async 提交+轮询（`X-DashScope-Async: enable`）；连接探针 `GET /tasks/__connectivity_probe__`（零费用，404=密钥有效/401=密钥无效）；真实出图已验证（1024×1024 PNG）。
- MiniMax 音乐：`music-3.0` 同步调用（`base_resp.status_code==0` 成功）；探针非法 model 负向探测（4xx=密钥有效，零费用）。注：官方已公告 2026-08 起不对新用户开放、免费档停服，仅存量付费用户可用。
- D-ID 数字人：talks 提交+轮询（文案驱动 TTS 或音频 URL 二选一，人物图需公网 URL）；探针 `GET /credits`（零费用）。
- Key 解析顺序：通道卡片 → 设置中心（`dashscope.api-key`/`minimax.api-key`/`did.api-key`）→ surrogate（仅 DashScope，沿用现有白名单）。
- 前端三页接真实接口：生成中禁用按钮+进度提示，失败显示脱敏错误；图片页预览、音乐页音频播放器、数字人页视频播放器；空 Key 保持诚实空状态。
- 单元/契约测试 29 例（录制回放 + MockMvc），总数 515→544 全绿。

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
