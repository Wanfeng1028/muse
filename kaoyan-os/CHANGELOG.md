# 更新日志

本文件记录 Kaoyan OS 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [1.24.0] - 2026-10-29

### Added
- GET /api/focus/summary/by-subject 的 days 参数越界收紧：整数小于 1 或大于 31 返回 400 { error: 'days 参数无效' }，此前静默钳制为 1 或 31；不传 days 仍统计全部历史，合法 1~31、非整数 400、错误体文案均不变，与 GET /api/focus/stats 的 v1.23.0 口径对齐。
- 改写测试 apps/server/tests/focus-summary-by-subject-days.test.ts 中锁定旧钳制语义的用例：days=0/-1/32/100/999 均返回 400，days=1/31 均返回 200。

### Notes
- 本轮模型调用走 BotsRouter 讯飞星辰 spark-x2.6。

## [1.23.0] - 2026-10-29

### Added
- GET /api/focus/stats 的 days 参数越界收紧：整数小于 1 或大于 31 返回 400 { error: 'days 参数无效' }，此前静默钳制为 1 或 31；缺省 7、合法 1~31、非整数 400、错误体文案均不变。
- 新增测试 apps/server/tests/focus-stats-days-range.test.ts，覆盖越界 0/-1/32/100 返回 400 与合法 1/31/07/缺省返回 200。
- 改写 focus-concurrency.deep3.test.ts 与 focus.deep.test.ts 中锁定旧钳制语义的 stats days 用例，预期由 200 改为 400。
- 文档 docs/API.md 同步更新 /api/focus/stats 的 days 参数说明。

### Notes
- 本轮模型调用走 BotsRouter：成稿由七牛免费版 qiniu/conatus-free 生成；讯飞星辰 spark-x2.6 两通作废（首通思考外溢未写完用例、次通在 max-tokens 内截断）；编排按逐字锚定应用并机械修正新测试稿路径一处（/focus/records 改为 /api/focus/stats）。

## [1.22.0] - 2026-10-28

### Added
- `apps/server/src/routes/settings.ts` 新增 `isValidExamDate` helper（格式正则 + Date 往返比对）；`PUT /api/settings` 的 `examDate` 分支与 `GET /api/settings` 的 `readSettings` 分支改用它。
- 行为变更：不存在的日期（2024-02-30、2023-02-29、2026-04-31、2026-13-01）PUT 返回 400 `{ error: 'invalid field: examDate' }` 且不写库；库里已存的不存在日期 GET 时回退 `DEFAULT_SETTINGS.examDate`。闰年 2024-02-29 与合法日期行为不变。`theme` 与数字字段、错误体文案、upsert 事务一字未动。

### Notes
- 模型链：本轮全部调用走 BotsRouter 讯飞星辰 spark-x2.6；编排按逐字锚定应用并修正测试稿两处列名。

## [1.21.0] - 2026-10-28

### Added

- GET /api/stats/weekly 的 start 参数增加日历往返校验，不存在的日期（2024-02-30、2023-02-29、2026-04-31）返回 400 { error: 'start 日期无效' }
- 格式错误的 start 参数仍返回 400 { error: 'start 日期格式无效' }
- start 参数缺省与合法日期的行为保持不变
- 日历校验口径与 plans.ts / mistakes.ts 的 isValidDate 对齐
- 新增测试 apps/server/tests/weekly-start-strict.test.ts，覆盖 7 个日历校验用例
- 更新 stats.deep3.test.ts 与 weekly-start-boundary.test.ts 中锁定旧语义的 2024-02-30 用例，预期响应由 200 改为 400
- 文档 API.md 同步更新 start 参数说明

### Notes

本轮模型调用走 BotsRouter 讯飞星辰 spark-x2.6，代码与测试均由其生成，编排按逐字锚定应用。

## [1.20.0] - 2026-10-28
### Added
- 后端两路正则校验：GET /api/plans/auto-schedule/preview 与 GET /api/plans/overload 的 dailyMinutes 查询串由 Number() 解析改为纯数字正则 /^-?\d+$/ 校验（60.0、0x3c、+60、带空格的 60 均返回 400 { error: 'dailyMinutes 非法' }，060 仍合法，范围 30~1440 与错误体不变）
- 新增测试 apps/server/tests/daily-minutes-strict.test.ts，13 例全绿
- 文档 API.md 四处同步（auto-schedule/preview 与 overload 的 dailyMinutes 参数行及 400 错误码行）
### Notes
- 本轮模型调用走 BotsRouter 讯飞星辰 spark-x2.6，代码与测试均由其生成，编排按逐字锚定应用并修正测试 harness 四处

## [1.19.0] - 2026-10-28
### Added
- 后端：`GET /api/mistakes/:id/source-exams` 与 `GET /api/exams/:id/related-mistakes` 的 `windowDays` 由 `Number()` 口径改用正则 `/^-?\d+$/` 校验；非法值返回 400 `{ error: 'windowDays 非法' }`，缺省 7、范围 0~90、错误体、404 顺序、查询与排序逻辑不变，并与 v1.16.0/v1.17.0/v1.18.0 的 days/months 严格口径对齐。
- 测试：新增 `apps/server/tests/window-days-strict.test.ts`，4 个用例（两路各非法表 10 值与合法表不传/07/0/90），靶向 10/10 全绿（含既有 `mistakes-exams-link.test.ts` 6 例）。
- 文档：同步 `docs/API.md` 两处 `windowDays` 严格口径说明。
### Notes
- 本轮模型调用走 BotsRouter，代码由讯飞星辰 `spark-x2.6` 生成、测试由七牛免费版 `conatus-free` 生成。

