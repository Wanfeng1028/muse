# feedflow「信流」运维手册

本文档面向自托管部署的运维人员，说明环境变量、启动停止、Fever 接入、监控指标、备份恢复、升级回滚、故障排查与日志使用方式。

所有命令默认在项目根目录执行，容器内路径按镜像约定书写。

---

## 1. 环境变量

所有环境变量均以 `FEEDFLOW_` 前缀。可在 `.env` 或 `docker-compose.yml` 的 `environment` 中配置。默认值取自 `config.py` 的 `load()`。

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `FEEDFLOW_DB` | `data/feedflow.db` | SQLite 数据库文件路径。相对路径按项目根解析。容器示例：`/app/data/feedflow.db`（该路径仅为示例，需自行确认挂载）。 |
| `FEEDFLOW_HOST` | `127.0.0.1` | Flask 监听地址。容器内应设为 `0.0.0.0`。 |
| `FEEDFLOW_PORT` | `8300` | HTTP 监听端口，取值 1-65535，非法值启动即失败。需与 compose 端口映射一致。 |
| `FEEDFLOW_FETCH_INTERVAL` | `30` | 调度器抓取间隔，单位分钟，必须大于 0。数值越小抓取越频繁。 |
| `FEEDFLOW_FETCH_TIMEOUT` | `20` | 单次抓取超时，单位秒，必须大于 0。 |
| `FEEDFLOW_FETCH_RETRIES` | `3` | 抓取失败后的重试次数（不含首次），必须大于等于 0。 |
| `FEEDFLOW_USER_AGENT` | `FeedFlow/0.1` | 抓取时使用的 User-Agent。部分站点按 UA 拒绝或限流。 |
| `FEEDFLOW_LOG_LEVEL` | `INFO` | 日志级别，建议使用 `DEBUG` / `INFO` / `WARNING` / `ERROR`。排查问题时用 `DEBUG`。 |
| `FEEDFLOW_BACKUP_DIR` | `data/backups` | 备份输出目录。相对路径按项目根解析，默认与数据同盘，注意磁盘容量。 |
| `FEEDFLOW_DIGEST_N` | `20` | 摘要/汇总条目数量，必须大于等于 1。 |
| `FEEDFLOW_EXTRACT_TIMEOUT` | `15` | 正文提取单篇超时，单位秒，必须大于 0。超时后回落到 RSS 摘要。 |
| `FEEDFLOW_FEVER_API_KEY` | 空 | 为空表示 Fever 功能关闭。填入 key 后启用 `/fever`。生成方式见第 3 节。 |
| `FEEDFLOW_NO_SCHEDULER` | 未设置 | 设为 `1` 时禁用后台调度器，仅用于调试。 |

修改环境变量后需重启服务生效。

---

## 2. 启动与停止

前台启动（调试用，日志直接打到终端）：

```bash
python -m feedflow serve
```

只跑一次抓取，不进调度循环：

```bash
python -m feedflow fetch
```

调试时禁用后台调度器，只保留 HTTP 服务：

```bash
FEEDFLOW_NO_SCHEDULER=1 python -m feedflow serve
```

docker compose 后台启动（本机无 daemon，未在本机实跑验证，请以实际环境为准）：

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

停止前台进程用 `Ctrl-C`。

---

## 3. Fever 接入与运维

Fever 协议明文传输 api_key，自用场景建议只走内网，或前置反向代理加 HTTPS。

生成 api_key（交互式输入邮箱与密码，结果为 `md5(邮箱:密码)`）：

```bash
python -m feedflow fever-key
```

把生成的 key 写入环境变量并重启服务：

```bash
FEEDFLOW_FEVER_API_KEY=<你的api_key>
```

客户端（Fever 兼容阅读器）地址填：

```
http://你的机器:8300/fever/
```

未配置 key 时，访问 `/fever` 返回 `{"api_version":3,"auth":0}`，表示功能关闭。

轮换流程：重新运行 `python -m feedflow fever-key` 生成新 key → 更新 `FEEDFLOW_FEVER_API_KEY` → 重启服务 → 在所有客户端更新 key。旧 key 立即失效。

安全提醒：key 泄露后立刻按上述流程轮换；不要把 key 写进公开仓库或日志。

---

## 4. Prometheus 指标

`GET /metrics` 返回 Prometheus 文本格式，可直接被抓取。

