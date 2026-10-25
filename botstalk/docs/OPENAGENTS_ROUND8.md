# OpenAgents 第 8 轮：拉人守卫 + 设权限角色端点（后端，REST 层）

来源：第 7 轮文档 §5 第 1、2 项未做——拉人未守 canInvite、设权限角色无 REST 端点。
本轮只动后端（网关 REST + 既有测试），不改 Web 前端，不改协议（canManageRoom /
canClearOrKick / canInvite / isPermRole 均已存在，直接复用）。

## 1 拉人守卫

- POST /api/rooms/:room/members 接 canManageRoom：guest 一律否决，workroom 仅房主，
  playroom 非 guest 成员放行；错误 ROOM_MANAGE_FORBIDDEN。
- 顺序为先鉴权后校验：无身份调用即使缺 adapter_id 也先回 403；已鉴权的缺 adapter
  调用仍回既有 400。rooms-server.test.ts 的缺 adapter 用例因此补 requester=alice，
  其余断言不变。

## 2 设权限角色端点（新增）

- PATCH /api/rooms/:room/members/:adapter_id/perm，body { perm_role, requester? }。
- 仅房主可设（requester 为空或不等于 room.owner 即 403 ROOM_MANAGE_FORBIDDEN）；
  房主本人权限固定不可改（目标等于 room.owner 即 403）；
  perm_role 非法即 400 INVALID_PERM_ROLE（用 db 层既有 isPermRole 判断）；
  目标不是现有成员即 404（不借此端点拉人，拉人仍走 POST 成员端点）；
  成功回 200 与该成员对象（含 perm_role 列）。
- 路由位置在通用 PATCH 成员人设之前：通用路由的正则要求 adapter_id 后紧跟结尾或问号，
  本不会误匹配 `/perm` 路径，但放前面可读性更强。

## 3 测试

- 网关 `gateway/test/management-matrix-r8.test.ts`：2 例（拉人四分支；
  设权限：非房主 403、非法角色 400、非成员 404、房主自降 403、房主降 guest 后
  该成员在 playroom 改名 403、房主恢复 member 200）。
- 既有测试随行为收紧同步改：rooms-server.test.ts 成员用例的拉人调用补 requester=alice，
  缺 adapter 用例补 requester=alice；management-matrix-r7.test.ts 的拉人调用补房主身份
  （workroom 用 alice、playroom 用 bob）。其余断言不变。
- 网关全量 71 文件 923 例零回归（此前为 70 / 921，增量恰为本轮 1 文件 2 例）；网关 tsc 全洁；协议本轮未改。

## 4 模型稿核对（未照抄）

- GLM-5.3 拉人守卫稿与设权限守卫/校验稿均可用正文（两通 429 后等 90 秒重发成功，
  未硬抢并发槽；429 通不计用量）。
- 编排修正：模型稿的 Express 式 `res.status().json()` 与单引号一律改为本仓
  `writeHead + end(JSON.stringify(...))` 与双引号写法；body 取值补 `?.` 防 undefined。
- 第 3 段模型稿作废：它编造了不存在的签名——listRoomMembers(db, adapterId, roomId)、
  setPermRole(db, adapterId, roomId, user_id, perm_role)、按 user_id 查成员；
  实测签名为 listRoomMembers(db, roomId)、setPermRole(db, roomId, adapterId, role)、
  按 adapter_id 查成员。该块由编排按实测签名手写，未采用模型稿一字。

## 5 未做与已知局限（明确边界，不编造）

1. REST requester 仍为自报身份，无鉴权（第 7 轮局限未变）；矩阵是授权逻辑，不是身份认证。
2. 无房主房间的设权限仍无人可用（仅房主可设，房主为空时任何 requester 均否决）；
   建房时应带 owner，改房主接口排期后续。
3. 第 6 轮其余未做项不变：PUBLIC / NETWORK / CHANNEL / MOD_ONLY 四级可见性、
   Web 端悄悄话/白名单发送 UI 仍未做。
