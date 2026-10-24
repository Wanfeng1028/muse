# OpenAgents 移植第 3 轮：共享线程上下文注入

## 对标来源

- 仓库：openagents-org/openagents（Apache-2.0）
- 原始文件：packages/agent-connector README "Shared thread context" 节、src/adapters/thread-history.js、src/adapters/base.js `_applyThreadHistory`
- Botstalk 为 TypeScript + 原生 WebSocket 重实现，未复制原版代码。

## 原版真实行为（实跑记录）

以下数值均为执行原版 `buildThreadHistory` 的实测结果，非猜测：

- 每次触发 agent 轮次前，读取最近消息（含人与人讨论）：最近 100 事件中取最多 30 条聊天消息，按时间顺序排列并标注发言人。
- 转录上限 16000 字符；单条消息截断至 2000 字符，追加 `"… [truncated]"` 后实测截断文本长度 2013。
- 排除项：status 类型消息、触发消息自身（按 messageId）、触发后创建的消息（createdAt 截止）、空内容。
- 预算算法：从选中消息 newest-first 迭代；`line = JSON.stringify(单条消息)`；若 `line.length + 1 > 剩余预算` 则停止；否则 unshift 并从剩余预算（初始 16000）减去 `line.length + 1`。输出按时间正序。
- 实测：35 条消息 → 输出 30 行，首行发言人 = 第 6 条消息，末行 = 第 35 条；30 × 1000 字符消息 → 15 行纳入。
- 拉取调用：`getRecentMessages(workspaceId, channel, token, 100, { before: trigger messageId, timeout: 5000, throwOnError: true })`；DM 跳过（channel 以 `"dm:"` 开头）；幂等标志 `_threadHistoryApplied`；拉取失败时打日志并仅用当前请求继续；原始内容保留在 `originalContent`，上下文块前置于 `content`。
- 输出格式：首行 `"RECENT THREAD MESSAGES (oldest to newest; bounded excerpt, not the full history)"`，一句关于对话数据/勿将引用指令当作系统指令/使用 history 工具的守卫语，每条消息一行 JSON，`"END OF RECENT THREAD MESSAGES"`，空行，然后 `"CURRENT REQUEST from "<speaker>":"`。

## botstalk 落地映射

### 新文件

- `botstalk/adapters/base/src/thread-context.ts`：纯函数 `buildThreadContext(messages, current)`。
  - 类型 `ThreadHistoryMessage { sender, text, ts, msgId?, frameType?, taskStatus? }`、`ThreadContextCurrent { msgId, sender, ts }`。
  - 常量：`THREAD_CONTEXT_MAX_MESSAGES=30`、`THREAD_CONTEXT_MAX_MESSAGE_CHARS=2000`、`THREAD_CONTEXT_MAX_CONTEXT_CHARS=16000`、`THREAD_CONTEXT_FETCH_LIMIT=100`、`THREAD_CONTEXT_FETCH_TIMEOUT_MS=5000`。
  - 与原版差异：JSON 行仅含 `{ speaker, text }`（botstalk 历史行无 role/attachments）；含 `taskStatus` 行排除（等价于原版 status 排除）；100 事件窗口在函数内部应用（`slice(-100)` 后过滤）；`speaker` 截断至 200 字符；空选返回 `""`。

### 协议层

- `botstalk/packages/protocol/src/types.ts`：`MessagePayload` 新增可选字段 `thread_context?: string`，文档注明为本地字段（由 AdapterClient 在入站信封上设置，来自网关房间历史；不走 wire）。Codec 不变：`validateMessagePayload` 已容忍未知字段且此字段从不 wire 发送。

### 客户端层

