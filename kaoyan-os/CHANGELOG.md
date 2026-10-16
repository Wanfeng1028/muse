# 更新日志

本文件记录 Kaoyan OS 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
