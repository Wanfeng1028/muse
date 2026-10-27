# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法，版本号按 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.32.0] - 2026-10-27

### 新增

- 分组延迟趋势：Store 层 GroupMonthlyLatency（单月分组聚合：组内成功检查延迟的 p50/p95/p99、均值、成功检查数、监控数、最慢监控）与 GroupLatencyTrend（复用既有 shiftMonth 逐月聚合，月份按时间顺序排列；months 取值 1~12、非法 endMonth/months 报错；分组不存在报错）；API（均需鉴权）GET /api/groups/{id}/latency/trend?end=YYYY-MM&months=N（end 缺省当月、months 缺省 6、非法 end/months 返回 400、不存在的分组返回 404）、GET /api/groups/{id}/latency/trend.html（中文 HTML 导出：分组延迟趋势标题、逐月表、p95 延迟条形，条形宽度按窗口内最大 p95 归一化）；控制台页 /group-latency-trend（分组下拉、截止月份选择、3/6/12 个月选择、总览卡片、逐月表、p95 延迟条形、导出 HTML 链接），18 个既有控制台页导航末尾加分组延迟趋势链，/group-latency-trend 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：只统计组内成员、ok=1 的成功检查，失败检查与组外监控不计入分位与均值；空月 p50/p95/p99/均值均为 0、成功检查数为 0、最慢监控为空；最慢监控取当月有成功检查的成员中 p95 最大者、并列取先遇到；监控数为组成员数；月份窗口用 RFC3339 起止（与全站延迟趋势一致）；分位复用既有 percentileLinear 线性插值。
- 无 schema 变更、无新环境变量。

### 测试

- 新增 internal/store/group_latency_trend_test.go（空组 3 个月：起止月份与空月零值与非法 months/endMonth/月份报错与不存在分组报错；双月：组内快 [100,200]、组内慢 [1000,1000]、组外 [5000,5000] 得 2 月 p50 600、p95 1000、p99 1000、均值 575、总数 4（组外未计入）、最慢为组内慢，3 月 [300,400,500] 加一条 9999 失败检查得 p50 400、p95 490、p99 498、均值 400、总数 3（失败检查已排除）、最慢为组内快；空组单月零值）、internal/handlers/group_latency_trend_test.go（JSON 的 group_id/group_name/end_month/months 与不存在分组 404 与非法 months/end 的 400、HTML 的 200 与“分组延迟趋势/组名/p95 延迟条形”字样与不存在分组 404 与非法 end 400）、internal/web/group_latency_trend_test.go（分组延迟趋势页 16 个标记与标记顺序、失败路径定义顺序、18 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包为既存最慢包，首跑 242.250 秒、最终代码状态重跑 240.796 秒）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18502 端口，SENTINEL_TICK_SEC=60；隔离库与隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建分组 1 号“核心业务”；新建组内 UP 监控 3 号（本地 200 服务）与组内 DOWN 监控 4 号（127.0.0.1:9 拒绝）加入分组，另建组外 UP 监控 5 号不加入；各 CheckNow 2 次后 GET /api/groups/1/latency/trend?end=2026-10&months=2 返回 9 月空月 0 检查/零延迟/监控数 2、10 月成功检查数 2（组内 DOWN 的失败检查与组外 UP 的成功检查均未计入）、最慢监控为冒烟UP；无鉴权 401、months=0 与 end=2026-13 均为 400、不存在的分组 404；latency/trend.html 含“分组延迟趋势”与“p95 延迟条形”；/group-latency-trend 页 200 且含全部标记；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 两次冒烟运行的 10 月延迟值不同（首跑 p50/p95/p99/均值均为 14.00/20.30/20.86/14.00，复拍为 6.50/9.65/9.93/6.50），系本地 200 服务实测延迟抖动，非口径变化。

### 视觉验收

- 截图 docs/screenshots/group-latency-trend-v032.png 亲眼核对——导航 19 链齐全且分组延迟趋势 active、控件（核心业务、October 2026、6 个月、查看、导出 HTML 版）、卡片（分组核心业务、截止月份 2026-10、成功检查总数 2）与逐月行（5–9 月 0.00、10 月 6.50/9.65/9.93/6.50、2 检查、监控数 2、最慢冒烟UP）及 p95 条形（10 月蓝色满格 9.65 ms、空月灰底 0.00 ms）均与 API 返回一致、无“加载失败”。
- 截图 harness 说明：按 v0.31.0 模式（setContent 内联样式与 app.js、app.js 的 sessionStorage 取 token 桩化为空串、页面脚本的 /api 改写为绝对地址并经 route 代理回真实服务，路由层注入冒烟 stub token、OPTIONS 预检直接回 200 并补 CORS 头），该改写仅限截图环境，产品代码未动。调试实证两处页面 bug 均由冒烟/截图暴露并已修复：① /api/groups 返回 {"items": [...]} 而非裸数组，选项加载原稿遍历 data 本身抛错致下拉为空（已改 data.items）；② 逐月行模板误用 m.slowest_monitor，API 字段为 slowest_monitor_name，致最慢监控恒显示“—”（已改名）。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night12_sentinel_call.py（令牌经 SSH 现取、只进子进程内存、不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，每次调用用量均已捕获记账，失败重试单独立行记账）；Go 代码、测试、页面均为小片段逐字输出口径；编排侧机械工作：路由与鉴权精确名单接线、18 页导航链机械追加（保留各页原行首缩进）、新页面 head/导航与全站页原文对齐（模型初稿编造了另一套导航）、Web 测试稿 staticFS 改既有 FS 符号、Handlers 渲染函数字段名修正（模型稿误用 P50/P95/Avg/SuccessCount/SlowestMonitor 短名）、Store 测试稿 %d 改 %v（float64 动词）、README/CHANGELOG 事实性文字；Handler 值测试一稿因收尾时间砍掉（数值已由 Store 测试覆盖，Handler 层保留 JSON+HTML 两稿）。
- 平台层现象：Handlers 整稿一次 reasoning-only 空响应（16000 上限占满，改拆小稿 + 骨架照抄后成功）；页面骨架照抄稿一次 reasoning-only 空响应（16000 上限占满，改缩目标：复用上一稿页面、仅机械对齐 head/导航、模型修两处 JS 语义 bug 后通过）。
- 调用统计（batch 目录 usage.log 全量记录）：成功调用 12 次，prompt 合计 291959、completion 合计 60205、合计 352164；空响应 2 次（均为 reasoning-only、16000 上限占满），其上报口径 prompt 合计 50531、completion 合计 32000、合计 82531；错误行 0 条；本轮无 429、无 HTTP 错误行；全量 14 条，prompt 合计 342490、completion 合计 92205、合计 434695；全部调用模型均为大写 GLM-5.3-Flash。

## [0.31.0] - 2026-10-27

### 新增

- 全站延迟趋势：Store 层 SiteMonthlyLatency（单月全站聚合：成功检查延迟的 p50/p95/p99、均值、成功检查数、监控数、最慢监控）与 SiteLatencyTrend（复用既有 shiftMonth 逐月聚合，月份按时间顺序排列；months 取值 1~12、非法 endMonth/months 报错）；API（均需鉴权）GET /api/latency/trend?end=YYYY-MM&months=N（end 缺省当月、months 缺省 6、非法 end/months 返回 400）、GET /api/latency/trend.html（中文 HTML 导出：延迟趋势标题、逐月表、p95 延迟条形，条形宽度按窗口内最大 p95 归一化）；控制台页 /latency-trend（截止月份选择、3/6/12 个月选择、总览卡片、逐月表、p95 延迟条形、导出 HTML 链接），17 个既有控制台页导航末尾加延迟趋势链，/latency-trend 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：只统计 ok=1 的成功检查，失败检查的延迟不计入分位与均值；空月 p50/p95/p99/均值均为 0、成功检查数为 0、最慢监控为空；最慢监控取当月有成功检查的监控中 p95 最大者、并列取先遇到；监控数为当前监控列表总数；月份窗口用 RFC3339 起止（与 MonthlySLA 一致）；分位复用既有 percentileLinear 线性插值。
- 无 schema 变更、无新环境变量。

### 测试

- 新增 internal/store/site_latency_trend_test.go（空库 3 个月：起止月份与空月零值与非法 months/endMonth/月份报错；双月：2 月延迟 [100,200] 与 [1000,1000] 得 p50 600、p95 1000、p99 1000、均值 575、总数 4、最慢为高延迟监控，3 月延迟 [300,400,500] 加一条 9999 失败检查得 p50 400、p95 490、p99 498、均值 400、总数 3、失败检查已排除）、internal/handlers/site_latency_trend_test.go（JSON 的 end_month/months 与 2 项与 3 月 p50 200/p95 290/总数 3 与非法参数 400、HTML 的 200 与“全站延迟趋势/p95 延迟条形/150.00”字样与非法 end 400；本轮新增 insertLatencyCheck helper 用 RFC3339 日期，规避既有 insertChecks 空格日期的月首漂移）、internal/web/latency_trend_test.go（延迟趋势页 14 个标记与标记顺序、失败路径定义顺序、17 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包为既存最慢包，239.351 秒）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18501 端口，SENTINEL_TICK_SEC=60；隔离库与隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建 UP 监控 3 号（本地 200 服务）与 DOWN 监控 4 号（127.0.0.1:9 拒绝）；各 CheckNow 2 次后 GET /api/latency/trend?end=2026-10&months=2 返回 9 月空月 0 检查/零延迟、10 月成功检查数 2（DOWN 的失败检查未计入）、最慢监控为冒烟UP、监控数 4；无鉴权 401、months=0 与 end=2026-13 均为 400；latency/trend.html 含“全站延迟趋势”与“p95 延迟条形”；/latency-trend 页 200 且含全部标记；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 两次冒烟运行的 10 月延迟值不同（首跑 p50/p95/p99/均值均为 2.00，复拍为 2.50/2.95/2.99/2.50），系本地 200 服务实测延迟抖动，非口径变化。

