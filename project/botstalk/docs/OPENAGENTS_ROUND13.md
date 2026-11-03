# OpenAgents 第 13 轮：消息反应 WebSocket 广播

## 原版规格
原版 messaging mod 的 eventdef.yaml 定义 thread.reaction.add（reactionAdd）与 thread.reaction.remove（reactionRemove）两个地址，ReactionMessage 为载体；本轮 TS 映射为协议帧 type=reaction_event，action 字段取 add/remove，sender 固定为 gateway，与 task_event 同款广播语义。

## 改动清单
1. 协议包 types.ts：FrameType 加 reaction_event，新增 ReactionEventPayload（message_id/reaction/reactor/action/added?/removed?）
2. 协议包 codec.ts：FRAME_TYPES 加 reaction_event，新增 validateReactionEventPayload（message_id 整数、reaction/reactor 非空串、action 仅 add/remove、added/removed 若出现须为布尔）
3. 网关 hub.ts：新增 broadcastReactionEvent（与 broadcastTaskEvent 同款 makeEnvelope + broadcast）
4. 网关 server.ts：REST POST 添加（added=true 时）与 DELETE 删除（removed=true 时）广播，幂等重复不广播
5. 测试 gateway/test/reaction-broadcast.test.ts 4 例

## 实测结果
- 新测试 4/4 全绿
- 既有 reactions.test.ts 19/19 同跑全绿
- 网关 tsc 主包与测试包 typecheck：本轮文件零新增错误（另有 game-frames/pairing/werewolf 既存类型错误与本轮无关）

## 已知保留
- Web 反应 UI 未做
- 反应列表仍需调 REST 端点或等广播帧
- 广播不做离线补发（断线期间的反应帧不补，客户端重查 REST 列表为准）

## 许可证注记
原版 OpenAgents 为 Apache-2.0；本轮为思想重实现（TS 原生 WS），非代码搬运。
