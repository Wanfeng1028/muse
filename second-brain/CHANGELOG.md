# 更新日志

本项目的所有重要变更都会记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.19.0] - 2026-10-25
### 未来到期预测
### 新增
- GET /api/review/forecast?days=（默认 7，钳制上限 30），按 X-User/?user= 隔离，返回 {days, overdue, total, forecast:[{date, due}]}，forecast 按日期升序、首日为今天；overdue 为 due_date 早于今天的行数；total = overdue + 窗口内各日 due 之和；无 schema 变更。
- 前端：复习统计页新增「未来到期预测」区块——三枚数字（已逾期 / 未来 7 天到期 / 待处理合计）+ 逐日条形（日期 MM-DD + 星期 + 条数，条长按当日最大值归一）。
- internal/store/review_forecast.go 新增 ReviewForecast 聚合；internal/api/review_forecast.go；前端 index.html 新区块、app.js 取数渲染、style.css 六个 forecast-* 规则。
### 测试
- Store 层 4 组（空库 / 计数与窗口 / 用户隔离 / 钳制）。
- API 层 3 组（空库默认 / 钳制 / POST 405）。
- go test ./... 全绿；go vet 全洁。
- app.js 经 node --check 通过。
- 真实服务冒烟：3 条笔记评分后预测为次日 3 条、逾期 0、合计 3，days=30 同样正确。
- 截图 docs/screenshots/forecast-v019.png 已验收通过。
### 已知限制
- 基准日为传入 today 的 dateOnly，与既有 streak / heatmap 口径一致。

## [0.18.0] - 2026-10-24
### 打卡连续详情

### 新增
- API：`GET /api/review/streak`（按 `X-User`/`?user=` 隔离），返回打卡连续详情：当前连续天数、历史最长连续天数、累计复习天数、最近复习日；当前连续天数语义与既有 `streakDays` 一致（含当天、当天未复习则从昨天起算）。
- 前端：复习统计页新增「打卡连续」区块——当前连续、历史最长、累计复习天数、最近复习日四项，失败静默。
- Store：`internal/store/review_streak.go` 新增 `ReviewStreak` 聚合（无 schema 变更；历史最长按日历连续日计算，断档即重计）。

### 测试
- Store 层 4 例（空库/最长与当前/昨天起算回退/用户隔离）全部通过。
- API 层 3 例（空库/有数据/非 GET 方法 405）全部通过。
- `go test ./...` 全绿，`go vet` 全洁。
- 真实服务冒烟通过：播种连续日期后 `/api/review/streak` 汇总与断言一致。
- 截图亲眼验收通过。

### 已知限制
- 当前连续天数与历史最长均按复习记录的 UTC 日期计算，与既有 `streakDays` 口径一致。

## [0.17.0] - 2026-10-24
### 记忆健康诊断

### 新增
- API：`GET /api/review/health`（按 `X-User`/`?user=` 隔离），返回记忆健康诊断：到期/逾期 7 天以上/从未复习汇总、平均 EF、EF 四档分布、最多 20 条需关注卡片（`reason` 为 ef_floor/overdue_long/never_reviewed_long，`reasonText` 大白话）、服务端规则生成的大白话建议 `advice`。
- 前端：复习统计页新增「记忆健康」区块——汇总 4 数字、EF 分布条、需关注卡片列表（点标题跳转笔记）、建议列表；失败静默。
- Store：`internal/store/review_health.go` 新增 `ReviewHealth` 聚合（汇总计数 + EF 分桶 + 三类需关注卡片 + 建议规则），无 schema 变更。

### 测试
- Store 层 6 例（空库/汇总计数/ef_floor/overdue_long/never_reviewed_long/用户隔离）全部通过。
- `go test ./...` 全绿，`go vet` 全洁。
- 真实服务冒烟通过：播种三类卡片后 `/api/review/health` 汇总与列表断言一致。
- 截图亲眼验收通过。

## [0.16.0] - 2026-10-23
### 年度复习热力图

