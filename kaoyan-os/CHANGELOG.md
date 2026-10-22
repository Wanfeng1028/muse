# 更新日志

本文件记录 Kaoyan OS 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
