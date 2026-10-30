
# 更新日志

本文件记录 linkshort 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。


## [v1.37.0] - 2026-10-31

### 新增
- 新增 11 个数值/布尔/duration 环境变量：`LINKSHORT_RATE_LIMIT_RPS`、`LINKSHORT_RATE_LIMIT_BURST`、`LINKSHORT_RATE_LIMIT_ENABLED`、`LINKSHORT_EXPORT_RATE_LIMIT_PER_MINUTE`、`LINKSHORT_BURN_PURGE_AFTER_DESTROY`、`LINKSHORT_PURGE_INTERVAL`、`LINKSHORT_PURGE_RETENTION_DAYS`、`LINKSHORT_BACKUP_MAX_AGE_DAYS`、`LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD`、`LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW`、`LINKSHORT_PASSWORD_FAIL_ALERT_IP_THRESHOLD`。非法值启动即 `log.Fatalf` 报错退出，不再静默回默认值；未设置或空串仍用默认值；范围钳制口径不变（PurgeInterval<=0 回 24h、PurgeRetentionDays<0 回 7、BackupMaxAgeDays<0 回 7、Threshold<=0 回 10、IPThreshold<=0 回 20、Window<=0 回 5m）。字符串变量、可信代理、自动生成密钥逻辑不动。

### 测试
- 新增 `config_env_strict_float_int_test.go`、`config_env_strict_bool_test.go`、`config_env_strict_duration_test.go` 四组 helper 表驱动测试。
- 旧非法回落测试已按新契约改写（Purge 保留天数负值）与删除（RateLimit 非法回落）。

## [v1.36.0] - 2026-10-29

### 新增
- `GET /api/stats/geo.csv` 的 `link_id` 参数收紧，照搬 v1.34.0 的 geo JSON 写法：缺省或空串仍默认 0（全局）；非整数（`abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "link_id 非法"}`；负数仍钳制为 0（行为不变）。仅改 `handleExportGeoCSV` 的 link_id 解析段；`days`、`handleStatsGeo`、`parseIntDefault` 一字未动。
- 注意：geo JSON 的 days 非数字回落 30 是 v1.34.0 已锁定的合同，geo.csv 的 days 同样不动（非数字仍回落 30、仅 7/30 有效），本轮不碰 days 口径。

### 测试
- 新增 `internal/handler/stats_geo_csv_linkid_validation_test.go`，函数名 TestStatsGeoCSVLinkIDValidation，7 例：`link_id=abc`、`1.5`、`1x` 返回 400 且体含“link_id 非法”；不带参数、`link_id=-5`、`link_id=1` 返回 200；`days=abc` 返回 200（days 回落口径锁定）。
- 既有 geo/geo.csv 测试不受影响（HeaderAndRowCount、NoData_HeaderOnly、DaysInvalid_FallsBackTo30、geo JSON link_id 校验均通过）；全量 `go test ./...` 14 包全过；`go vet` 全洁；改动文件 `gofmt` 全洁。
- 真实服务冒烟（18484 端口 `:memory:` 库）：无 key 返回 401；`link_id=abc`、`1.5`、`1x` 均返回错误体逐字为 `{"error": "link_id 非法"}`；`link_id=-5` 与不带参数均返回 200 且体为 CSV 表头；`days=abc` 返回 200；冒烟后服务已停、端口已关、冒烟二进制已删。

### 新增
- `GET /api/stats/hourly` 的 `link_id` 参数收紧，照搬 v1.34.0 的 geo link_id 写法：缺省或空串仍默认 0（全局）；非整数（`abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "link_id 非法"}`；负数仍钳制为 0（行为不变）。仅改 `handleStatsHourly`；`days`、`geo`、`geo.csv`、`parseIntDefault` 一字未动。

### 测试
- 新增 `internal/handler/stats_hourly_linkid_validation_test.go`，函数名 TestStatsHourlyLinkIDValidation，6 例：`link_id=abc`、`1.5`、`1x` 返回 400 且体含“link_id 非法”；不带参数、`link_id=-5`、`days=7` 返回 200。
- 既有 hourly 测试不受影响（基本、days 回落、负 linkID）与 days 校验测试全绿；全量 `go test ./...` 14 包全过；`go vet` 全洁；改动文件 `gofmt` 全洁。
- 真实服务冒烟（18483 端口 `:memory:` 库）：无 key 返回 401；`link_id=abc` 与 `1.5` 均 400 且错误体逐字为 `{"error": "link_id 非法"}`；`link_id=-5` 返回 200；不带参数返回 200；冒烟后服务已停、端口已关、冒烟二进制已删。

## [v1.34.0] - 2026-10-28

### 新增
- `GET /api/stats/geo` 的 `link_id` 参数收紧：缺省或空串仍默认 0（全局）；非整数（`abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "link_id 非法"}`；负数仍钳制为 0（行为不变）。仅改 `handleStatsGeo`；`days`、`n`、`country`、`geo.csv`、`hourly`、`parseIntDefault` 一字未动。
- 本轮曾一度把 geo 的 `days` 非数字也改成 400，后经全量测试发现既有测试 TestStatsGeoDaysFallback 与 TestGeoAPI_days非法回落30 明确锁定 days=abc 返回 200 且体 days=30，v1.33.0 轮亦已写明 geo 的 days 口径不动，故 days 已恢复原样（非数字回落 30、合法整数不在 7、30 中仍回落 30），不属本轮变更。

### 测试
- 新增 `internal/handler/stats_geo_linkid_days_validation_test.go`，函数名 TestStatsGeoLinkIDValidation，6 例：`link_id=abc`、`1.5`、`1x` 返回 400 且体含“link_id 非法”；不带参数、`link_id=-5`、`days=2` 返回 200。
- 既有 geo 回落测试不受影响（days=0/-5/100000 回落 30、n=0/101 回落 8 均通过）；全量 `go test ./...` 14 包全过；`go vet` 全洁；改动文件 `gofmt` 全洁。
- 真实服务冒烟（18482 端口 `:memory:` 库）：无 key 返回 401；`link_id=abc` 与 `1x` 均 400 且错误体逐字为 `{"error": "link_id 非法"}`；`days=abc` 返回 200 且 `days=30`（回落口径如实保留）；不带参数返回 200 且 `days=30`；`link_id=-5` 返回 200；冒烟后服务已停、端口已关、冒烟二进制已删。
- 批次质量：BotsRouter 讯飞星辰 spark-x2.6：补丁稿一次成功（首版 OLD 锚定同时命中 geo 与 geo.csv 两处被编排安全拒止后，改以函数签名锚定重派一次成功）；测试稿首版把 doJSON 第一个返回值错当状态码致编译失败、修正版漏写 srv := newTestServer(t) 一行致编译失败，两处均回喂模型修好；测试稿函数名与用例中文命名与 n 校验测试文件略有出入，不影响行为；冒烟首版鉴权头用错致全 401，改 X-API-Key 后重测通过，另 pkill -f 模式曾误杀编排自身 shell（教训：杀冒烟进程用 pkill -x 精确进程名）。

## [v1.33.0] - 2026-10-28

### 新增
- `GET /api/stats/hourly` 的 `days` 参数收紧：缺省或空串仍默认 30；非整数（`abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "days 非法"}`；合法整数但不在 1、7、30 中时仍回落为 30。
- 仅改 `handleStatsHourly`；`geo`、`geo.csv` 的 `days` 口径与 `parseIntDefault` 一字未动；文档页与 README 均无 hourly 参数行，本轮不动。