### 新增
- API：`GET /api/review/heatmap?days=`（默认 365，上限 366），返回最近 N 天每日复习数与新增数，日期升序含今天，口径与 `/api/review/trend` 完全一致。
- 前端：复习统计页新增「年度热力图」区块，GitHub 贡献图样式（列=周、行=周一至周日、周一对齐），5 档蓝色色系，大白话 tooltip，失败静默。
- Store：`ReviewTrend` 聚合逻辑抽为未导出 `reviewTrendCore`，`ReviewTrend` 与新增 `ReviewHeatmap` 共用，既有行为零变更。

### 测试
- Store 层 4 例（默认天数、钳制边界、数据正确性、跨用户隔离与 Trend 一致性）+ API 层 3 例（默认 365、钳制 366、跨用户隔离）全部通过。
- `go test ./...` 全绿，`go vet` 全洁。
- 真实服务冒烟通过：365 行数据、首尾日期正确、days=400 自动钳制为 366。
- 截图亲眼验收通过。

## [0.15.0] - 2026-10-20

复习产品化：困难卡片 + 统计页 + 图谱升级 + 推送深测

### 新增
- 困难卡片：`POST /api/review/{id}/hard` 标记/取消；复习队列项带 `hard` 字段；
  SM-2 联动——评 3 分（困难）且已标 hard 的卡片下次间隔减半（reviews.is_hard，
  迁移 v3）。
- 复习统计：`GET /api/review/trend?days=7`（每日复习/新增数）、
  `GET /api/review/mastery`（按标签：卡片数/平均 EF/困难数/今日到期）。
- 前端：卡片"标记为困难"切换钮；完成态 4 数字面板；"复习统计"视图
  （7 日趋势条形图 + 各科掌握度表）；图谱力导向布局（斥力/引力/重力/钳制，
  确定性）+ 孤立节点聚合 + 滚轮缩放/拖拽平移/悬停浮层/标签避让。
- P1-6：离线新建笔记客户端幂等键 `clientNoteId`（迁移 v4，唯一索引；
  offline-queue.js 入队注入）。
- P2-5：WebPush 无到期复习时也推送空 digest（与 SMTP/Webhook 一致）。
- `scripts/seed-demo`：55 篇中文演示数据（71 双链、20 篇复习历史），截图验收用。

### 测试
- 新增：困难卡片 store/API（含迁移幂等）、SM-2 困难惩罚、趋势、mastery、
  SMTP 失败注入（握手中断/连接被拒/535/完整对话）、WebPush 部分失败
  （410 清理/500 耗尽/混合）、死信 E2E（双通道耗尽/同日幂等/次日隔离/
  不可重试快速失败）、WebPush 空 digest、clientNoteId 幂等。
- 全量 `go test ./...` 全绿；`go vet`/`gofmt` 全洁。

### 已知限制
- 困难惩罚仅作用于 grade=3；grade≤2 本来就会重置学习进度。
- 种子脚本仅用于演示，不随服务发布。


Prometheus 指标 + API 限流

### 新增
- `internal/metrics`：手写 Prometheus exposition（零新依赖），`GET /metrics`；指标 `http_requests_total{method,route,status}`、`http_request_duration_seconds{method,route}`（histogram）、`push_sent_total{channel,status}`、`reviews_graded_total{grade}`、`notes_total`、`reviews_due`；gauge 采集时实时查库。`SB_METRICS_ENABLED`（默认 true）、`SB_METRICS_TOKEN`（Bearer 鉴权，为空不鉴权）。
- `internal/ratelimit`：token bucket 限流中间件，按 clientIP+用户双维度 key，读/写独立桶（写=POST/PUT/DELETE/PATCH 更严）；`SB_RATE_LIMIT_ENABLED`（默认 true）、`SB_RATE_LIMIT_RPS`（20）、`SB_RATE_LIMIT_BURST`（40）、`SB_RATE_LIMIT_WRITE_RPS`（5）、`SB_RATE_LIMIT_WRITE_BURST`（10）；超限 429 + `Retry-After` 秒头 + `{"error":"rate limit exceeded","request_id":"..."}`；非法值启动 fail-fast（log.Fatalf，exit 1）。
- 中间件链：request_id -> metrics -> ratelimit -> mux；复习评分埋点 `reviews_graded_total`，推送各结果（sent/failed/failed_permanent/skipped）埋点 `push_sent_total`。
- 文档：README 新增「指标与限流」章节与 7 个环境变量；`docs/OPERATIONS.md` 新增指标/限流运维节。