### 视觉验收

- 截图 docs/screenshots/latency-trend-v031.png 亲眼核对——导航 18 链齐全且延迟趋势 active、控件（October 2026、6 个月、查看、导出 HTML 版）、卡片（截止月份 2026-10、成功检查总数 2）与逐月行（5–9 月 0.00、10 月 2.50/2.95/2.99/2.50、2 检查、监控数 4、最慢冒烟UP）及 p95 条形（10 月蓝色满格 2.95 ms、空月灰底 0.00 ms）均与 API 返回一致、无“加载失败”。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败且 about:blank 不透明源读 sessionStorage 抛 SecurityError；截图脚本按既往模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 桩化为空串、页面脚本的 /api 改写为绝对地址并经 route 代理回真实服务（路由层注入冒烟 stub token、OPTIONS 预检直接回 200 并补 CORS 头），该改写仅限截图环境，产品代码未动。首拍 1280 宽下导航末尾被裁，改 1600 宽复拍后 18 链齐全。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 wave11_lat_call.py（令牌经 SSH 现取、只进子进程内存、不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，每次调用用量均已捕获记账，失败重试单独立行记账）；Go 代码、测试、页面均为小片段逐字输出口径；编排侧机械工作：片段拼接与 gofmt、17 页导航链机械追加（保留各页原行首缩进）、路由与鉴权精确名单接线、README/CHANGELOG 事实性文字、Handlers 测试稿 p50 断言修正（[100,200] 的 p50 为 150.00，提示词误写 200.00，模型按线性插值算对、编排侧改断言）。
- 平台层现象：3 通 reasoning-only 空响应（Store 月函数稿、Store 双月测试稿、Handlers JSON 测试稿，调用器自动重试后均出正文，空响应行已记账）。
- 调用统计（batch 目录 usage.log 全量记录）：成功调用 12 次，prompt 合计 290303、completion 合计 24128、合计 314431；空响应 3 次（均为 reasoning-only），其上报口径 prompt 合计 72903、completion 合计 12000、合计 84903；错误行 0 条；本轮无 429、无 HTTP 错误行；全量 15 条，prompt 合计 363206、completion 合计 36128、合计 399334；全部调用模型均为大写 GLM-5.3-Flash。

## [0.30.0] - 2026-10-27

### 新增

- 单监控年度 SLA 报告：Store 层 MonitorYearlySLA（复用单监控月报 MonthlySLA 聚合全年 12 个月，月份按时间顺序排列；年份取值 1970~9999、非法年份报错；先查 GetMonitor，不存在的监控返回“监控不存在”；年度可用性按检查数加权、零检查月份不计入加权分母、全部零检查时为 100；最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月；故障归因合计与占比与单监控月报口径一致）；API（均需鉴权）GET /api/monitors/{id}/sla/year?year=YYYY（缺省当年、非法年份返回 400、不存在的监控返回 404）、GET /api/monitors/{id}/sla/year.html（中文 HTML 导出：单监控年度标题、逐月表、可用性条形）；控制台页 /monitor-sla-year（监控下拉、年份选择、总览卡片、逐月表、可用性条形、导出 HTML 链接），16 个既有控制台页导航末尾加单监控年度SLA链，/monitor-sla-year 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：单监控年度 SLA 只聚合该监控的月报，其他监控不计入；空月可用性记 100（沿用单监控月报口径），但空月不参与最佳与最差月份评选；不存在监控的 404 依赖 Store 层先查 GetMonitor，因为单监控月报本身对不存在的监控不会报错。

### 测试

- 新增 internal/store/monitor_sla_year_test.go（空年 12 个月：首末月份与目标 99.9、空年可用性 100 与达标、最佳与最差回落首月、非法年份与不存在监控报错；双月：2 月 10 全成功、3 月 9 成功 1 失败得年度加权 95、最佳 2 月、最差 3 月、未达标）、internal/handlers/monitor_sla_year_test.go（JSON 的 monitor_id/monitor_name/year 与 12 项与不存在监控 404 与非法年份 400、HTML 的 200 与“单监控年度 SLA 报告/监控名/可用性条形”字样与不存在监控 404 与非法年份 400）、internal/web/monitor_sla_year_test.go（单监控年度SLA页 14 个标记与标记顺序、失败路径定义顺序、16 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包为既存最慢包，239.583 秒）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18500 端口，SENTINEL_TICK_SEC=60；隔离库与隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建 UP 监控 3 号（本地 200 服务）与 DOWN 监控 4 号（127.0.0.1:9 拒绝）；各 CheckNow 2 次后 GET /api/monitors/4/sla/year?year=2026 返回年度可用性 0%/检查总数 2/事件数 1/归因 connection 100%/未达标、最佳与最差月份均为 2026-10（全年唯一有检查的月份）、空月 100%/0 检查；GET /api/monitors/3/sla/year?year=2026 返回年度可用性 100%/检查总数 2/未达标为否（达标）、最佳与最差月份均为 2026-10；缺省 year 返回当年 2026 且数值一致；非法年份 abc/1969/10000 均为 400、不存在的监控 404、年度接口无鉴权 401；sla/year.html 含“单监控年度 SLA 报告 年报DOWN 2026”与可用性条形，HTML 的不存在监控 404 与非法年份 400 均通过；/monitor-sla-year 页 200 且含全部标记、无鉴权时页面壳仍 200（既有白名单口径、数据接口仍需鉴权）；冒烟完二进制、隔离库、备份文件均已清理，端口已关。

### 视觉验收

- 截图目视未完成：本轮未产出 docs/screenshots/monitor-sla-year-v030.png，页面未经过真实数据截图亲眼核对，原因如下（非页面代码问题）：约 22:21 UTC 起本机执行环境突变，Go 与 Python 二进制的文件写操作一律报 EPERM（SQLite 新库 WAL 报 disk I/O error，Python 写盘报 Operation not permitted，Shell/Perl/Node 写盘仍正常），Chromium 启动亦报 SIGTRAP 崩溃；为截图重启的隔离服务两次均因上述原因无法打开新库而退出，未能重建可截图的真实服务。截图脚本已留在本轮 batch 目录（shot_monitor_year.js，按既往模式：setContent 内联样式与 app.js、app.js 的 sessionStorage 取 token 桩化为空串、路由层注入冒烟 stub token 并处理 OPTIONS 预检与 CORS 头），待环境恢复后重跑即可补图。本条为已知限制，绝不视为已视觉验收。

### 办结状态

- 本轮代码、测试、冒烟、文档均已完成，但 commit 与 push 未完成：约 22:21 UTC 起本机执行环境突变，git 二进制写对象一律报 Operation not permitted（git add 与 git hash-object 均失败，index 未被改动、无半截暂存），工作树 25 个 sentinel 文件保持未提交状态；待环境恢复后按本节文件清单执行 git add、核对 diff --cached --stat、commit、push origin main 并用 git branch -r --contains 核实即可，不需重做代码与测试。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night10_sentinel_call.py（令牌经 SSH 现取、只进子进程内存、不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，每次调用用量均已捕获记账）；Go 代码、测试、页面均为单文件逐字输出口径；编排侧机械工作：Handlers 测试稿 CreateMonitor 单变量赋值改双返回值加 err 断言、页面稿 API 字段名改 total_checks/uptime_pct/down_incidents/total_downtime_sec 且卡片改用服务端 best_month/worst_month/uptime_pct/met（不再由页面自行重算）、16 页导航链每页只多一行且保留原行首缩进、路由与鉴权精确名单接线、README/CHANGELOG 事实性文字。
- 调用统计（batch 目录 usage.log 全量记录）：成功调用 6 次，空响应 0 次，错误 0 条；成功计 token：prompt 合计 145267、completion 合计 41520、合计 186787；全量与成功一致（无空响应与错误行）；本轮无 429、无 HTTP 错误行；全部调用模型均为大写 GLM-5.3-Flash。

## [0.29.0] - 2026-10-27

### 新增

- 分组年度 SLA 报告：Store 层 GroupYearlySLA（复用 v0.25.0 的 GroupMonthlySLA 聚合全年 12 个月，月份按时间顺序排列；年份取值 1970~9999、非法年份报错；年度可用性按检查数加权、零检查月份不计入加权分母、全部零检查时为 100；监控数为各月监控数最大值；最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月；故障归因合计与占比与分组月报口径一致）；API（均需鉴权）GET /api/groups/{id}/sla/year?year=YYYY（缺省当年、非法年份返回 400、不存在的分组返回 404）、GET /api/groups/{id}/sla/year.html（中文 HTML 导出：分组年度标题、逐月表、可用性条形）；控制台页 /group-sla-year（分组下拉、年份选择、总览卡片、逐月表、可用性条形、导出 HTML 链接），15 个既有控制台页导航末尾加分组年度SLA链，/group-sla-year 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：分组年度 SLA 只聚合组内监控的月报，不在组内的监控不计入；空月可用性记 100（沿用分组月报口径），但空月不参与最佳与最差月份评选；空月最差监控沿用分组月报的既有语义（取组内首个 100% 监控名）；年度监控数为峰值口径（各月监控数最大值，成员不变时与组内成员数相等）。

### 测试

