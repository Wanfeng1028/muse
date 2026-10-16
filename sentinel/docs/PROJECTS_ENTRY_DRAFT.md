
### sentinel v0.4.0（2026-10-16）
- 增量：Webhook 持久化投递队列——告警入 SQLite 队列表（pending/retrying/done/failed），worker 指数退避重投（默认 8 次/基数 60s/15s 扫描）；管理 API（列表+手动重试）与 /deliveries 控制台页；同一事件入队去重。
- 完成度：后端队列+测试、API+UI、文档对照报告已落地；待真实冒烟验证（必失败 webhook 观察 pending→retrying→failed 全链路）。
- 已知限制：单实例（SQLite）；故障演练与真实负载验证排期 v0.5。