### 测试
- metrics 8/8 全绿（exposition 格式、label 转义、histogram 桶累计、gauge（含 panic→NaN、nil 删除）、中间件路由 label 与 /metrics 跳过、50 goroutine 并发 -race）。
- ratelimit 7/7 全绿（Validate 非法值、令牌桶 refill/耗尽、读写桶独立、禁用透传、真实 HTTP 连续打超限 429+Retry-After+request_id、写接口更严、X-Forwarded-For IP 隔离）。
- 全量 `go test ./...` 全绿；`go build`/`go vet`/`gofmt` 全洁。
- 真实服务冒烟（2026-10-17）：指标值正确、429 行为正确、fail-fast exit 1、token 鉴权正确。

### 已知限制
- `reviews_due` 只统计默认用户的今日到期数，多用户各自到期数暂未拆分。
- 限流桶在单机内存里，多实例部署时每个实例独立计数（沿用 v0.10 调度器单实例假设）。
- histogram buckets 固定，不可配。

## [0.11.1] - 2026-10-16

结构化日志 + request_id 全链路追踪

### 新增
- 结构化日志：`internal/log` 包（标准库 `slog`，JSON 输出到 stdout），`SB_LOG_LEVEL` 控制级别（debug/info/warn/error，默认 info）。
- 请求全链路追踪：中间件透传/生成 `X-Request-ID`（32 位随机串），注入 context，响应头回写；每条请求记 `http.request` 日志（request_id/method/path/status/latency_ms，5xx 用 ERROR）。
- 错误响应体统一带 `request_id` 字段，方便按 ID 查日志定位。
- `store.CreateNoteFor` / `store.RecordReview` 首参加 `ctx`，关键操作（建笔记/评分/推送测试）打带 `request_id` 的日志；`CreateNote` 保持原签名兼容。
- 推送调度器、导出接口、`main.go` 的 `log.Printf` 全部替换为结构化日志。
- README「日志与可观测性」章节 + `docs/OPERATIONS.md` 日志运维说明。

## [0.11.0] - 2026-10-16

推送发送重试——网络抖动、对方 5xx、被限流时自动重发，重试完还失败记为死信

### 新增
- `internal/push/retry.go`：指数退避重试引擎。`RetryPolicy`（`SB_PUSH_MAX_RETRIES` 默认 3、上限 10；`SB_PUSH_RETRY_BASE_MS` 默认 1000ms；退避 `base*2^attempt` + ±25% 抖动，上限 30s）；`IsRetryable` 错误分类（可重试：网络/连接错误、HTTP 429、5xx；不可重试：鉴权失败、其他 4xx、WebPush 订阅失效 410/404；未知错误 fail-open）；`WrapWithRetry`（`Name()` 原样透出，`MaxRetries+1` 次尝试，ctx 取消立刻退出）；`SendWebPushWithRetry`（逐浏览器订阅重试）；`RecordDeadLetter`（`push_log` 写 `status='failed_permanent'`，同 date/channel/user 幂等不重复入死信）。
- `internal/store/push_status.go`：`PushLogStatus` 查询最新推送状态。
- `internal/push/scheduler.go` 接线：`BuildSenders` 出口统一包装 SMTP/Webhook（channel 名不变）；`RunPushForUser` 重试耗尽转死信；`sendWebPushDigest` 逐订阅重试，耗尽转死信（410/404 仍走订阅清理）。
- 文档：README 推送章节新增"发送重试"小节与两个环境变量说明；新建 `docs/OPERATIONS.md`（部署/推送配置/重试策略/死信处理/备份恢复/排障）；`docs/PRODUCTION_CHECKLIST_REPORT_v0.11.md` 发版对照报告。

### 测试
- push 包 17/17 全绿（新增 9 个 retry 单元测试：失败 2 次后成功、一直失败耗尽、不可重试 0 睡眠、退避时长区间、死信幂等、环境变量边界；2 个真实 HTTP 冒烟：httptest mock 前 2 次 500 → 真实 WebhookSender 第 3 次成功，请求计数 3；一直 503 → 耗尽转死信）。
- store 49/49、notify 12/12、markdown/review/search 全绿；`go vet`、`gofmt` 全洁。

