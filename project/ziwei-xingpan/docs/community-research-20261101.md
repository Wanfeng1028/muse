# 社区调研结论（2026-11-01）

> 任务：星命盘对话 agent + 多人档案 + 积分经济 + 海报分享 + 人格形象。
> 方法：全部搜索走用户 Keenable API；结论以“能否在微信云函数 / 小程序里
> 落地并可测试”为准。凡是“采用”的项，LICENSE 与来源一并记录；
> “仅存档”即不进代码、不进依赖。
>
> 口径纠正（2026-11-01 19:30 / 19:40 / 19:41，用户亲定）：
> 重 agent loop 砍掉，改轻量纯对话（每轮打包上下文 → 后端模型，
> 不做多步工具编排）；定价以纯积分制新表为准（1 元 = 50 积分；
> 档位免费 / Plus / Pro / Max；对话超额每百万 tokens 10 积分）。
> 下表 a1 的原“模式采用”结论随 loop 一并作废，改为仅存档。

## 结论总表

| # | 方向 | 候选 | 许可 | 结论 |
|---|---|---|---|---|
| a1 | agent loop（TS） | NarimanGardi/agent-loop（npm @narimangardi/agent-loop） | 仓库有 LICENSE 文件（类型未在摘要中确认） | **仅存档（19:30 纠正后）**：重 loop 已砍，改轻量纯对话，不做多步工具编排；该包的循环形状仅作背景参考，不进代码、不引 npm 包。原“模式采用”结论作废。 |
| a2 | agent loop（TS 教学实现） | teslalee-xometry/minimum_agent、miguelgarcia/agent-from-scratch | 未确认（教学项目） | 仅存档：两者都是教学演示，印证了 a1 的循环形状，无新增可抄代码。 |
| a3 | agent loop（重型） | huberp/agentloop（LangChain + MCP + 子代理编排） | 未确认 | 仅存档：编码代理取向、依赖重，不适合小程序云函数。 |
| b1 | 注入防御（TS，零依赖） | shanemhamilton/llm-prompt-guard | **MIT（已核实）** | **模式 + 分类法采用，检测器自写**：归一化流水线（NFKD、去零宽字符、Plane 14 标签解码、同形字映射、URL 解码、leet 映射、base64 片段解码）+ 8 类 56 模式（指令覆盖、角色劫持、提示词提取、格式注入、数据外泄、置信操纵、越狱、标记注入）+ 输出层扫描（提示词外泄标记、PII 形状、DAN 标记）。**不直接引包**：npm 安装路径未验证，且小程序端无法直接消费该包；云函数与客户端各一份同表检测器，另有节点单测 + 奇偶校验文档。envId 到位后可换成该包（detect→block/tag 接口同形）。 |
| b2 | 注入防御（云服务） | arcjet/arcjet-js（@arcjet/guard）、joergmichno/clawguard-shield-js | 未确认（两者均需外部 API key） | 仅存档：检测能力依赖外部服务与 key，不符合“云函数内闭环 + 不新增外部账号”的约束。 |
| c1 | 海报分享 | 微信官方 API：cloud.openapi.wxacode.get（小程序码）、canvasToTempFilePath、saveImageToPhotosAlbum、shareAppMessage | 微信平台 API（非社区代码） | **采用（平台 API，无需抄代码）**：社区教程（mo4tech、shulou）印证的标准流程与本项目既有 PosterCard（canvas + 保存相册）一致。本轮补齐：微信分享（shareAppMessage + H5 回退复制链接）与只读分享链路（?readonly=1 + 档案内查看，不改原盘）。小程序码仍走既有 invite 云函数（未配置时诚实占位）。 |
| d1 | 人格形象（SVG 生成） | AndreyAkinshin/avatarka（确定性 SVG 身份，8 主题） | **MIT（已核实）** | 仅存档：全部输出 SVG，而微信 `<image>` 无法渲染 SVG（本项目图标管线为此才做光栅化）；为形象单独建光栅化管线不划算。 |
| d2 | 人格形象（SVG 生成） | Chrisss666/avatarGenerator（零依赖单文件）、draftbit/avatar-generator（Personas） | avatarGenerator 许可未确认；Personas 未确认 | 仅存档：同 d1 的 SVG 原因；且 avatarGenerator 许可未核实，不引入。 |
| d3 | 人格形象（本地方案） | 按命宫主星预设（14 主星 → 色彩 + 母题 + 称号） | 自有设计（不抄任何形象美术） | **采用**：基础款本地出图（Lucide 星形 glyph + 主星配色 + 称号文案），不依赖云端；AI 定制形象走云端 aiImage（未配置时诚实未配置态，100 积分/次）。 |

## 本轮实际“抄”的东西

- 轻量纯对话的上下文打包形状（系统提示词 + 本盘关键数据摘要 +
  会话历史近 N 轮截断 + 用户问题 → 后端模型，返回文本或生图；
  不做多步工具编排。a1 的 loop 形状仅作背景参考，不进代码）。
- 注入防御的归一化流水线步骤与 8 类分类法（b1 文档，见
  cloudfunctions/_shared/chat-safety.js 与 client/src/lib/chat-safety.ts 注释）。
- 海报分享的平台 API 流程（c1，微信官方接口；教程仅作流程印证，不抄代码）。
- 其余方向无可直接引入的代码：凡是需要 npm 安装或外部 key 的候选，
  均因“本机无法验证安装、云端未到位无法联调”而降为模式/存档，
  并在下方“换包路径”中写明 envId 到位后的替换方式。

## 换包路径（envId 到位后，不改接口只换实现）

- 检测：把 chat-safety.js 换成 llm-prompt-guard 的 createGuard
 （block/tag 语义与本轮自写检测器的返回值同形）。
- 形象：如需 SVG 形象，先走既有 lucide-rasterize 式光栅化管线出 PNG
  再进小程序，绝不直接把 SVG 塞进 `<image>`。
- loop：无换包项（19:30 纠正后重 loop 已砍；如未来需要多步编排，
  再评估 a1 的 @narimangardi/agent-loop）。

## 合规红线（本轮不变）

- 不照抄 14:44 参照小程序的功能、版式与文案（2026-11-01 16:27 铁律）；
  本轮新增页面（档案/对话/人格）均为自有版式。
- UI 图标只用 Lucide（既有 43 glyph，不新增）；品牌标只走 vendor-logos
  （本轮未新增品牌标）。
- 系统提示词只存在云函数环境配置 CHAT_SYSTEM_PROMPT 中，不进
  客户端代码与仓库；云函数缺该变量时返回诚实未配置态，不编造回答。
- 产品名一律“星命盘”；紫微斗数体系名不动；logo 文件不动。
