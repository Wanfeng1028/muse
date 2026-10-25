# OpenAgents 第 5 轮：reply_to 引用 + 一层 thread

来源：OpenAgents 清单 6（messaging mod v2.0 的引用回复思想，照设计重实现，非代码搬运；对方是 Python，本轮为 TS 原生 WS 实现）。
协议版本不变（仍为 v1.3）：reply_to / thread_id 均为可选字段，老客户端不带时不受影响。

## 1 语义

- `MessagePayload.reply_to`：被引用消息的 msg_id，可选。
- `MessagePayload.thread_id`：一层 thread 的根消息 msg_id，可选，**由网关派生并覆盖客户端传入值**。
  - 无 reply_to：thread_id = 自身 msg_id（即为根）。
  - 有 reply_to：thread_id = 被引用消息的 thread_id（若有），否则 = reply_to。
  - 回复的回复因此扁平化到根，不做多级嵌套。
- 网关校验：reply_to 在同房间历史里找不到时，不落库、不广播，只给发件人回一条网关消息，文本含 `REPLY_TARGET_NOT_FOUND`。
- Codec 校验：reply_to / thread_id 若出现，必须是非空字符串且不超过 128 字符；reply_to 不得等于自身 msg_id。

## 2 文件清单

| 文件 | 职责 |
|---|---|
| `packages/protocol/src/types.ts` | MessagePayload 新增 reply_to / thread_id |
| `packages/protocol/src/codec.ts` | validateMessagePayload 校验上述规则 |
| `gateway/src/thread.ts` | deriveThreadId / findReplyTarget / targetThreadId / groupThreads（groupThreads 分组逻辑由 BotsRouter GLM-5.3 生成、经本轮人工改编） |
| `gateway/src/hub.ts` | message 落库前派生 thread_id、找不到目标时回错误不落库 |
| `web/src/api.ts` | HistoryMessage.payload 新增 reply_to / thread_id |
| `web/src/components/Chat.tsx` | toChatItem 透传 reply_to / thread_id；待回复态 + 回复条 |
| `web/src/components/MessageList.tsx` | 按 thread_id 分组，根下折叠显示回复（默认折叠），引用行显示发送者 + 前 80 字，找不到被引用消息时显示“引用消息已删除” |
| `web/src/components/Chat.tsx`、`web/src/ws.ts` | 回复按钮 → 待回复态 → sendMessage(text, mentions, replyTo) 发 reply_to |
| `web/src/components/MessageList.tsx` | MessageRow 增加“回复”按钮（经 ThreadGroup 透传） |

## 3 测试

- `packages/protocol/test/codec-thread.test.ts`：5 例（接受、空 reply_to、超长、自引用、超长 thread_id）。
- `gateway/test/thread.test.ts`：5 例（派生、查找、分组、孤回复、不改输入）。
- `gateway/test/thread-hub.test.ts`：2 例（真实 WS：回复派生 thread_id 且回复的回复扁平化到根；找不到目标时回错误且不落库）。
- 网关全量：68 文件 915 例全绿；协议全量：20 文件 185 例全绿；Web：tsc + vite build 通过。

## 4 已知限制

1. 历史查找只查最近 1000 条房间消息；更早的被引用消息会被判为找不到目标（与房间历史分页口径一致，后续轮次可改为按 msg_id 索引查库）。
2. Web 折叠只做一层 thread，不做多级嵌套展示（与网关扁平化语义一致）。
3. 任务帧（intent=task）不走 thread 语义：reply_to 仅在 chat 消息上有展示意义，任务派发仍按原有路由。
