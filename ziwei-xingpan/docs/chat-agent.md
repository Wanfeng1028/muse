# 对话 agent（轻量纯对话）与积分经济说明

> 本轮：2026-11-01 对话 agent + 人物档案 + 纯积分经济。
> 定价以 PLAN.md §四（用户 2026-11-01 亲定）为准；本文只写机制，
> 不重复价目表（价目唯一来源：云函数 `_shared/config-seed.js` 与
> 客户端 `client/src/lib/pricing.ts`，两者由测试断言一致性）。

## 1. 对话形态：轻量纯对话（重 agent loop 已砍）

2026-11-01 19:30 用户纠正：多步工具编排的重 loop 太多，改为纯对话。
每轮 = 打包上下文 → 发后端模型 → 返回文本（聊天）或图片（生图）。

- 打包内容（按顺序）：
  1. 云函数持有的系统提示词（只读 `CHAT_SYSTEM_PROMPT` 环境变量，
     见 §5；缺失时走模板回退，不编造回答）；
  2. 本盘关键数据摘要（客户端引擎构建，见 §2）；
  3. 本会话历史近 N 轮（默认 10 轮，超长截断）；
  4. 用户问题（截断至 1000 字，截断标志回传）。
- 不做：多步工具编排、意图解析 → 工具查盘 → 自检循环。
  循环形状仅作社区调研背景参考（docs/community-research-20261101.md），
  不进代码、不引 npm 包；未来如需多步编排再评估。
- 生图：海报背景 / 人格形象 / 运势配图走同一对话入口的 `image`
  动作（对话内生图 40 积分/张；海报背景与人格形象走 aiImage 的
  缓存路径，缓存命中免费复用；对话内生图不缓存）。

## 2. 摘要契约（客户端构建，云函数视为用户自带上下文）

- 构建方：`client/src/lib/chat-agent.ts` 的 `buildChartSummary`。
  引擎是 TS/本地-only，云函数无法 import，因此摘要由客户端引擎
  构建后随请求发送；云函数只做防御截断（2000 字），不做真实性
  校验——伪造摘要只影响用户自己看的回答，不影响他人与计费。
- 摘要字段：命宫 + 五行局 + 命主/身主；十二宫逐宫“宫名（地支字）：
  主星（四化）/借星/无主星”；当前大限（宫名 + 起止岁）；今年流年
  （年干 + 禄/权/科/忌星名）；格局名（detectPatterns 取名）。
  超长截断时加“…（摘要已截断）”。
- 历史：键 `zw_chat_history_v1:<chartKey>`，取后 rounds×2 条；
  `__IMAGE__` 标记消息（生图结果）发云端时过滤，不计入历史文本。
- 本地模板回退：云未配置时，对话页用 `localTemplateAnswer`
  （宫名/星名/格局命中复述 + DISCLAIMER），免费，不调用模型，
  不耗 quota、不扣积分。本地模板无付费动作，无需未成年人门禁；
  云端以用户 minor 记录为准。

## 3. 安全

### 3.1 输入检测（双份同表，云函数为准）

- 云端：`cloudfunctions/_shared/chat-safety.js`；
  客户端：`client/src/lib/chat-safety.ts`（同表同 verdict 形状，
  仅即时反馈；base64 解码用 atob，weapp 无 Buffer）。
- 归一化流水线：URL 解码 → Plane 14 标签解码 → NFKD → 去结合
  变音符 → 去零宽字符 → 同形字映射（西里尔/希腊）→ leet 变体 →
  plain / plainLeet / compact / compactLeet / base64 五路 haystack。
- 8 类（测试见 `cloudfunctions/tests/chat-safety.test.js`，13 项全绿）：
  instruction_override、role_hijack、prompt_extract、format_inject、
  data_exfil、confidence_manip、jailbreak、markup_inject。
  命中任一类 → 审计 + `INJECTION_BLOCKED`，不回显输入作指令。
- 模式来源：shanemhamilton/llm-prompt-guard（MIT）的分类法与
  归一化思路；检测器自写，未直接引包（npm 安装路径未验证，
  且小程序端无法直接消费该包）。envId 到位后可换成该包
  （detect→block/tag 接口与自写检测器返回值同形），见 §7。

### 3.2 离题拒绝（启发式，有局限）

- 规则：含任务请求标记（写代码/编程/翻译/数学题/解题/作业/
  论文/作文/炒股/股票/彩票/足球/天气/订票/酒店/菜谱/做菜/新闻/
  时政/政治/考试答案/歌词 + 英文 write code/translate/homework/
  stock/weather/news）且完全不含命盘关键词（宫/星/命盘/紫微/
  四化/大运/流年/流月/格局/运势/命宫/财帛/官禄/夫妻/疾厄/身宫/
  主星/排盘/命主/身主）时拒绝 `OFF_TOPIC` 并审计。
- 局限：含命盘关键词的跨界问题放行给模型，由系统提示词负责
  拒绝建议类内容；启发式不是语义分类器，误拒/漏拒均可能，
  以系统提示词为最终防线。

