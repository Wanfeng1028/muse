# 更新日志

本文件记录 Kaoyan OS 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