## [1.18.0] - 2026-10-27
### Added
- 后端：`GET /api/stats/heatmap` 的 months 参数改用正则 `/^-?\d+$/` 校验，非纯数字串（`1.0`、`0x2`、带空格、`+2`、空串）返回 400（错误体 `{ error: 'months 参数无效' }`）；此前 Number() 口径下 `1.0` 与 `0x2` 会静默通过返回 200，本轮与 v1.16.0/v1.17.0 的 days 参数口径对齐；范围 1..6 与缺省 3 不变。
- 测试：新增 `apps/server/tests/heatmap-months-strict.test.ts`，3 组用例覆盖 8 个输入值（`02`/`2` 返回 200，缺省返回 3）。
- 文档：`docs/API.md` 同步热力图 months 描述与错误码触发条件。
### Notes
- 本轮模型调用仅通过 BotsRouter 讯飞星辰 spark-x2.6。
## [1.17.0] - 2026-10-27
### Added
- 已验证：计划与真题分科汇总 days 测试文件 2 个 12/12 全绿；服务端 tsc --noEmit 零错；无前端改动，视觉验收不适用。
- 后端：`apps/server/src/routes/plans.ts` 的 `GET /api/plans/summary/by-subject` 与 `apps/server/src/routes/exams.ts` 的 `GET /api/exams/summary/by-subject` 统一用正则 `/^-?\d+$/` 校验 days 参数，非整数（`abc`、`1.5`、`1x`、空串）返回 400（错误体 `{ error: 'days 参数无效' }`）；保留原有整数越界钳制（`days` ≤ 0 钳制为 1，> 31 钳制为 31）与缺省语义（不传 `days` 统计全部历史）。此前两接口对非法 days 静默回落为全部历史（并对 `1.5` 做截断），与 v1.16.0 专注三接口口径不一致，本轮对齐。
- 测试：
  - `apps/server/tests/plans-summary-by-subject-days.test.ts`：原非法 abc 用例改为非法 400 用例（`abc`/`1.5`/`1x`/空串均返回 400 且错误体为 `days 参数无效`），新增不传 days 用例（统计全部历史，40 天前计划计入）。
  - `apps/server/tests/exams-summary-by-subject-days.test.ts`：原非法 abc 用例改为非法 400 用例（`abc`/`1.5`/`1x`/空串均返回 400 且错误体为 `days 参数无效`），新增不传 days 用例（统计全部历史）。
- 文档：`docs/API.md` 同步计划与真题分科汇总两处 days 描述（不传统计全部历史，非法返回 400）。

### Notes
- 本轮模型调用只走 BotsRouter 讯飞星辰 spark-x2.6。

## [1.16.0] - 2026-10-27
### Added
- 已验证：4 个专注相关测试文件 38/38 全绿；服务端 tsc --noEmit 零错；无前端改动，视觉验收不适用。
- 后端：`apps/server/src/routes/focus.ts` 统一使用正则 `/^-?\d+$/` 校验参数，非整数（`abc`、`1.5`、`1x`、空串）返回 400（错误体 `{ error: 'limit 参数无效' }` 与 `{ error: 'days 参数无效' }`）；保留原有整数越界钳制（`limit` ≤ 0 回落 50，> 500 钳制为 500；`days` ≤ 0 钳制为 1，> 31 钳制为 31）与缺省值（`limit` 50、stats `days` 7、by-subject 不传 `days` 统计全部历史）。涉及接口：
  - `GET /api/focus` 的 `limit` 参数
  - `GET /api/focus/stats` 的 `days` 参数
  - `GET /api/focus/summary/by-subject` 的 `days` 参数（注释同步更新为“不传时统计全部历史，非法 days 返回 400”）
- 测试：
  - 新增 `apps/server/tests/focus-param-validation.test.ts`，包含 10 例：`limit` 为 `abc`/`1.5`/`1x` 返回 400，`limit=2` 返回 200 长度 2；stats `days` 为 `abc`/`1.5` 返回 400，`days=7` 返回 200 长度 7；by-subject `days` 为 `abc`/`1.5` 返回 400，不传 `days` 返回 200 且 subjects 非空。
  - 同步更新 3 个旧测试文件中断言静默回落的 `abc` 用例（改为断言 400，钳制断言不变）：`focus-concurrency.deep3.test.ts`、`focus.deep.test.ts`、`focus-summary-by-subject-days.test.ts`。
- 文档：`docs/API.md` 同步 8 处，包括 `limit`/`days` 参数行、3 处错误码表新增 400 行、by-subject 描述句，以及计划与真题两处交叉引用删除与专注口径一致的说法。

### Notes
- 本轮模型调用仅通过 BotsRouter 讯飞星辰 spark-x2.6。
- 整批调用多次触发完成帽导致返回空正文（B1 整批、B2、B4a 整批各浪费一次，后拆分为微批重试成功）。
- 编排机械修正：B1a 应用时丢失换行导致合并行（已修复）；B2b 测试稿遗漏 `await` 且使用了中文科目名（已按真实 subject key 与旧文件写法修正）。

## [1.15.0] - 2026-10-27

### Added

- 后端新增 `GET /api/focus/export`：按科目筛选导出专注会话 CSV，表头 id,subject,subject_name,minutes,started_at,note,plan_id，按 started_at 升序、id 升序，note/plan_id 为空输出空串，非法 subject 返回 400；口径同其他导出（UTF-8 BOM、RFC4180 转义、Content-Type text/csv; charset=utf-8、Content-Disposition 附件下载，无筛选 kaoyan-focus.csv、有筛选 kaoyan-focus-加 subject 加 .csv），用户隔离与未登录 401 由全局认证钩子保证。
- 后端新增 `POST /api/import/focus`：专注会话 CSV 导入，必需列 subject/minutes/started_at，可选 note（缺省 null，超过 500 字记错）/plan_id（缺省 null，非空时须为正整数且为当前用户的计划，否则记错）；minutes 取整后须在 1 到 1440 之间，started_at 须以 YYYY-MM-DD 开头、长度 10 到 40、Date.parse 可解析；逐行校验与错误口径同计划导入（errors 最多 50 条、errorRows 为错误行总数、行号从 1 计含表头行），响应 200 { imported, errors, errorRows }；复用备份导入的 CSV 解析（BOM、引号转义、CRLF、表头大小写不敏感，取值一律用 Map.get）。
- 前端 api.ts 新增 exportFocusCsv / importFocusCsv 与 FocusImportResult 类型；番茄专注页页头新增「导出 CSV」按钮（按当前全部专注记录导出 kaoyan-focus.csv，Firefox 下先挂 DOM 再点击）；数据导入导出页（/data）新增「专注 CSV 导入」卡片（模板下载、文件选择、导入结果与错误列表，复用计划卡片样式与 ErrorList）。
- 新增测试 focus-export.test.ts / focus-import.test.ts，各 6 例：空库表头+BOM+text/csv、排序与中文名与空列、RFC4180 转义、筛选与非法参数 400、用户隔离、未登录 401；空 csv 400、缺列 400、混合行导入与错误行号、缺省值（note/plan_id 为 null）、非法 subject、未登录 401。
- API 文档第 3 章新增专注导出一节、第 8 章新增专注导入一节；前后端对照快照（api-route-parity）同步：调用数 59→61，计入本轮两条新路由。
- 截图：docs/screenshots/data-transfer-focus.png（真实服务 + 演示数据，/data 页专注导入卡片可见，console 零错误）、docs/screenshots/pomodoro-export.png（番茄专注页页头导出按钮可见，console 零错误）。

