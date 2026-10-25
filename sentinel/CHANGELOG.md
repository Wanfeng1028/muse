# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法，版本号按 [SemVer](https://semver.org/lang/zh-CN/)。


## [0.20.0] - 2026-10-26

### 新增
- 短信记录关联监控，关闭 v0.14.0 已知限制“短信记录无法按事件关联，sms_log 无 monitor_id”。
- 后端：sms_log 新增 monitor_id 列（v14 迁移，历史行默认 0）；新增 RecordSMSLogForMonitor，旧 RecordSMSLog 委托传 0，旧函数签名不变；分发时用 Target.MonitorID；接口 /api/sms/log 支持 monitor_id 参数，非法值返回 400“无效的监控 ID”，不带参数返回全部。
- 页面：筛选区加监控 ID 输入框，表格状态列后加监控列，无关联行显示破折号。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000）输出：多通，含 4 通正文 0 字作废（按口径缩小目标、改片段格式重发，无 429）。

### 测试
- 新增 store、handlers、web 三处监控筛选测试（store：监控 7 两条、9 一条、nil 查 3 条、指针 7 查 2 条、指针 9 查 1 条、旧行指针 0 查 1 条；handlers：monitor_id=5 返 1 条、abc 返 400、不带参数返 2 条；web：筛选输入、监控列头、参数拼接、渲染取值）；db_deep2 版本期望同步到 14。
- go vet 全洁；db、store、notify、handlers、web 五包合跑全绿。
- 真实服务冒烟（18220 端口隔离库）：种子 3 条；未过滤 total 3、monitor_id=5 total 1、abc 400；截图亲眼核对筛选框与监控列、旧行破折号、过滤后仅剩监控 5 一行；验收后服务按 PID 停掉、端口已关、隔离库与二进制与临时令牌已删。

## [0.19.1] - 2026-10-25

### 新增
- 短信记录页正文包进 <main class="container">：关闭 v0.19.0 保留的同类缺口（短信记录页仍无容器，筛选栏与表格拉满视口）。顶栏留在容器外、正文全部在容器内，不改任何 JS 与导航语义；容器口径与事件页同款 .container 规则，无新增样式表。个人资料页未动：它已有自有 .wrap 容器（1080px 居中），不算缺口。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000）输出：1 通即出 3 行断言标记（prompt 23819 / completion 93 / total 23912，无 429），编排按本包口径改写成 t.Errorf 式测试落仓，HTML 两处为编排机械插入。

### 测试
- 新增 internal/web/sms_log_container_test.go 1 例（容器标记齐全、表格与筛选在容器内、容器在 script 前闭合、顶栏在容器外）；与 v0.19.0 事件页测试合跑全绿，go vet 全洁。
- 真实服务冒烟（18296 端口隔离库）：/sms-log 200 且实取 HTML 含容器标记 1 处；截图亲眼核对 docs/screenshots/sentinel-v0191-smslog.png：容器计算样式 max-width 1100px、宽 1100px、左缘 170px 居中、内边距 16px，筛选输入框不再拉满视口，空表“还没有短信记录”为隔离库真实空态。验收后服务按 PID 停掉、端口已关、隔离库与二进制已删。

## [0.19.0] - 2026-10-25

### 新增
- 事件页正文包进 <main class="container">：关闭 v0.15.0 已知限制“事件页无 .container/.page 包裹，内容贴视口边缘、筛选框拉满宽”。顶栏留在容器外、正文（页头、筛选、表格、分页）全部在容器内，不改任何 JS 与导航语义；容器口径与总览页、快照页同一条 .container 规则（max-width 1100px、居中、16px 内边距），无新增样式表。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000）输出：首通正文 0 字（4000 全被推理占满，按口径缩小目标重发，429 通两次各等 90 秒，不计用量）；缩小后的第 2 通出 3 行断言标记（89 completion），编排按本包 design_v018 口径改写成 t.Errorf 式测试落仓，HTML 包裹两处为编排机械插入并经测试与真实服务核对。API 口径：首通 prompt 23940 / completion 4000 / total 27940（正文 0 字），第 2 通 prompt 23818 / completion 89 / total 23907。

### 测试
- 新增 internal/web/incidents_container_test.go 1 例（容器标记齐全、表格与筛选在容器内、容器在 script 前闭合、顶栏在容器外）；与 v015–v018 设计层及 style.css alert 测试合跑全绿，go vet 全洁。
- 真实服务冒烟（18295 端口隔离库）：/incidents 200 且实取 HTML 含容器标记 1 处，/api/incidents 200；截图亲眼核对 docs/screenshots/sentinel-v019-incidents.png：容器计算样式 max-width 1100px、宽 1100px、左缘 170px 居中、内边距 16px，筛选下拉不再拉满视口。截图里“加载失败”与空表是 setContent harness 下相对 /api/ 地址解析失败所致（真实服务 API 本身 200），非本轮回归；验收后服务按 PID 停掉、端口已关、隔离库与二进制已删。

### 已知限制
- 仅事件页包了容器，个人资料页与短信记录页仍无容器包裹，属同类既存差异，排期后续版本。

## [0.18.1] - 2026-10-25

