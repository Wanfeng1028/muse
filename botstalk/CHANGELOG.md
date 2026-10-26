# Changelog

## Unreleased - OpenAgents 第 10 轮（只读分享链接）

### 新增

- 只读分享链接（清单第 12 项“邀请链接 + 免安装只读查看”）：Workspace 可签发邀请链接，查看方免安装、浏览器打开即只读围观。
- 网关：share.ts + db.ts share_links 表（含 5 个函数）+ server.ts 4 个端点（签发/列表/吊销/只读查看）。
- 令牌 32 位字母数字，库中只存 sha256 哈希，明文仅签发响应返回一次；有效期默认 168 小时、钳制 1–720 小时。
- 签发与吊销仅限房主/管理员（canManageRoom）；查看端点只读：不写库、不加成员、不发广播。
- 错误码：INVALID_SHARE_TOKEN 400 / SHARE_LINK_NOT_FOUND 404 / SHARE_LINK_REVOKED 410 / SHARE_LINK_EXPIRED 410。
- Web：components/ShareView.tsx + api.ts fetchShareView + App.tsx #/share/<token> 分支。

### 验收

- share.test.ts 20/20；网关全量 73 文件 962 例全绿；网关源码 tsc 全洁；Web tsc -b 与 vite build 通过。
- 真实网关冒烟：建房 201、签发 201、WS 发 2 条消息、GET /api/share 200 且 messages 2 条。
- 截图 docs/screenshots/share-view.png 亲眼验收：房间名/话题/只读横条/2 条消息，无输入框，控制台零错误。
- 修复验收抓出的真 bug：snake_case 行直传驼峰判定致 410（服务端映射 ShareLinkRecord）、B4 编造签名、searchParams 误用、RoomRow 误传 getRoomHistory、B2 漏建表 DDL；截图 harness 以 setContent + replaceState 写 hash 解决。
- 已知局限：链接只读、不能入群/发消息（有意为之）；Web 签发/管理 UI 未做（仅 REST）；查看页不实时刷新；test tsc 既存错误（未动文件）不影响 vitest 全绿。

## Unreleased - OpenAgents 第 9 轮（配对码入驻，后端 + 设备侧兑码客户端）
### 新增
- 配对码入驻（抄清单 9 第一期）：网关 gateway/src/pairing.ts（XXXX-XXXX 码生成/归一化/哈希/TTL 钳制）+ pairing_codes 表与 issue/get/redeem 存取；POST /api/rooms/:room/pairing-codes（房主/管理员签发，默认 10 分钟、钳制 1–60 分钟，码只在响应返回一次、库里只存哈希）与 POST /api/pairing-codes/redeem（格式非法 400、未知码 404、已兑 409、过期 410；兑码成功即入房成员）；byo-bridge 新增 pairing.ts 兑码客户端（PairingError 原样透传服务端错误码）。
### 验收
- 网关新测 pairing.test.ts 19/19、byo-bridge 新测 pairing.test.ts 5/5、网关与 byo-bridge tsc 全洁；真实网关冒烟 scripts/smoke-pairing.mjs 9/9（SMOKE_PAIRING_PASS）；验收修冒烟脚本真 bug 1 个（process.exit 跳过 finally 致网关孤儿，改为 exit 前显式清理）。
- 已知保留：码为房间级单次码，设备信任二期（稳定 device key、多工作区配对表、连接令牌签发）未做；REST requester 仍自报身份无鉴权；Web 发码/兑码 UI 未做；只读分享链接（抄清单 12）未做。详见 docs/OPENAGENTS_ROUND9.md。

