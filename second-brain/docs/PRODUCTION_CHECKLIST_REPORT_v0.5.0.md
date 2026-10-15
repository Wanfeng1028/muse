# 生产级 Definition of Done 对照报告 — second-brain v0.5.0

## 版本与日期

- 版本：v0.5.0「反向链接面板」
- 日期：2026-10-16

## 变更摘要

新增反向链接面板：编辑区附件区下方列出引用当前笔记的所有笔记（引用上下文 + 点击跳转），并提供 `GET /api/notes/{id}/backlinks` 接口。

## 清单逐条对照

### 1. 功能完整性

结论：通过。

依据：新增文件 `internal/store/backlinks.go` 提供 `Backlink` 结构与 `Store.Backlinks(noteID)`；新增 API `GET /api/notes/{id}/backlinks`（`internal/api/server.go`）；前端 `internal/web/static` 中新增 `backlink-section` 区域与 `loadBacklinks`/`renderBacklinks`（app.js）；点击条目跳转已用 Playwright 真实交互验证通过。

### 2. 数据与迁移

结论：不适用。

理由：本轮为纯功能增量，无 DB 变更；`links` 表在既有 schema 中已存在，`Backlinks` 查询基于 `links.target_id = noteID`。

### 3. 配置与依赖

结论：不适用。

理由：无新配置项，无新依赖。

### 4. 可观测性

结论：通过（未新增日志点）。

依据：沿用既有请求日志；本轮未新增日志点。

### 5. 备份与恢复

结论：通过。

依据：沿用 v0.3.0 机制；本轮未改动存储结构。

### 6. 鉴权与安全

结论：通过（记为已知限制）。

依据：沿用既有单用户无鉴权设计，与 v0.4.0 一致，记为已知限制。

## 测试与验收证据

- `go test ./...` 全量 114 通过（v0.4.0 为 104，新增 10：store 6 + api 4）。
- `go vet`、`gofmt` 全洁。
- store 测试 `internal/store/backlink_test.go` 6 例。
- api 测试 4 例：有引用者 200、空数组 `[]`、不存在 404、非法 id 非 200（真实 HTTP）。
- 真实冒烟（2026-10-16）：3 篇真实笔记（遗忘曲线/复习计划/抽认卡技巧，后两者正文含 `[[遗忘曲线]]`）→ `GET /api/notes/1/backlinks` 返回 2 条，id 倒序，snippet 中文上下文正确。
- 视觉验收：`docs/screenshots/backlinks.png` 真实截图已由编排者亲眼验收通过（面板渲染正常、两条引用、样式沿用现有体系、无错字）。

## 已知限制

- 单用户无多租户（v0.4.0 已有）。
- 反向链接 snippet 只取第一处引用上下文。

## 本轮教训

- `apply_dpsk_sb.py` 不识别 `--dry-run` 参数，"试运行"实际已应用，导致 server.go 路由被注册两次引发 ServeMux panic，编排手工删除重复块后恢复。
- dpsk 猜错测试 helper `newTestServer` 签名（实际只返回 `*httptest.Server`），编排按真实 helper 手工重写测试。
- 截图 harness 里 setContent 下相对 URL 解析失败，模板字符串 `` `/api/ `` 也要改写为绝对地址（之前只处理了单双引号）。

## 结论

可发版。