### 修复
- style.css 尾部 .alert 规则补右括号：关闭 v0.15.0 起挂账的已知限制（文件此前以未闭合的 .alert 规则结尾，大括号 118 对 117，解析器会丢弃该规则）。改动仅此 1 行；全仓 HTML 均无 class="alert" 元素，故本修复不改变任何页面的可见样式，只恢复样式表有效性（此前截图 harness 把两表拼进同一个 style 块时被该截断吞掉设计规则的问题亦随之消除，但各页仍按独立样式表加载，行为不变）。
- 模型稿 1 通由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000）输出，即闭合后的 .alert 规则原文，编排核对后落仓。API 口径 prompt 23823 / completion 51 / total 23874，无 429。

### 测试
- 新增 internal/web/style_css_alert_test.go 1 例（大括号平衡、.alert 规则闭合且 padding 声明齐全、文件以闭合规则结尾）；go vet 全洁；internal/web 包全绿。
- 真实服务冒烟（18293 端口隔离库）：/incidents 与 /static/style.css 均 200，样式表大括号 118 对 118；验收后服务已按 PID 停掉，演示库与二进制已删。

## [0.18.0] - 2026-10-25

### 新增
- 投递页顶栏结构归一：关闭 v0.17.0 已知限制“两页顶栏结构仍不相同”。deliveries.html 的顶栏改用与 monitors.html 完全相同的三段式结构（logo-area + nav-links + user-area），内联顶栏 CSS 整段换成监控页同款数值（64px 白底顶栏、32px 内边距、logo-icon 蓝底 S、nav-links 28px 间距、user-area 管理员 + 头像）；旧 topbar-left / topbar-right / badge 顶栏标记全部删除。投递页导航链接目标保持自有（仪表盘 / 事件 / 投递队列 / 设置），只归一结构与样式，不改导航语义与任何 JS；状态徽标 badge-status 系列原样保留。v0.17.0 设计层的 .topbar-right a.active 规则对投递页不再生效（其激活态现走 .nav-links a.active，与监控页同一条规则，v017 文件本身未动）。
- 模型稿 4 通均由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000，每通一个小片段）输出，编排逐项核对后落仓（数值与监控页逐字一致）；第 3 通两次撞 429，各等 90 秒重发成功，不计用量。4 通 API 合计 prompt 95890 / completion 1028 / total 96918。

### 测试
- 新增 internal/web/design_v018_test.go 1 例（两页三段式顶栏标记与槽位顺序、投递页无旧顶栏残留、投递页自有导航链接齐全、归一后内联顶栏 CSS 齐全）；go vet 全洁；internal/web 包全绿。
- 真实服务冒烟（见本节视觉验收）：/monitors 与 /deliveries 均 200，截图亲眼核对两张，计算样式与归一规则一一对上；验收后服务已按 PID 停掉，演示库与二进制已删。

### 已知限制
- style.css 尾部 .alert 规则缺右括号（v0.15.0 已知限制）仍未动，排期后续版本。

## [0.17.0] - 2026-10-25

### 新增
- 前端美化设计层 internal/web/static/design-v017.css（值班日志本续篇）：关闭 v0.16.0 已知限制里的两页顶栏导航不统一缺口。两页均在 design-v016.css 之后引用本层。规则：监控页导航激活态文字改墨色 #1f2937、下划线改绿 #10b981；投递页导航激活态同款（墨色、600 字重、透明底、2px 绿下边框）；两页顶栏与投递筛选栏去阴影，筛选栏补 1px 细边 #e5e7eb（编排机械补一条，模型稿未含此条，如实记录）。
- 投递页导航激活项由行内 style 改为 class="active"，样式表层才能真正覆盖它（v0.16.0 留下的“行内 style 无法覆盖”至此闭合）；两页顶栏结构（监控页 logo-area/user-area、投递页 topbar-left/badge）仍各用各的既有结构，不动布局。

### 测试
- 新增 internal/web/design_v017_test.go 1 例（设计层标记与禁令、两页在 v016 之后引用本层、投递页激活项用 class 且无旧行内 style、监控页激活锚点）；go vet 全洁；internal/web 包全绿。
- 真实服务冒烟（18291 端口隔离库）：服务端内置种子监控 2 条（示例站点 https://example.com、示例 TCP 端口 example.com:80，均已禁用）+ 本轮直插投递 1 条（示例站点 down、已失败、2/8 次、connection refused），/monitors 与 /deliveries 均 200；截图亲眼核对两张：监控页激活项墨色 + 绿下划线、顶栏无阴影，投递页激活项墨色 + 2px 绿下边框、筛选栏无阴影 + 细边、失败徽标与重试按钮齐全，计算样式实证与规则一一对上。验收后服务已按 PID 停掉，演示库、二进制与服务端备份文件已删。

### 已知限制
- 两页顶栏结构仍不相同（监控页有 logo-area/user-area，投递页有 topbar-left/badge），只统一了激活态与阴影，未做顶栏结构归一。


## [0.16.0] - 2026-10-25

