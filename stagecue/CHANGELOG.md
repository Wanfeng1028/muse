# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