## Unreleased - Web 聊天室 AirBuild 版（前端，布局与风格照 AirBuild，模块与角色用自己的）
### 新增
- 新增 `web/src/design-airbuild.css` 覆盖层（原 `styles.css`、`design-v1.css`、`design-v2.css` 不动，`main.tsx` 在三者之后引用本层）：布局照 AirBuild——中间聊天列、右侧成员列、底部模块条；风格为浅底卡片聊天室风（底色 #f6f6f7、白色卡片、1px #e8e8ec 边线、12px 圆角、扁平无渐变无阴影），不再用“值班室台账”风作该聊天室主风格。内容来源：BotsRouter 大写 GLM-5.3，6 通各 3 条规则；编排时按真实布局过滤，剔掉 .chat 圆角、.chat-body 内边距与滚动、.msg-self 的 margin-left:auto、.member-dot 的实色背景（会让离线也变绿）。
- 底部模块条（`Chat.tsx` 内新增 `<nav class="module-bar">`，复用顶栏同一批开关处理器）：任务、审批（含待审批数）、工作流、娱乐厅、斗地主、狼人杀，全部是 BotsTalk 已有真实功能与自己的名字，不含 AirFeedback/AirPayment/AirRouter/AirKnowledge/AirTraffic。
- 右侧角色卡（`Members.tsx`）：只渲染网关 presence 的真实成员，不硬编人名；头像色只由 adapter_id 字符和取模派生（同一成员每次同一色）；职责只分两档——老板“派活、验收、拍板”，Agent“接活、交接”；在线状态取 presence 的 status。验收中发现并修了两处：在线圆点曾被换行挤到卡片左下角（改为名字+职责包一层，圆点回第一行右侧）、Agent 职责行曾被挤成孤字（改短为“接活、交接”）。
### 验收
- Web `tsc -b && vite build` 通过，构建产物 CSS 含本层规则（`.module-bar`、`.member-role` 实证）；真实网关（8765 端口、隔离库）+ REST 新建 `lobby` 工作坊 + seed-demo 6 任务 4 消息 + presence 种子（deepseek 在线、echo 离线），截图亲眼核对（`docs/screenshots/botstalk-airbuild-chat.png`）：浅底聊天列与白色消息卡、右侧三张成员卡（deepseek 在线带用量、老板、echo 离线）与职责行、底部六个自有模块按钮、控制台零错误、页面文本不含 Ato/Pluto/Coin/Camo 与 Air 模块名；计算样式实证：聊天底 #f6f6f7、顶栏与模块条白底、消息卡与成员卡 12px 圆角、头像圆。
- 已知保留：成员栏宽仍为原 240px（本轮未改布局宽度）；deepseek 的用量行在窄栏里仍按原有省略规则截断（既存行为）；本轮不动网关后端、协议、adapter，OpenAgents 第 9/10 轮未动。
- 验收用网关已停，隔离库与提示词/模型原文在 `relay-station/botstalk-airbuild/`，未入提交。

## Unreleased - OpenAgents 第 8 轮（拉人守卫 + 设权限角色端点，后端）
### 新增
- 拉人守卫：POST 成员接 canManageRoom（guest 否决、workroom 仅房主、playroom 非 guest 成员放行，错误 ROOM_MANAGE_FORBIDDEN；先鉴权后校验）。
- 设权限角色端点：PATCH /api/rooms/:room/members/:adapter_id/perm（仅房主可设、房主本人不可改、非法角色 400 INVALID_PERM_ROLE、非成员 404、不借此端点拉人，成功回成员对象）。
### 验收
- 网关新测 management-matrix-r8 2 例；网关全量 71 文件 923 例零回归（此前为 70 / 921，增量恰为本轮 1 文件 2 例）；网关 tsc 全洁；协议本轮未改。
- 已知保留：REST requester 仍为自报身份、无鉴权；无房主房间无人可设权限；其余四级可见性与 Web 悄悄话 UI 仍未做。详见 docs/OPENAGENTS_ROUND8.md。

## Unreleased - OpenAgents 第 7 轮（管理操作矩阵，后端）
### 新增
- 管理操作矩阵落地（关闭第 6 轮未做项“guest 管理操作未做权限矩阵”）：协议新增 canManageRoom（guest 一律否决，其余走既有 canUpdateRoom）；网关 DELETE 成员守既有 canClearOrKick（仅房主，身份取 `?requester=`）、PATCH 成员人设与 PATCH 房间名/话题守 canManageRoom（错误 ROOM_MANAGE_FORBIDDEN）、PATCH 房间类型加 guest 否决（错误仍为既有 ROOM_TYPE_FORBIDDEN）；身份解析为房主恒 admin、其余查 perm_role 列。
- 修复改人设 handler 只判房间存在、未绑定 room 变量的既有隐患（本轮守卫依赖该变量，不修无法编译）。
### 验收
- 协议新测 management-matrix 3 例、网关新测 management-matrix-r7 2 例；协议全量 22 文件 198 例、网关全量 70 文件 921 例零回归；网关 tsc 全洁（协议改后须先构建 dist，否则网关报 canManageRoom 未导出）。
- 已知保留：拉人（POST 成员）尚未守 canInvite；设权限角色无 REST 端点；REST requester 为自报身份、无鉴权；无房主 workroom 将无人能管理；其余四级可见性与 Web 悄悄话 UI 仍未做。详见 docs/OPENAGENTS_ROUND7.md。