### 测试
- 新增 `internal/handler/stats_hourly_days_validation_test.go` 6 例：`days=abc`、`1.5`、`1x` 返回 400 且体含“days 非法”；不带 `days`、`days=2`、`days=7` 返回 200。
- 既有 hourly/geo 边界测试不受影响；全量 `go test ./...` 14 包全过；`go vet` 全洁；改动文件 `gofmt` 全洁。
- 真实服务冒烟（18481 端口 `:memory:` 库）：`days=abc` 与 `1.5` 均 400 且错误体逐字为 `{"error": "days 非法"}`；不带 `days` 返回 200 且 `days=30`；`days=2` 返回 200 且 `days=30`；`days=7` 返回 200 且 `days=7`；无 key 返回 401；冒烟后服务已停、端口已关、冒烟二进制已删。

## [v1.32.0] - 2026-10-27

### 新增

- `GET /api/stats/geo` 的 `n` 参数收紧：照搬 top-referers 写法，空串先默认 `"8"` 再 `strconv.Atoi`；解析失败返回 400，错误体为 `{"error": "n 非法"}`；缺省/空串仍默认 8；合法数字小于等于 0 或大于 100 时仍回落 8（钳制口径不变）。仅改 `handleStatsGeo`；`hourly`、`geo.csv`、`parseIntDefault` 一字未动。

### 测试

- 新增 `internal/handler/stats_geo_n_validation_test.go` 6 例：n=abc、n=1.5、n=1x 返回 400 且体含 "n 非法"；不带 n、n=0、n=8 返回 200。
- 既有 geo 越界/days 回落测试不受影响。

## [v1.31.0] - 2026-10-27

### 新增
- 收紧 `GET /api/stats/top-referers` 接口的 `n` 参数校验，照搬 v1.30.0 top-links 的写法：缺省或空串仍默认 8；非整数（如 `abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "n 非法"}`；合法数字小于等于 0 或大于 100 时仍回落为 8（既有钳制口径不变）。仅改 `internal/handler/handler.go` 的 `handleTopReferers`；同级端点（top-links/geo/hourly）与 `parseIntDefault` 一字未动；docs.html 的 top-referers 行无参数细节，本轮不动。

### 测试
- 新增 `internal/handler/stats_top_referers_n_validation_test.go`，`TestStatsTopReferersNValidation` 6 例（n=abc/1.5/1x 均 400 且体含“n 非法”、不带 n/n=0/n=8 均 200）。

## [v1.30.0] - 2026-10-27

### 新增
- 收紧 `GET /api/stats/top-links` 接口的 `n` 参数校验，照搬 v1.28.0 referers 的 `n` 写法：缺省或空串仍默认 8；非整数（如 `abc`、`1.5`、`1x`）返回 400，错误体为 `{"error": "n 非法"}`；合法数字小于等于 0 或大于 100 时仍回落为 8（既有钳制口径不变）。仅改 `internal/handler/handler.go` 的 `handleTopLinks`；同级端点（top-referers/geo/hourly）与 `parseIntDefault` 一字未动；docs.html 无 top-links 行，本轮不动。

### 测试
- 新增 `internal/handler/stats_top_links_n_validation_test.go`，`TestStatsTopLinksNValidation` 6 例全绿（n=abc/1.5/1x 均 400 且体含“n 非法”、不带 n/n=0/n=8 均 200）；go vet 全洁；改动文件 gofmt 全洁；本轮只跑靶向组，全量 handler 套件未跑（耗时数分钟）。
- 真实服务冒烟（18437 端口 :memory: 隔离库，admin key）：n=abc 与 n=1.5 均 400 且错误体逐字为 `{"error": "n 非法"}`、不带 n 与 n=0 均 200 且 items 为空，冒烟后服务已停、端口复查已关、冒烟二进制与日志已删。

## [v1.29.0] - 2026-10-27

### 新增
- 收紧 `GET /api/stats/daily` 接口的 `days` 参数校验：非数字字符将直接返回 HTTP 400 及 `{"error": "days 非法"}` 错误提示。
- 未传参或传入空字符串时默认维持 30 天；对于合法数值但小于等于 0 或大于 365 的入参，仍维持现有的自动回退为 30 天的钳位策略。

### 测试
- 新增 `internal/handler/stats_daily_days_validation_test.go` 测试文件，`TestStatsDailyDaysValidation` 的 6 个用例全部通过（`abc`、`1.5`、`1x` 均返回 400 及指定错误；无参数、`0`、`7` 均正常返回 200）。
- 现有回归测试（`TestLinkReferersNValidation`、`TestLinkDailyDaysValidation`、`TestAnalyticsParamClamp`、`TestAnalyticsReferersTopN`）联合运行全部通过；`go vet` 与 `gofmt` 检查均无异常。
- 本地真实服务隔离数据库冒烟测试通过：在 `127.0.0.1:18470` 环境下验证，无参数、0、7 均返回 200，`abc` 和 `1.5` 返回 400，且 `readyz` 无鉴权 Key 请求返回 401。测试完成后，服务进程已停止，端口已释放，临时数据库已删除。

## [v1.28.0] - 2026-10-27

### 新增
- `GET /api/links/{id}/referers` 的 `n` 参数校验收紧：非数字值返回 400，错误体为 `{"error": "n 非法"}`；此前非数字值经默认值回落静默按 8 条统计。缺参或空串仍默认 8；合法数字小于等于 0 或大于 100 时仍回落为 8（既有口径不变，既有 TestAnalyticsParamClamp 覆盖 n=0 与 n=200 返回 200）；docs.html 无 referers 行，本轮不动；其余统计端点（stats/daily、top-links、top-referers、geo、hourly）一字未动。

### 测试
- 新增 internal/handler/link_referers_n_validation_test.go 6 例全绿（n=abc/1.5/1x 返回 400 且体含“n 非法”、不带 n 返回 200、n=0 返回 200、n=8 返回 200）；既有 TestAnalyticsParamClamp 与 daily 校验测同跑通过；go vet 全洁；本轮改动文件 gofmt 全洁。

## [v1.27.0] - 2026-10-27

### 新增
- `GET /api/links/{id}/daily` 的 `days` 参数校验收紧：非数字值返回 400，错误体为 `{"error": "days 非法"}`；此前非数字值经默认值回落静默按 30 天统计。缺参或空串仍默认 30；合法数字小于等于 0 或大于 365 时仍回落为 30（既有口径不变）。

### 测试
- 新增 internal/handler/link_daily_days_validation_test.go 6 例全绿（days=abc/1.5/1x 返回 400 且体含“days 非法”、不带 days 返回 200、days=0 返回 200、days=7 返回 200）；既有 TestAnalyticsParamClamp 同跑通过。

## [v1.26.0] - 2026-10-27

### 新增
- `GET /api/links/{id}/qrcode.png` 的 `size` 参数校验收紧：非数字值返回 400，错误体为 `{"error": "size 非法"}`；此前非数字值经默认值回落静默按 256 生成。缺参或空串仍默认 256；小于等于 0 仍返回 400（既有行为）；链接不存在仍先返回 404。

### 测试
- 新增 internal/handler/qrcode_size_validation_test.go 4 例全绿（size=abc 返回 400、无参返回 200 且为 PNG、size=256 返回 200 且为 PNG、不存在的链接加 size=abc 返回 404）。

## [v1.25.0] - 2026-10-26

### 新增
- `GET /api/links`（`internal/handler/handler.go`）的 `sort` 为空时默认为 `created_at`；`sort` 为非法值（非 `clicks`/`created_at`/`expires_at`）时返回 400，错误体为 `{"error": "sort 非法"}`。此前 v1.23.0 记录的非法 `sort` 静默回落至创建时间排序改为返回 400；store 层原有回落保留作后置防线。
- `page`/`per_page`/`enabled`/`burn`/`expired`/`has_password` 口径未动。
- 文档 `internal/handler/web/docs.html` 的 `/api/links` 说明中 `sort` 口径由“非法值回落创建时间”更新为“缺省 `created_at`，非法值 400”。

