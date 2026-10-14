
# 更新日志

本文件记录 linkshort 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.2.0] - 2026-10-14

### 新增

- `GET /metrics`：Prometheus 文本格式，不走鉴权，零外部依赖手写 exposition。指标有 `linkshort_http_requests_total{method,route,status}`、`linkshort_redirects_total{outcome}`（ok/gone/not_found/error）、`linkshort_burn_links_burned_total`、`linkshort_rate_limit_rejected_total`、`linkshort_process_start_time_seconds`。路由 label 取 chi RoutePattern，`/{slug}` 不会按具体 slug 爆炸。
- 限流 middleware：IP + API Key 双维度令牌桶。环境变量 `LINKSHORT_RATE_LIMIT_RPS`（默认 20）、`LINKSHORT_RATE_LIMIT_BURST`（默认 40）、`LINKSHORT_RATE_LIMIT_ENABLED`（默认 true）。超限返回 429 + `{"error":"rate limit exceeded"}` + `Retry-After: 1`。`/metrics`、`/api/health`、`/api/readyz` 免限流。
- `GET /api/readyz` 就绪探针：DB ping 通返回 200，否则 503。配套新增 `store.Ping()`。
- 失败注入测试：构造已关闭 DB 的服务，验证跳转 500、建链 500、health 仍 200、readyz 503、/metrics 仍 200，且全程不 panic。
- CSV 导入导出列扩展为 7 列（slug,url,title,enabled,expires_at,max_visits,burn）。
- `docs/OPERATIONS.md` 运维手册：部署/配置/备份恢复/升级/监控/排障/限流调参。
- 新增 24 例测试（metrics_test 5、ratelimit_test 6、middleware_test 3、csv_ext_test 4、failure_test 6），`go test ./...` 与 `-race` 全过。

### 变更

- `/api/health` 语义明确为存活探针：进程活着就返回 200。
- CSV 导出表头变为 7 列；旧 5 列 CSV 仍可导入。非法组合（burn+max_visits≠1、max_visits 越界/非数字、burn 非 bool）记错跳过。

## [v1.1.0] - 2026-10-14

### 新增

- **限次访问**：链接可设置最多可访问次数 N，前 N 次返回 302，第 N+1 次返回 410"链接已达访问上限"。
- **阅后即焚**：一次性链接，首次访问返回 302，之后返回 410"链接已阅销毁"。销毁检查在禁用检查之前。
- **remaining 字段**：API 响应新增 `max_visits`、`burn`、`remaining`（剩余次数，null=不限）。
- **数据库版本化迁移**：`db.go` 使用 `PRAGMA user_version` 做版本化迁移，v1→v2 自动为老库 `ALTER` 加列，实测老数据保留。
- **Web UI**：
  - 新建页加"限次访问"输入框 + "阅后即焚"复选框（互斥联动）。
  - 列表页加"限制"列徽标（阅后即焚 / 已销毁 / 限 N 次·剩 M 次 / 不限）。
  - 详情页加"访问限制"行，支持编辑保存与清除。
- **测试**：新增 10 例。store 4 例（迁移版本与列、CreateLinkEx、MarkBurned、UpdateLinkEx）；handler 6 例（创建限次/阅后即焚、非法限次 400、限次达限 410、阅后即焚 410、已阅销毁优先于禁用 404、PATCH 限次更新/清除）。

### 变更

- `linkJSON` 新增三个字段：`max_visits`、`burn`、`remaining`。
- `POST /api/links` 接受 `max_visits`（正整数，1~1000000）、`burn`（bool）；非法组合返回 400（burn 与 max_visits≠1、max_visits≤0）。
- `PATCH /api/links` 支持 `max_visits`（数字 / null 清除）、`burn`。

### 已知缺口

- CSV 导入导出未带新字段（排期 v1.2）。
- 高并发下两次访问可能都通过 clicks 检查（单连接串行写入缓解，未做分布式锁）。
- burn 链接"销毁"后数据仍保留在库中（可查统计，彻底删除需手动删）。

## [v1.0.0] - 2026-10-13

工程化 v1：短链 CRUD/跳转/统计/二维码/导入导出/Web UI 四页。