### Notes

- 本轮模型调用只走 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5）；专注导入稿首通 16000 预算被推理吃光、正文 0 字，改 32000 预算后出正文。
- 编排修正（非模型稿）：导入稿两块代码间的围栏行已清、import 路径由 ./backup.js 改回 ./backup、fastify.post 改回 app.post、表头处理由 map(normalizeHeader) 改回 normalizeHeader 整行（前者会把单格字符串当数组调 map 而崩溃）、行号由跳过空白行才递增改回真实行号 i+1；导出稿 req.user 改 req.user!、科目名查询改 find、查询结果断言加 as unknown 中转；导出测试的编造点已修正（new DatabaseSync 加 createDb(db) 改回 createDb(':memory:')）；前端模型稿的 Pomodoro 页头 JSX 与 DataTransfer 卡片样式按既有页面改回（计划卡片同款 dt-row/btn-ghost/btn-primary/muted 结构）。
- 上游 usage 回包里每通 prompt_tokens 约 24000，其中约 23936 为网关侧 cached_tokens（与 v1.13.0/v1.14.0 同口径），非本轮提示词本身长度；记账按回包原值汇总。

## [1.14.0] - 2026-10-27

### Added

- 后端新增 `POST /api/import/exams`：真题 CSV 导入，必需列 subject/paper/score/total_score，可选 duration_minutes（缺省 0，取整）/taken_at（缺省今天）；逐行校验（subject 合法性、score 在 0 到 total_score 之间、taken_at 严格日期），错误行记 errors（前 50 条）与 errorRows，合法行入库，响应 200 { imported, errors, errorRows }。
- 后端新增 `POST /api/import/plans`：计划 CSV 导入，必需列 date/subject/title，可选 planned_minutes（缺省 60，须 1~1440）/done（缺省 0，只接受 0/1）；逐行校验与错误口径同真题导入。
- 两路导入复用备份导入的 CSV 解析（BOM、引号转义、CRLF、表头大小写不敏感），backup.ts 的 parseCsv/isBlankRow/normalizeHeader/buildHeaderIndex/cellAt 改为导出函数；用户隔离与未登录 401 由全局认证钩子保证。
- 前端 api.ts 新增 importExamsCsv / importPlansCsv 与 ExamsImportResult / PlansImportResult 类型；数据导入导出页（/data）新增「真题 CSV 导入」与「计划 CSV 导入」两张卡片（模板下载、文件选择、导入结果与错误列表，复用错题卡片样式与 ErrorList）。
- 新增测试 exams-import.test.ts / plans-import.test.ts，各 6 例：空 csv 400、缺列 400、混合行导入与错误行号、非法 subject、缺省值（taken_at 今天 / planned_minutes 60 / done 1）、未登录 401。
- API 文档第 8 章新增两节（真题/计划导入）；前后端对照快照（api-route-parity）同步：调用数 57→59，计入本轮两条新路由。
- 截图：docs/screenshots/data-transfer-imports.png（真实服务 + 演示数据，/data 页两张新卡片均可见，console 零错误）。

### Notes

- 本轮模型调用只走 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5）；计划导入测试首通 16000 预算被推理吃光、正文 0 字，改 32000 预算后出正文。
- 编排修正（非模型稿）：真题导入表头处理改用备份解析真实的 Map 接口（模型稿误作 Record 索引）与 duration 取整改 Math.floor 对齐 POST 口径；计划导入同样改用 Map.get（模型稿误作索引致恒 400）并补 trim；两份测试的编造点已修正（auth 导入路径改回 ../src/auth、测试用登录改走 test-utils、科目中文名改 subject key、GET 断言字段改驼峰 totalScore/takenAt、计划表头 plannedMinutes 改 planned_minutes）；前端模型稿的独立函数形态改回 api 对象方法、downloadText 补齐 mime 参数、计划卡片文案纠正 planned_minutes 为可选列；文档模型稿的 errorRows 类型、Content-Type 与科目示例已按真实实现纠正。
- 上游 usage 回包里每通 prompt_tokens 约 24000，其中约 23936 为网关侧 cached_tokens（与 v1.13.0 同口径），非本轮提示词本身长度；记账按回包原值汇总。

## [1.13.0] - 2026-10-27

### Added

- 后端新增 `GET /api/mistakes/export`：按科目筛选导出错题 CSV，表头 id,subject,subject_name,title,content,analysis,mastered,created_at，mastered 输出 1/0，按 created_at 升序、id 升序，非法 subject 返回 400。
- 后端新增 `GET /api/words/export`：按来源筛选导出单词 CSV，表头 id,word,phonetic,meaning,example,source,source_name,memory_tip,repetitions,due_date，无 SRS 时 repetitions 与 due_date 为空，按 id 升序，非法 source 返回 400。
- 后端新增 `GET /api/plans/export`：按科目筛选导出计划 CSV，表头 id,date,subject,subject_name,title,planned_minutes,done,created_at，done 输出 1/0，按 date 升序、id 升序，非法 subject 返回 400。
- 三路导出统一真题导出口径：UTF-8 BOM、RFC4180 转义（逗号/双引号/换行加引号、内部双引号翻倍）、Content-Type text/csv; charset=utf-8、Content-Disposition 附件下载（带筛选时文件名含筛选值），用户隔离与未登录 401 由全局认证钩子保证。
- 前端 api.ts 新增 exportMistakesCsv / exportWordsCsv / exportPlansCsv（与 exportExamsCsv 同款 fetch + 401 处理）；错题页筛选栏、计划页页头（智能排期旁）、单词页词表管理卡片各新增「导出 CSV」按钮，导出按当前筛选（错题科目/计划科目/单词来源）走，下载文件名分别为 kaoyan-mistakes.csv / kaoyan-plans.csv / kaoyan-words.csv。
- 新增测试 mistakes-export.test.ts / words-export.test.ts / plans-export.test.ts，各 6 例：空库表头+BOM+text/csv、排序与中文名与状态列、RFC4180 转义、筛选与非法参数 400、用户隔离、未登录 401。
- API 文档新增三节（错题/单词/计划导出）；前后端对照快照（api-route-parity）同步：调用数 54→57，计入本轮三条新路由。
- 截图：docs/screenshots/plans-export.png、mistakes-export.png、words-export.png（真实服务 + 演示数据，三页导出按钮均可见，console 零错误；三路导出接口在真实服务上实测均为 200 且表头/数据行正确）。

### Notes

