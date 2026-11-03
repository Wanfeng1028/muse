# 发版对照报告：second-brain v0.17.0「记忆健康诊断」

## 变更清单

### 后端
- `internal/store/review_health.go` 新增 `ReviewHealth` 聚合逻辑，包含：
  - 汇总计数：Total、DueNow、Overdue7d、NeverReviewed、AvgEF。
  - EF 四档分桶：1.5以下、1.5到2.0、2.0到2.5、2.5以上。
  - Attention 三类需关注卡片（上限20条，优先级 ef_floor > never_reviewed_long > overdue_long，逾期天数降序、EF升序）：
    - ef_floor：复习>=2次且EF<=1.35；
    - overdue_long：逾期>=7天；
    - never_reviewed_long：last_reviewed_at为空且due_date早于30天前。
  - Advice：服务端规则生成的大白话建议。
- 无 schema 变更，无数据库迁移。

### API
- `internal/api/review_health.go` 新增 `GET /api/review/health` 接口，按 `X-User` 或 `?user=` 隔离，沿用 `RegisterReviewRoutes` 注册风格。
- `internal/api/review.go` 加一行 `registerReviewHealthRoutes(mux, st)` 调用。

### 前端
- 复习统计页（`index.html`）新增「记忆健康」section：
  - 汇总 4 数字 chips。
  - EF 分布条。
  - 需关注卡片列表（button 点标题调 selectNote 跳转笔记，title 用 textContent 防 XSS）。
  - 建议列表。
- `app.js` 新增 `renderHealth(data)` 并在 `loadReviewStatsView` 里并行拉取（失败静默）。
- `style.css` 新增 `health-*` 样式，沿用 `--surface`、`--border`、`--radius-lg`、`--text`、`--text-3` 变量与 `#2b7de9` 蓝色系。

### 测试
- `internal/store/review_health_test.go` 新增 6 例（空库、汇总计数、ef_floor、overdue_long、never_reviewed_long、用户隔离）全部通过。
- 验收修 2 处：
  1. 测试曾假设"连续两次 grade=0 则 EF 降到 1.3"，但实际 SM-2 里 grade<3 时 EF 不变，改为直接 UPDATE 造数。
  2. Attention 优先级原为 efFloor>overdueLong>neverLong，导致从未复习的卡会被判成 overdue_long，改为 efFloor>neverLong>overdueLong。
- `go test ./...` 10 个包全绿（`-count=1` 无缓存重跑）；`go vet ./internal/store/ ./internal/api/` 全洁；`gofmt` 全洁。
- 真实服务冒烟：4 张测试卡（1 张正常复习、1 张 EF=1.3 复习5次、2 张从未复习且逾期）。
  - 接口返回 total=4/dueNow=2/overdue7d=2/neverReviewed=2/avgEf=2.2。
  - attention 3 条（never_reviewed_long x2 按逾期天数降序 + ef_floor）。
  - advice 3 条大白话，全部断言一致。
- 截图 `docs/screenshots/health-v017.png` 亲眼验收通过（布局撑满、无错字、零 console 错误）。
- `CHANGELOG.md` 新增 0.17.0 条目；`README.md` API 表新增 `GET /api/review/health` 行。

## 生产 Checklist 关键项自评表

| 维度 | 状态 | 理由 |
| :--- | :--- | :--- |
| 可靠性 | 通过 | 失败静默；无 schema 变更；纯新增代码，既有行为零变更。 |
| 可观测性 | 不适用 | 未新增指标/日志，沿用现有。 |
| 数据 | 通过 | 只读聚合，无迁移；attention 上限 20 防止大库拖慢。 |
| 部署 | 通过 | 无新依赖、无配置项、无迁移脚本。 |
| 安全 | 通过 | X-User 隔离沿用；title 经 textContent 输出防 XSS。 |
| 可维护性 | 通过 | 聚合逻辑集中在 ReviewHealth，API 薄透传。 |

## 已知限制

- ef_floor 在真实评分流里很难自然出现（grade<3 时 EF 不变，只有连续多次 grade=3 困难才会把 EF 打到 1.3 附近）。
- overdueDays 按 UTC 日期差计算。
- attention 上限 20 条，超出的不再展示。

## 结论

可发版。
