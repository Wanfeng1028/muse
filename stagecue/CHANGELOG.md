# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

# Changelog

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
