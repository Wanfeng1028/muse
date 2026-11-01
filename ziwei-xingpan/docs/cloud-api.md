# 紫微星盘云函数 API

调用方式：小程序端 `wx.cloud.callFunction({ name, data })`。
通用信封：成功 `{ code: 0, data }`；失败 `{ code, message, ... }`。
所有函数先用 `cloud.getWXContext()` 取 OPENID，不自造 JWT；
除 order 的支付回调外，未登录一律返回 `NOT_LOGGED_IN`。
调用顺序：先 `login`，再其他函数（多数函数要求 users 记录已存在，
否则返回 `USER_NOT_FOUND`）。

## 通用错误码

| code | 含义 |
|---|---|
| NOT_LOGGED_IN | 取不到微信登录态 |
| USER_NOT_FOUND | 未调用 login 或用户记录不存在 |
| INVALID_PARAMS | 必填参数缺失或非法 |
| UNKNOWN_ACTION | 未知 action |
| CHART_NOT_FOUND / ORDER_NOT_FOUND | 资源不存在或不属于当前用户 |
| INSUFFICIENT_POINTS | 积分不足 |
| DAILY_LIMIT_REACHED / ALREADY_CLAIMED | 日限已满 / 一次性奖励已领 |
| DEVICE_MISMATCH / SAME_DEVICE | 设备指纹不一致 / 同一设备只计一次 |
| PAY_NOT_CONFIGURED | 支付商户号/环境未配置（订单已建为待支付，不伪造成功） |
| PAY_UNIFIED_ORDER_FAILED | 统一下单未返回支付参数 |
| AI_UNAVAILABLE / AI_IMAGE_UNAVAILABLE | 主备 AI 均失败（附 causes，不伪造结果） |
| BOTSROUTER_API_KEY_NOT_CONFIGURED | 备用通道密钥未配置 |
| BOTSROUTER_IMAGE_MODEL_NOT_CONFIGURED | 备用生图模型未配置（种子故意留空） |
| SELF_INVITE / ALREADY_BOUND / INVITE_CODE_NOT_FOUND | 自绑 / 已绑 / 邀请码不存在 |
| MINOR_AI_BLOCKED | 未成年人不可使用 AI 解读（含会员免费额度），在缓存命中前拦截 |
| MINOR_PURCHASE_BLOCKED | 未成年人不可购买付费会员（order.create 要求先 login 且用户非未成年人） |
| MINOR_PAID_BLOCKED | 未成年人不可用积分兑换付费内容（points.spend 全规则拦截） |

## login

入参：`{ nickname?, avatarUrl?, gender?, deviceFingerprint?, birthYear?, isMinor? }`
（gender 0 未知 / 1 男 / 2 女；birthYear 为出生年份整数，非法值忽略；
isMinor 为 true 时标记未成年人，且仅凭成年出生年份可清除该标记）。

出参 data：`{ openid, isNew, user }`。新用户分配专属邀请码
（openid 哈希派生，冲突重试），`_id` 即 openid，初始积分 0。

未成年人门禁（服务端强制，客户端提示仅作展示）：`ai` 在缓存命中前
拦截未成年人（MINOR_AI_BLOCKED）；`order.create` 要求用户记录存在且
非未成年人（MINOR_PURCHASE_BLOCKED）；`points.spend` 对未成年人全规则
拦截（MINOR_PAID_BLOCKED）。免费排盘、基础解读、知识科普、命盘历史
不受门禁影响。

## charts

入参含 `action`：

| action | 入参 | 出参 data |
|---|---|---|
| list | {} | `{ charts }`（默认盘在前，再按更新时间倒序，最多 100） |
| get | `{ chartId }` | `{ chart }` |
| create | `{ name?, birthParams, chartData }` | `{ chartId, chart }`（含服务端算的 chartHash） |
| update | `{ chartId, name?, birthParams?, chartData? }` | `{ chartId }` |
| remove | `{ chartId }` | `{ chartId, removed: true }` |
| setDefault | `{ chartId }` | `{ chartId, isDefault: true }` |

说明：后端只存不算；`birthParams` 键序不影响 chartHash；
所有权校验失败返回 `CHART_NOT_FOUND`（不区分不存在与非本人）。

## membership

| action | 入参 | 出参 data |
|---|---|---|
| status（默认） | {} | `{ tier, rawTier, expiresAt, autoRenew }`；tier 为到期折算后的有效档位 |
| cancelAutoRenew | {} | 同上 + note；档位保留到 expiresAt，到期降回普通 |

## order

| action | 入参 | 出参 data |
|---|---|---|
| create | `{ plan }`（proMonthly / proContinuous / maxMonthly / maxContinuous） | 成功：`{ orderId, outTradeNo, amountFen, payment, fromSeed }`，payment 直接传给 `wx.requestPayment`；未配置支付：`PAY_NOT_CONFIGURED` + orderId/outTradeNo（订单待支付，可配置后重调） |
| query | `{ orderId }` | `{ order, live }`（live 为 cloudPay 实时查询，未配置时为 null） |
| close | `{ orderId }` | `{ orderId, status: 'closed' }`（仅待支付订单；云调用要求下单满 5 分钟） |
| list | {} | `{ orders }`（倒序，最多 50） |

支付回调：微信直接调用本函数（unifiedOrder 的 functionName=order），
事件含 returnCode/outTradeNo；成功时订单置 paid 并按 plan 发放会员
（仍在有效期则从原到期日顺延，否则从当前时间起算），回调必须返回
`{ errcode: 0 }`。价目全部来自 configs.pricing，逻辑里无硬编码价格。

