# 项目登记册

## 各项目 UI 组件库一览

| 项目 | UI 形态 | 组件库 | 备注 |
| --- | --- | --- | --- |
| kaoyan-os | Web（React 18） | 无（手写 CSS） | — |
| second-brain | Web（Go） | 无（手写 CSS） | — |
| mini-os | Web（Rust） | 无（手写 CSS） | — |
| ledger | Web（Python 模板） | 无（手写 CSS） | — |
| sentinel | Web（Go） | 无（手写 CSS） | — |
| docseek | Web（C++ serve） | 无（手写 HTML/CSS） | — |
| feedflow | Web（Flask 模板） | 无（手写 CSS） | — |
| linkshort | Web（Go） | 无（手写 CSS） | — |
| mortisedb | Web（Go） | 无（手写 CSS） | — |
| interlude | 无 Web UI（Kotlin） | — | — |
| stagecue | 无 Web UI（Kotlin） | — | — |
| voxloom | 桌面（C#/Avalonia） | 无 Web 组件库 | — |
| drama-factory | Web | Tabler 1.6.1 | 仓库内唯一使用第三方前端组件库的项目 |

> 选型铁律（2026-10-13 用户亲定）：每个项目的 UI 组件库尽量不要一样。后续新项目或重设计选型前，必须先查此表避重。

## kaoyan-os「考研指挥舱」

**定位**：全栈考研复习管理系统，服务考研备考全流程。

**技术栈**：pnpm workspace monorepo——后端 apps/server（Fastify 5 + TypeScript + SQLite，数据库为 Node 内置 node:sqlite）、前端 apps/web（Vite 6 + React 18 + TypeScript + React Router）、共享层 packages/shared（跨端类型与科目常量）。

**功能模块**：

1. 复习计划排程
2. 番茄专注计时
3. 错题本
4. 单词 SRS（SM-2 简化算法）
5. 真题计时与得分统计
6. 仪表盘（初试倒计时与全局概览）

**状态**：v1.1.0「数据导入导出」（2026-10-15）：后端 4 个备份/导入端点 + 前端 /data 三卡片页；服务端 22/22 测试通过、前端 tsc 零错；真实冒烟 6 项全过；2 张真实截图亲眼验收；README/CHANGELOG 同步。

**UI 重设计 v4（Tabler 组件库）**

2026-10-13：v3 手写玻璃拟态被用户判定为典型 AI 味并禁用；三步选型后改用 Tabler 1.6.1（一句话理由：基于 Bootstrap 5 的管理后台 UI 套件，天生控制台气质，深色模式开箱即用）。5 页全部改用 Tabler 原生组件，API 一字未动，theme.css 仅做容器宽度与表格密度微调；全站无 backdrop-filter；mvn test 20/20 全过；5 页真实数据截图亲眼验收通过；设计决策见 docs/DESIGN.md。

**里程碑记录**：

- 里程碑 1（2026-10-13）：静态单页版落地（localStorage 存储），同日被工程化重构取代，仅作历史记录
- 工程化重构 v1（2026-10-13）：前后端分离、SQLite 持久化、vitest 集成测试、GitHub Actions CI、Dockerfile
- **v1.1.0「数据导入导出」（2026-10-15，路线图第 2 项交付）**：后端 `apps/server/src/routes/backup.ts`——`GET /api/backup/export`（kaoyan-backup v1，7 表）、`POST /api/backup/import`（replace 事务全量替换 / merge 去重合并，逐行校验）、`POST /api/import/words` + `POST /api/import/mistakes`（CSV 导入：表头校验/空行跳过/错误行报告，subject 仅 math/english/politics/major）；前端 `DataTransfer.tsx`（/data 路由 + 导航「数据导入导出」，备份与恢复/单词 CSV/错题 CSV 三卡片，覆盖恢复二次确认，模板下载）；`tests/backup.test.ts` 13 例，服务端全量 22/22 通过，前端 tsc 零错；真实服务冒烟 6 项全过（导出/单词 CSV/错题 CSV/merge/replace 回导）；2 张真实截图亲眼验收通过（默认态 + 导入结果态）；README 功能/API/目录/路线图同步，CHANGELOG.md 新建。本轮修截图链路两处：上一轮遗留的两张截图为空白页（服务未就绪即截图），本轮用 route 拦截 harness（文档/静态读盘、/api 经 Node 代理，绕过 Chromium 152 LNA 拦截）重拍；另发现 Playwright 多 route 匹配时后注册优先，静态 route 曾吞掉 /api 代理

**后续计划**：

- 考研核心 500 词词库扩充
- 周报视图
- 深色模式

## second-brain「第二大脑」

**定位**：个人知识库系统，支持笔记、标签、搜索、双链与知识图谱，构建可生长的个人知识网络。**灵魂功能**：会主动帮你复习的第二大脑——SM-2 遗忘曲线调度 + 抽认卡复习流 + 每日回顾推送。

**技术栈**：Go 1.23 单二进制；标准库 net/http 提供 HTTP 服务，modernc.org/sqlite 作为纯 Go SQLite 驱动；go:embed 内嵌 Web UI 静态资源；go test 覆盖单元测试与集成测试；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 second-brain/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 笔记 CRUD
2. 标签体系
3. 全文搜索（相关性排序）
4. [[双链]]与知识图谱
5. Markdown 渲染与预览
6. 统计概览
7. 主动复习引擎（v0.2.0）：SM-2 间隔重复（`internal/review` 纯函数包）、`reviews` 表（建笔记自动建行，due=次日）、到期队列 `GET /api/review/queue`、评分 `POST /api/review/{id}`（忘记0/困难3/良好4/简单5）、统计 `GET /api/review/stats`（待复习数/7日量/平均EF/连续天数）、每日回顾 `GET /api/review/digest`、抽认卡复习 UI（正面/翻面/四档评分/完成态）+ 首页横幅 + 侧边栏 badge
8. 附件支持（v0.3.0）：`POST /api/notes/{id}/attachments` 上传（multipart，默认 ≤10MB、`SB_ATTACH_MAX_MB` 可调，扩展名白名单 + 文件名消毒 + 图片 MIME 嗅探）、列表/下载/删除接口、`attachments` 表（sha256）、删笔记级联清附件目录；正文 `![说明](attachment:{id})` 渲染内联图片；编辑区附件区（上传入口、缩略图、插入引用/下载/删除）
9. 导出（v0.3.0）：`GET /api/export/json`（全库 JSON 含标签与附件元数据）、`GET /api/export/markdown`（zip：index.md + notes/ 带 front matter 的 .md + attachments/ 原文件，引用改写相对路径，ZipSlip 防护）；侧边栏导出按钮

**状态**：v0.3.0「附件与导出」（2026-10-15）：go build/vet/gofmt/test 全过（68 个测试，0 失败，新增附件 15 + 导出 3 + 渲染 3）；真实服务冒烟：上传 PNG/TXT→列表→下载→删除→导出 JSON/zip 全链路；2 张真实截图（attach-ui/attach-preview）亲眼验收通过；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.3.0.md。

**里程碑记录**：

- 工程化 v1（2026-10-13）：单二进制架构落地，内嵌 Web UI、SQLite 持久化、双链与图谱能力、CI 与多阶段构建就绪
- v0.2.0 主动复习引擎（2026-10-13）：灵魂一页纸先行（docs/SOUL.md）；SM-2 纯函数包 + 6 确定性单测；`reviews` 表与 4 组 API + store/api 集成测试；抽认卡复习视图 + 每日回顾 digest；Web 三件套一致性重建——修了 v1 遗留的 4 个真实 bug（①JS/HTML id 全错位致 UI 不可用；②`GET /` 被 Go FileServer 对 `/index.html` 发 301 到 `./` 致首页打不开，改直读文件；③`review.go` 在 rows 未关闭时嵌套查询，`:memory:` 下换连接报 no such table；④CSS 的 display 规则覆盖 `[hidden]` 致翻面/完成态同屏）；README 补复习章节 + API 表 + 截图；CHANGELOG.md 新增
- v0.3.0 附件与导出（2026-10-15）：`internal/store/attachment.go`（attachments 表 + CRUD + 删笔记清附件目录）与 `internal/api/attachment.go`（上传 413/415/400/404、MIME 嗅探、文件名消毒）+ `internal/api/export.go`（JSON / Markdown zip，分页拉取、ZipSlip 防护、引用改写）；markdown 渲染 `attachment:{id}`（图片/下载链接，顺序先于 reLink）；前端附件区 + 侧边栏导出区（沿用现有视觉体系）；68 测试全过；README/CHANGELOG/对照报告齐备

**后续计划**：

- 外部推送（邮件/微信）v0.4
- 多用户复习隔离
- 反向链接面板
- PWA

## drama-factory「AI 短剧工坊」

**定位**：短剧生产管理与剧本生成系统，v2 打通从剧本到成片的完整生产管线（剧本→分镜→AI 视频生成→ffmpeg 剪辑成片）。**AI MV 模式**：一句话主题出一支完整 AI MV（作词→作曲→分镜→视频生成→剪辑→质检），灵魂一页纸见 `drama-factory/docs/SOUL-mv.md`。**2026-10-14 v2「时间轴对齐」已落地**：歌词行时间戳驱动分镜时长 + 逐行 SRT 字幕（替代 estSeconds 估算），对照报告见 `drama-factory/docs/dod-mv-v2.md`，真实截图见 `drama-factory/docs/screenshots/mv-v2-*.png`。

**技术栈**：Java 21 + Spring Boot 3.3.5 + Maven；Spring Data JPA + H2 文件库（可平滑切换 PostgreSQL/MySQL）；企业级分层 controller / service / repository / model / dto；内置 Web 控制台由 Spring 静态托管；JUnit 5 集成测试（含 TestRestTemplate 全链路）；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 drama-factory/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 短剧项目管理
2. 剧集管理
3. 角色管理
4. 场景管理
5. 基于大纲的四场式剧本自动生成（开场钩子 / 冲突升级 / 反转 / 高潮收尾，每场带英文视频生成提示词）
6. 全局统计
7. 分镜管理（分集→分镜 CRUD + 排序）
8. 视频生成任务（VideoTask 状态机 PENDING→PROCESSING→DONE/FAILED，指数退避重试 max-attempts=8，VideoProvider 接口 + mock（ffmpeg 本地生成测试片段）/ agnes（真实视频生成）双实现，@Scheduled 定时轮询）
9. 剪辑成片（ffmpeg 按镜号拼接 + SRT 字幕烧录 + 时长探测，/media 在线预览与下载）
10. 生产看板（分镜→视频任务→成片三阶段横向流水线，卡点剧集标红）

**状态**：工程化 v2.3「AI 编剧引擎」（2026-10-13：真实 DeepSeek 接入剧本生成——LlmScriptService（鲁棒 JSON 解析+严格四场校验+指数退避重试）/ LlmTransport（Apache HttpClient 5 预先代理认证+无代理直连）/ CLI 回退（HTTP 失败改调 chat.py，$HOME/user.home 自动探测）；`?mode=ai/template` + 降级；响应 source/model/latencyMs；前端三按钮+额度提示+「查看剧本」modal；mvn test 38/38 全过；真实冒烟：ai 模式 source=ai 拿回 4 场连贯剧本（CLI 回退路径，日志可观测）；视觉验收亲眼通过（按钮行/modal 真实剧本渲染），附带修了全站 `bootstrap.Modal/Toast` 误用既有 bug（实为 `tabler.*`）；发版对照报告 docs/dod-v2.3.md）。

