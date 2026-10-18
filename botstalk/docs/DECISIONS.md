# BotsTalk 决策记录

## 2026-10-15：DeepSeek 本体路线验证结论：可行

### 验证过程

在 2026-10-15 对 DeepSeek 本体路线（`dsh` CLI）进行了实测验证。

**安装验证**

执行 `npx -y @deepseek-ai/dsh --version`，输出 `0.2.0-rc.2`，安装成功。

**能力探查**

`dsh headless --help` 显示该子命令支持以下与 adapter 集成相关的参数：

- `--json`：以 NDJSON 形式输出 run events，适合被 adapter 逐行消费。
- `--session-id`：支持续接已有 session，具备会话保持能力。

**鉴权行为验证（无 key）**

在未提供 API key 的环境下执行，报错信息为：

```
MISSING_CREDENTIAL: llm-deepseek: no API key... export DEEPSEEK_API_KEY
```

说明 `dsh` 明确要求 `DEEPSEEK_API_KEY` 环境变量，缺失时不会静默降级。

**链路验证（假 key）**

使用假 key 执行 `dsh headless --json "say hi"`，依次输出：

```json
{"type":"session",...}
{"type":"status","phase":"turn_start"}
{"type":"status","phase":"step_start"}
{"type":"final","text":""}
```

进程 exit 0。事件序列完整，链路打通；`final.text` 为空是鉴权失败的表现，属预期行为，只差真实 key 即可跑通真实推理。

**社区插件考察**

`ds-bot` 0.1.5 社区插件可安装（需 pnpm），但其定位为交互式 UI 插件，adapter 集成不需要它，故不纳入依赖。

### 结论

DeepSeek 本体路线**可行**。adapter 采用 brain/body 双模式设计：

- **chat intent** → 走 DeepSeek 官方 API 直连，对应**脑力层**（brain），仅做对话生成，无执行能力。
- **task intent** → 走 `dsh headless --json`，对应**本体层**（body），具备执行能力（有手）。
- 模式切换由 `DEEPSEEK_BODY` 环境变量控制。
- **无 key 时**：如实返回 `task_status: failed`，reason 为 `upstream_error`，不伪造成功。

### 能力边界

- `[deepseek:brain]`：纯模型 API，无执行能力。
- `[deepseek:body]`：DSH 本体，可执行任务（需 `DEEPSEEK_API_KEY`）。
- 无 key 时：所有请求回 `task_status: failed`，reason 为 `upstream_error`，不伪造成功。

## 2026-10-15：联调发现的网关 bug（已修复）

网关联调过程中发现以下三处 bug，均已修复：

1. **task 回执被误当新 task 路由**
   router 把带 `task_status` 的 task 回执又当成新 task 进行路由，导致未广播。修复方式：当 `task_status` 已设置时，走广播路径，不再重新路由为新 task。

2. **resendQueue 生命周期错误**
   原实现中 resendQueue 是 per-connection 的，连接断开即丢失待补发帧。修复方式：改为 Hub 级 `Map`，按 `adapter_id` 持久化，连接重建后可继续补发。

3. **btrfs 上 SQLite WAL 导致网关进程 D 状态卡死**
   在 btrfs 文件系统上，SQLite 的 WAL 模式会使网关进程进入 D 状态（不可中断睡眠）卡死。经定位为环境问题而非代码 bug，e2e 测试改用 `/dev/shm` 规避。

## 2026-10-15：e2e 联调结果

e2e 联调共 6 项，**5/6 通过**。

**通过项（5 项）**

- 普通消息
- @定向消息
- task 派发
- presence
- artifact 上传

**未通过项（1 项）**

- 断线重连补发

**原因**

`last_seen_seq` 与 per-sender seq 的语义不匹配：当前 `last_seen_seq` 的语义无法正确表达 per-sender 序列的补发起点，导致重连后补发范围计算错误。

**后续计划**

需在协议 v1.1 中重新设计 `last_seen_seq` 与 per-sender seq 的对应关系，明确补发语义后再实现并回归此项。

## 2026-10-16：protocol v1.1 落地，e2e 6/6 通过

**v1.1 设计（已实现）**

- `Envelope` 新增可选 `gseq`：网关全局序列号，网关发往客户端的所有帧单调递增打戳（`Hub.stampOutbound`，幂等，broadcast 多收件人共用同一 gseq）；客户端发往网关的帧不带。
- `PROTOCOL_VERSION_STR` 1.0 → 1.1；`HelloPayload.last_seen_seq` 重定义为"客户端已见最大 gseq"。
- `ResendQueue.getMissing` 按 `gseq` 过滤；新增 `getMissingBySeq` 供客户端 gap 响应（客户端重发队列是自发帧、无 gseq，按 per-sender seq 查）。
- `AdapterClient` 跟踪 `maxGseq`（收到带 gseq 的新帧推进），重连 hello 携带真实水位。
- 已知边界：`globalSeq` 与 resendQueues 均为内存态，网关重启后 gseq 从 1 开始、队列丢失（v1.1 不修）。

**自激风暴根因与修复（实测）**

