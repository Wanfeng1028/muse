# sentinel v0.12.0 发版对照报告
日期：2026-10-25

| 检查项 | 状态 | 理由 |
|---|---|---|
| 短信记录落库 | 通过 | buildNotifier 接上 SMSLogger 后，真服务冒烟：死链检查失败产生 open incident 1 条，/api/sms/log 查到 phone 13800138000、provider mock、status sent 的记录 1 条 |
| /sms-log 页可访问 | 通过 | 内嵌资源化后真服务 GET /sms-log 返回 200；白名单补齐后浏览器可直达（与兄弟控制台页一致） |
| /sms-log 页可渲染 | 通过 | JS 改按 data.logs 与 r.message 取数，与 handleSMSLogAPI 的实际返回一致；页面测试断言 200 且含 sms-log-body |
| 腾讯云配置示例 | 通过 | .env.example 补齐 7 个腾讯云变量与默认值注释，与 config.go 读取项一致 |
| 旧接口兼容 | 通过 | 旧短信分发、记录查询、监控字段全部不动；改动只涉及 main 接线、页 handler、白名单与页 JS |
| 测试与回归 | 通过 | 新增 3 例全绿；go vet 全洁；改动前全量 15 包基线全绿 |

结论：全部必达项通过。

已知限制：
- 浏览器里的短信页仍需用户自行提供 API Token（sessionStorage 机制，与 monitors/profile/snapshots 页同款）。
- 阿里云与腾讯云真发未在本轮实测（无真实云账号与模板，仅 mock 模式端到端实测）。
- 分布式多实例仍不支持（SQLite 单实例，历史限制）。
