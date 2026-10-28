# OpenAgents 第 20 轮：吊销在线设备即踢人

## 原版规格

第 18 轮遗留项「在线连接吊销不踢人」：本轮关闭该项。第 19 轮已落地 adapter 客户端 hello 设备密钥透传，本轮在此基础上补齐吊销踢人。

## 落地

### gateway/src/hub.ts

- `Conn` 新增可选字段 `deviceId?: string`，在 hello 设备鉴权成功时赋值，legacy 连接为 `undefined`。
- 新增 Hub 方法 `kickDeviceConnections(room: string, deviceId: string): number`：遍历 `conns`，房间与 `deviceId` 同时匹配才关闭连接（关闭码 4403、原因 `"device revoked"`），返回踢掉数；`close` 抛异常不计入。
- legacy 连接与其它房间的同名设备绝不被踢。
- 方法本身不删 `conns`、不写 presence；删连接与 presence 下线由既有 close 回调负责。

### gateway/src/server.ts

- `DELETE /api/rooms/:room/devices/:device_id` 在 `revokeResult` 为 `ok` 或 `already` 时，先调 `hub.kickDeviceConnections(roomId, deviceId)` 再返回 204；`already` 也踢，覆盖旧版本遗留的在线连接。
- 404 与 403 分支一字未动。
- `hub` 为同一 `startServer` 函数内后定义的变量，请求时回调引用，与既有 `hub.broadcast` 调用方式相同；无新增 import、无参数改动。

## 测试

新增 `gateway/test/device-revoke-kick.test.ts`，共 7 例：

Hub 级 5 例：

1. 踢掉设备鉴权连接返回 4403 且 `conns` 与在线表清除
2. legacy 连接不被踢
3. 其它房间同名设备不被踢
4. 踢未知设备返回 0
5. 同设备第二次踢返回 0

REST 级 2 例：

6. REST 吊销踢掉在线连接且同 key 再 hello 被 4403 拒绝
7. REST 吊销未知设备返回 404 `DEVICE_NOT_FOUND`

数字：相关三文件 36 例全绿（新测 7 + device-auth 12 + devices 17）；网关全量 79 文件 1023 例全绿（基线 78 文件 1016 例，恰增本轮 1 文件 7 例）。

## 冒烟

新增 `scripts/smoke-device-revoke-kick.mjs`，真实网关端口 18494，10 ok，打印 `SMOKE_DEVICE_REVOKE_KICK_PASS`。

覆盖清单：建房、签发、兑码、设备客户端在线、legacy 在线、未知设备吊销 404 且无人被踢、吊销 204、被踢下线、legacy 不受影响。

## 验收

- 网关源码 tsc 全洁。
- 新测试文件测试 tsc 零错（既存旧文件错误未动）。
- 网关全量 79 文件 1023 例全绿。

## 编排机械修正

1. 测试稿把兑码状态写成 201，按 `devices.test.ts` 既定 200 修正。
2. 新测试文件两处 `server.httpServer.address().port` 按 `device-auth.test.ts` 的 `typeof` narrowing 写法修正空值类型错。
3. 冒烟脚本初版按 presence 成员在场判在线而失败——presence 端点返回含 offline 行的全部记录，修正为按 `status === "online"` 判定三处（两助手函数与两处事后断言），gateway 本身无 bug，修正后 10/10 通过。

## 已知保留

- 吊销仍为终态（无取消吊销接口）。
- REST requester 自报身份未动。
- 第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口本轮未代补，仍在。
- 被踢的 AdapterClient 会按既有重连逻辑反复重连并反复被 4403 拒绝（presence 保持 offline），4403 不停重连的行为本轮未改，列为后续可选项。
- 无 Web UI 改动，视觉验收不适用；无协议版本变更。