## Unreleased - Web 房间列表全宽台账（设计层 v2）
### 新增
- 新增 `web/src/design-v2.css` 覆盖层（原 `styles.css` 与 `design-v1.css` 不动，`main.tsx` 在 v1 之后引用本层）：关闭 v1 已知保留“房间列表页仍为居中卡片”。列表容器取消居中、面板取消卡片边框与最大宽，房间行只靠 1px 底线分隔，页头用 2px 墨线收束；沿用既有纸色 token，不引入新配色；不用渐变、不用阴影、不用新字体、不用 emoji；不改任何 TSX。
### 验收
- Web `tsc -b && vite build` 通过，构建产物 CSS 中 v2 规则压在旧规则之后（`max-width:none`、`display:block` 实证）；真实网关（8765 端口、隔离库）+ REST 新建 2 个真实房间（大厅 workroom、娱乐厅 playroom），截图亲眼核对（`docs/screenshots/botstalk-v2-rooms.png`）：页头 2px 墨线、两行全宽台账行、徽标右对齐、控制台零错误；计算样式实证：列表 display block、面板 max-width none / 无边框 / 透明底 / 内边距 0、行下边框 1px solid #E3DCD0、页头下边框 2px solid #1C1B1A。验收用网关已停，隔离库未入提交；截图下方空白属只有 2 个房间的数据量。
- 已知保留：房间行悬停仍走 v1 的纸面白底（本轮未动悬停态）。


## Unreleased - Web 聊天室设计层 v1（值班室台账）
### 新增
- 新增 `web/src/design-v1.css` 覆盖层（原 `styles.css` 不动，`main.tsx` 在主样式后引用本层）：视觉逻辑为值班室台账——房间是台账本，消息是一行行记录，成员是值班名单，任务是盖戳的条子；全部左对齐，层级只靠字重、字号、线宽三档；沿用既有纸色 token（纸面、墨色、赭石点睛），不引入新配色。
- 顶栏底边 2px 墨线；消息列上限 780px、行间细线分隔、自己消息赭石左缘 3px；成员栏沉底色、表头 2px 线；输入区顶边 2px 线、焦点环 2px 赭石；房间行与任务行均为台账行、未读 pill 赭石底白字；引用块 3px 线 + 沉底色。
- 去 AI 味自查：无渐变、无阴影、无 Inter、无 emoji、无居中英雄区、无圆角胶囊按钮；不改布局宽度、不改任何 HTML/JS。
### 验收
- Web `tsc -b && vite build` 通过（CSS 已打进产物）；真实网关（8765 端口、隔离库）+ `seed-demo.mjs` 种子数据（6 任务、4 消息）+ 新建 `lobby` 房间，截图亲眼核对两张（`docs/screenshots/botstalk-v1-rooms.png`、`botstalk-v1-chat.png`）：房间行真实可见、聊天消息与成员在线态真实渲染、顶栏墨线与自己消息左缘实证可见、控制台零错误；验收用网关已停，隔离库未入提交。
- 已知保留：种子消息只有 4 条，聊天区下方为空白（属数据量，非样式问题）；echo/deepseek 未连接，成员栏只显示在线的老板（属真实在线态）；房间列表页仍为居中卡片（既存布局，本层按规则不改布局宽度）。
- 本轮另有网关核心大上下文评审 3 通未出可用正文（见进度文件），架构评审文档未入仓，排期后续。

## Unreleased - OpenAgents 第 6 轮（帧级可见性 + 房间角色组）
### 新增
- 信封新增可选 visibility（direct/restricted）与 visible_to（v1.3 兼容，缺省行为不变）；makeEnvelope 加 extra 参数；validateEnvelope 入口校验（direct 恰好 1 项、restricted 至少 1 项、单项 ≤64 字符、重复报错）。
- 网关 broadcast 与 workroom 定向分支按可见集合过滤；direct/restricted 消息只发在线、不落共享历史（history 接口无请求者身份，落库即泄漏）。
- room_members 加 perm_role 列（新库建表 + 老库 ALTER 迁移）；setPermRole/getPermRole（非法值按 member 计）；房间 owner 恒为 admin；guest 发任务被拒绝（PERMISSION_DENIED，task_status=unsupported），聊天不受影响。
- 测试：协议 visibility 10 例、网关 visibility-hub 真实 WS 4 例；网关全量 69 文件 919 例、协议全量 21 文件 195 例全绿。
- 文档：docs/OPENAGENTS_ROUND6.md（含未做清单：其余四级可见性、管理操作矩阵、Web 发送 UI 均未做）。