### 测试
- `internal/handler/list_links_sort_expires_test.go` 的 `bogus` 断言由 200 改为 400，且响应体含 “sort 非法”。
- 新增 `internal/handler/list_links_sort_validation_test.go`，含 5 个子测试：`sort_bogus`、`sort_empty`、`sort_clicks`、`sort_created_at`、`sort_expires_at`。
- 全量测试：`go test ./... -race -count=1`，14 包全部通过；`go vet` 全洁；本轮改动文件 `gofmt` 全洁；真实服务冒烟（18455 隔离库）：建链 2 条，sort=bogus 400 且体含“sort 非法”，缺省 sort 与 sort=clicks 均 200，docs 页含新 sort 口径短语。

## [v1.24.0] - 2026-10-26

### 新增

- `GET /api/links` 分页参数收紧：`page` 缺省为 1，须为正整数，非法值返回 400（`page 非法`）；`per_page` 缺省为 20，合法范围 1–200，非法值返回 400（`per_page 非法`）；其余筛选与排序口径不变。
- store 层原有的分页钳制逻辑保留，作为 handler 参数校验之后的后置防线。
- API 文档页 `GET /api/links` 说明同步更新分页参数口径。

### 测试

- 新增 `internal/handler/list_links_pagination_test.go`，含 8 个子测试：`page_zero`、`page_abc`、`page_negative`、`per_page_zero`、`per_page_over`、`per_page_abc`、`valid_pagination`、`defaults`。
- 全量测试：`go test ./... -race -count=1`，14 个包全部通过；`go vet` 全洁；本轮改动文件与新文件 `gofmt` 全洁；真实服务冒烟（18451 隔离库）：建链 3 条，page=0 / per_page=201 / page=abc 均 400 且体含对应参数名，page=1&per_page=2 返回 total 3、2 条，page=2&per_page=2 返回 total 3、1 条且与前页无交集，缺省参数返回 total 3，`GET /ui/docs.html` 实测含新分页口径短语。

## [v1.23.0] - 2026-10-26

### 新增

- 链接列表支持按到期时间排序：GET /api/links?sort=expires_at 按到期时间倒序（最晚到期在前），永不过期链沉底（SQLite 下 ORDER BY expires_at DESC 会把 NULL 排最前，本轮以 (expires_at IS NULL), expires_at DESC 显式纠正）；非法 sort 值仍回落创建时间排序。排序下拉框新增“按到期时间”选项；API 文档页注明 sort 可选值与非法值回落口径。

### 测试

- 新增 internal/store/list_links_sort_expires_test.go（到期远/近/过去/永不过期四条顺序断言：far、near、past、never；非法 sort 回落且全量返回）与 internal/handler/list_links_sort_expires_test.go（sort=expires_at 返回顺序 s-far、s-near、s-never；非法 sort 返回 200）。全量测试：14 个包全部通过；go vet 全洁；本轮新文件 gofmt 全洁；真实服务冒烟（隔离库 18446）：sort=expires_at 返回顺序 s-far、s-near、s-never，非法 sort 返回 200；浏览器实测链接管理页：排序下拉已选“按到期时间”、三行顺序与冒烟一致，截图亲眼验收通过。
- 如实记录：本轮实现与两份测试文件均由编排按既有锚点机械改动——模型实现稿 1 通连空 2 次后被外层超时截断（Flash 路本时段 reasoning-only 空响应频发），未再耗通；截图走 setContent 内联+route 代带密钥 harness（Chromium 直连遭 LNA 拦截为已知环境限制）。

## [v1.22.0] - 2026-10-26

### 新增

- 链接列表支持密码筛选：GET /api/links?has_password=true 只返回已设密码链、has_password=false 只返回无密码链，不带参数返回全部；非法值返回 400（has_password 非法）；密码判定为 password_hash 非空（已设）与空或 NULL（无密码）；筛选与启用状态筛选、阅后即焚筛选、过期筛选、搜索、排序、分页组合使用时 total 与分页一致。store 新增 ListLinksFilteredEx3（enabled、burn、expired、hasPassword 四个可选指针，hasPassword=nil 时行为与旧 ListLinksFilteredEx2 一致，旧函数改为委托调用，签名不变）；列表页工具栏新增“全部密码 / 已设密码 / 无密码”下拉框，切换后回到第 1 页重载。API 文档页 GET /api/links 说明同步更新密码筛选口径。

### 测试

- 新增 internal/store/list_links_has_password_test.go（6 组断言：不过滤/仅已设密码/仅无密码/与启用筛选组合/与搜索组合/分页 total 一致且两页无交集）与 internal/handler/list_links_has_password_test.go（5 个子测试：已设密码筛选/无密码筛选/非法值 400 且体含 has_password/与启用组合/不带参数返回全部）。全量测试：14 个包全部通过；go vet 全洁；本轮新文件 gofmt 全洁（既存 gofmt 漂移文件未动）；links.js 经 node --check 通过。真实服务冒烟（隔离库 18445）：建已设密码链、已设密码已停用链、无密码链各 1 条外加无密码链 1 条共 4 条，has_password=true 只返已设密码链 total=2、has_password=false 只返无密码链 total=2、has_password=true 与 enabled=false 组合只返已设密码已停用链 total=1、非法值 400（has_password 非法）、不带参数返全部 total=4；浏览器实测链接管理页：默认 4 行、选“已设密码”后剩 2 行（pw2/pw1，均标密码保护），两张真实截图亲眼验收通过（下拉框位置正确、行数据与冒烟一致）。
- 如实记录：实现稿（store+handler）由 BotsRouter 大写 GLM-5.3-Flash 一通出稿，落仓时纠正 1 处与原文不符的错误包装文案（scan links 改回 iterate links）；前端下拉框与文档行由编排按既有锚点机械改动；两份测试文件由编排照过期筛选测试骨架机械写成——模型测试稿 3 通均未成交（第 1 通只交元文本、第 2 通 reasoning-only 空响应后第 2 次重试亦空、第 3 通被外层 280 秒超时截断），未再耗通；截图走 setContent 内联+route 代带密钥 harness（Chromium 152 直连 127.0.0.1/localhost 均遭 LNA 拦截，属已知环境限制）。

## [v1.21.0] - 2026-10-26

### 新增

- 链接列表支持过期筛选：GET /api/links?expired=true 只返回已过期链、expired=false 只返回未过期链（含永不过期），不带参数返回全部；非法值返回 400（expired 非法）；过期判定与跳转一致（expires_at 早于当前时刻为已过期，等于当前时刻算未过期）；筛选与启用状态筛选、搜索、排序、分页组合使用时 total 与分页一致。store 新增 ListLinksFilteredEx2（enabled、burn、expired 三个可选指针，expired=nil 时行为与旧 ListLinksFilteredEx 一致，旧函数改为委托调用，签名不变）；列表页工具栏新增“全部有效期 / 已过期 / 未过期”下拉框，切换后回到第 1 页重载。API 文档页 GET /api/links 说明同步更新过期筛选口径。

### 测试