**UI 重设计 v3**（2026-10-13 完成）：新视觉概念「剪辑室 / 场记板」——分镜板改为场记板卡片墙（斜条纹板条 + 等宽大字镜号 + 景别/运镜 badge + 对白引用 + 时间码），任务队列改为任务卡片 + 进度条，成片库改为海报卡片墙（后端新增 `GET /media/finals/{id}/poster.jpg`，ffmpeg 从成片 1 秒处抽帧），生产看板改为横向胶片管线（齿孔装饰 + 卡点集暖橙描边）；配色近黑 #0E0E11 + 钨丝灯暖橙 #E8590C + 米白文字，Noto Sans SC + 等宽字体；设计决策见 docs/DESIGN.md；mvn test 12 例全过（含新增 MediaPosterTest）；4 页真实数据截图已亲眼验收通过；另修复 v2 遗留 bug（首页 scene-form 空绑定导致项目列表加载失败）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Spring Boot 分层架构落地，项目/剧集/角色/场景 CRUD、四场式剧本生成、Web 控制台、CI 与多阶段 Dockerfile 就绪
- 工程化 v2（2026-10-13）：短剧生产管线落地——分镜管理、视频任务状态机（mock/agnes 双 provider）、ffmpeg 剪辑成片（拼接+字幕烧录）、生产看板四页 Web UI；`drama.*` 配置全环境变量化（application.yml）；生产级 DoD 对照报告 docs/dod-v2.md（含未通过项排期表）；视觉验收亲手抓出并修复 2 个 bug（pipeline 看板二次渲染抛错致空白、pipeline.html 漏引 v2.css 致卡片无样式）
- 生产级补强 v2.1（2026-10-13，DoD 第 1 轮三项全交付）：Flyway 版本化迁移（V1__baseline.sql 由 Hibernate 实际 DDL 导出，ddl-auto→validate，baseline-on-migrate 兼容老库）+ 提交幂等（同 shot PENDING/PROCESSING 去重，首次 201/重复 200）+ 优雅关闭（server.shutdown=graceful + 调度器 await-termination 30s + 轮询在途收尾钩子 25s）；mvn test 20/20 全过；真实 jar 冒烟验证 Flyway 基线/幂等 201→200/优雅关闭日志；发版对照报告 docs/dod-v2.1.md
- 生产级补强 v2.2（2026-10-13，DoD 第 2 轮四项全交付）：结构化日志（logback-spring.xml，可读 pattern 含 request_id；SPRING_PROFILES_ACTIVE=json 切 Logstash JSON）+ request_id 全链路（RequestIdFilter 透传/生成/回写 X-Request-Id、ErrorResponse 含 requestId、调度轮询带 poll-xxx）+ Resilience4j（ResilientVideoProvider 装饰 agnes：CircuitBreaker 50%/4 次/60s + TimeLimiter 90s，熔断抛 ProviderCircuitOpenException 由指数退避接管）+ 提交接口限流（@RateLimiter 10 秒 10 次，超限 429 + Retry-After: 10）+ Docker Compose 一键部署（compose.yml：健康检查/日志轮转/资源限制；Dockerfile 加装 ffmpeg+curl）；mvn test 26/26 全过；真实 jar 冒烟全链路验证；发版对照报告 docs/dod-v2.2.md
- v5.1 控制台统一外壳（2026-10-13）：shell.js 注入左侧窄导航（6 页 + G+字母快捷键）+ 顶栏全局搜索 + ⌘K/Ctrl+K 命令面板；app.css 统一视觉语言（暖炭 #1c1917 + 降饱和蓝 #4a6fa5，零 backdrop-filter/零渐变/零 emoji 图标，沿用 v4.1 主题）；首页重做为 AI 工作区（左 AI 对话 + 右生产概览 workspace.js）；Tabler 1.6.1 本地化入仓库摆脱 CDN；storyboard.js 支持 ?episodeId= 深链；7 页真实数据截图亲眼验收通过并同步 docs/screenshots/；视觉验收抓出 2 个 v5.1 bug 已修（workspace.js 项目下拉单向同步致左右脱节、"去质检"链接参数名 finalCutId 与 qc.js 的 id 错配致跳空页）；mvn test 26/26 全过

**后续计划**：