- 本轮模型调用只走 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5）；首通错题导出 16000 预算与 32000 预算连空两次，原始响应实测为模型只发 reasoning_content 后以 tool_calls 收尾、正文 0 字，属 reasoning-only 空响应；改在首行加“不许调用任何工具”后出正文，后续各通均沿用该首行。
- 编排修正（非模型稿）：错题导出路由路径由模型写的相对路径 /export 改为本文件全路径 /api/mistakes/export；错题导出查询结果断言加 as unknown 中转（TS2352）；前端三组处理器补真题页同款 document.body.appendChild（模型稿漏掉，Firefox 下不挂 DOM 点不动）；单词测试把模型编造的表名 word_srs 改为真实表 srs_state；api.ts 新方法缩进统一为 2 空格。
- 上游 usage 回包里每通 prompt_tokens 约 24000，其中约 23936 为网关侧 cached_tokens（首通探活小提示词亦如此），非本轮提示词本身长度；记账按回包原值汇总。

## [1.12.11] - 2026-10-26

### Added

- 后端 `GET /api/exams/summary/by-subject` 新增可选 `days` 参数：合法数字时只统计最近 N 天（含今天，按 `taken_at` 日期部分界定），N 按 1~31 钳制；不传或非法时统计全部历史，与计划、专注分科汇总 `days` 口径一致；聚合口径、科目顺序、响应字段不变；SQL 用 `substr(taken_at, 1, 10) >= rangeStart` 过滤，覆盖 ISO 日期时间与纯日期两种 `taken_at` 格式。
- 前端真题页「各科汇总」卡片新增范围切换：全部 / 近 7 天 / 今日，切换即按窗口重拉分科汇总，复用既有 `card`/`form-row`/`btn` 样式，无新增 CSS；`examSummaryBySubject` 仍为同一方法，仅加可选 `days` 参数。
- 新增 `tests/exams-summary-by-subject-days.test.ts` 5 例：`days=7` 排除 7 天前及更早、`days=1` 只含今天、`days` 超 31 钳制且 `days=100` 与 `days=31` 结果相同、非法 `days` 视为全部历史、未登录 401。

## [1.12.10] - 2026-10-26

### Added

- 后端 GET /api/plans/summary/by-subject 新增可选 days 参数：合法数字时只统计最近 N 天（含今天，按计划 date 界定），N 按 1~31 钳制；不传或非法时统计全部历史，与专注分科汇总 days 口径一致；专注分钟随计划走（窗口内计划的专注分钟计入，不另按专注开始时间过滤）。
- 前端计划页「各科汇总」卡片新增范围切换：全部 / 近 7 天 / 今日，切换即按窗口重拉分科汇总（复用既有 card/form-row/btn 样式，无新增 CSS；api 方法仍为同一个 plansBySubject，数量快照 54 不变）。
- 新增 tests/plans-summary-by-subject-days.test.ts 5 例：days=7 排除 7 天前及更早、days=1 只含今天、days 超 31 钳制且 days=100 与 days=31 结果相同、非法 days 视为全部历史、未登录 401。

## [1.12.9] - 2026-10-26

### Added

- 后端新增 `GET /api/plans/summary/by-subject`，按科目返回计划分科汇总：条数/已完成/完成率（保留四位小数）/计划分钟之和/关联专注分钟之和，仅返回有计划的科目，按 math、english、politics、major 顺序排列，全量不按日期过滤。
- 共享包新增 `PlanSubjectSummary` 与 `PlansBySubjectResponse` 类型。
- 前端计划页新增「各科汇总」卡片（复用既有 card/list/badge 样式，无新增 CSS），跟随计划增删改刷新。
- 新增 `tests/plans-summary-by-subject.test.ts` 5 例：空库/精确值与顺序及多专注会话不重复计数/零记录科目省略/用户隔离/未登录 401。
- 前后端对照快照（api-route-parity）同步：调用数 53→54，计入本轮新路由。
- 截图：docs/screenshots/plans-bysubject.png（真实服务 + 演示数据，卡片四科数值与冒烟 JSON 一致，已亲眼验收，console 零错误）。

### Notes

- 实现说明：分科汇总用计划聚合与专注分钟聚合两路分开查询再合并，避免单条 JOIN 后 COUNT(*) 把多专注会话的计划重复计数（该用例由新测试第 2 例锁定）。
- 编排修正（非模型稿）：模型首版路由用单 JOIN 聚合（条数会被扇出放大），已改两路聚合；测试文件首版编造了 4 个 import 路径与错误 URL，已按既有文件修正；前端首版把 api.ts 的 import 行误加 type 前缀，已还原。

## [1.12.8] - 2026-10-25

### Changed

- 番茄专注页重做（用户亲口指 v1.12.7 截图“丑得没边了”的返工）：计时器改成真正等宽零字距读数（72px、700 字重、tabular-nums）并加 8px 进度条作视觉锚点，不再孤零零飘在白卡里；科目与关联计划并排成一行仪器设置（标签在上、控件 44px 高撑满）；开始按钮加大到 48px 高一眼可见；分科累计改成量表行——分钟 22px 粗体突出、次数 12px 次要、条长按最高科占比、四科只用 SUBJECTS 既有色；底部统计收成单行紧凑条，页面补 32px 底部呼吸；侧栏 55 天倒计时改纯白（根因：.countdown-big 用浅色主题的深色 --text-main 落在深色侧栏上看不见，.sidebar-footer 本身也是 #5c6375 深灰）。
- 新增设计层 `design-v1128.css`（原 index.css 与 v1127 层不动，main.tsx 在 v1127 之后引用）：视觉逻辑“专注仪器”——计时是仪表读数、进度条是表盘刻度、开始按钮是主开关、分科条是各科量表；左对齐，无渐变、无 Inter 等外来字体、无居中 hero、无三栏特性格、无 emoji 图标、无阴影辉光、不用 !important。
- 番茄页 JSX 结构调整（编排机械改动，非模型稿）：计时器下方加 .pomo-progress 进度条（进度 = 已过 / 本段总长，填充色取当前科目色）；分科每行改成 .pomo-subject-bar-row 结构（科名、分钟、条形、次数四元素，条长按最高科占比），原一行文本写法废弃。

### Notes