### 已知限制
- `POST /api/push/test` 测试通道保持单次发送，不重试。
- 死信次日不补发，第二天正常推送当天的。
- 调度器单实例假设，多实例部署会重复推送（沿用 v0.10 限制）。
- api 集成测试（触发推送→重试→push_log 流转→history 可见死信）待 `internal/api` 重构完成后补。

## [0.10.0] - 2026-10-16

浏览器 Web Push 推送——每天到点，浏览器弹提醒，不用开邮箱也能收到复习通知

### 新增
- `push_subscriptions` 表（`endpoint` 全局唯一，按 `user_id` 隔离）+ `internal/store/subscription.go`（Upsert/Delete/List/Count，参数校验中文错误）。
- `internal/notify/webpush.go`：VAPID Web Push 发送器（`github.com/SherClockHolmes/webpush-go`），410/404 自动清理失效订阅，单订阅失败不影响其他，发送超时 10s。
- 4 个 API：`POST/DELETE/GET /api/push/subscriptions`、`GET /api/push/vapid-public-key`；`p256dh`/`auth` 一律脱敏返回，VAPID 未配置时返回 503。
- 调度器集成：有到期复习时给已订阅用户推送（沿用 X-User 用户隔离口径），与 SMTP/Webhook 共用"今日已推送"去重。
- 前端：推送设置页「浏览器推送」区（通知权限/订阅状态/开启/关闭按钮，大白话失败提示）；`/#review` hash 直达复习页。
- `sw.js`：`push` 事件解析载荷显示通知，`notificationclick` 聚焦或打开复习页；缓存版本升到 v0.10.0。
- 配置：`SB_VAPID_PUBLIC_KEY` / `SB_VAPID_PRIVATE_KEY` / `SB_VAPID_SUBJECT`；只配 VAPID 也能启动（`Validate` 已修正）。

### 测试
- `go test./...` 157/157 全绿（新增 18 例：`subscription_test.go` 6、`push_subscription_test.go` 8、`webpush_test.go` 4，覆盖 CRUD/校验/跨用户隔离/503/脱敏/410 清理/加密发送）。
- `go vet`、`gofmt` 全洁。
- 真实冒烟：真实服务 + mock push service 全链路通过（订阅→到期复习→scheduler 触发→mock 收到 aes128gcm 加密推送→退订）；推送设置页两态截图已验收（`docs/screenshots/push/`）。

### 已知限制
- VAPID 密钥需用户自己生成配置（README 有生成命令）。
- 调度器单实例假设，多实例部署会重复推送。
- iOS 需 16.4+ 且已安装到主屏幕才能收 Web Push。
- 无到期复习时不推送。

## [0.8.0] - 2026-10-16

搜索相关性升级——中文搜得准，还能看懂为什么排前面

### 新增
- `internal/search` 新增 `ScoreDetailed`/`RankDetailed`/`QueryTerms`：查询词 AND 语义（缺一词不得分）、标题权重 3 / 标签权重 2 / 正文权重 1、正文长度归一化（长文不再靠词频碾压）、中文二元词组加成（标题含"复习"整体比"复""习"分散分高）、整串完全匹配加成、中文单字停用字过滤（的/了/是/在……），并返回"查询词×命中字段"明细（可解释）。
- `store.SearchNotes` 的 SQL 增加标签匹配（`EXISTS` 子查询走 `note_tags`/`tags` 表），只打标签的笔记也能被搜到；无 schema 变更。
- `GET /api/search` 响应改为对象 `{"query","terms","notes","meta"}`，`meta` 含每条笔记的 `score` 与命中字段（标题/标签/正文）；q 为空返回各字段为空的对象。
- 前端搜索结果：命中词 `<mark>` 高亮（先转义后标记，防 XSS）、正文显示命中上下文摘要（前后各 30 字）、每条结果标注"命中：标题 · 正文"；沿用现有视觉变量，无新配色。

### 变更
- `GET /api/search` 响应体由数组改为对象，**不兼容**：旧客户端按数组解析会失败，需取 `data.notes`。

