# 纠正轮（2026-11-01）：门户轮照抄的清理与首页重做

## 起因

门户轮（commit 81d853bc）把参照小程序（黄色主题占星小程序 7 张实拍）
的布局和全部功能清单整套搬进来了。用户纠正（2026-11-01 16:27，
最高优先级）：**参考不等于照抄**。功能一律以 GitHub 开源项目
Renhuai123/ziwei-doushu 为准，以 `~/workspace/ziwei-doushu-source`
的实际代码为准绳；参照小程序只借“门户式首页”这个抽象思路
（信息分层、核心功能前置这类通用做法），不许照搬它的版式顺序、
组件形态、功能清单、文案、配色。

## 源码功能清单（准绳，全部以源码实际代码核对）

- 排盘：`app/chart/page.tsx` + `components/BirthForm.tsx` +
  `lib/ziwei/algorithm.ts`（generateChart，真太阳时、中国 DST 1986–1991、
  时钟修正）。
- 命盘图：十四主星、辅星、煞星、四化、庙旺利陷、三方四正、格局
  （`lib/ziwei/patterns.ts`、`sihua.ts`、`components/ChartBoard.tsx`、
  `PatternsCard.tsx`、`StarDetailPanel.tsx`）。
- 运限：大运 / 流年 / 流月 / 流日 / 小限
  （`lib/ziwei/yunxian-context.ts`、`components/TimeNav.tsx`）。
- 星曜知识：`app/knowledge/[star]/[topic]`。
- 古籍原典库：`app/library/*` + `lib/classics`（未移植进小程序，
  不在本次删除范围）。
- 命例库：`lib/ziwei/famous.ts`（未移植进小程序，不在本次删除范围）。
- 合盘：`app/heming/page.tsx`（两张命盘对照）。
- AI 解读：`app/chart` 的 `InsightPanel.tsx` / `ChatPanel.tsx`
  （命格分析 + 六大维度 + 大限流年）；客户端 13 维为本地扩展。
- 分享：`components/ShareCardCanvas.tsx`、`ShareModal.tsx`、
  `lib/ziwei/share.ts`。
- 源码中**没有**的功能（全文 grep 核实）：今日运势评分、八字运势、
  星象日历 / 万年历 / 老黄历 / 星宿工具、许愿 / 祈福、星座骰子、
  塔罗、六爻工具、AI 解梦、MBTI、人格化 AI 占星师。
  （源码中“八字”仅指出生数据输入口径与倪师课程知识，“六爻”仅见于
  倪师课程知识库文本，均不是功能；“星宿”仅见于 lunar-javascript
  的 API 字段说明。）

## 去留表

| 模块 | 处置 | 依据 |
|---|---|---|
| 排盘表单 birth | 留 | 源码 BirthForm |
| 命盘图 chart（含连线与详情卡） | 留，不动 | 源码 chart + patterns + sihua + yunxian |
| 大运 / 流年 / 流月 / 流日 | 留 | 源码 yunxian-context + TimeNav |
| 星曜知识 knowledge | 留，不动 | 源码 knowledge/[star] |
| 合盘 compare | 留 | 源码 heming（两张盘对照） |
| 解读 interpret（13 维 + AI 按钮） | 留，不动（仅 import 改指一行，逻辑零动） | 源码 InsightPanel/ChatPanel；13 维为本地扩展 |
| 分享海报 poster（我的页内） | 留，不动 | 源码 ShareCardCanvas/ShareModal |
| 会员 / 积分 / 邀请 / 订单（我的页） | 留，不动 | 门户轮之前一期～三期已有 |
| 档案管理（已保存命盘，我的页） | 留，不动 | 门户轮之前三期历史功能 |
| 6 交互组件 + 演示页 demo | 留 | 门户轮之前已有 |
| 表单预览卡、悬浮底栏 | 留 | 产品化一轮 |
| 解读页今日运势配图 dailyImage | 留，不动 | 三期 AI 配图功能，与评分模块无关 |
| 今日运势评分 fortune.ts + fortune 页 | 删 | 源码无评分；圆环 + 四条组合照搬参照 |
| 八字运势 bazi | 删 | 源码无八字运势功能 |
| 星象日历 / 万年历 / 老黄历 / 星宿 calendar | 删 | 源码无 |
| 许愿 / 祈福 wish | 删 | 源码无 |
| 星座骰子 dice | 删 | 源码无（西洋占星非本项目） |
| 塔罗 tarot | 删 | 源码无 |
| 六爻 liuyao | 删 | 源码无六爻工具 |
| AI 解梦 dream | 删 | 源码无 |
| MBTI mbti | 删 | 源码无 |
| AI 占星师 astrologers + PERSONAS | 删 | 源码只有解读对话，无人格化占星师 |
| 门户趣味工具 tools.ts / tools-data.ts | 删 | 全部为门户轮新增 |
| 门户样式 portal.scss | 删 | 仅门户页样式，compare 未用其 class |
| 门户自检 portal-selfcheck.ts + package.json 脚本 | 删 | 仅校验已删内容 |
| 首页热门功能 / 三卡 / 六卡阵 / 报告列 / AI 占星师入口 | 删（形态），见新布局 | 参照的版式与功能清单 |
| 我的页星币 section | 删 | 仅门户轮新增，照搬参照我的页；积分体系本身保留 |
| 我的页报告记录 section | 删 | 仅门户轮新增，照搬参照我的页 |
| interpret 的 recordReport 调用 | 留（逻辑零动） | 写入 lib/reports.ts（新文件，原样移出）；我的页入口已删，暂无读取方，写入继续（本地数据，用户自有） |
| ?dim= 深链机制（interpret 内） | 留 | 新首页维度 chips 为新调用方；interpret 逻辑不动 |
| 11 个 Lucide 图标（dices/hand-heart/brain/gift/scroll/moon/heart/briefcase/graduation-cap/calendar/sparkles） | 删（SVG + PNG + 生成器列表） | 随删除的功能变死资产；生成器重跑后 43 图标 |
| 命盘图页注释中的参照表述 | 改 | 删“天象对应星象日历，见首页三卡”等残留表述 |
| 出生页 caption 中的“首页门户查看今日运势” | 改 | 已删模块的残留表述，改为命宫与今年运限 |
| 我的页 s6 pattern 注释 | 留 | 通用 pattern（去分割线大留白），内容为本站自有会员体系，非参照功能 |

