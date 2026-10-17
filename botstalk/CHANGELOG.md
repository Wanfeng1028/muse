# Changelog

## v0.3.0 - 2026-10-17
### 新增
- 协议 v1.2 新增 task_event 帧，网关向房间广播任务状态事件（dispatched/running/done/failed/unsupported/cancelled），携带 assignee/title/note。
- 网关新增 tasks 台账表，派发、回执、无可用 adapter、取消全链路写库。
- 新增 REST 接口 GET /api/tasks，支持 room/status/limit 过滤。
- 新增 REST 接口 GET /api/tasks/stats，返回任务状态统计。
- 新增 REST 接口 GET /api/tasks/:task_id，返回单个任务详情。
- 新增 REST 接口 POST /api/tasks/:task_id/cancel，仅 owner 可取消，终态任务返回 409。
- 新增 REST 接口 GET /api/rooms/:room/unread?since_id=，返回未读计数。
- Web 新增任务追踪面板，支持列表、状态筛选、详情、取消。
- Web Composer 新增派活模式（intent=task，@指定 bot）。
- Web 任务状态通过 task_event 实时刷新。
- Web 在任务面板时收到新消息显示 pill，提示 N 条新消息。
- 新增 Dockerfile 多阶段一体化镜像，网关直出 Web 静态文件（PUBLIC_DIR）。
- 新增 compose.yml，一键启动。
- 新增 docs/OPERATIONS.md 运维手册。
- 新增 .env.example。
- 新增 db 台账单元测试、router 任务钩子测试、REST 集成测试、任务全生命周期 WS 端到端测试。
### 变更
- 协议 v1.2（hello 版本号 "1.2"；旧版客户端会被网关以 4400 拒绝，需同步升级）。

## v0.2.0 - 2026-10-17
- 补发语义收敛、usage 可观测、重启持久化。
- 修 Web 端 gseq 水位 bug，曾用 per-sender seq 当 last_seen_seq。
- presence API 返回全量成员 + usage。
- 新增 /api/usage。
- gseq 与重发队列 SQLite 持久化。
- 测试卫生。

## v0.1.0 - 2026-10-16
- protocol v1.1：原生 WS + 统一 seq/ack 信封 + gseq 网关全局序列号 + 心跳 20s/45s 判离线 + per-adapter FIFO 补发 + seq 单调去重窗口。
- 网关：@提及路由与 task 派发（task 回执广播）、presence 心跳与 usage 随心跳上报、断线重连补发（last_seen_seq=gseq 语义）、artifacts 整份重传（upload_url 5 分钟发起窗口）、历史分页 API 与 Web 分页加载、usage 可观测（/api/usage + 成员面板用量展示）、gseq 与重发队列 SQLite 持久化（网关重启不断补发）。
- adapter：base（AdapterClient：gseq 水位跟踪与磁盘持久化）+ deepseek（brain/body 双模式）+ echo。
- web：Vite + React 18 + 手写 CSS + lucide-react 图标；聊天/成员/用量展示。