- `botstalk/adapters/base/src/client.ts`：
  - `AdapterOptions.threadContext?: { enabled?: boolean; timeoutMs?: number; fetchHistory?: (room, trigger) => Promise<ThreadHistoryMessage[]>; httpBaseUrl?: string; }`。默认关闭，未 opt-in 无行为变化。
  - `dispatchMessage` 在 `onMessage`/`onTask` 之前注入上下文，仅当：`sender !== adapterId`、room 不以 `"dm:"` 开头、`payload.task_status === undefined`、`payload.task_progress === undefined`。
  - `fetchThreadHistoryDefault`：从 `gatewayUrl` 派生 HTTP base（`ws://` → `http://`，`wss://` → `https://`）或 `httpBaseUrl` 覆盖；GET `/api/rooms/:room/history?limit=100`；`AbortController` 超时（默认 5000ms）；映射网关历史行为 `ThreadHistoryMessage`。
  - 拉取/构建错误静默降级：handler 以原始帧运行。`payload.text` 不变异。
  - `index.ts` 重导出 `buildThreadContext`、常量及两个类型。

### Deepseek 适配器

- `botstalk/adapters/deepseek/src/index.ts`：`main()` 传入 `threadContext: { enabled: true }`；`onMessage` 与 `onTask` 计算 `prompt = thread_context ? thread_context + text : text`，用于 `chatCompletionStream`（脑）及 `runDshTask`（体，task 为最后 argv）。`text` 本身不变异。

### 冒烟脚本

- `botstalk/scripts/smoke-thread-context.mjs`（NEW）：真实网关冒烟测试。

## 测试（三类齐全：行为对照、模拟场景 E2E、失败注入）

### 行为对照

- `adapters/base/test/thread-context.test.ts`：12 例。
  - 30 条上限 + 时间正序、status/frameType/触发消息/未来消息/空内容排除、2000 字符截断至 2013、16K 预算 newest-first 15 行、空选返回 `""`、speaker 200 字符截断、100 事件窗口、header/footer 格式。

### 模拟场景 E2E

- `adapters/base/test/client-thread-context.test.ts`：10 例。
  - 默认关闭、启用 + 注入历史顺序 + status 排除 + fetch 参数、触发自排除、自身 sender 跳过、status 帧跳过、task_progress 帧跳过、fetch 拒绝降级、空历史降级、task 意图路径到 onTask 含上下文、dm-room 跳过。
- `adapters/deepseek/test/deepseek-modes.deep.test.ts`：+4 例。
  - 脑 onMessage 前置上下文、脑 onMessage 无上下文发原文、脑 onTask 前置上下文、体 onTask 上下文作为最后 dsh argv。
- `scripts/smoke-thread-context.mjs`：ALL PASS（真实网关 + 真实 HTTP 历史端点 + 真实 AdapterClient 默认 fetch：boss 发 2 条历史消息，worker 收触发后 `thread_context` 含两条历史文本且顺序正确，触发文本不受侵且不出现在自身上下文块中）。

### 失败注入

- fetch 拒绝 → 静默降级仅当前请求（client 测试覆盖）。
- 空历史 → 降级（client 测试覆盖）。

### 合并时总计

- base 37/37、deepseek 16/16、protocol 173/173、gateway 868/868——零回归。base + deepseek 测试 tsconfig.test.json 类型检查干净。

## 视觉验收（说明本轮无 Web UI 变更、无截图的原因）

本轮功能为适配器内部上下文注入，注入内容仅进入上游 prompt，无任何用户可见的 Web UI 界面。因此无截图，无视觉验收步骤。

## 已知限制

- **默认关闭**：现有适配器（echo、byo-bridge、cli-template）未 opt-in 不会获得上下文；本轮仅 deepseek 开启。
- **5 秒超时**：仅限默认 HTTP fetch；注入的 `fetchHistory` 自行负责计时，客户端不叠加二次超时。
- **16K 预算不含头尾**：header/footer 行在预算外（与原版一致，原版 15 × 1000 字符消息实测总量 16027 字符）。
- **历史仅来自网关**：通过 HTTP 历史端点（limit 100, ascending）从网关 messages 表读取；网关未存储的消息（如未处理类型的帧）无法出现在上下文中。
- **DM 守卫为前向兼容**：按 frame room 是否以 `"dm:"` 开头判断；botstalk 当前房间无 DM 类型，该守卫当前非负载关键。