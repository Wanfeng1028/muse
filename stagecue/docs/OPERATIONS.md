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
| `STAGECUE_HTTP_ENGINE` | `cio` | HTTP 引擎：cio（默认）或 netty；非法值启动即报错退出 |

示例：

```bash
export STAGECUE_PORT=9000
export STAGECUE_DATA_DIR=/var/lib/stagecue
./gradlew :server:run
```

## 告警规则

告警规则文件有两份，内容一样：

- 仓库里：`docs/alerts/stagecue.rules.yml`，给人看和给 Prometheus 加载都行。
- 发行版里：装好 server 后，在 server 安装目录的 `alerts/stagecue.rules.yml`，随包分发。

### 怎么让 Prometheus 加载

在 `prometheus.yml` 里加一行 `rule_files`，指向上面那个文件：

```yaml
rule_files:
  - /etc/prometheus/stagecue.rules.yml
```

改完重启 Prometheus，或者发 SIGHUP 让它重载配置。

### 5 条告警

| 告警名 | 级别 | 触发条件 | 可能原因 | 先查什么 |
| --- | --- | --- | --- | --- |
| StageCueDown | critical | `up{job="stagecue"} == 0` 持续 1 分钟 | 进程挂了、端口没监听、防火墙拦了、/metrics 路由坏了 | 先 `systemctl status` 看进程，再 `ss -lntp` 看端口，最后看 Prometheus 的 /targets 页面 |
| StageCueWsDisconnectSpike | warning | 5 分钟内断开速率 / 连接速率 > 0.5，持续 5 分钟 | 客户端网络抖动、反代空闲超时、广播异常踢连接、有人在压测 | 先看服务端日志里 WS 的关闭原因，再确认反向代理的 idle timeout 配置 |
| StageCueRateLimitSpike | warning | `rate(stagecue_http_rate_limited_total[5m]) > 5` 持续 5 分钟 | 压测、爬虫、限流阈值太低误伤、客户端死循环重试 | 先看访问日志的来源 IP 和 UA，判断是封来源还是调阈值 |
| StageCueBroadcastDrop | warning | `rate(stagecue_ws_broadcast_dropped_total[5m]) > 0` 持续 5 分钟 | 某个客户端消费太慢、网络卡顿、客户端机器负载高 | 先定位是哪个连接在拖后腿，再看那台机器和网络；演出中当事故处理 |
| StageCueDbMigrationStuck | warning | `changes(stagecue_db_migrations_applied[10m]) > 3` 立刻触发 | 数据目录被反复清空重建、部署脚本反复跑、测试环境误连生产库 | 先确认 `STAGECUE_DATA_DIR` 指向的目录有没有被反复清掉，再看部署记录 |

### 告警不响怎么办

先打开 Prometheus 的 `/alerts` 页面，看规则有没有加载成功。如果列表里根本没有这几条告警，说明 `rule_files` 路径写错了或者文件没读到，先解决这个，再谈别的。

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

## 返听屏（MONITOR）只读接口

- `GET /api/monitor`：返回 `{"current": <当前 cue 或 null>, "next": <下一 cue 或 null>, "remainingMs": <倒计时毫秒或 null>, "rehearsal": bool, "serverTimeMs": ...}`。只读，无鉴权，供返听屏首屏拉取。
- WS：MONITOR 上线（Hello role=MONITOR）后服务端即推一条 `state_snapshot` 全量快照；之后 cue 触发/预备经现有广播推送（`cue_fired`/`cue_armed`）。
- 越权写操作：MONITOR 发送 `trigger_cue`/`arm_cue`/`set_rehearsal` 会收到 `{"kind":"error","code":"FORBIDDEN",...}`，操作不执行、服务端状态不变。
- OpLog：`<dataDir>/oplog/oplog.jsonl`（JSON Lines）；重连时 Hello 带 `lastSeenSeq`，服务端回放未同步条目（`oplog_replay`，只做展示补齐，不重放执行）。

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

## HTTP 引擎切换

默认 CIO。生产/CI 环境如需 Netty：

```bash
export STAGECUE_HTTP_ENGINE=netty
```

- 取值大小写不敏感，仅接受 cio/netty，其他值启动时直接报错退出（fail-fast，不静默回退）。
- Netty 在本开发 VM 上曾因误用 KQueue 启动失败（见 docs/TECH_DEBT.md #7），CI/生产 Linux 环境可用；切引擎后先跑一遍 /healthz 与 /readyz 冒烟。
- 启动日志会打印实际生效的引擎（engine: cio/netty）。

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
