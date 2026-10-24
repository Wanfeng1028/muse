# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，
版本号使用项目内版本（`v2.x`）。

## [Unreleased]

### Added（深耕轮 2026-10-25 03:07：HyperFrames 可寻址时间线模板（关闭 TD-002））
- HyperFramesVideoProvider 新增 drama.video.hyperframes.template 开关：shot-timeline 模板含 bg/title/subtitle/accent 四个带 data-clip/data-start/data-duration 的可寻址 clip；节拍数学（S=seconds）：bg(0,S)、title(0,max(1,(2*S)/3))、subtitle(S/3,S-S/3)、accent((2*S)/3,S-(2*S)/3)；shot-card 仍为默认，老行为不变；非法值 submit 直接拒绝；测试 HyperFramesTimelineTemplateTest 7 例全绿；视觉验收：真实生成 HTML 抓屏亲眼通过（标题/副标题分开、底部 accent 条正常扫过，零 console 错误），验收中抓出并修复 1 个真问题：模板缺全局 margin 清零致 accent 条被 body 默认 8px 边距顶出视口之外。

### Added（深耕轮 2026-10-24 05:07：视频拆解「逐字稿（内嵌字幕提取）」）
- 深耕轮 2026-10-24 17:07，SkillHub 索引默认分页（关闭 TD-003）。GET /api/skillhub/index 始终分页，无参默认第 0 页、每页 50 条（此前无参返回全部条目）；total 仍为过滤后全量，totalPages 按 ceil(total/size) 计算；size 钳制 1 到 200 不变；前端 skillhub 页恒发 page/size 参数，不受影响；依赖无参返回全部的调用方须改传 page/size 或用 q 过滤定位单条。
- 深耕轮 2026-10-24 17:07，前端 skillhub.js 两处修复（视觉验收发现）：卡片描述字段由 desc 改为 description，之前卡片描述恒为空；补齐 skillhub 页 9 个缺失的 i18n 键并按同站既定做法注册词典，之前标题、副标题、搜索框等位置显示 skh.heading 之类裸键。
- 新服务 `SubtitleTranscriptService`：ffprobe 列字幕流（优先 chi/zho/zh）→ ffmpeg 抽取为 SRT → 解析为分段时间轴；无字幕轨道/提取失败时诚实降级（found=false），不炸拆解流水线。
- 流水线接入：`DeconstructionService.runPipeline` 在关键帧抽取后提取逐字稿；逐镜按时段重叠映射字幕文本（`video_deconstruction_shots.transcript_text`）；任务表新增 `transcript_status`（EMBEDDED/NONE）/`transcript_track_info`/`transcript_json`（Flyway V23）。
- 报告：`DeconstructionReportBuilder` 新增 4 参重载，报告新增「## 逐字稿（内嵌字幕提取）」节；口径说明更新——逐字稿改标注"内嵌字幕轨道离线提取"，ASR 语音转写仍未接入（诚实标注，不冒充）。
- API：`DetailDto` 新增 transcriptStatus/transcriptTrackInfo/transcriptSegments；`ShotDto` 新增 transcriptText；`SummaryDto` 新增 transcriptStatus。
- 前端 `deconstruct.html/js`：详情页新增逐字稿区（轨道信息+条数+时间戳列表，无字幕时诚实提示"未检测到内嵌字幕轨道；语音转写（ASR）尚未接入"），逐镜卡片新增"本镜字幕"行；中英双语。
- 测试 9 例全绿：`SubtitleTranscriptServiceTest` 6 例（SRT/VTT 解析：多行/坏块/空/CRLF/NOTE）+ `SubtitleTranscriptExtractIT` 2 例（真实 ffmpeg 生成带字幕/无字幕视频走 extract）+ `DeconstructionTranscriptApiTest` 1 例（MockMvc 全链路：上传带字幕视频→EMBEDDED→3 段→逐镜字幕→报告含逐字稿）；另修 `DeconstructionAnalyzerTest.reportContainsAllSections` 断言以匹配新口径。
- 附带修复生产启动阻断：`RunApproval`/`StepAttempt` 实体此前已存在但无建表迁移，`ddl-auto: validate` 下启动即报 missing table；新增 Flyway V24 补建 `run_approvals`/`step_attempts` 两表，生产 jar 真实启动验证通过。
- 视觉验收：`docs/screenshots/deconstruct-transcript.png`（真实 6 秒 3 镜带字幕视频：逐字稿区 3 条+逐镜本镜字幕+关键帧，零 console 错误）。

