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

**状态**：工程化 v1（2026-10-13 完成全栈重构，后端 API 与前端构建、集成测试均已跑通）。

**UI 重设计 v4（Tabler 组件库）**

2026-10-13：v3 手写玻璃拟态被用户判定为典型 AI 味并禁用；三步选型后改用 Tabler 1.6.1（一句话理由：基于 Bootstrap 5 的管理后台 UI 套件，天生控制台气质，深色模式开箱即用）。5 页全部改用 Tabler 原生组件，API 一字未动，theme.css 仅做容器宽度与表格密度微调；全站无 backdrop-filter；mvn test 20/20 全过；5 页真实数据截图亲眼验收通过；设计决策见 docs/DESIGN.md。

**里程碑记录**：

- 里程碑 1（2026-10-13）：静态单页版落地（localStorage 存储），同日被工程化重构取代，仅作历史记录
- 工程化重构 v1（2026-10-13）：前后端分离、SQLite 持久化、vitest 集成测试、GitHub Actions CI、Dockerfile

**后续计划**：

- 数据导入/导出
- 考研核心 500 词词库扩充
- 周报视图
- 深色模式

## second-brain「第二大脑」

**定位**：个人知识库系统，支持笔记、标签、搜索、双链与知识图谱，构建可生长的个人知识网络。

**技术栈**：Go 1.23 单二进制；标准库 net/http 提供 HTTP 服务，modernc.org/sqlite 作为纯 Go SQLite 驱动；go:embed 内嵌 Web UI 静态资源；go test 覆盖单元测试与集成测试；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 second-brain/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 笔记 CRUD
2. 标签体系
3. 全文搜索（相关性排序）
4. [[双链]]与知识图谱
5. Markdown 渲染与预览
6. 统计概览

**状态**：工程化 v1（2026-10-13 完成，构建、vet、全量测试与真实服务冒烟均已跑通）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：单二进制架构落地，内嵌 Web UI、SQLite 持久化、双链与图谱能力、CI 与多阶段构建就绪

**后续计划**：

- 数据导入/导出
- 附件支持
- 反向链接面板
- PWA

## drama-factory「AI 短剧工坊」

**定位**：短剧生产管理与剧本生成系统，v2 打通从剧本到成片的完整生产管线（剧本→分镜→AI 视频生成→ffmpeg 剪辑成片）。

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

**状态**：工程化 v2.2（2026-10-13：DoD 第 2 轮——结构化日志 + request_id 全链路、Resilience4j 超时熔断、提交接口限流、Docker Compose 一键部署；mvn test 26/26 全过；真实 jar 冒烟：request_id 透传/错误体/可读+JSON 日志、10 次内提交放行第 11 次 429 + Retry-After、调度日志带 poll-xxx；发版对照报告 docs/dod-v2.2.md）。