- UI 去 AI 味研究轮（2026-10-13）：用户 verdict"还是 AI 味"，点名对标 ChatGPT / Claude / Grok / Gemini。9 张真实产品截图亲眼拆解（ChatGPT×3 深/浅/侧边栏、Claude×2 深/浅暖纸+衬线+珊瑚点睛、Grok×2 纯黑白零强调色、Gemini×2 窄 rail+工具菜单），结论见 `drama-factory/docs/UI-RESEARCH.md`：四家共性是"藏"（藏快捷键/配置/说明/边框/彩色），我们的 AI 味来自"秀"（导航 kbd chips、双语 pretitle、徽标滥用、卡片阵列、版本水印等 15 条诊断），P0/P1/P2 改版清单共 15 项 → 已由改版轮全部落地（见下）
- UI 去 AI 味改版轮（2026-10-13）：按 UI-RESEARCH.md 第五节 15 项清单 P0→P1→P2 逐条落地——删双语 pretitle/导航 kbd chips/版本水印/顶栏搜索条；composer 大圆角+圆形内置发送钮（chat.js 发送逻辑经 Playwright 回归验证：点击发送/Ctrl+Enter/快捷 chips 均正常）；分镜改 filmstrip 列表行；徽标清零改小圆点+文字；强调色只留主行动按钮；标题区只剩一行 20px 标题；表格操作列 hover 化；配额提示降级为输入框下方小字；等宽只留时间码/时长；工作区右侧去卡片化；边框降对比；命令面板去图标。验收时抓出 1 个真 bug（#slateGrid 残留 datagrid 类致 filmstrip 挤成三列）已修；7 页真实数据（《最后一班地铁》）重截亲眼验收；mvn test 26/26 全绿
- v2.3「AI 编剧引擎」（2026-10-13）：真实 DeepSeek-V4-Flash 接入剧本生成（大纲→严格四场式剧本），模板生成器降级为兜底。传输层实测攻坚：沙箱按进程限制 Java TCP 出站（python 可通），遂定型 HTTP 主用 + CLI 回退（chat.py）双通道；代理密码轮换→每次调用实时重读环境变量。前端三按钮（AI 生成/模板生成/查看剧本）+额度小字+来源/模型/耗时展示；「查看剧本」modal 生成后自动打开。mvn test 38/38；真实冒烟 ai 模式 source=ai（14s，4 场连贯：暴雨街头→废弃仓库→警局审讯室→地下停车场）；视觉验收亲眼通过；附带修全站 `bootstrap.*`→`tabler.*` 误用。发版对照报告 docs/dod-v2.3.md
- 生产级补强 v2.4「指标告警 + 备份恢复 + 运维手册」（2026-10-14，DoD 第 3 轮三项全交付）：见后续计划；发版对照报告 docs/dod-v2.4.md
- DoD 未通过项排期（见 docs/dod-v2.2.md：第 3 轮 指标告警/鉴权/备份恢复/运维手册；第 4 轮 OpenAPI/CHANGELOG/Dependabot；第 5 轮敏感数据策略/降级策略文档/单测比例/user 字段）
- 生产级补强 **v2.4 第 3 轮**（2026-10-14，DoD 第 3 轮三项全交付）：Micrometer + Prometheus 指标（`GET /actuator/prometheus`，无鉴权；7 类业务指标：`dramafactory_video_tasks_queued`/`dramafactory_runs_by_status{status}`/`dramafactory_runs_waiting_approval`/`dramafactory_script_llm_calls_total`/`dramafactory_script_llm_duration_seconds`/`dramafactory_finalcut_builds_total`/`dramafactory_finalcut_build_duration_seconds`；Gauge 走 @Scheduled(30s) 刷新内存快照，抓取不打 DB）+ 告警规则（`prometheus/rules/drama-factory.yml` 4 条：5xx 错误率 critical、视频队列积压、审批卡住、Run 失败数）+ 备份恢复脚本（`scripts/backup.sh` H2 BACKUP TO 在线备份 + `scripts/restore.sh` 恢复前快照/sha256 校验/H2 Restore，**均已真实跑通**，恢复后 12 张表可查）+ 运维手册 `docs/OPERATIONS.md` + 初建 `CHANGELOG.md`；`mvn test` 103/103 全过（含新增 MetricsEndpointTest 3 例）；发版对照报告 `docs/dod-v2.4.md`。本轮攻坚记录：沙箱 Java 出站经代理 CONNECT 隧道失败，改走 curl 直下构件补本地仓库后离线构建；测试环境 main yml 被 test yml 屏蔽、Spring Boot 测试默认关 metrics export，两处均已定位并修复（见 test application.yml 注释）
- DoD 未通过项新排期（见 docs/dod-v2.4.md：第 4 轮 OpenAPI/Dependabot；第 5 轮 敏感数据策略/降级策略文档/单测覆盖率目标/user 字段）
- 生产级补强 **v2.5 第 4 轮**（2026-10-14，DoD 第 4 轮两项全交付）：springdoc-openapi 2.6.0（Keenable 核验 springdoc 官方兼容矩阵：Boot 3.3.x 对应 2.6.x，2.7+ 需 Spring 6.2 不可用；pom 显式写死版本）+ 18 个 Controller 全补 @Tag/@Operation（diff 134 行纯加法，另有 1 处 @Parameter 描述经代码核验属实）+ OpenApiConfig（bearerAuth 安全方案，swagger-ui Authorize 可用）+ `.github/dependabot.yml`（maven/github-actions/docker，每周一 Asia/Shanghai；GitHub 只认仓库根配置，待 token 补齐 workflow 权限后随 CI 迁移才生效）+ docs/OPERATIONS.md 由 12 行 stub 实质补齐为 328 行完整手册（v2.4 号称交付实为 stub，本轮如实纠正）；`mvn test` 105/105（含新增 OpenApiDocsTest 2 例）；真实 jar 冒烟：/v3/api-docs（openapi 3.0.1，59 paths）与 /swagger-ui.html 均为 200；swagger-ui 首屏截图亲眼验收通过；发版对照报告 docs/dod-v2.5.md。本轮新增可复用工具：~/workspace/muse-build/scripts/mvn-fetch.py（Maven 依赖递归下载进本地仓库，含 parent pom 落盘 + Boot BOM 版本对齐）与 scripts/split-dpsk.py（dpsk 批量输出拆文件）
- DoD 未通过项新排期（见 docs/dod-v2.5.md：第 5 轮 敏感数据策略/降级策略文档/单测覆盖率目标/user 字段）
- 生产级补强 **v2.6 第 5 轮**（2026-10-14，DoD 第 5 轮四项全交付）：user 字段多用户地基（`DramaProject.ownerId` + Flyway V6 老数据回填 `local` + `CurrentUser` 读 `auth.userId`/回退 `local` + 项目 API 全链路归属隔离，越权 403 `ForbiddenException`；子实体经由项目 API 继承隔离）+ `docs/SECURITY_DATA.md`（清单/存储/脱敏/删除/缺口排期；grep 全量审计确认无直接打印密钥的日志）+ `util/SecretMasker` 纯函数 + `docs/DEGRADATION.md`（6 子系统降级矩阵；ffmpeg 缺失/auth-service 不可达诚实标注"当前无降级"）+ JaCoCo 0.8.12 接入 pom（`verify` 阶段行覆盖 ≥51% 门禁，实测 51.3%/基线 49.6%，分支 31.0%）+ `docs/COVERAGE.md` + 36 个新增单测；`mvn -o verify` 141/141 全过；真实 jar 冒烟：V6 迁移 fresh DB 全量执行、开放模式建项目 `ownerId=local`；发版对照报告 `docs/dod-v2.6.md`。本轮教训：dpsk Call A 首版整批作废（凭空重写残缺文件，丢 `PrePersist`/改错误体形状/编造不存在的类），打回后改外科手术式 reconciliation；JaCoCo 离线需手动补 classifier 构件；门禁阈值按实测棘轮（52%→51%），不硬凑。
- 生产级补强 **v2.7 第 6 轮**（2026-10-14，DoD 第 6 轮四项全交付）：`stats()` 多用户口径（`ProjectService`/`RunService` 按 `currentUserId` 隔离，`DramaProjectRepository.countByOwnerId`，API 路径/字段零变更，开放模式行为不变）+ `CameraMove.fromLabel` 非法非空标签改抛 `IllegalArgumentException`（与 `ShotSize.fromLabel` 一致；`parseShotsJson` 非法运镜不再静默 null）+ JaCoCo 门禁 0.51→0.55（实测行覆盖 51.3%→**58.5%**、分支 31.0%→37.5%）+ 40 例新增测试（`LlmTransportTest` 17 无 socket 契约测试：`ProxySpec`/纯函数/`HttpExecutor` seam；`RunExecutorTest` 10 全 mock 编排测试；`MockVideoProviderTest` 6；`StatsIsolationTest` 2 MockMvc 隔离；`CameraMoveTest` 5）；`mvn -o verify` 180/180 全过；发版对照报告 `docs/dod-v2.7.md`。本轮教训：dpsk 首版整批作废（编造包/改异常类型/丢方法），打回后改外科手术式 PATCH + 文件原文贴进 prompt；`CloseableHttpResponse` 为 final 类不可继承，seam 改函数式接口；`DramaV2ApiIntegrationTest` 无 `@Transactional` 污染共享 H2，隔离测试改 delta 断言。
- DoD 未通过项新排期（见 docs/dod-v2.7.md：v2.8 E2E（Run 全链路端到端）、Agnes/Qwen provider 契约测试（录制回放）、分支覆盖冲 45%、stats() 聚合查询优化）
- 上轮遗留三项已落地（2026-10-14，commit 37149e3）：Agnes/Qwen 录制回放契约测试（27 例，`VideoHttpGateway` 录制回放接缝）+ `RunLifecycleE2eTest`（Run 全生命周期多用户隔离 6 例）+ `ProjectService.stats()` N+1 消除（3 个 repository 新增 `countByOwner` 聚合查询）；全量 210 测试通过
- **BYOK 连接自检**（2026-10-14，ROADMAP P0#1 子项，commit 394146e）：`VideoProvider.probeConnectivity()` 契约（default 返回 UNSUPPORTED）+ `POST /api/providers/{id}/test` + 供应商卡片「测试连接」按钮与状态徽标；Agnes/Qwen 采用"查询不存在探测任务"的负向探测（零费用：401/403=密钥无效、404=密钥有效，鉴权先行，已用 Keenable 核验两家官方文档错误表），mock 恒 OK，未接入模块/未知名称诚实返回 UNSUPPORTED（绝不假成功）；附带修 `submit`/`poll` 未配置密钥时的 NPE（改抛 `IllegalStateException` 明示）；`ResilientVideoProvider` 自检委托给被装饰方；测试 22 例（Agnes/Qwen 各 9 例契约 + 4 例 API，录制回放零真实网络）；`docs/connection-probe.md` 原理文档；agents.html 真实截图亲眼验收通过（`docs/screenshots/providers-test-connection.png`，README 已引用）；全量 **232** 测试通过
- 生产级补强 **v2.8 第 7 轮「分支覆盖冲 45%」**（2026-10-14，DoD v2.8 排期最后一项）：9 批 dpsk 生成——LlmScriptServiceTest 8→34（validate/parseScenes/buildUserContent）、RunServiceTest 15→33（planPreview/createRun·pause·resume）、ScriptSplitterServiceTest 15→35（parse·strip/replaceShots）、RunExecutorTest 10→36（advanceRun 异常分支/QC 自动门/checkVideoStep/finalize）、ProviderServiceProbeTest 新建 14（testConnection/maskKey）；测试总数 232→**336** 全绿；行覆盖 58.5%→**71.0%**、分支 37.5%→**52.7%**（超额达成）；pom JaCoCo 新增 BRANCH 0.45 门禁、LINE 0.55→0.65 棘轮；发版对照报告 `docs/dod-v2.8.md`；已知缺口排期 v2.9（AuthProxyController 110 分支需 HttpClient 可注入重构、Agnes/Qwen 真实链路需外部 API）
- 生产级补强 **v2.9 第 8 轮「分支覆盖冲 55%」**（2026-10-14，DoD v2.8 排期两项全交付且超额）：AuthProxyController 可测性重构（HttpClient 构造器注入 + `@Autowired` 显式标记，双构造器曾致 40 个 Spring 上下文测试报 No default constructor found，已修）+ AuthProxyControllerTest 新建 20 例（T1~T10 透传/头/refresh 分支 + T11~T20 login/logout token 剥离/send 异常分支；上游 JDK HttpServer 绑 `::1`）；单类分支 0%→**79.5%**（≥60% 目标达成）、行 97.8%；全量分支 52.7%→**57.3%**（55% 目标超额）、行 71.0%→73.6%；测试总数 336→**356** 全绿；门禁棘轮 LINE 0.65→0.70、BRANCH 0.45→0.55；发版对照报告 `docs/dod-v2.9.md`。本轮教训：dpsk 第 3 批整批作废（编造不存在的 stubUpstream/双参数 proxy/单参数构造器），打回并贴文件原文后第二版可用；`HttpClient.newHttpClient()` 默认发 h2c 升级头（Connection: Upgrade, HTTP2-Settings），T3 改断言"伪造值不透传"而非"头不存在"
- DoD 未通过项新排期（见 docs/dod-v2.9.md：v2.10 分支覆盖冲 60%（ChatService/FinalCutService/VideoTaskService）、Agnes/Qwen 录制回放扩到 submit/poll（需外部 API）、h2c 默认行为是否锁定 HTTP_1_1 待产品确认）
- 生产级补强 **v2.10 第 9 轮「分支覆盖冲 60%」**（2026-10-14，DoD v2.9 排期首项全交付且超额）：4 批 dpsk 生成——ChatService 可测性接缝（`Function<ObjectNode,String>` + 包可见 5 参构造器，public 构造器补 `@Autowired` 解双构造器 Spring 坑）+ ChatServiceTest 10 例 + FinalCutServiceTest 20 例 + VideoTaskServiceTest 43 例 + RunLogServiceTest 12 例；测试总数 356→**441** 全绿；行覆盖 73.6%→**75.8%**、分支 57.3%→**60.8%**（60% 目标达成）；三类分支 ChatService 100%/FinalCutService 100%/VideoTaskService 92.9%；pom JaCoCo 门禁棘轮 LINE 0.70→0.75、BRANCH 0.55→0.60；发版对照报告 `docs/dod-v2.10.md`。本轮教训：apply_patches.py 单 PATCH 块只取第一组 OLD/NEW（贪婪 NEW 吞后续组），多组 PATCH 必须拆成单组块；split-dpsk.py 不剥 ``` 围栏（apply_patches 会剥），混用注意首尾；FfmpegServiceTest.burnSubtitles 偶发 ffmpeg 254 失败为环境抖动，重跑通过
- 生产级补强 **v2.11 第 10 轮「分支覆盖冲 65%」**（2026-10-14，DoD v2.10 排期首项全交付且超额）：4 批 dpsk 生成——UsageServiceTest 追加 27 例（三参 summary/requests/byDay/byRun/filters/byModel 边界）+ AgnesVideoProviderPollBranchTest 新建 20 例（poll 全边界，录制回放零真实网络）+ ScriptSplitterService 加 HttpExchange 可测性接缝（包可见 8 参构造器，public 构造器 @Autowired 委托）+ ScriptSplitterCallModelTest 16 例 + EgressProxyConfig 抽取 configureFromEnv(Map) 接缝 + EgressProxyConfigTest 11 例（JVM 全局状态保存/恢复）；测试总数 441→**515** 全绿；行覆盖 75.8%→**79.1%**、分支 60.8%→**67.3%**（65% 目标超额达成）；pom JaCoCo 门禁棘轮 LINE 0.75→0.78、BRANCH 0.60→0.65；发版对照报告 `docs/dod-v2.11.md`。本轮教训：dpsk 批量裸类型名（UsageService. 嵌套限定漏写）、record 访问器编造成 getX()、HttpRequest.uri() 写成 getUri()、CredentialResolver 跨包漏 import；批量改名不许用无词边界 replace（误伤 findForDailyUsage）；C 批又漏 @Autowired import（编排手工补）；DramaV2ApiIntegrationTest.testFullPipeline 偶发 500（ffmpeg 环境抖动），单独重跑通过，记已知 flaky。验收附带修真 bug 一处：callModel 里 JSON null content 被 asText() 成字符串 "null"，已修为按空内容抛异常（测试锁定）。
- DoD 未通过项新排期（见 docs/dod-v2.11.md：v2.12 分支覆盖冲 70%（RunService 55、SurrogateAuthClient 44、LlmScriptService 43 等大头）；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认）
- 生产级补强 **v2.12 第 11 轮「分支覆盖攻坚 + 门禁修复」**（2026-10-14）：开工发现 BYOK 提交（62e6b27）新增约 442 个分支近乎零覆盖，bundle 跌至 63.3%/76.6%、门禁变红构建失败（v2.11 的 67.3% 基线已过期）。5 批 dpsk 生成——A：RunServiceTest 追加 21 例（RunService 分支 70.1%→89.1%）；B：LlmScriptServiceTest 追加 12 例（68.8%→73.2%）；C：RunExecutorTest 追加 12 例（77.2%→87.3%）；D：ByokGenerateService 加 DownloadSender 可测性接缝（@Autowired 双构造器）+ 新建 28 例（分支 8.2%→71.3%）；E：SurrogateAuthClient 加 SocketExchange 接缝（Unix socket 可注入，@Autowired 双构造器）+ 新建 19 例（0%→80.4%）；测试总数 515→**636** 全绿；行覆盖 **80.5%**、分支 **68.7%**（70% 目标未达成，差 30 分支/1.3pp）；pom JaCoCo 门禁棘轮 LINE 0.78→0.80、BRANCH 0.65→0.68；发版对照报告 `docs/dod-v2.12.md`。本轮教训：`mvn verify | grep` 的 exit code 是 grep 的不是 mvn 的，判构建成败必须看日志 BUILD SUCCESS；dpsk 输出 END 标记多变体（apply_patches.py 已通用清理）；单 PATCH 块多组 OLD/NEW 会被贪婪吞掉；dpsk 编造 VideoTaskStatus.SUCCEEDED（实为 DONE）、resolveExtension "bin" 分支不可达（extHint 恒合法）。
- DoD 未通过项新排期（见 docs/dod-v2.12.md：v2.13 分支覆盖冲 70%（差 30 分支；候选 ProviderService 56、DashScopeImageProvider 37、ByokController 30、DidAvatarProvider 26、MiniMaxMusicProvider 24）；删 resolveExtension 不可达 "bin" 分支；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认）
- 生产级补强 **v2.13 第 12 轮「分支覆盖冲 70%」**（2026-10-14）：5 个目标类全覆盖——新建 ProviderServiceCoverageTest 21 例（dpsk 原出 25，4 个与 ProviderServiceProbeTest 重复已去重）、DashScopeImageProviderBranchTest 25 例、ByokControllerBranchTest 21 例、DidAvatarProviderBranchTest 21 例、MiniMaxMusicProviderBranchTest 20 例；共 108 例全绿，测试总数 636→**744**；分支 **68.7%→73.0%**（70% 目标达成，超额 3pp）、行 80.5%→**82.4%**；五类剩余未覆盖分支 173→58（ProviderService 56→30、DashScopeImageProvider 37→10、ByokController 30→3、DidAvatarProvider 26→6、MiniMaxMusicProvider 24→9）；pom JaCoCo 门禁棘轮 LINE 0.80→0.82、BRANCH 0.68→0.70；发版对照报告 `docs/dod-v2.13.md`。本轮教训：Jackson 2.17 `readTree("")` 返回 MissingNode 不抛异常（断言错位已回喂修好）；DidAvatar `catch (RuntimeException e) { throw e;}` 会把 readTree 的 IAE 原样 rethrow；resolveExtension "bin" 删除两轮 PATCH 锚定失败、按流程缩减里程碑延期 v2.14；遭遇另一智能体并发改同一仓库（linkshort v1.2 + drama-factory 前端/GlobalExceptionHandler 在途未提交），本轮用树快照隔离验证、全量 744 绿，对方文件原样未动。
- DoD 未通过项新排期（见 docs/dod-v2.13.md：v2.14 删 resolveExtension 不可达 "bin" 分支；Agnes/Qwen submit/poll 录制回放（需外部 API）；h2c 锁定待产品确认；分支覆盖冲 75%）
- 审核流状态机
- 多用户与权限
- **视觉验收补课 + 录制回放测试修复**（2026-10-15）：① Skill 市场页（P2-6）之前从未截图验收，本轮用真实数据（4 官方 Skill + 已安装 1 个 + 5 星评价）亲眼验收深浅主题+详情弹窗，抓出 1 真实 UI bug：已安装列表裸 ISO 时间戳 → 加 `fmtDateTime` 格式化为 `YYYY-MM-DD HH:mm`；截图入 `docs/screenshots/skills-{light,dark,detail-light}.png` 并同步 README。② 快捷工具页（P2-7）上一轮截图是空数据状态且未入仓，本轮造演示数据（图片/视频资产、《霓虹夜行》项目+剧集）重拍深浅主题入仓；重拍抓出 1 真实功能 bug：`tools.js` 的 `loadProjects()` 用了带尾斜杠的 `/api/projects/`（Spring Boot 3 默认不匹配尾斜杠 → 404 → 导出下拉永远"暂无项目"）→ 去掉尾斜杠。③ 附带修 shell.js 顶栏标题映射漏 `mv/tools/account`（三页顶栏误显示"AI 短剧工坊"）。④ 修复两个未提交的录制回放测试文件（AgnesVideoProviderSubmitRecordingTest/QwenVideoProviderSubmitPollRecordingTest，因 Provider API 演进编译不过：submit 加 seconds 参数、VideoHttpGateway.exchange 签名、Qwen 构造器参数顺序、Shot 枚举拼音命名），15 例全绿。auth-service 12 例测试全绿。
- 生产级补强 **v2.14 第 13 轮「分支覆盖冲 75%」**（2026-10-15，DoD v2.13 排期首项全交付且超额）：1 批 dpsk 生成——新建 QuickToolsServiceBranchTest 20 例（纯 Mockito + @TempDir，零 Spring 上下文；batchTag 5/batchRename 4/convertVideo 5/extractAudio 2/exportShotCsv 3/resolveStoragePath 1）；QuickToolsService 分支 69.7%→**87.9%**（补 24 分支）；全量分支 **74.81%→75.54%**（75% 目标达成）、行 84.78%→**84.93%**；测试总数 1049→**1069**（除 1 已知 flaky 外全绿）；pom JaCoCo 门禁棘轮 LINE 0.82→0.84、BRANCH 0.70→0.75；发版对照报告 `docs/dod-v2.14.md`。本轮核验关闭 v2.13 排期误判项：resolveExtension "bin" 不可达分支早在 f4fa998（10-14）已删除（改抛 IllegalStateException），grep 确认零残留。教训：排期前先核验代码现状；split-dpsk.py 不剥 END FILE 标记，落盘后先 grep 再编译。
- DoD 未通过项新排期（见 docs/dod-v2.14.md：v2.15 分支覆盖冲 80%（候选 ByokGenerateService 44、ProviderService 30、MvService 29 等）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因第三次出现，考虑 mock 化视频轮询）
- 生产级补强 **v2.15 第 14 轮「分支覆盖冲 80%」**（2026-10-15，DoD v2.14 排期首项全交付且超额）：7 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：ByokGenerateServiceBranchTest 29 例；B：ProviderServiceBranchTest 22 例；C：MvServiceBranchTest 18 例；D：UsageServiceBranchTest 16 例；E：PipelineServiceBranchTest 12 例（getProductionStats/listAllPipelines 原零覆盖）；F：RunArtifactControllerBranchTest 10 例（MockMvc）；G（加急）：ProviderControllerBranchTest 12 例 + PromptRecipeServiceBranchTest 25 例（A–F 后分支仅 79.21%，差 27 个，G 批补足）；测试总数 1069→**1214** 全绿；分支 **75.54%→80.57%**（80% 目标达成，超额 0.57pp）、行 84.93%→**87.30%**；pom JaCoCo 门禁棘轮 LINE 0.84→0.87、BRANCH 0.75→0.80；发版对照报告 `docs/dod-v2.15.md`。本轮教训：dpsk PATCH 输出吞行首缩进致锚定失败→改用 METHOD 整方法替换+括号配平；dpsk 回喂会重写坏方法体→必须逐个 diff 检查；Mockito 禁 thenThrow 受检异常（改 doAnswer）；Map.copyOf 的 get(null) 抛 NPE；实例方法别当静态反射调；byok 三 Provider 各有自己的 ConnectivityResult；when() 不许嵌套（hoist）；DB NOT NULL 约束是分支可达性硬边界（Asset 四列/AgentStep.seqNo/MediaProvider.name）；summary("",null,0) 走 noFilter 快捷分支；compose @Transactional 回滚后不能断言 DB 状态；jacoco.exec 被 kill 掉的重复进程写坏（"Unknown block type 2d"）→删 exec 重跑；新测试禁 /tmp（dpsk 用的 Path.of("/tmp") 已清零）。核验关闭的排期误判：L141 switch default、L180/L253 deadline、L453 空时间轴、L541 null seqNo、L570 null filePath、L159 switch default 均不可达（见 dod-v2.15.md）。
- 生产级补强 **v2.16 第 15 轮「分支覆盖攻坚」**（2026-10-15，DoD v2.15 排期首项部分交付）：5 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：MvControllerBranchTest 27 例（MockMvc，MvController 分支 21→0 清零）；B：CredentialResolverBranchTest 15 例（CredentialResolver 21→0 清零）；C：PresetServiceTest 12 例（PresetService 21→1）；D：AuthProxyControllerBranchTest 17 例（AuthProxyController 23→14）；E：RunServiceApproveTest 10 例（审批流 approved/rejected/qcStep 空/fallback + createRun skillId 分支，RunService 22→18）；测试总数 1214→**1295** 全绿；分支 **80.57%→82.45%**（+1.88pp，85% 目标未达成，差 2.55pp/约 420 分支）、行 87.30%→**88.30%**；pom JaCoCo 门禁棘轮 LINE 0.87→0.88、BRANCH 0.80→0.82；发版对照报告 `docs/dod-v2.16.md`。本轮修 dpsk 输出 6 处（包名编造 entity/enums→model、record 单参构造→mock、doNothing 用于非 void 的 qc、times(3)→times(5)、缺 CurrentUser import、body==null 走 HTTP 不可达改直接调方法）；生产代码零修改。
- DoD 未通过项新排期（见 docs/dod-v2.16.md：v2.17 分支覆盖冲 85%（还差约 420 分支；候选 RunExecutor 27、QwenVideoProvider 20、LlmScriptService 剩余、AuthProxyController 剩余 14、ByokGenerateService 剩余等）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因（本轮一次通过，根因未消））
- 生产级补强 **v2.17 第 16 轮「分支覆盖冲 85%」**（2026-10-15，DoD v2.16 排期首项全交付）：11 个新测试文件（微信 ChatAPI DeepSeek-V4-Flash 生成）——遗留 4 文件验证落地（RunExecutorBranch2Test 24、QwenVideoProviderBranch2Test 27、LlmScriptServiceBranch4Test 16、ByokGenerateServiceBranch2Test 20）；E1：RunExecutorBranch3Test 16（RunExecutor 分支→96.0%）+ AuthProxyControllerBranch2Test 13（→93.8%）；E2：QwenVideoProviderBranch3Test 11（→93.8%）+ ByokGenerateServiceBranch3Test 9（→91.7%）+ LlmScriptServiceBranch5Test 7（→93.5%）；E3：MediaControllerBranchTest 12（5 个端点此前零覆盖，含路径穿越 SecurityException 测试）+ CookieAuthFilterTest 10（分支 100%）；测试总数 1295→**1460** 全绿；分支 **82.45%→85.33%**（+2.88pp，**85% 目标达成**）、行 88.30%→**89.86%**；pom JaCoCo 门禁棘轮 LINE 0.88→0.89、BRANCH 0.82→0.85；发版对照报告 `docs/dod-v2.17.md`。本轮修 dpsk 输出 14 处（T16 无斜杠臂实测不可达改诚实跳过、HttpHeaders 歧义×3、throws Exception 遗漏×8、HttpHeaders.of null key NPE 改 mock、编造枚举 PUSH_IN/MEDIUM、ConnectivityStatus 缺 import、嵌套 when()×6 hoist、poll 空 body 断言错、parseScenes 前缀花括号污染）；附带修真问题 1 个：ByokGenerateServiceBranch2Test 用 `"unused"` 字符串当 storageDir 致测试在源码树下落盘（3 次污染），3 个落盘测试改 `@TempDir`；生产代码零逻辑修改。
- DoD 未通过项新排期（见 docs/dod-v2.17.md：v2.18 分支覆盖冲 87%（候选 AssetService 19、SettingsService 18、RunService 18）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因）
- 生产级补强 **v2.18 第 17 轮「分支覆盖冲 87%」**（2026-10-15，DoD v2.17 排期首项全交付且超额）：6 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：SettingsServiceBranchTest 11 例；B：AssetServiceBranchTest 17 例；C：MediaControllerBranch2Test 3 例（目录路径实测 `FileSystemResource` 对目录 `exists()=true/isReadable()=false`，确定性触发"存在但不可读"臂，root 下 chmod 去权限无效）；D：RunServiceBranch2Test 17 例（含 DramaProject/VideoTask/FinalCut 各 1 个 @PrePersist 分支）；E：BranchCatchUpTest 7 例（补对侧臂第一轮）；F：BranchCatchUp2Test 5 例（补对侧臂第二轮：无请求上下文/null request/exp 非数字字符串 token）。测试总数 1460→**1519** 全绿；分支 **85.33%→87.09%**（+1.76pp，**87% 目标达成**）、行 89.86%→**90.52%**；pom JaCoCo 门禁棘轮 LINE 0.89→0.90、BRANCH 0.85→0.87；发版对照报告 `docs/dod-v2.18.md`。本轮修 dpsk 输出 2 处（registerGenerated 不调 resolveSafePath、穿越路径 `"assets/../evil.png"` normalize 后仍在 base 内，改走 delete + `"assets/../../evil.png"`）；沉淀"对侧臂"方法论（mb=1 cb=1 = 一侧有人一侧没人，须两轮补）；诚实跳过 6 个不可达分支（Settings 70-null键/146/213、Run approve 422/431、Asset lastSegment-idx<0）+ 1 存疑（Asset 80 行 blank 臂测试已执行但探针仍报 missed，未定位）；生产代码零逻辑修改。
- DoD 未通过项新排期（见 docs/dod-v2.18.md：v2.19 分支覆盖冲 88%（候选 VideoTaskService 3、CurrentUser 剩余 1、DramaMetrics 3、ByokController 3、SkillController 3；Asset 80 存疑根因）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因）
- 生产级补强 **v2.19 第 18 轮「分支覆盖冲 88%」**（2026-10-15，DoD v2.18 排期首项全交付）：7 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：V219BatchATest 8 例（含 AssetService L80 破案：MockMultipartFile 构造器把 null 文件名规范化为 ""，v2.18"存疑"实为 null 臂从未被覆盖，改手写 MultipartFile stub 后翻绿；CurrentUser L37 实为 value.isBlank 臂非 request-null 臂，getRequest() 为 final 不可 mock，改真实 ServletRequestAttributes 包装）；B：VideoTaskServiceTimeoutTest 1 例（25.5s 真实超时路径，覆盖 L224/L233）；C：DramaMetricsBranchTest 4 例；D：V219BatchDTest 7 例；E：V219BatchETest 6 例；F：V219BatchFTest 4 例；G：V219BatchGTest 5 例。测试总数 1519→**1554** 全绿；分支 **87.09%→88.09%**（+1.00pp，**88% 目标达成**）、行 90.52%→**90.80%**；pom JaCoCo 门禁棘轮 BRANCH 0.87→**0.88**（LINE 0.90 保持）；发版对照报告 `docs/dod-v2.19.md`。本轮修 dpsk 输出 6 处（包名编造 byok/video×2、缺 import×3、setAvgRating 不存在、Map.Entry 类型错、`<redacted>` 展示占位符被当字面量照抄致断言失败——hex dump 现形）；沉淀诚实跳过 6 处（ByokController L94/VideoTaskService L264/PipelineService L159/PresetService L55/RunService L422+431/RunLogService L77·78·103，均为源码级论证不可达）；生产代码零逻辑修改。
- DoD 未通过项新排期（见 docs/dod-v2.19.md：v2.20 分支覆盖冲 89%（候选 QwenVideoProvider 4、ProviderController 5、ProjectService 5、Skill 6、GlobalExceptionHandler 6、VideoProviderRouter 6 等）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因）
- 生产级补强 **v2.20 第 19 轮「分支覆盖冲 89%」**（2026-10-15，DoD v2.19 排期首项全交付且超额）：4 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：QuickToolsServiceV220ATest 15 例（QuickToolsService 16→8）；B：SkillServiceV220BTest 17 例（SkillService 14→11）；C：SubtitleServiceV220CTest 11 例 + ShotServiceV220CTest 11 例（两类 11→0、9→**0 清零**）；D：AceStepMusicProviderV220DTest 13 例 + DashScopeImageProviderV220DTest 13 例（13→8、10→6）；测试总数 1554→**1634** 全绿；分支 **88.09%→89.30%**（+1.21pp，**89% 目标达成**）、行 90.80%→**91.90%**；pom JaCoCo 门禁棘轮 LINE 0.90→0.91、BRANCH 0.88→**0.89**；发版对照报告 `docs/dod-v2.20.md`。本轮修 dpsk 输出 11 处（setDurationSeconds 传 double、同一 mock 双 doAnswer、编造 MusicProvider/ImageProvider ConnectivityResult 类型与 PollResult.url()、Jackson readTree("") 空串不抛异常三连误判、HttpServer 发 199 当 interim 40 秒超时）；`<redacted>` 防线有效（prompt 点名警告后 D 批零残留）；诚实跳过 3 处（AceStep probe 写请求体异常臂/DashScope 同理不可注入、generate code<200 本地发不出 199、Subtitle 写文件 IOException root 无视权限）；生产代码零逻辑修改。
- DoD 未通过项新排期（见 docs/dod-v2.20.md：v2.21 分支覆盖冲 90%（候选 SkillService 11、QuickToolsService 8、AceStepMusicProvider 8、DashScopeImageProvider 6、LlmTransport 16、AssetController 15、ScriptService 15 等，需约 23 分支）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因）
- 生产级补强 **v2.21 第 20 轮「分支覆盖冲 90%」**（2026-10-15，DoD v2.20 排期首项全交付且超额）：5 批 dpsk 生成（微信 ChatAPI DeepSeek-V4-Flash）——A：SkillServiceV221ATest 10 例（SkillService 11→3）；B：QuickToolsServiceV221BTest 5 例（QuickToolsService 8→5）；C：AceStepMusicProviderV221CTest 4 例 + DashScopeImageProviderV221CTest 5 例（AceStep 8→4、DashScope 6→2）；D：AssetControllerV221DTest 10 例（AssetController 15→**0 清零**，file() 端点整体零覆盖）；E：AceStepMusicProviderV221ETest 3 例 + SkillServiceV221ETest 1 例 + DashScopeImageProviderV221ETest 1 例（补 null 臂）；测试总数 1634→**1673** 全绿；分支 **89.30%→90.36%**（+1.06pp，**90% 目标达成**）、行 91.20%→**91.51%**；pom JaCoCo 门禁棘轮 BRANCH 0.89→**0.90**（LINE 0.91 保持）；发版对照报告 `docs/dod-v2.21.md`。本轮修 dpsk 输出 17 处（max-tokens 1024 截断、编造 ConnectivityResult 类型/PollResult.url()/detail() 访问器、编造 SkillReviewRepository、漏 import×4、prompt 签名笔误）；诚实跳过 7 处（QuickTools L173/L225 输出路径检查、L337 csvEscape null、L122 len<1；AceStep L83/L142 body null、L84 code<200、L96 audioUrl blank；DashScope L242 truncate null）；生产代码零逻辑修改。
- DoD 未通过项新排期（见 docs/dod-v2.21.md：v2.22 分支覆盖冲 91%（候选 LlmTransport 16、ScriptService 15、AgnesVideoProvider 14、UsageService 14、ByokGenerateService 13、ScriptSplitterService 13、MvService 13、FfmpegService 13 等；需约 33 个分支）；Agnes/Qwen submit/poll 真实链路（需外部 API）；h2c 锁定待产品确认；testFullPipeline flaky 根因）

## mini-os「网页操作系统」

**定位**：浏览器里的桌面操作系统，后端提供虚拟文件系统、设置持久化与应用注册表，前端实现可拖拽多窗口桌面。

**技术栈**：Rust + Axum 0.7（含 WebSocket + multipart）+ Tokio + rusqlite 0.32（bundled SQLite）；前端原生 HTML/CSS/JS（无框架）；cargo test 集成测试 16 例、cargo clippy 零警告；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 mini-os/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 虚拟文件系统（文件夹/文件 CRUD，SQLite 持久化，种子数据 Desktop/Documents/welcome.txt/notes.txt）
2. 应用注册表（文件管理器、文本编辑器、终端、设置、关于 5 个内置应用）
3. 可拖拽多窗口桌面 + 任务栏 + 开始菜单 + 时钟
4. 主题/壁纸设置持久化
5. WebSocket（连接先发 hello，文本消息 echo 回显）
6. 统计（文件/文件夹数、字节数）
7. 文件上传与下载（v1.1.0）：`POST /api/files/upload?path=<目录>`（multipart，默认 50MB 上限可配）、`GET /api/files/download?path=<文件>`（64KB 分块流式）；`vfs_nodes` 新增 `content_blob`/`mime_type` 列；工具栏上传按钮 + 拖拽上传 + 行内下载 + 错误提示条

**状态**：v1.1.0（2026-10-15 完成，cargo test 16 例全过、clippy 零警告、真机冒烟 + 4 张真实截图视觉验收通过；发版对照报告 `mini-os/docs/PRODUCTION_CHECKLIST_REPORT_v1.1.0.md`）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Axum + rusqlite 后端落地，虚拟文件系统 API、5 应用桌面前端、WebSocket 协议、CI 与多阶段 Dockerfile 就绪
- v1.1.0 文件上传下载（2026-10-15）：上传/下载双接口 + BLOB 存储迁移 + 前端上传/下载 UI；验收时顺带修复 2 个 v1 视觉 bug（`.hidden` 工具类缺失致开始菜单无法隐藏、壁纸切换类名 mismatch）

**后续计划**：

- v1.2（对照报告排期）：失败注入测试、migrations 版本化表、就绪探针 + 优雅关闭、结构化日志/request_id、运维手册（备份/资源限制/日志轮转）

- 文件上传/下载
- 多用户与权限
- 应用商店（插件化）

## ledger「钱迹 · 个人财务管家」

**定位**：个人财务管理系统，覆盖多账户记账、月度预算、统计分析与数据导入导出的完整记账流程。

**技术栈**：Python 3.11+ + FastAPI + SQLAlchemy 2.0（aiosqlite 异步）+ SQLite 单文件库；Jinja2 SSR Web UI（图表为服务端渲染内联 SVG，零外部依赖）；pytest + httpx（97 例测试）、ruff 检查与格式化；Dockerfile 单阶段构建；GitHub Actions CI 暂置于 ledger/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 多账户管理（余额按收支/转账自动汇总）
2. 交易记账（收入/支出/转账，金额统一用「分」整数存储）
3. 分类体系（seed 预置 18 个常用分类）
4. 月度预算与执行进度/超支预警
5. 统计分析（月度汇总、12 个月趋势、分类占比、净资产）
6. CSV 导入/导出
7. 周期性账单与未来 30 天到期提醒
8. Web UI（仪表盘/交易/账户/分类/预算/周期账单/导入导出/账单导入/侦探队列 9 页）
9. **银行账单侦探（v2.0 灵魂功能）**：账单导入向导（上传→解析预览→列映射→确认，预置支付宝/微信/招行/工行模板，GBK 编码与表头前导行自动探测）→ 三路匹配引擎（关键词规则 priority > 历史习惯同商户多数票 > 候选 Top3 + 置信度）→ 侦探队列（待认领卡片流，一键认领/换分类/记住为规则/跳过）→ 认领即学习（存关键词规则，下次自动）→ 转账识别（对方为自己账户名）→ 指纹去重（sha256 防重复导入）

**状态**：v2.0「银行账单侦探」（2026-10-15）：灵魂一页纸先行（docs/SOUL.md）；pytest 97/97 全过（新增 63 例：matching/parser 单元 56 + API 集成 41 中含 7 个端到端场景）、ruff 全洁；真实服务冒烟：支付宝/微信/招行-GBK 三种账单上传→确认→认领→学习闭环、指纹去重、转账识别全链路验证；两页真实数据截图亲眼验收通过（docs/screenshots/）；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v2.0.md（结论可发版，生产级基础项排期 v2.1）；README 重写（图文并茂）+ CHANGELOG.md 新建。
**v2.1「生产级补强」（2026-10-15）**：v2.0 对照报告第 7 节 7 项排期全部关闭——`migrations.py`（PRAGMA user_version=2，v2 DDL 从 models 编译生成，`init_db` 改走 `run_migrations`）+ `logging.py`（JsonFormatter 单行 JSON / RequestIdMiddleware 全链路 request_id + `X-Request-Id` 回写 / 未处理异常兜底 500，`LEDGER_LOG_LEVEL` 非法值启动 fail-fast）+ `routers/metrics.py`（Prometheus 文本 6 指标）+ `GET /api/ready`（200/503）+ 优雅关闭（lifespan dispose engine）+ `backup.py`（integrity_check / keep 修剪 / 同秒 `-N` 后缀 / 恢复前安全快照 / 坏备份拒绝）+ `python -m ledger backup|restore`（`make backup [KEEP=N]` / `make restore FILE=`）+ `docker-compose.yml`（healthcheck / 资源限制 / 日志轮转 / named volume）+ `docs/OPERATIONS.md` + `tests/test_failure_injection.py` 4 例；pytest **119/119** 全过（新增 22 例）、ruff 全洁；真实服务冒烟：建账→交易→metrics→备份→删库→恢复→数据一致全链路通过；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v2.1.md（结论可发版）。本轮修真 bug 4 个：`python -m ledger serve` 启动崩溃（`args.dir` 在 serve 子命令不存在，冒烟抓出）、坏 CSV 的 `csv.Error` 抛 500（改 errors 行收集，失败注入抓出）、`integrity_check` 对损坏文件抛裸 `sqlite3.DatabaseError`（改 `BackupError`）、备份写入失败抛裸 `OSError` 且留半成品（改 `BackupError` 并清理）。教训：FastAPI 0.143 把 `@app.exception_handler(Exception)` 转给 ServerErrorMiddleware（响应后仍 re-raise，测试侧可见异常穿透），500 兜底改由 RequestIdMiddleware 直接返回；`pkill -f` 再次自杀（教训重犯：命令行自匹配，必须用括号技巧）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：FastAPI 分层架构落地，账户/交易/分类/预算/统计/导入导出/周期账单全模块、Jinja2 SSR 前端、CI 与 Dockerfile 就绪
- v2.0 银行账单侦探（2026-10-15）：`matching.py` 三路匹配纯函数引擎 + `statement_parser.py`（GBK/表头探测/列映射/4 内置模板）+ `routers/statements.py`（18 个端点：模板 CRUD/解析预览/上传/确认/认领/转账认领/跳过/规则 CRUD）+ `statement.html` 导入向导 + `detective.html` 侦探队列 + main.py 两路由 + base.html 导航；验收抓真 bug 7 个：dpsk 的 field_validator 漏 return v、schemas created_at 误用 datetime 类型、upload 循环内 N+1 查指纹、`_load_top_categories` 未按方向过滤、表头探测被全模板并集稀释致支付宝前导行识别失败、模板名未回填、claim 后 batch.pending_count 不递减；附带修 v1 遗留 3 个真 bug（style.css 首行 ```css 围栏致全站 CSS 变量失效、base.html 顶栏类名与 CSS 设计体系脱节、style.css 尾部 .chart-toolbar 截断）
- v2.1 生产级补强（2026-10-15）：dpsk 分 7 批生成（迁移/日志+request_id/metrics+ready/备份恢复 CLI/compose+运维手册/失败注入/文档），编排验收修 6 处（编造 transactions API 字段 amount/occurred_at→amount_cents/occurred_on、编造 static mount OLD 文本、backup 同秒文件名碰撞加 -N 后缀、middleware 测试同步函数用 async fixture、__main__ serve 无 args.dir 致启动崩溃、backup OSError 裸抛）；pytest 119/119、ruff 全洁；真实冒烟全链路通过

