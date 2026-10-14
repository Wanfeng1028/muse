# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

# Changelog

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