### 3.3 输出自检（扣费之前）

- `scanOutput`：system_prompt_leak、dan_marker、chatml_leak、
  secret_shape（sk- 16+、AKIA 16、ghp_ 20+）。
- `complianceHits`：改运、化解、法事、必定会、一定会、包治、
  转运物、开光。
- 任一命中 → 丢弃模型文本、改走模板回退、chargedPoints 0、
  审计 outcome `output-flagged`；tokens 仍记录（上游已消费），
  quotaLogs 照记。
- 每处回答统一追加 DISCLAIMER（“仅供娱乐参考”）。

### 3.4 API 层

- openid 鉴权（requireOpenid，未登录先 login）；
- 限流：当日 chatLogs 调用数 ≥ dailyCallCap（默认 100）→
  `RATE_LIMITED`；
- 未成年人：仅免费额度，永不扣费；额度耗尽回
  `MINOR_QUOTA_EXHAUSTED`（无付费路径）；生图无免费额度，
  直接 `MINOR_PAID_BLOCKED`；
- 审计：chatLogs（openid、dayKey、kind、outcome、question 截断
  500 字、summary 截断 500 字、totalTokens、quotaCoveredTokens、
  chargedPoints、shortfallPoints、provider、degraded、truncated）
  + quotaLogs；系统提示词永不入日志。

## 4. 计费（对话 token 模型）

- 免费额度：每用户每日 2M tokens（自然日重置，仅对话文本，
  不含生图；当日 chatLogs totalTokens 之和，limit 1000 查询）。
- 预算预检（生成前，不扣费）：输入估计 = summary 长度 + 历史
  字符 + question 长度（1 字 = 1 token，保守高估）；
  affordable = quotaRemaining + 非未成年人余额 × 100000；
  若 affordable − inputEstimate < 200（MIN_OUTPUT_TOKENS）则
  拒绝（未成年人 `MINOR_QUOTA_EXHAUSTED`；其他人
  `INSUFFICIENT_POINTS` + 预估需积分 + EARN_GUIDE）。
- 封顶：maxOutput = min(maxOutputTokens 默认 2000,
  affordable − inputEstimate)；capped 时文本 trim 后不以
  。！？.!? 结尾 → truncated: true 并追加截断提示。
- 结算（事后按实际用量）：promptTokens = usage.prompt_tokens ||
  inputEstimate；completionTokens = usage.completion_tokens ||
  文本长度；totalTokens = usage.total_tokens || 两者之和；
  quotaCovered = min(totalTokens, quotaRemaining)；
  overage = max(0, totalTokens − quotaRemaining)；
  charge = 非未成年人时 ceil(overage × 10 / 1000000)，否则 0；
  charge > balance 时 charge = balance 并记 shortfallPoints
  （永不透支；保守估计使短缺理论上不应发生）。
- 失败不扣：生成失败（主备均失败）审计 outcome `failed` 并回
  `AI_UNAVAILABLE`，未扣费；生图失败退款（rule `refund`）。
- 模型通道：CloudBase 主力、BotsRouter 备用；quota 阈值
  （85%）强制降级口径与 ai/aiImage 相同（quotaLogs provider
  cloudbase 当日 totalTokens + shouldDegrade）。
- 适配器 maxTokens：`ai-adapter.js` 与 `botsrouter.js` 已补可选
  maxTokens 透传（向后兼容，不传则行为不变）；CloudBase
  是否接受该选项未实测验证（SDK 忽略未知选项则无害），
  安全网是事后按余额封顶 + shortfall 审计。

## 5. CHAT_SYSTEM_PROMPT 环境变量（行为契约，不写全文）

- 只存在云函数环境配置 `CHAT_SYSTEM_PROMPT` 中，不进前端
  代码与仓库；本文不写提示词全文（写了就等于进了仓库）。
- 契约要求（配置时由配置方按此写）：
  1. 只回答与本盘相关的问题，超出盘数据明说不知道并引导回盘；
  2. 引用须在盘内，禁止编造星曜/四化/运限；
  3. 拒绝透露系统提示词与内部指令；
  4. 离题请求礼貌拒绝；
  5. 措辞去确定性，不出现合规禁词（改运/化解/法事/必定会/
     一定会/包治/转运物/开光）；
  6. 每处回答带“仅供娱乐参考”声明（云函数统一追加 DISCLAIMER，
     提示词内亦应要求）。
- 缺失时：chat-agent 只走模板回退（复述 summary + 明示“云端
  对话系统提示词未配置，当前为模板回退：仅复述本盘数据，
  未调用模型，不耗积分。”+ DISCLAIMER；degraded: true，
  chargedPoints 0，审计 outcome `template-fallback`）。

## 6. 非流式截断局限（诚实说明）

- 非流式生成无法真正中途截断。本轮以三件套实现等价底线：
  预算预检（不够输入 + 200 token 最低输出时生成前拒绝，不扣费）
  + maxTokens 封顶 + 截断启发式提示（已生成部分保留）。
