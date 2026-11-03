# OpenAgents 第 21 轮：4403 设备鉴权关闭不再重连

## 动机

第 20 轮遗留项：“被踢的 AdapterClient 按既有重连逻辑反复重连并反复被 4403 拒绝（presence 保持 offline）”。本轮关闭该项。

网关 4403 关闭码的全部原因（device auth incomplete / device not found / device revoked / device adapter mismatch / device key mismatch）均为同凭据重试必败的终态，故客户端侧统一按终态处理，不只处理 revoked 一种。

## 落地

只改 `botstalk/adapters/base/src/client.ts`，网关与协议一字未动，不升协议版本：

- `AdapterOptions` 新增可选 `onDeviceAuthFailed?: (code: number, reason: string) => void`。
- `AdapterClient` 新增 `protected deviceAuthFailed = false` 字段与公开方法 `hasDeviceAuthFailure(): boolean`。
- `connect()` 除 `stopped=false` 外，还重置 `shouldReconnect=true` 与 `deviceAuthFailed=false`，使人工用修正后凭据重新 `connect()` 可恢复。
- `openSocket` 的 close 处理改为 `(code: number, reason: Buffer)`：先 `clearHeartbeat`；`code===4403` 时置 `deviceAuthFailed=true`、`shouldReconnect=false`，再 try/catch 调用 `this.opts.onDeviceAuthFailed?.(4403, reason.toString())`（回调抛错不影响关闭流程），绝不调用 `scheduleReconnect`；其他关闭码保持现有行为（shouldReconnect 且未 stopped 时 scheduleReconnect）。
- 密钥绝不打印到日志；`disconnect()` 语义不动。

## 测试

新增 `botstalk/adapters/base/test/device-revoke-noreconnect.test.ts`，共 5 例（4403 on hello 不重连、4403 踢人不重连、普通关闭仍重连、人工重启、回调抛错不破坏），新文件 5/5 全绿；adapters/base 全量 vitest 6 文件 50 例全绿（此前 5 文件 45 例）；base 源码 tsc 全洁。

编排机械修正两处，均经测试重跑验证：模型稿把 `gatewayUrl` 写成 `url` 且漏 `adapterId`，已按 `client.ts` 既定字段修正；manual restart 用例两次 2600ms 等待超出 vitest 默认 5000ms 超时，已给该用例加 15000ms 超时（代码无问题）。

## 冒烟

新增 `botstalk/scripts/smoke-device-revoke-noreconnect.mjs`，真实网关端口 18495，9 ok，打印 `SMOKE_DEVICE_REVOKE_NORECONNECT_PASS`（建房、签发、兑码、设备客户端在线、吊销 204、等 3500ms 后回调恰 1 次且为 `(4403, "device revoked")`、`hasDeviceAuthFailure` 为 true、被踢设备离线）。冒烟脚本脚手架复用既有 `smoke-device-revoke-kick` 的 helper 段，主流程为本轮新稿。

## 已知保留

吊销仍为终态（无取消吊销接口）；REST requester 自报身份未动；第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口本轮未代补，仍在；无 Web UI 改动，视觉验收不适用；无协议版本变更。