**UI 重设计 v3**（2026-10-13 完成）：新视觉概念「剪辑室 / 场记板」——分镜板改为场记板卡片墙（斜条纹板条 + 等宽大字镜号 + 景别/运镜 badge + 对白引用 + 时间码），任务队列改为任务卡片 + 进度条，成片库改为海报卡片墙（后端新增 `GET /media/finals/{id}/poster.jpg`，ffmpeg 从成片 1 秒处抽帧），生产看板改为横向胶片管线（齿孔装饰 + 卡点集暖橙描边）；配色近黑 #0E0E11 + 钨丝灯暖橙 #E8590C + 米白文字，Noto Sans SC + 等宽字体；设计决策见 docs/DESIGN.md；mvn test 12 例全过（含新增 MediaPosterTest）；4 页真实数据截图已亲眼验收通过；另修复 v2 遗留 bug（首页 scene-form 空绑定导致项目列表加载失败）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Spring Boot 分层架构落地，项目/剧集/角色/场景 CRUD、四场式剧本生成、Web 控制台、CI 与多阶段 Dockerfile 就绪
- 工程化 v2（2026-10-13）：短剧生产管线落地——分镜管理、视频任务状态机（mock/agnes 双 provider）、ffmpeg 剪辑成片（拼接+字幕烧录）、生产看板四页 Web UI；`drama.*` 配置全环境变量化（application.yml）；生产级 DoD 对照报告 docs/dod-v2.md（含未通过项排期表）；视觉验收亲手抓出并修复 2 个 bug（pipeline 看板二次渲染抛错致空白、pipeline.html 漏引 v2.css 致卡片无样式）
- 生产级补强 v2.1（2026-10-13，DoD 第 1 轮三项全交付）：Flyway 版本化迁移（V1__baseline.sql 由 Hibernate 实际 DDL 导出，ddl-auto→validate，baseline-on-migrate 兼容老库）+ 提交幂等（同 shot PENDING/PROCESSING 去重，首次 201/重复 200）+ 优雅关闭（server.shutdown=graceful + 调度器 await-termination 30s + 轮询在途收尾钩子 25s）；mvn test 20/20 全过；真实 jar 冒烟验证 Flyway 基线/幂等 201→200/优雅关闭日志；发版对照报告 docs/dod-v2.1.md
- 生产级补强 v2.2（2026-10-13，DoD 第 2 轮四项全交付）：结构化日志（logback-spring.xml，可读 pattern 含 request_id；SPRING_PROFILES_ACTIVE=json 切 Logstash JSON）+ request_id 全链路（RequestIdFilter 透传/生成/回写 X-Request-Id、ErrorResponse 含 requestId、调度轮询带 poll-xxx）+ Resilience4j（ResilientVideoProvider 装饰 agnes：CircuitBreaker 50%/4 次/60s + TimeLimiter 90s，熔断抛 ProviderCircuitOpenException 由指数退避接管）+ 提交接口限流（@RateLimiter 10 秒 10 次，超限 429 + Retry-After: 10）+ Docker Compose 一键部署（compose.yml：健康检查/日志轮转/资源限制；Dockerfile 加装 ffmpeg+curl）；mvn test 26/26 全过；真实 jar 冒烟全链路验证；发版对照报告 docs/dod-v2.2.md
- v5.1 控制台统一外壳（2026-10-13）：shell.js 注入左侧窄导航（6 页 + G+字母快捷键）+ 顶栏全局搜索 + ⌘K/Ctrl+K 命令面板；app.css 统一视觉语言（暖炭 #1c1917 + 降饱和蓝 #4a6fa5，零 backdrop-filter/零渐变/零 emoji 图标，沿用 v4.1 主题）；首页重做为 AI 工作区（左 AI 对话 + 右生产概览 workspace.js）；Tabler 1.6.1 本地化入仓库摆脱 CDN；storyboard.js 支持 ?episodeId= 深链；7 页真实数据截图亲眼验收通过并同步 docs/screenshots/；视觉验收抓出 2 个 v5.1 bug 已修（workspace.js 项目下拉单向同步致左右脱节、"去质检"链接参数名 finalCutId 与 qc.js 的 id 错配致跳空页）；mvn test 26/26 全过

**后续计划**：

- 接入真实大模型生成剧本
- DoD 未通过项排期（见 docs/dod-v2.2.md：第 3 轮 指标告警/鉴权/备份恢复/运维手册；第 4 轮 OpenAPI/CHANGELOG/Dependabot；第 5 轮敏感数据策略/降级策略文档/单测比例/user 字段）
- 审核流状态机
- 多用户与权限

## mini-os「网页操作系统」

**定位**：浏览器里的桌面操作系统，后端提供虚拟文件系统、设置持久化与应用注册表，前端实现可拖拽多窗口桌面。

**技术栈**：Rust + Axum 0.7（含 WebSocket）+ Tokio + rusqlite 0.32（bundled SQLite）；前端原生 HTML/CSS/JS（无框架）；cargo test 集成测试 8 例、cargo clippy 零警告；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 mini-os/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 虚拟文件系统（文件夹/文件 CRUD，SQLite 持久化，种子数据 Desktop/Documents/welcome.txt/notes.txt）
2. 应用注册表（文件管理器、文本编辑器、终端、设置、关于 5 个内置应用）
3. 可拖拽多窗口桌面 + 任务栏 + 开始菜单 + 时钟
4. 主题/壁纸设置持久化
5. WebSocket（连接先发 hello，文本消息 echo 回显）
6. 统计（文件/文件夹数、字节数）

**状态**：工程化 v1（2026-10-13 完成，cargo test 8 例全过、clippy 零警告、release 单二进制真实服务冒烟全过）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Axum + rusqlite 后端落地，虚拟文件系统 API、5 应用桌面前端、WebSocket 协议、CI 与多阶段 Dockerfile 就绪

**后续计划**：

- 文件上传/下载
- 多用户与权限
- 应用商店（插件化）

## ledger「钱迹 · 个人财务管家」

**定位**：个人财务管理系统，覆盖多账户记账、月度预算、统计分析与数据导入导出的完整记账流程。