### 测试
- `go test ./...` 全量 125 通过、0 失败（新增 `internal/search/search_relevance_test.go` 10 例、`internal/api/search_relevance_test.go` 2 例，覆盖权重排序/AND 语义/词组加成/完全匹配/停用字/长度归一化/Matches 明细/真实 HTTP 集成）。
- `go vet`、`gofmt` 全洁；真实服务冒烟：5 篇中文笔记搜索排序/高亮验证通过。

### 已知限制
- CJK 仍为逐字切分（无真实中文分词），词组加成只能缓解，复杂长词的语义理解有限。
- 查询词 AND 语义：多词查询缺一词即无结果，对只想"沾边"的搜法不友好。

## [0.7.0] - 2026-10-16


PWA——装到手机上，断网也能用

### 新增
- Web App Manifest（`internal/web/static/manifest.webmanifest`）：name/short_name/start_url/display standalone/id，主题色 `#4f7cff`；图标 192/512/maskable PNG + SVG（`internal/web/static/icons/`，Chromium 从 SVG 光栅化）。
- Service Worker（`internal/web/static/sw.js`，由 `GET /sw.js` 从站点根提供，`Service-Worker-Allowed: /`）：应用壳预缓存；导航请求网络优先、失败回退 index.html；GET 类 API stale-while-revalidate；写操作只走网络。
- 离线写队列（`internal/web/static/offline-queue.js`，IndexedDB）：断网时新建/修改/删除笔记、复习评分入队，联网后按序回放；`pwa.js` 负责 SW 注册/更新提示/在线状态徽标，`install.js` 负责安装横幅（Chromium `beforeinstallprompt`）与 iOS 手动安装说明。
- 服务端：`GET /sw.js`（no-cache）与 `GET /manifest.webmanifest`（`application/manifest+json`）两个路由（`internal/api/server.go`）。
- 文档：`docs/PWA_INSTALL.md`（iOS/Android/桌面安装步骤）、`docs/PWA_OFFLINE_DESIGN.md`（缓存策略/队列/冲突规则）、`docs/PWA_QA.md`（手工验收清单）、`docs/PRODUCTION_CHECKLIST_REPORT_v0.7.md`（发版对照报告）。

### 已知限制
- 推送通知本版不支持（后续计划）。
- iOS 无后台同步，队列靠 online 事件与启动时回放；iOS 无自动安装提示，需手动"添加到主屏幕"。
- 离线新建笔记回放时会产生新 id（无客户端幂等键）；冲突以服务端为准、后写入胜出。
- 局域网 `http://IP:8080` 不安全上下文中 PWA 不可用（需 HTTPS 或 localhost）。

### 测试
- 新增 `internal/api/pwa_test.go`：manifest 字段与图标存在性、sw.js 响应头、SW 缓存清单与文件一致性回归。
- `go test ./...` 全量通过，`go vet`、`gofmt` 全洁；真实服务冒烟（manifest/sw.js 200、离线刷新可用）。

## [0.6.0] - 2026-10-16
>>>>>>> REPLACE


多用户复习隔离——一台机器，多个人各记各的复习进度

### 新增
- `reviews` 表加 `user_id` 列，主键改为 `(note_id, user_id)` 复合；新库直接建新 schema，老库打开时自动迁移（加列 + 重建主键，幂等，历史数据归属 `local`）。
- `internal/store` 新增 `NormalizeUser`/`DefaultUser`（`internal/store/user.go`）；复习查询（`GetReviewState`/`RecordReview`/`ListDueReviews`/`ReviewStats`/`DigestNotes`）全部按用户过滤；`CreateNoteFor(n, user)` 建笔记时复习行归属当前用户。
- 新增 `internal/api/user.go`：`CurrentUser(r)` 从 `X-User` 头 / `?user=` 参数解析身份，默认 `local`；复习四组 API 与 `POST /api/notes` 按用户隔离。
- 前端侧边栏顶部新增"使用者"切换器：输入名字点切换即生效，身份记 localStorage（`sb-user`），每个请求自动带 `X-User` 头；复习徽标、队列、统计、每日回顾按当前使用者刷新。
- 定时推送暂按默认 `local` 用户聚合（后续计划支持按用户推送）。