- 本轮模型调用只走 BotsRouter 大写 GLM-5.3-Flash（令牌 id=5，单路串行，SSE 按 data: 行拼 content，prompt 首行禁思考过程）：第 1 通 max_tokens 16000 全被推理吃掉、正文 0 字（作废）；第 2 通同提示词 max_tokens 32000 才出正文 6065 字设计层（上游 prompt 35737 / completion 31111 / total 66848），落地前逐项核对：括号 40/40 平衡、禁令只出现在注释里、全部类名均在仓库真实存在或为本轮新列的 5 个类名。教训：Flash 大上下文任务用 16000 预算出不了正文，必须给到 32000 才能越过推理墙。
- 视觉验收：真实服务 + 播种专注数据截图亲眼核对，截图存 docs/screenshots/pomodoro-v1128.png（1440x900 视口）与 pomodoro-v1128-full.png（整页），验收后服务与演示库已停/已删；播种数与截图精确对上：分科数学 105 / 英语 55 / 政治 85 / 专业课 95 分钟各 2 次，今日专注 125 分钟。
- 编排第二轮修正（首张截图亲眼核对后发现的问题，非模型稿）：第一版计时仍显“25 : 00”发飘，根因是等宽字体下冒号自带左右空位、只改 letter-spacing 不够，改成计时器拆三段（分、冒号、秒），冒号单独定宽 0.45em 居中；计时 72px 改 64px、计时卡内边距与分科行距收紧后，整页在 900px 视口内完整露出底部统计条，截断问题消除。

## [1.12.8] - 2026-10-25

### Added

- 后端新增 `GET /api/exams/summary/by-subject`，按科目返回真题汇总：场次/平均分/平均得分率/最高分/最近一场/最早一场/进步幅度，仅返回有记录的科目，按数学、英语、政治、专业课 821 的顺序排列。
- 共享包新增 `ExamSubjectSummary` 与 `ExamsBySubjectResponse` 类型。
- 前端真题页新增「各科汇总」卡片（复用现有 card/list 样式，无新增 CSS），跟随新增/删除记录刷新。
- 新增 `tests/exams-summary-by-subject.test.ts` 5 例：空库/分科精确值与顺序及零记录科目省略/用户隔离 2 例/未登录 401。
- API 文档新增 `GET /api/exams/summary/by-subject` 一节。

### Fixed

- 前端调用与后端路由对照快照（api-route-parity）同步：补 1.12.5–1.12.7 轮遗漏的 `GET /api/focus/summary/by-subject` 与 `GET /api/words/summary/by-source` 两条，并计入本轮新路由 `GET /api/exams/summary/by-subject`，数量快照 50→53。

## [1.12.7] - 2026-10-25

### Added

- 后端 `GET /api/focus/summary/by-subject` 新增可选 `days` 参数：只统计最近 N 天（含今天），N 按 1~31 钳制，不传或非法时统计全部历史（与 `GET /api/focus/stats` 同款钳制口径）。
- 前端番茄专注页「各科专注累计」卡片上方新增范围切换：全部 / 近 7 天 / 今日，切换即重新拉取分科汇总。
- 前端番茄页新增设计层 `design-v1127.css`（原样式表不动，main.tsx 在 index.css 之后引用）：专注台仪表视觉逻辑——左对齐、计时数字等宽 64px/800 字重、模式标签小号墨色细边框、主按钮去辉光、卡片去阴影只留 1px 细边、窗口切换激活态为墨底白字；无渐变、无阴影、无外来字体、无 emoji、无居中 hero。设计层计时器部分稿件由 GLM-5.3 微批产出，编排剪掉不存在的类名与未定义变量后落仓，其余行（科目/计划行、统计卡、窗口切换）为编排按同一视觉逻辑补写。
- 新增 `tests/focus-summary-by-subject-days.test.ts` 4 例：days=1 排除旧记录且不传 days 仍计入、days 超 31 钳制与非法 days 视为全部历史、窗口内用户隔离、未登录 401。
- API 文档 `GET /api/focus/summary/by-subject` 一节补 `days` 参数说明。

## [1.12.6] - 2026-10-25

### Added

- 后端新增 `GET /api/focus/summary/by-subject`，按科目返回专注汇总：sessions（记录条数）/totalMinutes，仅返回有专注记录的科目，按数学、英语、政治、专业课 821 的顺序排列。
- 共享包新增 `FocusSubjectSummary` 与 `FocusBySubjectResponse` 类型。
- 前端番茄专注页新增「各科专注累计」卡片（复用现有 card/list/list-item 样式，无新增 CSS），跟随专注落库刷新。
- 新增 `tests/focus-summary-by-subject.test.ts` 4 例：空库、分科精确值与顺序及零记录科目省略、用户隔离、未登录 401。
- API 文档新增 `GET /api/focus/summary/by-subject` 一节。

## [1.12.5] - 2026-10-25

### Added

- 后端新增 `GET /api/words/summary/by-source`，按来源返回单词汇总：total/due（有 SRS 且 due_date <= 今天）/notStarted（无 SRS 状态），仅返回有单词的来源，按内置、核心500词库、手动录入、CSV导入的顺序排列。
- 共享包新增 `WordSourceSummary` 与 `WordsBySourceResponse` 类型。
- 前端词库页新增「按来源汇总」卡片（复用现有 card/list/list-item 样式，无新增 CSS），跟随导入/复习操作刷新。
- 新增 `tests/words-summary-by-source.test.ts` 4 例：空库、分来源统计精确值与顺序及零词来源省略、用户隔离、未登录 401。
- API 文档新增 `GET /api/words/summary/by-source` 一节。

## [1.12.4] - 2026-10-25

### Added

- 后端新增 `GET /api/mistakes/summary/by-subject`，按科目返回错题掌握率汇总：仅返回有错题的科目，按数学、英语、政治、专业课 821 的顺序排列，掌握率与单科汇总同一舍入口径（4 位小数）。
- 共享包新增 `MistakeSubjectSummary` 与 `MistakesBySubjectResponse` 类型。
- 前端错题页新增「各科掌握情况」卡片（复用现有 card/list/list-item 样式，无新增 CSS），跟随汇总卡片展示，不跟随科目筛选。
- 新增 `tests/mistakes-summary-by-subject.test.ts` 4 例：空库、科目顺序与零错题科目省略、用户隔离、未登录 401。

## [1.12.3] - 2026-10-25

### Added

- 后端新增 `GET /api/plans/overdue`，返回当前用户 date 小于服务端今天且 done 为 false 的计划，按 date 升序、id 升序排列。
- 前端复习计划页顶部新增逾期区，count 大于 0 才显示，每项可一键标为完成（复用 PATCH /api/plans/:id）。
- 测试 plans-overdue.test.ts 共 7 例：逾期纳入、已完成排除、今天与未来排除、排序、用户隔离、空库、未登录 401。

## [1.12.2] - 2026-10-24

### Added

