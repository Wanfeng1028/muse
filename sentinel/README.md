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
- 事件幂等：并发检查同一监控只产生一个 open 事件，不重复告警

**灵魂功能：**

- **站点健康档案** `/profile?id=N`：7/30 天可用性、延迟分位、30 天每日柱状图、月度 SLA 一页看全
- **月度 SLA**：选月份，看可用性、检查数、宕机时长、是否达标 99.9%
- **全站月度 SLA 总报** `/sla-report`：全部监控按月聚合，一页看全站可用性、最差监控与逐监控表，可导出中文 HTML 月报
- **全站 SLA 趋势** `/sla-trend`：最近 N 个月（3/6/12）全站逐月对比，含可用性条形与中文 HTML 导出
- **公开状态页** `/status/{slug}`：对外展示，无需登录，客户直接看
- **状态页主题**：每页可配浅色/深色/自定义主色，`PUT /api/status-pages/{id}/theme`，访客可在页面上切换预览
- **订阅通知**：访客在状态页留邮箱订阅，宕机/恢复时收邮件；订阅需点确认链接（含退订），防滥用
- **告警投递队列**：webhook 告警先入 SQLite 队列表，后台 worker 按指数退避重投（默认最多 8 次），`/deliveries` 页可看投递状态、手动重投，失败不再丢告警
- **短信告警**：mock/阿里云/腾讯云三通道，监控可配短信渠道与接收号码，发送记录持久化到 sms_log 表，`/sms-log` 页可查每条短信的发送结果
- **维护窗口**：窗口内调度检查整段跳过，不产生检查记录与新事件；手动检查不受影响，`/maintenance` 页可新建/删除（监控 ID 为 0 表示全部监控）
- **监控分组**：监控按业务线归组（新建/删除分组、监控加入/移出分组、按组查看成员），只做归类与筛选，不影响检查调度与告警，`/groups` 页管理
- **分组 SLA 月报**：按分组聚合当月可用性（检查加权、最差监控、故障归因），只统计组内监控，`/group-sla` 页按分组与月份查看，可导出中文 HTML 月报
- **分组 SLA 趋势**：按分组聚合最近 N 个月（3/6/12）逐月可用性（检查加权、最差监控、宕机时长），只统计组内监控，`/group-sla-trend` 页按分组与截止月份查看，可导出中文 HTML 趋势
- **单监控 SLA 趋势**：单个监控最近 N 个月（3/6/12）逐月可用性（检查数、事件数、宕机时长、是否达标），只统计该监控，`/monitor-sla-trend` 页按监控与截止月份查看，可导出中文 HTML 趋势
- **全站年度 SLA 报告**：全年 12 个月全站聚合（检查加权可用性、检查总数、事件总数、宕机时长、最佳与最差月份、故障归因），最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月，`/sla-year` 页按年份查看，可导出中文 HTML 年报
- **分组年度 SLA 报告**：全年 12 个月按分组聚合（检查加权可用性、检查总数、事件总数、宕机时长、最佳与最差月份、故障归因），只统计组内监控，最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月，`/group-sla-year` 页按分组与年份查看，可导出中文 HTML 年报
- **单监控年度 SLA 报告**：全年 12 个月按单监控聚合（检查加权可用性、检查总数、事件总数、宕机时长、最佳与最差月份、故障归因），只统计该监控，最佳与最差月份只在有检查的月份中评选、全年无检查时回落首月，`/monitor-sla-year` 页按监控与年份查看，可导出中文 HTML 年报
## 截图

> 以下为真实运行抓屏，非设计稿。