### 新增
- 前端美化设计层 internal/web/static/design-v016.css（值班日志本续篇）：把 v0.15.0 已知限制里排期后续的 monitors.html 与 deliveries.html 并入同一视觉口径，只覆盖、不改原内联样式与任何 JS 逻辑；两页均在内联 `<style>` 块之后以 `<link>` 引用本层。规则 6 条（模型分两通小稿出正文，编排逐项核对选择器真实存在后落仓）：监控表表头纯白底、取消大写、13px/600 墨色，表体行间只靠 1px 底边 #e5e7eb 分隔，卡片去阴影改纯白底 + 1px 细边，投递页页头 20px 加粗 + 下方 1px 细线，投递表表头同款台账样式。
- 投递页真修：`<script src="/static/app.js">` 去掉 `defer`。原因为行内脚本在解析时就调 `loadDeliveries()`，而带 `defer` 的 app.js 要等解析完才执行，此时 `api` 尚未定义，首屏会一直卡在“加载中”，只有手动点刷新才好；去掉后 app.js 先于行内脚本执行，首屏直接出数据。

### 测试
- 新增 internal/web/design_v016_test.go 1 例（设计层标记与禁令、两页在内联 `<style>` 块之后引用本层、选择器锚点真实存在、app.js 不带 defer）；go vet 全洁；internal/web 包全绿。
- 真实服务冒烟（18281 端口隔离库）：种子监控 2 条（示例站点、示例 TCP 端口）+ 种子投递 1 条（示例站点 down、已失败、2/8 次、connection refused），/monitors 与 /deliveries 均 200，API 在 Bearer 鉴权下返回种子数据；截图亲眼核对两张：监控表表头白底无大写、卡片无阴影 + 1px 边、投递页头 20px 加粗、投递表头白底无大写、失败徽标与重试按钮齐全，计算样式实证与规则一一对上。验收后服务已按 PID 停掉，演示库、编译产物与服务端备份文件已删。

### 已知限制
- 两页顶栏导航仍各用各的样式（监控页蓝字激活、投递页蓝灰底激活），其中投递页激活项是行内 style，样式表层无法覆盖，留待后续改 HTML 时统一；本轮未用强制优先级写法硬压。
- 监控页顶栏阴影与投递页筛选栏圆角阴影仍是原内联样式，未在本层覆盖，视觉上与台账页一致但未完全归一。

## [0.15.0] - 2026-10-25

### 新增
- 前端美化设计层 internal/web/static/design-v015.css（值班日志本）：在 style.css 之后引用，只覆盖、不改原样式表与任何 JS；页头 20px 加粗 + 下方 1px 细线分隔；表格改台账行（表头取消大写转换、纯白底、取消斑马纹、行间只靠 1px 底边分隔）；事件详情行底色 #f9fafb、左缘 3px 琥珀实线、内边距 16px；导航激活项下边框加粗到 3px 绿色信号；统计数字 28px 加粗等宽数字。引用 style.css 的 6 页（总览/事件/个人资料/短信记录/快照/状态）均在 style.css 之后引用本层。
- 事件页与短信记录页的 bare <nav> 补 class="nav"，与总览/个人资料/快照页一致，使共享顶栏规则与激活态真正落到这两页（此前两页导航链接未走 .nav 样式，呈默认蓝色）。

### 测试
- 新增 internal/web/design_v015_test.go 1 例（设计层标记与禁令、6 页引用顺序、两页 nav class）；go vet 全洁；真服务冒烟（18271 端口隔离库）：死链检查失败开事件 1 条，事件页真实数据 1 行，点击展开详情 9 行齐全（恢复检查“未恢复，无恢复检查”、通知记录“暂无通知记录”属实）；截图 docs/screenshots/sentinel-v015-incidents.png 与 sentinel-v015-incidents-expanded.png 亲眼核对：导航绿下划线、台账表头、详情琥珀左缘均实证可见。

### 已知限制
- style.css 尾部 .alert 规则缺右括号（既存截断，本轮未动原文件）：在真实部署里设计层是独立样式表，不受影响；但把两表拼进同一个 <style> 块的截图脚本会把设计规则吞掉，截图 harness 已改成分开的两个 <style> 块，属实记录。
- monitors.html 与 deliveries.html 用内联样式，本层不覆盖，仍与设计层页面风格不一致，排期后续统一；事件页无 .container/.page 包裹，内容贴视口边缘、筛选框拉满宽，属既存结构，本轮未改。

## [0.14.0] - 2026-10-25

### 新增
- 事件详情端点 GET /api/incidents/{id}（需鉴权，与列表端点同款）：返回 incident（id、监控、开始/恢复时间、持续、触发原因）+ recovery_check（事件开始后最早的一次成功检查：checked_at、ok、status_code、latency_ms、error；未恢复时为 null）+ deliveries（事件窗口内 monitor_id 相同、event 为 down/recovered 的 webhook 投递记录，按 id 升序、上限 200，空时为空数组；不返回 payload 全文）。无数据库迁移，只用已存在的 checks 与 webhook_deliveries 表；恢复检查的口径是“开始之后最早成功检查”，通知记录的窗口是 started_at 至 ended_at（未关闭事件以上限为空）。
- 事件页展开详情时按需拉取该端点，追加“恢复检查”与“通知记录”两行（全部用 textContent；未恢复显示“未恢复，无恢复检查”，无记录显示“暂无通知记录”；拉取失败静默保留原有 7 字段，不打断展开）。

