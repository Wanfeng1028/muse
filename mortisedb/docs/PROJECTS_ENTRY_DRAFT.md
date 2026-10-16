
## mortisedb（榫卯 MortiseDB）· v1.3.0 物化视图 + 刷新策略（2026-10-16）

- 新增：`views` 声明 `materialize: {enabled, refresh}`（on_sync/manual/interval）；`views.Refresh` 事务全量刷新 + `views.RefreshDue` 策略调度；sync 自动刷新（打印 `刷新 N，跳过 M`）/ `views refresh` CLI / `POST /api/views/{name}/refresh`；Web UI 物化标记 + 一键刷新；`_m_views` 新增 4 列（老库幂等迁移）；3 个 Prometheus 新指标；e2e 新增第 9 步物化演练。
- 修复：`RecordViewRefresh` 时间格式 RFC3339（修复 interval 策略误判）。
- 验收：`go test ./...` 9 包 74 测试全绿；`scripts/e2e.sh` E2E PASS（10 步）；视图页截图亲验。
- 文档：CHANGELOG [1.3.0]、README（物化视图节 + 指标表 + 路线图）、`docs/OPERATIONS.md` §5、`docs/PRODUCTION_CHECKLIST_REPORT_v1.3.0.md`。
- 遗留：Dependabot 需用户在 GitHub 仓库侧手动开启。