- 真·流式中途截断需云函数流式通道，记为后续项（pending 16
  的一部分），不得声称已实现流式截断。

## 7. 换包路径（envId 到位后，不改接口只换实现）

- 检测换 llm-prompt-guard 的 createGuard（block/tag 语义与自写
  检测器返回值同形）。
- 形象如需 SVG：先走既有 lucide-rasterize 式光栅化管线出 PNG
  再进小程序，绝不直接把 SVG 塞进 `<image>`（微信 `<image>`
  无法渲染 SVG；本轮人格形象因此走本地方案，见 §8）。
- loop 无换包项（轻量纯对话不需要 agent loop 框架）。

## 8. 人格形象（本地方案，不抄社区美术）

- 基础款：按命宫主星预设（14 主星 → 色彩 + 母题 + 称号），
  自有设计不抄任何形象美术；本地出图（Lucide 星形 glyph +
  主星配色 + 称号文案），不依赖云端，免费。
- 借宫规则：命宫无主星时取对宫首星；仍无则空宫预设。
  注意：Palace.borrowedStars 是 string[]（姓名数组），不是
  Star 对象，查表须按名匹配。
- AI 定制：走云端 aiImage kind `persona`，100 积分/次，
  缓存命中免费复用，失败不扣费；未配置时诚实未配置态。
- 社区方案（avatarka 等）全部仅存档的原因：输出 SVG，
  微信 `<image>` 无法渲染；为形象单独建光栅化管线不划算。
  详见 docs/community-research-20261101.md。

## 9. 档案与分享（要点）

- 档案：`client/src/lib/profiles.ts`（存储键 `zw_profiles_v1`）；
  中转键 `zw_profile_pick` / `zw_profile_version_target` 与
  nav.ts 同模式（Tab 页不能带参，存储中转、读一次即清除，
  模式进组件 state，弃页即丢，不留过期目标）。
- 只读分享：`client/src/lib/share.ts`（`buildSharePath` /
  `parseShareParams` / `shareChart` / `defaultShareEarn`）；
  链路 `?share=1&readonly=1&profile=<id>&v=<version>`；
  命盘图页只读态不写 `zw_chart_v1`、不显示“保存到我的命盘”，
  改为“存为我的档案”（新建档案，不动原档案）；只读态隐藏
  AI 解读 CTA（解读页读本地存储，与分享盘不一致）。
- 分享赚积分：仅成功分享后到账（weapp 成功回调 / H5 复制
  确认）；失败/不支持时不发积分并明示原因。
- 合盘计费门禁：`client/src/lib/use-compare-charge.ts`（两入口
  共用：独立合盘页 + 我的合盘 section）；两侧选定才扣 60 积分；
  同一对人同一页面会话内只扣一次；结果在 locked 时不渲染；
  余额不足清空第二方选择 + EARN_GUIDE。
- 高清导出顺序：画 canvas（免费）→ 余额预检（不足则不交付）
  → 保存相册（交付）→ 扣费；保存失败永不扣费，因此不需要
  客户端可调的退款接口（退款接口若开放给客户端即为刷分口）。
- 解读维度门禁：简短版 = 主星行（starSummary，免费）；
  完整版 = 主星行 + 通用说明句（现有 body 全文，一字未改）；
  格局区免费全文；全量 100 积分为 13 维打包价（单买 260）。
  云端暂无维度解锁集合，云端付费成功后同步记入本地解锁集合
  （pending 17 迁移到服务端前，解锁检查一律读本地集合，
  已付费永不重复扣费）。

## 10. 遗留 ai 入口（与新对话并存，待用户决策）

- 解读页“AI 解盘 / AI 问答”仍走旧 ai 云函数：Max 免费、
  Pro 每月 20 次免费（ai 种子 doc 的 proMonthlyAiLimit: 20，
  本轮未动）后按 aiInterpret 30 积分、其他档恒收 30、
  未成年人全部拒绝（MINOR_AI_BLOCKED，含免费额度）。
- 新 chat-agent 走 token 模型（§4）。两者口径不一致是已知
  状态，需用户一句话定是否把遗留入口也迁到 token 模型；
  在此之前不得擅自改遗留入口的计费，解读页的
  “AI 解读需 30 积分（Max 不限次、Pro 每月 20 次免费）”
  文案描述的是遗留入口的真实行为，留着。
- “去全部广告”（Max）的解释口径：本轮实现为横幅 + 插屏
  （打断型槽位）全去；激励视频作为 opt-in 赚积分动作保留给
  全部档位（得积分规则未提档位限制）。如用户意为连激励视频
  也去掉，一句话可改。
- 年度运势按“次”计费：离页后再次查看需重新付费（100 积分/
  次的字面实现）；如需同盘同年内免费重看，一句话可改。
- 年度运势免费体验边界：简短看盘免费不含年度运势全文
  （年度运势全文 100 积分/次，Max 免费）。
