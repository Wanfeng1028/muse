# 哨兵 Sentinel

> 半夜宕机没人知道？哨兵帮你盯着。

一个用 Go 写的站点监控告警系统。单二进制，零外部依赖，SQLite 存数据，自带 Web UI。跑起来就能用。

## 特性

**生产级该有的都有：**

- 结构化日志（slog JSON），每条请求带 request_id，方便串日志
- `/healthz` 存活探针、`/readyz` 就绪探针，K8s 直接接
- Prometheus 指标 `/api/metrics`，监控系统自己也能被监控
- DB 迁移版本化，启动自动跑，幂等
- 自动备份 + `-restore` 一键恢复，已实测
- API Token 鉴权，Bearer 走标准头
- 检查失败指数退避重试，带 jitter
- 优雅关闭，inflight 检查等完再退

**灵魂功能：**

- **站点健康档案** `/profile?id=N`：7/30 天可用性、延迟分位、30 天每日柱状图、月度 SLA 一页看全
- **月度 SLA**：选月份，看可用性、检查数、宕机时长、是否达标 99.9%
- **公开状态页** `/status/{slug}`：对外展示，无需登录，客户直接看
- **状态页主题**：每页可配浅色/深色/自定义主色，`PUT /api/status-pages/{id}/theme`，访客可在页面上切换预览
- **订阅通知**：访客在状态页留邮箱订阅，宕机/恢复时收邮件；订阅需点确认链接（含退订），防滥用

## 截图

> 以下为真实运行抓屏，非设计稿。

- 总览：`docs/screenshots/dashboard.png`
- 站点健康档案：`docs/screenshots/profile.png`
- 公开状态页（浅色 / 深色 / 自定义主色三主题）：`docs/screenshots/status.png`、`docs/screenshots/status-dark.png`、`docs/screenshots/status-custom.png`

## 快速开始

三步。

```bash
# 1. 准备配置
cp .env.example .env
openssl rand -hex 32   # 把输出填进 .env 的 SENTINEL_API_TOKEN

# 2. 起服务
docker compose up -d

# 3. 打开浏览器
open http://localhost:8200
```

数据在 `sentinel-data` 卷，备份在 `sentinel-backups` 卷，容器重建不丢。

不想用 Docker？`make build` 后 `./bin/sentinel` 直跑。

## 配置

全部走环境变量，详见 `.env.example`。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SENTINEL_DB` | `data/sentinel.db` | SQLite 文件路径 |
| `SENTINEL_HOST` | `0.0.0.0` | 监听地址 |
| `SENTINEL_PORT` | `8200` | 监听端口 |
| `SENTINEL_WEBHOOK_URL` | 空 | 告警 webhook |
| `SENTINEL_API_TOKEN` | 空（必填） | API token |
| `SENTINEL_LOG_LEVEL` | `info` | 日志级别 |
| `SENTINEL_BACKUP_DIR` | `backups` | 备份目录 |
| `SENTINEL_BACKUP_KEEP` | `7` | 备份保留份数 |
| `SENTINEL_BACKUP_INTERVAL_H` | `24` | 备份间隔（小时） |
| `SENTINEL_CHECK_CONCURRENCY` | `8` | 并发检查上限 |
| `SENTINEL_CHECK_RETRY_MAX` | `3` | 失败重试次数 |
| `SENTINEL_TICK_SEC` | `10` | 调度 tick 间隔 |
| `SENTINEL_PUBLIC_URL` | 空 | 对外基地址，用于订阅邮件里的确认/退订链接；为空用相对路径 |

## API 一览

需鉴权的接口带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/monitors/{id}/profile` | 是 | 站点健康档案（可用性、延迟分位、30 天每日数据） |
| GET | `/api/monitors/{id}/sla?month=YYYY-MM` | 是 | 月度 SLA 报告 |
| PUT | `/api/monitors/{id}/public` | 是 | 设置是否公开，body `{"is_public":0|1}` |
| POST | `/api/status-pages` | 是 | 新建状态页，body `{"slug":"...","title":"..."}` |
| GET | `/api/status-pages` | 是 | 状态页列表 |
| POST | `/api/status-pages/auto` | 是 | 自动生成状态页 |
| GET | `/api/status/{slug}` | 否 | 公开状态页数据 |
| PUT | `/api/status-pages/{id}/theme` | 是 | 设置状态页主题，body `{"theme":"light\|dark","accent_color":"#rrggbb"}` |
| POST | `/api/status/{slug}/subscribe` | 否 | 订阅状态通知，body `{"email":"..."}`，返回 pending/already |
| GET | `/api/status/{slug}/confirm?token=...` | 否 | 订阅确认（邮件链接） |
| GET | `/api/status/{slug}/unsubscribe?token=...` | 否 | 退订确认页 |
| POST | `/api/status/{slug}/unsubscribe` | 否 | 执行退订，body `{"token":"..."}` |
| GET | `/healthz` | 否 | 存活探针 |
| GET | `/readyz` | 否 | 就绪探针 |
| GET | `/api/metrics` | 否 | Prometheus 指标 |

