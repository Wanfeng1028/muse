# 星命盘云开发后端

微信云开发后端：10 个云函数 + 云数据库 + 云存储。不配域名、不配 Docker/Caddy、
不走日本服务器。会话走云开发原生 openid，不自造 JWT。

## 函数清单

| 函数 | 职责 |
|---|---|
| login | 创建/更新 users 记录（openid、昵称头像、性别、设备指纹、邀请码） |
| charts | 命盘历史 CRUD + 设默认盘 + 删除；后端只存不算，排盘在小程序端完成 |
| membership | 查会员状态（有效档位/到期/续费开关）、取消续费 |
| order | 建订单 + cloudPay 统一下单返回支付参数 + 支付回调（本函数即回调，functionName=order） |
| points | 积分账本（只增不改）+ 领取/消费/兑换 Pro |
| invite | 专属码、绑定、成功结算、阶梯奖励、小程序码（占位降级） |
| ai | AI 解盘/问答：CloudBase 主力 + BotsRouter 备用 + aiCache 缓存 + 额度降级 |
| aiImage | 生图：CloudBase 混元生图主力 + BotsRouter 备用 + imageCache 缓存 + 云存储 fileID |
| config | 下发广告位 ID、会员价目、积分规则、AI 配置（客户端绝不硬编码这些值） |
| feedback | 意见反馈：创建 + 本人列表（状态 open，回复由运营在控制台处理，不伪造回复） |

每个函数目录独立可部署：`index.js` + `package.json` + `shared/`（共享模块的
物化副本）。`tests/` 不是云函数，不要部署。

## 共享模块规则

- 唯一事实来源：`_shared/*.js`。改动只改这里。
- 每次改完跑同步，再部署：
  - `node cloudfunctions/sync-shared.js`
- 同步后各函数目录的 `shared/` 与 `_shared/` 内容一致，可直接在开发者工具里
  右键上传并部署单个函数。

## 部署步骤

1. 微信开发者工具打开小程序项目，确认 `project.config.json` 的
   `cloudfunctionRoot` 指向本目录（`cloudfunctions/`）。
2. 开通云开发环境，记下环境 ID（只填进开发者工具/云函数环境配置，不进代码）。
3. 云开发控制台 → 数据库，新建 11 个集合（见 `docs/cloud-schema.md`），
   并按文档建索引、配安全规则（客户端直连数据库只读自己文档，写操作一律走云函数）。
4. 把 `cloudfunctions/_shared/config-seed.js` 里的 `SEED_CONFIGS` 5 条文档
   （pricing、ads、pointsRules、ai、quota）导入 `configs` 集合。
   未导入时函数会用种子兜底并返回 `fromSeed: true`，上线前必须消除该标记。
5. 云函数环境配置（控制台 → 云函数 → 环境变量）按下面清单填写。
   全部留空时对应功能返回明确的未配置错误，绝不伪造成功。
6. 开发者工具里对 10 个函数逐个右键「上传并部署：云端安装依赖」。
   超时建议：ai 120 秒，aiImage 300 秒（生图官方建议最长 900 秒）。
7. 小程序端 `wx.cloud.init({ env: '<环境ID>', traceUser: true })` 后按
   `docs/cloud-api.md` 依次调用：先 `login`，再其他函数。

## 环境配置清单

| 变量 | 用途 | 未配置时表现 |
|---|---|---|
| CLOUDBASE_ENV_ID（或 ENV_ID / TCB_ENV_ID） | @cloudbase/node-sdk 初始化，AI 主力通道 | AI 走 BotsRouter 备用并标注 degraded |
| BOTSROUTER_API_KEY | BotsRouter 备用通道密钥 | 备用不可用时返回 AI_UNAVAILABLE，不伪造结果 |
| BOTSROUTER_BASE_URL | 备用通道地址，默认 https://api.botsarena.tech/v1 | 默认值 |
| BOTSROUTER_CHAT_MODEL | 备用对话模型（configs 可覆盖，默认 deepseek-v4.1-flash） | 默认值 |
| BOTSROUTER_IMAGE_MODEL | 备用生图模型；种子故意留空，不编造模型名 | 生图备用返回未配置错误 |
| WECHAT_PAY_SUB_MCH_ID | 云调用支付商户号（subMchId） | order 返回 PAY_NOT_CONFIGURED，订单保持待支付 |
| WECHAT_PAY_ENV_ID | 支付回调所在云环境 ID | 同上 |
| WECHAT_PAY_CALLBACK_FUNCTION | 支付回调云函数名，默认 order | 默认 order |

补充前置（用户侧在控制台/支付后台完成，不阻塞代码）：
- 商户号超级管理员在「微信支付商家助手」小程序确认授权给
  1800008281（小程序云开发服务商账号）。
- CloudBase 控制台 → AI → 生文/生图模型：启用 deepseek-v4-flash 与
  HY-Image-3.0-Plus-4090-Tob-v1.0（或在 configs 里改成已启用的模型名）。
- 流量主 UV 达 1000 后，在 configs.ads 里把 4 个占位广告位 ID 换成真实 ID。

## AI 通道（以官方文档为准，不猜接口）

- 对话主力：`@cloudbase/node-sdk`，`app.ai().createModel('cloudbase')` +
  `generateText({ model, messages })`，模型默认 deepseek-v4-flash。
  另有一条微信侧写法（wx-server-sdk 的 `cloud.ai` / 小程序 `wx.cloud.extend.AI`）
  与本实现等价，未采用是因为其云函数侧 generateText 入参形态在文档中
  以 streamText 为主；如需切换，先以官方文档核对后再改适配器。
- 生图主力：`app.ai().createImageModel('hunyuan-image')` +
  `generateImage({ model: 'HY-Image-3.0-Plus-4090-Tob-v1.0', prompt, size, revise })`，
  要求 @cloudbase/node-sdk >= 3.18.3。模型返回 24 小时有效 URL，
  本函数下载后转存云存储，缓存与返回的一律是 fileID。
- 备用：BotsRouter OpenAI 兼容 `/chat/completions` 与 `/images/generations`。
- 额度：quotaLogs 按日统计 CloudBase 用量，达阈值（默认 85%）自动降级到
  BotsRouter 并在响应里标注 `degraded: true` + 原因，绝不静默失败。

## 本地检查

- 语法：`for f in login charts membership order points invite ai aiImage config feedback; do node --check $f/index.js; done`
- 纯逻辑测试：`node cloudfunctions/tests/pure-logic.test.js`（20 项，含积分规则、
  邀请阶梯、盘 hash、缓存键、额度阈值、种子价目、不降级发放、未成年人门禁）
- 接口契约检查：`node cloudfunctions/tests/contract-check.js`（客户端每个
  callFn 调用点在服务端都有对应函数与 action，无真实云环境时以此
  代替联调；真实云端调用仍需 envId 后复测）
- 真实云环境调用、支付、AI、生图均需真实 envId/商户号/密钥，见
  `docs/cloud-api.md` 末尾「无真实配置时不可测的项」。
- 部署前置补记（2026-11-01 二期联调发现）：小程序端 `project.config.json`
  的 `cloudfunctionRoot` 须指向本目录；开发者工具导入的构建产物目录
  不同，相对路径以导入目录为准，导入后以开发者工具实际解析为准，
  本仓库不猜测导入目录，部署时以工具内显示的函数列表为准核验。
