# 技术债清单（2026-10-16 快照）

> 状态更新：2026-10-19 复核，P0-1、P1-1~P1-4、P2-1、P2-8、P2-9 确认已交付；P2-6 本轮交付；P2-7 当晚深耕轮交付。P1-5 待 gh token 补 workflow 权限；P1-6、P2-5 待确认；P2-2/P2-3/P2-4 为平台限制。

## P0（影响发版/生产）

| 编号 | 位置 | 问题 | 影响 | 偿还计划 | 出处 |
| --- | --- | --- | --- | --- | --- |
| P0-1 | 推送发送链路 | 发送重试缺失，v0.10 发版对照未通过，已排期到 v0.11 | 推送发失败时没有重试，到期复习提醒可能丢 | ✅ 已交付（2026-10-19 核实）。证据 internal/push/retry.go、internal/api/push_retry_test.go。v0.11 排期处理（登记册后续计划原话"发送重试（v0.10 未通过项排期 v0.11）"） | 后续计划："发送重试（v0.10 未通过项排期 v0.11）" |

## P1（影响可维护性/可观测性）

| 编号 | 位置 | 问题 | 影响 | 偿还计划 | 出处 |
| --- | --- | --- | --- | --- | --- |
| P1-1 | 全局（日志） | 没有结构化日志/request_id | 出问题时排查困难，请求链路对不上 | ✅ 已交付（2026-10-19 核实）。证据 internal/log/log.go、internal/api/server.go（request_id）。后续计划已列"结构化日志/request_id"，具体轮次待确认 | 后续计划："结构化日志/request_id、metrics、API 限流" |
| P1-2 | 全局（监控） | 没有 metrics | 运行状态不可量化，无法观测 | ✅ 已交付（2026-10-19 核实）。证据 internal/metrics/metrics.go。后续计划已列"metrics"，具体轮次待确认 | 后续计划："结构化日志/request_id、metrics、API 限流" |
| P1-3 | API 层 | 没有 API 限流 | 接口可被无限制调用，存在被刷风险 | ✅ 已交付（2026-10-19 核实）。证据 internal/ratelimit/ratelimit.go。后续计划已列"API 限流"，具体轮次待确认 | 后续计划："结构化日志/request_id、metrics、API 限流" |
| P1-4 | 推送调度器 | 调度器按单实例假设运行 | 多实例部署时可能重复推送或行为不确定 | ✅ 已交付（2026-10-19 核实）。证据 internal/push/scheduler_lock.go（syscall.Flock）。待确认 | v0.10 已知限制："调度器单实例假设" |
| P1-5 | CI 配置 | GitHub Actions CI 暂放在 second-brain/.github，未迁到仓库根目录 | CI 位置不规范，迁移前 workflow 权限问题未解 | 待 token 补齐 workflow 权限后迁移至仓库根目录 | 技术栈："GitHub Actions CI 暂置于 second-brain/.github，待 token 补齐 workflow 权限后迁移至仓库根目录" |
| P1-6 | 离线写队列（PWA） | 离线新建笔记回放会产生新 id | 离线新建后回放，id 与预期不一致 | 待确认 | v0.7 诚实边界："离线新建笔记回放会产生新 id" |

## P2（体验/文档缺口）