### 测试
- store 新增隔离测试 8 例：归一化、建行归属、A 到期 B 不可见、评分互不干扰、digest/stats 按用户、老库迁移、跨用户自动建行。
- api 新增真实 HTTP 隔离测试 5 例：queue 隔离、query 参数与头优先级、评分隔离、digest 隔离、默认 local。
- `go test ./...` 全量通过，`go vet`、`gofmt` 全洁。

## [0.5.0] - 2026-10-16

反向链接面板——打开一篇笔记就知道谁引用了它

### 新增
- 新增 `internal/store/backlinks.go`：`Backlink` 结构与 `Store.Backlinks(noteID)`，按引用者 id 倒序返回；`buildSnippet` 按 rune 提取 `[[标题]]` 所在行前后各 40 字上下文，中文不断字。
- 新增 API `GET /api/notes/{id}/backlinks`：笔记不存在返回 404，无人引用返回空数组 `[]`。
- 前端编辑区附件区下方新增「反向链接」区：引用者标题 + 引用上下文，点击标题跳转到引用者笔记；沿用附件区视觉体系，无新颜色。
- 真实截图 `docs/screenshots/backlinks.png` 已亲眼验收。

### 测试
- 全量 114 通过（v0.4.0 的 104 + 新增 10：store 6 + api 4），`go vet`、`gofmt` 全洁。
- store 6 例：基本查询、空返回非 nil、多条倒序、删源笔记、去掉链接后消失、先写 `[[Gamma]]` 再建 Gamma 回填生效。
- api 4 例：有引用者 200、空数组 `[]`、不存在 404、非法 id 非 200（真实 HTTP）。
- 真实冒烟：3 篇真实笔记 → 反向链接 2 条倒序，snippet 中文正确；Playwright 真实点击跳转验证通过。

## [0.4.0] - 2026-10-16

主动复习外部推送——到期提醒推出去

### 新增
- 新增 `internal/notify` 包：定义 `Sender` 接口，提供 SMTP 与 Webhook 两种通知通道。
- 新增 `SMTPSender`：基于标准库 `net/smtp`，支持 STARTTLS 与明文两种模式。
- 新增 `WebhookSender`：POST JSON，带 `X-Event: review.digest`，带 `X-Signature: sha256=<hex(hmac-sha256(secret, body))>`。
- 新增 `BuildDigestMessage` 纯函数：生成主题、纯文本正文和邮件客户端兼容 HTML（table 布局、内联样式，标题与摘要做 HTML 转义）。
- 新增 `internal/push` 包：`NextPushTime` 纯函数、30 秒 tick 的 `Scheduler`、`RunPush` 推送流程。
- 推送幂等：同一天同一通道只成功推送一次，靠 `push_log` 唯一索引加 `HasPushed` 检查。
- 新增推送 API：`GET/PUT /api/push/settings`、`POST /api/push/test`、`GET /api/push/history`。
- 新增推送设置页：侧边导航「推送设置」，含启用、时间、时区、收件邮箱、SMTP 主机、发件地址、Webhook 地址、保存、测试 SMTP、测试 Webhook、推送历史表。
- 新增 12 个推送配置项：`SB_PUSH_ENABLED`、`SB_PUSH_TIME`、`SB_PUSH_TZ`、`SB_SMTP_HOST`、`SB_SMTP_PORT`、`SB_SMTP_USER`、`SB_SMTP_PASS`、`SB_SMTP_FROM`、`SB_SMTP_TLS`、`SB_MAIL_TO`、`SB_WEBHOOK_URL`、`SB_WEBHOOK_SECRET`。

### 测试
- 全量 104 通过，v0.3.0 时 68，新增 36。
- notify 单元 8 条：标题、空队列、HTML 转义 XSS、webhook 成功与验签、非 2xx、超时、SMTP 不可达。
- push 调度单测：`NextPushTime` 当天未来、已过转次日、非法格式、时区；`RunPush` 幂等；单通道失败不影响另一通道。
- api 集成：webhook 接收端验 `X-Signature`；自研最小 fake SMTP 服务器走完 EHLO→DATA→QUIT 真实收信；settings 脱敏；PUT 非法 time 返回 400；body 含 password 返回 400。
- 真实冒烟（2026-10-16）：webhook 接收桩真实收到 `X-Event`、`X-Signature` 与完整 payload；调度器按配置时间真实触发，`push_log` 记 sent；`/api/push/test` 真实发出。

