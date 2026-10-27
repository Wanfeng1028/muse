# 发版对照报告：GET /api/digest 的 n 参数校验收紧

## 改动摘要
- 收紧 `GET /api/digest` 的 `n` 参数校验，口径与既有的 `GET /api/review/digest` 完全一致。
- 缺省或空 `n` 仍默认 5；非整数（如 `abc`、`1.5`、`1x`）直接返回 HTTP 400，错误文案逐字为 `n 参数非法`。
- 解析成功后钳制逻辑不变：`n` 小于等于 0 置 5、大于 200 置 200。
- 改动文件：`internal/api/review.go`（仅 `/api/digest` 处理器）；新增测试文件：`internal/api/digest_n_validation_test.go`。
- 不单独升版，仅记入 `CHANGELOG [Unreleased]` 的 Changed 节，与本轮之前已有的 trend/queue/digest 收紧条目并列。

## 测试与验收
- 新增测试：`TestDigest_NValidation_Invalid`（4 个子用例）与 `TestDigest_NValidation_Clamp`（4 个子用例），共 8 个子用例，全部通过。
- `go test ./internal/api/ -count=1`：通过。
- `go test ./...`：全量各包全部通过。
- `go vet`：无告警。
- `gofmt`：对 `internal/api/review.go` 与 `internal/api/digest_n_validation_test.go` 两个改动文件无差异。
- 真实服务冒烟（18451 端口隔离库）：建笔记 3 条均 201；`n=abc` 与 `n=1.5` 均 400，且 error 逐字为“n 参数非法”；不传 `n` 返回 3 条；`n=1` 返回 1 条；`n=0` 返回 3 条。冒烟后服务已停、端口复查已关、冒烟库与二进制已删除。

## 已知限制
- 本次改动不单独升版，作为 `Unreleased` 累积条目之一，与本轮之前已有的 trend/queue/digest 收紧条目一同待在下个版本统一发版。
- 全量套件与冒烟均已按上述数字执行并记录；除此之外未另跑其他附加场景。
