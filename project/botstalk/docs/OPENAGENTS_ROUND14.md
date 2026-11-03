# OpenAgents 第 14 轮：Web 消息反应 UI

## 原版规格
本模块基于原版 OpenAgents 第 12 轮定义的 REST 反应接口与第 13 轮实现的反应广播逻辑，本轮 Web UI 是其在客户端的最终闭环。

## 改动清单
1. web/src/api.ts：新增 ReactionSummary 类型、REACTION_OPTIONS（顺序与网关一致，包含 +1, like, smile, ok, done, heart, thumbs_up, thumbs_down 共 8 项）、fetchMessageReactions、addMessageReaction、removeMessageReaction 函数；HistoryMessage.id 类型调整为 number | string。
2. web/src/components/Chat.tsx：ChatItem 经 toChatItem 取 dbId；新增 reactions 状态与 reaction_event 广播分支；实现 resolveDbId、loadReactions、toggleReaction 三个回调，并接入 MessageList。
3. web/src/components/MessageList.tsx：ChatItem 新增 dbId 字段；消息行加入反应汇总 chip、反应开关按钮及 8 项选择器；TaskRow 保持不添加反应。
4. web/src/styles.css：新增 .msg-react-btn、.msg-reactions、.reaction-chip、.reaction-chip-mine、.reaction-picker 样式。

## 关键设计
- UUID 与整数主键错位：前端原有 msgId 为客户端生成的 UUID 字符串，而反应接口依赖 messages 表的整数主键。为此 ChatItem 新增 dbId。历史消息直接从历史接口的整数 id 取，实时 WS 消息 dbId 初始为 null。
- 懒解析：当 dbId 为 null 时，若用户打开反应器或切换反应，前端会先按 sender+seq 从最近 50 条历史中查询并解析出整数 id，再执行接口调用。
- 切换先 GET：切换反应前先 GET 当前汇总状态，根据远端状态决定发起 POST 还是 DELETE，以规避使用过期本地状态导致的误判。

## 实测结果
- 构建验证：web 端 tsc -b 与 vite build 均顺利通过。
- 网关测试：既有测试 reactions 19 例与 reaction-broadcast 4 例，共计 23 例全部通过。
- UI 截图：截图脚本运行成功并输出 REACTIONS_UI_SHOT_PASS，浏览器 console 零错误。已确认 3 张真实截图：reactions-ui.png（汇总含 +1 1 与高亮 heart 1）、reactions-ui-picker.png（8 项选择器展开，heart 高亮）、reactions-ui-toggled.png（取消 heart 后只剩 +1 1）。
- 执行记录：原计划 scripts/smoke-reactions-ui.mjs 因中途截断未落地并作废，其契约由截图脚本内的 REST 序列（建房、取整数 id、两次 POST 断言 added、取消断言）覆盖。
- 模型链：全部调用走 BotsRouter 讯飞星辰 spark-x2.6，合计 22082 真实 token（B1 2386、B2a 2005、B2b 4987、B3 3810、B4 1039、B6 7855）；智谱 glm-4.7 未用（周限额 429 至 2026-10-30 重置），七牛未用，dpsk 未探活仍停用。

## 已知保留
- 反应广播不做离线补发：断线期间的反应帧不补，以 REST 列表为准（沿用第 13 轮规则）。
- 无独立 toggle 端点：前端采用 GET + POST/DELETE 组合实现切换逻辑。
- 历史窗口限制：实时消息若超出最近 50 条历史窗口，懒解析将失败，导致该条消息无法点反应，需刷新历史后恢复。
- 消息类型限制：direct/restricted 消息不落共享历史，因此没有反应入口（与网关落库规则一致）。

## 许可证注记
原版 OpenAgents 遵循 Apache-2.0 许可证。本轮实现为思想重实现，非代码直接搬运。