- 新增 internal/store/group_sla_year_test.go（空组年 12 个月：首末月份与目标 99.9、空年可用性 100 与达标、最佳与最差回落首月、非法年份与不存在分组报错；双月单监控：2 月 10 全成功、3 月 9 成功 1 失败得年度加权 95、最佳 2 月、最差 3 月、未达标、监控数 1）、internal/handlers/group_sla_year_test.go（JSON 的 group_id/group_name/year 与 12 项与不存在分组 404 与非法年份 400、HTML 的 200 与“分组年度 SLA 报告/组名/可用性条形”字样与不存在分组 404 与非法年份 400）、internal/web/group_sla_year_test.go（分组年度SLA页 15 个标记与标记顺序、失败路径定义顺序、15 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包为既存最慢包）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18499 端口，SENTINEL_TICK_SEC=60；隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建分组 1 号“核心业务”返回 201；新建组内 UP 监控 3 号（本地 200 服务）与组内 DOWN 监控 4 号（127.0.0.1:9 拒绝）加入分组，另建组外 DOWN 监控 5 号不加入；各 CheckNow 2 次后 GET /api/groups/1/sla/year?year=2026 返回年度可用性 50%/检查总数 4（组外监控未计入）/事件数 1/归因 connection 100%/未达标、最佳与最差月份均为 2026-10（全年唯一有检查的月份）、空月 100%/0 检查/最差为组内 UP（沿用分组月报口径）；缺省 year 返回当年 2026 且数值一致；非法年份 abc/1969/10000 均为 400、不存在的分组 404、年度接口无鉴权 401；sla/year.html 含“分组年度 SLA 报告 核心业务 2026”与可用性条形；/group-sla-year 页 200 且含全部标记、无鉴权时页面壳仍 200（既有白名单口径、数据接口仍需鉴权）；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 宕机时长在截图时为 21 秒，系 MonthlySLA 对未恢复事件的既有开放估算口径，非本轮新口径。

### 视觉验收

- 截图 docs/screenshots/group-sla-year-v029.png 亲眼核对——导航 16 链齐全且分组年度SLA active、分组下拉选中核心业务、年份输入 2026、查看与导出 HTML 版齐全、卡片（年度 2026、年度可用性 50.00%、检查总数 4、最佳月份 2026-10、最差月份 2026-10、是否达标未达标）与逐月行（1–9 月与 11–12 月 100% 达标、10 月 50.00% 4 检查 1 事件 最差组内DOWN 未达标）及可用性条形（10 月半格 + 灰底余量）均与 API 返回一致、无“加载失败”。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败；截图脚本按既往模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为空串（about:blank 不透明源下直接读 sessionStorage 会抛 SecurityError，api 在 fetch 前即失败）、页面脚本的 /api 改写为绝对地址并经 route 代理回真实服务（路由层注入冒烟 stub token、OPTIONS 预检直接回 200 并补 CORS 头），该改写仅限截图环境，产品代码未动。另实证：page.goto 直连 127.0.0.1 会被 ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS 拦掉，加 disable-features 旗标亦未解封，故未走直连路线。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night9_wave9_call.py（令牌经 SSH 现取、只进子进程环境变量、不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，探活用量已捕获记账）；Go 代码、测试、页面均为微片段逐字输出口径；编排侧机械工作：类型稿 Year 字段 string 改 int、Store 稿 Month 字段 m 改 mr.Month 与拼接处多余循环闭合括号删除、测试稿虚构的 seedGroup 辅助改 CreateGroup、Handlers 测试稿 doJSON 入参改字符串 body 与建组断言 201、Web 测试稿 static.ReadFile 改 fs.ReadFile(FS, ...) 与失败路径空值补全、页面稿 nav class 补齐与年度可用性两位小数与 const status 独立声明与双重 init 去重、15 页导航链与路由/鉴权名单机械接线、README/CHANGELOG 事实性文字；另有语义说明一处：空月最差监控为组内首个 100% 监控名是分组月报既有语义，非本轮新口径。
- 平台层现象：Handlers 处理器稿一次 reasoning-only 空响应（改 max_tokens 16000 后出正文）；Store 双月测试稿连续 4 次 reasoning-only 空响应（4000 与 16000 均空，改骨架照抄 + 16000 后出正文）；截图调试中发现 about:blank 下 sessionStorage 抛 SecurityError（见视觉验收 harness 说明）。
- 调用统计（batch 目录 usage.log 全量记录，含空响应；成功计 token 与空响应分开标明）：成功调用 14 次，prompt 合计 335590、completion 合计 52227、合计 387817；空响应 5 次（均为 reasoning-only），其上报口径 prompt 合计 119771、completion 合计 32000、合计 151771；错误行 0 条；本轮无 429、无 HTTP 错误行；全量 19 条，prompt 合计 455361、completion 合计 84227、合计 539588。

## [0.28.0] - 2026-10-27

### 新增

- 全站年度 SLA 报告：Store 层 SiteYearlySLA（复用 v0.21.0 的 SiteMonthlySLA 聚合全年 12 个月，月份按时间顺序排列；年份取值 1970~9999、非法年份报错；年度可用性按检查数加权、零检查月份不计入加权分母、全部零检查时为 100；监控数为各月监控数最大值；最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月；故障归因合计与占比与全站口径一致）；API（均需鉴权）GET /api/sla/year?year=YYYY（缺省当年、非法年份返回 400）、GET /api/sla/year.html（中文 HTML 导出：年度总览、逐月表、可用性条形）；控制台页 /sla-year（年份选择、总览卡片、逐月表、可用性条形、导出 HTML 链接），14 个既有控制台页导航末尾加年度SLA链，/sla-year 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：全站年度 SLA 只聚合全站月报，不改变任何单月口径；空月可用性记 100（沿用单月报告口径），但空月不参与最佳与最差月份评选；年度监控数为峰值口径（各月监控数最大值），因单月监控数取当前监控列表、各月实际相等。
- 既有口径说明（本轮调试实证，非新改动）：handlers 既有 insertChecks 测试 helper 用空格格式日期，月首日记录会因空格小于 RFC3339 的 T 而落入上月桶；本轮新增的 insertYearChecks helper 改用 RFC3339 格式，月份归属无此漂移。

### 测试

- 新增 internal/store/site_sla_year_test.go（空年 12 个月：首末月份与目标 99.9、空年可用性 100 与达标、最佳与最差回落首月、非法年份报错；双月：2 月 10 全成功、3 月 9 成功 1 失败得年度加权 95、最佳 2 月、最差 3 月、未达标）、internal/handlers/site_sla_year_test.go（JSON 的 year/uptime_pct/total_checks/best_month/worst_month 与 12 项、非法年份 400、HTML 的 200 与“全站年度 SLA 报告/年份/可用性条形”字样与非法年份 400）、internal/web/sla_year_test.go（年度SLA页 12 个标记与标记顺序、失败路径定义顺序、14 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包 238.9 秒为既存最慢包）。
### 真实服务冒烟

- 真实服务冒烟（隔离库 18498 端口，SENTINEL_TICK_SEC=60；隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建 UP 监控 3 号（本地 200 服务）与 DOWN 监控 4 号（127.0.0.1:9 拒绝）；各 CheckNow 2 次后 GET /api/sla/year?year=2026 返回年度可用性 50%/检查总数 4/事件数 1/归因 connection 100%/未达标、最佳与最差月份均为 2026-10（全年唯一有检查的月份）、空月 100%/0 检查/最差为示例站点（沿用单月口径）；缺省 year 返回当年 2026 且数值一致；非法年份 abc/1969/10000 均为 400、年度接口无鉴权 401；sla/year.html 含“全站年度 SLA 报告 2026”与可用性条形与年报DOWN；/sla-year 页 200 且含全部标记、无鉴权时页面壳仍 200（既有白名单口径、数据接口仍需鉴权）；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 宕机时长在截图时为 1 分 49 秒（冒烟断言时为 4 秒），系 MonthlySLA 对未恢复事件的既有开放估算口径，非本轮新口径。

### 视觉验收

- 截图 docs/screenshots/sla-year-v028.png 亲眼核对——导航 14 链齐全且年度SLA active、年份输入 2026、查看与导出 HTML 版齐全、卡片（年度 2026、年度可用性 50.00%、检查总数 4、最佳月份 2026-10、最差月份 2026-10、是否达标未达标）与逐月行（1–9 月与 11–12 月 100% 达标、10 月 50.00% 4 检查 1 事件 最差年报DOWN 未达标）及可用性条形（10 月半格 + 灰底余量）均与 API 返回一致、无“加载失败”。
- 截图 harness 说明：Playwright setContent 会忽略 url 选项（文档基址为 about:blank，相对 /api 解析失败），首拍因此“加载失败”；截图脚本按 shoot2.js 模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为空串（鉴权由截图代理在服务端注入冒烟 stub token）、页面脚本的 /api 改写为绝对地址并经 route 代理回真实服务，该改写仅限截图环境，产品代码未动。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 sentinel_night8_wave_call.py（令牌经 SSH 现取、只进子进程环境变量、不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，探活用量已捕获记账）；Go 代码、测试、页面均为微片段逐字输出口径；编排侧机械工作：Store 稿 Attribution map 类型修正、Handler 稿 slaDur 入参补 float64 转换、页面脚本稿字段名按 API 合同修正（months/down_sec/worst_monitor/meets_sla 改为 items/total_downtime_sec/worst_monitor_name/met）、测试稿签名修正（insertCheckAt 补 latency、SiteYearlySLA 去 monitorID 入参、newSLATestServer 三返回值补齐）、14 页导航链与路由/鉴权名单机械接线、README/CHANGELOG 事实性文字；另有语义修正一处：测试揪出空月 100% 会抢走最佳月份，改口径为最佳与最差只在有检查月份中评选、全年无检查回落首月（API 补丁稿 + 测试双绿验证）。
- 平台层现象：Store 双月测试稿两次 reasoning-only 空响应（改 max_tokens 16000 后出正文）；其后一通 ok 正文因本机写文件瞬时 EPERM 未落盘（token 已计入 ok 合计），重取一通后落盘；页面脚本稿一次 reasoning-only 空响应（改 max_tokens 16000 后出正文）；Handlers 调试中发现既有 insertChecks 空格日期格式的月首漂移，本轮 helper 改 RFC3339 规避（见上文既有口径说明）。
- 调用统计（batch 目录 usage.log 全量记录，含空响应；成功计 token 与空响应分开标明）：成功调用 16 次，prompt 合计 382242、completion 合计 32306、合计 414548（其中 1 通 ok 正文因 EPERM 丢失、token 2951 仍计入该合计，重取通另计）；空响应 3 次（均为 reasoning-only，4000 token 上限占满），其上报口径 prompt 合计 71686、completion 合计 12000、合计 83686；错误行 0 条；全量 19 条，prompt 合计 453928、completion 合计 44306、合计 498234；本轮无 429、无 HTTP 错误行。

