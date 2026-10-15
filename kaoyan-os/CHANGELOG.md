# 更新日志

本文件记录 Kaoyan OS 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