### 测试
- 新增 internal/store/incident_detail_test.go 2 例（已关闭事件恢复检查与窗口内投递过滤、未关闭事件恢复为 null 且投递为空数组、不存在事件为 sql.ErrNoRows）与 internal/handlers/incident_detail_test.go 1 例（200 且 recovery_check 字段齐全、不存在 404、非法 id 400）与 internal/web 静态标记测试 1 例；go vet 全洁；真服务冒烟（18261 端口隔离库）：死链检查失败开事件 1 条，改健康目标再检查后事件关闭、详情返回 recovery_check 状态码 200、延迟 6 毫秒，deliveries 为空（冒烟未配 webhook，属实）。

### 已知限制
- 短信记录（sms_log 表）没有 monitor_id 字段，无法按事件窗口关联，故本轮通知记录只含 webhook 投递，不含短信；如需短信关联须先给 sms_log 加 monitor_id 迁移，排期后续。

## [0.13.0] - 2026-10-25

### 新增
- 事件页 internal/web/static/incidents.html 点击数据行展开详情行（关闭 docs/TECH_DEBT_GAP_incidents.md 缺口二“点击行展开详情不存在”）。数据行加 incident-row、tabindex、aria-expanded、title“点击查看详情”；详情行 class incident-detail、单列 colSpan=6；详情只用 /api/incidents 已返回字段：事件 ID、监控、开始时间、恢复时间（未恢复显示“未恢复”）、持续（复用 fmtDuration）、状态（已恢复/未恢复）、触发原因（空值显示“无”）；同一时间只展开一行；Enter/Space 键盘同样切换；筛选/翻页重载后详情默认关闭；副标题追加“点击一行可展开详情。”。

### 测试
- 新增 internal/web/incidents_detail_test.go 4 例（静态标记/7 字段标签/单开与键盘标记/副标题提示），go test 全绿；无新 API、无后端改动、无假数据。Go 静态测试只断言页面静态标记齐全，浏览器内真实点击行为由真服务冒烟与截图验收。

## [0.12.0] - 2026-10-25

### 新增
- 短信告警通道正式发版：mock/aliyun/tencent 三发送器、目标级 sms_phones 优先、全局 SENTINEL_SMS_PHONES 回退、手机号格式校验、aliyun/tencent 模式缺配置启动即报错退出；短信记录持久化（sms_log 表）与查询 API GET /api/sms/log、控制台页 /sms-log。
- .env.example 补齐腾讯云短信 7 个变量，模式注释改成 mock/aliyun/tencent。

### 修复
- main.go 通知器接线缺失：Notifier 字面量从未设置 SMSLogger，线上短信只进 mock 内存、永不写入 sms_log 表；抽出 buildNotifier(cfg, st) 并加 SMSLogger: st，真实告警的短信记录现可落库查询。
- /sms-log 页部署后 404：原 handler 用 http.ServeFile 加工作目录相对路径，Docker 运行镜像里只有二进制没有源码树；改成与其他页一致的内嵌资源 serveStaticFile。
- /sms-log 页有记录也渲染不出：页 JS 按 data.rows/data.items 与 r.content 取数，真实 API 返回 {"logs":[...]} 且字段是 message；改成 data.logs 与 r.message；并把 /sms-log 加进鉴权精确白名单（与 /monitors、/incidents、/deliveries、/snapshots 一致），fetch 接上 sessionStorage sentinel_token（与 monitors.html 同款）。

### 测试
- 新增 sentinel/main_test.go 2 例与 internal/handlers/sms_log_page_test.go 1 例，全绿；go vet 全洁；真服务冒烟：死链监控手动检查失败后 incident open 1 条、/api/sms/log 出现 mock/sent 记录 1 条、修后 /sms-log 页 200。

## [0.11.1] - 2026-10-24

### 新增
- GET /api/incidents 新增 status 查询参数，取 open 表示未关闭事件（ended_at IS NULL）、closed 表示已恢复事件（ended_at IS NOT NULL）、不传表示全部、非法值返回 400。
- 控制台事件页新增状态下拉框（全部状态/进行中/已恢复），切换后回到第 1 页重新加载。
- Store 层新增 CountIncidentsByStatus 与 ListIncidentsPagedByStatus 函数。

### 修复
- 补齐 v0.8.0 曾承诺但未落地的事件页状态筛选，之前事件页只能按监控筛选。

## [0.11.0] - 2026-10-24

### 新增
- 数据库迁移 v13：新建 `status_snapshots` 表用于持久化存储快照，`status_pages` 表新增 `snapshot_schedule` 列（支持 off/daily/hourly，默认 off）。
- 快照归档与定时生成相关 API（均需鉴权）：
  - `POST /api/status-pages/{id}/snapshots`：生成并归档快照，返回 201 及 id/created_at/size_bytes。
  - `GET /api/status-pages/{id}/snapshots`：获取快照列表，limit 默认 50 上限 200。
  - `GET /api/status-pages/{id}/snapshots/{sid}`：下载指定快照的 HTML 附件。
  - `DELETE /api/status-pages/{id}/snapshots/{sid}`：删除指定快照，返回 204 且幂等。
  - `PUT /api/status-pages/{id}/snapshot-schedule`：设置定时计划，非法参数返回 400。
  - 跨页访问快照返回 404，原 `POST /api/status-pages/{id}/snapshot` 下载接口保持不变。
