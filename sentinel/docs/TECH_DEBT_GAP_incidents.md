# incidents.html 技术债缺口记录

本文件记录 incidents.html 在技术债清理收尾时发现的缺口，和 CHANGELOG 的描述不一致的地方。

## 缺口一：状态筛选下拉不存在

- 缺什么：CHANGELOG 写了"事件页新增监控筛选与状态筛选"，但当前 internal/web/static/incidents.html 里只有一个监控筛选 `#monitor-filter`，没有状态筛选控件。
- 影响谁：想看"只看未恢复事件"的人，现在只能在整页里自己找。
- 建议怎么做：在事件页加一个状态筛选 `<select>`，选项是"全部 / 未恢复 / 已恢复"。接口侧 `/api/incidents` 目前只支持 `monitor_id`、`page`、`page_size`（`limit`），没有状态参数，所以要么在 `handleListIncidents` 加一个 `status` 查询参数并让 `ListIncidentsPaged` 支持，要么先在页面侧过滤。接口没落地之前不许在前端写假数据。

## 缺口二：点击行展开详情不存在

- 缺什么：CHANGELOG 写了"事件行支持点击展开详情行"，但当前 `renderRows` 只往每行塞了 6 个 `<td>`，没有任何点击事件或展开行逻辑。
- 影响谁：想点开一条事件看更多细节的人，现在看不到详情。
- 建议怎么做：需要先确定"详情"要展示哪些字段。当前 `/api/incidents` 返回的字段是 `id, monitor_id, monitor_name, started_at, ended_at, downtime_sec, start_error`，如果详情需要更多字段（比如恢复原因、通知记录），那要先加接口。接口没定之前不许在前端拼假详情。

## 缺口三：CHANGELOG 与代码不一致

- CHANGELOG 的两条偿还记录说事件页"改接真实 API"，这条和代码一致，已验证。
- 但 CHANGELOG 同时提到"状态筛选"和"点击展开详情"，这两条在代码里不存在，属于文档写在了代码前面。要么补代码，要么把 CHANGELOG 里这两句删掉，别让文档骗人。

补充说明：测试文件按仓库现有约定放在 `internal/web` 包内，直接用包里的 `FS`（`go:embed all:static`），路径 `static/incidents.html` 与嵌入根一致。断言里的 `fetch("/api/incidents` 和 `fetch("/api/monitors")` 与 incidents.html 里逐字出现的调用一致，`/api/incidents`、`/api/monitors` 与事实来源二的路由注册逐字一致。没有改任何 HTML，因为审计结论是已无模拟数据。

## 关闭记录（2026-10-25，v0.13.0）
- renderRows 已为数据行补充点击与键盘切换，详情行紧跟数据行且单列 colSpan=6，详情字段全部取自 /api/incidents 已返回字段（事件 ID、监控、开始时间、恢复时间、持续、状态、触发原因），未新增接口、未拼假详情。
- 恢复原因与通知记录不在本次详情字段内，仍属未实现项，已如实写明。
- internal/web/incidents_detail_test.go 4 例静态标记断言通过；浏览器内真实点击行为留待真服务冒烟与截图验收，未做自动化测试。
