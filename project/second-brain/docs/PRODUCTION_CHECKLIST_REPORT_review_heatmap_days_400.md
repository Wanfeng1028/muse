# second-brain 发版对照报告：review_heatmap_days_400

## 改动摘要

- 接口：GET /api/review/heatmap
- days 非整数：由静默回落 365 改为返回 400，error 为“days 参数非法”
- days 缺省或空：仍默认 365
- 钳制逻辑：不变（<=0 置 365、>366 置 366）
- store 层：未改动
- 前端：只发 days=365，不受影响，无 UI 改动

## 验收范围

### 靶向测试

- 新测 TestReviewHeatmap_DaysValidation：8 子用例全绿
- 既有 TestReviewHeatmapAPI_Default、TestReviewHeatmapAPI_Clamp（已同步）、TestReviewHeatmapAPI_UserIsolation：全绿
- store 层 TestReviewHeatmap 与 forecast 的 TestReviewForecast_DaysValidation：回归全绿
- go vet：全洁
- gofmt：本轮 3 文件全洁

### 真实服务冒烟

- 18428 端口隔离库：8/8
- abc/1.5/1x：均 400，error 为“days 参数非法”
- 不传/1/0/999/-5：均 200，days 与 heatmap 长度分别为 365/1/365/366/365
- 冒烟后服务已停、端口复查已关

## 对照表

| 维度 | 结论 |
| --- | --- |
| 可靠性 | 通过 |
| 可观测性 | 通过 |
| 数据 | 通过 |
| 部署 | 通过 |
| 安全 | 通过 |
| 可维护性 | 通过 |

## 已知限制

- trend/digest 的 days/n 仍沿用静默回落口径，不在本轮范围
- 全量测试套件本轮未跑（只跑靶向组）