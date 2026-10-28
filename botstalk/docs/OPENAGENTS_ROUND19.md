# OpenAgents 第 19 轮：adapter 客户端 hello 设备密钥透传

## 原版规格

第 18 轮网关鉴权：adapter 连接网关时由 hello 帧承载设备凭据，网关据此鉴权；仅发一个字段会被网关以 4403 拒绝，无凭据按 legacy 连接放行。第 18 轮留待下轮项一句话：在 adapter 客户端侧实现 hello 设备密钥透传（`AdapterOptions` 支持显式 `device`，并支持环境变量注入），本轮落地。

## 落地

### client.ts

`adapters/base/src/client.ts`：`AdapterOptions` 新增可选 `device?: { id: string; key: string }`；新增 `protected resolveDeviceCredentials()`：显式 `device` 两字段非空优先，否则环境变量 `BOTSTALK_DEVICE_ID` 与 `BOTSTALK_DEVICE_KEY` 两字段非空时用环境变量对，单字段或空串返回 `undefined`（绝不只发一个字段，否则网关 4403）；`onOpen` 有凭据时 hello payload 带 `device_id`/`device_key`，无凭据时 hello 与旧版一字不差；重连时 `onOpen` 重发，故重连同样带凭据。网关与 protocol 包一字未动，不升协议版本。deepseek 适配器 main 未改代码：它经 `AdapterClient` 构造，进程设置上述环境变量即自动透传。

### 测试

新增 `adapters/base/test/device-hello.test.ts` 8 例：opts 对发送、无设备无字段、环境变量对发送、opts 压过环境变量、单 opts 字段省略、单环境变量字段省略、空串 opts 省略、空环境变量省略；用 FakeGateway 断言 hello 首帧 payload。

### 冒烟

新增 `scripts/smoke-device-hello.mjs`，对真实网关冒烟：端口 18493，有效设备 adapter1 进 presence、legacy adapter2 进 presence、错密钥 adapter3 不进 presence；精确 4403 码由第 18 轮原始 WS 冒烟覆盖。冒烟 10 ok，打印 `SMOKE_DEVICE_HELLO_PASS`。

## 验收

- base 全量 vitest：5 文件 45 例全绿。
- base 源码 tsc 全洁。
- base 测试 tsc 有 3 处既存错误，均在旧文件 `client.test.ts` 与 `client-gseq-reconnect.deep.test.ts` 内，本轮未动；本轮新文件零错。
- 真实网关冒烟 `scripts/smoke-device-hello.mjs`：10 ok，打印 `SMOKE_DEVICE_HELLO_PASS`（端口 18493：有效设备 adapter1 进 presence、legacy adapter2 进 presence、错密钥 adapter3 不进 presence；精确 4403 码由第 18 轮原始 WS 冒烟覆盖）。
- 无 Web UI 改动，视觉验收不适用。

## 已知保留

- 第 18 轮保留项仍在：在线连接吊销不踢人、吊销终态、REST requester 自报身份未动。
- 第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口本轮未代补，仍在。
