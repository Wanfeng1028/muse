# sentinel v0.33.5 生产对照报告

变更：GET /api/monitors MonitorStats 读取失败现直接返回 500 “读取监控统计失败”并记录 logErr，不再静默 uptime_24h=100.0；store 无变更。

| 项目 | 结果 |
|---|---|
| 可靠性-关键路径错误不再掩盖 | 通过 (dropped-checks-table test returns 500) |
| 可观测性-结构化日志 request_id | 通过 (logErr carries request_id and handler name) |
| 数据-无 schema 变更 | 通过 |
| 部署运维-无新配置 | 通过 |
| 安全-鉴权与响应体结构不变 | 通过 |
| 可维护性-CHANGELOG 与测试同步 | 通过 |
| 全量测试 | 通过 (go test ./... all 16 packages ok) |
| 真实服务冒烟 | 通过 (isolated port, healthz 200, no-auth 401, bad token 401, authed list 200 with seeded monitors at uptime_24h 100 from store no-data semantics) |
| 视觉验收 | 不适用 (no UI change) |
| 已知遗留 | checks-list total=0 fallback untouched, stats-days and delivery limit clamps remain locked 200 contracts, LastCheck error still renders null/"" degradation |