- 新增 internal/store/list_links_expired_test.go（6 组断言：不过滤/仅已过期/仅未过期/与启用筛选组合/与搜索组合/分页 total 一致且两页无交集）与 internal/handler/list_links_expired_test.go（5 个子测试：已过期筛选/未过期筛选/非法值 400 且体含 expired/与启用组合/不带参数返回全部）。全量测试：14 个包全部通过；go vet/gofmt 全洁；links.js 经 node --check 通过。真实服务冒烟（隔离库 18433）：建已过期链、已过期已停用链、未过期链、永不过期链各 1 条，expired=true 只返已过期链 total=2、expired=false 只返未过期链 total=2、expired=true 与 enabled=false 组合只返已过期已停用链 total=1、非法值 400（expired 非法）、不带参数返全部 total=4；浏览器实测链接管理页：默认 4 行、选“已过期”后剩 2 行，真实截图亲眼验收通过。

## [v1.20.0] - 2026-10-26

### 新增
- 链接列表支持阅后即焚筛选：`GET /api/links?burn=true` 只返回阅后即焚链、`burn=false` 只返回普通链，不带参数返回全部；非法值返回 400（`burn 非法`）；筛选与启用状态筛选、搜索、排序、分页组合使用时 total 与分页一致。store 新增 `ListLinksFilteredEx`（enabled 与 burn 两个可选指针，burn=nil 时行为与旧 `ListLinksFiltered` 一致，旧函数改为委托调用，签名不变）；列表页工具栏新增"全部类型 / 阅后即焚 / 普通链接"下拉框，切换后回到第 1 页重载。
- API 文档页 `GET /api/links` 说明同步更新阅后即焚筛选口径。

### 测试
- 新增 `internal/store/list_links_burn_test.go`（7 组断言：不过滤/仅阅后即焚/仅普通/与启用筛选两组合/与搜索组合/分页 total 一致且两页无交集）与 `internal/handler/list_links_burn_test.go`（5 个子测试：阅后即焚筛选/普通筛选/非法值 400/与启用组合/不带参数返回全部）。
- 全量测试：14 个包全部通过（handler 包 36 秒、store 包 5 秒，其余包均通过）；`go vet`/`gofmt` 全洁；`links.js` 经 `node --check` 通过。真实服务冒烟（18431/18432 隔离库）：建阅后即焚链、普通链、已停用阅后即焚链各 1 条，burn=true 只返阅后即焚链 total=2、burn=false 只返普通链 total=1、burn=true 与 enabled=false 组合只返已停用阅后即焚链 total=1、非法值 400（burn 非法）、不带参数返全部 total=3；浏览器实测链接管理页：默认 3 行、选"阅后即焚"后剩 2 行（burndis、burn1），两张真实截图亲眼验收通过（下拉框位置正确、行数据与冒烟一致）。

## [v1.19.0] - 2026-10-26

### 新增
- 链接列表支持启用状态筛选：`GET /api/links?enabled=true` 只返回启用链、`enabled=false` 只返回停用链，不带参数返回全部；非法值返回 400（`enabled 非法`）；筛选与搜索、排序、分页组合使用时 total 与分页一致。store 新增 `ListLinksFiltered`（enabled=nil 时行为与旧 `ListLinks` 一致，旧函数改为委托调用，签名不变）；列表页工具栏新增"全部状态 / 启用中 / 已停用"下拉框，切换后回到第 1 页重载。
- API 文档页 `GET /api/links` 说明同步更新启用筛选口径。

### 测试
- 新增 `internal/store/list_links_enabled_test.go`（5 例：不过滤/仅启用/仅停用/与搜索组合/分页 total 一致无交集）与 `internal/handler/list_links_enabled_test.go`（4 例：启用筛选/停用筛选/非法值 400/不带参数返回全部）。
- 全量测试：14 个包全部通过（handler 包 108 秒、store 包 12 秒，其余包均通过）；新增测试：store 1 个测试函数含 5 组断言、handler 1 个测试函数含 4 个子测试，全部通过。真实服务冒烟（18419 端口隔离库）：建启用链与停用链各 1 条，enabled=true 只返启用链 total=1、enabled=false 只返停用链 total=1、不带参数返全部 total=2、非法值 400（enabled 非法）、enabled=false 与 search 组合只返停用链；链接管理页截图亲眼验收通过（下拉框位置正确、2 行真实数据、启用勾选状态与冒烟一致）。

## [v1.18.0] - 2026-10-25

### 新增
- 批量页支持逐项密码：行格式改为 URL [自定义短码] [逐项密码]，第三段即逐项密码；逐项密码优先于统一密码，统一密码只应用于未逐项设密码的条目；结果表密码列按提交时记录的逐项/统一密码标记显示已设或横线，密码明文永不回显。由此关闭 v1.17.1 已知限制“批量页仍不支持逐项不同密码”。API 层逐项密码口径自 v1.16.0 已落地，本轮只改批量页前端与文案，未动 API。
- 编排修正 2 处（模型稿按仓库实测核对后改动，如实记录）：①模型第 1 通正则写成双反斜杠，落仓时改回单反斜杠；②模型第 2 通用响应体 item.password 判已设，但批量响应体根本无 password 字段，改用提交时记录的 sentPw[item.index] 判定。

### 测试
- 新增 `internal/handler/bulk_peritem_password_test.go`：三段正则、逐项优先、sentPw 记录与渲染、密码绝不进 DOM 文本/HTML 断言；与 v1.17.0/v1.17.1 及批量密码旧测合跑全绿。
- 真实服务验收（18118 端口，隔离库）：批量 POST 3 条（两条逐项密码各不相同、一条无密码）全部 201 且响应无明文；v118a 错密码 401、对密码 302 跳转目标；v118b 用 v118a 的密码 401，证明逐项密码互不通用；无密码条直接 302。批量页截图亲眼核对：新格式提示与统一密码新口径齐全、无重叠；截图顶部密钥横幅是 setContent  harness 无密钥所致，真实浏览器设密钥后隐藏。
- node --check bulk.js 通过；gofmt 新测文件全洁。

### 已知限制
- 逐项密码写在行末明文段里，提交前在输入框可见，属批量粘贴的固有形态；提交后结果表只显示已设或横线，不回显。

## [v1.17.1] - 2026-10-25

### 新增
- API 文档页并入设计层：`docs.html` 在内联样式块之后引用 `/ui/assets/css/design-v117.css`（此前只引 `style.css`，v1.17.0 已知限制所记缺口至此关闭）；设计层补 3 条文档页规则——文档标题 28px/600、二级标题 16px/600、文档表头 13px/600 且无字距、无大写转换，与其余 6 页表头口径一致。原内联样式与文档正文一字未动。

### 测试
- 新增 `internal/handler/docs_design_test.go`：文档页引用设计层、设计层在内联样式块之后、设计层在 `style.css` 之后、3 个文档选择器齐全。
- `go test ./internal/handler/ -run 'TestDocsPageDesignLayer|TestV117'` 全绿（见验收）。

## [v1.17.0] - 2026-10-25

### 新增
- 批量建链 Web UI 补统一访问密码：批量页新增“统一访问密码（选填）”密码框，填了则应用于本批全部条目（`POST /api/links/batch` 每项带 `password`，复用 v1.16.0 已落地的逐项密码口径与策略）；结果表新增“密码”列，只显示“已设 / —”，密码明文永不回显。诚实边界：批量页只支持统一密码，不同条目要不同密码请走单条新建或直接调 API；v1.16.0 文档“批量 Web UI 无密码输入框”缺口至此对统一密码场景关闭。
- 前端美化设计层 `web/assets/css/design-v117.css`（在 `style.css` 之后加载，6 个页面均引用）：快递面单 / 邮政标签体系不变，只修首屏毛病——顶栏标题与面板标题改 600、无字距；表格表头 600、次级字、无大写转换；侧栏激活态由整块墨底改成邮戳红左缘 3px 加淡红底；主按钮与输入框焦点环统一 2px 邮戳红。去 AI 味自查：无新渐变、无辉光、无衬线正文、无 emoji、无居中英雄区。

