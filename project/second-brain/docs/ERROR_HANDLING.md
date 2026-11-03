# 错误处理策略（second-brain）

这份文档说明 second-brain 出错时怎么办。分成四块：重试、幂等、降级、fail-fast。最后一块诚实列出还没做好的地方。

## 1. 重试

推送发送失败时，我们不会立刻放弃，而是按策略重试几次。策略定义在 internal/push/retry.go 的 RetryPolicy 里。

### 策略参数

| 参数 | 默认值 | 环境变量 | 上限 | 说明 |
| --- | --- | --- | --- | --- |
| MaxRetries | 3 | SB_PUSH_MAX_RETRIES | 10 | 最多重试几次 |
| BaseBackoff | 1000ms | SB_PUSH_RETRY_BASE_MS | 60000 | 第一次退避的基准时间 |
| MaxBackoff | 30s | 无 | 无 | 单次退避不超过这个值 |
| JitterRatio | 0.25 | 无 | 无 | 退避时间上随机抖动的比例 |

退避按指数增长，但被 MaxBackoff 封顶。JitterRatio 让每次退避时间上下浮动，避免多个任务同时重试撞在一起。

### 什么错误会重试

- 网络错误
- HTTP 429（限流）
- HTTP 5xx（服务端错误）
- 未知错误：fail-open，当作可重试处理

### 什么错误不重试

- 鉴权类错误（token 无效、权限不足）
- 其他 4xx（请求本身有问题，重试也没用）
- 订阅失效（410 / 404）
- context 被取消

判断逻辑在 IsRetryable 里。WrapWithRetry 把 sender 包一层，调用方不用自己写重试循环。

### 重试耗尽怎么办

重试次数用完还是失败，就转死信。记录方式是把 push_log 的 status 写成 'failed_permanent'，同时调 RecordDeadLetter 记一条死信。RecordDeadLetter 本身是幂等的，同一批次重复调用不会写两条。

## 2. 幂等

这些操作重复执行是安全的，不会产生重复数据或副作用：

- Migrate()：重复调用是 noop。当前 schema 版本记在 schema_version 表里，已经是最新版本就什么都不做。
- RecordPushFor：同一天、同一渠道、同一用户重复记录会去重。
- RecordDeadLetter：同一批次不会重复进死信。
- seed-vocab：按 word 去重，重复执行不会插重复词。

## 3. 降级

某些环节出问题时，我们选择让整体继续跑，而不是整个挂掉：

- sender 为 nil 的通道直接跳过，不影响其他通道。
- /metrics 端点的 gauge 回调如果 panic，safeCall 会把它按 NaN 输出，不会让整个端点返回 500。
- 推送调度里单个通道失败，不影响其他通道继续发。
- review digest 没有到期内容时，仍然生成一条"今日无待复习"的消息，而不是报错或什么都不发。

## 4. fail-fast

非法配置在启动时直接拒绝，不让服务带着坏配置跑起来。这类情况会走 log.Fatalf：

- SB_PUSH_TIME 格式错误
- 限流参数非法
- metrics token 非法
- 其他同类非法配置

### 日志

日志用结构化 slog，输出 JSON。每个请求带 request_id，通过 X-Request-ID 头透传，没有就生成一个。错误响应体里统一带上 request_id，方便对日志。

## 5. 未覆盖的降级缺口

这两块目前还没做好，如实列出：

- 多实例部署的分布式锁缺失。当前没有跨实例的锁机制，多实例同时跑调度会重复触发。单实例约束的说明见 SCHEDULER_DEPLOYMENT.md。
- 离线写队列回放冲突策略未定义。离线期间攒下的写操作在回放时如果和线上状态冲突，目前没有明确的处理规则。