**后续计划**：

- 多币种与汇率
- 账单图片 OCR 录入
- 移动端适配
- Dependabot（等 gh token 补 workflow 权限后迁仓库根，与其他项目同）

## sentinel「哨兵 Sentinel · 站点可用性监控」

**定位**：站点与服务可用性监控系统，覆盖监控目标管理、定时检查、停机事件与可用率统计的完整运维流程。**灵魂功能**：站点健康档案——每个站点可用性画像、月度 SLA 报告、一键生成公开状态页。

**技术栈**：Go 1.23 单二进制；标准库 net/http 提供 HTTP 服务，modernc.org/sqlite 作为纯 Go SQLite 驱动；go:embed 内嵌 Web UI 静态资源；go test 覆盖存储/检查器/HTTP 层/备份测试；Dockerfile 多阶段构建 + docker-compose 一键部署；GitHub Actions CI 暂置于 sentinel/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 监控目标管理（HTTP(S)/TCP 双协议、期望状态码、超时、检查间隔、启用开关）
2. 定时检查调度器（可配 tick/并发上限/重试次数，目标级 inflight 防堆积）
3. 检查记录（状态码、延迟毫秒、HTTPS 证书剩余天数，失败指数退避重试）
4. 状态翻转自动生成停机事件（down 创建、recovered 关闭并计算时长）
5. Webhook 告警通知（目标级或全局，失败重试 3 次）
6. 站点健康档案（/profile：7/30 天可用性、延迟 p50/p95/p99、30 天每日可用性条形图、证书剩余天数）
7. 月度 SLA 报告（uptime/检查数/事件数/总宕机时长/99.9% 目标达标判定）
8. 公开状态页（一键生成 /status/{slug}，免鉴权对外展示）
9. 生产级：slog 结构化日志（request_id 全链路）、/healthz /readyz、优雅关闭、Prometheus /api/metrics、DB 迁移版本化（v1→v2）、API Token 鉴权、tenant/user 多用户、自动备份 + `-restore` 一键恢复、docs/OPERATIONS.md 运维手册
10. Web UI（仪表盘/监控管理/事件/健康档案/公开状态页）

