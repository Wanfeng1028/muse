
# Sentinel v0.7 发版对照报告（生产就绪检查）

## 对照标准

沿用 `PRODUCTION_CHECKLIST.md`，v0.7 增量为入队限流+投递熔断。

## 结论口径声明

本报告结论以 v0.7 已实现并通过验证的功能事实为准；凡未在本轮变更的条目，均沿用 v0.6 口径，不重复举证。

## §1 可靠性

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 失败重试 | 通过 | 沿用 v0.6 口径 |
| 指数退避 | 通过 | 沿用 v0.6 口径；与投递熔断正交 |
| 幂等/去重 | 通过 | 沿用 v0.6 口径 |
| 持久化 | 通过 | 沿用 v0.6 口径 |

**§1 结论：通过（沿用 v0.6 口径）**

## §2 可观测性

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 指标暴露 | 通过 | `/api/metrics` 新增 `sentinel_webhook_enqueue_rejected_total`（counter）、`sentinel_webhook_breaker_state{host}`（gauge，0=闭合/1=断开/2=半开） |
| 告警规则 | 通过 | `prometheus/rules/sentinel.yml` 从 6 条加到 8 条，新增 SentinelWebhookEnqueueRejected、SentinelWebhookBreakerOpen；rules 回归测试同步更新 |
| 日志 | 通过 | 入队超限 warn 日志；沿用 v0.6 口径 |

**§2 结论：通过**

## §3 性能与容量

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 吞吐 | 通过 | 沿用 v0.6 口径 |
| 背压 | 通过 | 沿用 v0.6 口径；入队限流提供入口侧保护 |
| 资源占用 | 通过 | 沿用 v0.6 口径 |

**§3 结论：通过（沿用 v0.6 口径）**

## §4 部署与运维

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 配置管理 | 通过 | 新增 4 个环境变量，非法值启动 fail-fast 中文报错 |
| 升级/回滚 | 通过 | 沿用 v0.6 口径 |
| 运行手册 | 通过 | `docs/OPERATIONS.md` 新增第 12 章（入队限流与投递熔断调参：变量表、何时调、丢弃取舍、观测排障） |

**§4 结论：通过**

## §5 安全与健壮性

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 限流/超时/熔断 | 通过 | 入队限流：`internal/notify/limiter.go` 令牌桶（满桶启动、并发安全），`QueueSender.Limiter` 字段 + `EnqueueWebhook` 入口检查，`SENTINEL_WEBHOOK_QUEUE_ENQUEUE_RPS`（默认 20；0=禁用；非零须 0.1~10000）、`SENTINEL_WEBHOOK_QUEUE_ENQUEUE_BURST`（默认 40；1~100000），超限丢弃+计数+warn 日志并返回 `ErrEnqueueRateLimited`。投递熔断：`internal/notify/circuit.go` 按下游 host 独立熔断（闭合→连续失败达阈值→断开→超时→半开单探测→成功回闭合/失败重回断开），断开期间该下游投递整条跳过且记录保留原样，`SENTINEL_WEBHOOK_BREAKER_FAILURE_THRESHOLD`（默认 5；1~100）、`SENTINEL_WEBHOOK_BREAKER_OPEN_TIMEOUT_SEC`（默认 300；10~86400），与指数退避/手动重试正交。冒烟证据：必失败 sink 下 2 次连续失败即熔断断开（`breaker_state==1`）；10 个死目标同时 down 的洪峰下入队限流拒绝 8 次（`enqueue_rejected_total=8`）；sink 恢复 200 后半开探测成功、熔断闭合（`breaker_state==0`）、投递最终 done |
| 输入校验 | 通过 | 沿用 v0.6 口径；新增环境变量非法值 fail-fast |
| 敏感信息 | 通过 | 沿用 v0.6 口径 |

**§5 结论：通过**

## §6 可维护性

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 测试覆盖 | 通过 | `go test ./...` 190/190 全过（v0.6 为 141）；新增 limiter/circuit/协同集成/config 解析测试，含 -race 并发；`go vet` 全洁；经手文件 `gofmt` 无输出 |
| 文档 | 通过 | CHANGELOG [0.7.0]；`docs/OPERATIONS.md` 第 12 章 |
| 代码结构 | 通过 | 沿用 v0.6 口径 |

**§6 结论：通过**

## §7 兼容性

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| API 兼容 | 通过 | 沿用 v0.6 口径 |
| 配置兼容 | 通过 | 新增环境变量均有默认值，不配置即沿用旧行为 |
| 数据兼容 | 通过 | 沿用 v0.6 口径 |

**§7 结论：通过（沿用 v0.6 口径）**

## §8 周期机制

| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 定时任务 | 通过 | 沿用 v0.6 口径 |
| 清理/归档 | 通过 | 沿用 v0.6 口径 |

**§8 结论：通过（沿用 v0.6 口径）**

## 汇总

### 通过

- §1 可靠性、§2 可观测性、§3 性能与容量、§4 部署与运维、§5 安全与健壮性、§6 可维护性、§7 兼容性、§8 周期机制

### 部分通过

- 无

### 不适用

- 无

### 未通过

- 无

### 本轮 v0.7 完成项

- 入队限流（`internal/notify/limiter.go`，令牌桶，满桶启动，并发安全）
- 投递熔断（`internal/notify/circuit.go`，按 host 独立熔断）
- 指标：`sentinel_webhook_enqueue_rejected_total`、`sentinel_webhook_breaker_state{host}` 进 `/api/metrics`
- 告警：`prometheus/rules/sentinel.yml` 由 6 条加到 8 条
- 文档：`docs/OPERATIONS.md` 第 12 章
- 测试：190/190 全过（v0.6 为 141），含 -race 并发，`go vet` 全洁
- 真实冒烟（S5）：熔断断开、限流拒绝 8 次、半开探测成功后闭合、投递 done
- 关闭 v0.6 排期：入队限流、投递熔断（§5 部分通过 → 通过）

### 本轮未做、改排期

- Go 工具链升级后依赖复扫（46 个标准库漏洞根因）

### 遗留挂账

- `incidents.html` 模拟数据债

## 诚实边界声明

- ①冒烟规模（10 目标、单机）不代表大规模故障风暴。
- ②熔断按 host 维度，同一 host 多 URL 共用一个熔断器。
