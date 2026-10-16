
# 更新日志

本文件记录 linkshort 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.7.0] - 2026-10-16

### 新增

- burn 逐条 purge：`POST /api/links` 与 `PATCH /api/links/{id}` 新增 `purge` 字段；`purge=true` 仅当 burn 链接有效，非 burn 链传 `purge=true` 返回 400（"只有阅后即焚链接才能设置销毁后彻底删除"）；响应新增 `purge_after_burn` 布尔字段。
- DB 迁移 v4→v5：`links.purge_after_burn INTEGER NOT NULL DEFAULT 0`，老库自动 ALTER，老行默认 0。
- 销毁语义：逐条 `purge=true` 或全局 `LINKSHORT_BURN_PURGE_AFTER_DESTROY=true` 任一成立即彻底删除行（含 visits 级联）。
- 审计日志：`handler: 彻底删除已销毁链接 link=<id> slug=<slug> cause=per-link|env`。
- 指标复用 `linkshort_burn_links_purged_total`。
- Web UI 新建页与详情页各加一个"销毁后彻底删除"复选框（新建页仅 burn 勾选时可用）。
- `scripts/backup-drill.sh` 一键自动化演练：构建→起服务→建链（含普通/burn+purge/限次）→访问造数据→快照→backup.sh 备份→停服→删库→restore.sh --force 恢复→重启→一致性校验（links/visits/clicks 行数一致、普通链 302、限次链第 3 次 410、burn+purge 链 404、`/api/backup/health` status=ok）；用法 `backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N]`；退出码 0 通过 / 2 参数或依赖缺失 / 其他非零为某步 FAIL；演练全程 mktemp 隔离工作区不碰生产 data/ 与 backups/。
- Makefile 新增 `make drill`；OPERATIONS.md 新增 3.9 节。
- 新增 9 例测试（store 4——v4→v5 真实迁移/CreateLinkEx purge 标记/UpdateLinkEx purge 标记/PurgeLink 删行+visits 级联；handler 5——purge 非 burn 报 400/逐条 purge 302→404/默认软保留 302→410/PATCH 设 purge/全局开关仍有效）；`go test ./... -race` 104 例全过。

### 变更

- 无破坏性变更。默认行为与 v1.6.0 一致。

### 已知缺口

- v1.5 之前销毁的 burn 链没有 `burned_at`，定时清理仍跳过它们（v1.5 起已知）。
- PATCH 把 burn 设为 false 时若该链 `purge=true` 会 400，需先把 purge 设 false（严格校验，有意为之）。

## [v1.6.0] - 2026-10-16


### 新增

- 备份健康自检：`GET /api/backup/health`（需 API Key）返回最近备份时间、完整性校验结果、备份份数与过期判定；无备份/上次失败/完整性未通过/超过 `LINKSHORT_BACKUP_MAX_AGE_DAYS` 天（默认 7）时 `status` 为 `degraded`（HTTP 仍 200）。
- `scripts/backup.sh` 每次运行把结果原子写入 `$BACKUP_DIR/last-backup.json`（健康端点读取的依据）；失败时若配了 `LINKSHORT_ALERT_WEBHOOK_URL` 则 POST JSON 告警（curl 10 秒超时，通知失败不影响退出码）。
- Prometheus 新增 `linkshort_backup_last_success_timestamp`（最近成功备份的 unix 秒）与 `linkshort_backup_health_status`（1 健康/0 降级）两个 gauge。
- Web UI 仪表盘新增"备份健康"面板：状态徽标（健康/降级）+ 最近备份时间 + 备份文件 + 备注。
- 新增 12 例测试（handler 7、metrics 2、backupscript 3 含 fake webhook 捕获）；`go test ./... -race` 95 例全过。

### 变更

- 无破坏性变更。`.env.example` 新增 `LINKSHORT_BACKUP_DIR` / `LINKSHORT_BACKUP_MAX_AGE_DAYS` / `LINKSHORT_ALERT_WEBHOOK_URL`。

## [v1.5.0] - 2026-10-16

### 新增

- purge 定时清理：后台 goroutine 按 `LINKSHORT_PURGE_INTERVAL`（默认 `24h`）轮询，删除销毁时间超过 `LINKSHORT_PURGE_RETENTION_DAYS`（默认 `7` 天）的已销毁 burn 短链；启动时打日志说明清理配置，优雅退出时先停清理再停 HTTP。
- DB 迁移 v3→v4：`links` 新增 `burned_at TEXT` 列（老库自动 ALTER），`MarkBurned` 销毁时写入销毁时间；清理只认 `burned_at` 非空的行，v1.5 之前销毁的历史行（`burned_at` 为 NULL）不在清理范围内。
- Prometheus 新增 `linkshort_links_purged_total`（定时清理删除数）；`GET /api/meta` 新增 `purge_interval` / `purge_retention_days` 字段。
- `GET /docs` 公开 API 文档页（无需鉴权）：邮政标签视觉，表格列出全部 22 个端点（方法/路径/鉴权/说明），随二进制内嵌发布。
- 新增 10 例测试（store 3、purge 1、config 3、metrics 1、handler 2）；`go test ./... -race` 83 例全过。