- echo 适配器：`onMessage` 透传 mentions 自循环；`onTask` 对 task 回执（含自己发的）无限响应。修复：sender 自检 + 仅 chat intent + 回复 strip mentions；onTask 忽略带 task_status 的回执。
- deepseek 适配器：`onTask` 同样无守卫，自己发的 "task accepted" 广播回来触发自己，无限风暴。修复：同款 sender 自检 + task_status 拦截。
- 风暴曾打满网关事件循环（HTTP 被饿死）并塞满重发队列，是用例5/6 失败的直接原因。

**e2e 结果（2026-10-16 实测，`scripts/e2e-round2.mjs`）**

6/6 全部通过：普通消息、@定向、task 派发、心跳 presence、artifact 上传、断线重连补发。

**单元测试**

- protocol 38/38、gateway 22/22、adapter-base 7/7、echo 5/5、deepseek 5/5，共 77 全绿。

## 2026-10-17：v0.2 补发语义收敛 + usage 可观测 + 重启持久化

### Web 端 gseq 水位修复

web/src/ws.ts 之前把 per-sender seq 当成 `last_seen_seq` 上报，跟 v1.1 定义的“客户端已见最大 gseq”对不上，重连后补发范围算错，跟 2026-10-15 那次失败一个毛病。现在改成跟踪收到的 `frame.gseq`，取最大值存为 `maxGseq`，重连 hello 时携带它。如果新收到的 gseq 比当前水位小（说明网关重启过、gseq 从 1 重新开始），就把水位重置，跟 adapters/base 里的处理保持一致。

### usage 可观测

先把语义定清楚：presence 心跳里带的 usage 是 adapter 侧自己累计的数值，网关收到后直接覆盖写入 presence 表，不做差分累加，避免重复心跳把数字越加越大。新增 `GET /api/rooms/:room/usage`，返回该房间下每个 adapter 的累计用量以及房间总计。presence 端点改成返回全量成员（含离线的），每条带 `usage_in` / `usage_out`。Web 成员面板上把用量展示出来。

### gseq 与重发队列 SQLite 持久化

这条是补 2026-10-16 里记的已知边界：`globalSeq` 和 resendQueues 都是内存态，网关一重启就没了。现在新增 `gateway_state` 表存 `global_seq`，Hub 构造时读回来恢复，`stampOutbound` 每次打戳后写透。新增 `pending_frames` 表存重发帧，`sendTo` 入队时写透，`getResendQueue` 第一次建队时从表里恢复，队列超过 `RESEND_MAX_MSGS` 时裁掉最老的。

### 测试卫生

test/hub.test.ts 里用 `process.cwd()` 建临时目录，跑测试时会在 gateway/ 下留下一堆 `test-tmp-*` 目录。改成用 `tmpdir()`，跑完不再堆在仓库里。之前残留的 8 个目录已经删掉了。

## 2026-10-18：A2345 顺子口径决策（斗地主）

**决策**：A 不可作为 1 回绕，A2345 / A23456 均为非法牌型。引擎现行行为（判 invalid）正确，保持不变。

**依据**（2026-10-18 经 Keenable 核验）：
- gameabc.com《斗地主顺子可以打A23456吗？》明确指出 A23456 不是顺子、不能打；顺子最小 3、最大 A。
- 同城游斗地主：顺子最大牌型为 10JQKA，不可带 2，最大点数为 A。
- 腾讯欢乐斗地主官方规则：顺子是"点数相连的牌，2 和王不能出现在顺子中"，牌序 3..A，A 为端点不回绕。

**影响**：
- `gateway/src/doudizhu/cards.ts` 中 `tryStraight` 注释已写明该口径。
- `gateway/test/doudizhu-cards.deep.test.ts` 用例锁定 A2345 为 invalid。

## 2026-10-18：presence/usage 端点按网关全局返回（presence 是网关全局概念）

**决策**：
- `GET /api/rooms/:room/presence` 与 `GET /api/rooms/:room/usage` 取 `listPresence` 全量，不按 room 过滤。
- 端点保持返回全量排序 presence。
- presence 是网关全局概念，adapter 心跳不归属某个 room。

**理由（依据）**：
- presence 表没有 room 字段，见 `db.ts` 签名：`upsertPresence` 只收 `adapter_id`/`status`/`last_seen_ms`/`usage_in`/`usage_out`。
- adapter 的 presence 心跳是网关级存活信号，不归属某个 room。
- `listPresence` 本来就返回全表，签名逐字为 `export function listPresence(db: Db): PresenceRow[] {`。
- 服务端用 `sortPresence` 排序（online 排前、同状态按 `adapter_id` 字典序），逐字为：
  `function sortPresence<T extends { adapter_id: string; status: string }>(rows: T[]): T[] {`
  `  return [...rows].sort((a, b) => {`
  `    const aOnline = a.status === "online" ? 0 : 1;`
  `    const bOnline = b.status === "online" ? 0 : 1;`
  `    if (aOnline !== bOnline) return aOnline - bOnline;`
  `    return a.adapter_id < b.adapter_id ? -1 : a.adapter_id > b.adapter_id ? 1 : 0;`
  `  });`
  `}`
- URL 里的 `:room` 段保留只为路由对称，不参与过滤。
- 单条读取走 `getPresence`，签名逐字为 `export function getPresence(db: Db, adapter_id: string): PresenceRow | undefined {`。

**影响**：
- `gateway/test/presence-usage.r2.test.ts` 中 3 处"行为待确认"注释转为语义锁定用例，行为不变。