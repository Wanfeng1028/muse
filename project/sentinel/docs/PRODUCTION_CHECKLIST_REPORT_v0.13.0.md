# 哨兵 Sentinel v0.13.0 发版对照报告

日期：2026-10-25

| 检查项 | 状态 | 理由 |
| --- | --- | --- |
| 事件页详情展开功能 | 通过 | internal/web/static/incidents.html 点击数据行展开详情行，关闭 docs/TECH_DEBT_GAP_incidents.md 缺口二 |
| 详情数据源 | 通过 | 详情字段全部取自 /api/incidents 已返回字段（事件 ID、监控、开始时间、恢复时间、持续、状态、触发原因），无新 API、无后端改动、无假数据 |
| 交互逻辑 | 通过 | 单开、Enter/Space 键盘切换、筛选翻页重载后关闭 |
| 单元测试 | 通过 | 新增 internal/web/incidents_detail_test.go 4 例全绿；go vet 全洁；全量 go test 16 包全绿（含 internal/notify 239 秒长用例、internal/checker 28 秒） |
| 真服务冒烟 | 通过 | 18251 端口隔离库：建死链监控（http://127.0.0.1:9/never）手动检查失败，/api/incidents 返回 open 事件 1 条（monitor_name 冒烟死链、start_error 为 connection refused）；/incidents 页返回 200 且含新标记 |
| 视觉验收 | 通过 | 真浏览器截图两张（docs/screenshots/incidents-detail-collapsed.png 与 incidents-detail-expanded.png），展开态详情 7 字段与冒烟事件逐字一致，console 零错误；截图顶栏左右缘轻微裁切为 setContent 抓屏已知差异（此前多轮同款），非产品布局问题 |

## 结论

基于上述检查项全部通过，v0.13.0 满足发版标准。

## 已知限制

- Go 静态测试只断言页面静态标记，浏览器点击行为靠冒烟截图实测、无浏览器自动化点击测试
- 详情不含恢复原因与通知记录（缺口二原文提到的扩展字段仍未实现）
- 浏览器内事件页仍需用户自备 API Token（与兄弟页同款机制）
- 分布式多实例仍不支持（SQLite 单实例历史限制）