- 定时生成能力：调度器每 tick 结束后经 5 分钟节流扫描一次，对 schedule 为 daily（24h）或 hourly（1h）的页面自动生成快照（generator 为 "schedule"），生成后按 `SENTINEL_SNAPSHOT_RETAIN` 裁剪旧快照，生成失败仅记日志不中断其他页面。
- 控制台新增「快照归档」页面（/snapshots），支持列出全部状态页、设定时计划、立即生成、快照列表下载与删除，导航栏新增入口。

### 修复
- 关闭 v0.8.3/v0.8.4 已知限制：快照为下载附件形态，未做服务端持久化与定时生成。现已支持服务端持久化及定时生成。

### 运维
- 新增环境变量 `SENTINEL_SNAPSHOT_RETAIN`（默认 30），用于控制每个状态页保留的最新快照数量，定时生成后按此值裁剪旧快照。

## [0.10.1] - 2026-10-23

### 修复
- 并发恢复通知去重：`CloseOpenIncident` 改为返回 `(closed bool, err)`，调度器仅在真正关闭了一个未关闭 incident 时才发送 `recovered` 通知。修复手动检查与调度 tick 并发恢复时重复发送恢复通知的竞态（v0.8 已知限制）。`go test -race` 下 20 并发恢复仅 1 次通知；`go test ./...` 全绿。

## [0.10.0] - 2026-10-22

### 新增
- 公开 SLA 徽章：`GET /api/status/{slug}/badge.svg` 返回 shields.io flat 风格 SVG，可直接嵌入 README。右侧文案：全部 up 显示 `up · 99.95%`（当月平均可用性）；任一最近检查 down 显示 `down`；无检查数据则 `unknown`。`Content-Type: image/svg+xml`，免鉴权（公开路由）。
- 测试：`sentinel/internal/handlers/status_badge_test.go` 3 例（未知 slug 404、无检查数据 unknown、空页面 unknown），`go test` 全绿。

## [0.9.0] - 2026-10-20

### 新增
- 一键发布公开状态页：`POST /api/status-pages/{id}/publish` 将状态页静态站原子发布到磁盘目录（默认 `data/published/<slug>/`，含 `index.html`、`manifest.json` 与 `history/`，版本历史保留 10 版）；`POST /api/status-pages/{id}/publish/rollback` 回滚到上一版本；`GET /api/status-pages/{id}/publish` 查询发布状态。发布失败时旧版本不受影响。
- 可用性画像 v1：`GET /api/monitors/{id}/profile` 新增 `jitter_score`（0~100，up/down 翻转频率）、`jitter_level`（稳定/轻微波动/波动明显/频繁抖动/数据不足）、`timeline`（近 30 天故障时间线）；`store.MonitorPortrait` 聚合；控制台 profile 页新增"稳定性画像"面板（抖动评分 + 故障时间线）。
- SLA 月报 v3：`MonthlySLA` 新增 `attribution`（故障归因计数：timeout/dns/connection/cert/keyword/http_5xx/other）与 `attribution_pct`（占比，1 位小数）；`GET /api/monitors/{id}/sla.html?month=YYYY-MM` 导出中文 HTML 月报（含归因表与占比条形）；`docs/SLA_METHOD.md` 新增第 7 节。
- 检查器纵深：monitor 新增 `cert_warn_days`（证书过期预警阈值天数，0=不预警）、`keyword`（关键字断言）、`keyword_mode`（exact/ignorecase/regex）；证书剩余天数低于阈值则检查失败（文案"证书将于 N 天后过期，低于预警阈值 D 天"）；DB 迁移 version 12；`POST/PUT /api/monitors` 支持三个新字段并校验（cert_warn_days 0~365、keyword 最长 500、keyword_mode 非法 400、regex 模式预编译）。
- 测试：`go test ./...` 全绿；新增 publish E2E（生成→断言内容→增量更新→回滚→发布失败旧版本不受影响）、画像/归因/证书/关键字单测、失败注入（过期证书、关键字 miss、非法正则、发布目录不可写）。

## [0.8.4] - 2026-10-20


### 修复
- `POST /api/monitors` 创建时忽略 `is_public`（0.8.3 已知限制第一条）：现在读取请求体 `is_public` 字段（0/1，不传按 0；非法值返回 400）。`PUT /api/monitors/{id}` 未传 `is_public` 时保留原值，不再静默重置。控制台新建表单新增"公开（状态页可见）"复选框，列表中公开项显示"公开"徽标。

### 新增
- `GET /api/incidents` 分页参数新增 `per_page`：优先级 `per_page` > `page_size` > `limit`；取值钳制 1~100，非法值回退默认 20；`page` 非法或 <1 按 1，超大页码返回空 `items` 不报错。响应契约不变（`{items, total, page, page_size}`）。

### 已知限制
- 快照为下载附件形态，未做服务端持久化/定时生成（排期后续）。

## [0.8.3] - 2026-10-19