**技术栈**：Python 3.11+ + FastAPI + SQLAlchemy 2.0（aiosqlite 异步）+ SQLite 单文件库；Jinja2 SSR Web UI（图表为服务端渲染内联 SVG，零外部依赖）；pytest + httpx（34 例测试）、ruff 检查与格式化；Dockerfile 单阶段构建；GitHub Actions CI 暂置于 ledger/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。

**功能模块**：

1. 多账户管理（余额按收支/转账自动汇总）
2. 交易记账（收入/支出/转账，金额统一用「分」整数存储）
3. 分类体系（seed 预置 18 个常用分类）
4. 月度预算与执行进度/超支预警
5. 统计分析（月度汇总、12 个月趋势、分类占比、净资产）
6. CSV 导入/导出
7. 周期性账单与未来 30 天到期提醒
8. Web UI（仪表盘/交易/账户/分类/预算/周期账单/导入导出 7 页）

**状态**：工程化 v1（2026-10-13 完成，pytest 34 例全过、ruff 全洁、真实服务 7 页面与核心业务流冒烟均已跑通）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：FastAPI 分层架构落地，账户/交易/分类/预算/统计/导入导出/周期账单全模块、Jinja2 SSR 前端、CI 与 Dockerfile 就绪

**后续计划**：

- 多币种与汇率
- 账单图片 OCR 录入
- 移动端适配

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

**状态**：工程化 v3（2026-10-13 完成：真中文分词 + 混合检索 v1；构建零警告、GoogleTest 40 例中 39 过〈WatcherTest.SubDir 为 pre-existing flaky，在 pristine v0.2.0 上同样偶发失败〉、中文语料 Top-1 10/10 符合预期、万级文件索引性能抽查完成）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：Database（SQLite+FTS5 手动同步）/ Indexer（递归爬取+增量）/ Searcher（查询构造）三层库 + docseek CLI（index/search/stats/prune）+ 15 例测试 + CI 与多阶段 Dockerfile 就绪
- 工程化 v2（2026-10-13）：`serve` 子命令落地——自研极简 HTTP 服务器（零第三方网络库）+ inotify 实时监控（新增/修改/删除自动增量索引，debounce）+ 内嵌 Web UI；7 个 REST 端点（/api/health、/api/stats、/api/search、/api/index、/api/prune、/api/watch GET/POST/DELETE）；测试扩至 32 例全过；真实冒烟验证新增/修改/删除自动索引、watch 增删 API 与 Web UI；补齐完整 README（安装/构建/测试/API 表格/已知局限）
- 工程化 v3（2026-10-13）：**中文分词攻坚**——cppjieba（v5.6.2，MIT，Keenable 核验 2026 年仍在维护）实现的 FTS5 自定义分词器（`tokenize='jieba'`，fts5_api 注册，CutForSearch + 字节偏移，ASCII 小写折叠）；`PRAGMA user_version` 2→3 旧库自动迁移（事务包裹，失败回滚）；**混合检索 v1**（BM25 + AND→OR 回退 + 标题/短语加成重排序）；词典运行时四级定位（DOCSEEK_DICT_DIR > ../share/docseek/dict > 同级 dict/ > 编译期默认），缺失则 fail-fast。评测：12 篇中文语料 10 查询 Top-1 全部符合预期（docs/eval.md）；万级文件（40MB）索引 267 秒，检索 2.7 秒（含词典加载）。调试中发现并修复 dpsk 埋的 bug：Jieba 构造函数传参顺序错误（把 idf.utf8 当用户词典加载导致切词异常）。

**后续计划**：

- HTML/PDF/Office 文本提取
- 结构化日志、备份恢复命令、运维手册（生产级补齐）
- 索引批量事务优化（当前约 37 文件/秒，单文件独立事务）
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

**里程碑记录**：

- 工程化 v1（2026-10-13）：Flask 应用工厂 + 蓝图分层落地，订阅/抓取/阅读/搜索/OPML/统计全模块、Jinja2 三栏阅读器前端、CI 与 Dockerfile 就绪
- 生产级补强 v1.1（2026-10-13）：抓取超时/重试/失败分类、调度状态持久化与补跑、结构化日志 + /healthz、配置校验、DB 迁移、备份恢复、docker-compose、运维手册；SimHash + Jaccard 两阶段去重聚类与折叠显示上线
- **灵魂功能 v1.2 重要性排序**（2026-10-13）：`feedflow/ranking.py`——五维加权可解释分数（时效衰减半衰期 48h 0.30 / 事件热度 0.25 / 来源权重 0.20 / 关键词 0.15 / 未读 0.10），分项归一 0~1、确定性无随机；「今日必读」页（/digest，默认 20 篇，每篇标注"为什么排前面"分项理由）+ 兴趣设置页（/settings/interests：关键词增删、来源手动权重、每日篇数 N）；来源质量从已读/星标比率自动学习；DB 迁移 v2（keywords/feed_weights/settings 三表）；pytest 62 例全过（新增 test_ranking.py 16 例）、ruff check 全洁、真实服务冒烟与 3 张新截图（digest/interests/reader）逐张视觉验收通过