### Added（深耕轮 2026-10-20 晚：DoD 未通过项 F2/F3/F4 部署运维补齐）
- F4 依赖更新机制：`.github/dependabot.yml` 升级——maven / github-actions / docker 三生态，每周一（Asia/Shanghai）检查，open-pull-requests-limit 5，commit 前缀 `chore(deps)`，reviewer Wanfeng1028；新增 `spring-boot` 依赖分组（`org.springframework.boot:*` 同批升级）；springdoc 继续钉死 2.6.x（2.7+ 要求 Spring Framework 6.2，本项目 Spring Boot 3.3.5 对应 Spring 6.1.x，见 docs/DEPENDENCY_POLICY.md 附录 B）；npm 生态未启用（仓库无根 package.json，src/main/resources/skills-bundled/ 下约 90 个 package.json 均为 vendored 第三方模板，不适合 dependabot 跟踪）。
- F2 一键部署事实核验：`Dockerfile`（多阶段：maven:3.9-eclipse-temurin-21 构建 → eclipse-temurin:21-jre 运行，内置 ffmpeg；HEALTHCHECK 用 wget 探 http://localhost:8081/api/health）、`compose.yml`（单服务一键部署：docker compose up -d --build）、`docker-compose.yml`（auth + app + nginx 全栈）、`.env.example`（全部环境变量占位齐全）逐项与 `src/main/resources/application.yml`（端口 ${PORT:8081}，默认 8081）、`HealthController`（@RequestMapping("/api") + @GetMapping("/health") 即 /api/health）、`target/drama-factory-1.0.0.jar`（实际构建产物名）核对一致；`compose.yml` 的 healthcheck 由 curl 改为 wget（eclipse-temurin:21-jre 镜像不带 curl，与 Dockerfile 自带 HEALTHCHECK 一致）；`docker-compose.yml` 的 app 服务补 healthcheck（wget 探 /api/health）与 mem_limit: 1g。
- F3 本文件：即本次更新本身，补"已知限制"与"升级指南"两节。

### Added（OpenMontage 集成变更补记，2026-10-19）
- Java 源码 5 个：service/video/VideoProviderRouter.java（七维评分路由）、service/video/ProviderScoreCard.java、service/video/RoutingDecision.java、service/CutRhythmChecker.java、service/UsageService.java（计费台账）。
- 配置/资源：prometheus/prometheus.yml（抓取配置）、resources/pipeline-templates/ 下 animated-explainer / screen-demo / talking-head 三个 pipeline YAML 模板、resources/skills-bundled/ 下 OpenMontage skill 库收录（AGPL-3.0 来源如实标注）。
- 文档 5 篇：docs/OPENMONTAGE_RESEARCH.md、docs/PIPELINE_TEMPLATES.md、docs/SKILL_AUDIT_2026-10-19.md、docs/BACKUP_DRILL_AUTH_2026-10-19.md、docs/OPERATIONS.md、docs/OPERATIONS-AUTH.md。
- 注：HyperFrames 渲染双引擎（chromium/hyperframes，drama.video.htmlrender.engine）已记于本文件"深耕轮 2026-10-20 凌晨 lane A"条目，不重复记录。

### 已知限制（发版级声明，2026-10-20）
- 容器化一键部署已提供（Dockerfile / compose.yml / docker-compose.yml / .env.example），但未经本机实测、未做生产压测，生产上线前必须实测验证。
- 本轮 OpenMontage/HyperFrames 集成范围内无可观测性指标埋点代码（渲染时长、CLI 失败率等未暴露）；仓库既有基础业务指标见 v2.4 条目，Prometheus 抓取配置仅覆盖既有端点。
- 滚动更新/零停机未验证：当前升级动作为停机更新（见升级指南），不支持滚动更新。

