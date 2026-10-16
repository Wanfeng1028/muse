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

=== END ===
