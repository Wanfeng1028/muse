# Changelog

## Unreleased
### 新增
- 审批中心 Web UI（关闭"人工审批 web UI 未做"缺口）：顶栏"审批"按钮（待审批数徽标）+ 右侧抽屉审批队列——待审批项显示标题/派发人→执行者/任务短码/5 分钟倒计时、可选备注、放行/驳回按钮；执行者本人按钮禁用并提示防自批规则；过期显示"已过期，等待网关清扫…"；放行/驳回/过期后收到网关 task_event 自动从队列移除；刷新页面后经 GET /api/rooms/:room/approvals 恢复列表。网关新增该 REST 端点（只返回元数据，不泄露 env 原始帧）+ PendingApprovals.list()。测试：gateway/test/approvals_rest.test.ts 3 例；网关全量 704 例全绿；web/gateway tsc 零错；scripts/smoke-approval.mjs 真实网关 E2E 16/16（挂起→REST→放行→执行者收到原任务帧→驳回→防自批）；2 张真实截图亲眼验收（docs/screenshots/approvals/，console 零错误）。
- 狼人杀纵深测试 r1：werewolf-statemachine.deep.test.ts 27 例（createGame 配置 7/夜晚状态机 11/白天与胜负 9）+ werewolf-ai-vision.deep.test.ts 20 例（AI 决策 10/视角隔离 10），47/47 全绿；修测试侧 4 处误解（announce 阶段 currentSeat 为空、女巫救人后跳过 announce、10 人局 3 狼、放逐后先遗言再入夜），产品无真 bug。
- 狼人杀 E2E 冒烟脚本 scripts/smoke-werewolf.mjs：建 playroom→开 werewolf session（201）→WS hello 1.3 通过/1.2 被 4400 拒绝→game_action start→game_state 广播→状态落库；workroom 开狼人杀 403；12/12。
### 修复
- web/src/ws.ts：PROTOCOL_VERSION '1.2'→'1.3'，与协议层 PROTOCOL_VERSION_STR="1.3" 对齐（否则网关 hello 握手 4400 拒绝）。
- web/src/werewolf/WerewolfResult.tsx：角色/死因 key 改英文（werewolf/villager/seer/witch/hunter/guard），与网关 serializeForSeat 对齐。
- web/src/components/Chat.tsx：game_state 帧解包网关 {v, state} 会话包取内层 state。

## v0.4.1 - 2026-10-18
### 新增
- 测试纵深 r3（斗地主）：牌型判定纵深 21 例（连对/飞机带翅/四带二边界）、canBeat 压牌纵深 23 例、叫分状态机纵深 13 例、AI 自由领出 12 例、AI 压牌策略 12 例。
- 测试纵深 r3（网关）：rooms-router 未覆盖分支 8 例（未知 intent 静默丢弃、回执 task 不存在仍广播、候选能力过滤、定向不看 room、routeStream 落库内容）、artifacts 7 例（invalid_request 非法 body、handle 非 artifact 路径返回 false、mime 空串）、db gateway_state 8 例、pending_frames 8 例、Hub.getOnlineAdapters(room) 6 例、静态文件服务 serveStatic 8 例、loadConfig 10 例。
- 测试纵深 r3（protocol）：ResendQueue.getMissingBySeq 8 例、SeqTracker 未覆盖分支 8 例、StreamTracker 未覆盖分支 7 例、codec parse/validate 未覆盖分支 10 例、GapRateLimiter 边界 6 例。
- docs/DECISIONS.md 新增决策"2026-10-18：presence/usage 端点按网关全局返回"：presence 是网关全局概念，adapter 心跳不归属某个 room；GET /api/rooms/:room/presence 与 /usage 取 listPresence 全量，不按 room 过滤。
### 变更
- gateway/test/presence-usage.r2.test.ts：3 处"行为待确认：未按 room 过滤"注释转为语义锁定用例（引用 DECISIONS 条目），测试行为不变。
- 本轮无源码行为变更，仅测试与文档。

## v0.4.0 - 2026-10-17
### 新增
- 房间类型：workroom（工作坊）/ playroom（娱乐厅），协议层 packages/protocol/src/rooms-types.ts（类型、权限矩阵、路由策略、游戏清单）。
- 网关 DB 新增 rooms / room_members / game_sessions 三表（老库自动建表），房间不存在时按 workroom 兼容。
- 网关配置新增 ROOM_MAX_MEMBERS_WORKROOM（默认 50）、ROOM_MAX_MEMBERS_PLAYROOM（默认 200）、GAME_BROADCAST_THROTTLE_MS（默认 500），非法值启动 fail-fast。
- 路由语义：workroom 聊天 @定向（只派发给被@者与发送者，禁止抢话）；playroom 聊天广播（允许抢话）；playroom 内新 task 意图直接拒绝并回 ROOM_TYPE_FORBIDDEN。
- REST：POST /api/rooms、GET /api/rooms、GET/PATCH /api/rooms/:room（含改类型权限：workroom 仅房主，playroom 所有成员）、成员增删改查（超上限 403 ROOM_FULL）、小游戏会话 CRUD（按房间类型强制游戏清单，不过滤 403 ROOM_TYPE_FORBIDDEN）。
- Web：房间列表（含工作坊/娱乐厅徽标、建房）、聊天头房间名 + 类型徽标、房间设置（改类型）。
- 测试：protocol rooms-types 35 例；gateway 新增 rooms-db（26）、rooms-router（7）、rooms-server（5）三套；网关全量 14 文件 104 用例全绿；另修复 3 处既有测试类型错误（config 新字段、.ts 后缀 import、"pending" 非法 TaskStatus）。
### 变更
- GatewayConfig 新增三个必填字段；既有测试调用点已同步。
- PATCH /api/rooms/:room/games/:id 的 state 同时接受 string 与 JSON 对象（对象自动序列化）。
- 协议 v1.3（hello 版本号 "1.3"；v1.2 客户端连 v1.3 网关会被 4400 拒绝，需同步升级；客户端可据版本号判断服务端是否支持房间类型）。
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