## [0.27.0] - 2026-10-27

### 新增

- 单监控 SLA 趋势：Store 层 MonitorSLATrend（复用单月 MonthlySLA 逐月聚合，月份按时间顺序排列；months 取值 1~12、非法 endMonth/months 报错；先 GetMonitor，不存在的监控返回“监控不存在”错误）；API（均需鉴权）GET /api/monitors/{id}/sla/trend?end=YYYY-MM&months=N（end 缺省当月、months 缺省 6、非法 end/months 返回 400、不存在的监控 404）、GET /api/monitors/{id}/sla/trend.html（中文 HTML 导出：单监控趋势标题、逐月表、可用性条形）；控制台页 /monitor-sla-trend（监控下拉、截止月份选择、3/6/12 个月选择、逐月表、可用性条形、导出 HTML 链接），13 个既有控制台页导航末尾加单监控SLA趋势链，/monitor-sla-trend 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：单监控 SLA 趋势只统计该监控，不含其他监控；空月可用性记 100（沿用 MonthlySLA 单月报告口径）。

### 测试

- 新增 internal/store/monitor_sla_trend_test.go（空监控 3 个月：起止月份与目标 99.9、空月可用性 100；非法 months/endMonth 与不存在监控报错；双月：2 月 10 全成功、3 月 9 成功 1 失败得 90%）、internal/handlers/monitor_sla_trend_test.go（JSON 的 monitor_id/monitor_name/end_month/months 与不存在监控 404 与非法 months/end 的 400、HTML 的 200 与“单监控 SLA 趋势/监控名/可用性条形”字样与不存在监控 404）、internal/web/monitor_sla_trend_test.go（单监控SLA趋势页 16 个标记与标记顺序、失败路径定义顺序、13 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包 238.5 秒为既存最慢包）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18497 端口，SENTINEL_TICK_SEC=60；隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建 UP 监控 3 号（本地 200 服务）与 DOWN 监控 4 号（127.0.0.1:9 拒绝）；各 CheckNow 2 次后 GET /api/monitors/4/sla/trend?end=2026-10&months=2 返回 9 月空月 100%/0 检查、10 月 0%/2 检查/1 事件/未达标，GET /api/monitors/3/sla/trend?end=2026-10&months=2 返回 10 月 100%/2 检查/达标；不存在的监控返回 404、months=0/abc 与 end=2026-13 均为 400、趋势接口无鉴权 401；sla/trend.html 含“单监控 SLA 趋势 组内DOWN 2026-10”与可用性条形；/monitor-sla-trend 页 200 且含全部标记；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 视觉验收：截图 docs/screenshots/monitor-sla-trend-v027.png 亲眼核对——导航 13 链齐全且单监控SLA趋势 active、监控下拉选中组内DOWN、月份 October 2026、6 个月、查看与导出 HTML 版齐全、卡片（监控组内DOWN、截止月份 2026-10、目标 99.9%）与逐月行（5–9 月 100% 达标、10 月 0.00% 未达标）及可用性条形（5–9 月蓝色满格、10 月空轨）均与 API 返回一致、无“加载失败”。截图重拍时 10 月检查数由 2 变 3、宕机时长由 57 秒变 1 分 45 秒，系 60 秒调度 tick 对已启用 DOWN 监控又执行一次失败检查、以及未恢复事件的既有开放估算口径，非本轮新口径。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败且无 CORS 头，截图脚本按 shoot2.js 模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为空串（鉴权由截图代理在服务端注入冒烟 stub token）、页面脚本的 /api 经 base 改写为绝对地址并经 route 代理回真实服务，该改写仅限截图环境，产品代码未动。首版截图发现可用性条形未着色（条形内外层误用 span，行内元素宽度不生效），改 div 后复拍通过。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night7_sentinel_call.py（令牌经 SSH 现取不落盘、未读任何现成调用脚本；显式流式解析 + include_usage，首个探活用量已捕获记账）；Go 代码、测试、页面均为微片段逐字输出口径；编排侧机械工作：Handler 接收者与 s.store/s.serveStaticFile 补齐、parsePathID 返回值修正、截断稿续尾字段名修正（Availability/items 改为 UptimePct/rep.Items）、条形 span 改 div、13 页导航链机械追加、路由与鉴权名单接线、README/CHANGELOG 事实性文字。
- 调用统计（batch 目录 usage.log 全量记录，含空响应；成功计 token 与空响应分开标明）：成功调用 13 次，prompt 合计 310867、completion 合计 29540、合计 340407；空响应 2 次（Handler HTML 整稿、页面 load 稿，均为 reasoning-only，改拆小稿后均成功），其上报口径 prompt 合计 47948、completion 合计 8000；错误行 0 条；全量 15 条，prompt 合计 358815、completion 合计 37540、合计 396355；本轮无 429、无 HTTP 错误行。另有一稿因 4000 token 上限截断在半行（计入成功合计），经贴断点原文向 API 要续尾补全后通过测试。

## [0.26.0] - 2026-10-27

### 新增

- 分组 SLA 趋势：Store 层 GroupSLATrend（复用 v0.25.0 的 GroupMonthlySLA 逐月聚合，月份按时间顺序排列；months 取值 1~12、非法 endMonth/months 报错；分组不存在时由首月月报返回“分组不存在”错误）；API（均需鉴权）GET /api/groups/{id}/sla/trend?end=YYYY-MM&months=N（end 缺省当月、months 缺省 6、非法 end/months 返回 400、不存在的分组 404）、GET /api/groups/{id}/sla/trend.html（中文 HTML 导出：分组趋势标题、逐月表、可用性条形）；控制台页 /group-sla-trend（分组下拉、截止月份选择、3/6/12 个月选择、逐月表、可用性条形、导出 HTML 链接），12 个既有控制台页导航末尾加分组SLA趋势链，/group-sla-trend 加进鉴权精确名单（页面壳为既有白名单口径、数据接口仍需鉴权）。
- 语义界定：分组 SLA 趋势只统计组内监控，不在组内的监控不计入；空月可用性记 100、监控数为组内成员数（沿用 v0.25.0 单月报告口径，空月最差监控仍显示首个 100% 监控名）。

### 测试

- 新增 internal/store/group_sla_trend_test.go（空组 3 个月：起止月份与目标 99.9、空月可用性 100；非法 months/endMonth 与不存在分组报错；双月：2 月 10 全成功、3 月 9 成功 1 失败得 90%）、internal/handlers/group_sla_trend_test.go（JSON 的 group_id/group_name/end_month/months 与不存在分组 404 与非法 months/end 的 400、HTML 的 200 与“分组 SLA 趋势/组名/可用性条形”字样与不存在分组 404）、internal/web/group_sla_trend_test.go（分组SLA趋势页 16 个标记与标记顺序、失败路径定义顺序、12 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（16 包，notify 包 239.2 秒为既存最慢包）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18496 端口，SENTINEL_TICK_SEC=60；隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建分组 1 号“核心业务”返回 201；新建组内 UP 监控 3 号（本地 200 服务）与组内 DOWN 监控 4 号（127.0.0.1:9 拒绝）加入分组；各 CheckNow 2 次后 GET /api/groups/1/sla/trend?end=2026-10&months=2 返回 9 月空月 100%/0 检查、10 月 50%/4 检查/1 事件/监控数 2/最差为组内DOWN/未达标；不存在的分组返回 404、months=0/abc 与 end=2026-13 均为 400、趋势接口无鉴权 401；sla/trend.html 含“分组 SLA 趋势 核心业务 2026-10”与可用性条形；/group-sla-trend 页 200 且含全部标记；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 视觉验收：截图 docs/screenshots/group-sla-trend-v026.png 亲眼核对——导航 12 链齐全且分组SLA趋势 active、分组下拉选中核心业务、月份 October 2026、6 个月、查看与导出 HTML 版齐全、卡片（分组核心业务、截止月份 2026-10、目标 99.9%）与逐月行（5–9 月 100% 达标、10 月 50.00% 4 检查 1 事件 最差组内DOWN 未达标）及可用性条形（10 月半格 + 灰底余量）均与 API 返回一致、无“加载失败”。宕机时长在截图时为 7 秒（冒烟断言时为 4 秒），系 MonthlySLA 对未恢复事件的既有开放估算口径，非本轮新口径。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败且无 CORS 头，截图脚本按 shoot2.js 模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为冒烟 stub token、页面脚本的 /api 改写为绝对地址并经 route 代理回真实服务，该改写仅限截图环境，产品代码未动。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night6_sentinel_call.py（令牌经 SSH 现取不落盘、未读任何现成调用脚本；取令牌走 SSH 远程 python 读 /home/azureuser 绝对路径库）；Go 代码、测试、页面均为微片段逐字输出口径；编排侧机械工作：片段拼接与 gofmt、12 页导航链机械追加、路由与鉴权名单接线、README/CHANGELOG 事实性文字；另有平台层现象：首个探活用量因 SSE 用量未捕获而漏记一行（修解析器改显式流式 + include_usage 后重探成功，该行仍保留在日志中、用量未知）；三通 reasoning-only 空响应（Store 初稿、Store 测试二稿、Handlers HTML 初稿，改拆小稿/骨架照抄后均成功）。
- 调用统计（batch 目录 usage.log 全量记录，含重试与空响应；成功计 token 与空响应分开标明）：成功计 token 的调用 13 次，prompt 合计 312913、completion 合计 14134、合计 327047；空响应 3 次（均为 reasoning-only），其上报口径 prompt 合计 72334、completion 合计 12000；另有首个探活成功行 1 条因解析器 bug 用量未捕获（prompt/completion 均为空，不计入合计）；全量已知 token 行 16 条，prompt 合计 385247、completion 合计 26134、合计 411381；本轮无 429、无 HTTP 错误行。

