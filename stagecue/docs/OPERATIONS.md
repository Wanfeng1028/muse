# 运维手册

这份文档写给部署和维护 StageCue 的人。

## 环境要求

- JDK 21（Temurin 或 Oracle 均可）
- 操作系统：Linux / macOS / Windows
- 同步服务默认监听 `0.0.0.0:8080`
- 客户端到服务端的网络需可达，WebSocket 不要被反向代理拦掉

## 配置项

通过环境变量传入，都有默认值。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `STAGECUE_PORT` | `8080` | 同步服务监听端口 |
| `STAGECUE_DATA_DIR` | `./data` | 数据目录，存放 show 与 cue 表 |

示例：

```bash
export STAGECUE_PORT=9000
export STAGECUE_DATA_DIR=/var/lib/stagecue
./gradlew :server:run
```

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

所有状态都在 `STAGECUE_DATA_DIR` 下，直接拷走即可：

```bash
tar czf stagecue-backup-$(date +%F).tar.gz -C "$STAGECUE_DATA_DIR" .
```

建议在排练前和演出前各做一次。cue 表改动频繁时，可以加个 cron 每小时增量拷。

## 恢复

1. 停止同步服务。
2. 清空或移走原 `STAGECUE_DATA_DIR`。
3. 解包备份：

   ```bash
   mkdir -p "$STAGECUE_DATA_DIR"
   tar xzf stagecue-backup-2026-10-13.tar.gz -C "$STAGECUE_DATA_DIR"
   ```

4. 启动同步服务，导演台连上后确认 cue 列表条数对得上。

## 升级

1. 备份 `STAGECUE_DATA_DIR`。
2. `git pull` 或切到目标 release tag。
3. `./gradlew build`。
4. 停旧进程，起新进程。
5. 客户端升级到匹配版本（协议字段有变动时，旧客户端可能连不上）。

如果数据格式有迁移，README 或 release notes 会说明。

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