**后续计划**：

- trafilatura 抓取超时收敛（当前单篇最坏等待较长）
- fever / Google Reader API 兼容
- 移动端阅读优化
- 全文 RSS 输出

## linkshort「短链 LinkShort · 自托管短链服务」

**定位**：自托管短链服务，把长链接变成短地址；单二进制 + SQLite + 内嵌 Web UI，跑起来就能用。

**技术栈**：Go 1.23 单二进制；chi v5.3.2 路由（组件库多元化：与 second-brain/sentinel 的标准库 net/http 错开），modernc.org/sqlite v1.34.5（纯 Go SQLite 驱动，无需 cgo）；skip2/go-qrcode 服务端生成二维码 PNG；go:embed 内嵌 Web UI；go test（24 例）、go vet、gofmt；Dockerfile 多阶段构建；GitHub Actions CI 暂置于 linkshort/.github，待 token 补齐 workflow 权限后迁移至仓库根目录。选型经三步调研：dpsk 出候选清单与对比维度（chi/gin/echo/fiber、skip2/go-qrcode/boombuler/yeqown）→ Keenable 核验时效性（chi v5.3.2 2026-09 发布、活跃维护；qrcode 为短链场景事实标准）→ go get 实际安装验证通过。选 chi 而非 gin/echo：一句话——单二进制小服务，chi 零第三方依赖、纯 net/http 兼容，与"一个二进制跑起来"的气质最贴合。

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

**里程碑记录**：

- 工程化 v1（2026-10-13）：chi 路由 + 分层架构落地（config/db/model/store/handler/util/qr），短链 CRUD/跳转/统计/二维码/导入导出全模块、内嵌四页 Web UI、CI 与多阶段 Dockerfile 就绪

**后续计划**：

- 密码保护短链
- 访问地域统计
- 公开 API 文档页

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

**状态**：工程化 v1（2026-10-13 完成，go build/vet/test 全过；真实冒烟：3 异构源同步→跨源 JOIN→水位线增量→冲突策略全链路验证；5 张 Web UI 真实截图已亲眼验收，修了 3 轮真实 bug：tab 切换失效、API 大小写字段错位、table.grid CSS 错位）。

**发版对照**：`mortisedb/docs/PRODUCTION_CHECKLIST.md`——有条件发版，6 项未通过均为已知限制且有排期（端到端自动化测试、优雅关闭、metrics、backup 子命令、Dependabot、10 万行负载验证）。

**里程碑记录**：

- 工程化 v1（2026-10-13）：31 个文件 dpsk 生成 + 编排验收；修 5 个后端 bug（含跨源删除误删、dir 根目录计行、水位线日期格式）；Web UI app.js 按真实 API 契约重写

**后续计划**：

- Postgres/MySQL 只读源、冲突 Webhook 通知、视图定时物化、CSV 增量导入 API
- 端到端自动化测试、backup 子命令、/metrics 指标

## voxloom「声纹工坊 VoxLoom · 中文播客文字剪辑工作站」

**定位**：中文播客/有声书创作者的文字剪辑工作站——转写稿当时间轴，文字删改自动生成音频剪辑方案（保留呼吸节奏），语气词一键弱化，EDL 导出供 Premiere/Reaper 精修。Descript 闭源英文优先，开源侧中文文字剪辑是空位。

**技术栈**：C#/.NET 8 + Avalonia UI 12.1.4（跨平台桌面）+ 自研 VoxLoom.Core（无 UI 依赖）；CommunityToolkit.Mvvm；xunit（testhost 在 VM 上 IPC 不通，改用 SmokeRunner 反射直跑）；GitHub Actions CI（ubuntu+windows）。

**功能模块**：

1. 音频导入（WAV）+ WaveformLod 多级波形金字塔，万级采样点流畅渲染
2. 转写稿导入：Whisper JSON / LRC / 纯文本；RuleBasedAligner 规则对齐（能量检测精修），文字↔音频双向定位
3. 文字删除/替换 → 音频剪辑：EditPlan + Delete/Replace/Attenuate 三种 op，过零点拼接 + 短交叉淡化防爆音，冲突检测抛 EditConflictException
4. 语气词（嗯/那个/对吧）检测 + 一键弱化（-12dB，首尾 50ms raised-cosine 过渡，保留呼吸节奏而非静音）
5. EDL（CMX3600）导出；演示模式 `--demo-wav` / `--screenshot`（Xvfb 离屏抓屏）