| 编号 | 位置 | 问题 | 影响 | 偿还计划 | 出处 |
| --- | --- | --- | --- | --- | --- |
| P2-1 | PWA 推送 | 推送通知暂不支持 | 装机后收不到系统级提醒 | ✅ 已交付（2026-10-19 核实）。证据 v0.10 Web Push，internal/api/push_subscription.go（GET /api/push/vapid-public-key）。待确认（v0.10 已补 Web Push，此项为 v0.7 当时的边界描述） | v0.7 诚实边界："推送通知暂不支持" |
| P2-2 | PWA / iOS | iOS 无后台同步，靠 online 事件回放 | iOS 上断网期间的操作要等回到前台才回放 | 待确认 | v0.7 诚实边界："iOS 无后台同步（靠 online 事件回放）" |
| P2-3 | PWA / 局域网 | 局域网 HTTP 下 PWA 不可用，需 HTTPS 或 localhost | 局域网内无法按 PWA 方式使用 | 待确认 | v0.7 诚实边界："局域网 HTTP 下 PWA 不可用（需 HTTPS 或 localhost）" |
| P2-4 | Web Push / iOS | iOS 需 16.4+ 且已安装到主屏幕才能用推送 | 低版本或未装到主屏幕的 iOS 用户收不到推送 | 待确认 | v0.10 已知限制："iOS 需 16.4+ 且已安装到主屏幕" |
| P2-5 | Web Push | 无到期复习时不推送 | 用户当天没到期内容就收不到任何提醒 | 待确认 | v0.10 已知限制："无到期复习时不推送" |
| P2-6 | 搜索 | CJK 仍逐字切分 | 中文搜索切分粒度粗，可能影响召回/排序 | ✅ 2026-10-19 交付：Tokenize 已接入 SegmentCJK 词典分词（internal/search/search.go） | v0.8.0 已知边界："CJK 仍逐字切分、多词 AND 语义" |
| P2-7 | 搜索 | 多词查询是 AND 语义 | 多词查询结果偏严，漏召回 | ✅ 2026-10-19 晚深耕轮交付：`GET /api/search` AND 无结果且分词≥2 时自动降级 OR 语义（`search.RankOr` + `store.SearchNotesAny`，响应 `"fallback": true`，`?format=legacy` 同样生效）；顺带修复 `SearchWithFallback` 的 hitCounts 排序错位真 bug（RankedNote 新增 HitCount 字段），回归测试 `TestRankOrHitCountRegression3` 已验证旧实现确会错排 | v0.8.0 已知边界："CJK 仍逐字切分、多词 AND 语义" |
| P2-8 | 搜索 API | `GET /api/search` 响应体数组改对象 `{query,terms,notes,meta}`，是不兼容变更 | 旧客户端按数组解析会坏 | ✅ 已交付（2026-10-19 核实）。证据 v0.14，GET /api/search?format=legacy（internal/api/server.go）。已在 v0.14 交付：`?format=legacy` 返回旧数组形状，默认仍为对象 | v0.8.0："响应体数组→对象 `{query,terms,notes,meta}`（不兼容变更，已标注）" |

| P2-9 | 推送聚合 | 定时推送暂按默认 `local` 用户聚合 | 非 `local` 用户的定时推送行为与预期不一致 | ✅ 已交付（2026-10-19 核实）。证据 v0.9，internal/push/scheduler.go RunPushForUser。后续计划支持按用户推送（v0.9 已做按用户推送，此项为 v0.6 当时描述） | v0.6.0："定时推送暂按默认 `local` 用户聚合（后续计划支持按用户推送）" |

## 已规划功能（非技术债，仅索引）

- 发送重试：v0.10 未通过项，排期到 v0.11（出处：后续计划）。（✅ 已交付，2026-10-19 核实）
- 结构化日志/request_id：后续计划已列（出处：后续计划）。（✅ 已交付，2026-10-19 核实）
- metrics：后续计划已列（出处：后续计划）。（✅ 已交付，2026-10-19 核实）
- API 限流：后续计划已列（出处：后续计划）。（✅ 已交付，2026-10-19 核实）
- 按用户推送：v0.6.0 当时说后续计划支持，v0.9 已实现（出处：v0.6.0 里程碑记录、v0.9 里程碑记录）。
- DB 迁移版本化：v0.12 发版对照未通过项，已在 v0.14 交付（internal/store/migrate.go：schema_version 表 + 有序迁移注册表，CurrentSchemaVersion=2）。
- reviews_due 多用户拆分：v0.12 发版对照未通过项，已在 v0.14 交付（GET /metrics 新增 reviews_due_by_user{user}；原 reviews_due 保留）。
- P2-8 search 响应兼容：已在 v0.14 交付（GET /api/search?format=legacy 返回旧数组形状）。


## 偿还节奏建议

按 DoD 第 8 条"每若干轮强制一轮技术债清理"，未来 3 轮建议顺序如下（只排 P0/P1）：

- 第 1 轮：P0-1（发送重试）——唯一 P0，v0.11 已排期，优先清掉，先过发版对照。
- 第 2 轮：P1-1 + P1-2（结构化日志/request_id + metrics）——都在后续计划里，且互相配套，一轮一起做能先把可观测性立起来；顺带把 P1-4（调度器单实例假设）确认清楚，写成待确认结论或补上约束。
- 第 3 轮：P1-3（API 限流）+ P1-5（CI 迁移到仓库根目录）——限流补上接口保护；CI 迁移等 token 权限到位就做。P1-6（离线新建笔记回放产生新 id）视轮次余量安排，做不了就明确标"待确认"。