## [0.25.0] - 2026-10-27

### 新增

- 分组 SLA 月报：Store 层 GroupMonthlySLA（分组不存在报错、非法月份报错；成员取 ListGroupMonitors、逐监控复用 MonthlySLA；可用性按检查数加权、零检查监控不计入加权分母、全部零检查时为 100；最差监控取组内最低可用性；故障归因合计与占比与全站口径一致；空组返回监控数 0、可用性 100、达标）；API（均需鉴权）GET /api/groups/{id}/sla?month=YYYY-MM（缺省当月、非法月份 400、不存在的分组 404）、GET /api/groups/{id}/sla.html（中文 HTML 导出：分组卡片、组内监控表、故障归因）；控制台页 /group-sla（分组下拉、月份选择、总览卡片、组内监控表、导出 HTML 链接），11 个既有控制台页导航末尾加分组SLA链，/group-sla 加进鉴权精确名单。
- 语义界定：分组 SLA 只统计组内监控，不在组内的监控不计入；分组本身不影响检查调度与告警（沿用 v0.24.0 界定）。

### 测试

- 新增 internal/store/group_sla_test.go（空组与不存在分组与非法月份、加权 90/100 对 100/100 得 95 与最差监控为组内 90 分监控、组外全失败监控不计入）、internal/handlers/group_sla_test.go（JSON 的 group_id/group_name/month/monitor_count 与不存在分组 404 与非法月份 400、HTML 的 200 与“分组 SLA 月报/组名/本组暂无监控”字样与不存在分组 404）、internal/web/group_sla_test.go（分组SLA页 13 个标记、失败路径定义顺序、11 页导航链）；页面 JS 经 node --check 通过。
- go vet 全洁；go test ./... 全绿（notify 包为既存最慢包）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18495 端口，SENTINEL_TICK_SEC=60；隔离备份目录，绝未写仓库 data/backups）：种子监控占 1/2 号（已禁用）；新建分组 1 号“核心业务”返回 201；新建组内 UP 监控 3 号（本地 200 服务）与组内 DOWN 监控 4 号（127.0.0.1:9 拒绝）加入分组，另建组外 DOWN 监控 5 号不加入；各 CheckNow 2 次后 GET /api/groups/1/sla?month=2026-10 返回可用性 50、检查总数 4（组外监控未计入）、监控数 2、最差为组内DOWN、归因 connection 100%、未达标；不存在的分组返回 404、非法月份返回 400；sla.html 含“分组 SLA 月报 核心业务 2026-10”与卡片；/group-sla 页 200 且无鉴权 401；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 视觉验收：截图 docs/screenshots/group-sla-v025.png 亲眼核对——导航 11 链齐全且分组SLA active、分组下拉选中核心业务、月份 October 2026、查看与导出 HTML 版齐全、五张卡片（分组可用性 50.00%、检查总数 4、宕机时长、事件总数 1、是否达标未达标）与真实组内行（组内UP 100.00% 达标、组内DOWN 0.00% 未达标）均与 API 返回一致、无“加载失败”。宕机时长在截图时已从 10 秒涨到 1 分 46 秒，系 MonthlySLA 对未恢复事件的既有开放估算口径，非本轮新口径。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败，截图脚本按 shoot2.js 模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为冒烟 stub token、页面脚本的 /api/groups 改写为绝对地址并经 route 代理回真实服务，该改写仅限截图环境，产品代码未动。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器为本轮现写最小新文件 night5_sentinel_call.py（令牌经 SSH 现取不落盘、未读任何现成调用脚本；中途因 sudo 下 ~ 解析到 root 家目录致库路径错一次，改走 /home/azureuser 绝对路径后取通，属取令牌路径问题、无 API 调用产生）；Go 代码、测试、页面均为微片段逐字输出口径；编排侧机械工作：片段拼接与 gofmt、结构体稿去重 package 行、测试鉴权头补齐、11 页导航链机械追加、路由与鉴权名单接线、README/CHANGELOG 事实性文字；另有平台层现象：首通 4 次 reasoning-only 空响应（改小稿加“最高指令禁思考过程”后出正文）、一通 HTTP 500 与两通 reasoning-only 后第 4 次成功、一稿因 4000 token 上限截断在半行（贴断点原文只向 API 要续尾补全）。
- 调用统计（batch 目录 usage.log 全量记录，含重试与空响应；成功计 token 与空响应分开标明）：成功调用 17 次，prompt 合计 407367、completion 合计 20940、合计 428307；空响应 6 次（首通 4 次、加权测试稿 2 次，均为 reasoning-only），其上报口径 prompt 合计 143764、completion 合计 13325；错误行 1 条（HTTP 500，不计用量；本轮无 429）；全量计 token 行 23 条，prompt 合计 551131、completion 合计 34265、合计 585396。另有一稿因 4000 token 上限截断在半行（计入成功合计），经贴断点原文向 API 要续尾补全后通过测试。

## [0.24.0] - 2026-10-27

### 新增

- 监控分组：DB 迁移 v16 新建 monitor_groups 表（id/name UNIQUE/created_at）与 monitor_group_members 关联表（group_id/monitor_id 复合主键、双外键级联）；Store 层 CreateGroup（空名与重名均报错）、ListGroups（含各组监控数）、DeleteGroup（先清成员再删组）、AddMonitorToGroup（分组与监控不存在均报错、重复加入幂等）、RemoveMonitorFromGroup、ListGroupMonitors；API（均需鉴权）POST /api/groups（非法 JSON/空名/重名均 400）、GET /api/groups、DELETE /api/groups/{id}、POST /api/groups/{id}/monitors、DELETE /api/groups/{id}/monitors/{mid}、GET /api/groups/{id}/monitors；控制台页 /groups（新建分组表单、分组列表与删除、按分组选成员加入/移出），10 个既有控制台页导航末尾加监控分组链，/groups 加进鉴权精确名单。
- 语义界定：分组只做归类与筛选，不影响检查调度、事件与告警。

### 测试

- 新增 internal/store/groups_test.go（创建与列表字段、空名与重名拒绝、成员加入幂等与不存在的分组/监控拒绝、移出与删组清成员）、internal/handlers/groups_test.go（创建 201 与重名/空名 400、成员加入/不存在监控 400/成员列表/移出/删组后列表为空）、internal/web/groups_test.go（分组页 18 个标记、失败路径定义顺序、10 页导航链）；db_deep2 全新库版本期望同步到 1~16。
- go vet 全洁；go test ./... 16 包全绿（notify 包 240.1 秒为既存最慢包）。


### 真实服务冒烟

- 真实服务冒烟（隔离库 18494 端口，SENTINEL_TICK_SEC=60）：种子监控占 1/2 号（已禁用）；新建分组返回 201，重名返回 400“分组名已存在”、空名返回 400“name 不能为空”；种子监控 1 号加入分组后成员列表含示例站点、分组列表监控数由 0 变 1；移出后成员列表为空，删组后分组列表为空；/groups 页 200 且无鉴权 401；冒烟完二进制、隔离库、备份文件均已清理，端口已关。
- 视觉验收：截图 docs/screenshots/groups-v024.png 亲眼核对——导航 10 链齐全且监控分组 active、新建分组表单齐全、真实分组行（核心业务、监控数 1、创建时间、删除按钮）与 API 返回一致、成员区下拉选中核心业务后真实成员行（示例站点、https://example.com、http、移出按钮）与 API 返回一致、无“加载失败”。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败，截图脚本按 shoot2.js 模式把样式与 app.js 内联、app.js 的 sessionStorage 取 token 在截图环境内桩化为冒烟 stub token、/api 经 route 代理回真实服务，该改写仅限截图环境，产品代码未动。

## [0.23.0] - 2026-10-27

### 新增

- 维护窗口：调度检查在窗口内整段跳过，不产生检查记录、不开新事件、不发通知；与静默（只压通知、检查照常记）不同。DB 迁移 v15 新建 maintenance_windows 表（monitor_id/title/starts_at/ends_at/created_at，monitor_id 为 0 表示全部监控）；Store 层 CreateMaintenanceWindow（标题非空、RFC3339 时间、开始早于结束、monitor_id 小于 0 或不存在均报错）、ListMaintenanceWindows、DeleteMaintenanceWindow、ActiveMaintenanceWindow（多条命中取 id 最小、端点 inclusive）；调度器 runOne 入口命中窗口时记日志并直接返回（信号量与 inflight 均由既有 defer 释放）；API（均需鉴权）POST /api/maintenance（非法 JSON/不存在的监控/非法窗口均 400）、GET /api/maintenance、DELETE /api/maintenance/{id}；控制台页 /maintenance（标题/监控 ID/开始/结束表单、新建、列表、删除），9 个既有控制台页导航末尾加维护窗口链，/maintenance 加进鉴权精确名单。
- 语义界定：手动检查 POST /api/monitors/{id}/check 不受维护窗口影响（显式人工操作照常执行并记检查）；窗口开始前已 open 的事件不会被窗口自动关闭，窗口只阻止新检查与新事件；窗口内跳过的检查不计入 SLA 检查数（SLA 按实际检查记录聚合）。

### 测试