## 和 Uptime Kuma 对比

| 维度 | 哨兵 Sentinel | Uptime Kuma |
| --- | --- | --- |
| 部署形态 | 单 Go 二进制，零依赖 | Node.js 应用，需 Node 运行时 |
| 数据存储 | SQLite，开箱即用 | SQLite（内部用），配置项多 |
| 健康档案 + SLA + 状态页 | 一体，内置 | 状态页有，SLA 报表需插件或外部 |
| 资源占用 | 512MB 内存跑得动 | 通常更重 |
| 面向场景 | 自托管、想省事、要 SLA 报表 | 功能面更广、集成更多 |
| 学习成本 | 一个 `.env` + 一条 compose 命令 | 需要理解较多概念 |

两边都能用。你如果想要一个塞进去就不管的单二进制，选哨兵；如果想要生态和通知渠道最全，选 Kuma。

## 架构

```
                    ┌──────────────────────────┐
                    │        客户端 / 浏览器      │
                    └────────────┬─────────────┘
                                 │ HTTP :8200
                                 ▼
        ┌────────────────────────────────────────────────┐
        │               哨兵 Sentinel 进程                │
        │                                                │
        │  ┌──────────────┐    ┌──────────────────────┐  │
        │  │  HTTP 路由层   │    │  中间件：request_id   │  │
        │  │  /api/*      │◄───│  Bearer 鉴权 / 日志    │  │
        │  │  /status/*   │    └──────────────────────┘  │
        │  │  /healthz 等 │                              │
        │  └──────┬───────┘                              │
        │         │                                      │
        │  ┌──────▼───────┐    ┌──────────────────────┐  │
        │  │  业务 handler │    │  静态文件（内嵌）      │  │
        │  └──────┬───────┘    │  profile / status     │  │
        │         │            └──────────────────────┘  │
        │  ┌──────▼───────┐    ┌──────────────────────┐  │
        │  │  调度器 + 检查 │───►│  重试（指数退避）      │  │
        │  │  tick / 并发  │    └──────────────────────┘  │
        │  └──────┬───────┘                              │
        │         │                                      │
        │  ┌──────▼───────┐    ┌──────────────────────┐  │
        │  │  存储层（DB）  │    │  告警（webhook）       │  │
        │  │  迁移 / 备份   │    └──────────────────────┘  │
        │  └──────┬───────┘                              │
        │         │                                      │
        │  ┌──────▼───────┐                              │
        │  │  SQLite 文件  │  data/sentinel.db            │
        │  └──────────────┘                              │
        └────────────────────────────────────────────────┘
```

## 开发

```bash
make build     # 编译到 bin/sentinel
make test      # 跑全部测试
make run       # 本地起服务
```

跑测试前确保 `.env` 里的 `SENTINEL_API_TOKEN` 有值，测试会读。

## License

MIT
