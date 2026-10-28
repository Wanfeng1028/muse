# OpenAgents 第 18 轮：设备密钥 WS 握手鉴权

## 原版规格

OpenAgents agent-connector 的身份分级思想（key-proof 挑战应答 / JWT / DID 三级）与第 16 轮已核实的兑码行为：短配对码一次性兑换为私有连接 token，设备配对跨工作区持久存在。本轮为 TypeScript 重新实现，并非代码复制；只取“兑码签发的密钥应当在连接时验真”这一条，不引入 JWT/DID。

## 落地

- botstalk/packages/protocol/src/types.ts：HelloPayload 增加可选字段 device_id 与 device_key；不出现表示沿用既有无鉴权握手。
- botstalk/packages/protocol/src/codec.ts：validateHelloPayload 只做形状校验，device_id/device_key 出现时必须为非空字符串；成对性不在 codec 校验。
- botstalk/gateway/src/hub.ts：握手鉴权插在协议版本校验之后、顶号之前。规则：只出现一个字段时关闭 4403 "device auth incomplete"；查不到设备时关闭 4403 "device not found"；已吊销时关闭 4403 "device revoked"；设备 adapter_id 与 hello adapter_id 不一致时关闭 4403 "device adapter mismatch"；hashDeviceKey 比对失败时关闭 4403 "device key mismatch"（等长 timingSafeEqual）；鉴权成功后用既有哈希调 upsertDevice 只刷新 last_seen，不轮换密钥。鉴权失败绝不顶掉既有连接。
- botstalk/gateway/test/device-auth.test.ts：12 例（legacy 连接、合法密钥连接与 last_seen 刷新、未知设备、错误密钥、已吊销、单字段两例、adapter 不一致、失败不顶号、密钥轮换、鉴权后发消息帧、跨房间设备）。
- botstalk/packages/protocol/test/codec-hello-device.test.ts：5 例（无字段通过、双字段通过、空 device_id 拒绝、非字符串 device_key 拒绝、单字段时 codec 不拒绝并注释成对性归网关层）。
- botstalk/scripts/smoke-device-auth.mjs：真实网关 11 次 ok（建房、签发、兑码、合法握手保持连接、错误密钥 4403、未知设备 4403、单字段 4403、legacy 握手保持连接、吊销、吊销后旧密钥 4403、吊销后 legacy 仍可连接），成功打印 SMOKE_DEVICE_AUTH_PASS；运行时用 NODE_PATH 指向 botstalk 根 node_modules 解析 ws，GATEWAY_PORT 默认 18492。
- 不升协议版本：device 字段为可选，向后兼容；旧客户端不带字段走既有路径，旧网关忽略未知字段。

## 验收

- 网关源码 tsc 全洁；协议 tsc 全洁；网关测试包 tsc 本轮文件零错（既存 better-sqlite3/pairing/werewolf 错误未动）。
- 网关全量 78 文件 1016 例全绿（基线 77 文件 1004 例，恰增本轮 1 文件 12 例）。
- 协议全量 23 文件 203 例全绿（恰增本轮 1 文件 5 例）。
- 真实网关冒烟 SMOKE_DEVICE_AUTH_PASS（11 次 ok）。
- 无 Web UI 改动，视觉验收不适用。

## 已知保留

- 设备密钥只在握手时验真；连接建立后吊销不踢在线连接（吊销后重连才会被挡）。
- 吊销为终态，无解吊销端点。
- adapter 客户端（base/deepseek）尚未在 hello 中发送 device 字段；密钥握手目前面向原始 WS 客户端与 byo 侧自带实现，base 客户端透传留待下轮。
- REST requester 仍自报身份（既有限制，本轮未动）。
- 第 17 轮（设备管理 Web UI）未补 CHANGELOG 与轮次文档，本轮未代补，缺口仍在。