- 新增 internal/store/maintenance_test.go（创建与列表字段、空标题/倒置时间/非法时间/不存在监控/负 ID 五种拒绝、专属窗口优先命中、未来与过期窗口不命中、90 分钟后全局窗口生效）、internal/handlers/maintenance_test.go（创建 201 与正 id、倒置窗口 400、不存在监控 400、列表与删除后为空）、internal/scheduler/maintenance_test.go（窗口内 runOne 零检查记录零通知、删窗后 runOne 产生 1 条失败检查记录）、internal/web/maintenance_test.go（维护页 13 个标记、失败路径定义顺序、9 页导航链）；db_deep2 全新库版本期望同步到 1~15。
- go vet 全洁；go test ./... 16 包全绿（notify 包 238.9 秒为既存最慢包）。

### 真实服务冒烟

- 真实服务冒烟（隔离库 18493 端口，SENTINEL_TICK_SEC=60）：种子监控占 1/2 号（已禁用），新建 up 监控 3 号（本地 200 服务）与 down 监控 4 号（127.0.0.1:9 拒绝），各 CheckNow 1 次后基线均为 1 条；建全局窗口（覆盖当前时刻）后等 75 秒（含一次调度 tick，到期检查本应执行），两监控检查数仍为 1/1，证明 tick 检查被窗口跳过；窗口内手动 CheckNow 4 号仍执行并新增 1 条失败记录，证明手动检查不受影响；倒置窗口返回 400“starts_at 必须早于 ends_at”；删除窗口后列表为空；/maintenance 页 200 且含全部标记；无鉴权 401；冒烟完二进制、隔离库、端口均已清理。
- 视觉验收：截图 docs/screenshots/maintenance-v023.png 亲眼核对——导航 9 链齐全且维护窗口 active、表单（标题/监控 ID/开始/结束/新建按钮）齐全、真实窗口行（机房割接、监控 0、开始/结束/创建时间、删除按钮）与 API 返回一致、无“加载失败”。

### 已知限制

- 窗口开始前已 open 的事件在窗口内不会自动关闭（恢复仍需窗口结束后的一次成功检查）；如需“窗口开始即挂起事件”须另做事件状态机改动。
- 截图 harness 说明：Playwright setContent 下相对 /api 解析失败且无 CORS 头，截图脚本按 shoot2.js 模式把页面 /api 改写为绝对地址并经 route 代理回真实服务（token 在截图环境内桩化），该改写仅限截图环境，产品代码未动。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行；调用器先为本轮现写最小新文件 night3_sentinel_call.py，后因本机 python 写文件间歇报 EPERM（同机 shell/node 写间歇亦失败，属平台层瞬时故障，与模型无关）改走同口径 node 新文件 night3_sentinel_call.js，模型与通道全程未变；Go 代码、测试、页面、脚本均为微片段逐字输出口径；编排侧机械工作：SQL 引号统一为反引号、H1 创建调用改为结构体实参、T3 删除改捕获的 winID 并补删窗后对照、db 深度测试期望同步到 v15、导航链机械追加、README/CHANGELOG 事实性文字；另有平台层事故复盘：中途两次把既有文件截成 0 字节（导航脚本与 README 写操作撞上 EPERM），均用 git loose 对象解压精确恢复并以 hash-object 验明与 HEAD 一致，仓内无残留损坏。
- 调用统计（batch 目录 usage.log 全量记录，含重试与空响应；成功计 token 与空响应分开标明）：成功调用 20 次，prompt 合计 478973、completion 合计 43120、合计 522093；空响应 5 次（F1 一次、H2 两次、T1 两次，均为 reasoning-only），其上报口径 prompt 合计 119798、completion 合计 6148；错误行 5 条（写文件 EPERM 4 条、远端断连 1 条，不计用量；本轮无 429）；总记录 30 条。其中 P2 脚本稿曾三次生成成功均因写文件 EPERM 未落盘（3 次成功调用的 token 已计入上述成功合计），第 4 次经 node 调用器重试后落盘。

## [0.22.0] - 2026-10-27

### 新增

- 全站 SLA 趋势：`GET /api/sla/trend?end=YYYY-MM&months=N`（需鉴权）返回最近 N 个月逐月全站聚合（月份、可用性、检查数、事件数、宕机时长、监控数、最差监控、是否达标），end 缺省为当月、months 缺省 6、取值 1~12，非法 end/months 返回 400；`GET /api/sla/trend.html` 中文 HTML 导出（含逐月表与可用性条形）；控制台页 `/sla-trend`（截止月份选择、3/6/12 个月选择、逐月表、可用性条形、导出 HTML 链接），各控制台页导航末尾加 SLA趋势链，`/sla-trend` 同时加进鉴权精确名单。
- Store 层 `SiteSLATrend` 复用 v0.21.0 的 `SiteMonthlySLA` 逐月聚合（月份按时间顺序排列，空月可用性记 100、零检查监控不计入加权）；无 schema 变更、无新环境变量。

### 修复

- 趋势页失败路径变量未初始化问题：首版页面脚本把 `cards`/`status` 的 const 定义放在 `await api(...)` 之后，请求一旦失败、catch 里写 `status` 会命中 TDZ 二次抛错，“加载失败”永远显示不出来；现把两行定义移到 `try` 之前，并新增 `TestSLATrendPageFailurePathOrder` 顺序回归测试锁死该顺序。

### 测试

- 新增 `internal/store/site_sla_trend_test.go`（空库 3 个月：起止月份与目标 99.9、非法 months/endMonth 报错；双月：2 月 10 全成功、3 月 9 成功 1 失败得 90%）与 `internal/handlers/site_sla_trend_test.go`（JSON 的 end_month/months/逐月顺序与 months=0/abc、end=2024-13 的 400、HTML 的 200 与“全站 SLA 趋势/可用性条形”字样）与 `internal/web/sla_trend_test.go`（页面标记与顺序、失败路径顺序）；`go test ./...` 16 包全绿；`go vet` 全洁。
- 页面 JS 经 node 桩测双路径通过：成功路径渲染逐月行与条形宽度；失败路径（api 抛错）status 为“加载失败”。
- 真实服务冒烟（隔离库 18492 端口，SENTINEL_TICK_SEC=60）：种子 2 监控（1 up 本地 200 服务、1 down 死端口）各 CheckNow 2 次后 `/api/sla/trend?end=2026-10&months=2` 返回 9 月空月 100%/0 检查、10 月 50%/4 检查/1 事件/最差为死端口/未达标；缺省参数返回 end=2026-10、months=6、6 项；months=0/abc、end=2024-13 均为 400；无鉴权 401；HTML 含趋势字样与条形标记；`/sla-trend` 页 200 且含全部标记；冒烟完二进制、隔离库、端口均已清理。
- 视觉验收：截图 `docs/screenshots/sla-trend-v022.png` 亲眼核对——导航 8 链齐全且 SLA趋势 active、控件（October 2026、6 个月、查看、导出 HTML 版）、6 个月逐月行（5–9 月 100% 达标、10 月 50% 未达标）、绿色可用性条形（10 月半格 + 灰底余量）均与真实数据一致。

### 已知限制

- 趋势逐月的“最差监控”沿用 v0.21.0 单月报告的口径：空月（零检查）最差监控仍显示首个 100% 监控名（如种子“示例站点”），属继承语义，非本轮新口径；如需“空月最差为空”须另改单月报告逻辑。
- 截图 harness 说明：本机 Playwright 的 `setContent` 会忽略 url 选项（文档基址为 about:blank，相对 `/api` 解析失败），截图脚本按 shoot2.js 模式把页面脚本的 `/api` 改写为绝对地址后才拿到真实数据；该改写仅限截图环境，产品代码未动。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行，调用器为本轮现写最小新文件 night2_sentinel_call.py，令牌经 SSH 现取不落盘、未读任何现成调用脚本；Go 代码、测试、页面、条形 CSS 均为微片段逐字输出口径；编排侧机械工作：片段拼接换行、F1a 长度守卫加固（`len==0` 改为 `len!=2` 后返回防下标越界）、G2 测试按包内惯例改写（`web.FS`→`FS`、`[]byte`→`string`）、导航链机械追加、CHANGELOG/README 事实性文字。
- 调用统计（batch 目录 usage.log 全量记录，含重试与空响应）：成功计 token 的调用 prompt 合计 477244、completion 合计 32357；另有 6 条错误行（429 与 IncompleteRead 重试，不计用量）与 6 条空响应行（首通探活解析 bug 致用量未捕获 1 条、F1 两次、H2 一次、H3 两次 reasoning-only 空响应，改拆小稿后均成功；G2 首通推理占满 4000 token 仅出半行签名，改 max_tokens 16000 重发成功）。注意：API 回报的单通 prompt token 约 2.4 万、远大于提示词本身长度，属服务端回报口径、此处如实记录不做折算。

## [0.21.0] - 2026-10-27

### 新增

- 全站月度 SLA 总报：`GET /api/sla?month=YYYY-MM`（需鉴权）聚合全部监控：检查加权可用性（零检查监控不计入加权分母、全部零检查时为 100）、检查总数、事件总数、宕机时长、目标 99.9、是否达标、最差监控、归因合计与占比；`GET /api/sla.html?month=YYYY-MM` 中文 HTML 导出；控制台页 `/sla-report`（月份选择、总览卡片、逐监控表、导出 HTML 链接），各控制台页导航末尾加 SLA总报链。
- Store 层 `SiteMonthlySLA` 复用单监控 `MonthlySLA`；无 schema 变更、无新环境变量。

### 测试

- 新增 `internal/store/site_sla_test.go`（空库与非法月份、90 正常+10 失败对 100 全正常加权得 95 与最差监控）与 `internal/handlers/site_sla_test.go`（JSON 的 month/monitor_count、非法月份 400、HTML 200 与“全站”字样）；`go test ./...` 16 包全绿；`go vet` 全洁。
- 真实服务冒烟（隔离库 18491 端口）：种子 2 监控 + 新建 1 up（本地 200 服务）+ 1 down（127.0.0.1:9 拒绝），各 CheckNow 2 次后 `/api/sla?month=2026-10` 返回 total_checks 8、uptime 75、最差为死端口、met false、归因 connection 100%；HTML 含两监控名与未达标；无鉴权 401、非法月份 400；`/sla-report` 页 200 且含 month-input/load-btn/report-rows。

