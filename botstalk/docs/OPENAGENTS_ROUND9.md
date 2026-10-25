# OpenAgents 第 9 轮：配对码入驻（房间级单次码 + 兑码入房）

来源：对标报告抄清单 9（设备配对码入驻）。对方是 Python + TS Launcher 异构实现，本轮为 TS 原生重实现，非代码搬运；许可证：原版 Apache-2.0，botstalk 沿用 MIT。

## 1 原版规格（已从 openagents-develop.tar.gz 提取核实）

- CLI：`agent-connector device connect XXXX-XXXX`（Workspace 的 Devices 页生成配对码）；配对一次后，该设备上创建的 agent 免令牌加入；`agent-connector device status` 可查设备状态。
- 兑码链路：短码经 POST /v1/nodes/redeem 换回私有连接令牌（launcher/src/main/node-pairing.ts 注释原话：short-lived code that hands back a private connection token）。
- 设备配对持久化：设备有稳定 device id，配对记录按工作区多条共存（pairings 数组，newest first）；同一工作区同一 owner 重兑码更新原记录；忘掉某工作区配对后只有新码能恢复。
- 本轮只取其中"配对一次、凭码加入"核心闭环；设备信任存量（稳定 device key、多工作区配对表、连接令牌签发）记为二期，见 §5。

## 2 本轮设计决策

- 码格式：XXXX-XXXX，字符表排除易混淆的 I、O、0、1（32 字符）；网关只存 SHA-256 哈希，码本身只在签发响应返回一次。
- 作用域：码绑定单个房间（原版绑定设备/工作区；房间级是本轮落地的第一步，见 §5 局限）。
- 有效期：默认 10 分钟，签发时 ttl_minutes 可配，钳制到 [1, 60]。
- 签发权限：沿用第 7/8 轮管理矩阵——POST /api/rooms/:room/pairing-codes 只允许房主/管理员（canManageRoom），否则 403 ROOM_MANAGE_FORBIDDEN；未知房 404。
- 兑码语义：POST /api/pairing-codes/redeem，格式非法 400 INVALID_PAIRING_CODE、未知码 404 PAIRING_CODE_NOT_FOUND、已兑 409 PAIRING_CODE_USED、过期 410 PAIRING_CODE_EXPIRED；兑码成功即把 adapter 加为该房成员（幂等：已是成员不再重复加）。
- 设备侧：adapters/byo-bridge 新增 pairing.ts，redeemPairingCode(httpBase, code, adapterId, fetchImpl) 纯 fetch 封装；服务端错误原样以 PairingError(code) 抛出；空参数在发请求前抛 invalid_argument。
- 不碰 Web 前端、不改协议版本（v1.3 兼容，纯 REST 新增）。

## 3 交付

- 网关 gateway/src/pairing.ts：码生成/归一化/格式化/哈希/TTL 钳制/过期与已兑判断。
- 网关 gateway/src/db.ts：pairing_codes 表（code_hash 主键、room、created_at_ms、expires_at_ms、redeemed_at_ms、redeemed_adapter_id）+ issuePairingCode/getPairingCode/redeemPairingCode（先查行再判定过期/已兑，UPDATE 带 redeemed_at_ms IS NULL 条件防并发二次兑）。
- 网关 gateway/src/server.ts：POST /api/rooms/:room/pairing-codes 与 POST /api/pairing-codes/redeem 两端点。
- 设备侧 adapters/byo-bridge/src/pairing.ts + 测试。
- 冒烟 scripts/smoke-pairing.mjs：真实网关 9 步全过（建房→非房主发码 403→房主发码 201→未知码 404→兑码 200→成员含兑码者→二次兑码 409→第二码兑码 200）。

## 4 验收

- 网关新测试 gateway/test/pairing.test.ts 19/19（纯函数 7、db 4、REST 8）；byo-bridge 新测试 test/pairing.test.ts 5/5；网关 tsc 与 byo-bridge tsc 全洁。
- 验收抓出 3 个测试侧问题已修（均非产品 bug）：成员端点返回 {members:[...]} 而非数组；db 行字段为 code_hash 而非 codeHash；REST harness 误用 startServer 单参数与 server.server，实为 startServer(config, db) 与 server.httpServer。
- 验收抓出 1 个冒烟脚本真 bug 已修：脚本在 catch 与成功分支直接 process.exit()，finally 里的杀网关根本不执行，首跑网关成孤儿进程占住管道；修为 exit 前显式 cleanup（SIGTERM + 删数据目录），重跑 9/9 通过且无孤儿进程。

## 5 未做与已知局限

1. 未做设备信任二期：无稳定 device key、无多工作区配对表、无连接令牌签发；本轮码为房间级单次码，兑完即废，不复用。
2. REST requester 仍为自报身份、无鉴权（第 7/8 轮局限未变）；矩阵是授权逻辑，不是身份认证。
3. Web 端无发码/兑码 UI；只读分享链接（抄清单 12）仍未做，排期下一机动轮。