### 升级指南
- 停服务：docker compose down（或 kill 掉 java 进程）。
- 备份：./scripts/backup.sh（没备份不许往下走；备份恢复详见 docs/OPERATIONS.md 第 4 节）。
- 拉代码并重建：git pull 后 docker compose build && docker compose up -d（裸 jar 方式：替换 target/drama-factory-1.0.0.jar 后重启；Flyway 启动时自动执行 src/main/resources/db/migration/ 下未执行的迁移脚本）。
- 验证健康端点：curl -s http://localhost:8081/api/health 返回 200 且 JSON 状态正常。
- 回滚：./scripts/restore.sh backups/<备份目录>，换回旧 jar 重启（详见 docs/OPERATIONS.md 第 5 节）。

### Added（视频通道硬约束前置校验，2026-10-20）
- `docs/OPERATIONS.md` 新增「视频通道硬约束」一节：`constraints` 字段含义、提交前校验流程、违规 400 错误体格式（`VIDEO_CONSTRAINT_VIOLATION` + `channel`/`field`/`value`/`allowed`/`source`）、新通道补约束的步骤（出处必须能查证）。
- `README.md` 视频生成任务章节补硬约束说明 + 4 个模型 × 核验值的约束表（agnes-video-2.5-flash / minimax music-3.0 / hyperframes / htmlrender（chromium）），核验日期 2026-10-20，每个值带出处。
- 约束值必须能查到出处，不许瞎填；出处变更先更表再改通道 `constraints`。

### Added（深耕轮 2026-10-20 下午：成本账本看板）
- 后端：`CostLedgerService.summarizeTrend(days)`（[1,90]钳制，含今天，按日期升序，每天一条）；`CostLedgerService.budgetStatus()`（budgetTotalUsd/spentUsd/reservedUsd/usableUsd/utilizationPct/mode/enabled，构造器注入 BillingProperties，reserve() 复用抽出的 usableBudget(BudgetPolicy)）；`CostLedgerController` 新增 `GET /api/cost-ledger/trend?days`（默认14，非法400，超限由 service 钳制）、`GET /api/cost-ledger/budget`；`GET /api/cost-ledger/entries` 新增 limit 参数（默认100、最大500，非法400）。
- 前端：`cost-ledger.html` 看板页（导航"运行"→"成本账本"，shell.js 接入+nav.costLedger 中英 key）：预算卡（总额/已花费/冻结中/可用+使用率进度条，70%/90% 变色）、今日/近7天/累计条目/供应商数 KPI、14 天趋势 SVG 折线图（7/14/30 天切换，手写 SVG 零依赖）、按供应商条形、当天明细表（limit=20，状态 badge）；中英双语（PAGE_I18N 38+18 key）；Tabler 原生组件，无自创配色。
- 测试：新增 6 个测试文件 24 例全绿；修 1 个 dpsk 测试 bug（failedCountsTowardSpentAndRefundedCountsTowardNothing 误调 complete，应调 refund，spent 口径以实现为准）。
- 文档：README 成本账本节升级（含 5 接口表与看板截图）、OPERATIONS.md 查询接口表补齐 5 行、截图 docs/screenshots/cost-ledger/dashboard.png（36 条跨 14 天种子数据，亲眼验收：KPI/趋势/条形/明细全对）。
- 附带修：shell.js 补 nav.prompts 中英 key（历史遗漏致导航显示 raw key）。

### Added（深耕轮 2026-10-20 凌晨，lane A：skillhub / HyperFrames 渲染 / Toonflow 二阶段）
- 自有 SkillHub：`GET /api/skillhub/index`（hub=playhouse-skillhub，全部内置+社区收录 skills，来源标注"官方出品"/"社区收录"，含 installed 状态；异常时返回空列表 200，不 500）+ 前端 `skillhub.html`（搜索/来源筛选/一键安装到 data/skills/，挂载"运行"分组导航，Tabler 风格）。测试：SkillHubIndexControllerTest 5 例。
- HtmlRenderVideoProvider 双引擎：`drama.video.htmlrender.engine=chromium|hyperframes`（默认 chromium）；hyperframes 引擎经 `--version` 探活后走 `hyperframes render -c composition.html -o out/video.mp4 --resolution 1080p --fps <fps> --no-browser-gpu`，CLI 不可用/渲染失败自动降级 chromium 并打 warn。测试：HtmlRenderEngineSelectionTest 7 例。运维：`scripts/hyperframes_probe.sh`（JSON 探活，输出 engine 推荐值）。文档：docs/DEGRADATION.md 新增"htmlrender 双引擎"小节；application.yml/.env.example 新增配置说明。
- Toonflow 二阶段：docs/TOONFLOW_DEEPSEEK_PROVIDER_EVAL.md（deepSeek 语言 provider 评估：能力事实/与 LlmScriptService 对照/价格待官网核验/并入建议走可配置 language-provider 注册表）；3 组 toonflow skills 合规复审 docs/TOONFLOW_SKILLS_REVIEW_2026-10-20.md（difflib 相似度 0.911–0.982，_index.json rewritten 标注失实已纠正，3 个目录补上游 MIT LICENSE）。
- 4 个 Toonflow provider 描述符 QA：docs/TOONFLOW_DESCRIPTORS_QA_2026-10-20.md（schema 一致性逐项核验）。

