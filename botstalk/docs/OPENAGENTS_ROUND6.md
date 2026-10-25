# OpenAgents 第 6 轮：帧级可见性 + 房间角色组

来源：OpenAgents 清单 4（事件可见性分级）与清单 14（agent_groups + 角色权限），照设计重实现，非代码搬运；对方示例口令 hash 写法未学。
协议版本不变（仍为 v1.3）：visibility / visible_to 均为可选信封字段，缺省时行为与原来完全一致。

## 1 可见性（DIRECT / RESTRICTED）

- 信封字段：`Envelope.visibility?: 'direct' | 'restricted'`，`Envelope.visible_to?: string[]`（信封级，不是 payload 级——可见性是投递属性，不只属于聊天消息）。
- 构造器：`makeEnvelope(..., ts?, extra?: { visibility, visible_to })`，不传 extra 时行为不变；入站帧走 `validateEnvelope`，非法组合在入口被挡。
- 校验（`packages/protocol/src/visibility.ts`，codec 与网关共用同一份，不留两份重复逻辑）：
  - visibility 只能是 direct/restricted；缺省时带 visible_to 报错。
  - direct 要求 visible_to 恰好 1 项；restricted 要求至少 1 项；每项非空且不超过 64 字符；重复项报错。
- 投递（`visibleRecipients`，返回 null 表示按原房间路由广播）：
  - direct：仅 sender 与 visible_to[0]；restricted：sender 与 visible_to 全体。
  - `hub.broadcast` 按此过滤；`routeMessage` 的 workroom 定向分支同样过滤，不绕过。
  - 网关系统帧（presence / task_event）不带 visibility，不受过滤。
- 安全铁律：direct/restricted 消息只发在线、不写入共享房间历史——因为 `GET /api/rooms/:room/history` 无请求者身份，落库即向全房间泄漏。离线目标的 per-adapter 重发队列不受影响（队列只发给本人）。

## 2 房间角色组（最小集）

- `room_members` 表加 `perm_role` 列（新库建表 + 老库 PRAGMA 检查后 ALTER，与 tasks deadline_ms 的迁移模式一致）；`persona_role` 是人设，绝不复用为权限角色。
- `db.ts`：`setPermRole` / `getPermRole`（upsert 语义，与 setPersonaRole / getPersonaRole 对齐；非法列值按 member 计；非成员返回 undefined）；房间 owner 恒为 admin，不依赖列值。
- 权限矩阵（本轮最小集）：guest 发 intent=task（非回执、非进度）时，网关按 playroom 禁止任务的既有模式回一条网关消息（`PERMISSION_DENIED`，task_status=unsupported）并拒绝路由；admin/member 不变；guest 聊天不受影响。

## 3 文件清单

| 文件 | 职责 |
|---|---|
| `packages/protocol/src/visibility.ts` | visibleRecipients / validateVisibility（GLM-5.3 大上下文调用生成，经本轮改编：放进 protocol 包供两边共用，并把错误前缀改为信封级中性写法） |
| `packages/protocol/src/types.ts` | Envelope 新增 visibility / visible_to |
| `packages/protocol/src/codec.ts` | makeEnvelope 加 extra 参数；validateEnvelope 做信封级可见性校验 |
| `packages/protocol/src/index.ts` | 导出 visibility |
| `gateway/src/hub.ts` | broadcast 按可见集合过滤；可见消息不落库 |
| `gateway/src/router.ts` | workroom 定向分支过滤；guest 任务拒绝 |
| `gateway/src/db.ts` | perm_role 列迁移 + setPermRole / getPermRole + RoomMemberRow 扩展 |

## 4 测试

- `packages/protocol/test/visibility.test.ts`：10 例（收件人 3、校验 5、信封编解码 2）。
- `gateway/test/visibility-hub.test.ts`：4 例（真实 WS：direct 只达目标且不落库、restricted 只达白名单、guest 任务拒绝且聊天照常、perm_role 存取/默认/非法回落/非成员）。
- 网关全量：69 文件 919 例全绿；协议全量：21 文件 195 例全绿；网关与协议构建通过。

## 5 未做（明确边界，不编造）

1. PUBLIC / NETWORK / CHANNEL / MOD_ONLY 四级未落（本轮只落 DIRECT 与 RESTRICTED）。
2. guest 改房间类型、删成员等管理操作未做权限矩阵（只做了 guest 禁任务）。
3. Web 端未加“悄悄话/白名单”发送 UI（网关与协议已通，UI 在后续轮次接）。
4. 可见消息不进历史，因此刷新后不可见（安全铁律的直接后果，非 bug）。
