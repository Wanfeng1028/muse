# 运维手册

这份文档写给部署和维护 StageCue 的人。

## 环境要求

- JDK 21（Temurin 或 Oracle 均可）
- 操作系统：Linux / macOS / Windows
- 同步服务默认监听 `0.0.0.0:8080`
- 客户端到服务端的网络需可达，WebSocket 不要被反向代理拦掉
- 指标端点 `GET /metrics`（Prometheus 文本格式，无需鉴权，局域网可信环境）

## 配置项

通过环境变量传入，都有默认值。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `STAGECUE_PORT` | `8080` | 同步服务监听端口 |
| `STAGECUE_DATA_DIR` | `./data` | 数据目录，存放 stagecue.db（SQLite）与备份 |
| `STAGECUE_RATE_LIMIT_RPS` | `60` | 每 IP 每秒补充的令牌数（限流速率） |
| `STAGECUE_RATE_LIMIT_BURST` | `120` | 每 IP 令牌桶容量（突发上限） |

示例：

```bash
export STAGECUE_PORT=9000
export STAGECUE_DATA_DIR=/var/lib/stagecue
./gradlew :server:run
```

## 启动校验

`ServerConfig.fromEnv().validateOrExit()` 在进程启动时校验全部环境变量，任一项非法直接打印中文错误并退出（exit 1），不会带病运行：

- `STAGECUE_PORT` 不是 1~65535 的整数
- `STAGECUE_LOG_LEVEL` 不是 `DEBUG` / `INFO` / `WARN` / `ERROR` 之一
- `STAGECUE_WS_PING_INTERVAL_MS` 不是 ≥1000 的整数
- `STAGECUE_DATA_DIR` 不存在且无法创建，或不可写
- `STAGECUE_RATE_LIMIT_RPS` 不是 ≥1 的整数
- `STAGECUE_RATE_LIMIT_BURST` 不是 ≥1 的整数

## 启动与停止

启动：

```bash
./gradlew :server:run
```

前台运行，日志打在 stdout。生产部署建议用 systemd 或 supervisord 托管，`SIGTERM` 会触发优雅关闭。

停止：

```bash
kill <pid>
```

或 systemd：

```bash
systemctl stop stagecue
```

## 备份

所有状态都在 `STAGECUE_DATA_DIR` 下，核心是 `stagecue.db`（SQLite，WAL 模式）。**必须停服务后备份**——WAL 模式下在线热拷可能拿到不一致快照：

```bash
# 1. 停服务
systemctl stop stagecue  # 或 kill <pid>，等优雅关闭完成
# 2. 打包
tar czf stagecue-backup-$(date +%F).tar.gz -C "$STAGECUE_DATA_DIR" .
# 3. 起服务
systemctl start stagecue
```

建议在排练前和演出前各做一次。v0.2.0 已做备份→删库→恢复真实演练（见 `docs/BACKUP_DRILL_v0.2.0.md`）。

## 恢复

1. 停止同步服务。
2. 清空或移走原 `STAGECUE_DATA_DIR`。
3. 解包备份：

   ```bash
   mkdir -p "$STAGECUE_DATA_DIR"
   tar xzf stagecue-backup-2026-10-13.tar.gz -C "$STAGECUE_DATA_DIR"
   ```

4. 启动同步服务，看日志确认 `Flyway migrate 完成`（`Schema "main" is up to date`），再执行恢复验证三板斧：
   - `curl http://localhost:8080/api/show`：核对 cue 条数与名字
   - `curl http://localhost:8080/api/rehearsal`：核对排练开关状态
   - `curl http://localhost:8080/metrics`：确认指标端点正常

## 升级

1. 备份 `STAGECUE_DATA_DIR`。
2. `git pull` 或切到目标 release tag。
3. `./gradlew build`。
4. 停旧进程，起新进程。
5. 客户端升级到匹配版本（协议字段有变动时，旧客户端可能连不上）。

如果数据格式有迁移，README 或 release notes 会说明。

### v0.1.0 → v0.2.0 数据迁移（JSON → SQLite）