### 新增
- SLA 月报 v2（`MonthlySLA`）：新增 `mttr_sec`（仅已关闭事件的平均恢复时长）、`severity`（按单事件宕机时长分级 P1>=30min/P2>=5min/P3<5min，未关闭事件按查询时刻估算参与分级）、`open_incidents`（区间内开始且仍未关闭的事件数）；旧字段语义不变。口径文档 `docs/SLA_METHOD.md`（uptime=检查成功占比、无检查记 100 的假设声明、downtime/open 估算、MTTR 定义域、分级阈值理由、UTC 归属）。
- 状态页一键发布静态快照：`POST /api/status-pages/{id}/snapshot`（需鉴权），生成单文件 HTML（内联 CSS、零外部资源）作为附件下载，含总览横幅（全部正常/N 个服务异常/部分未知）、每 monitor 状态 pill + 30 天可用性 + 最近检查/延迟 + 90 天每日可用性色条；深色主题与 accent_color 透出；全部文本转义。
- 检查器 context 传播：`checker.CheckWithRetryCtx(ctx, ...)`（HTTP `req.WithContext`、TCP `DialContext`、退避等待可被 ctx 中断、首次 attempt 前取消返回 Ok=0 的 Check）；`CheckWithRetry` 改为薄封装，语义不变；`scheduler.runOne` 与 `Scheduler.CheckNow(ctx, ...)` 接入 ctx（`handleCheckNow` 传 `r.Context()`）。

### 实测
- `go test ./...` 全绿（含 -race：store/checker/scheduler）；handlers 142 测试通过。
- 真实服务冒烟：18231 端口起服，2 监控（1 up/1 down）各 CheckNow 3 次 → 状态页快照 200、180 个 data-day 条、Content-Disposition 附件、body 零 http(s):// 外部引用；截图 `docs/screenshots/snapshot-dark-20261019.png` 亲眼验收通过（深色主题、双 pill、色条正常、无 AI 味）。
- ctx 中断实测：3s sleep 目标在 100ms/200ms 取消后均 2.5s 内返回；完整退避 15.5s 被中断到 <5s。

### 已知限制
- 快照为下载附件形态，未做服务端持久化/定时生成（排期后续）。

## [0.8.2] - 2026-10-19

### 修复
- migration v11：部分唯一索引 `uq_webhook_deliveries_dedup ON webhook_deliveries(monitor_id, url, event, payload) WHERE status IN ('pending','retrying')`，关上 deliveries 并发幂等缺口（0.8.1 已知限制第一项）。
- `EnqueueDelivery` 改为原子写法：`INSERT OR IGNORE` + 冲突时回查已存在行 id；16 goroutine 同 key 并发只插一行、返回同一 id。去重范围仍是 pending/retrying 行，已完成（done）的行不受影响，语义不变。
- wecom `SendMarkdown`：URL 非法等请求构造失败统一包装为"企业微信 Webhook 发送失败"前缀，与发送失败同一口径（测试 TestWeComSendMarkdown_InvalidURL 要求）。
- 测试修正 3 处（源码无问题）：`sms_log_dispatch_test.go` 两个用例补 `Channels: []string{"sms"}`（原来默认走 webhook，短信路径根本没执行）；`TestDailyBreakdown_IncludesEmptyDaysAndBoundaries` 浮点比较改 1e-9 容差；`TestMonthlySLA_WithClosedAndOpenIncident` 的未关闭 incident `started_at` 改为窗口内的 `"2024-06-04T00:02:00Z"`（原来用了 now，落在 2024-06 报告窗口外）。

### 实测
- 待本轮验证后填写。

### 已知限制
- 0.8.1 挂账的 deliveries 并发幂等缺口与 6 个失败测试已在本轮处理；剩余 1 个 pre-existing 失败待定位。

## [0.8.1] - 2026-10-19

### 新增
- migration v10：部分唯一索引 `uq_incidents_open_monitor ON incidents(monitor_id) WHERE ended_at IS NULL`，含历史重复 open 数据去重。
- `OpenIncident` 幂等化：签名变为 `(id, created, err)`，底层 `INSERT ... ON CONFLICT DO NOTHING`，返回 created 标志。
- `record()` 仅在真正新建事件时发 down 通知，重复并发不再重复告警。

### 实测
- 复现测试 `TestManualAndTickConcurrent_DuplicateOpenIncident` 先红（open incident 数量 = 23，期望 1）后绿。
- 新增 8 个测试全部通过（1 复现 + 4 store 幂等/索引/重开 + 3 scheduler 回归）。
- `go vet` 全洁；经手文件 gofmt 全洁。
- 真实服务 30 并发冒烟：GET /api/incidents 恰好 1 条 open，无重复。
- 恢复→重开闭环正常：关闭后 ended_at 非空，downtime_sec=432；切回 down 后新开事件（共 2 条，1 open）。

### 已知限制
- Go 工具链旧，依赖复扫仍挂账（46 个标准库漏洞根因，排期升级后复扫）。
- store/notify 包 7 个 pre-existing 测试失败（已在干净树复现，与本轮无关，排期修）。
- deliveries 表存在同类并发幂等缺口（TestEnqueueDeliveryConcurrentSameKey 失败），排期按本轮 incidents 方案同理修复。

## [0.8.0] - 2026-10-17

