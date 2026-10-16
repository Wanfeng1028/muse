# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

# Changelog

## [Unreleased]

### 新增
- OpLog 文件持久化替代内存版：`FileOpLogStore` 每次 append 后 `fd.sync()`（崩溃不丢已落盘行）；启动加载跳过损坏行（截断尾行不拖垮启动）；`Main.kt` 接入 `SyncHub(opLog=...)`，oplog 落 `<dataDir>/oplog/oplog.jsonl`；重连回放：`Hello.lastSeenSeq` + `SyncHub.missedOps` + `OpLogReplay` 消息，客户端重连后自动补齐未同步条目（只做展示补齐，不重放执行）。
- 返听屏二期（MONITOR 只读接口）：`GET /api/monitor` 返回当前 cue + 倒计时 + 下一 cue；MONITOR 上线即推 `StateSnapshot` 全量快照；写操作鉴权：MONITOR 发 trigger_cue/arm_cue/set_rehearsal 返回 `FORBIDDEN` Error；新增 `SyncHub.monitorSnapshot`/`authorizeWrite`/`roleOf` 与 shared `MonitorState`。
- 测试：FileOpLogStoreTest 8 例（含重启恢复/并发 append/损坏尾行跳过）；MonitorApiTest 6 例（含 WS 真实鉴权与快照推送）。

### 文档
- `docs/OPERATIONS.md` 新增"返听屏（MONITOR）只读接口"节；`docs/TECH_DEBT.md` 第 9 项更新 v0.5 进度。

## [0.4.0] - 2026-10-16

### 新增
- Logback 日志轮转：控制台 + 文件双输出，日志落在 `STAGECUE_DATA_DIR/logs`；按天轮转、单文件 50MB 切分、保留 14 天、总量上限 512MB；日志级别跟 `STAGECUE_LOG_LEVEL`。
- Prometheus 告警规则示例 `docs/alerts/stagecue.rules.yml`：StageCueDown（critical）、WS 断开突增、限流 429 突增、广播丢包、迁移计数异常（4 个 warning）；Alertmanager 接收器示例（邮件 + 企业微信 webhook 占位）。
- docker-compose 资源限制：memory 512M / cpu 1.0 上限、128M 预留；容器日志 json-file 轮转（10m×5）。

### 文档
- `docs/OPERATIONS.md` 新增"告警规则"节（规则加载、5 条告警的含义与排查）；`docs/TECH_DEBT.md` 关闭"告警规则""日志轮转/资源限制"债务项。
- 新增 `docs/PRODUCTION_REPORT_v0.4.0.md` 发版对照报告。

## [0.3.0] - 2026-10-16

### 新增
- IP 令牌桶限流：`STAGECUE_RATE_LIMIT_RPS`（默认 60）/ `STAGECUE_RATE_LIMIT_BURST`（默认 120）
  环境变量配置，非法值启动即报错退出；超限返回 429 + `Retry-After` 头（秒）与 JSON 错误体；
  `GET /healthz`、`/readyz`、`/metrics` 探针免限流。
- `GET /readyz` 就绪检查：settings 表可读则 200 `{"status":"ready"}`，否则 503。
- WS 广播背压：每客户端独立有界队列（64）+ 专属发送协程；队列满时丢弃最旧（DROP_OLDEST），
  不断开慢消费者；丢弃数经 `stagecue_ws_broadcast_dropped_total` 可观测。
- 指标新增：`stagecue_http_rate_limited_total`（429 计数）、`stagecue_ws_broadcast_dropped_total`（广播丢弃计数）。

### 文档
- `docs/OPERATIONS.md` 新增限流调参说明；`docs/TECH_DEBT.md` 关闭"限流熔断"债务项。

## [0.2.0] - 2026-10-15

### 新增
- SQLite + Flyway 版本化迁移替代 JSON 文件存储（V1 建表、V2 settings 表；旧 show.json 自动幂等导入；WAL 模式）。
- `GET /metrics`：Micrometer Prometheus 指标（WS 连接、cue 触发/预备、HTTP 请求、迁移数）。
- 启动配置校验：非法 `STAGECUE_PORT`/`STAGECUE_LOG_LEVEL`/`STAGECUE_WS_PING_INTERVAL_MS`/`STAGECUE_DATA_DIR` 直接报错退出（exit 1）。
- 排练模式后端真实实现：服务端持久化开关 + WS `set_rehearsal`/`rehearsal_changed` 广播 + `CueFired.rehearsal` 标记 + `GET /api/rehearsal`；导演台开关直连服务端。
- MP3 音频解码（mp3spi + jlayer），WAV 回归通过。
- `docs/TECH_DEBT.md` 技术债集中记录；`docs/PRODUCTION_REPORT_v0.2.0.md` 发版对照报告。

### 修复
- 备份恢复流程真实演练通过（见 `docs/BACKUP_DRILL_v0.2.0.md`）。
## [0.1.0] - 2026-10-13

初始版本。

### 新增

- 同步服务（Ktor）：WebSocket 广播 cue 事件，HTTP `GET /api/show` 提供完整 show 数据。
- 桌面导演台（Compose Desktop）：cue 列表展示、触发、排练模式。
- 时间轴 cue 编排：新增、编辑、排序、删除 cue。
- 多端毫秒级同步：导演台触发后，所有已连接客户端收到 `CueFired` 事件。
- 离线优先：本地缓存 show 数据，网络恢复后自动重连并重新拉取。
- 音频播放：支持 WAV 格式。
- 数据持久化：`STAGECUE_DATA_DIR` 下的 JSON 文件。
- 配置项：`STAGECUE_PORT`、`STAGECUE_DATA_DIR`。
- CI：GitHub Actions 在 ubuntu-latest + Temurin JDK 21 上跑 `gradle build`。

### 已知问题

- 仅桌面导演台，移动端在二期。
- 音频仅 WAV。
- 多人同时编辑同一份 show 未支持。