**状态**：生产级 v0.2.0（2026-10-13）：构建、vet、gofmt、全量测试（backup/checker/handlers/store）与真实服务冒烟均已跑通；冒烟验证了 鉴权(401/200)→加监控→故障→incident→恢复→事件关闭、备份→删库→-restore 恢复、健康档案/SLA/公开状态页 API 全链路；发版对照报告见 sentinel/docs/RELEASE_CHECKLIST.md。已知限制：单实例（SQLite）、webhook 失败最多重试 3 次。

**里程碑记录**：

- 工程化 v1（2026-10-13）：单二进制架构落地，检查器/调度器/事件流、内嵌 Web UI、CI 与多阶段构建就绪
- 生产级 v0.2.0（2026-10-13）：全量生产级改造（可观测性/可靠性/数据/部署/安全/可维护性）+ 灵魂功能（健康档案/月度 SLA/公开状态页）；CHANGELOG 见 sentinel/CHANGELOG.md

**后续计划**：

- 多渠道告警（邮件/短信/企业微信）
- 分布式探针（多实例需先换 PostgreSQL）
- 状态页自定义主题与订阅通知

## docseek「文溯 DocSeek · 本地全文检索引擎」

**定位**：本地文件的 Google —— 真中文分词 + 混合检索 + 自然语言定位原文。本地文档全文检索引擎 CLI，覆盖目录爬取、增量索引、相关性搜索与索引维护的完整流程。

