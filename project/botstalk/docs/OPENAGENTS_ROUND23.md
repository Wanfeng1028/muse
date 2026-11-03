# OpenAgents 第 23 轮：分享链接签发 ttl_hours 非法值返回 400

## 动机
分享链接签发接口此前对 ttl_hours 的非法取值采取静默钳制或回落 168：调用方传入的有效期被网关悄悄改写后照常签发，调用方既无法感知输入被改写，也无法区分“我传的值生效了”与“我传的值被丢掉了”。本轮将该分支改为显式校验：非法值一律拒绝，不再静默钳制或回落，让非法输入在入口即暴露。

## 落地
改动范围仅 botstalk/gateway/src/server.ts 的 POST /api/rooms/:room/share-links 分支。在权限校验之后、generateShareToken 之前新增校验逻辑：显式 ttl_hours 不是整数、小于 1 或大于 720 时，返回 400 {"error": "INVALID_TTL_HOURS"}，不签发分享链接；缺省（不传 ttl_hours）仍默认 168 小时；显式传 null 同样返回 400；非房主传非法 ttl_hours 时，仍先在权限校验处得到 403，不进入本轮新增的 ttl 校验。clampShareTtlHours 本身一字未动；校验通过的值再进入它，作为既有防线保留。本轮未动的部分：兑码分支、列出分支、撤销分支、Web 前端均一字未动。分享链接 ttl_hours 的取值范围为 1 到 720 小时，与配对码 ttl_minutes 的 1 到 60 分钟口径同款（第 22 轮），仅单位与上限不同。

## 测试
新增 botstalk/gateway/test/share-ttl-validation.test.ts，12 例全绿：0、-1、721、9999、1.5、字符串 "24"、null、true 各返回 400；非房主传 0 得 403；1 小时、720 小时、缺省各 201，且有效期差值在容差内。关联三文件（新测、share、pairing-ttl-validation）共 44 例全绿。网关全量 vitest：81 文件 1047 例全绿（基线 80 文件 1035 例，恰增本轮 1 文件 12 例）。网关源码 tsc --noEmit 零错；测试 tsc 共 7 处既存错误，均在旧文件内（game-frames、pairing、werewolf），本轮新文件零错。

## 冒烟
新增冒烟脚本 botstalk/scripts/smoke-share-ttl.mjs：对真实网关端口 18497 发起请求，8 项全过，脚本打印 SMOKE_SHARE_TTL_PASS，冒烟结束后端口已关闭。

## 已知保留
吊销仍为终态，无取消吊销接口；REST requester 自报身份未动；第 17 轮设备管理 Web UI 缺 CHANGELOG 与轮次文档的缺口本轮未代补，仍然存在；本轮无 Web UI 改动，视觉验收不适用；本轮无协议版本变更；本轮关闭第 22 轮留下的分享链接 ttl_hours 钳制项。

## 编排机械修正
测试稿编写过程中，签发请求的 requester 字段在多处漏写（只写了 ttl_hours），另有一处把 requester 误写成了 owner。已按 pairing-ttl-validation.test.ts 既有写法，将请求体逐行补为 requester: "alice"（非房主用例为 requester: "mallory"）后，测试才全绿。此为纯测试稿字段名的机械修正，不涉及产品行为改动。冒烟稿首行 import { spawn } 被模型输出的工具调用标记吞并一行，已按第 22 轮冒烟稿的 import 原文机械补回，node --check 通过后冒烟才全过。