## points

| action | 入参 | 出参 data |
|---|---|---|
| balance | {} | `{ balance, ledger }`（最近 50 条） |
| earn | `{ rule, deviceFingerprint? }`（rule: signin / video / share / profile） | `{ rule, delta, balance }`；invite / inviteeBonus 不接受客户端领取 |
| spend | `{ rule, chartId? }`（rule: advancedInterpret / aiInterpret / pro7d / pro30d） | `{ rule, delta, balance, membership }`；pro7d/pro30d 同时续 7/30 天 Pro |

规则：签到 +10（日 1 次）、视频 +20（日 5 次）、分享 +5（日 1 次）、
完善资料 +30（一次）；高级解读 50、AI 解读 30、7 天 Pro 300、30 天 Pro 1500；
永不过期。账本只增不改；日限按 Asia/Shanghai 日期算；
登录设备指纹与领取设备指纹不一致时拒绝。

## invite

| action | 入参 | 出参 data |
|---|---|---|
| info | {} | `{ inviteCode, successCount, nextTier, grantedTiers }` |
| bind | `{ code }` | `{ inviterOpenid, inviteeBonus: 50 }`；被邀人 +50 在绑定时发放 |
| settle | {} | `{ newlySuccess, successCount, tiersGrantedNow, nextTier }`；幂等，可重复调 |
| qrcode | {} | 成功 `{ fileID, placeholder: false }`；接口不可用时 `{ placeholder: true, message, error }`（不返回假 fileID） |

成功判定：被邀人 charts 里有盘才计（settle 时核查）；邀请人 +100 在
成功时发放。阶梯：3 人 → 7 天 Pro；10 人 → 30 天 Pro；30 人 → 30 天 Max，
已发阶梯记在 users.grantedInviteTiers，重复结算不重发。

## ai

| action | 入参 | 出参 data |
|---|---|---|
| interpret | `{ chartId, interpretType? }`（默认 full） | 见下 |
| ask | `{ chartId, question, history? }` | 见下 |

出参 data：`{ text, cached, provider, degraded, degradedReason, quotaUsedToday, quotaBudget, chargedPoints, disclaimer }`。
缓存：interpret 按盘 hash + 类型查 aiCache，命中返回 cached:true 且不扣费；
ask 不缓存。计费：Max 不限次免费；Pro 每月 20 次免费，超了按 AI 解读
30 积分扣；其他档位每次 30 积分，余额不足返回 `INSUFFICIENT_POINTS`。
额度：当日 CloudBase 用量达阈值（默认 85%）自动降级 BotsRouter，
响应标注 degraded:true 与原因。主备均失败返回 `AI_UNAVAILABLE`，
不返回伪造文本。每条解读附免责声明。

## aiImage

入参：`{ prompt?, chartId?, kind?, size? }`（kind: poster / daily；
prompt 与 chartId 至少一个；daily + chartId 时按日期 + 盘 hash 缓存）。

出参 data：`{ fileID, cached, provider, degraded, degradedReason }`。
缓存命中直接返回云存储 fileID；新图经 CloudBase 混元生图生成后
下载转存云存储再返回 fileID（模型原 URL 仅 24 小时有效，不作为结果）。
备用为 BotsRouter 图像模型，未配置模型名时返回
`BOTSROUTER_IMAGE_MODEL_NOT_CONFIGURED` 而不是编造图片。

## config

入参：`{ action: 'get' }`（默认 get）。

出参 data：`{ ads, pricing, pointsRules, ai, disclaimer, fromSeed }`。
ads 含 bannerHome / bannerInterpret / rewardedVideo / interstitial
（未开通流量主前为占位 ID，enabled=false）；ai 只下发模型名与
Pro 月限，不含任何密钥。fromSeed=true 表示 configs 集合尚未导入种子，
上线前必须消除。

## feedback

| action | 入参 | 出参 data |
|---|---|---|
| create | `{ content, contact? }`（content 1–1000 字） | `{ feedbackId, status: 'open' }` |
| list | {} | `{ feedbacks }`（本人，倒序，最多 50） |

说明：反馈只有提交与本人查看两条路；运营回复不在本函数内伪造，
未回复的项状态保持 `open`，如实显示。

## 无真实 envId / 商户号时不可测的项

以下各项在本机无真实配置时均不可测，需在真实云环境 + 真实配置下
由协调方复测，复测前不要宣称通过：

1. 全部 10 个函数的真实云端调用（getWXContext、数据库、存储）。
2. 支付全链路：unifiedOrder 返回 payment、wx.requestPayment 调起、
   支付回调 order 发放会员、queryOrder/closeOrder。
3. CloudBase AI 对话与生图（含模型启用、用量计入 quotaLogs、阈值降级实测）。
4. BotsRouter 备用对话（需 BOTSROUTER_API_KEY）与备用生图
   （还需在 configs 中填入真实可用的 BotsRouter 图像模型名）。
5. 小程序码 getUnlimited 生成与云存储上传（需真实 AppID 环境）。
6. configs 种子导入后的 fromSeed=false 状态与真实广告位 ID 下发。
7. 依赖安装：各函数 `npm install`（wx-server-sdk、ai/aiImage 的
   @cloudbase/node-sdk >= 3.18.3）需在开发者工具部署时完成。

已在本机验证：10 个函数 + 10 个共享模块 `node --check` 通过；
纯逻辑测试 `node cloudfunctions/tests/pure-logic.test.js` 13 项通过；
代码与种子中无真实密钥、AppID、商户号、envId（仅占位符与环境变量名）。