### 新增
- incidents.html 事件页改接真实 API：删除写死的 MONITORS/INCIDENTS 常量与残缺 JS，列表数据来自 GET /api/incidents（monitor_id 筛选在服务端完成，limit=100），筛选下拉由 GET /api/monitors 填充。
- 事件列表新增"状态"列：进行中/已恢复 pill；未恢复事件的持续时长按 now-started_at 实时计算。
- 事件页新增监控筛选与状态筛选。
- 事件行支持点击展开详情行，展示完整错误文本与监控档案链接。
- 事件列表加入客户端分页，每页 20 条。
- 事件页加入空态（图标 + 文案 + 去监控列表链接）与错误态（带重试按钮）。
- 新增 scripts/smoke_incidents.sh：down→recovered 事件闭环冒烟，断言 open 态 ended_at/downtime_sec 为 null、recovered 态字段齐全；幂等可重跑，运行后自清理。
- 新增测试 TestListIncidentsOpenEndedNull，覆盖 /api/incidents 的 open/closed 两种 JSON 契约。

### 实测
- incidents.html 事件页改接真实 API（待验收填写）
- 状态列与持续时长实时计算（待验收填写）
- 监控筛选与状态筛选（待验收填写）
- 点击行展开详情行（待验收填写）
- 客户端分页（待验收填写）
- 空态与错误态（待验收填写）
- scripts/smoke_incidents.sh 事件闭环冒烟（待验收填写）
- TestListIncidentsOpenEndedNull（待验收填写）

### 偿还排期
- 关闭 v0.6/v0.7 对照报告挂账的 incidents.html 模拟数据债：事件页改接真实 API，相关挂账条目结清。

## [0.7.0] - 2026-10-17

### 新增

- **入队限流**：`internal/notify/limiter.go` 令牌桶（满桶启动）；`SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS`（默认 20，0=禁用）/`_BURST`（默认 40），非法启动 fail-fast；超限丢弃+计数+warn 日志（后台入队无 HTTP 上下文可 429）
- **投递熔断**：`internal/notify/circuit.go`，按 host 独立熔断（闭合→断开→半开→闭合，半开单探测）；`SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD`（默认 5）/`_OPEN_TIMEOUT_SEC`（默认 300）；与指数退避/手动重试正交
- **指标**：`sentinel_webhook_enqueue_rejected_total`、`sentinel_webhook_breaker_state{host}`（0/1/2）进 `/api/metrics`
- **告警**：`prometheus/rules/sentinel.yml` 8 条（新增 SentinelWebhookEnqueueRejected、SentinelWebhookBreakerOpen）
- **文档**：`docs/OPERATIONS.md` 第 12 章（限流熔断调参）；发版对照报告 `docs/PRODUCTION_CHECKLIST_REPORT_v0.7.md`

### 实测

- `go test` 190/190（含 -race 并发），`go vet` 全洁
- 真实冒烟：必失败 sink 下 2 次连续失败即熔断断开；10 死目标洪峰下限流拒绝 8 次；sink 恢复后半开探测成功、熔断闭合、投递 done

### 关闭排期

- v0.6 排期的入队限流、投递熔断已交付（§5 限流/超时/熔断：部分通过 → 通过）

### 已知限制

- Go 工具链 go1.23.4 过旧（46 个标准库漏洞根因），排期升级后复扫
- `incidents.html` 模拟数据债仍挂账

## [0.6.0] - 2026-10-17


### 新增

- **Prometheus 告警规则**：`prometheus/rules/sentinel.yml`，6 条（实例 down / 调度停滞 / 队列积压>50 / 投递失败率>20% / 检查失败激增 / 自身 API 5xx 率>5%），配套 `prometheus/prometheus.yml` 抓取示例（含 /api/metrics 鉴权说明）；`docs/OPERATIONS.md` 新增第 10 章（阈值依据、静默/值班建议）
- **队列积压指标**：`GET /api/metrics` 新增 gauge `sentinel_webhook_queue_backlog{status="pending"|"retrying"}`（`internal/metrics.RenderQueueBacklog` + handleMetrics 追加，DB 查询失败只记日志不中断抓取）
- **依赖漏洞扫描**：`scripts/depscan.sh`（go list 取模块 → OSV querybatch → govulncheck 优先；退出码 0/1/2；报告 `docs/dependency-scan-YYYYMMDD.json`）
- **真实负载验证**：`scripts/load_check.sh`（8 假目标 + webhook sink，采集检查延迟 p50/p99、事件正确性、故障时队列积压/排空；报告 `docs/load-test-YYYYMMDD.md`）
- **测试**：4 个新增（规则 YAML 回归 `prometheus/rules/sentinel_rules_test.go`、积压 gauge 精确输出、积压计数 pending+retrying）；`go test` 141/141 全过

### 实测

- depscan：23 个模块，OSV 3 个 + govulncheck 46 个 = 49 个漏洞（全在 Go 标准库 go1.23.4 与 x/mod、x/sys，无第三方业务依赖漏洞）
- load_check：40 轮检查，p50=6.0ms、p99=14.8ms；4 down 事件全对、无误报；webhook 4/4；积压峰值 2 并排空；73s
- fault-drill.sh：13/13（34s）

### 已知限制

- 46 个标准库漏洞源于工具链 go1.23.4 过旧，排期 v0.7 升级 Go 工具链后复扫
- 入队侧限流、投递侧熔断仍未做（v0.5 已排期），继续排期 v0.7
- `incidents.html` 模拟数据债（v0.4.0 记）仍挂账