### 测试
- 新增 `internal/handler/design_v117_test.go`：设计层覆盖与禁令断言、6 页均引用设计层且在 `style.css` 之后、批量密码字段与结果列断言、批量 JS 送 `password` 且只渲染“已设”不回显明文。
- `go test ./internal/handler/ -run 'TestV117|TestBatch'` 全绿；`bulk.js` 经 `node --check` 通过。
- 真实服务视觉验收（18091 端口，演示库 11 条 + 本轮新造 2 条共 13 条）：仪表盘截图真实数据（短链总数 13、总点击 1、启用中 13、30 天点击柱 1 根），批量页截图密码框与提示齐全，侧栏激活态红左缘、文字无移位、无重叠错位；验收后服务已停，演示库未入提交。批量密码端到端：带密码条目详情 `has_password=true`、无密码为 `false`，错密码访问 401。

### 已知限制
- ~~批量页仍不支持逐项不同密码~~（v1.18.0 已关闭：行末第三段即逐项密码）；~~`docs.html` 未引用设计层~~（v1.17.1 已关闭）。

## [v1.16.0] - 2026-10-25

### 新增

- 批量建链支持逐项密码：`POST /api/links/batch` 每项的 `password` 不再拒单，复用单条建链口径——先 `auth.ValidPasswordPolicy` + `auth.HashPassword`，策略失败则该项失败、不建链；建链后 `st.SetLinkPassword`，设密码失败则 `st.DeleteLink` 回滚该条、该项失败，不影响同批其他项；成功项形状不变，响应与详情均不回显密码明文，密码只以 bcrypt 哈希落库。由此关闭 v1.13.0 文档中“批量暂不支持密码”的缺口（仅 API 层；批量 Web UI 仍无密码输入框，本轮未改）。
- 公开 API 文档页 `POST /api/links/batch` 说明同步更新。

### 测试

- 新增 `internal/handler/batch_create_password_test.go`（3 例）：带密码与无密码混批全部成功且详情 `has_password=true`、响应不含明文；密码超 128 字符该项失败、其他项照常成功（207）；带密码链先出密码门、错密码 401、对密码 302 到目标。
- 旧 `TestBatch_Password` 语义更新：密码项不再拒单，改为断言 201 成功（深测见新文件）。

## [v1.15.0] - 2026-10-25

### 新增

- CSV 导出额外限流：`GET /api/export.csv` 与 `GET /api/stats/geo.csv` 共用一个独立的慢速令牌桶（默认 `LINKSHORT_EXPORT_RATE_LIMIT_PER_MINUTE=10`，即每分钟 10 次、桶容量 10，按 IP + API Key 分桶），叠加在全局限流之上；超限返回 429 JSON `{"error": "rate limit exceeded"}` + `Retry-After`（秒数 = 60 / 每分钟限额，最小 1），拒绝计入既有指标 `linkshort_rate_limit_rejected_total`。仅当全局限流开启且该值 > 0 时生效；设为 `<=0` 即关闭导出额外限流（全局限流仍在）。
- `GET /api/meta` 新增 `export_rate_limit_per_minute` 字段，暴露当前导出限额。
- 关闭 v1.9 已知缺口“CSV 导出除 API 鉴权外无额外限流”。

### 测试

- 新增 `internal/handler/handler_export_ratelimit_test.go`（6 例）：每分钟 2 次时第 3 次导出 429 且 `Retry-After: 30`；地域 CSV 与全量导出共用同一桶；限额为 0 时不限流；全局限流关闭时导出不限流；导出限流不影响 `/api/links` 与 `/api/meta`；meta 字段值与配置一致。6/6 全绿。

## [v1.14.0] - 2026-10-25

### 新增

- `store.BackfillBurnedAt()`：在定时清理每轮删除前先执行，回填口径为 `burn = 1 AND enabled = 0 AND burned_at IS NULL`；回填值取该链最后一次访问时间，若无访问记录则回退 `updated_at`；回填失败记日志并跳过本轮删除（fail-closed），回填成功记一条回填日志；删除仍按保留期 cutoff 执行，不会立即删除刚回填的行。由此关闭自 v1.5 挂账的已知缺口：v1.5 之前销毁的 burn 链缺少 burned_at，导致定时清理永远跳过它们。

### 测试
- 新增 `internal/store/backfill_test.go`（5 例）：
- `TestBackfillBurnedAtUsesLastVisit`：回填返回 1，BurnedAt 等于较晚的访问时间 t2，再调一次返回 0。
- `TestBackfillBurnedAtFallsBackToUpdatedAt`：回填返回 1，BurnedAt 非空（只断言非空，不声称等于 updated_at）。
- `TestBackfillBurnedAtSkipsEnabledBurnLink`：回填返回 0，BurnedAt 仍为 nil。
- `TestBackfillBurnedAtSkipsNonBurnLink`：回填返回 0。
- `TestBackfillBurnedAtKeepsExistingAndIdempotent`：已有 burned_at 的行回填返回 0 且 BurnedAt 不变，二次调用返回 0。

## [v1.13.1] - 2026-10-24

### 安全
- 可信代理配置 `LINKSHORT_TRUSTED_PROXIES`（逗号分隔的 IP/CIDR，默认空）：`clientIP` 只在直连接入方（RemoteAddr）落在可信名单内时才信任 `X-Forwarded-For`/`X-Real-IP`，否则一律回退到 `RemoteAddr`；关闭 v1.12.0 已知缺口"攻击者伪造 XFF 稀释 IP 告警计数"。非法配置项导致启动直接报错退出（fail-closed）。
- 默认行为变更：此前无条件信任 XFF/X-Real-IP；升级后若服务跑在反向代理之后，必须把代理 IP 配进 `LINKSHORT_TRUSTED_PROXIES`，否则地域统计与 IP 告警将按代理 IP 聚合。
- **真 bug 修复**：chi 的 `middleware.RealIP` 会无条件用 XFF 改写 `RemoteAddr`，导致上述可信代理检查在中间件阶段即被绕过（冒烟实测：伪造 XFF 的请求在日志里显示 `from <伪造IP>`），且限流器按被污染的 RemoteAddr 分桶、可被 XFF 轮换绕过。已移除该中间件；限流器改走调用方注入的信任代理感知 IP 函数（`rl.IPFunc = clientIP`），与告警/统计口径统一。

### 测试
- 新增 17 例：config 7（空输入/混合 IP+CIDR/非法项指明/空项跳过/nil 名单/FromEnv 默认/FromEnv 解析）、handler 7（不可信对端忽略伪造 XFF/可信对端取 XFF 首段/可信对端 X-Real-IP 回退/非法头回退/nil cfg/CIDR 范围判定）、ratelimit 3（IPFunc 合并分桶/默认忽略伪造 XFF/nil 回退）；旧 `TestClientIPHeaderPrecedence` 2 处调用点适配新签名；`go test ./... -race` 14 包全绿。

## [v1.13.0] - 2026-10-24


### 新增
- 批量建链 Web UI（`/ui/bulk.html`）：textarea 每行一条 URL（URL 后空一格可加自定义短码），调用 `POST /api/links/batch`，逐项展示短链/状态/错误，支持一键复制全部成功短链；207 部分成功按项如实展示。
- 公开 API 文档页补 `POST /api/links/batch` 端点说明（上限 100 条、201/207/400 语义、暂不支持密码）。