**视觉**：「录音棚调音台」——深板岩 #1C1A17 底、纸色 #EDE6D6 波形、橙色 #E8833A 高亮；去 AI 味：无紫渐变、无 emoji 图标、无营销腔文案。

**状态**：v0.1.0（2026-10-13 完成，commit 2df8304）：dotnet build（Debug/Release）全过；测试 44/44（含端到端链路 导入→对齐→删除→弱化→导出）；桌面 UI 在 Xvfb 下真实渲染截图已亲眼验收（docs/screenshots/main.png）；修了 dpsk 生成的 10+ 处跨文件 API 对不齐 + Avalonia.Generators 需 Roslyn 4.14 而 SDK 自带 4.11 的 InitializeComponent 坑（改用 AvaloniaXamlLoader.Load）。

**发版对照**：`voxloom/docs/PRODUCTION_CHECKLIST_REPORT.md`——有条件发版，18 项未通过均有排期（v1.1：结构化日志/错误处理策略文档/备份恢复/运维手册/CHANGELOG/Dependabot/文档同步；v2：指标告警/限流熔断/故障演练）。

**里程碑记录**：

- v0.1.0（2026-10-13）：灵魂一页纸先行（docs/SOUL.md）；Core 库 dpsk 生成 + 编排验收；UI Round D 生成后 2 轮修复额度用尽仍有残留，编排者亲自做跨文件 reconciliation 收尾

**后续计划**：

- v1.1：MP3/FLAC/M4A 导入、结构化日志、错误处理策略文档、备份恢复、运维手册、Dependabot
- v2：ONNX 本地声学模型精对齐 + 内置转写、多轨口误自动推荐最自然一版

## interlude「幕间 Interlude · 分支叙事的 linter」

**定位**：给独立游戏叙事设计师/互动小说/剧本杀作者的开源桌面工具——分支叙事的 linter。Twine 太简单无校验，articy:draft 闭源贵，开源侧真空。

**技术栈**：Kotlin 2.1.0 + Compose Multiplatform Desktop 1.7.3 + Gradle；手写递归下降 DSL 解析器；JUnit5（24 例全过）。

**功能模块**：

1. 叙事 DSL：scene/choice/jump/set/text/end，行号精确报错
2. 一致性校验引擎：死路、不可达节点、变量未初始化、条件永假、跳转目标缺失（5 条规则，定位到行号）
3. 可视化分支图：层次化布局，问题节点朱砂红圈注
4. 本地化文本抽取与回填（保留 `{var}` 占位）

**视觉**：「剧本排练室」——深墨底 #1B1712 + 暖纸黄 #E8DCC0 + 朱砂红 #C8402A；去 AI 味：无紫渐变、无渐变标题、无一切居中、无 emoji 图标。

**状态**：v1 核心完成（2026-10-13）：DSL 解析/校验/本地化/布局算法全部单测通过（24/24），示例剧本冒烟报出 5 个问题全部命中，分支图布局算法已可视化验证。UI 源码完成但沙箱环境无法构建桌面二进制（Gradle daemon IPC 故障 + 手工 kotlinc 的 compose 插件后端崩溃），UI 截图待正常环境补拍——未虚报验收。

**发版对照**：`interlude/docs/PRODUCTION_CHECKLIST_REPORT.md`——核心达到生产级基础；未通过项（集成测试、结构化日志、.bak 备份、Dependabot、运维手册）均有排期或声明为已知限制。

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

**状态**：v0.1.0（2026-10-13）：`:shared` 25/25 单测通过，`:server` 10/10 单测通过，WS 冒烟 8/8 通过（双客户端 Welcome/时钟同步/CueFired 广播/幂等）。桌面端全量编译通过（含 Compose UI）；运行时截图因 VM 缺 `libXtst.so.6` 系统库无法验收——未虚报。

**发版对照**：`stagecue/docs/PRODUCTION_REPORT_v0.1.0.md`——13/22 通过；未通过项（SQLite 迁移、/metrics、备份实测、限流等）均有排期或声明为已知限制。

**已知限制**：Gradle daemon 本 VM 无法运行（改 kotlinc 直接验证）；服务端用 CIO 非 Netty（Netty 在本 VM 误用 KQueue）；排练模式为 UI 占位；音频仅 WAV。
