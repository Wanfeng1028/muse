# 生产检查清单对照报告（v0.11 发送重试）

本报告对照 v0.11「发送重试」的实际交付（`internal/push/retry.go`、`internal/store/push_status.go`、`internal/push/scheduler.go`、相关测试与文档）逐项核查生产检查清单。结论取值仅三种：**通过**（有对应实现且测试覆盖）、**未通过**（未实现或未验证，已写排期或列为已知限制）、**不适用**（本版本范围内无对应面，附理由）。

覆盖范围声明：本轮 `internal/api` 正在重构（`writeError` 签名变更中，包暂不可编译），`go test ./...` 全量待其完成后补跑；本报告覆盖 push/store/notify/markdown/review/search 六包共 110 个测试（push 15、store 49、notify 12、markdown 1、review 7、search 26），`go vet` 三包全洁、`gofmt` 全洁。

## 可靠性

| 检查项 | 结论 | 说明 |
|---|---|---|
| 发送失败具备重试机制 | 通过 | `internal/push/retry.go` 提供 `RetryPolicy` 与 `WrapWithRetry`，`MaxRetries+1` 次尝试；`SendWebPushWithRetry` 与 `scheduler.go` 的 `sendWebPushDigest` 逐订阅重试。测试覆盖"失败 2 次后成功"与"一直失败耗尽转死信"。 |
| 重试上限可配置且有硬上限 | 通过 | `SB_PUSH_MAX_RETRIES` 默认 3、上限 10；单测覆盖环境变量解析边界。 |
| 退避策略含基数与上限 | 通过 | `SB_PUSH_RETRY_BASE_MS` 默认 1000ms，`MaxBackoff` 30s。退避时长区间断言测试注入 rng+Sleep，不真睡。 |
| 退避含抖动避免惊群 | 通过 | 抖动 ±25%，退避区间断言测试覆盖。 |
| 区分可重试与不可重试错误 | 通过 | `IsRetryable`：ErrConn/网络、HTTP 429、5xx 可重试；ErrAuth、其他 4xx、ErrSubscriptionGone 不可重试；未知错误 fail-open 可重试。测试覆盖"不可重试直接死信且 0 睡眠"。 |
| 上下文取消立即退出 | 通过 | `WrapWithRetry` ctx 取消立刻退出，由测试覆盖。 |
| 重试耗尽落死信而非静默丢弃 | 通过 | `RunPushForUser` 与 `sendWebPushDigest` 耗尽转死信，写入 `push_log` status='failed_permanent'。 |
| 死信写入幂等 | 通过 | `RecordDeadLetter` 幂等，测试覆盖"重复写入不改写"。 |

## 可观测性

| 检查项 | 结论 | 说明 |
|---|---|---|
| 结构化日志 | 未通过 | 沿用标准 log，未引入结构化日志。排期 v0.12。 |
| request_id 贯穿 | 未通过 | 未实现 request_id 透传。排期 v0.12。 |
| metrics 暴露 | 未通过 | 未暴露重试次数、死信计数等 metrics。排期 v0.12。 |
| 死信可查询 | 通过 | `internal/store/push_status.go` 提供 `PushLogStatus` 查询；`docs/OPERATIONS.md` 含死信查询 SQL。 |
| 排障文档 | 通过 | 新建 `docs/OPERATIONS.md`，含死信查询 SQL 与排障步骤。 |

## 数据与状态

| 检查项 | 结论 | 说明 |
|---|---|---|
| 失败永久态持久化 | 通过 | `RecordDeadLetter` 写入 `push_log` status='failed_permanent'。 |
| 幂等写入 | 通过 | 死信幂等由测试覆盖（重复写入不改写）。 |
| 状态查询接口 | 通过 | `internal/store/push_status.go` 的 `PushLogStatus` 查询，store 包 49 测试全绿。 |
| 死信补发 | 未通过 | 死信不补发次日（见已知限制）。排期 v0.12。 |