| 指标名 | labels | 含义 |
| --- | --- | --- |
| `feedflow_http_requests_total` | `method`、`route`、`status` | HTTP 请求计数，按方法、路由、状态码分组。 |
| `feedflow_fetch_total` | `status` | 抓取总次数，按结果状态分组。 |
| `feedflow_fetch_errors_total` | `kind` | 抓取错误计数，`kind` 取值 `timeout` / `dns` / `http_4xx` / `http_5xx` / `parse_error` / `unknown`。 |
| `feedflow_articles_stored_total` | 无 | 已入库文章累计数量。 |
| `feedflow_fetch_duration_seconds_total` | 无 | 抓取耗时累计秒数。 |
| `feedflow_feeds_total` | 无 | 订阅源总数。 |
| `feedflow_articles_total` | 无 | 文章总数。 |
| `feedflow_unread_total` | 无 | 未读文章数。 |
| `feedflow_starred_total` | 无 | 加星文章数。 |

抓取示例：

```bash
curl -s http://127.0.0.1:8300/metrics
```

告警建议：

- `feedflow_fetch_errors_total` 在短时间内持续增长，说明抓取链路异常，按 `kind` 区分排查（见第 7 节）。
- `feedflow_unread_total` 异常归零，可能是数据库被清空或服务连到错误库，需人工确认。
- `GET /healthz` 返回 `status=degraded`，说明 db 异常，立即排查磁盘与数据库文件。

`GET /healthz` 返回 `{"status","version","db","scheduler","now"}`，正常时 `status=ok`。

---

## 5. 备份与恢复

备份：

```bash
python -m feedflow backup
```

恢复（需指定备份文件路径）：

```bash
python -m feedflow restore <备份文件路径>
```

`restore` 对非法备份文件抛 `ValueError` 并拒绝恢复，不会覆盖现有数据。备份与恢复的具体参数见 `Makefile` 中的 `backup` / `restore` 目标。

建议：执行恢复前先手动做一次当前库的快照，例如把 `FEEDFLOW_DB` 指向的文件复制到 `FEEDFLOW_BACKUP_DIR` 下另存一份，恢复失败时可退回。

---

## 6. 升级与回滚

数据库迁移用 SQLite `PRAGMA user_version` 做版本化，启动时检测到旧版本会自动升级，无需手工执行 SQL。

升级步骤：备份 → 停服务 → 拉取新版本 → 启动服务（自动迁移）→ 检查 `/healthz` 与 `/metrics`。

回滚步骤：停服务 → 用备份恢复数据库 → 切回旧版本代码 → 启动服务 → 检查 `/healthz`。

注意：升级后若已有数据写入，直接回滚到旧版代码可能不兼容新库结构，必须配合备份恢复。

---

## 7. 常见故障排查

| 现象 | 可能原因 | 排查命令 |
| --- | --- | --- |
| 抓取全部失败 | 网络不通、DNS 解析失败、目标站点 5xx、UA 被拒 | `curl -s http://127.0.0.1:8300/metrics \| grep feedflow_fetch_errors_total`，按 `kind` 区分：`timeout` 查网络与 `FEEDFLOW_FETCH_TIMEOUT`，`dns` 查解析，`http_4xx`/`http_5xx` 查目标站点，`parse_error` 查订阅源格式 |
| `/healthz` 返回 `degraded` | 数据库文件不可写、磁盘满、路径错误 | `curl -s http://127.0.0.1:8300/healthz`；检查 `FEEDFLOW_DB` 指向文件与所在目录权限 |
| `/fever` 返回 `auth=0` | 未配置 `FEEDFLOW_FEVER_API_KEY` | `echo $FEEDFLOW_FEVER_API_KEY`；未设置则按第 3 节生成并配置后重启 |
| OPML 导入 0 条 | 文件格式不符、字段缺失、编码问题 | 用文本编辑器确认 OPML 含 `outline` 节点与 `xmlUrl` 属性，另存为 UTF-8 后重试 |
| 磁盘满 | 数据库增长、备份堆积、日志膨胀 | `df -h`；清理 `FEEDFLOW_BACKUP_DIR` 下的旧备份；检查 `FEEDFLOW_DB` 大小 |

抓取失败会累计连续失败计数，并按指数退避重试：基准 `RETRY_BASE_SECONDS=2.0`，遇到 429 时读取 `Retry-After`，封顶 60 秒。

---

## 8. 日志使用

日志由 `feedflow/logging.py` 输出，格式为 JSON Lines，每行一个 JSON 对象，便于 grep 与结构化解析。

每条日志带 `request_id`，全链路可追踪：请求头 `X-Request-ID` 会透传或生成，并在响应头回写。排查某个请求时，从响应头取 `X-Request-ID`，再到日志里按该值过滤即可串起整条链路。

前台运行时日志直接输出到终端；容器中查看：

```bash
docker compose logs -f
```

调整 `FEEDFLOW_LOG_LEVEL` 到 `DEBUG` 后重启，可拿到更详细的过程日志。