### Added（v3.0 审核流，2026-10-19）
- 剧本两级审核状态机：DRAFT → PENDING_L1 →（驳回回 DRAFT / 通过去 PENDING_L2）→ APPROVED / REJECTED。
- 分镜单级审核状态机：DRAFT → PENDING → APPROVED / REJECTED。
- Run 执行门：VIDEO 步骤执行前要求该集剧本为 APPROVED，未过审则 run 置 PAUSED 等待（日志"等待剧本过审"），过审后 resume 继续。
- 审核历史审计：review_history 表记录每次流转（谁、何时、事件、意见、版本号），只增不删。
- 审核队列页：review.html（Tabler 1.6.1），待审列表 + 批准/驳回按钮 + 意见输入。
- 自审透明标记：ReviewDetailResponse.selfReviewed 字段，前端醒目提示，不硬拦截同人提交与审批。
- REST API：/api/projects/{projectId}/episodes/{episodeId}/review/submit|l1|l2|reject|history，/api/projects/{projectId}/review/queue。错误码：非法流转 409、跨项目 403、kind 不匹配 404。
- Flyway V18__review_flow.sql：review_item / review_history 表，episode 删除级联。
- 新增测试：ReviewServiceTest 29 例、ReviewApiTest 9 例、RunExecutorReviewGateTest 3 例。
- 设计文档：docs/REVIEW_FLOW.md。

### Fixed（深测轮 r3，2026-10-18）
- PromptRecipeService.apply 并发丢更新：改为 `@Modifying` 原子自增 + `@Transactional`。
- UsageService.summary/requests 的"不限时间"查询：`LocalDateTime.MIN` 在 H2 上比较返回空，改用 1970-01-01 下界常量 `TIME_BEGIN`。
- GlobalExceptionHandler 新增 `DataIntegrityViolationException` -> 400 映射（超长入参不再 500）。

### Tests（深测轮 r3，2026-10-18）

- 41 个 `*DeepTest`、652 用例；全量失败+错误从 73 降至 61。
- 新增 `PromptTemplateServiceDeepTest` / `RunServiceDeepTest` / `PipelineServiceDeepTest` / `ChatServiceDeepTest` / `PresetServiceDeepTest`。
- 对齐了一批测试期望与产品真实语义的偏差（见 `docs/DEEPTEST_ROUND_R3.md`）。

### Known issues

- SkillService.install 并发同版本安装存在竞态（唯一约束冲突），测试暂为串行幂等验证，产品侧修复待排期。

### Added

- v2.32「flaky 收尾：ffmpeg 输出竞态 + 中断异常收敛 + 重试逃逸」（2026-10-17，关闭 `docs/FLAKY_ROOT_CAUSE.md` §7 残余风险 ③④⑥）：
  - `FfmpegService.run()`：`reader.join(2000)` 固定上限等待改为有上限循环 join + `reader.isAlive()` 守卫，
    预算耗尽仍未结束时 message 标注"可能不完整"，不再静默截断；新增
    `FfmpegInterruptedException extends FfmpegException`（`(String, Throwable)` → `super(m, t, false)`），
    三处中断 throw 点收敛为专用异常。
  - `FinalCutService.withFfmpegRetry`：新增 `catch (FfmpegInterruptedException)` 直接 throw（终止重试）；
    sleep 中断改抛专用异常（修复 cause=null）；`catch (RuntimeException)` 收敛为保守 transient 重试。
  - `VideoTaskService.processDueTasks()`：新增 `catch (FfmpegInterruptedException)`——恢复中断标志 +
    `failOrRetry(task, msg, true)`。
  - 测试 9 例：`FfmpegOutputRaceV232Test` 3 例（2.621s）+ `FfmpegInterruptV232Test` 3 例（12.92s）+
    `FfmpegRetryEscapeV232Test` 3 例（14.12s）。
  - 文档：`docs/FLAKY_ROOT_CAUSE.md` §7/§2/§6/§8/§9 同步；`docs/dod-v2.32.md` 为发版对照。
  - 验证：新测试 9/9；回归 13 类 64/64（既有 10 类 55/55 基线），无回归；
    全量 `mvn -o verify` 本轮未跑（只跑受影响的 13 类；铁律：不降 JaCoCo 门禁），
    v2.31 全量数据（2013 例，14 失败 + 11 错误，Qwen 相关）保持原样。
  - 诚实声明：残余风险 ⑤（多实例 CAS 单飞）本轮仍未关闭，留待多实例场景再议；
    概率性场景（输出竞态 / 中断路径）9/9 通过为当前样本量观测结果，不宣称已彻底消除。