### 修复
- 批量 API 成功项新增 `short_url`（服务端用 `shortBaseURL` 拼好，与单条创建接口一致）；修复此前成功项返回请求原文 slug、自动生成短码时返回空字符串的 bug（改为 `GetLink` 取真实值），前端不再依赖 `location.origin` 拼地址。

### 说明
- 批量 API 本体（wave5，2026-10-21）与深测此前已合入，本轮补齐迟到的文档与 Web UI。

## [v1.12.1] - 2026-10-22

### 测试
- 访问画像端点边界深测 `internal/handler/handler_analytics_deep_test.go` 6 例全绿：按日 PV/UV 真实跳转计数、referer TopN 分组、UA 家族分组求和、days/n 参数钳制、stats/overview 烟雾、非法 id 400。

## [v1.12.0] - 2026-10-22

### 新增
- 密码失败告警新增 IP 维度聚合：`Tracker.RecordIPFail` 按客户端 IP 做独立滑动窗口计数（窗口复用 `LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW`），同一 IP 在窗口内密码失败达到 `LINKSHORT_PASSWORD_FAIL_ALERT_IP_THRESHOLD`（默认 20）时触发一次；跨越触发/不重复/回落重布防语义与 slug 维度一致，两维度互不干扰。
- webhook 支持多地址：`LINKSHORT_ALERT_WEBHOOK_URL` 支持逗号分隔多个 URL（空格自动 trim、空项剔除、去重保序），告警逐个 POST；单个地址失败只记日志不影响其他地址。
- webhook payload 新增 `scope`（"slug"/"ip"）与 `ip_hash`（IP 的 sha256 hex 前 16 位，`omitempty`）；IP 维度告警的 `slug` 为空。日志与 payload 中不出现原始 IP 明文。

### 测试
- 新增 `passalert_ip_test.go`（8 例）、`notify_ip_test.go`（4 例）、`config_webhook_test.go`（6 例）、`password_alert_ip_test.go`（3 例）。

### 已知缺口

- ~~IP 维度聚合基于 `clientIP`（X-Forwarded-For 首个 → X-Real-IP → RemoteAddr）；若前置代理未 strip 不可信的 XFF，攻击者可伪造 IP 稀释计数（与既有限流同假设）。~~（v1.13.1 已关闭：引入 `LINKSHORT_TRUSTED_PROXIES` 可信代理名单，默认不再信任 XFF 头）

## [v1.11.0] - 2026-10-20

### 新增
- 新增访问画像 API：`GET /api/links/{id}/ua` 返回 `{total, devices[{name,count,pct}], browsers[...], os[...], crawler_count}`；`Store.UAStats` 纯 Go 分类（设备：手机/桌面/平板/爬虫/未知；浏览器：Chrome/Edge/Firefox/Safari/微信/QQ/其他；OS：Windows/macOS/Android/iOS/Linux/其他）。
- 详情页新增“访问画像”面板：24 小时分布、星期分布、终端与 UA 三组比例条、地域；地域无数据时显示“地域数据未采集”不编造；爬虫访问诚实标注。
- 新增 per-link 来源 Top：`Store.LinkTopReferers(linkID, n)` + `GET /api/links/{id}/referers`。

### 修复
- 修复详情页“来源 Top”此前误调全局接口的问题。

### 测试
- 新增 `handler_limits_deep_test.go`（9 例）：阅后即焚/限时限次边界深测全绿——max_visits=3 耗尽（3 次 302 后 410、visits 恰 3 行）、过期 410、burn 一次读取后 410 且 enabled=0、burn+purge 后行删除（GET /api/links/{id} 变 404）、max_visits=1 的 20 并发抢（恰 1 个 302）、burn 10 并发（恰 1 个 302）、burn+max_visits=1 时 burn 语义胜出、burn+max_visits=5 建链 400。
- 新增 `handler_ua_test.go`（4 例）、`handler_link_referers_test.go`（3 例）、`link_top_referers_test.go`（4 例）、`ua_stats_deep_test.go`。
- `go test ./...` 全绿，`go vet` 全洁。

## [v1.10.0] - 2026-10-17


### 新增

- 密码失败高告警：`internal/passalert.Tracker` 按 slug 做滑动窗口计数（`LINKSHORT_PASSWORD_FAIL_ALERT_THRESHOLD` 默认 10 次 / `LINKSHORT_PASSWORD_FAIL_ALERT_WINDOW` 默认 5m），只在计数从阈值下方跨越到阈值及以上时触发一次：打 warn 日志 + 指标 `linkshort_password_fail_alerts_total` +1 + 异步 POST JSON 到复用的 `LINKSHORT_ALERT_WEBHOOK_URL`（10 秒超时，失败只记日志不影响主流程；URL 为空则不通知）；持续超阈值不重复触发，计数回落到阈值下方后重新布防。
- `prometheus/rules/linkshort.yml`：`LinkshortPasswordFailRateHigh`（warning，5 分钟失败速率 >0.2/s 持续 2m）与 `LinkshortPasswordFailAlertFired`（critical，应用内滑动窗口触发）。
- `docs/OPERATIONS.md`：环境变量表新增两行、`### 3.10 密码失败高告警（v1.10）`、`5.2` 新增指标说明、`5.3` 新增规则说明。

### 测试

- 新增 13 例：`passalert` 8 例（首次跨越触发/未达阈值不触发/持续超阈值不重复/窗口滑动重布防/旧事件裁剪/空 slug/默认值/并发 -race）、`notify` 3 例（空 URL 直接返回/JSON 字段/500 不抛 panic）、`handler` 2 例（webhook 只触发一次/指标 +1）；`go test./... -race` 149 例全过。

### 已知缺口

- 告警按 slug 维度聚合，未做按 IP 聚合；webhook 只支持单个 URL。

## [v1.9.0] - 2026-10-17


### 新增

- 地域分布 Web UI 面板（`/ui/geo.html`）：世界地图热力（手写 SVG，23 国简化路径，5 档着色）、国家排行（点击/独立访客/占比条，点击国家下钻看城市）、近 7 天/近 30 天切换、CSV 导出按钮；导航新增"地域分布"项。
- `GET /api/stats/geo` 升级：新增 `days`（只接受 7/30，非法回落 30）、`country`（国家码精确过滤，供下钻用）、`city` 粒度聚合、每项 `uv`（独立访客，`COUNT(DISTINCT NULLIF(ip_hash,''))`，空哈希不计）、`total_clicks`/`total_uv`。
- DB 迁移 v6→v7：`visits` 表新增 `city` 列（`TEXT NOT NULL DEFAULT ""`），老库自动 ALTER。
- `geo.Location` 新增 `City` 字段：MMDB 解析城市名（zh-CN 优先），内置表/请求头走 honest unknown，不编数据。
- 新增 `GET /api/stats/geo.csv`：地域分布 CSV 导出（BOM + encoding/csv 转义，文件名按天数区分）。

### 变更

- `store.GeoStats` 签名改为 `(linkID, days, country, n)`，返回 `GeoOverview`（Items/TotalClicks/TotalUV/UnknownPct/Days）；`RecordVisitGeo` 加 `city` 参数。无破坏性变更：旧查询参数缺省行为与 v1.8 一致。
- `unknown_pct` 口径不变（country_code 为空或 unknown 的占比，内网 lan 算已知）。

### 已知缺口

- 内置 IP 段表无城市数据，city 精度依赖 MMDB；未配置 MMDB 时城市一律 unknown。
- 世界地图为手写简化示意，非精确国界。
- ~~CSV 导出除 API 鉴权外无额外限流。~~（v1.15.0 已关闭：两处 CSV 导出共用独立慢速令牌桶，默认每分钟 10 次）

