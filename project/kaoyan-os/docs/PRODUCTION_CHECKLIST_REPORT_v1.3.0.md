# v1.3.0 发版对照报告

对照 `PRODUCTION_CHECKLIST.md`，逐条过一遍。版本 v1.3.0，自律热力图，日期 2026-10-16。

## 1. 功能与测试

[通过] 自律热力图功能完成：后端 `GET /api/stats/heatmap?months=N`（默认 3，只接受整数 1~6，否则 400 `{ error: 'months 参数无效'}`），`packages/shared` 新增 `HeatmapDay` / `HeatmapResponse` 类型；前端 `/heatmap` 页面 + 导航项「自律热力图」（在"周报"之后）。

[通过] vitest 50/50 全过，本轮 `heatmap.test.ts` 新增 7 例：默认 3 个月 93 天、months=1 返回 31 天、months=0/7 返回 400、focus+45 差值、plans 完成差值、-7 天补记录 streak+1、-30 天孤立记录 streak 不变。

[通过] 真实冒烟：`/api/stats/heatmap` 返回 200，符合预期。

[通过] 前端 `tsc --noEmit` 零错，`vite build` 成功。

[通过] 视觉验收：3 张真实截图（浅色 / 点击详情 / 深色），人工看过，无布局问题。截图在 `docs/screenshots/`（`light-heatmap.png`、`light-heatmap-detail.png`、`dark-heatmap.png`）。

## 2. 数据库与迁移

[不适用] 本轮无 DB 迁移。只新增只读聚合路由与前端页面，无表结构变更，老库直接能跑。

## 3. 备份与恢复

[通过] 沿用 v1.1.0 的全量 JSON 备份 / 恢复机制，本轮没动这部分代码，热力图只读聚合不新增持久化数据。

## 4. 故障演练

[未通过] 本轮没做故障演练，排期上放到了后面。不阻塞本次发版，但记在这里。

## 5. 可观测性

[通过] 日志 / 指标沿用既有方案（Fastify 默认日志），本轮没引入新的观测需求，也没改动日志配置。

## 6. 安全

[不适用] 鉴权限流不适用：本项目是本地单用户自托管，没有多租户、没有公网暴露面；`GET /api/stats/heatmap` 的 `months` 参数校验（只收整数 1~6，否则 400）已覆盖。

## 7. 文档

[通过] CHANGELOG.md 已更新到 1.3.0，README.md 已补功能列表、页面说明、API 概览、路线图。
