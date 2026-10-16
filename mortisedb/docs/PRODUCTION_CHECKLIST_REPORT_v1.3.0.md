
# 榫卯 MortiseDB v1.3.0 发版对照报告

本报告对照 `docs/PRODUCTION_CHECKLIST.md` 的验收硬指标，并汇总 v1.3 增补项的落地结论。所有结论均以本轮实测输出为唯一依据，未实测项如实标注。

## 一、验收硬指标

| # | 检查项 | 结论 | 依据 |
|---|--------|------|------|
| 1 | `go build ./...` | ✅ 通过 | 本轮实测 |
| 2 | `go vet ./...` | ✅ 通过 | 本轮实测 |
| 3 | `gofmt -l` | ✅ 本轮涉及文件干净 | 本轮实测 |
| 4 | `go test ./...` | ✅ 全过（9 个包 ok，共 74 个测试 PASS） | 本轮实测：config 物化校验、store 物化列迁移/表名/刷新记录、views Refresh/RefreshDue 8 例、api refresh 接口 2 例 |
| 5 | `scripts/e2e.sh` | ✅ E2E PASS（10 步） | 本轮实测：v1.2 全链路（视图自动注册/更新/清理、CSV 导出 10 行含"龙井"）+ 新增第 9 步物化演练（`物化视图刷新: 刷新 1，跳过 1`、`_mv_v_order_detail` 10 行、`views refresh v_city_revenue` 写入 4 行、`POST /api/views/{name}/refresh` 返回 rows） |
| 6 | Web UI 回归 | ✅ 通过（截图亲验） | 视图页：物化标记 + 刷新按钮 + 上次刷新时间显示正常，风格与现有 UI 一致（`docs/screenshots/views-materialized.png`） |

## 二、v1.3 增补对照表

| # | 检查项 | 结论 | 依据 |
|---|--------|------|------|
| — | 物化视图 + 刷新策略 | ✅ 通过 | `views.Refresh`（事务全量刷新）/ `views.RefreshDue`（on_sync/manual/interval 调度 + 取消物化 DROP 表）；`_m_views` 4 列扩展，老库 `Migrate()` 幂等补列；sync/CLI/API 三路触发；单测 8+2 锁定 |
| — | 可观测性 | ✅ 通过 | 新增 `mortise_view_refresh_total{view,status}` / `mortise_view_refresh_duration_seconds{view}` / `mortise_view_last_refresh_rows{view}`，手写 exposition 无新依赖 |
| — | 真实 bug 修复 | ✅ 通过 | `RecordViewRefresh` 时间格式由 SQLite `datetime('now')` 改为 Go RFC3339，修复 `interval` 策略误判到期；`TestRefreshDueInterval` 回归锁定 |
| — | docker-compose | ✅ 通过（静态校验） | 本轮未改动 compose；**未实测 `docker run`——本机无 daemon**，如实标注 |
| 14 | Dependabot | ⬜ 未通过 | 需在 GitHub 仓库 Settings → Security → Dependabot 手动开启，超出 agent 权限；`go.mod` 已 pin 版本，风险可控 |

## 三、结论

v1.3 达到发版标准，建议打 tag `mortisedb-v1.3.0`。

唯一遗留项为 Dependabot 开启，需用户在 GitHub 仓库侧手动操作，非代码层面阻塞。
