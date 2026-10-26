# linkshort 项目发版对照报告 v1.27.0


## 版本与改动
- 版本：v1.27.0
- 改动：GET /api/links/{id}/daily 的 days 参数校验收紧——非数字值返回 400，错误体为 {"error": "days 非法"}；此前非数字值经默认值回落静默按 30 天统计；缺参或空串仍默认 30；合法数字小于等于 0 或大于 365 时仍回落为 30（既有口径不变，既有 TestAnalyticsParamClamp 要求 days=0 与 days=999 返回 200）。

## 测试与检查
- 靶向测试：新增 internal/handler/link_daily_days_validation_test.go 6 例全绿（days_abc、days_float、days_suffix 返回 400 且体含“days 非法”；days_missing、days_zero_clamp、days_valid 返回 200）；既有 TestAnalyticsParamClamp 同跑通过。
- 全量套件：go test ./... -race -count=1，14 个包全部通过（handler 包耗时 210.874 秒，为最慢项；其余包均在 35 秒内）。
- 静态检查：go vet ./... 全洁；本轮 2 个 Go 改动文件 gofmt 全洁（新测试文件经 gofmt -w 补齐文末换行后全洁）。
- 真实服务冒烟（18471 端口 :memory: 隔离库，冒烟后服务已停、端口复查已关）：健康检查 200；建链成功（id 1，slug smoke0407）；days=abc、days=1.5、days=1x 均返回 400 且错误体逐字为 {"error": "days 非法"}；不带 days 返回 200 且 30 条；days=0 返回 200 且 30 条；days=7 返回 200 且 7 条；文档页 /docs 实测含新口径短语。

## 环境限制说明
冒烟用 :memory: 隔离库；文件库启动路径未在本轮实测（与 v1.26.0 报告相同的已知限制）；单元与全量测试中的文件库用例仍全绿。

## 无变更项
无 schema 变更、无迁移、无新增环境变量、无 UI 结构改动（仅文档页一行文字，视觉验收不适用）；版本号只记 CHANGELOG（代码内无版本常量）。

## PRODUCTION_CHECKLIST 七条对照
1. 可靠性通过
2. 可观测性不适用
3. 数据与状态不适用
4. 部署运维不适用（冒烟隔离库说明见已知限制）
5. 安全与健壮性通过（输入校验收紧即本轮内容）
6. 可维护性通过（CHANGELOG v1.27.0 一节、新测试文件与文档同步）
7. 发版对照即本文件