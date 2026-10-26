# linkshort 发版对照报告：v1.28.0

## 改动摘要
GET /api/links/{id}/referers 的 n 参数校验收紧：非数字值直接返回 400（错误体 {"error": "n 非法"}）；缺参或空串维持默认 8；合法数字 ≤0 或 >100 仍回落为 8（既有口径不变）。其余统计端点一字未动，docs.html 无 referers 行，本轮不涉及。

## 验收范围
### 靶向测试
- 新增 internal/handler/link_referers_n_validation_test.go 6 例全绿（覆盖 n=abc/1.5/1x 返回 400 且体含 “n 非法”；不带 n/n=0/n=8 返回 200）。
- 既有 TestAnalyticsParamClamp（覆盖 referers?n=0 与 n=200 返回 200）、TestLinkDailyDaysValidation、TestAnalyticsReferersTopN 同跑通过。
- go vet 全洁，本轮改动文件 gofmt 全洁。

### 真实服务冒烟
- 18432 端口隔离库实测：建链 201。
- referers?n=abc 返回 400 且体为 {"error": "n 非法"}。
- referers?n=0 与不带 n 均返回 200，items 为空（冒烟库无点击数据，空列表为预期）。
- readyz 未带 key 返回 unauthorized，仅证明服务已起。
- 冒烟后服务已停、端口复查已关。

## 对照表
| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 可靠性 | 通过 | 非数字 n 已被 400 拦截，隔离库真机冒烟与靶向测试均验证。 |
| 可观测性 | 通过 | 非法 n 错误体明确为 {"error": "n 非法"}，合法数字边界回落逻辑由既有 TestAnalyticsParamClamp 覆盖。 |
| 数据 | 通过 | 新增 6 例测试覆盖 n=0 与无参等边界，确保空库环境下 200 且 items 为空行为正常。 |
| 部署 | 通过 | 18432 端口隔离库冒烟全绿，服务启停及端口复查符合预期。 |
| 安全 | 通过 | n 参数校验收紧，成功拦截 abc/1.5/1x 等非法输入。 |
| 可维护性 | 通过 | 新增独立单测文件覆盖校验逻辑，改动文件 gofmt/vet 全洁。 |

## 已知限制
- 全量 go test ./... 本轮未跑（仅跑靶向组）。
- 其余统计端点的 parseIntDefault 回落（stats/daily、top-links、top-referers、geo、hourly）不在本轮范围。
