# OpenAgents 第 7 轮：管理操作矩阵（后端，REST 层）

来源：第 6 轮文档 §5 第 2 项未做——guest 改房间类型、删成员等管理操作未做权限矩阵。
本轮只动后端（协议 + 网关 REST），不改 Web 前端。前端抄 AirBuild 的决策仍待用户答复，
本轮不碰任何前端文件。

## 1 矩阵（以 requester 身份为准，REST 的 requester 为调用方自报，见 §5 局限）

| 操作 | workroom | playroom | guest |
| --- | --- | --- | --- |
| DELETE 成员（踢人） | 仅房主（沿用协议已有的 canClearOrKick） | 仅房主 | 否（非房主即否） |
| PATCH 成员人设 | 房主 | 非 guest 成员 | 否 |
| PATCH 房间名 / 话题 | 房主 | 非 guest 成员 | 否 |
| PATCH 房间类型 | 房主（既有规则不变） | 非 guest 成员（新增 guest 否决） | 否 |

身份解析（网关 server.ts 的 managePerm）：requester 等于 room.owner 恒为 admin；
其余查 room_members 的 perm_role 列（非法值按 member 计，与第 6 轮一致）；
非成员、未带 requester 时 perm 为 undefined，不按 guest 处理。

## 2 落点

- 协议 `packages/protocol/src/rooms-types.ts`：新增 canManageRoom(roomType, isOwner, permRole)——
  guest 一律 false，其余走既有 canUpdateRoom（workroom 房主、playroom 全员）。
  踢人直接复用既有 canClearOrKick，不新增函数。
- 网关 `gateway/src/server.ts`：新增 managePerm 辅助；PATCH 房间在改类型之前先守改名/话题，
  改类型分支加 guest 否决（错误仍为既有 ROOM_TYPE_FORBIDDEN）；DELETE 成员用查询串
  `?requester=` 取身份（DELETE 请求体不可靠携带），守 canClearOrKick，错误
  ROOM_MANAGE_FORBIDDEN；PATCH 成员人设守 canManageRoom，错误同上。
  另修一处既有隐患：改人设 handler 原先只判房间存在、未绑定 room 变量，
  本轮改为绑定 room 后再守卫，否则守卫代码无法编译。
- 既有测试随行为收紧同步改（不是悄悄放宽）：rooms-server.test.ts 的改名用例补
  requester=alice；成员用例的房间补 owner=alice，改人设补 requester=alice，
  删成员改走 `?requester=alice`。其余既有用例行为不变。

## 3 测试

- 协议 `packages/protocol/test/management-matrix.test.ts`：3 例（guest 否决优先、
  workroom 房主/非房主、playroom 成员/guest）。
- 网关 `gateway/test/management-matrix-r7.test.ts`：2 例（workroom 六分支、
  playroom guest 改名/改类型否决、成员改名放行、成员踢人仍否决、房主踢人放行）。
- 协议全量 22 文件 198 例、网关全量 70 文件 921 例零回归（此前为 195 / 919，增量恰为本轮 3 + 2 例）。

## 4 模型稿核对（未照抄）

- GLM-5.3 五段小稿均可用正文（协议函数、服务端辅助、改名守卫、踢人守卫、改人设守卫）。
- 编排修正 3 处：模型稿的 Express 式 `res.status(403).json(...)` 改为本仓
  `writeHead + end(JSON.stringify(...))` 写法；踢人稿的 `new URL(url)`（相对路径会抛错）
  改为本仓既有用法的 `new URL(url, "http://localhost")`；协议函数稿补 `export`（本文件函数一律导出）。
- 网关构建依赖协议 dist：协议源码改后须先 `npm run build` 再测网关，否则网关 tsc 报
  canManageRoom 未导出（本轮实测踩到，已记）。

## 5 未做与已知局限（明确边界，不编造）

1. 拉人（POST 成员）仍未守权限：协议已有 canInvite（workroom 房主、playroom 全员），
   但服务端 POST 成员端点尚未接线，排期下一轮。
2. 设权限角色无 REST 端点：setPermRole 只存在于 db 层，房主目前无法经 API 把成员
   升为 admin / 降为 guest；guest 身份须由建库方直接写库，排期下一轮（与拉人守卫一起做）。
3. REST requester 为自报身份，无鉴权：矩阵是授权逻辑，不是身份认证；playroom 下
   未带身份的调用仍按既有 canUpdateRoom 放行改名/人设，workroom 下未带身份一律否决。
   真鉴权（登录态绑定 requester）不在本轮范围。
4. 无房主的 workroom 将无人能管理（踢人/人设/改名均需房主）：建房时应带 owner；
   目前没有改房主的接口，旧无房主房间的管理恢复排期后续。
5. 第 6 轮其余未做项不变：PUBLIC / NETWORK / CHANNEL / MOD_ONLY 四级可见性、
   Web 端悄悄话/白名单发送 UI 仍未做。
