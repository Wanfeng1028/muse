# 文溯 DocSeek 运维手册（v0.5.0）

本地单机部署的运维指南：备份/恢复/升级/排障。所有命令默认在本仓库 `docseek/` 目录下执行。

## 1. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DOCSEEK_DB` | `$HOME/.local/share/docseek/docseek.db` | 数据库文件路径（命令行 `--db` 优先级更高） |
| `DOCSEEK_DICT_DIR` | （四级定位） | cppjieba 词典目录；定位顺序见 README |
| `DOCSEEK_LOG_LEVEL` | `info` | 日志级别：`debug`/`info`/`warn`/`error` |
| `DOCSEEK_SLOW_MS` | `500` | 慢查询阈值（毫秒），超限记入 `/api/metrics` 的 slow_queries 并可用于告警 |
| `DOCSEEK_LOCATE_CONCURRENCY` | `4` | `/api/locate` 最大并发数，超限回 429 |
| `DOCSEEK_LOCATE_WAIT_MS` | `2000` | 拿不到并发槽位时的最大等待（毫秒），超时回 429 |

注：上述三个变量的值必须整串合法，带尾随字符时（如 `0.001x`、`4x`）按默认值处理，不再静默截断接受。
| `DOCSEEK_JIEBA_VERBOSE` | （空） | 设为 `1` 恢复词典加载时的 limonp 噪音日志，用于排障 |

## 2. 日志

`serve` 的所有日志打到 stderr，单行 JSON（JSON Lines），可直接喂给 loki / fluent-bit：

```json
{"ts":"2026-10-15T05:30:00Z","level":"info","request_id":"r-000001","module":"http","msg":"request completed","method":"GET","path":"/api/locate","status":"200","latency_ms":"12.3"}
```

- 每个 HTTP 请求自动生成 `request_id`（`r-000001` 起），同时通过响应头 `X-Request-Id` 返回给客户端，方便把客户端报错和服务端日志对上。
- 异常请求记 `level=error`（含 error 字段），限流拒绝记 `level=warn`。

## 3. 指标

`GET /api/metrics` 返回实时指标：

```json
{
  "uptime_sec": 3600,
  "queries": {
    "search": {"count": 120, "avg_ms": 8.4, "max_ms": 3920.6},
    "locate": {"count": 45, "avg_ms": 3.1, "max_ms": 20.0}
  },
  "top_queries": [{"q": "全文检索", "count": 30}],
  "slow_queries": [{"ts": "...", "endpoint": "search", "q": "...", "latency_ms": 3920.6}],
  "locate_rejected": 0
}
```

- `slow_queries` 只保留最近 20 条；`top_queries` 取前 10。
- 告警建议：`slow_queries` 持续增长 → 查磁盘/大库；`locate_rejected` 非零 → 调大 `DOCSEEK_LOCATE_CONCURRENCY` 或加机器。

## 4. 备份与恢复

```bash
# 在线备份（SQLite backup API，备份时不阻塞读写）
docseek --db /data/docseek.db backup /data/docseek-backup.db

# 恢复：先校验备份有效性，再原子替换当前库（旧库的 -wal/-shm 一并清理）
docseek --db /data/docseek.db restore /data/docseek-backup.db
```

- 备份文件本身就是合法的库，可直接 `--db` 指向它验证（`docseek --db 备份文件 stats`）。
- 无效备份（垃圾文件/非文溯库）会被拒绝，exit 2，当前库不受影响。
- 建议每天一次定时备份（cron），保留最近 7 天。

## 5. 升级

单进程服务，升级即替换二进制：

1. 备份数据库（见第 4 节）。
2. 停服务（`Ctrl+C` 或 `kill -INT`，优雅停止；`kill -9` 也可，WAL 模式下数据不丢，2026-10-15 已实测）。
3. 替换 `docseek` 二进制（或 `docker compose up -d --build`）。
4. 启动后调 `/api/health` 确认版本号。

旧库自动迁移：`PRAGMA user_version` 机制，新版本打开旧库会自动重建 FTS 索引（事务包裹，失败回滚）。

## 6. 排障

| 现象 | 排查 |
|---|---|
| `search`/`locate` 报 `error in tokenizer constructor` | 词典没找到。检查 `DOCSEEK_DICT_DIR` 与四级定位路径（README 环境变量节）；注意 `stats` 等不碰 FTS 的命令不受影响，这是正常的 |
| 启动报 `无法定位 cppjieba 词典目录` | 同上，四个候选路径都不存在；Docker 部署确认镜像内 `/usr/local/share/docseek/dict` 存在 |
| `/api/locate` 回 429 | 并发超限，属限流保护；调大 `DOCSEEK_LOCATE_CONCURRENCY` 或排查是否有慢查询占住槽位（看 `/api/metrics`） |
| 索引慢 | v0.5.0 起索引走批量事务（每 500 文件提交），实测约 147 文件/秒；仍慢则查磁盘 IO |
| 端口被占用 | `serve --port 0` 自动分配，或换端口 |
| 测试里 `WatcherTest.SubDir` 偶发失败 | 已知 flaky（inotify 时序），与功能无关，重跑即可 |

## 7. Docker Compose 一键部署

```bash
cd docseek && docker compose up -d
```

- 数据库持久化在 `./data/docseek.db`；日志走 json-file 轮转（10MB × 3）。
- 把 `./docs` 换成自己的文档目录（只读挂载），或改 `command` 里的 `--watch`。
- 资源限制：`mem_limit: 512m`（2 核小机器实测够用）。

## 8. 依赖季度检查清单

Dependabot 管不了 CMake FetchContent，每季度人工过一遍：

- [ ] cppjieba：当前 v5.6.2，查上游 tag 有无安全修复（https://github.com/yanyiwu/cppjieba）
- [ ] googletest：当前 v1.14.0，查有无新版本
- [ ] SQLite amalgamation（third_party/sqlite3）：查有无 CVE
- [ ] Debian 基础镜像（Dockerfile）：`debian:12-slim` 有无安全更新

检查结论记入 CHANGELOG。