- 前端接线后端已有的 POST /api/words/import：apps/web/src/api.ts 新增 WordImportItem/WordImportResult 类型与 importWordsJson 方法；核心词库页（/vocab）新增 JSON 批量导入卡片，粘贴单词数组或 { words: [...] } 均可导入，客户端 JSON 解析失败先行报错不发请求，成功后显示导入数/已有跳过数/无效数与逐条错误并刷新列表与词库状态。
- 截图 harness 路由顺序铁律 P1-2 闭环：shot-harness.mjs 静态与 /api 两路注册点加注释（Playwright 后注册优先）；docs/SCREENSHOT_HARNESS.md 该节措辞纠正为 Playwright context.route 顺序并注明颠倒症状；self-check.mjs 新增第 6 项源码顺序断言；新增 scripts/shots/route-order-probe.mjs 浏览器实测探针。

## [1.12.1] - 2026-10-22

### 测试
- 新增关键路径 E2E 冒烟 `scripts/e2e-keypaths-smoke.mjs`：注册登录、备份导出、备份合并回导、非法备份导入 400、单词播种幂等、热力图、周报，共 7 步；真实服务全绿（`KEYPATHS E2E OK`）。

## [1.12.0] - 2026-10-20

### Added

- 智能排期 v2（甘特周视图）：后端 apps/server/src/schedule-stats.ts 纯函数 kindOf（标题含"智能排期·"+"新学"/"复习"判 kind）与 computeDayLoads（连续 N 天 DayLoad：items 按分钟降序、totalMinutes 求和、overloaded = 总和 > dailyMinutes）；GET /api/plans/range?from&to（区间≤62 天，400 全覆盖）与 GET /api/plans/overload?weekStart&dailyMinutes（7 天负荷 + overloadedDays）；packages/shared 新增 PlansRangeQuery/DayLoadItem/DayLoad/OverloadResponse。前端 /plans/gantt：7 列周视图（周一..周日），新学实心/复习描边/手动灰三色块，已完成半透明删除线，列头总分钟数 + 超负荷标签 + 顶部预警条，HTML5 拖拽改日期（PATCH /api/plans/:id），图例齐备；gantt- 全套 CSS 浅/深两套。测试：tests/plans-range-overload.test.ts 18 例（纯函数 6 + range 6 + overload 6，含 overloaded 边界"等于不算超"、用户隔离、62/63 天边界）。
- 错题本"一键组卷"：POST /api/mistakes/quiz/generate（subject/unmasteredOnly 缺省 true/from/to/limit 缺省 20 上限 100；未掌握优先排序；返回 QuizItem 不含 analysis；严格日期校验复用 plans.ts 同款 isValidDate 语义）与 POST /api/mistakes/quiz/grade（results 非空≤200、无重复 id、全量预校验后原子写库；correct=true→mastered=1、false→0；updatedIds 只含实际变化的 id 升序）；packages/shared 新增 QuizItem/QuizGenerateInput/QuizGradeInput/QuizGradeResult。前端 /mistakes/quiz 三段式（组卷条件→自评答题→成绩回写），打印样式 @media print 适配（打印时隐藏导航/表单/自评按钮）。测试：tests/mistakes-quiz.test.ts 16 例（含 404 原子性：混入非法 id 时全不更新；跨用户 id 404）。
- API 契约文档：docs/API.md（10 章：认证/计划/专注/错题/单词/真题/统计/备份/设置/健康检查 + 附录 A 错误码速查 + 附录 B 同步机制说明，48 个接口标题）；tests/api-docs-sync.test.ts 用 onRoute 钩子枚举全部注册路由，逐个断言文档含对应反引号标题，路由数下限 40。
- 深色模式查漏：全 11 页走查，补齐排期/组卷/甘特/打印相关深色覆盖；修 ScheduleGantt 行内硬编码浅色（改走 CSS 类 + --gantt-c 变量）与 subjectLabel 读错 SUBJECTS 字段致 tooltip 显示英文 key 的真 bug。

### Fixed

- POST /api/mistakes/quiz/generate 的 from/to 曾用双反斜杠正则（`/^\\d{4}-\\d{2}-\\d{2}$/` 的字面量误写，实际匹配含反斜杠的字符串，导致带 from/to 的请求恒 400；且 '2026-13-01' 这类非法月份能通过），改为与 plans.ts 同款严格 isValidDate。
- ScheduleGantt 的 subjectLabel 误读 SUBJECTS 不存在的 label 字段，tooltip 显示 "math" 等英文 key，改为读 name。
- ScheduleGantt 的 `(SUBJECTS as Record<string, ...>)` 在 tsc 严格模式下 TS2352 编译失败，改为 find 查找。
- 深色模式走查追加修复（真机截图验收）：`apps/web/src/index.css` 的 `:root` / `[data-theme="dark"]` 声明 `color-scheme: light` / `color-scheme: dark`（原生 select/date/file 控件深色跟随，不再是白色）；`apps/web/src/App.tsx` 的 NAV_ITEMS 里 `/plans` 与 `/mistakes` 的 NavLink `end` 改为 `true`（`/plans/gantt` 与 `/mistakes/quiz` 页不再双高亮）；桌面端 `.brand` 加 `white-space: nowrap`（品牌字不再被断成"考研指/挥舱"两行）。
- 测试 bug 修复：`tests/plans-range-overload.test.ts` 的 createPlan 传 subject 中文名致 5 例 `expected 400 to be 201` 失败，改为传 subject key（math/english/politics）后 21/21 通过；`tests/api-docs-sync.test.ts` 的文档路径少一层 `../` 致 beforeAll ENOENT、3 例被 skip，修正为 `../../../docs/API.md` 后 3/3 通过。

## [1.11.0] - 2026-10-19

### Added

- 后端：focus_sessions 表新增 plan_id 列（新库建表 + 老库 ALTER 迁移 + migrateToMultiUser 重建保留该列）；POST /api/focus 接受可选 planId（非正整数 400，计划不存在或非当前用户 404），写入关联并回显；GET /api/focus 列表项含 planId；GET /api/plans/summary 新增 plans 明细（每项 id/title/subject/plannedMinutes/actualMinutes/done，actualMinutes 为关联专注分钟之和）；DELETE /api/plans/:id 先将关联专注记录的 plan_id 置 NULL 再删计划；packages/shared 新增 PlanProgress 类型，FocusSession/CreateFocusInput/PlanSummary 扩展。
- 前端：复习计划页每条计划下方新增"已专注 X/Y 分钟"达成率行 + Tabler 进度条；番茄专注页新增"关联计划"下拉（今日计划，不关联/单选，计时开始后锁定），专注结束落库时带 planId。
- 测试：tests/focus-plan-link.test.ts 8 例（关联写入读出、planId 非法 400、不存在/他人 404、summary 聚合、删计划置空、跨日期口径、不带 planId 回归）；tests/plans-autoschedule.deep3.test.ts 8 例（单日窗口/紧窗口 discarded 精确口径/dailyMinutes=30 新学全丢/顺延顶出 examDate/多用户幂等隔离/preview-POST 一致性/重复科目错峰/400 全覆盖）。