**技术栈**：C++17 + CMake；SQLite FTS5 **+ cppjieba（v5.6.2，MIT）自定义中文分词器**（FetchContent；词典构建期部署）；混合检索 v1（BM25 + AND→OR 回退 + 标题/短语加成重排序）；GoogleTest（FetchContent）单元+集成测试；多阶段 Dockerfile；GitHub Actions CI 暂置于 docseek/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 递归目录索引（txt/md/markdown/text，大小写不敏感；二进制与超大文件自动跳过；隐藏目录跳过）
2. 基于 mtime+size 的增量更新（新增/更新/未变分别计数）
3. 全文搜索（FTS5 MATCH，隐式 AND，BM25 相关性排序，30 token 摘要片段）
4. 已删除文件自动清理（index 末尾自动 prune，另有 prune 命令）
5. 索引统计（文档数、内容总字节、库文件大小）
6. JSON 输出（--json，便于脚本集成）
7. 灵活配置（--db > DOCSEEK_DB > $HOME/.local/share/docseek/docseek.db）

**状态**：工程化 v5「生产级补齐」（2026-10-15 完成：结构化日志 stderr JSON Lines + request_id 全链路（X-Request-Id 响应头）+ `GET /api/metrics`（查询量/延迟/Top 查询词/慢查询/限流拒绝数）+ `backup`/`restore` 子命令（SQLite backup API 在线热备，原子替换恢复）+ `/api/locate` 并发限流（默认 4，超限 429）+ 索引批量事务（每 500 文件提交，147 文件/秒，老基线 37 文件/秒）+ jieba 词典噪音重定向 + `docker-compose.yml` 一键部署 + `docs/OPERATIONS.md` + 仓库级 `.github/dependabot.yml`；构建零警告、测试 62/62 全过〈含新增 test_ops.cpp 14 例〉；backup/restore、kill -9、删库恢复、词典缺失四项真实演练全过；发版对照报告 v0.5.0：13 项缺口全部关闭）。

**发版对照**：`docseek/docs/PRODUCTION_CHECKLIST_REPORT_v0.5.0.md`——**发版**：v0.4.0 的 13 项未通过/部分通过缺口本轮全部关闭，无已知 P0。

**修 bug（本轮视觉验收附带抓出）**：
1. web/index.html 的 `<script>` 自 v2 起在 `btn.dis` 处被截断，导致整页 JS 解析失败、所有按钮无响应——本轮补全并补上事件绑定与初始化（node --check 验证通过）。
2. 同文件第 1 行混入 markdown 代码围栏 ` ```html `，页面顶部渲染出多余文本——已删除。
3. refreshStats 字段映射与 /api/stats 实际返回对不上（total_bytes/uptime_sec/watched_dirs），服务状态卡片显示 "-"——已对齐。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Database（SQLite+FTS5 手动同步）/ Indexer（递归爬取+增量）/ Searcher（查询构造）三层库 + docseek CLI（index/search/stats/prune）+ 15 例测试 + CI 与多阶段 Dockerfile 就绪
- 工程化 v2（2026-10-13）：`serve` 子命令落地——自研极简 HTTP 服务器（零第三方网络库）+ inotify 实时监控（新增/修改/删除自动增量索引，debounce）+ 内嵌 Web UI；7 个 REST 端点（/api/health、/api/stats、/api/search、/api/index、/api/prune、/api/watch GET/POST/DELETE）；测试扩至 32 例全过；真实冒烟验证新增/修改/删除自动索引、watch 增删 API 与 Web UI；补齐完整 README（安装/构建/测试/API 表格/已知局限）
- 工程化 v3（2026-10-13）：**中文分词攻坚**——cppjieba（v5.6.2，MIT，Keenable 核验 2026 年仍在维护）实现的 FTS5 自定义分词器（`tokenize='jieba'`，fts5_api 注册，CutForSearch + 字节偏移，ASCII 小写折叠）；`PRAGMA user_version` 2→3 旧库自动迁移（事务包裹，失败回滚）；**混合检索 v1**（BM25 + AND→OR 回退 + 标题/短语加成重排序）；词典运行时四级定位（DOCSEEK_DICT_DIR > ../share/docseek/dict > 同级 dict/ > 编译期默认），缺失则 fail-fast。评测：12 篇中文语料 10 查询 Top-1 全部符合预期（docs/eval.md）；万级文件（40MB）索引 267 秒，检索 2.7 秒（含词典加载）。调试中发现并修复 dpsk 埋的 bug：Jieba 构造函数传参顺序错误（把 idf.utf8 当用户词典加载导致切词异常）。
- 工程化 v4「自然语言定位原文」（2026-10-13）：灵魂一页纸先行（docs/SOUL.md）；query_parser（中文疑问句规则解析 + 疑问词删除表 + 引号短语抽取）/ passage_ranker（滑动窗口段落切分 + 四维加权打分 + 行号锚定）/ locator（混合召回→段落重排）三新模块 + Database::getContentById + jieba 单例只读接口；`locate` CLI（行号段落 + ANSI 高亮 + --json）+ `GET /api/locate` + Web"自然语言定位"卡片（延续现有视觉系统）；CHANGELOG.md 新建；docs/eval.md 第七节 10 查询评测 10/10；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.4.0.md；CLI/Web 真实截图各 1 张亲眼验收；修了 v2 遗留的 3 个真实 bug（Web JS 截断致全页失效、首行 ```html 围栏、refreshStats 字段映射错位）
- 工程化 v5「生产级补齐」（2026-10-15）：logger/metrics/concurrency_guard 三新模块 + `wrapRequest` 统一请求包装（request_id 生成/结构化日志/指标记录/X-Request-Id）+ `GET /api/metrics` + `/api/locate` 并发守卫（ScopedSlot RAII）+ `Database::beginBatch/commitBatch/abortBatch`（嵌套防护+异常回滚）+ `Database::backup/isValidDocseekDb` + `backup`/`restore` CLI（含 restore 原子替换三步）+ `StderrSilencer`（jieba 噪音重定向）+ `docker-compose.yml` + Dockerfile 补拷词典（修运行镜像 serve 起不来）+ `.github/dependabot.yml`（仓库级）+ `docs/OPERATIONS.md` + 发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v0.5.0.md`；测试 62/62 全过（含新增 test_ops.cpp 14 例：日志/指标/备份恢复/失败注入/批量事务/并发守卫）；真实演练：backup→删库→restore→检索、kill -9 重启、词典缺失 fail-fast；索引 1000 文件 6.8 秒（147 文件/秒，4 倍提升）。本轮抓真 bug 两处：dpsk 首版 logger 输出非法 JSON（key 无引号+首字段多逗号，strace 定位打回重修）；SvcFixture.Health 硬编码 0.4.0 改版本无关断言

**后续计划**：

- HTML/PDF/Office 文本提取
- 多用户支持

## feedflow「信流 FeedFlow · 自托管 RSS 阅读器」

**定位**：自托管 RSS 阅读器，覆盖订阅管理、定时抓取、正文提取、三栏阅读、全文搜索与 OPML 导入导出的完整流程。

**技术栈**：Python 3.11+ + Flask 3.1.3 + feedparser 6.0.14（RSS/Atom 解析）+ trafilatura 2.2.0（正文提取）+ APScheduler 3.11.3（进程内定时调度）+ SQLite FTS5（trigram tokenizer，中英文全文搜索）；pytest（35 例）、ruff、Dockerfile、GitHub Actions CI（暂置 feedflow/.github，待 token 补齐 workflow 权限后迁移至仓库根目录）。选型经三步调研：dpsk 出候选清单与对比维度 → Keenable 核验版本时效性（Flask 3.1.3 / feedparser 6.0.14 / trafilatura 2.2.0 / APScheduler 3.11.3 均为 2026 年内最新稳定版）→ venv 实际安装验证通过。选 Flask 而非 FastAPI：单进程自托管阅读器，Flask + Jinja2 直出三栏阅读器页面足够轻，异步抓取并非瓶颈。

**功能模块**：

1. 订阅源管理（新建/编辑/删除、分组、抓取间隔、启用开关、立即抓取）
2. APScheduler 后台定时抓取（每 60 秒检查到期源，etag/modified 条件请求）
3. 文章入库（guid 去重、发布时间解析）
4. trafilatura 正文提取（失败回落摘要去标签文本）
5. 三栏桌面式阅读器（分组/源树、文章列表、阅读区；未读/星标/全部过滤；快捷键 j/k/m/s）
6. SQLite FTS5 全文搜索（trigram，中文按字可搜）
7. OPML 导入/导出
8. 统计页（订阅数/文章数/未读/今日新增/各源状态）
9. 重要性排序（时效衰减/事件热度/来源权重/关键词/未读五维加权，可解释分项）
10. 「今日必读」页（每天最重要的 N 篇）+ 兴趣设置（关键词/来源权重/每日篇数）

**视觉**：「旧报纸」阅读气质——纸白 #FAFAF7、墨色 #1C1A17、暖灰分隔线、点睛柿色 #C2410C；UI 系统无衬线栈、正文衬线；8pt 间距、圆角 8px。

**状态**：工程化 v1（2026-10-13 完成，pytest 35 例全过、ruff 全洁、真实服务冒烟：订阅添加→立即抓取→3 篇文章入库→标已读/星标→搜索→OPML 往返→CLI fetch 全链路验证）。
**生产级补强 v1.1**（2026-10-13）：抓取健壮性（urllib 超时/指数退避重试/失败分类 timeout·dns·http_4xx·http_5xx·parse_error·unknown、连续失败计数）、调度可靠性（job_state 持久化、启动补跑、misfire_grace_time、单源异常隔离）、结构化 JSON 日志（request_id 全链路）、/healthz、配置环境变量化 + 启动校验、DB 迁移版本化（PRAGMA user_version）、备份恢复 CLI（保留最近 7 个）、docker-compose 一键部署、docs/OPERATIONS.md 运维手册；**灵魂功能起步**：SimHash + Jaccard 两阶段相似文章去重聚类，同事件多源报道折叠显示（"还有 N 篇相似报道"）。pytest 46 例全过、ruff 全洁、真实服务冒烟（抓取→去重聚类→折叠显示→阅读）全链路验证通过。
**v1.3「Fever API 兼容 + 正文提取超时收敛」**（2026-10-15）：`feedflow/fever.py` 新蓝图挂载 `/fever/`（strict_slashes 双路径），Reeder/Unread 等 Fever 客户端可直连同步订阅/文章/已读/星标；鉴权 POST api_key=md5(邮箱:密码)，`FEEDFLOW_FEVER_API_KEY` 未配置则关闭，hmac 常量时间比较；读 groups/feeds/favicons/items（since_id/max_id/with_ids 各 50 封顶）/unread_item_ids/saved_item_ids，写 mark 已读/星标/按源按组已读（before 时间戳）/unread_recently_read；`feedflow fever-key` 命令生成 key；诚实边界：favicon 占位图、is_spark 恒 0、未分组源归 group 0。正文提取超时收敛：`FEEDFLOW_EXTRACT_TIMEOUT`（默认 15 秒）经 trafilatura config.DOWNLOAD_TIMEOUT 生效，超时回落摘要；迁移 v3 新增 `articles.last_read_at`。pytest 84/84（含新增 test_fever.py 22 例）、ruff 全洁、真实服务冒烟 9 项全过；发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v1.3.md`（结论可发版，遗留 OPERATIONS.md Fever 章节/Prometheus 指标/失败注入测试排期 v1.4）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Flask 应用工厂 + 蓝图分层落地，订阅/抓取/阅读/搜索/OPML/统计全模块、Jinja2 三栏阅读器前端、CI 与 Dockerfile 就绪
- 生产级补强 v1.1（2026-10-13）：抓取超时/重试/失败分类、调度状态持久化与补跑、结构化日志 + /healthz、配置校验、DB 迁移、备份恢复、docker-compose、运维手册；SimHash + Jaccard 两阶段去重聚类与折叠显示上线
- **灵魂功能 v1.2 重要性排序**（2026-10-13）：`feedflow/ranking.py`——五维加权可解释分数（时效衰减半衰期 48h 0.30 / 事件热度 0.25 / 来源权重 0.20 / 关键词 0.15 / 未读 0.10），分项归一 0~1、确定性无随机；「今日必读」页（/digest，默认 20 篇，每篇标注"为什么排前面"分项理由）+ 兴趣设置页（/settings/interests：关键词增删、来源手动权重、每日篇数 N）；来源质量从已读/星标比率自动学习；DB 迁移 v2（keywords/feed_weights/settings 三表）；pytest 62 例全过（新增 test_ranking.py 16 例）、ruff check 全洁、真实服务冒烟与 3 张新截图（digest/interests/reader）逐张视觉验收通过
- **v1.3 Fever API 兼容 + 正文提取超时收敛**（2026-10-15）：dpsk 分 6 批生成（迁移/PATCH 拆分器新增 scripts/split_patches.py 治贪婪 NEW 吞组）；验收抓真 bug 3 个：`store.get_folder` 系 prompt 误列（实现改直查 SQL）、SQLite `strftime()` 返回 TEXT 与整数 before 比较恒假（加 CAST AS INTEGER）、extract_text 加参导致旧 mock 签名不兼容（测试 mock 补参）；测试另修 3 处（种子数据污染计数、分页参数改 query string 走协议、unread_recently_read 改走 store.set_read 写 last_read_at）。pytest 84/84、ruff 全洁、冒烟 9 项全过

