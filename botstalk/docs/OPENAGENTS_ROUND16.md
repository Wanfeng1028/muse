# OpenAgents 第 16 轮：设备信任（稳定 device key + 幂等重兑 + 设备管理）

## 原版规格
OpenAgents agent-connector 的设备配对行为：短配对码一次性兑换为私有连接 token；设备配对跨工作区持久存在；使用同一设备重新兑换会更新原记录而非重复创建。本轮为 TypeScript 重新实现，并非代码复制。

## 落地
- `gateway/src/devices.ts`：`generateDeviceKey`（32 随机字节转为 64 位小写 hex）、`hashDeviceKey`（SHA-256）、`normalizeDeviceId`（trim + 长度 1..128）、`DeviceRecord`、`isDeviceRevoked`。
- `gateway/src/db.ts`：`devices` 表（`device_id`、`room` 作为主键）+ `device_key_hash`/`adapter_id`/`created_at_ms`/`last_seen_ms`/`revoked_at_ms` + `upsertDevice`（created/updated/revoked）+ `getDevice` + `listDevicesByRoom` + `revokeDevice`（ok/already/not_found）。
- `gateway/src/server.ts`：`POST /api/pairing-codes/redeem` 接受可选 `device_id`（缺省 = `adapter_id`，无效返回 `400 INVALID_DEVICE_ID`），在消耗配对码前对吊销设备进行预检查返回 `403 DEVICE_REVOKED`，成功时仅返回一次 `device_id` + `device_key`（仅存储哈希）；`GET /api/rooms/:room/devices`（owner/admin 权限，仅返回元数据，绝不返回 `device_key_hash`）；`DELETE /api/rooms/:room/devices/:device_id`（owner/admin 权限，成功返回 `204`，未知设备返回 `404 DEVICE_NOT_FOUND`）。
- `gateway/test/devices.test.ts`：17 个测试（4 个纯函数 + 5 个数据库 + 8 个 REST）。
- `scripts/smoke-devices.mjs`：在真实网关上执行 11 步，结果为 PASS。

## 验收
- `gateway` `tsc` 编译通过（clean）。
- 设备测试 17/17 全部通过。
- 冒烟测试 11/11 全部通过。

## 已知保留
- `device_key` 尚未用于后续连接的身份验证（暂未实现通过设备密钥认证的 WS 连接）。
- 吊销状态为终结状态（暂无取消吊销接口）。
- Web 端设备管理 UI 尚未完成。
- REST 请求者目前仍依赖自我报告（预存限制，本轮未改变）。