### Fixed

- 修复 v1.9.0 遗留：.mobile-nav 桌面端未隐藏导致顶部泄漏一行移动端导航，加桌面默认 display:none。

## [1.7.2] - 2026-10-18

### Added

- 后端：GET /api/mistakes/summary（可选 ?subject=，非法值 400）返回错题掌握率：total/mastered/unmastered/masteredRate（4 位小数）；packages/shared 新增 MistakeSummary 类型。
- 前端：错题页新增掌握率汇总条（全部/已掌握/未掌握/掌握率，跟随科目筛选）。
- 测试：apps/server/tests/mistakes-summary.test.ts 6 例；服务端 vitest 384/384 全绿；server/web tsc 零错。
- 另：exams-summary 边界深测 tests/exams-summary.deep.test.ts 8 例。

## [1.7.1] - 2026-10-18

### Added

- 后端：GET /api/exams/export（可选 ?subject=，非法值 400）导出真题记录为 CSV：表头 id,subject,subject_name,paper,score,total_score,rate,duration_minutes,taken_at，按 taken_at 升序；RFC4180 转义；带 BOM（Excel 直接认中文）；Content-Disposition 附件下载。
- 前端：真题页考试记录卡片新增「导出 CSV」按钮，按当前筛选科目导出并直接下载 kaoyan-exams.csv。
- 测试：apps/server/tests/exams-export.test.ts 8 例；服务端 vitest 全绿；server/web tsc 零错。

## [1.7.0] - 2026-10-18



### Added

- 后端：GET /api/exams/summary（可选?subject=，非法值 400 { error: '无效的 subject 参数'}），返回真题汇总 { subject/count/avgScore（1 位小数）/avgRate（加权平均得分率，4 位小数）/bestScore+bestTakenAt（并列取最早）/latestScore+latestTakenAt（taken_at 最晚，并列取 id 大者）/firstScore+firstTakenAt（taken_at 最早，并列取 id 小者）/improvement（最新减最早，少于 2 场为 0）}；空库时 count=0 其余数字 0、字符串 ''。
- 共享类型：packages/shared 新增 ExamSummary 接口；apps/web/src/api.ts 新增 api.examSummary(subject?)。
- 前端：真题页（/exams）在新增表单与趋势图之间新增「本阶段汇总」卡片，跟随趋势图科目筛选，展示模考场次/平均分/平均得分率/最高分（含日期）/进步幅度（正绿负红，少于 2 场显示 —）；空态大白话「还没有模考记录，先在上面记一场吧」。
- 测试：apps/server/tests/exams-summary.test.ts 8 例全绿；服务端 vitest 全量通过；server/web tsc --noEmit 零错。
- 截图：docs/screenshots/light-exams-summary.png（浅色）、docs/screenshots/dark-exams-summary.png（深色），真实演示数据、已亲眼验收。

## [1.6.0] - 2026-10-17


### Added

- 500 词词库 words-500.json 接入播种：POST /api/words/seed-vocab 现加载 7 个文件（vocab-500-a~d、words-05/words-06 共 1000 条 + src/seed/words-500.json 500 条）；120 条与旧库重复去重，空库首次播种 imported=1380、skippedExisting=120，重复调用 imported=0、skippedExisting=1500（幂等）。
- 播种核心抽为可测试的导出函数 seedVocabFromEntries(db, files) 与 getBundledVocabFiles()（apps/server/src/routes/words.ts）；非法条目不再 400 中断，改为跳过并记数（skippedInvalid + errors 明细）。
- words-500 条目无 memory_tip 字段，入库时记空字符串；旧 1000 条 memory_tip 不变。
- 测试：apps/server/tests/vocab-seed.test.ts 断言更新为 1380/120，新增 seedVocabFromEntries 坏条目容错、幂等、同批重复词用例；服务端 vitest 81/81 全绿。

## [1.5.0] - 2026-10-16

### Added

- 词库从 500 扩到 1000：新增 apps/server/src/data/words-05.json（250 词：高频动词/高频形容词副词/高频名词/熟词僻义/易混词辨析 各 50）、apps/server/src/data/words-06.json（250 词：逻辑连接词/学术写作高频词/长难句拆解关键词/完形高频词/翻译高频词 各 50）
- 每个词条字段为 word、phonetic（英式 IPA）、pos、meanings_zh（考研常考义 2-3 个）、example_en（贴近真题语境 15-25 词）+ example_zh 翻译、memory_tip（词根/谐音/辨析钩子）
- 去重：新 500 词与旧 500 词、与 seed.ts 内置 24 词逐一比对零重叠，其中 9 个撞内置词的已替换
- 后端：apps/server/src/routes/words.ts 的 POST /api/words/seed-vocab 改为加载 6 个词库文件，source 仍为 core500，幂等逻辑不变；二次调用返回 imported=0、skippedExisting=1000
- 测试：apps/server/tests/vocab-seed.test.ts 断言更新为 1000（六文件合计 1000 且 word 无重复、每文件条数 [125,125,125,125,250,250]）；服务端 vitest 全量 73/73 全绿；server/web tsc --noEmit 零错
- 前端：apps/web/src/pages/Vocab.tsx 标题与按钮文案去掉写死的"500"（改为"核心词库"/"导入词库"），词数统计改走 /api/words/vocab-status 动态值
- 截图：docs/screenshots/light-words.png、dark-words.png 按 1000 词状态重截并已验收

## [1.4.0] - 2026-10-16

### Added