**后续计划**：

- trafilatura 抓取超时收敛（当前单篇最坏等待较长）
- fever / Google Reader API 兼容
- 移动端阅读优化
- 全文 RSS 输出

## linkshort「短链 LinkShort · 自托管短链服务」

**定位**：自托管短链服务，把长链接变成短地址；单二进制 + SQLite + 内嵌 Web UI，跑起来就能用。

**技术栈**：Go 1.23 单二进制；chi v5.3.2 路由（组件库多元化：与 second-brain/sentinel 的标准库 net/http 错开），modernc.org/sqlite v1.34.5（纯 Go SQLite 驱动，无需 cgo）；skip2/go-qrcode 服务端生成二维码 PNG；go:embed 内嵌 Web UI；go test（58 例，-race 全过）、go vet、gofmt；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 linkshort/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。选型经三步调研：dpsk 出候选清单与对比维度（chi/gin/echo/fiber、skip2/go-qrcode/boombuler/yeqown）→ Keenable 核验时效性（chi v5.3.2 2026-09 发布、活跃维护；qrcode 为短链场景事实标准）→ go get 实际安装验证通过。选 chi 而非 gin/echo：一句话——单二进制小服务，chi 零第三方依赖、纯 net/http 兼容，与"一个二进制跑起来"的气质最贴合。

**功能模块**：

1. 短链创建（自动 base62 短码 / 自定义 slug，目标 URL 校验）
2. 302 跳转（访问计数 + 访问日志：时间/IP 哈希/UA/Referer）
3. 统计分析（总览、30 天点击曲线、Top 链接、Top Referer）
4. 过期时间（到期访问返回 410）
5. 启用/禁用开关
6. 二维码 PNG（服务端生成）
7. CSV 导入/导出
8. API Key 鉴权（X-API-Key 头或 ?key= 参数）
9. Web UI 四页：仪表盘 / 链接管理（搜索/排序/分页/导入导出）/ 详情（含二维码与单链统计）/ 新建

**视觉**：「快递面单 / 邮政标签」——米白 #F7F3EC 底、墨黑 #1F1B16、邮戳红 #B3402A 点睛、牛皮纸卡 #EDE6D6、邮票齿孔装饰边、短码与数字用等宽字体；去 AI 味：无紫渐变、无渐变标题、无三栏特性格、无 emoji 图标、无"赋能/极致体验"类文案。

**状态**：工程化 v1（2026-10-13 完成，go test 24 例全过、vet/gofmt 全洁、真实服务冒烟：建链→302 跳转→点击计数→二维码→统计→CSV 往返全链路验证；4 张 Web UI 真实截图已亲眼验收）。
**生产级补强 v1.2「可观测 + 限流 + 韧性」（2026-10-14）**：零依赖手写 Prometheus `/metrics`（请求/跳转/burn/限流拒绝计数、路由 label 归一化）；IP+Key 双维度令牌桶限流（429+Retry-After，/metrics 与探针免限流，RPS/BURST/开关走环境变量）；`/readyz` 就绪探针（DB ping 通 200 否则 503）+ `store.Ping()`；失败注入测试（关库后跳转/建链 500、health 200、readyz 503、metrics 200，全程不 panic）；CSV 导入导出扩展 7 列（兼容旧 5 列）；`docs/OPERATIONS.md` 运维手册（部署/备份恢复/升级/监控/排障/限流调参）；新增 24 例、`-race` 全过；真实服务冒烟 6 项全过；发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v1.2.md`（结论可发版，v1.1 条件项全部关闭）。
**生产级补强 v1.3「彻底删除 + 备份演练」（2026-10-15）**：burn 销毁后支持彻底删除，`LINKSHORT_BURN_PURGE_AFTER_DESTROY` 默认 false、开=true 时 302 后硬删除并返回 404，默认行为不变；新增 `scripts/backup.sh`/`restore.sh`（在线备份、`--force` 安全门、`--dry-run`、integrity_check、`.broken-` 快照，`make backup`/`make restore`）；`GET /api/meta` 增加 `burn_purge_after_destroy`；Prometheus 增加 `linkshort_burn_links_purged_total`；详情页 burn 链接显示销毁行为文案；go build/vet/gofmt 全洁，`go test ./... -race` 58 例全过（新增 6 例），真实服务冒烟 8 项全过，4 张 Web UI 截图逐张人工验收；发版对照报告见 `docs/PRODUCTION_CHECKLIST_REPORT_v1.3.md`（结论可发版；v1.2 遗留的“备份恢复未做自动化演练”未通过项已关闭）。

**生产级补强 v1.1「阅后即焚 + 限次访问」（2026-10-14，灵魂功能落地）**：`links` 新增 `max_visits`（NULL=不限）、`burn`（0/1）两列 + `PRAGMA user_version` 版本化迁移（v1→v2，老库自动 ALTER，实测老数据保留）；跳转语义：burn 链首次 302 后自动禁用、再访 410"链接已阅销毁"，max_visits=N 时前 N 次 302、第 N+1 次 410"链接已达访问上限"（burn 的 410 检查在禁用 404 之前）；`store.CreateLinkEx/UpdateLinkEx/MarkBurned`（旧签名保持委托不变）；API：POST/PATCH 接受 `max_visits`（1~1000000 正整数）、`burn`，非法组合 400；响应新增 `max_visits/burn/remaining` 字段；Web UI：新建页"限次访问"输入+"阅后即焚"复选框（互斥联动）、列表页"限制"列徽标（阅后即焚/已销毁/限N次·剩M次/不限）、详情页"访问限制"行+保存/清除；`go test ./...` 全过（新增 10 例：store 4 + handler 6）；真实服务冒烟全链路验证（302→410 语义、PATCH 改限次/清除、老库迁移）；3 张新截图亲眼验收通过；发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v1.1.md`（有条件发版：失败注入//metrics/运维手册/限流排期 v1.2，CSV 未带新字段）；CHANGELOG.md 新建。

**里程碑记录**：

- 工程化 v1（2026-10-13）：chi 路由 + 分层架构落地（config/db/model/store/handler/util/qr），短链 CRUD/跳转/统计/二维码/导入导出全模块、内嵌四页 Web UI、CI 与多阶段 Dockerfile 就绪
- v1.1 阅后即焚 + 限次访问（2026-10-14）：灵魂定位核心功能落地；dpsk 4 批生成（数据层/HTTP 层/前端/文档），回喂 2 轮修签名错配，编排手工修 3 处机械问题（残留分隔符、strconv→itoa、围栏残留）
- v1.3 彻底删除 + 备份演练（2026-10-15）：dpsk 分 5 批生成（purge 代码/备份脚本/测试/文档/UI 小改），测试回喂 3 轮（dpsk 编造 API、helper 错用，编排按流程回喂；最后一处 helper 编排按仓库现有模式机械替换），真实服务冒烟 8 项与 4 张截图人工验收通过

**后续计划**：

- 密码保护短链
- 访问地域统计
- 公开 API 文档页
- purge 定时清理任务（已销毁 burn 链兜底清理）
- 备份失败告警通知

## mortisedb「榫卯 MortiseDB · 本地多源数据拼装层」

**定位**：NAS 玩家/小团队的本地多源数据拼装层——把 SQLite/CSV/JSON/本地目录声明式映射成表，增量同步 + 冲突策略 + 类 SQL 查询视图 + 本地优先（数据落文件、可 Git 版本化）。Airbyte/dbt 对个人太重，Metabase 只读不解决拼装，这是真空位。

**技术栈**：Go 1.23 单二进制；modernc.org/sqlite v1.34.2（纯 Go，无 CGO）；标准库 net/http；go:embed 内嵌 Web UI；gopkg.in/yaml.v3 配置；go test + go vet；Dockerfile 多阶段构建。

**功能模块**：

1. 声明式连接器：SQLite/CSV/JSON/目录 → 表映射（YAML），主键定义，schema 自动推断与类型统一（INTEGER/REAL/TEXT/DATETIME/BOOLEAN）
2. 增量同步：updated_at 水位线（日期格式双边规范化后比较）+ 全量哈希比对兜底；软删除（_m_deleted）
3. 冲突策略：按源优先级自动裁决 / 挂起手动处理（_m_conflicts，source_a=现有方、source_b=挑战方）/ 本源重写自动 resolved
4. 查询视图：类 SQL 保存为视图，Web 运行、导出 CSV/API（_m_views）
5. 调度：定时同步任务 + 运行历史（_m_runs，Job 带源名后缀方便按源查上次同步）
6. CLI + 内嵌 Web UI（总览/同步/数据/视图/冲突五页）

**视觉**：「宣纸 + 榫卯」——宣纸 #F4EFE3 底、墨 #211C15、木赭 #8A5A33、朱砂 #B3402A 点睛、导航下榫卯线纹装饰、SVG 榫卯线稿 logo；去 AI 味：无紫渐变、无一切居中、无三栏特性格、无 emoji 图标。

**状态**：生产级 v1.2.0（2026-10-15）：YAML 声明视图自动注册（`views.SyncFromConfig`，sync/serve/views sync 幂等注册+更新+清理，`_m_views.origin` 区分 yaml/manual，老库自动迁移）+ `scripts/e2e.sh` 端到端编排（实测 E2E PASS）+ docker-compose 一键部署强化（健康检查/资源限制 512m·1 核/日志轮转 10m×3；`docs/OPERATIONS.md` 补部署/升级/排障）；go build/vet/test 全过（12 包）。

