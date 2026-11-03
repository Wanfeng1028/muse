# second-brain v0.24.0 发版对照报告

## 改动范围

- 只改 internal/api/review_forecast.go 的 GET /api/review/forecast handler：import 增加 strconv；原始参数非空时 strconv.Atoi 解析，失败返回 400，文案“days 参数非法”；解析成功后钳制 <=0 置 7、>30 置 30。
- 新增测试文件 internal/api/review_forecast_validation_test.go。
- CHANGELOG 新增 [0.24.0] 一节。
- 其余文件（store 层、POST 405、前端、其他端点）一字未动。

## 实测数字

- 靶向 TestReviewForecast_DaysValidation 8/8 全绿。
- 既有 TestReviewForecast 三组（默认/钳制/405）全绿。
- go test ./... 全量 823 通过、0 失败。
- go vet 全洁。
- gofmt 本轮 2 个改动文件全洁（新测试文件仅补文件尾换行）。
- 真实服务冒烟（18427 端口隔离库）：days=abc/1.5 均 400 且 error 为“days 参数非法”、不传/0 均 200 且 days=7、days=99 均 200 且 days=30。

## 合同变更

- days=abc 从静默按默认值 7 处理改为显式返回 400。
- 前端只发 days=7，不受影响。

## 对照表

### 可靠性
通过：靶向 8/8 全绿，既有三组全绿，go test ./... 823 通过、0 失败。

### 可观测性
通过：非法 days 显式返回 400 且 error 文案为“days 参数非法”，真实服务冒烟可复现。

### 数据与状态
通过：无 schema 变更，无数据迁移；store 层钳制保留作兜底。

### 部署与运维
通过：无新配置项，部署方式与启动流程不变。

### 安全与健壮性
通过：非法输入显式 400 拒绝，不再静默按默认值处理。

### 可维护性
通过：无代码内版本号常量（版本记录以 CHANGELOG v0.24.0 一节为准），改动集中于单个 handler 及配套测试。视觉验收不适用：无 UI 改动。

## 结论

靶向范围可发版。

## 已知限制清单

- 只收紧 forecast 的 days 一个参数，heatmap 的 days 等仍沿用静默口径未动。
- store 层钳制保留作兜底。
- 前端未动。
- 0.23.0 预留给并行轮次的逾期前端接线（未提交），本轮顺延为 0.24.0。

2026-10-26