## [v0.4.0] - 2026-10-16

### 新增

- **Webhook 持久化投递队列**：告警产生时只做 SQLite 入队（`webhook_deliveries` 表，迁移 v5），后台 worker 每 15 秒扫一次到期任务，按指数退避（基数 60 秒，`base*2^(attempt-1)+jitter`）重投；状态 pending（待投递）/retrying（重试中）/done（已送达）/failed（已失败）；默认最多投 8 次，失败自动标 failed，不再丢告警
- **投递队列管理 API**：`GET /api/alerts/deliveries`（按 status/monitor_id/limit 查）、`POST /api/alerts/deliveries/{id}/retry`（手动重投，仅 failed/retrying 可重试）
- **投递队列控制台页** `/deliveries`：状态筛选、尝试次数/下次重试/最近错误一览，失败的可一键手动重投
- **配置**：`SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS`（默认 8）、`SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC`（默认 60）、`SENTINEL_WEBHOOK_QUEUE_TICK_SEC`（默认 15）

### 变更

- webhook 渠道改为异步投递：告警产生时只入队，不再阻塞等待投递结果；smtp/企业微信渠道仍同步发送
- 同一告警事件重复入队自动去重（按 monitor+url+event+payload）

### 已知限制

- v0.2.0 的"Webhook 仅重试 3 次，失败后只写日志，不做持久化队列重投"已解决，删除该条
- 分布式多实例未支持，仅单实例部署（SQLite，worker 单实例运行）

## [v0.3.0] - 2026-10-16
### 新增

- **状态页主题**：每个状态页可配浅色/深色/自定义主色（`accent_color` #rrggbb），存 DB（迁移 v3，老库自动补列）；`GET /api/status/{slug}` 透出主题；公开页按主题渲染，访客可用页面上的切换器预览浅色/深色/跟随站点
- **订阅通知**：公开状态页支持访客邮箱订阅（`status_subscriptions` 表，迁移 v4）；订阅需点击确认邮件里的 token 链接（防滥用），退订走 token 链接；monitor 发生 down/recovered 事件时扇出邮件给已确认订阅者（同一邮箱多页去重）
- **配置**：`SENTINEL_PUBLIC_URL`（可选）作为订阅邮件中确认/退订链接的基地址，为空用相对路径
- **API**：`PUT /api/status-pages/{id}/theme`、`POST /api/status/{slug}/subscribe`、`GET /api/status/{slug}/confirm`、`GET /api/status/{slug}/unsubscribe`、`POST /api/status/{slug}/unsubscribe`

## [v0.2.0] - 2026-10-13

### 生产级改造

- **结构化日志**：全量切到 `slog`，JSON 输出，字段固定，业务字段按需附加。
- **request_id**：HTTP 中间件为每个请求生成 request_id，贯穿 handler 和下游日志。
- **健康探针**：新增 `/healthz`（存活）和 `/readyz`（就绪，检查 DB 和调度器）。
- **优雅关闭**：收到 SIGINT/SIGTERM 后停收新请求，等 inflight 检查完成再退，带超时兜底。
- **Prometheus 指标**：新增 `/api/metrics`，暴露 monitors_total、checks_total、check_duration_seconds、check_failures_total、incidents_open、http_requests_total。
- **DB 迁移版本化**：引入 `schema_version` 表，v1→v2 幂等迁移，启动自动执行。v2 新增 `users`、`status_pages` 表，`monitors` 增加 `is_public` 列。
- **检查重试**：失败按指数退避重试，带 jitter，上限由 `SENTINEL_CHECK_RETRY_MAX` 控制。
- **失败注入测试**：覆盖 DNS 失败、连接超时、非 2xx 响应、DB 写失败等路径。
- **配置启动校验**：所有环境变量集中校验，不合法直接退出并打印原因。
- **API Token 鉴权**：`Authorization: Bearer <token>` 校验，401 统一响应。
- **tenant / user**：v2 引入 `users` 表（id/username/token_hash/created_at），为多用户场景预留。
- **自动备份 + 一键恢复**：按周期自动备份，保留 N 份；新增 `-restore` 参数，恢复流程已实测。
- **docker-compose**：一键部署，端口 8200，数据卷、备份卷、资源限制（1 CPU / 512MB）、日志轮转全部配好。
- **OPERATIONS.md**：运维手册，覆盖部署、配置、备份恢复、升级、可观测性、token 管理、排障、资源限制。

### 灵魂功能

- **站点健康档案** `/profile?id=N`：7/30 天可用性、延迟 p50/p95/p99、30 天每日可用性柱状图、月度 SLA，一页看全。
- **月度 SLA**：`GET /api/monitors/{id}/sla?month=YYYY-MM`，返回可用性、检查数、宕机事件数、总宕机时长、SLA 目标 99.9%、是否达标。
- **公开状态页** `/status/{slug}`：对外展示，无需登录，展示各 monitor 状态、30 天可用性、最近检查时间。配套 `POST /api/status-pages`、`GET /api/status-pages`、`POST /api/status-pages/auto` 三个接口。

### 已知限制

- 分布式多实例未支持，仅单实例部署（SQLite）。
- Webhook 仅重试 3 次，失败后只写日志，不做持久化队列重投。
