# OpenAgents 移植第 2 轮：任务进度上报 + 超时状态机

## 对标来源
OpenAgents task_delegation mod（Apache-2.0；mod 内 manifest 自声明 MIT，botstalk 按 Apache-2.0 口径保留声明）：sdk/src/openagents/mods/coordination/task_delegation/（mod.py、adapter.py、a2a_delegation.py、mod_manifest.json、eventdef.yaml）。botstalk 为 TS + 原生 WS 异构实现，代码不可直搬，按设计重实现；数据格式与语义逐项对照。

## 原版真实行为（实跑记录）
以下行为来自对原版 a2a_delegation.py 的桩驱动实跑（stub openagents.models.a2a 后 import 原文件执行），非凭代码猜测：
- 超时判定 is_task_expired：终端态（completed/failed/canceled/rejected）即使远超期也不过期；无 created_at 不过期；无 delegation 元数据不过期；timeout_seconds 缺失时默认 300；elapsed 严格大于 timeout_seconds 才过期；SUBMITTED 与 WORKING 两态都纳入清扫；默认超时 300 秒，清扫间隔默认 10 秒（timeout_check_interval 可配）。
- 超时处理：completed_at=当前时间、error="Task timed out"、is_timeout=True；A2A 状态置 FAILED；向 delegator 与 assignee 双方各发一条 task.notification.timeout（相同载荷，含 task_id/delegator_id/assignee_id/description）。
- 进度上报 task.report：task_id 必填；任务不存在报错；仅 assignee 可上报（他人报 "Unauthorized: only assignee can report progress"）；任务须为 SUBMITTED/WORKING（否则 "Cannot report progress: task status is X"）；SUBMITTED 任务首次上报自动转 WORKING；上报追加进任务历史并 progress_summary.total_reports 自增；通知 delegator（task.notification.progress）；响应含 progress_count。
- 完成 task.complete：仅 assignee；须 SUBMITTED/WORKING；结果存为 artifact；状态 COMPLETED；通知 delegator；注意原版一个真实 quirks：完成响应的 completed_at 取自更新前的元数据，实际返回 None（fail 处理是更新后取，正确）。botstalk 取 fail 式正确行为（返回更新后的 completed_at）。
- 失败 task.fail：仅 assignee；须 SUBMITTED/WORKING；error 缺省 "Unknown error"；状态 FAILED 并写 error；通知 delegator。
- 委派 task.delegate：timeout_seconds 须为正数，否则 "timeout_seconds must be a positive number"；默认 300；通知 assignee（task.notification.assigned）。
- 列表 task.list：role 默认 delegated_by_me（另 assigned_to_me）；status 数组过滤；limit 默认 20（1~100）；offset 默认 0；按 created_at 倒序；has_more=(offset+limit)<total_count。