### 变更

- 无破坏性变更。默认配置下 purge 每天跑一轮、保留 7 天；v1.5 之前已销毁的 burn 链因无 `burned_at` 不会被自动清理（已知缺口见下）。

### 已知缺口

- v1.5 之前销毁的 burn 链没有 `burned_at`，定时清理跳过它们；如需清理请手动删除或等后续版本补回填脚本。
- OPERATIONS.md 5.2 指标列表历史欠账：`linkshort_burn_links_purged_total`（v1.3）、`linkshort_password_attempts_total`（v1.4）之前漏记，本轮仅补记 v1.5 新增指标。

## [v1.4.0] - 2026-10-16

### 新增

- 密码保护短链：创建时可设访问密码（POST /api/links 的 `password` 字段），访问者必须在密码门页输入正确密码才能跳转。密码只存 bcrypt 哈希（golang.org/x/crypto v0.31.0），明文永不落库、不进响应、不进日志。
- `PATCH /api/links/{id}` 支持 `password`：null=不动、`""`=清除、非空=设置/修改；创建时密码落库失败会回滚整条短链，避免半吊子状态。
- 跳转语义：`GET /{slug}` 有密码返回 200 密码门页（服务端渲染，邮政标签视觉）；`POST /{slug}` 校验密码，正确 302（正常记点击、burn 链照常销毁），错误 401（不计点击、不触发阅后即焚）。密码校验在限次访问检查之前，防错误尝试耗尽次数。
- Prometheus 新增 `linkshort_password_attempts_total{result="ok"|"fail"}`；错误尝试走全局 IP 限流（默认 20 RPS）。
- Web UI：新建页"访问密码"输入框、列表"限制"列"密码保护"徽标（与其他徽标同行）、详情页"密码保护"区（状态文案+设置/清除）。
- DB 迁移 v2→v3（`password_hash TEXT`，老库自动 ALTER 升级，数据不丢）。
- 新增 15 例测试（auth 3、store 4 含 v2→v3 真实迁移、handler 8 含门页/401/302/burn 联动）；`go test ./... -race` 73 例全过。

### 变更

- 无破坏性变更。默认配置下所有行为与 v1.3 一致；`go.mod` 新增 `golang.org/x/crypto v0.31.0`（go 1.23 兼容版，未升级工具链）。

### 已知缺口

- CSV 导入导出未带密码字段：密码不可批量导入/导出（有意为之，防明文密码进 CSV）。
- 高并发 clicks 检查仍未做分布式锁（单连接串行写入缓解，v1.1 起已知）。

## [v1.3.0] - 2026-10-15


### 新增

- burn 销毁后彻底删除（可选）：环境变量 `LINKSHORT_BURN_PURGE_AFTER_DESTROY`（默认 false）。设为 true 时 burn 链首次访问 302 后行被彻底删除（visits 级联清除），之后再访 404；默认 false 保持 v1.2 行为（仅禁用、410、数据留档）。
- `GET /api/meta` 新增 `burn_purge_after_destroy` 字段；Prometheus 新增 `linkshort_burn_links_purged_total`。
- 详情页 burn 链接显示销毁行为（"销毁后彻底删除" / "销毁后仅禁用、数据留档"）。
- `scripts/backup.sh` / `scripts/restore.sh`：在线备份（sqlite3 `.backup` + integrity_check + `--keep-days` 默认 7）与恢复（`--force` 安全门、`--dry-run`、恢复前后 integrity_check、旧库 `.broken-` 快照）；`make backup` / `make restore BACKUP=...`。
- docs/OPERATIONS.md：备份恢复改走脚本 + 2026-10-15 真实演练输出归档；新增 burn purge 行为与数据影响说明。
- 新增 6 例测试（store PurgeLink 2、handler 跳转 purge 语义 2 + meta 1、metrics purged 指标 1）；`go test ./... -race` 58 例全过。

### 变更

- 无破坏性变更。默认配置下所有行为与 v1.2 一致。

### 已知缺口

- 高并发 clicks 检查仍未做分布式锁（单连接串行写入缓解）。
- restore.sh 目标 DB 不存在时提示文案小瑕疵（打印了不存在的快照路径）。

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