## Unreleased - OpenAgents 第 5 轮（reply_to + 一层 thread）
### 新增
- 协议 MessagePayload 新增可选 reply_to / thread_id（v1.3 兼容，老客户端不受影响）；网关派生 thread_id，回复的回复扁平化到根。
- 网关找不到被引用消息时回 REPLY_TARGET_NOT_FOUND 且不落库不广播。
- Web：根消息下折叠显示同 thread 回复（默认折叠），引用行显示发送者 + 前 80 字，消息行增加“回复”按钮，待回复态发出的消息带 reply_to。
- 测试：协议 codec-thread 5 例、网关 thread 5 例、网关 thread-hub 真实 WS 2 例；网关全量 68 文件 915 例、协议全量 20 文件 185 例全绿；Web tsc + vite build 通过。
- 文档：docs/OPENAGENTS_ROUND5.md。


## Unreleased
### 新增
- OpenAgents 移植第 4 轮（抄清单 8 + 7）：清单规范先行 + 能力匹配派单结构化打分版（LLM 兜底后置）。协议 v1.3 兼容新增可选字段：capability_update.capabilities 加 skills/tags、message 加 required_capabilities；网关 capability.ts（归一化 + ALL 布尔匹配 + 权重打分 skills 0.5/tags 0.25/input_modes 0.125/output_modes 0.125、在场维度重归一化、最高分胜出/并列字典序/零分走 unsupported）与 manifest.ts（清单校验 + 文件/目录加载）+ adapters/deepseek/manifest.json 示例；hub 存储 adapter 声明的技能/标签，router 无 @ 时按 required_capabilities 打分派单、@ 指定压过打分；base client sendCapability 可声明 skills/tags；capability-llm.ts 只移植原版 prompt 构建与响应解析、不调用 LLM。测试：capability 24 例、manifest 11 例、协议 codec 7 例、路由 5 例；网关全量 66 文件 908 例、协议 180 例、base 37 例零回归；真实网关冒烟 smoke-capability-matching.mjs 全过。验收抓出 1 个真 bug 已修：@ 指定后仍走打分致零分被提及者走 unsupported，改为 mentions 非空时跳过打分。移植规格见 docs/OPENAGENTS_ROUND4.md。
- OpenAgents 移植第 3 轮（抄清单 3）：共享线程上下文注入——adapters/base 新增 thread-context 模块（近 100 事件取 30 条、16K 上限、单条 2000 截断、5 秒降级）+ AdapterClient threadContext 选项（默认关闭，deepseek 已开启；拉取失败/超时静默降级为仅当前请求）+ 协议 MessagePayload 本地字段 thread_context（不走 wire）；deepseek 脑/体双模式均把上下文拼在当前请求之前发给上游。测试：行为对照 12 例、client 10 例、deepseek 4 例、真实网关冒烟全过；协议 173、网关 868 零回归。移植规格见 docs/OPENAGENTS_ROUND3.md。
- OpenAgents 移植第 2 轮（抄清单 2）：任务进度上报 + 超时状态机。协议补 task_event 的 progress/timed_out 状态与 progress/progress_count 字段、MessagePayload 的 task_progress 上报帧（message 上限 2000 字符）；网关台账加 deadline_ms/error/progress_count 列与 task_progress_reports 明细表（老库自动迁移）；handleTaskProgress（仅 assignee 可报、终端态拒报、dispatched 首报转 running、广播 task_event(progress)）+ sweepTaskTimeouts（15 秒 tick 清扫 dispatched/running 中过期任务，标 timed_out 并向 owner 与 assignee 双方发 TASK_TIMEOUT 通知；默认超时 300 秒，可用 BOTSTALK_TASK_TIMEOUT_MS 配置）；审批门下 deadline 从放行起算；GET /api/tasks/:task_id 返回进度明细；Web 任务面板新增「已超时」状态/筛选/详情（超时期限、失败原因、进度明细列表）与顶栏已超时计数。测试：protocol 14 例、db 13 例、网关行为对照 17 例、E2E 6 例、tasks-api 白名单 2 例；真实网关冒烟 13/13；视觉验收 3 张截图（docs/screenshots/task-progress-timeout/，console 零错误）。验收抓出 2 个真缺陷已修：进度帧缺顶层 task_id 致 hub 4401 断连；服务端 status 白名单漏 timed_out 致筛选 400。移植规格见 docs/OPENAGENTS_ROUND2.md。
- OpenAgents 移植第 1 轮（抄清单 1）：`@botstalk/registry`（22 个 agent 描述符 JSON 原样移植自 openagents-org/openagents（Apache-2.0）+ Registry 类 TS 重实现：featured 按 order 排序/其余按 label 字母序/support 空对象补 DEFAULT_SUPPORT，行为与原版逐项对照测试锁定）+ `@botstalk/cli-template`（CliAdapter 基类：按描述符 spawn CLI 子进程执行任务，`{agent_name}` 模板替换，checkReady/probe/runTask/stopCurrent，进程组杀+SIGNT→SIGKILL 升级，stdout 1MB 截断）+ claude/codex 两个开箱即用 adapter + 网关 `GET /api/registry/agents`（白名单字段）/`/:name`。测试：registry 6/6、cli-template 14/14（含失败注入抓出的真 bug：孙进程占管道致 close 挂起，已修为进程组杀+exit 兜底）、网关全量 826/826 零回归、真实网关冒烟通过。移植规格见 docs/OPENAGENTS_ROUND1.md。
- 审批中心 Web UI（关闭"人工审批 web UI 未做"缺口）：顶栏"审批"按钮（待审批数徽标）+ 右侧抽屉审批队列——待审批项显示标题/派发人→执行者/任务短码/5 分钟倒计时、可选备注、放行/驳回按钮；执行者本人按钮禁用并提示防自批规则；过期显示"已过期，等待网关清扫…"；放行/驳回/过期后收到网关 task_event 自动从队列移除；刷新页面后经 GET /api/rooms/:room/approvals 恢复列表。网关新增该 REST 端点（只返回元数据，不泄露 env 原始帧）+ PendingApprovals.list()。测试：gateway/test/approvals_rest.test.ts 3 例；网关全量 704 例全绿；web/gateway tsc 零错；scripts/smoke-approval.mjs 真实网关 E2E 16/16（挂起→REST→放行→执行者收到原任务帧→驳回→防自批）；2 张真实截图亲眼验收（docs/screenshots/approvals/，console 零错误）。
- 狼人杀纵深测试 r1：werewolf-statemachine.deep.test.ts 27 例（createGame 配置 7/夜晚状态机 11/白天与胜负 9）+ werewolf-ai-vision.deep.test.ts 20 例（AI 决策 10/视角隔离 10），47/47 全绿；修测试侧 4 处误解（announce 阶段 currentSeat 为空、女巫救人后跳过 announce、10 人局 3 狼、放逐后先遗言再入夜），产品无真 bug。
- 狼人杀 E2E 冒烟脚本 scripts/smoke-werewolf.mjs：建 playroom→开 werewolf session（201）→WS hello 1.3 通过/1.2 被 4400 拒绝→game_action start→game_state 广播→状态落库；workroom 开狼人杀 403；12/12。
- 新增「工作流」功能，支持定时任务与触发规则：后端新增 scheduled_tasks/trigger_rules 两表及 CRUD、模板渲染（{text}/{sender}/{room}）、规则匹配、原子领取与冷却，scheduler 每 15 秒 sweep 合成 scheduler 任务帧复用 routeMessage，triggers 在消息入口接入 checkTriggers 并防自触发风暴，server 暴露 10 个 REST 端点；前端新增 Workflows 主抽屉、ScheduleForm/TriggerForm 表单（含 IntervalPicker 与 match_type 分段）、8 个 CRUD 客户端函数及 17 个 wf-* 样式；修复 createTriggerRule 列数错位、node:sqlite Record 位置索引、updateScheduledTask 禁用任务更新静默失败、4 个端点漏 return 等缺陷。新增 4 个测试文件 44 例全绿，网关全量 748/748，web tsc/vite build 零错，smoke-workflows.mjs E2E 全过，3 张截图验收 console 零错误。
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