- 发版对照报告：`docs/dod-v2.32.md`。

- v2.31「flaky 收尾：退避预算上限 + 启动异常精细分类」（2026-10-17，dod-v2.28 排期"flaky 残留 2 处代码漏洞"全交付）：
  - `FinalCutService`：单次成片构建内所有 ffmpeg 步骤共享退避预算，
    `drama.ffmpeg.retry-total-budget-ms`（`FFMPEG_RETRY_TOTAL_BUDGET_MS`，默认 20000ms）；
    `claimRetryBackoff(AtomicLong, long)` 认领睡眠；预算耗尽后仍尝试剩余次数但不再睡眠；
    13 参 `@Autowired` 构造器 + 保留 12 参委托构造器（默认 20000L），既有测试零改动。
  - `FfmpegService.isTransientLaunchFailure(IOException)`：正向识别 cannot allocate memory /
    too many open files / resource temporarily unavailable 为瞬时，其余保持永久（v2.29 行为）。
  - 测试 17 例：`FinalCutRetryBudgetV231Test` 7 例 + `FfmpegLaunchClassifyV231Test` 10 例（含真实缺失二进制端到端）。
  - 文档：新增 `docs/FLAKY_ROOT_CAUSE.md`（诚实根因报告）；`docs/dod-v2.31.md` 为发版对照；
    `application.yml` + `docs/FFMPEG_RELIABILITY.md` + `docs/OPERATIONS.md` 同步新配置键。
  - 验证：新测试 17/17；既有相关 8 类 38/38 无回归；testFullPipeline 基线 2/2 → 修复后 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）；
    全量 verify 2013 例，14 失败 + 11 错误，8 skipped，JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）。
- 发版对照报告：`docs/dod-v2.31.md`。

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
- v2.29 第二阶段「覆盖率收尾 + flaky 根因验证」（2026-10-17）：
  - 基线：干净环境全量 1921 例，BRANCH 84.07% / LINE 87.95%（门禁已红，缺口 65.8% 来自他人在途新代码——视频管线轮次 + agent-canvas，按铁律不代写）。
  - 新增 11 个 *V229* 测试文件共 75 例（dpsk 生成），终版全量 1996 例全部通过，无新增失败：
    AuthProxyControllerV229Test(13) / V229D2Test(6)、LlmScriptServiceV229Test(4) / V229D2Test(4)、
    JwtAuthFilterV229Test(9)、SettingsEnvPostProcessorV229Test(2 skipped)、EpisodeServiceV229Test(7)、
    PromptTemplateServiceV229Test(8)、CharacterServiceV229Test(10)、RunExecutorV229Test(9) / V229D2Test(3)。
  - 覆盖率：BRANCH 84.07%→85.00%（+0.93%）、LINE 87.95%→88.75%（+0.80%）；3 个类清零（JwtAuthFilter/CharacterService/PromptTemplateService）。
  - flaky 验证结论：基本歼灭，有低概率残留（testFullPipeline 本轮 25.31s 通过；2 处结构性残留：退避总额无上限、pb.start IOException 误判永久）。
  - 诚实声明：门禁仍红（BRANCH 0.85/LINE 0.89）；Qwen 6 个测试类红（他人在途改动未同步）；11 处不可达分支已论证（见报告）。
  - 发版对照报告：`docs/dod-v2.29.md`（本轮重写）。

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
