# OpenAgents 第 15 轮：配对码 Web UI

## 原版规格

- 第 9 轮已落地房间级单次配对码 REST：`POST /api/rooms/:room/pairing-codes` 签发返回 201；`POST /api/pairing-codes/redeem` 兑码返回 200。
- 原版 Apache-2.0。
- 本轮只做 Web 闭环，不改网关与协议。

## 改动清单

1. `web/src/api.ts`
   - 新增类型 `IssuedPairingCode` / `RedeemedPairingCode`。
   - 新增封装 `issuePairingCode(room, requester, ttlMinutes?)` 与 `redeemPairingCode(code, adapterId)`。

2. 新文件 `web/src/components/PairingPanel.tsx`
   - 签发区：分钟数输入，默认 10，钳制 1~60；成功显示码、过期时间与复制按钮。
   - 兑码区：配对码输入与设备 id 输入（默认当前 nick）；成功显示房间、设备与兑码时间。
   - 失败时原样显示服务端 `error` 字符串。
   - 两区独立 `loading` / `error`。
   - 复用 `appr-*` 类，无新增 CSS。

3. `web/src/components/Chat.tsx`（6 处）
   - 引入 `KeyRound` 图标。
   - 引入 `PairingPanel`。
   - 新增 `showPairing` 状态。
   - 顶栏新增“配对码”按钮。
   - 模块栏新增“配对码”入口。
   - 渲染配对面板。

## 实测结果

- `web` 执行 `tsc -b` 与 `vite build` 通过。
- 网关执行 `tsc` 构建通过（网关代码本轮一字未动）。
- 截图脚本输出 `PAIRING_UI_SHOT_PASS`，配对码 `6FGE-PUDW`，浏览器 console 零错误。
- 真实截图 2 张：`docs/screenshots/pairing/pairing-issue.png` 与 `docs/screenshots/pairing/pairing-redeemed.png`，均已亲眼确认。

## 已知保留

- 设备信任二期未做。
- 配对码兑完即废。
- 兑码成功显示 `redeemed.room` 与 `adapter_id`。
- 非房主签发时服务端返回 `ROOM_MANAGE_FORBIDDEN`，前端原样显示。

## 许可证注记

- 配对码 REST 为 TS 重实现，原版 Apache-2.0。