### 已知限制

- `/sla-report` 页的浏览器内目视截图验收未在本轮完成（子智能体无 live browser 权限），需主 agent 以浏览器实测一遍真实数据页后再算终验；curl 层面的页面标记与 API 数据已实证。

### 模型稿

- 全程只走 BotsRouter，大写 GLM-5.3-Flash，令牌 id=5，单路串行，调用器为本轮现写最小新文件 night_sentinel_call.py，令牌经 SSH 现取不落盘、未读任何现成调用脚本；Go 代码与测试为规格生成稿，页面 HTML 片段因自由生成一通编造了假数据仪表盘而整通废弃，改走微片段逐字输出口径后落仓；另有 9 通 reasoning-only 空响应作废（均计入用量）。



## [0.20.12] - 2026-10-26

### 改动

**接口行为变更**  
`GET /api/monitors/{id}/checks` 的 `limit` 参数校验规则收紧：
- 改动前：`limit < 1` 静默钳制为 1，`limit > 1000` 静默钳制为 1000。
- 改动后：`limit < 1` 或 `limit > 1000` 返回 HTTP 400，错误文案为 `"limit 参数非法"`。

**未改动行为**  
- 缺省 `limit` 值保持为 100。
- `limit` 为非数字字符串时返回 400。
- 监控不存在时返回 404。

**测试同步**
- `handlers_deep2_test.go` 中原有针对钳制逻辑的测试重命名为 `TestHandleListChecksLimitValidationDeep3`，其中两处断言由 `200` 改为 `400`。
- 既有 `checks_limit_validation_test.go` 中非数字 `limit` 返回 400、合法 `limit=10` 返回 200 的用例不受影响。

**影响范围**
- 版本号：CHANGELOG 新增 [0.20.12] 一节（代码内无版本常量，版本号只记 CHANGELOG，与 0.20.11 轮一致）。
- 无 schema 变更。
- 无 UI 改动。

## [0.20.11] - 2026-10-26

### 修复

- `GET /api/status-pages/{id}/snapshots`（`internal/handlers/snapshot_archive.go` 的 `handleListSnapshots`）新增 `limit` 校验：`limit` 存在但不是整数、或小于 1 时返回 400，文案为“limit 参数非法”，与检查记录、事件、短信记录接口的校验口径一致。
- 合同变更声明：此前 `limit` 非法时静默回退为默认 50，本版起改为返回 400；缺参或空串时仍默认 50；大于等于 1 的值照旧采用，不新增上限钳制。

### 测试

- 新增 `internal/handlers/snapshot_limit_validation_test.go` 中的 `TestSnapshotListLimitValidation`：建 1 页并生成 2 条快照，limit=abc、limit=0、limit=-1 均期望 400，limit=2 期望 200 且 items 长度 2，无 limit 参数期望 200 且 items 长度 2。
- 既有快照测试同跑通过：`TestSnapshotArchiveFullCycle`、`TestSnapshotListLimit` 与新测试 3/3 全绿；`go vet ./internal/handlers/` 全洁；`gofmt` 本轮文件全洁。
- 无 UI 改动，无 schema 变更，无新环境变量。

## [0.20.10] - 2026-10-26

### 修复

- `GET /api/incidents`(`internal/handlers/handlers.go` 的 `handleListIncidents`)新增分页参数校验:`page`、`per_page`、`page_size`、`limit` 存在但不是整数时返回 400,文案分别为“page 参数非法”、“per_page 参数非法”、“page_size 参数非法”、“limit 参数非法”,与检查记录、事件 monitor_id、短信记录接口的校验口径一致。
- 合同变更声明:此前分页参数非法时静默回退(页码回退为 1、每页大小沿降级链回退为缺省 20),本版起改为返回 400;数值钳制行为不变(page<1 钳制为 1、pageSize 钳制 1~100、limit 有效时 page=1)。

### 测试

- 新增 `internal/handlers/incidents_pagination_validation_test.go` 中的 `TestHandleListIncidentsPaginationValidationDeep3`:page=abc、per_page=abc、page_size=xyz、limit=zzz 均期望 400,合法分页期望 200 且响应包含 items 数组。
- 既有锁死回退行为的测试已同步改为断言 400:`incidents_deep_r2_test.go` 的 3 个降级链测试与 page 钳制测试(去掉 page=abc 用例)、`incidents_pagination_test.go` 的 InvalidPage、`incidents_perpage_test.go` 的 PerPageInvalid、`handlers_deep2_test.go` 的 LimitClampDeep3(去掉 limit=bad 的 200 用例、另加 400 断言)。


## [0.20.9] - 2026-10-26

### 修复

- `GET /api/monitors/{id}/stats`(`internal/handlers/handlers.go` 的 `handleStats`)新增 `days` 校验:`days` 存在但不是整数时返回 400,文案为“days 参数非法”,与检查记录、事件、短信记录接口的校验口径一致。
- 合同变更声明:此前 `days` 非法时静默回退为 7,本版起改为返回 400;数值钳制行为不变(1~90)。

### 测试

- 新增 `internal/handlers/stats_days_validation_test.go` 中的 `TestHandleStatsDaysValidationDeep3`:`days=abc` 期望 400,`days=10` 期望 200 且响应包含 uptime_pct、avg_latency_ms、total_checks、down_incidents。
- 既有 `TestHandleStatsDaysClampDeep3` 已同步去掉 `days=abc` 的 200 断言(钳制用例 0/-3/9999 不变)。


## [0.20.8] - 2026-10-26

### 修复

- `GET /api/incidents`(`internal/handlers/handlers.go` 的 `handleListIncidents`)新增 `monitor_id` 校验:`monitor_id` 存在但不是整数、或为负数时返回 400,文案为“monitor_id 参数非法”,与投递列表、短信记录接口的 `monitor_id` 校验口径一致。
- 合同变更声明:此前 `monitor_id` 非法时静默回退为 0(即查询全部事件),本版起改为返回 400;事件列表的 `limit`/`page`/`page_size` 钳制行为不变。

### 测试

- 新增 `internal/handlers/incidents_monitor_validation_test.go` 中的 `TestHandleListIncidentsMonitorIDValidationDeep3`:`notanumber` 与 `-1` 均期望 400,合法监控 id 期望 200 且响应包含 items 数组。
- 既有 `TestHandleListIncidentsMonitorIDNonNumericDeep3` 已同步改为断言 400;事件 limit 钳制测试同跑通过。


## [0.20.7] - 2026-10-26

### 修复

- `GET /api/monitors/{id}/checks`（`internal/handlers/handlers.go` 的 `handleListChecks`）新增 `limit` 类型校验：`limit` 存在但不是整数时返回 400，错误文案为「limit 参数非法」；数值仍保留 1~1000 钳制。
- 校验口径与 v0.20.6 短信记录接口的 `limit` 校验保持一致。
- 合同变更声明：此前非法 `limit` 会静默回退为 100，本版起改为返回 400；数值钳制行为不变。

### 测试

- 新增 `internal/handlers/checks_limit_validation_test.go` 的 `TestHandleListChecksLimitInvalidDeep3`：`limit=abc` 期望 400，`limit=10` 期望 200 且响应含 `items` 数组。
- 既有钳制测试同跑通过（`limit=-5` 与 `limit=99999` 均仍返回 200）。


## [0.20.6] - 2026-10-26

### 新增
- internal/handlers/handlers.go 中的 `handleSMSLogAPI`（GET /api/sms/log）新增状态校验：当 `status` 参数非空且不等于 `sent`/`failed` 时返回 `400`，文案为“status 参数非法，只支持 sent/failed”。
- internal/handlers/handlers.go 中的 `handleSMSLogAPI` 校验 `limit` 参数：存在但不是整数时返回 `400`，文案为“limit 参数非法”。
- internal/handlers/handlers.go 中的 `handleSMSLogAPI` 校验 `offset` 参数：存在但不是整数时返回 `400`，文案为“offset 参数非法”。
- internal/handlers/handlers.go 中的 `handleSMSLogAPI` 校验 `monitor_id` 参数：解析失败或解析为负数时均返回 `400`，文案为“无效的监控 ID”。

### 修复
- 修复短信日志接口与投递列表接口在状态校验、`limit` 和 `monitor_id` 校验上的口径不一致问题。短信接口现与 `handleListDeliveries` 保持一致，严格返回 `400` 错误。合同变更声明：原 `internal/handlers/handlers_deep2_test.go` 中的 `TestHandleSMSLogAPIInvalidParamsDeep3` 曾期望“非法 limit/offset 回退默认值 50/0”（例如 `limit=abc&offset=xyz` 返回 `200`）。v0.20.6 起该行为改为直接返回 `400`，对应测试已同步更新为断言 `400`。这属于有意的合同变更，而非回归。

### 测试
- 新增测试文件 `internal/handlers/sms_log_validation_test.go`，包含测试函数 `TestHandleSMSLogValidation`，共 9 个子用例（status=sent/failed/非法值、limit/offset 类型非法、limit=2、monitor_id=-1、无参）全部通过。
- 全量测试套件执行 `go test ./...`，16 个包均通过，零失败。notify 包用时 239.8 秒，为现有最慢包。
- `go vet` 检查通过，无问题。
- 真实服务冒烟测试：监听端口 18471，种子创建 3 条短信记录（1 条 sent、2 条 failed）。验证矩阵如下：
  * status=sent → 200，返回 1 条记录
  * status=failed → 200，返回 2 条记录
  * status=pending → 400
  * status=SENT → 400
  * limit=abc → 400
  * offset=abc → 400
  * monitor_id=-1 → 400
  * limit=2 → 200，返回 2 条记录
  * 无参查询 → 200，返回 total 为 3
  * 无鉴权请求 → 401
  * /sms-log 页面 → 200
  * 冒烟二进制与隔离库已清理。
