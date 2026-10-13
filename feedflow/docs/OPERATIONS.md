# feedflow「信流」运维手册

本文档面向自托管部署的运维人员，说明环境变量、备份恢复、升级回滚、常见故障排查与日志使用方式。

---

## 1. 环境变量

所有环境变量均以 `FEEDFLOW_` 前缀。可在 `.env.example` 或 `docker-compose.yml` 的 `environment` 中配置。

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `FEEDFLOW_DB` | `/app/data/feedflow.db` | SQLite 数据库文件绝对路径。目录需可写，容器内建议放在 `/app/data`。 |
| `FEEDFLOW_HOST` | `0.0.0.0` | Flask 监听地址。容器内应为 `0.0.0.0`，本机调试可改 `127.0.0.1`。 |
| `FEEDFLOW_PORT` | `8300` | HTTP 监听端口，需与 compose 的端口映射一致。 |
| `FEEDFLOW_FETCH_INTERVAL` | `15` | 调度器抓取间隔，单位分钟。数值越小抓取越频繁，注意目标站点压力。 |
| `FEEDFLOW_USER_AGENT` | `feedflow/1.0 (+https://github.com/feedflow)` | 抓取时使用的 User-Agent。部分站点会按 UA 拒绝或限流。 |
| `FEEDFLOW_FETCH_TIMEOUT` | `15` | 单次抓取超时，单位秒。网络较差时可适当增大。 |
| `FEEDFLOW_FETCH_RETRIES` | `2` | 抓取失败后的重试次数（不含首次）。遇到 5xx/超时时生效。 |
| `FEEDFLOW_LOG_LEVEL` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR`。排查问题时建议 `DEBUG`。 |
| `FEEDFLOW_BACKUP_DIR` | `/app/data/backups` | 备份输出目录。默认与数据同盘，注意磁盘容量。 |

修改环境变量后需重启服务生效：