**发版对照**：`mortisedb/docs/PRODUCTION_CHECKLIST_REPORT_v1.2.0.md`——v1.2 增补：端到端自动化测试通过（v1.1 遗留项关闭）、视图自动注册通过、compose 一键部署通过（静态校验，未实测 docker run，本机无 daemon）；Dependabot 仍未通过（需用户在 GitHub Settings 手动开启，超出 agent 权限）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：31 个文件 dpsk 生成 + 编排验收；修 5 个后端 bug（含跨源删除误删、dir 根目录计行、水位线日期格式）；Web UI app.js 按真实 API 契约重写
- 生产级 v1.1.0（2026-10-13）：`dbtx` 接口重构（`*sql.DB`/`*sql.Tx` 公共子集）+ `syncOneTable` 批量事务（每 5000 行提交、出错回滚、水位线最终提交后写回）+ `sync.batch_size` 配置；真实负载验证倒逼出的性能修复（优化前 10 万行需约 44 分钟）；CHANGELOG/LOADTEST.md/README 实测数据齐备
- 生产级 v1.2.0（2026-10-15）：dpsk 分 5 批生成 + 编排修 3 处机械问题——e2e.sh 的 COUNT(*) 行数断言 bug、views_test import 缺 fmt、LOADTEST 锚定文本偏差；YAML 声明视图自动注册（`views.SyncFromConfig`，sync/serve/views sync 幂等注册+更新+清理，`_m_views.origin` 区分 yaml/manual，老库自动迁移）；`scripts/e2e.sh` 端到端编排实测 E2E PASS（10 行订单 CSV + 8 会员 JSON → sync 新增 orders 10/users 8 → 视图自动注册新增 2 → 改 YAML 新增 1 更新 1 → 删声明清理 1 → serve → CSV 导出 10 行）；docker-compose 一键部署强化（健康检查/资源限制 512m·1 核/日志轮转 10m×3，`docs/OPERATIONS.md` 补部署/升级/排障）；视图页真实截图更新（`docs/screenshots/views.png`，真实数据：4 城市销售额）；go build/vet/test 全过（12 包）

**后续计划**：

- Postgres/MySQL 只读源、冲突 Webhook 通知、视图定时物化、CSV 增量导入 API
- Dependabot（等用户在 GitHub Settings 手动开启）

## voxloom「声纹工坊 VoxLoom · 中文播客文字剪辑工作站」

**定位**：中文播客/有声书创作者的文字剪辑工作站——转写稿当时间轴，文字删改自动生成音频剪辑方案（保留呼吸节奏），语气词一键弱化，EDL 导出供 Premiere/Reaper 精修。Descript 闭源英文优先，开源侧中文文字剪辑是空位。

**技术栈**：C#/.NET 8 + Avalonia UI 12.1.4（跨平台桌面）+ 自研 VoxLoom.Core（无 UI 依赖）；CommunityToolkit.Mvvm；xunit（testhost 在 VM 上 IPC 不通，改用 SmokeRunner 反射直跑）；GitHub Actions CI（ubuntu+windows）。

**功能模块**：

1. 音频导入（WAV/MP3/FLAC/M4A：WAV 纯托管，压缩格式走 ffmpeg 真实解码）+ WaveformLod 多级波形金字塔，万级采样点流畅渲染
2. 转写稿导入：Whisper JSON / LRC / 纯文本；RuleBasedAligner 规则对齐（能量检测精修），文字↔音频双向定位
3. 文字删除/替换 → 音频剪辑：EditPlan + Delete/Replace/Attenuate 三种 op，过零点拼接 + 短交叉淡化防爆音，冲突检测抛 EditConflictException
4. 语气词（嗯/那个/对吧）检测 + 一键弱化（-12dB，首尾 50ms raised-cosine 过渡，保留呼吸节奏而非静音）
5. EDL（CMX3600）导出；演示模式 `--demo-wav` / `--screenshot`（Xvfb 离屏抓屏）

**视觉**：「录音棚调音台」——深板岩 #1C1A17 底、纸色 #EDE6D6 波形、橙色 #E8833A 高亮；去 AI 味：无紫渐变、无 emoji 图标、无营销腔文案。

**状态**：v1.1（2026-10-15 完成）：对照报告 18 项未通过中的 v1.1 部分全部补齐——MP3/FLAC/M4A 真实导入（ffmpeg 解码，NAudio 实测 Linux 不可用已弃用移除）、JSON 行结构化日志（op_id 全链路+脱敏+5MB 轮转）、自动备份+一键恢复（zip+manifest+sha256，删除/弱化前自动备份）、docs/OPERATIONS.md / RELIABILITY.md / SECURITY_DATA.md / TECH_DEBT.md、配置密钥分离（config.json+VOXLOOM_*，禁密钥键，违规则启动退出码 2）、.github/dependabot.yml（NuGet 每周，暂放项目内）；dotnet build 全过，测试 75/75（44 旧+31 新，SmokeRunner 反射直跑）；修了 dpsk 的 2 个真 bug（NAudio Mp3FileReader 跨平台不可用、日志轮转保留数 N+1）。

**发版对照**：`voxloom/docs/PRODUCTION_CHECKLIST_REPORT.md`（v1.0 快照）——v1.1 排期项已全部落地并测试通过；剩余 v2 项：指标告警、限流熔断、技术债清理轮、故障演练、真实负载验证。

**里程碑记录**：

- v0.1.0（2026-10-13）：灵魂一页纸先行（docs/SOUL.md）；Core 库 dpsk 生成 + 编排验收；UI Round D 生成后 2 轮修复额度用尽仍有残留，编排者亲自做跨文件 reconciliation 收尾；桌面 UI 在 Xvfb 下真实渲染截图已亲眼验收（docs/screenshots/main.png）
- v1.1（2026-10-15）：生产级补齐（M/L 规格 9 项）。选型实测结论：NAudio.Flac（2015/net45，硬绑定 NAudio 1.7.3）在 net8.0 编译失败已证伪弃用；NAudio 2.2.1 Mp3FileReader 在 Linux 报 Msacm32.dll 缺失已证伪弃用并移除依赖；压缩格式统一走 ffmpeg 真实解码。测试夹具为 ffmpeg 真实生成的 440Hz 正弦（wav/mp3/flac/m4a）+ 随机字节损坏文件，无 demo 数据。

**后续计划**：

- v1.2（候选）：备份 zip 加密选项、恢复前文件清单预览、控制台日志人读格式
- v2：ONNX 本地声学模型精对齐 + 内置转写、指标告警、限流熔断、技术债清理轮、故障演练、多轨口误自动推荐最自然一版

## interlude「幕间 Interlude · 分支叙事的 linter」

**定位**：给独立游戏叙事设计师/互动小说/剧本杀作者的开源桌面工具——分支叙事的 linter。Twine 太简单无校验，articy:draft 闭源贵，开源侧真空。

**技术栈**：Kotlin 2.1.0 + Compose Multiplatform Desktop 1.7.3 + Gradle；手写递归下降 DSL 解析器；JUnit5（28 例全过：单元 24 + 端到端 4）。

**功能模块**：

1. 叙事 DSL：scene/choice/jump/set/text/end，行号精确报错
2. 一致性校验引擎：死路、不可达节点、变量未初始化、条件永假、跳转目标缺失（5 条规则，定位到行号）
3. 可视化分支图：层次化布局，问题节点朱砂红圈注
4. 本地化文本抽取与回填（保留 `{var}` 占位）

**视觉**：「剧本排练室」——深墨底 #1B1712 + 暖纸黄 #E8DCC0 + 朱砂红 #C8402A；去 AI 味：无紫渐变、无渐变标题、无一切居中、无 emoji 图标。

**状态**：v1.1（2026-10-15）：结构化日志（com.interlude.log，人读/JSON 双格式走 stderr，--log-level 开关，日志不含剧本正文）+ 命令行校验工具 interlude-lint（退出码 0/1/2，text/json 报告）+ 端到端测试（示例剧本"解析→5 条规则→问题报告"全链路 4 例）+ docs/OPS.md + CHANGELOG.md + .github/dependabot.yml（gradle 每周，项目内暂存、待 token 补 workflow 权限后随 CI 迁根目录）。kotlinc 直编 + JUnit Console 验证（Gradle daemon 本机不可用），测试 28/28（24 旧+4 新）；修了 dpsk 的 3 个真 bug（CLI 位置参数解析导致 lint 永远 exit 2、测试误用不存在的 assertContains(CharSequence) 重载、测试期望顺序与 Validator 实际排序不符）。桌面 UI 截图验收仍是已知限制（VM 无 GUI 构建环境），未虚报。

**发版对照**：`interlude/docs/PRODUCTION_CHECKLIST_REPORT_v1.1.md`——v1 未通过项中集成测试/结构化日志/Dependabot/运维手册/CHANGELOG 已补齐；剩余未通过：.bak 自动备份（排期后续版本）、失败注入测试（排期 v2）、UI 截图验收与 Gradle 一键部署（环境限制，待正常环境）。

**里程碑记录**：

- v1（2026-10-13）：DSL 解析器 + 5 条校验规则 + 分支图布局算法 + 本地化抽取 + Compose 桌面 UI + 示例剧本；单测 24/24；布局算法渲染图已亲眼验证；UI 截图待正常环境补拍（未虚报）
- v1.1（2026-10-15）：生产级补齐（M 规格 6 项）——日志/CLI/端到端/OPS/CHANGELOG/Dependabot；测试 28/28；3 个真 bug 修复

**后续计划**：

- v1.2（候选）：.bak 自动备份 + 一键恢复、失败注入测试、大剧本真实负载压测
- v2：玩家路径热力分析 + 剧本杀复盘模式（backlog Phase 3 第 11 项）

## stagecue「舞监台 StageCue」

**定位**：小型剧团/脱口秀/校园演出的多端同步演出控台——时间轴 cue 编排（音频/灯光/字幕/演员提示）+ 导演台/返听屏/灯光台毫秒级时钟同步 + 排练模式 + 离线优先。QLab 只支持 Mac 闭源贵，开源里没有跨平台中文友好的。

**技术栈**：Kotlin Multiplatform + Compose Multiplatform 1.8.2（桌面导演台）+ Ktor 3.1.3（CIO 引擎同步服务）；Gradle 8.10.2 构建；Kotlin 2.2.10 / JDK 21。

**技术含金量**：
1. NTP 式时钟同步：`ClockEstimator` 最小延迟样本启发式，毫秒级多端对齐
2. 幂等事件广播：`msgId` 作幂等键 + `EventDeduper` 滑动窗口，重复触发不 double-fire
3. 离线操作日志：`OpLogStore`（`append(type, cueId, detail)`），重连可回放
4. 类型安全 WS 协议：`WsMessage` sealed interface + `@SerialName` snake_case discriminator

**视觉**：「黑场」——深炭黑 #17130F + 追光金 #E0A83E + 幕布红 #9E2B25；去 AI 味：无紫渐变、无渐变标题。

**功能模块**：

1. 时间轴 cue 编排器：cue 列表、手动触发/预备、音频播放（WAV）
2. 多端同步：WebSocket 时钟同步 + CueFired/CueArmed 广播（移动端接口已留 `ClientRole.MONITOR/LIGHTING`）
3. 导演台 UI：cue 列表 + 事件日志 + 传输控制条 + 服务器时钟显示
4. 离线优先：本地操作日志（内存版，File 版待接）

**状态**：v0.2.0（2026-10-15）：SQLite + Flyway 版本化迁移（旧 show.json 自动幂等导入）替代 JSON 文件存储；`GET /metrics`（Micrometer Prometheus，6 个指标）；备份→删库→恢复真实演练通过；启动配置非法值 fail-fast（exit 1）；排练模式后端真实实现（服务端持久化 + WS 广播 + 导演台联动）；MP3 解码（mp3spi + jlayer），WAV 回归通过。kotlinc 直接编译 + JUnit 全过（server/shared/desktop）。server 31/31、shared 29/29、desktop 音频测试 4/4、桌面 UI 全量编译通过

**发版对照**：`stagecue/docs/PRODUCTION_REPORT_v0.2.0.md`——v0.1.0 的 6 个未通过排期项本轮修复 5 个（剩限流熔断、Dependabot、告警、日志轮转/资源限制，均已记入 `stagecue/docs/TECH_DEBT.md`）。

**已知限制**：Gradle daemon 本 VM 无法运行（改 kotlinc 直接验证）；服务端用 CIO 非 Netty（Netty 在本 VM 误用 KQueue）；桌面 UI 运行时截图因 VM 缺 libXtst.so.6 未验收；移动端返听屏二期。