1. 按"备份"节停服务并打包。
2. 部署 v0.2.0 并启动：Flyway 自动建表（V1 show_meta/cue、V2 settings）。
3. 若数据目录下有旧 `show.json` 且 cue 表为空，启动时自动导入（幂等，重复启动不重复导入；损坏的 JSON 只记 warn，不阻断启动）。
4. `curl http://localhost:8080/api/show` 核对 cue 条数与 v0.1.0 一致。

## /metrics 指标

`GET /metrics` 返回 `text/plain; version=0.0.4`：

| 指标 | 类型 | 说明 |
|---|---|---|
| `stagecue_ws_connections_total` | counter | WebSocket 连接建立次数 |
| `stagecue_ws_disconnections_total` | counter | WebSocket 连接断开次数 |
| `stagecue_cues_triggered_total{rehearsal="true"\|"false"}` | counter | cue 触发次数（按是否排练打标签） |
| `stagecue_cues_armed_total` | counter | cue 预备次数 |
| `stagecue_http_show_requests_total` | counter | `GET /api/show` 请求次数 |
| `stagecue_db_migrations_applied` | gauge | 启动时 Flyway 执行的迁移数 |
| `stagecue_http_rate_limited_total` | counter | 被限流拒绝的 HTTP 请求数（429） |
| `stagecue_ws_broadcast_dropped_total` | counter | WS 广播因慢消费者丢弃的消息数 |

## 排练模式

- 服务端状态，持久化在 `settings` 表（key=`rehearsal`），重启不丢失。
- 排练模式下触发的 cue，`CueFired.rehearsal=true` 并广播；灯光台/返听屏等执行端应只做提示、**不驱动真实设备**；导演台本地音频仍可播放（排练也要听声音）。
- 切换：WS 发 `set_rehearsal`，服务端广播 `rehearsal_changed`；查询：`GET /api/rehearsal` 返回 `{"rehearsal": true|false}`。

## 限流调参

每个客户端 IP 一个令牌桶，每秒补充 RPS 个令牌、桶最多装 BURST 个；每次 HTTP/WS 请求消耗 1 个，没令牌就 429，告诉客户端多少秒后再试（Retry-After）。

调参建议：

- 局域网演出默认 60/120 够用。
- 导演台是单 IP 高频操作（连点触发 cue），如果导演台被 429 拦了，把 BURST 调大（如 300）。
- 公网暴露时 RPS 可收紧到 20~30。

观察指标：

- `stagecue_http_rate_limited_total` 持续增长说明有人被限流，先看是不是误伤正常客户端。
- `stagecue_ws_broadcast_dropped_total` 增长说明有慢消费者，检查该返听屏/灯光台的网络，或考虑调大队列（目前 64，改代码常量）。

探针（/healthz、/readyz、/metrics）不走限流，反向代理的健康检查不会被误杀。

## 常见故障

### 端口占用

症状：启动日志出现 `Address already in use`。

排查：

```bash
lsof -i :8080
```

改 `STAGECUE_PORT` 或杀掉占用进程。

### 客户端连不上

症状：导演台右上角状态灯一直是灰的，日志刷 `连接断开`。

排查顺序：

1. 同步服务是否在跑：`curl http://localhost:8080/api/show`。
2. 防火墙是否放行 `STAGECUE_PORT`。
3. 反向代理是否支持 WebSocket Upgrade（Nginx 需要 `proxy_set_header Upgrade $http_upgrade;` 和 `Connection "upgrade"`）。
4. 客户端配置的 host/port 是否和服务端一致。

### 时钟漂移告警

症状：导演台日志出现"时钟漂移"提示，或 cue 触发比预期晚。

StageCue 不做本地时间推算，所有事件以服务端广播为准。出现漂移告警通常说明：

- 服务端机器负载过高，广播延迟累积。
- 客户端机器系统时间被 NTP 大幅调整过。

处理：

1. 检查服务端 CPU / 内存。
2. 在服务端和客户端都开启 NTP 同步。
3. 重启同步服务，让所有客户端重新握手。