## [v1.8.0] - 2026-10-17

### 新增

- 新增 `internal/geo` 包：`china.go` 内置中国省域 IP 段抽样表，按 CIDR 最长前缀匹配，并在代码注释中诚实声明精度边界。
- 新增 `internal/geo` 包：`chain.go` 实现地域解析责任链（CDN 头 → MMDB → 内置表 → unknown），并支持 `ReloadFromEnv` 从环境变量重载解析器配置。
- 新增 `internal/geo` 包：`header.go` 负责 CDN 厂商头解析，提供 `HeaderNames`/`LookupHeader` 以适配不同厂商的客户端 IP 与地域头。
- `handler.go` 新增 `clientIP` 取址策略：`X-Forwarded-For` 首段 → `X-Real-IP` → `RemoteAddr` 去端口，并在代码中注明对上游代理的信任假设。
- `handler.go` 的 `finishRedirect` 改用 `clientIP` 计算 `ipHash`，并调用 `geo.LookupRequest(cip, r.Header.Get)` 解析地域。
- 访问记录改用 `st.RecordVisitGeo(link.ID, ipHash, ua, referer, CountryCode, CountryName, Province)` 落库地域字段。
- 新增 `GET /api/stats/geo`（`handleStatsGeo`）：按国家/省份聚合 TopN，并返回 unknown 占比。

### 变更

- 无破坏性变更；默认行为保持不变。
- 未配置 MMDB 时，地域解析走内置抽样表 + unknown 诚实降级，不影响既有短链跳转与统计链路。

### 已知缺口

- 内置 IP 段表为抽样而非全量，精确到省需配置 `LINKSHORT_GEO_MMDB`。
- anycast 段解析出的省份为运营商总部所在地，仅供参考。
- Web UI 暂无地域分布面板，API 已就绪，排期下轮。

## [v1.7.0] - 2026-10-16

### 新增

- burn 逐条 purge：`POST /api/links` 与 `PATCH /api/links/{id}` 新增 `purge` 字段；`purge=true` 仅当 burn 链接有效，非 burn 链传 `purge=true` 返回 400（"只有阅后即焚链接才能设置销毁后彻底删除"）；响应新增 `purge_after_burn` 布尔字段。
- DB 迁移 v4→v5：`links.purge_after_burn INTEGER NOT NULL DEFAULT 0`，老库自动 ALTER，老行默认 0。
- 销毁语义：逐条 `purge=true` 或全局 `LINKSHORT_BURN_PURGE_AFTER_DESTROY=true` 任一成立即彻底删除行（含 visits 级联）。
- 审计日志：`handler: 彻底删除已销毁链接 link=<id> slug=<slug> cause=per-link|env`。
- 指标复用 `linkshort_burn_links_purged_total`。
- Web UI 新建页与详情页各加一个"销毁后彻底删除"复选框（新建页仅 burn 勾选时可用）。
- `scripts/backup-drill.sh` 一键自动化演练：构建→起服务→建链（含普通/burn+purge/限次）→访问造数据→快照→backup.sh 备份→停服→删库→restore.sh --force 恢复→重启→一致性校验（links/visits/clicks 行数一致、普通链 302、限次链第 3 次 410、burn+purge 链 404、`/api/backup/health` status=ok）；用法 `backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N]`；退出码 0 通过 / 2 参数或依赖缺失 / 其他非零为某步 FAIL；演练全程 mktemp 隔离工作区不碰生产 data/ 与 backups/。
- Makefile 新增 `make drill`；OPERATIONS.md 新增 3.9 节。
- 新增 9 例测试（store 4——v4→v5 真实迁移/CreateLinkEx purge 标记/UpdateLinkEx purge 标记/PurgeLink 删行+visits 级联；handler 5——purge 非 burn 报 400/逐条 purge 302→404/默认软保留 302→410/PATCH 设 purge/全局开关仍有效）；`go test ./... -race` 104 例全过。

### 变更

- 无破坏性变更。默认行为与 v1.6.0 一致。

### 已知缺口

- ~~v1.5 之前销毁的 burn 链没有 `burned_at`，定时清理仍跳过它们（v1.5 起已知）。~~（v1.14.0 已关闭：定时清理每轮先回填 burned_at，历史行进入正常保留期口径）
- PATCH 把 burn 设为 false 时若该链 `purge=true` 会 400，需先把 purge 设 false（严格校验，有意为之）。

## [v1.6.0] - 2026-10-16


### 新增

- 备份健康自检：`GET /api/backup/health`（需 API Key）返回最近备份时间、完整性校验结果、备份份数与过期判定；无备份/上次失败/完整性未通过/超过 `LINKSHORT_BACKUP_MAX_AGE_DAYS` 天（默认 7）时 `status` 为 `degraded`（HTTP 仍 200）。
- `scripts/backup.sh` 每次运行把结果原子写入 `$BACKUP_DIR/last-backup.json`（健康端点读取的依据）；失败时若配了 `LINKSHORT_ALERT_WEBHOOK_URL` 则 POST JSON 告警（curl 10 秒超时，通知失败不影响退出码）。
- Prometheus 新增 `linkshort_backup_last_success_timestamp`（最近成功备份的 unix 秒）与 `linkshort_backup_health_status`（1 健康/0 降级）两个 gauge。
- Web UI 仪表盘新增"备份健康"面板：状态徽标（健康/降级）+ 最近备份时间 + 备份文件 + 备注。
- 新增 12 例测试（handler 7、metrics 2、backupscript 3 含 fake webhook 捕获）；`go test ./... -race` 95 例全过。

### 变更

- 无破坏性变更。`.env.example` 新增 `LINKSHORT_BACKUP_DIR` / `LINKSHORT_BACKUP_MAX_AGE_DAYS` / `LINKSHORT_ALERT_WEBHOOK_URL`。

## [v1.5.0] - 2026-10-16

### 新增

- purge 定时清理：后台 goroutine 按 `LINKSHORT_PURGE_INTERVAL`（默认 `24h`）轮询，删除销毁时间超过 `LINKSHORT_PURGE_RETENTION_DAYS`（默认 `7` 天）的已销毁 burn 短链；启动时打日志说明清理配置，优雅退出时先停清理再停 HTTP。
- DB 迁移 v3→v4：`links` 新增 `burned_at TEXT` 列（老库自动 ALTER），`MarkBurned` 销毁时写入销毁时间；清理只认 `burned_at` 非空的行，v1.5 之前销毁的历史行（`burned_at` 为 NULL）不在清理范围内。
- Prometheus 新增 `linkshort_links_purged_total`（定时清理删除数）；`GET /api/meta` 新增 `purge_interval` / `purge_retention_days` 字段。
- `GET /docs` 公开 API 文档页（无需鉴权）：邮政标签视觉，表格列出全部 22 个端点（方法/路径/鉴权/说明），随二进制内嵌发布。
- 新增 10 例测试（store 3、purge 1、config 3、metrics 1、handler 2）；`go test ./... -race` 83 例全过。

### 变更

- 无破坏性变更。默认配置下 purge 每天跑一轮、保留 7 天；v1.5 之前已销毁的 burn 链因无 `burned_at` 不会被自动清理（已知缺口见下）。

### 已知缺口

- ~~v1.5 之前销毁的 burn 链没有 `burned_at`，定时清理跳过它们；如需清理请手动删除或等后续版本补回填脚本。~~（v1.14.0 已关闭：定时清理每轮先回填 burned_at，历史行进入正常保留期口径）
- OPERATIONS.md 5.2 指标列表历史欠账：`linkshort_burn_links_purged_total`（v1.3）、`linkshort_password_attempts_total`（v1.4）之前漏记，本轮仅补记 v1.5 新增指标。