## 部署与运维

| 检查项 | 结论 | 说明 |
|---|---|---|
| 容器化构建 | 通过 | 已有 Dockerfile，支持 Docker Compose。 |
| 一键部署（Compose 之外） | 未通过 | 未提供 Compose 之外的一键部署。排期 v0.12。 |
| 日志轮转 | 未通过 | 未实现日志轮转。排期 v0.12。 |
| 资源限制 | 未通过 | 未设置资源限制。排期 v0.12。 |
| 运维手册 | 通过 | 新建 `docs/OPERATIONS.md`（含死信查询 SQL 与排障）。 |

## 安全与健壮性

| 检查项 | 结论 | 说明 |
|---|---|---|
| 鉴权错误不重试 | 通过 | `IsRetryable` 对 ErrAuth 返回不可重试；测试覆盖不可重试直接死信且 0 睡眠。 |
| 订阅失效不重试 | 通过 | ErrSubscriptionGone 归为不可重试。 |
| 未知错误 fail-open | 通过 | 未知错误归为可重试，由 `IsRetryable` 实现。 |
| 重试上限防放大 | 通过 | `SB_PUSH_MAX_RETRIES` 上限 10，硬约束。 |
| 退避上限防长挂 | 通过 | `MaxBackoff` 30s。 |
| 安全审查/渗透 | 不适用 | 本版本为发送重试逻辑，未引入新外部接口面；无对应审查项。 |

## 可维护性

| 检查项 | 结论 | 说明 |
|---|---|---|
| 单元测试覆盖 | 通过 | push 15/15、store 49/49、notify 12/12、markdown 1/1、review 7/7、search 26/26 全绿。 |
| 静态检查 | 通过 | `go vet` 三包全洁。 |
| 格式检查 | 通过 | `gofmt` 全洁。 |
| 测试不依赖真实睡眠 | 通过 | 退避测试注入 rng+Sleep，不真睡。 |
| 模块边界清晰 | 通过 | 重试策略集中于 `internal/push/retry.go`，状态查询集中于 `internal/store/push_status.go`。 |

## 发版前对照

| 检查项 | 结论 | 说明 |
|---|---|---|
| 全量测试 | 未通过 | `go test ./...` 因 `internal/api` 重构（`writeError` 签名变更中，包暂不可编译）待其完成后补跑。 |
| api 集成测试 | 未通过 | `internal/api/push_retry_test.go` 待 api 重构完成后补。 |
| 真实冒烟 | 未通过 | 待 api 重构完成后补。 |
| 文档更新 | 通过 | README 推送章节加"发送重试"小节与两个环境变量；新建 `docs/OPERATIONS.md`。 |
| 发版说明 | 通过 | 本报告即为 v0.11 发版对照。 |

## 周期机制

| 检查项 | 结论 | 说明 |
|---|---|---|
| 定期死信巡检 | 未通过 | 未实现定时巡检，依赖 `PushLogStatus` 手动查询。排期 v0.12。 |
| 定期重试指标复盘 | 未通过 | 无 metrics，无法自动复盘。排期 v0.12。 |
| 文档随版本更新 | 通过 | README 与 `docs/OPERATIONS.md` 已随 v0.11 更新。 |
| 测试回归周期 | 不适用 | 依赖 CI 调度，非本版本交付范围。 |

## 已知限制

- **单实例**：重试与死信写入基于单实例假设，未实现分布式协调；多实例部署下死信幂等依赖存储层，未做跨实例去重验证。
- **死信不补发次日**：死信写入 `push_log` status='failed_permanent' 后不自动补发，需人工介入；补发排期 v0.12。
- **测试通道不重试**：测试通道（test channel）不走重试路径，仅生产发送路径受 `RetryPolicy` 约束。
- **全量测试待补**：`internal/api` 重构中，`go test ./...`、api 集成测试与真实冒烟均待其完成后补跑。