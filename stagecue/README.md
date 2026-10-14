# 舞监台 StageCue

小剧场演出还在靠微信群 + Excel + 人肉喊 cue。

StageCue 是一个开源的舞台监督工具：把 cue 表放到时间轴上，导演台按一下，所有屏幕、灯光、音效的提示同步触发。不用再对着微信语音喊"灯光准备——走"。

## 功能

- **时间轴 cue 编排**：每个 cue 有编号、描述、触发时间，拖一下就能改顺序。
- **多端毫秒级同步**：导演台按一下，返听屏、灯光台在同一帧收到信号。
- **排练模式**：服务端真实开关（重启不丢失），排练触发打标、不驱动真实设备，导演台一键切换。
- **离线优先**：本地存一份 show 数据，网络断了也能继续排练，连上后自动同步。
- **持久化**：SQLite + Flyway 版本化迁移，旧版 show.json 自动导入。

## 对比

|  | StageCue | QLab | 微信群 + Excel |
|---|---|---|---|
| 跨平台 | Windows / macOS / Linux | 仅 macOS | 是（但不是干这个的） |
| 中文界面 | 是 | 否 | 是 |
| 开源 | 是（Apache-2.0） | 否 | — |
| 价格 | 免费 | 按 license 收费 | 免费 |
| 多端同步 | 原生支持 | 需额外授权 | 靠人喊 |

## 快速开始

需要 JDK 21。

```bash
export PATH=~/workspace/toolchains/jdk/bin:$PATH
```

1. 启动同步服务：

   ```bash
   ./gradlew :server:run
   ```

2. 启动导演台：

   ```bash
   ./gradlew :desktopApp:run
   ```

3. 导演台打开后会自动连接 `localhost:8080`，右上角状态灯变绿就绪。

## 架构

```
┌──────────────┐   WebSocket   ┌──────────────┐   WebSocket   ┌──────────────┐
│   导演台     │ ◄───────────► │   同步服务   │ ◄───────────► │  返听屏 /    │
│ (Compose)    │               │   (Ktor)     │               │  灯光台(二期)│
└──────────────┘               └──────────────┘               └──────────────┘
```

导演台和同步服务之间跑一条 WebSocket，所有 cue 事件由服务端广播，客户端不做时间推算，避免时钟漂移。

## 可观测性

- `GET /healthz`：存活检查。
- `GET /metrics`：Prometheus 文本格式指标（WS 连接、cue 触发/预备、HTTP 请求、DB 迁移数），详见 `docs/OPERATIONS.md`。
- 日志：SLF4J + Logback，HTTP 请求带 `X-Request-Id`（CallId）全链路。

## 技术栈

- **Kotlin Multiplatform**：一套 model / protocol 代码，桌面端和二期移动端共用。
- **Ktor**：服务端和客户端的 WebSocket 都能用一套协程 API，写起来顺手。
- **Compose Desktop**：UI 声明式，改个 cue 列表不用碰 XML。

## 截图

![导演台](docs/screenshots/director.png)

> 真实截图待补。

## 已知限制

- 只有桌面导演台，没有移动端（返听屏/灯光台独立客户端在二期计划里）。
- 音频播放支持 WAV / MP3。
- 多人同时编辑同一份 show 暂不支持，先单导演。

## 许可

Apache-2.0。