## 新首页布局（自有版式）

只借通用做法（信息分层、核心功能前置），版式、组件形态、文案、
配色均为本站自有（Medley 为底 + Gemini 蓝 + Lucide）：

1. hero 文本区：品牌行 + 日期行（公历 + 农历）+ 大标题
   “你的命盘，一眼看懂” + 副标题（本地排盘，不走服务器）。
2. 命盘锚点深色卡（两态下的视觉锚点，Medley 深色欢迎卡 pattern）：
   命宫干支 + 命宫主星（含亮度与四化）+ 出生信息 + 格局（引擎
   detectPatterns，前两个）+ 双按钮（查看我的命盘 / 重新排盘）。
   无盘时为排盘 CTA（ComposerBar 开始排盘 + 查看上次命盘）。
3. 今年运限（双卡并排，无分数、无条形、无圆环）：
   今年流年卡（流年宫 + 主星 + 流年干四化）与本月流月卡
   （农历月 + 月干 + 流月四化），算法与命盘图页流年 / 流月卡
   完全一致（流年支 = 农历年 −4 取余；大限按年取段；流月按农历
   月序、月份天干五虎遁），点卡片到命盘图页；下方附所属大限与
   虚岁。无盘时为诚实空态卡。
4. 解读卡：13 维 chips（命宫 / 财帛 / 事业 / 感情 / 健康 / 子女 /
   手足 / 迁移 / 田宅 / 福德 / 父母 / 交友 / 身宫），点 chips 经
   goInterpret 直达解读页对应维度；无盘时为文字说明 + 去排盘。
5. 功能双 tiles：星曜知识（switchTab 知识页）与合盘对照
   （compare 页），均匀两格，无 HOT 角标。
6. 免责声明 + 流量主横幅（免费档）+ 悬浮圆角底栏（不变）。

亮色默认、深色保留切换；无盘态、亮 / 暗两态均重拍验证。

## 验收（实测结果，2026-11-01）

- tsc：干净（0 error；中途仅 interpret 的 lib/tools import 报错，
  随 reports.ts 移出解决）。
- weapp 构建：成功（exit 0；chunk 顺序警告与 vendors.js 834 KiB
  警告为既有项，与此前轮次一致）。
- 引擎 smoke：768 盘 0 失败（ENGINE SMOKE OK）。
- H5 构建：成功（exit 0；dist/js 258.js + app.js 与 spa-index.html
  引用一致），截图脚本 shot-correct.js 全过。
- 产品代码零残留 grep：禁用词（骰子 / 塔罗 / 六爻 / 解梦 / MBTI /
  许愿 / 祈福 / 万年历 / 老黄历 / 占星师 / 八字运势 / 星象日历 /
  热门功能 / 为你推荐）零命中；已删页面路径与 lib/tools /
  lib/fortune / portal.scss 零命中（lib/reports.ts 头注中提及
  tools.ts 一次，为去留说明本身）；“星宿”仅存 lunar-javascript.d.ts
  的第三方库 API 字段说明一行，非功能。
- 截图：shots-correct/（首页亮 / 暗 / 无盘、我的页亮 / 暗）；
  已删 fortune 路由实测不再渲染旧内容（false）。
- 轮中修 1 真 bug：深色卡上的次按钮在亮色主题下深色字不可见
  （btn-medley-outline-light），已单立白字描边 .home-ming-btn，
  重拍验过。
- OCR delegation 审查：preview 15 reviewable（14 本轮 + 1 他人
  docseek 文件，跳过并注明原因）；rule 取回 3 组；14 个本轮文件
  逐项审过 diff，结论：无 High/Critical、无 Medium；25 个删除文件
  与 44 个二进制图标文件在 excluded 中，与 grep 零残留 + 两次构建
  交叉验证一致；CORRECTION.md 属 unsupported_ext 文档，自审。
  审中注意到的两点均非问题：首页 render 内同步读本地存储与
  引擎纯计算，与命盘图 / 解读页既有模式一致；reports.ts 暂无读取方
  已在文档中明说（写入继续，本地数据）。轮中目视发现的深色卡次按钮
  不可见问题已修掉重拍（见上）。
- 本轮未动：logo、登录页、命盘图 / 解读 / 知识页系统、我的页
  会员 / 积分 / 邀请 / 订单 / 档案系统、v3 闭合项、产品化功能。
- 注意：工作树另有他人未提交改动
  （ziwei-xingpan/client/src/pages/auth/index.scss，新增
  auth-agreement / auth-legal-body 样式，非本轮改动，本轮提交已排除；
  居中修复本身已在 commit 6473c6fd9 中）。