- 无 UI 改动，故无新截图；无 schema 变更；无新环境变量。

### 模型稿
- 代码批与测试批均由 OpenRouter 免费 lane（cohere/north-mini-code:free）输出。
- 代码批首版曾包含 `strings.TrimSpace` 等规格外改动，已机械剥离。
- 测试批首版复用了旧文件已定义的 `smsLogResp` 类型名，后经机械改名统一为 `smsLogValidationResp`；同时在 sent 用例中给 `Logs[0]` 访问增加了长度守卫。
- dpsk lane 本轮未探活；Zhipu lane 本轮因周限额于 05:07 轮触及 429，于 2026-10-30 01:14:56 重置。

## [0.20.5] - 2026-10-26

### 修复

- 全站导航互通，关闭各页导航互相缺链的缺口：monitors.html、incidents.html、deliveries.html、sms_log.html 四页导航末尾补快照归档链；index.html 与 snapshots.html 导航末尾补短信记录链；profile.html 导航末尾补短信记录链与快照归档链。
- 全部为末尾追加，既有链接顺序与 active 标记一字未动；各页首页文案（总览/仪表盘）沿用各页原有；未新建任何路由与页面。

### 测试

- 新增 internal/web/nav_reachability_test.go（3 组：四页含快照归档链；首页与快照页含短信记录链；详情页同时含短信记录链与快照归档链且顺序为投递队列在前、短信记录居中、快照归档在后）。
- 与 v0.20.4 的 nav_missing_links_test.go 及 internal/web 包全量合跑通过；go vet 全洁。

**模型稿**：只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，调用器为本轮现写最小新文件 glm53_r29_call.py，令牌经 SSH 现取不落盘、未读任何现成调用脚本：导航稿与测试稿各 1 通成功（沿用 v0.20.4 已验证的“无文件访问、原文照抄/按给定断言组装”口径）；无 429。

### 视觉验收

- 真实服务冒烟（隔离库 18436 端口）：monitors、incidents、deliveries、sms-log、snapshots、profile 与首页 / 均 200，七页响应体均含补入的新链且零 /settings；/index 返回 404 是既有路由口径（首页路由就是 /），非回归。
- 浏览器 DOM 实测监控页导航为“总览 监控管理 事件 投递队列 短信记录 快照归档”；截图存 docs/screenshots/monitors-nav-v0205.png，亲眼核对导航 6 链齐全、监控管理 active 绿下划线正常、无重叠。
- 验收后服务按端口反查真实 PID 停掉、端口已关、隔离库与二进制与临时令牌已删。

## [0.20.4] - 2026-10-26

### 修复

- 关闭 v0.20.2/v0.20.3 已知限制里挂账的缺链：`incidents.html` 与 `sms_log.html` 导航补监控管理链，`deliveries.html` 导航补监控管理链与短信记录链。
- 三页 active 标记保持在各自当前页；deliveries 页首页文案仍用该页原有的"仪表盘"。
- 其余导航与页面内容一字未动；profile/snapshots/index 三页导航集合不同（带快照归档等），不在本轮范围。

### 测试

- 新增 `internal/web/nav_missing_links_test.go`，共 3 组：事件页与短信记录页含监控管理链且顺序为总览在前、事件在后；投递页含监控管理链与短信记录链且顺序为仪表盘、监控管理、事件、投递队列 active、短信记录。
- 与 `monitors_nav_test.go`、`settings_nav_removed_test.go` 及 `internal/web` 包全量合跑通过；`go vet` 全洁；全量 16 包全部通过、零失败（notify 包约 250 秒为既存最慢包）。

#### 模型稿

模型稿（只走 BotsRouter，大写 GLM-5.3，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，调用器为本轮现写最小新文件 `glm53_r29_call.py`，令牌经 SSH 现取不落盘、未读任何现成调用脚本）：导航稿首通 4 次推理-only 空响应作废，改"无文件访问、原文照抄"口径后 1 通成功；测试稿首通 4 次推理-only 空响应作废，改"无文件访问、按给定断言组装"口径后 1 通成功；无 429。

### 视觉验收

- 真实服务冒烟（隔离库 18435 端口）：三页与监控页均 200。
- 响应体三页均含新链、零 `/settings`；浏览器 DOM 实测事件页导航为"总览 监控管理 事件 投递队列 短信记录"。
- 截图存 `docs/screenshots/incidents-nav-v0204.png`，亲眼核对导航 5 链齐全、事件 active 绿下划线正常；截图中"加载失败"为 setContent harness 下相对 `/api` 地址在 about:blank 解析失败的已知假象，非产品回归。
- 验收后服务按端口反查真实 PID 停掉、端口已关、隔离库与二进制与临时令牌已删。

## [0.20.3] - 2026-10-26
### 修复
- 关闭 v0.20.2 已知限制“/settings 仍无路由”：incidents.html、sms_log.html、deliveries.html 三页导航各删 1 行 `<a href="/settings">设置</a>` 死链；不新建 /settings 路由、不编造页面；三页其余导航与页面内容一字未动（incidents 页仍无监控管理链、deliveries 页仍无短信记录链，那是缺链不是死链，不在本轮扩面）。
- 另更新 1 处过期测试期望：design_v018_test.go 的 deliveries 自有导航断言原先含 /settings 链（v0.18 时所写），现删去该行并注明 v0.20.3 已删死链；其余断言未动。
### 测试
- 新增 internal/web/settings_nav_removed_test.go（3 组：三页均不含 "/settings"，且各自 active 标记仍在）；与 monitors_nav_test.go 及 internal/web 包全量合跑通过；go vet 全洁；gofmt 全洁（新测试文件经 gofmt -w 对齐）。
- 全量测试：16 个包全部通过、零失败（notify 包 241 秒为既存最慢包）；真实服务冒烟（隔离库 18434）：三页 200 且响应体零 "settings" 出现；其余路由 / 与 /monitors 亦 200；浏览器 DOM 实测 incidents 导航为“总览 事件 投递队列 短信记录”、deliveries 导航为“仪表盘 事件 投递队列”，均无设置项；incidents 页截图亲眼核对导航无设置项（setContent 渲染未内联样式、仅验导航文案，页内“加载失败”为 harness 未代理 /api 所致，非产品回归）。
### 模型稿
- 由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，调用器为本轮现写的最小新文件 glm53_r28_call.py，令牌经 SSH 现取不落盘、未读任何现成调用脚本）输出：测试稿 1 通即出可用正文；3 处删链为编排机械执行（每页删 1 行死链），无模型稿；无 429。

## [0.20.2] - 2026-10-26

### 修复
- 监控管理页导航死链：monitors.html 是全站唯一导航用 .html 路径的一页，其 /index.html、/monitors.html、/alerts.html、/settings.html 均无路由，点开到不了页面；本轮导航改成全站已有的 live 路由：总览 /、监控管理 /monitors（active）、事件 /incidents、投递队列 /deliveries、短信记录 /sms-log。告警与设置没有对应页面，故去掉这两项，不编造路由；JS 与页面其余部分未动。

### 测试
- 新增 internal/web/monitors_nav_test.go（5 条新链接标记齐全、4 条死链标记均不存在）；与 incidents/sms-log 容器测试合跑全绿，internal/web 包全量通过；go vet 全洁；gofmt 标出的 incidents_detail_test.go 与 web_deep_test.go 为既存漂移，本轮未动。
- 真实服务冒烟（18231 端口隔离库）：5 条新导航路由全部 200；4 条旧死链路径全部 401（非路由，鉴权中间件先拒，同样不是页面）；截图亲眼核对导航 5 链齐全、监控管理 active 下划线正常、布局无重叠；截图存 docs/screenshots/monitors-nav-v0202.png（空表为隔离库真实空态，本轮只改导航）。
- 验收后服务按端口反查 PID 停掉、端口已关、隔离库与二进制与临时令牌已删。

### 已知限制
- /settings 仍无路由：incidents/deliveries/sms-log 三页导航仍链 /settings，点开到不了页面，属全站既存问题，本轮不扩面，排期后续单独处理。

### 模型稿
- 由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，调用器为本轮现写的 flash_call_n11.py，令牌经 SSH 现取不落盘）输出：导航稿 1 通即出；测试稿首版连空 3 通作废（reasoning-only 空响应），缩小目标（去掉顺序断言）后 1 通成功；无 429。

## [0.20.1] - 2026-10-26

### 新增
- 投递记录页加监控筛选：筛选栏状态下拉后加监控 ID 输入框，查询时拼 monitor_id 参数，输入框 change 时自动重查；表格监控列此前已显示监控名，本轮不改。
- 接口层 monitor_id 参数此前已落地（delivery_deep2_test.go 已覆盖非法值 400 与按监控过滤），本轮只补页面，未动后端。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行）输出：筛选栏与 JS 各 1 通片段稿（max_tokens 4000）；页面测试 1 通因推理占满 4000 致正文 0 字作废，改 max_tokens 16000 重发成功；无 429。

### 测试
- 新增 internal/web/deliveries_monitor_test.go（监控筛选输入框、monitor_id 参数拼接、change 监听、筛选框位于状态筛选之后刷新按钮之前）；go vet 全洁；web 包与 handlers 投递测试合跑全绿。
- 真实服务冒烟（18221 端口隔离库）：种子 3 条（监控 5 两条、监控 6 一条）；未过滤 total 3、monitor_id=5 total 2 且监控列均为官网首页、abc 400“monitor_id 参数非法”；截图亲眼核对筛选框可见、过滤后仅剩监控 5 两行；验收后服务按 PID 停掉、端口已关、隔离库与二进制与临时令牌已删。

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
