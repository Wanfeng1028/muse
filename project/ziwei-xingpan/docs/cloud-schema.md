# 星命盘云数据库 Schema

环境：微信云开发云数据库（JSON 文档型）。集合名全小写。
约定：所有业务写操作走云函数；客户端直连数据库时安全规则只允许
「登录用户读写自己的文档」，`pointsLedger`、`orders`、`quotaLogs`
客户端只读自己的记录、永不直接写。`_id` 为文档主键；凡以 openid
为键的集合（users、memberships），文档 `_id` 即 openid。

种子文档见 `cloudfunctions/_shared/config-seed.js`（SEED_CONFIGS），
导入 `configs` 集合后以库内文档为准。

## users（用户）

| 字段 | 类型 | 说明 |
|---|---|---|
| _id / openid | string | openid，文档主键 |
| nickname | string | 昵称（最长 64） |
| avatarUrl | string | 头像 URL（最长 512） |
| gender | number | 0 未知 / 1 男 / 2 女 |
| birthYear | number \| null | 出生年份（未成年人门禁换算用，1900–当年之外的非法值不存） |
| minor | boolean | 是否未成年人：主动声明或出生年份换算未满 18 岁；声明后仅凭成年出生年份可清除 |
| deviceFingerprint | string | 设备指纹，防刷用（最长 128） |
| inviteCode | string | 本人专属邀请码，如 ZW + 8 位 |
| invitedBy | string | 邀请人 openid，未绑定为空串 |
| grantedInviteTiers | number[] | 已发放的邀请阶梯 count，如 [3, 10] |
| pointsBalance | number | 积分余额（由账本增量维护） |
| profileBonusClaimed | boolean | 完善资料 +30 是否已领 |
| createdAt / updatedAt / lastLoginAt | date | 时间戳 |

索引建议：`inviteCode`（唯一）、`createdAt`。

## memberships（会员）

| 字段 | 类型 | 说明 |
|---|---|---|
| _id / openid | string | openid，文档主键 |
| tier | string | free / pro / max（原始档位） |
| expiresAt | date \| null | 到期时间；free 为 null |
| autoRenew | boolean | 是否连续包月；取消随时生效，到期降回普通 |
| createdAt / updatedAt | date | 时间戳 |

有效档位判定（见共享模块 membership.js）：`expiresAt` 已过则视为 free，
与 `autoRenew` 无关。索引建议：`expiresAt`。

发放档位不降级规则（见共享模块 membership.js `grantTier`）：
邀请阶梯奖励、积分兑换 Pro、付费购买在发放时一律不得把在用高档位
（如 Max）覆盖成低档位（如 Pro）；高档位在用时只顺延其到期时间，
否则按发放档位写入。订单的 `tier` 字段仍记录购买档位，会员有效档位
以 `memberships` 文档为准。

## orders（订单）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 下单用户 |
| plan | string | plusMonthly / proMonthly / maxMonthly / recharge |
| tier | string | plus / pro / max（recharge 订单为空） |
| days | number | 会员天数（30；recharge 订单为 0） |
| continuous | boolean | 是否连续包月（新档位均为 false；月付，积分一次性到账） |
| yuan | number | 充值元数（仅 recharge 订单） |
| pointsGrant | number | 本单赠送积分数（档位 plans.pointsGrant 或充值 yuan × pointsPerYuan） |
| amountFen | number | 金额（分），与 configs.pricing 一致 |
| outTradeNo | string | 商户订单号，ZW + 时间戳 + 随机数 |
| status | string | pending / paid / failed / closed |
| paidAt | date \| null | 支付成功时间（回调写入） |
| createdAt / updatedAt | date | 时间戳 |

索引建议：`openid + createdAt`、`outTradeNo`（唯一）。

## pointsLedger（积分账本，只增不改）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 用户 |
| type | string | earn / spend |
| rule | string | signin / video / invite / profile / share / inviteeBonus / advancedInterpret / aiInterpret / pro7d / pro30d / dimInterpret / aiPersona / compare / chatImage / posterBg / hdExport / annualFortune / membership / recharge / refund / chatOverage |
| delta | number | 正数为得、负数为花 |
| dayKey | string | Asia/Shanghai 日期，如 2026-11-01（日限用） |
| deviceFingerprint | string | 领取/消费时设备指纹 |
| chartId | string | 关联命盘（消费时可空） |
| createdAt | date | 时间戳 |

规则：代码里只调用 `add()`，永不 `update/remove`；安全规则禁止客户端写。
索引建议：`openid + createdAt`、`openid + rule + dayKey`（日限查询）。

## invites（邀请）

| 字段 | 类型 | 说明 |
|---|---|---|
| inviterOpenid | string | 邀请人 |
| inviteeOpenid | string | 被邀人 |
| inviteCode | string | 绑定时用的邀请码 |
| status | string | pending / success |
| inviteeBonusGranted | boolean | 被邀人 +50 是否已发（绑定时发） |
| inviterRewardGranted | boolean | 邀请人 +100 是否已发（成功时发） |
| createdAt / updatedAt | date | 时间戳 |

成功判定：被邀人在 `charts` 里有至少一张盘（invite.settle 结算时核查）。
同一微信号、同一设备只计一次（bind 拒绝自绑、已绑、设备相同）。
索引建议：`inviterOpenid + status`、`inviteeOpenid + status`。

## charts（命盘历史）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 所属用户（所有权校验键） |
| name | string | 盘名（最长 64） |
| birthParams | object | 出生参数（姓名可选、性别、公历生日、时辰、出生地等），由客户端传 |
| chartData | object | 小程序端排盘结果全文；后端只存不算 |
| chartHash | string | birthParams 归一化后 sha256（服务端算，键序无关） |
| isDefault | boolean | 是否默认盘（每用户至多一张，setDefault 会先清其他） |
| createdAt / updatedAt | date | 时间戳 |