## botstalk 落地映射
- 协议（@botstalk/protocol）：task_event 状态新增 "progress" | "timed_out"；TaskEventPayload 新增 progress?: TaskProgress（message + 可选 data）与 progress_count?: number；MessagePayload 新增 task_progress?: { task_id, message, data? }（assignee→网关的上报帧）；TASK_PROGRESS_MESSAGE_MAX=2000；codec 校验：progress 状态时 progress 必填、progress_count 非负整数、非 progress 状态带 progressD报错；task_progress 的 task_id 非空、message 非空且不超 2000。
- 关键约束（冒烟实测发现）：intent=task 帧的顶层 task_id 是 codec 强制字段，hub 对非法帧直接 4401 断连；因此进度帧的顶层 task_id 必填且须与 task_progress.task_id 一致，不一致时网关回 TASK_PROGRESS_REJECTED+拒绝。早期冒烟曾因此丢上报并踢掉 assignee 连接，属真实缺陷已修复。
- 台账（gateway/src/db.ts）：tasks 表新增 deadline_ms（NULL=无超时限制）、error（超时/失败原因）、progress_count（冗余计数）；新增 task_progress_reports 表（task_id, seq, reporter, message, data_json, created_at_ms；seq 按任务自增）；迁移用 PRAGMA 查列后 ALTER（老库幂等）；新增 recordTaskProgress（显式 BEGIN IMMEDIATE 事务：插明细 + 同步 progress_count）、getTaskProgress（seq 升序，limit 默认 100 上限 500）、listExpiredTasks（status IN dispatched/running 且 deadline_ms 严格小于 nowMs，按 deadline 升序）、markTaskTimedOut（仅 dispatched/running 生效，防并发重复标记）。
- 网关逻辑（gateway/src/router.ts）：handleTaskProgress（不存在→TASK_PROGRESS_NOT_FOUND；非 assignee→TASK_PROGRESS_UNAUTHORIZED；终端态→TASK_PROGRESS_REJECTED；dispatched 首次上报转 running；记台账后广播 task_event(progress) 并回 TASK_PROGRESS_OK）；sweepTaskTimeouts（按 listExpiredTasks 清扫，标 timed_out + 写 error="Task timed out" + 广播 task_event(timed_out) + 向 owner 与 assignee 双方发 TASK_TIMEOUT 消息通知）；派发点（直派与审批放行）写 deadline_ms=now+taskTimeoutMs；pending_approval 任务不进超时清扫（由审批 TTL 守，见下）。
- 超时默认值与配置：默认 300000 毫秒（对标原版 300 秒）；环境变量 BOTSTALK_TASK_TIMEOUT_MS（范围 1000~86400000，非法启动 fail-fast）；server 启动时 setTaskTimeoutMs 注入；清扫挂在主循环 15 秒 tick 上（与 sweepApprovals、sweepScheduledTasks 同 tick）。
- 审批门交互：pending_approval 任务的 deadline 从放行时刻起算（放行时 upsertTaskDispatch 重写 deadline），放行前不触发任务超时；审批过期仍走原有审批清扫（状态 cancelled）。
- HTTP：GET /api/tasks/:task_id 返回体新增 progress 数组（seq 升序明细）；GET /api/tasks 的 status 白名单补 pending_approval 与 timed_out（此前漏 timed_out 致面板「已超时」筛选报 400，冒烟截图实锤后修复）。
- Web 任务面板：状态新增 timed_out（文案「已超时」，红色 pill）；筛选器新增「已超时」；详情区新增超时期限（NULL 显示「无超时限制」）、失败原因、进度上报次数与进度明细列表（#seq + message + 时间）；顶栏统计新增已超时计数；timed_out 为终端态，不可取消。

## 测试（三类齐全）
- 行为对照：protocol taskprogress 14 例（progress/timed_out 帧合法性、message 长度边界、progress_count 校验、序列化往返）；db task-timeout-db 13 例（迁移默认值、deadline 刷新、seq 递增、严格小于边界、幂等标记、老库迁移幂等）；网关 task-progress-timeout 17 例（上报成功/转 running/seq 递增/data 可选/非 assignee 拒/不存在/终端态拒/帧 task_id 不一致拒/超时标记/双通知/未过期不扫/终端态不扫/严格边界/掉线仍扫/重复扫幂等/空 message 拒/超时后上报拒）。
- 模拟场景 E2E：gateway/test/task-e2e.test.ts 6 例（派发→进度两轮→完成→超时全链路→超时详情→审批门下 deadline 从放行起算）。
- 失败注入：见行为对照中的掉线/重复/空消息/不一致帧各例；另真实网关冒烟 smoke8765.mjs 13/13（WS 派发→进度×2→HTTP 详情→超时清扫→双方通知）。
- 回归：protocol 173 例、gateway 859+ 例全绿；web tsc/vite build 零错；gateway test tsconfig 仅剩 5 个与本轮无关的 pre-existing 错误（werewolf 测试与 better-sqlite3 类型缺失）。

## 视觉验收
真实网关 + 真实 Web 构建截图（docs/screenshots/task-progress-timeout/）：任务列表「已超时」红 pill；详情区超时期限/失败原因/进度 2 条明细；筛选「已超时」正常出结果；console 零错误。验收中抓出的两个真缺陷均已修复：①进度帧缺顶层 task_id 致 hub 4401 断连；②服务端 status 白名单漏 timed_out 致筛选 400。

## 已知限制
- pending_approval 任务不进任务超时清扫，只受审批 TTL 约束；如审批 TTL 大于任务超时，放行后 deadline 从放行起算，不补算挂起时间。
- 进度上报 message 上限 2000 字符（超长帧 codec 直接拒绝，网关不截断）。
- 清扫粒度为 15 秒 tick，超时实际标记时间在 deadline 后的下一个 tick（最长晚 15 秒），与原版 10 秒 tick 同理。