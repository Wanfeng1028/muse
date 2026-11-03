# 榫卯 MortiseDB v1.2.0 发版对照报告

本报告对照 v1.0 生产就绪清单（`docs/PRODUCTION_CHECKLIST.md`（v1.0 报告 + v1.1 增补对照））的验收硬指标，并汇总 v1.2 增补项的落地结论。所有结论均以本轮实测输出为唯一依据，未实测项如实标注。

## 一、验收硬指标

| # | 检查项 | 结论 | 依据 |
|---|--------|------|------|
| 1 | `go build ./...` | ✅ 通过 | 本轮实测 |
| 2 | `go vet ./...` | ✅ 通过 | 本轮实测 |
| 3 | `gofmt -l` | ✅ 本轮涉及文件干净 | 本轮实测 |
| 4 | `go test ./...` | ✅ 全过（12 个包：api/backup/config/connector/infer/metrics/store/sync/views + 3 个无测试文件的包 cmd/log/scheduler/web） | 本轮实测 |
| 5 | `scripts/e2e.sh` | ✅ E2E PASS | 本轮实测：10 行茶叶订单 CSV + 8 会员 JSON → sync 新增 orders 10/users 8 → 视图自动注册 新增 2 → 改 YAML 新增 1 更新 1 → 删声明 清理 1 → serve 起 127.0.0.1:18421 → /api/views 查到 → CSV 导出 10 行数据且含"龙井" |
| 6 | Web UI 回归 | ✅ 本轮无视图相关改动 | 自动注册不改动前端渲染逻辑，视图页沿用既有实现，故不新增截图 |

## 二、v1.2 增补对照表

| # | 检查项 | 结论 | 依据 |
|---|--------|------|------|
| 15 | 视图自动注册 | ✅ 通过 | `views.SyncFromConfig` 幂等/更新/清理；`_m_views.origin` 列区分 yaml/manual；老库 `Migrate()` 自动补列回填；单测 5+3 锁定 |
| 13 | 端到端自动化测试 | ✅ 通过 | `scripts/e2e.sh`：真实服务 + 真实数据 + 断言；v1.1 遗留项关闭 |
| — | docker-compose 一键部署 | ✅ 通过（静态校验） | 健康检查 / 资源限制 / 日志轮转；**未实测 `docker run`——本机无 daemon**，如实标注 |
| 14 | Dependabot | ⬜ 未通过 | 需在 GitHub 仓库 Settings → Security → Dependabot 手动开启，超出 agent 权限；`go.mod` 已 pin 版本，风险可控；排期：用户手动开启后关闭此项 |

## 三、结论

v1.2 达到发版标准，建议打 tag `v1.2.0`。

唯一遗留项为 Dependabot 开启，需用户在 GitHub 仓库侧手动操作，非代码层面阻塞。