索引建议：`openid + updatedAt`、`openid + isDefault`。注意：`list` 同时按
`isDefault` 与 `updatedAt` 排序，需在控制台为 `charts` 建 `openid + isDefault
+ updatedAt` 复合索引，否则该查询会报索引缺失。

## aiCache（AI 解读缓存）

| 字段 | 类型 | 说明 |
|---|---|---|
| cacheKey | string | sha256（归一化 birthParams + 解读类型），命中键 |
| openid | string | 首次生成用户 |
| chartId | string | 关联命盘 |
| interpretType | string | 解读类型，如 full / wealth / career |
| text | string | 解读全文（含免责声明由响应层附加） |
| provider | string | 生成通道 cloudbase / botsrouter |
| createdAt | date | 时间戳 |

缓存命中不扣积分、不重复调模型。索引建议：`cacheKey`（唯一）。

## imageCache（生图缓存）

| 字段 | 类型 | 说明 |
|---|---|---|
| cacheKey | string | 提示词 hash，或 daily 下的 日期 + 盘 hash |
| openid | string | 首次生成用户 |
| kind | string | poster（海报背景）/ daily（每日运势配图） |
| prompt | string | 最终提示词 |
| fileID | string | 云存储 fileID（ durable 结果；模型原 URL 仅 24 小时有效，不存它） |
| provider | string | cloudbase / botsrouter |
| createdAt | date | 时间戳 |

索引建议：`cacheKey`（唯一）。

## feedbacks（意见反馈）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 提交用户 |
| content | string | 反馈内容（1–1000 字，服务端校验） |
| contact | string | 用户自留联系方式，可空（最长 128） |
| status | string | open（待处理）；回复由运营在控制台处理，客户端不伪造回复状态 |
| createdAt / updatedAt | date | 时间戳 |

索引建议：`openid + createdAt`。

## configs（配置种子，6 条文档）

`_id` 即配置键，内容见 `cloudfunctions/_shared/config-seed.js`：

| _id | 内容 |
|---|---|
| pricing | tiers（free/plus/pro/max，含 pointsGrant 与 noBannerAds/noInterstitialAds/noAllAds/hdExportFree/annualFortuneFree/earlyAccess 标志）+ plans（plusMonthly 1990 分/1000 积分、proMonthly 3490 分/2000 积分、maxMonthly 6990 分/4000 积分，billingCycle monthly）+ recharge（pointsPerYuan 50，minYuan 1）+ 取消说明 |
| ads | bannerHome / bannerInterpret / rewardedVideo / interstitial，全部为 PLACEHOLDER 占位 ID，enabled=false |
| pointsRules | 得（签到 10/视频 20 日限 5/邀请 100/完善资料 30 一次/分享 5 日限 1/被邀 50）与花（全量解读 100/AI 解读 30/单维解读 20/合盘 60/对话内生图 40/海报背景 40/高清导出 40/年度运势 100/人格形象 AI 定制 100/7 天 Pro 300/30 天 Pro 1500），永不过期 |
| ai | cloudbaseChatModel deepseek-v4-flash、cloudbaseImageModel HY-Image-3.0-Plus-4090-Tob-v1.0、botsrouterChatModel deepseek-v4.1-flash、botsrouterImageModel 留空、proMonthlyAiLimit 20、免责声明 |
| quota | dailyTokenBudget 1000000、thresholdPercent 85 |
| chat | dailyTokenQuota 2000000、dailyCallCap 100、historyRounds 10、maxOutputTokens 2000、pointsPerMillionTokens 10 |

索引建议：`_id` 为主键，无需另建。密钥、AppID、商户号绝不进本集合，
一律走云函数环境配置。

## chatLogs（对话审计日志，只增不改）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 对话用户 |
| dayKey | string | 自然日（YYYY-MM-DD，用于免费额度与频次统计） |
| kind | string | chat / image |
| outcome | string | ok / template-fallback / output-flagged / failed / blocked（注入/离题/限流/余额不足均审计） |
| question | string | 用户问题截断 500 字（注入拒绝时亦审计，不回显作指令） |
| summary | string | 本盘关键数据摘要截断 500 字 |
| totalTokens | number | 本轮总 tokens（上游 usage 或估算） |
| quotaCoveredTokens | number | 免费额度覆盖的 tokens |
| chargedPoints | number | 实扣积分（未成年人恒 0） |
| shortfallPoints | number | 余额封顶时的短缺积分（永不透支的审计痕迹） |
| provider | string | cloudbase / botsrouter / template |
| degraded | boolean | 是否降级或模板回退 |
| truncated | boolean | 是否因额度触顶截断 |

系统提示词永不入日志。索引建议：`openid + dayKey`。

## quotaLogs（用量日志，只增不改）

| 字段 | 类型 | 说明 |
|---|---|---|
| openid | string | 调用用户 |
| kind | string | ai / image |
| provider | string | cloudbase / botsrouter |
| model | string | 实际模型名 |
| promptTokens / completionTokens / totalTokens | number | 用量（生图为 0，由通道方另计） |
| dayKey | string | Asia/Shanghai 日期 |
| monthKey | string | 如 2026-11（Pro 每月 20 次免费额度计数用） |
| degraded | boolean | 是否走了降级通道 |
| chartId | string | 关联命盘 |
| createdAt | date | 时间戳 |

索引建议：`provider + dayKey`（额度门统计）、`openid + kind + monthKey`。