## [v1.4.0] - 2026-10-16

### 新增

- 密码保护短链：创建时可设访问密码（POST /api/links 的 `password` 字段），访问者必须在密码门页输入正确密码才能跳转。密码只存 bcrypt 哈希（golang.org/x/crypto v0.31.0），明文永不落库、不进响应、不进日志。
- `PATCH /api/links/{id}` 支持 `password`：null=不动、`""`=清除、非空=设置/修改；创建时密码落库失败会回滚整条短链，避免半吊子状态。
- 跳转语义：`GET /{slug}` 有密码返回 200 密码门页（服务端渲染，邮政标签视觉）；`POST /{slug}` 校验密码，正确 302（正常记点击、burn 链照常销毁），错误 401（不计点击、不触发阅后即焚）。密码校验在限次访问检查之前，防错误尝试耗尽次数。
- Prometheus 新增 `linkshort_password_attempts_total{result="ok"|"fail"}`；错误尝试走全局 IP 限流（默认 20 RPS）。
- Web UI：新建页"访问密码"输入框、列表"限制"列"密码保护"徽标（与其他徽标同行）、详情页"密码保护"区（状态文案+设置/清除）。
- DB 迁移 v2→v3（`password_hash TEXT`，老库自动 ALTER 升级，数据不丢）。
- 新增 15 例测试（auth 3、store 4 含 v2→v3 真实迁移、handler 8 含门页/401/302/burn 联动）；`go test ./... -race` 73 例全过。

### 变更

- 无破坏性变更。默认配置下所有行为与 v1.3 一致；`go.mod` 新增 `golang.org/x/crypto v0.31.0`（go 1.23 兼容版，未升级工具链）。

### 已知缺口

- CSV 导入导出未带密码字段：密码不可批量导入/导出（有意为之，防明文密码进 CSV）。
- 高并发 clicks 检查仍未做分布式锁（单连接串行写入缓解，v1.1 起已知）。

## [v1.3.0] - 2026-10-15


### 新增

- burn 销毁后彻底删除（可选）：环境变量 `LINKSHORT_BURN_PURGE_AFTER_DESTROY`（默认 false）。设为 true 时 burn 链首次访问 302 后行被彻底删除（visits 级联清除），之后再访 404；默认 false 保持 v1.2 行为（仅禁用、410、数据留档）。
- `GET /api/meta` 新增 `burn_purge_after_destroy` 字段；Prometheus 新增 `linkshort_burn_links_purged_total`。
- 详情页 burn 链接显示销毁行为（"销毁后彻底删除" / "销毁后仅禁用、数据留档"）。
- `scripts/backup.sh` / `scripts/restore.sh`：在线备份（sqlite3 `.backup` + integrity_check + `--keep-days` 默认 7）与恢复（`--force` 安全门、`--dry-run`、恢复前后 integrity_check、旧库 `.broken-` 快照）；`make backup` / `make restore BACKUP=...`。
- docs/OPERATIONS.md：备份恢复改走脚本 + 2026-10-15 真实演练输出归档；新增 burn purge 行为与数据影响说明。
- 新增 6 例测试（store PurgeLink 2、handler 跳转 purge 语义 2 + meta 1、metrics purged 指标 1）；`go test ./... -race` 58 例全过。

### 变更

- 无破坏性变更。默认配置下所有行为与 v1.2 一致。

### 已知缺口

- 高并发 clicks 检查仍未做分布式锁（单连接串行写入缓解）。
- restore.sh 目标 DB 不存在时提示文案小瑕疵（打印了不存在的快照路径）。

## [v1.2.0] - 2026-10-14


### 新增

- `GET /metrics`：Prometheus 文本格式，不走鉴权，零外部依赖手写 exposition。指标有 `linkshort_http_requests_total{method,route,status}`、`linkshort_redirects_total{outcome}`（ok/gone/not_found/error）、`linkshort_burn_links_burned_total`、`linkshort_rate_limit_rejected_total`、`linkshort_process_start_time_seconds`。路由 label 取 chi RoutePattern，`/{slug}` 不会按具体 slug 爆炸。
- 限流 middleware：IP + API Key 双维度令牌桶。环境变量 `LINKSHORT_RATE_LIMIT_RPS`（默认 20）、`LINKSHORT_RATE_LIMIT_BURST`（默认 40）、`LINKSHORT_RATE_LIMIT_ENABLED`（默认 true）。超限返回 429 + `{"error":"rate limit exceeded"}` + `Retry-After: 1`。`/metrics`、`/api/health`、`/api/readyz` 免限流。
- `GET /api/readyz` 就绪探针：DB ping 通返回 200，否则 503。配套新增 `store.Ping()`。
- 失败注入测试：构造已关闭 DB 的服务，验证跳转 500、建链 500、health 仍 200、readyz 503、/metrics 仍 200，且全程不 panic。
- CSV 导入导出列扩展为 7 列（slug,url,title,enabled,expires_at,max_visits,burn）。
- `docs/OPERATIONS.md` 运维手册：部署/配置/备份恢复/升级/监控/排障/限流调参。
- 新增 24 例测试（metrics_test 5、ratelimit_test 6、middleware_test 3、csv_ext_test 4、failure_test 6），`go test ./...` 与 `-race` 全过。

### 变更

- `/api/health` 语义明确为存活探针：进程活着就返回 200。
- CSV 导出表头变为 7 列；旧 5 列 CSV 仍可导入。非法组合（burn+max_visits≠1、max_visits 越界/非数字、burn 非 bool）记错跳过。

## [v1.1.0] - 2026-10-14

### 新增

- **限次访问**：链接可设置最多可访问次数 N，前 N 次返回 302，第 N+1 次返回 410"链接已达访问上限"。
- **阅后即焚**：一次性链接，首次访问返回 302，之后返回 410"链接已阅销毁"。销毁检查在禁用检查之前。
- **remaining 字段**：API 响应新增 `max_visits`、`burn`、`remaining`（剩余次数，null=不限）。
- **数据库版本化迁移**：`db.go` 使用 `PRAGMA user_version` 做版本化迁移，v1→v2 自动为老库 `ALTER` 加列，实测老数据保留。
- **Web UI**：
  - 新建页加"限次访问"输入框 + "阅后即焚"复选框（互斥联动）。
  - 列表页加"限制"列徽标（阅后即焚 / 已销毁 / 限 N 次·剩 M 次 / 不限）。
  - 详情页加"访问限制"行，支持编辑保存与清除。
- **测试**：新增 10 例。store 4 例（迁移版本与列、CreateLinkEx、MarkBurned、UpdateLinkEx）；handler 6 例（创建限次/阅后即焚、非法限次 400、限次达限 410、阅后即焚 410、已阅销毁优先于禁用 404、PATCH 限次更新/清除）。

### 变更

- `linkJSON` 新增三个字段：`max_visits`、`burn`、`remaining`。
- `POST /api/links` 接受 `max_visits`（正整数，1~1000000）、`burn`（bool）；非法组合返回 400（burn 与 max_visits≠1、max_visits≤0）。
- `PATCH /api/links` 支持 `max_visits`（数字 / null 清除）、`burn`。

### 已知缺口

- CSV 导入导出未带新字段（排期 v1.2）。
- 高并发下两次访问可能都通过 clicks 检查（单连接串行写入缓解，未做分布式锁）。
- burn 链接"销毁"后数据仍保留在库中（可查统计，彻底删除需手动删）。

## [v1.0.0] - 2026-10-13

工程化 v1：短链 CRUD/跳转/统计/二维码/导入导出/Web UI 四页。