### 已知限制
- SMTP 密码与 webhook 密钥只能走环境变量，页面不可配置。
- 单用户，无多租户。
- 调度器按单实例假设工作，多实例部署会重复推送，需要外部保证单实例。
- SMTP 发送失败按次记录，可等次日或手动测试重发，没有自动重试队列。

## [0.3.0]
## [0.3.0] - 2026-10-15

附件与导出——笔记可以带图片和文件了，全库也能一键带走。

### 新增

- **附件支持**：`POST /api/notes/{id}/attachments` 上传附件（multipart，默认单个 ≤10MB，可用 `SB_ATTACH_MAX_MB` 调整）；扩展名白名单 + 文件名消毒 + 图片 MIME 嗅探校验；文件落 `<数据目录>/attachments/<笔记id>/`，元数据记 `attachments` 表（含 sha256）；`GET /api/notes/{id}/attachments` 列表、`GET /api/attachments/{id}` 下载、`DELETE /api/attachments/{id}` 删除；删笔记时附件目录一并清理。
- **Markdown 附件引用**：正文中 `![说明](attachment:123)` 渲染为内联图片，`[说明](attachment:123)` 渲染为下载链接，编辑预览与复习卡片共用同一渲染。
- **附件 Web UI**：编辑区新增附件区（上传入口、附件列表、图片缩略图预览、插入引用/下载/删除）。
- **导出**：`GET /api/export/markdown` 打包全库为 zip（`index.md` + `notes/` 下每篇一个带 front matter 的 `.md` + `attachments/` 原文件，引用改写为相对路径，条目名消毒防 ZipSlip）；`GET /api/export/json` 导出全库 JSON（含标签与附件元数据）；侧边栏新增导出按钮。

### 文档

- README 新增附件与导出章节、API 表与配置项，路线图移除已落地的两项。

## [0.2.0] - 2026-10-13

主动复习引擎——让笔记从“记录”走向“记忆”。

### 新增

- **SM-2 间隔重复算法**：新增 `internal/review` 纯函数包，实现 SuperMemo SM-2 调度算法，核心逻辑无副作用、可独立测试，包含难度因子（EF）更新、间隔递增与复习时间计算。
- **`reviews` 表与到期队列**：新增 `reviews` 数据表，记录每次复习的评分、时间与调度状态；提供按到期时间排序的复习队列，支持“今日待复习”查询。
- **复习统计**：新增学习统计能力，包括连续复习天数（streak）、近 7 日复习量、平均难度因子（平均 EF）等指标。
- **每日回顾 digest**：新增每日回顾摘要生成，汇总当日到期卡片与复习进度，帮助用户快速进入复习状态。
- **抽认卡复习 UI**：新增抽认卡（flashcard）复习界面，支持翻卡、四档评分（忘记 / 困难 / 良好 / 简单）与复习进度展示。

### 修复

- **Web 三件套一致性重建**：修复 HTML、CSS、JavaScript 之间元素 `id` 错位导致的事件绑定失效与状态渲染异常问题，重建三者一致的 DOM 契约。

### 变更

- 复习相关调度逻辑统一收敛至 `internal/review` 纯函数包，UI 与存储层仅负责编排与持久化，便于后续测试与替换算法。

## [0.1.0] - 2026-10-13

工程化 v1——从零搭建可用的第二大脑基础设施。

### 新增

- **笔记 CRUD**：支持笔记的创建、读取、更新与删除。
- **标签**：支持为笔记打标签，并按标签组织与筛选内容。
- **全文搜索**：基于 SQLite 的全文搜索能力，快速定位笔记内容。
- **双链与知识图谱**：支持笔记间双向链接，并据此构建知识图谱视图。
- **内嵌 Web UI**：提供内嵌于应用的 Web 界面，无需额外部署即可使用。
- **SQLite 持久化**：所有数据通过 SQLite 本地持久化，保证数据可迁移、可备份。
