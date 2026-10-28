# OpenAgents 第 22 轮：配对码签发 ttl_minutes 非法值返回 400

## 动机

配对码签发接口此前对 `ttl_minutes` 的非法取值采取静默钳制/回落：调用方传入的有效期被网关悄悄改写后照常签发，调用方既无法感知输入被改写，也无法区分"我传的值生效了"与"我传的值被丢掉了"。本轮将该分支改为显式校验：非法值一律拒绝，不再静默钳制/回落，让非法输入在入口即暴露。

## 落地

改动范围：仅 `botstalk/gateway/src/server.ts` 的 `POST /api/rooms/:room/pairing-codes` 分支。

在权限校验之后、`generatePairingCode` 之前新增校验逻辑：

- 显式 `ttl_minutes` 不是整数、小于 1 或大于 60 时，返回 `400 {"error": "INVALID_TTL_MINUTES"}`，不签发配对码。
- 缺省（不传 `ttl_minutes`）仍默认 10 分钟。
- 显式传 `null` 同样返回 400。
- 非房主传非法 `ttl_minutes` 时，仍先在权限校验处得到 403，不进入本轮新增的 ttl 校验。

`clampPairingTtlMinutes` 本身一字未动；校验通过的值再进入它，作为既有防线保留。

本轮未动的部分：兑码分支、分享链接分支、Web 前端均一字未动。Web 面板本身只发送 1 到 60 的整数，不受本轮校验影响。

## 测试

新增 `botstalk/gateway/test/pairing-ttl-validation.test.ts`，12 例全绿：

- 0、-1、61、999、1.5、字符串 "10"、null、true 各返回 400；
- 非房主传 0 得 403；
- 1 分钟、60 分钟、缺省各 201，且有效期差值在容差内。

关联三文件（新测、pairing、devices）共 48 例全绿。

网关全量 vitest：80 文件 1035 例全绿（基线 79 文件 1023 例，恰增本轮 1 文件 12 例）。

## 冒烟

新增冒烟脚本 `botstalk/scripts/smoke-pairing-ttl.mjs`：对真实网关端口 18496 发起请求，8 项全过，脚本打印 `SMOKE_PAIRING_TTL_PASS`，冒烟结束后端口已关闭。

## 已知保留

- 分享链接 `ttl_hours` 的 `clampShareTtlHours` 静默钳制本轮未动，留待后续轮次。
- 吊销仍为终态，无取消吊销接口。
- REST requester 自报身份未动。
- 第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口本轮未代补，仍然存在。
- 本轮无 Web UI 改动，视觉验收不适用。
- 本轮无协议版本变更。

## 编排机械修正

测试稿编写过程中，把签发请求的 `requester` 字段误写成了 `owner`。已按 `pairing.test.ts` 既有写法，将请求体中的字段逐行改回 `requester` 后，测试才全绿。此为纯测试稿字段名的机械修正，不涉及产品行为改动。