- 总览：`docs/screenshots/dashboard.png`
- 站点健康档案：`docs/screenshots/profile.png`
- 公开状态页（浅色 / 深色 / 自定义主色三主题）：`docs/screenshots/status.png`、`docs/screenshots/status-dark.png`、`docs/screenshots/status-custom.png`
- 投递队列：`docs/screenshots/deliveries.png`
- 短信记录：`docs/screenshots/sms-log.png`
- 可用性画像 v1（抖动评分 + 故障时间线）：`docs/screenshots/profile-v2-20261020.png`
- SLA 月报 HTML 导出：`docs/screenshots/sla-html-20261020.png`
- 一键发布的公开状态页静态站：`docs/screenshots/status-published-20261020.png`
- 快照归档管理页（定时计划/立即生成/下载/删除）：`docs/screenshots/snapshots-20261024.png`
- 维护窗口：`docs/screenshots/maintenance-v023.png`
- 监控分组：`docs/screenshots/groups-v024.png`
- 分组 SLA 月报：`docs/screenshots/group-sla-v025.png`
- 分组 SLA 趋势：`docs/screenshots/group-sla-trend-v026.png`
- 单监控 SLA 趋势：`docs/screenshots/monitor-sla-trend-v027.png`
- 全站年度 SLA 报告：`docs/screenshots/sla-year-v028.png`
- 分组年度 SLA 报告：`docs/screenshots/group-sla-year-v029.png`
- 事件页状态筛选（全部/仅进行中）：`docs/screenshots/incidents-status-all.png`、`docs/screenshots/incidents-status-open.png`
- 事件页点击行展开详情（事件 ID、监控、开始时间、恢复时间、持续、状态、触发原因）：`docs/screenshots/incidents-detail-collapsed.png`、`docs/screenshots/incidents-detail-expanded.png`

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
| `SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS` | `8` | webhook 投递最大次数（1~20） |
| `SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC` | `60` | 投递退避基数秒（5~3600） |
| `SENTINEL_WEBHOOK_QUEUE_TICK_SEC` | `15` | 队列 worker 扫描间隔秒（5~300） |
| `SENTINEL_API_TOKEN` | 空（必填） | API token || `SENTINEL_LOG_LEVEL` | `info` | 日志级别 |
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
| GET | `/api/monitors/{id}/profile` | 是 | 站点健康档案（可用性、延迟分位、30 天每日数据、抖动评分、故障时间线） |
| GET | `/api/monitors/{id}/sla?month=YYYY-MM` | 是 | 月度 SLA 报告 |
| GET | `/api/monitors/{id}/sla.html?month=YYYY-MM` | 是 | 月度 SLA 报告（中文 HTML，可存档） |
| GET | `/api/sla?month=YYYY-MM` | 是 | 全站月度 SLA 总报（全部监控聚合） |
| GET | `/api/sla.html?month=YYYY-MM` | 是 | 全站月度 SLA 总报（中文 HTML，可存档） |
| GET | `/api/sla/trend?end=YYYY-MM&months=N` | 是 | 全站 SLA 趋势（最近 N 个月逐月聚合，N=1~12，默认 end=当月、months=6） |
| GET | `/api/sla/trend.html?end=YYYY-MM&months=N` | 是 | 全站 SLA 趋势（中文 HTML，含逐月表与可用性条形） |
| PUT | `/api/monitors/{id}/public` | 是 | 设置是否公开，body `{"is_public":0|1}` |
| POST | `/api/status-pages` | 是 | 新建状态页，body `{"slug":"...","title":"..."}` |
| GET | `/api/status-pages` | 是 | 状态页列表 |
| POST | `/api/status-pages/auto` | 是 | 自动生成状态页 |
| POST | `/api/status-pages/{id}/publish` | 是 | 一键发布公开状态页静态站（原子写入，失败旧版本不受影响） |
| POST | `/api/status-pages/{id}/publish/rollback` | 是 | 回滚到上一发布版本 |
| GET | `/api/status-pages/{id}/publish` | 是 | 查询发布状态 |
| GET | `/api/status/{slug}` | 否 | 公开状态页数据 |
| PUT | `/api/status-pages/{id}/theme` | 是 | 设置状态页主题，body `{"theme":"light\|dark","accent_color":"#rrggbb"}` |
| POST | `/api/status/{slug}/subscribe` | 否 | 订阅状态通知，body `{"email":"..."}`，返回 pending/already |
| GET | `/api/status/{slug}/confirm?token=...` | 否 | 订阅确认（邮件链接） |
| GET | `/api/status/{slug}/unsubscribe?token=...` | 否 | 退订确认页 |
| POST | `/api/status/{slug}/unsubscribe` | 否 | 执行退订，body `{"token":"..."}` |
| GET | `/api/alerts/deliveries` | 是 | 投递队列列表（status/monitor_id/limit 过滤） |
| POST | `/api/alerts/deliveries/{id}/retry` | 是 | 手动重投（仅失败/重试中） |
| POST | `/api/maintenance` | 是 | 新建维护窗口，body `{"monitor_id":0,"title":"...","starts_at":"...","ends_at":"..."}`（monitor_id 为 0 表示全部监控） |
| GET | `/api/maintenance` | 是 | 维护窗口列表 |
| DELETE | `/api/maintenance/{id}` | 是 | 删除维护窗口 |
| POST | `/api/groups` | 是 | 新建分组，body `{"name":"..."}`，空名/重名返回 400 |
| GET | `/api/groups` | 是 | 分组列表（含各组监控数） |
| DELETE | `/api/groups/{id}` | 是 | 删除分组（成员关联一并清除） |
| POST | `/api/groups/{id}/monitors` | 是 | 监控加入分组，body `{"monitor_id":N}` |
| DELETE | `/api/groups/{id}/monitors/{mid}` | 是 | 监控移出分组 |
| GET | `/api/groups/{id}/monitors` | 是 | 分组成员列表 |
| GET | `/api/groups/{id}/sla?month=YYYY-MM` | 是 | 分组月度 SLA 报告（只统计组内监控） |
| GET | `/api/groups/{id}/sla.html?month=YYYY-MM` | 是 | 分组月度 SLA 报告（中文 HTML，可存档） |
| GET | `/api/groups/{id}/sla/trend?end=YYYY-MM&months=N` | 是 | 分组 SLA 趋势（最近 N 个月逐月聚合，N=1~12，默认 end=当月、months=6，只统计组内监控） |
| GET | `/api/groups/{id}/sla/trend.html?end=YYYY-MM&months=N` | 是 | 分组 SLA 趋势（中文 HTML，含逐月表与可用性条形） |
| GET | `/api/monitors/{id}/sla/trend?end=YYYY-MM&months=N` | 是 | 单监控 SLA 趋势（最近 N 个月逐月聚合，N=1~12，默认 end=当月、months=6，只统计该监控） |
| GET | `/api/monitors/{id}/sla/trend.html?end=YYYY-MM&months=N` | 是 | 单监控 SLA 趋势（中文 HTML，含逐月表与可用性条形） |
| GET | `/api/sla/year?year=YYYY` | 是 | 全站年度 SLA 报告（全年 12 个月聚合，缺省当年，非法年份返回 400） |
| GET | `/api/sla/year.html?year=YYYY` | 是 | 全站年度 SLA 报告（中文 HTML，含逐月表与可用性条形） |
| GET | `/api/groups/{id}/sla/year?year=YYYY` | 是 | 分组年度 SLA 报告（全年 12 个月按分组聚合，缺省当年，非法年份返回 400、不存在的分组返回 404） |
| GET | `/api/groups/{id}/sla/year.html?year=YYYY` | 是 | 分组年度 SLA 报告（中文 HTML，含逐月表与可用性条形） |
| GET | `/api/monitors/{id}/sla/year?year=YYYY` | 是 | 单监控年度 SLA 报告（全年 12 个月按单监控聚合，缺省当年，非法年份返回 400、不存在的监控返回 404） |
| GET | `/api/monitors/{id}/sla/year.html?year=YYYY` | 是 | 单监控年度 SLA 报告（中文 HTML，含逐月表与可用性条形） |
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
│ │ 存储层（DB） │ │ 告警 webhook 持久化队列+worker │ │
│ │ 迁移 / 备份 │ └──────────────────────┘ │        │  └──────┬───────┘                              │
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