- 后端：packages/shared 的 WeeklyStats 新增 2 个字段——focusMinutesByDay（7 个数，周一..周日每日专注分钟）、currentStreak（连续打卡天数，口径与热力图一致：今日有专注则从今日往前数，否则从昨日往前数）；GET /api/stats/weekly 既有参数与字段语义不变（start=YYYY-MM-DD 缺省本周一，非法值 400）。
- 前端：apps/web/src/pages/Weekly.tsx（/weekly 路由、导航「周报」不变）升级——顶部概览卡（本周专注、计划完成率、连续打卡、新增错题、模考场次）、7 天专注分钟条形、计划完成率 SVG 圆环 + 四科专注条、「和上周比一比」（专注分钟/完成率/错题/模考与上周的增减，大白话）、单词卡；深色模式跟随 data-theme；视觉延续 v1.3.0 热力图体系（蓝五档：浅 #c9e2fb→#2f74e0 / 深 #1e4068→#5b9bf3），未引入新配色与新字体。
- 测试与构建：apps/server/tests/weekly.test.ts 新增 5 例（focusMinutesByDay 长度 7 且总和等于 focusMinutes、周三补记录对应下标 +25、今天补专注后 streak≥1、-30 天孤立记录不影响 streak、start=20261012 返回 400）；服务端 vitest 55/55 全绿；前端 tsc --noEmit 零错；vite build 成功。
- 截图：docs/screenshots/light-weekly.png（浅色）、docs/screenshots/dark-weekly.png（深色），真实演示数据、已亲眼验收（布局撑满视口、无错字）。
- 备注：里程碑原计划参数为 week=YYYY-Www，实际保留了已有的 start=YYYY-MM-DD（前端已在使用且有测试覆盖，避免破坏性变更）。

## [1.3.0] - 2026-10-16

### Added

- 自律热力图。
- 后端：`packages/shared` 新增 `HeatmapDay` / `HeatmapResponse` 类型；`apps/server/src/routes/stats.ts` 新增 `GET /api/stats/heatmap?months=N`（默认 3，只接受整数 1~6，否则 400）：按天聚合专注分钟、计划总数/完成数、新增错题、模考场次，返回 currentStreak（今日为 0 则从昨日往前数）、bestStreak、activeDays。
- 前端：新增 `apps/web/src/pages/Heatmap.tsx`，路由 `/heatmap`，导航项「自律热力图」；GitHub 贡献图式热力图（列=周、行=周一..周日、月份标签、少→多图例），颜色五档蓝（浅 `#c9e2fb → #2f74e0` / 深 `#1e4068 → #5b9bf3`）；顶部当前连续打卡/最长连续/累计专注天数三卡；近 1/3/6 个月切换；格子 title 显示当日明细，点击格子展开当日详情卡（含当日专注会话列表，科目中文名）。
- 测试：`apps/server/tests/heatmap.test.ts` 新增 7 例（默认 3 个月 93 天、months=1 返回 31 天、months=0/7 返回 400、focus+45 差值、plans 完成差值、-7 天补记录 streak+1、-30 天孤立记录 streak 不变）；服务端全量 50/50 通过（vitest）；前端 `tsc --noEmit` 零错，`vite build` 成功。
- 截图：`docs/screenshots/light-heatmap.png`（热力图默认态）、`docs/screenshots/light-heatmap-detail.png`（点击 2026-10-16 当日详情态）、`docs/screenshots/dark-heatmap.png`（深色）。

## [1.2.0] - 2026-10-16


### Added

- 深色模式。
  - 后端：`packages/shared` 新增 `ThemeMode = 'light' | 'dark'`，`Settings.theme` 默认 `'light'`；`PUT /api/settings` 支持 theme，非法值返回 400。vitest 28/28 通过，其中新增 6 例：默认 light、PUT dark 后持久化、`'blue'` / 数字 `1` / `'Dark'` 三例返回 400、再切回 light。
  - 前端：`App.tsx` 侧边栏底部加主题切换按钮，文案按当前主题显示"深色模式" / "浅色模式"，无 emoji；`document.documentElement` 的 `data-theme` 属性驱动；`index.css` 新增 `[data-theme="dark"]`，覆盖全部设计 token。`tsc --noEmit` 零错，`vite build` 成功。
  - 设计体系：slate 家族，页面 #161a23、卡片 #1e2430，与既有侧边栏 #141824 同族；文字 #e6e9f0 / 次要 #9aa0ae；边框 #2a3040；科目四色深色下提亮一档保持可辨识；阴影改弱黑影。
  - 截图 14 张（7 页 × 浅/深）另加考试记录表、错题筛选态，存在 `docs/screenshots/`：`light-*.png` / `dark-*.png`（dashboard / plans / pomodoro / mistakes / words / exams / data）及 `dark-exams-table.png`、`dark-mistakes-filter.png`。

### Fixed

- `api.updateSettings` 误用 PATCH（后端只注册了 PUT），导致点主题切换按钮报 404。改为 PUT。
- `api.listMistakes` 把 `mastered=false` 当布尔串发出去，后端只认 0/1，导致仪表盘"未掌握错题"和错题筛选报 400。改为在 api 层转成 `'1'` / `'0'`。
- 真题页把 `subject=all` 透传给后端，导致 400。改为 `'all'` 转 undefined 再发。

修复后全站 API 零非 200，页面 console 零错误。

## [1.1.0] - 2026-10-15

### Added

- 后端新增 `apps/server/src/routes/backup.ts`，并在 `app.ts` 注册：
  - `GET /api/backup/export`：导出格式名 `kaoyan-backup`、`version` 1，含 plans/focus_sessions/mistakes/words/srs_state/exam_records/settings 共 7 张表。
  - `POST /api/backup/import`：body `{data, mode}`，`mode=replace|merge`，逐行校验；replace 走事务全量替换，merge 按单词去重、其余表按 id 冲突跳过。
  - `POST /api/import/words`：CSV 表头 `word,meaning` 必需，可选 `phonetic,example`；空词跳过、已存在词跳过、自动建 `srs_state` 行。
  - `POST /api/import/mistakes`：CSV 表头 `subject,title` 必需，可选 `content,analysis`；subject 仅允许 math/english/politics/major。
- 前端新增 `apps/web/src/pages/DataTransfer.tsx`，路由 `/data`，导航项「数据导入导出」：
  - 「备份与恢复」：导出备份下载 JSON，恢复支持覆盖/合并两种模式，覆盖前二次确认。
  - 「单词 CSV 导入」：支持下载模板。
  - 「错题 CSV 导入」：支持下载模板。
- `api.ts` 新增 `exportBackup`/`importBackup`/`importWordsCsv`/`importMistakesCsv`。
- 测试：`apps/server/tests/backup.test.ts` 新增 13 例；服务端全量 22/22 通过（vitest）；前端 `tsc --noEmit` 通过。
- 截图：`docs/screenshots/data-transfer.png`（页面默认态）、`docs/screenshots/data-transfer-imported.png`（单词导入结果态：导入 2 个/已存在 1 个）。

## [1.0.0] - 2026-10-13

### Added

- 工程化重构——pnpm workspace monorepo 落地，后端 Fastify 5 + TypeScript + node:sqlite SQLite 持久化，前端 Vite 6 + React 18 六页面，vitest 集成测试、Dockerfile、GitHub Actions CI 就绪。
