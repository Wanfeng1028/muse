# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，
版本号使用项目内版本（`v2.x`）。

## [Unreleased]

### Added（5.3 路 2026-10-26：运行页设计层 v2）
- 新增 static/runs-design-v2.css（模型稿 2 条规则原文入仓，runs.html 在 v1 之后引用 1 行）：关闭运行页 v1 未覆盖的 3 处行内样式——两处错误提示图标尺寸与空态内边距。JS 机械迁移（编排落仓，非模型稿）：直接删 3 处行内 style 属性、不加新类（图标规则以 .error-box svg 为目标，lucide 会把 i 换成 svg；空态规则以 #planArea .empty 为目标、用特异度压住 harness.css 全局 .empty{padding:48px 20px}）；#planArea 容器自身的 margin-top:16px 行内样式与本轮无关，不碰；v1 已有的 .error-box 字号圆角与 .state-empty 不重复写。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r21_call.py、令牌经 SSH 现取不落盘、钉死 UserKnownHostsFile=/home/hatch/.ssh/known_hosts、未读任何现成调用脚本）1 通产出：API prompt 24003 / completion 541 / total 24544，reasoning_tokens 0，正文即入仓 2 条规则，零编排修正。括号 2/2 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无十六进制颜色字面量，原值（15px/15px/-2px/24px）逐字保留。
- 验收：新增 RunsDesignV2Test 4 例全绿，设计层合跑 104/104 全绿（隔离构建；含他路未提交的 skills v3 测试 3 例与 run-detail v2 测试 3 例，本轮不提交他路文件），Maven 离线 BUILD SUCCESS；隔离构建真实服务（18206 端口，复制 H2 库，开放模式）实测：runs.html 与 runs-design-v2.css 均 200、served 内容与文件对上；/api/runs 真实 3 条（AI MV 冒烟测试主题失败、取消测试已取消、验证用短剧失败）与列表对上；计算样式实证：注入节点测得 #planArea .empty padding=24px（压住 harness 全局 48px 20px）、.error-box svg 15px/15px/-2px，注入后即删、截图仍为真实态；视口截图亲眼核对布局撑满、无错位重叠、零 console 错误；另有 1 条 pageerror（setContent 下 document.write SyntaxError，与音乐页同款 harness 环境 artifact，不影响内容与样式）。截图存 docs/screenshots/runs-design-v2.png。验收后服务按真实 java PID 28440 停干净、18206 端口已关、隔离构建与复制库已删。如实保留：截图统计条写总运行数 2、列表却有 3 条，属既有统计口径缺口、非本层所致，本轮不扩范围修统计。

### Added（5.3 路 2026-10-26：成本账本页设计层 v2）
- 新增 static/cost-ledger-design-v2.css（模型稿 1 条规则原文入仓，cost-ledger.html 在 v1 之后引用 1 行）：关闭上一位留下的 v2 候选——cost-ledger.js 里 4 处行内 style="font-variant-numeric: tabular-nums;"（供应商明细金额 span、最近明细表时间/预估/实际 3 个 td）改由 CSS 接管。JS 机械迁移（编排落仓，非模型稿）：4 处统一挂 cl-num 类、删行内样式；动态进度条宽度（数据驱动）仍留行内；页内 inline style 块的 .kpi-value 等宽规则与本层无关，不碰。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r21_call.py、令牌经 SSH 现取不落盘、钉死 UserKnownHostsFile=/home/hatch/.ssh/known_hosts、未读任何现成调用脚本）1 通产出：API prompt 23902 / completion 76 / total 23978，reasoning_tokens 0，正文即入仓 1 条规则，零编排修正。括号 1/1 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无十六进制颜色字面量，选择器 .cl-num 为本轮新增、无冲突。
- 验收：新增 CostLedgerDesignV2Test 4 例全绿，设计层合跑 97/97 全绿（隔离构建；含他路未提交的 skills v3 测试 3 例，本轮不提交他路文件），Maven 离线 BUILD SUCCESS；隔离构建真实服务（18205 端口，复制 H2 库，开放模式，启动约 50 秒）实测：cost-ledger.html 与 cost-ledger-design-v2.css 均 200、served 内容与文件对上；/api/cost-ledger/entries 真实 1 条（2026-10-20 mock video-generate 已完成）与最近明细表对上；计算样式实证 3 个 td.cl-num 全部 font-variant-numeric=tabular-nums；供应商明细今日真实空态（“今天还没有供应商产生花费”，库内无今日行），同规则以注入节点实测 tabular-nums、注入后即删、截图仍为真实空态；视口截图亲眼核对布局撑满、无错位重叠、零 console 错误；另有 1 条 pageerror（setContent 下 document.write SyntaxError，与音乐页同款 harness 环境 artifact，内联脚本中无 document.write 调用，不影响内容与样式）。截图存 docs/screenshots/cost-ledger-design-v2.png。验收后服务按真实 java PID 24422 停干净、18205 端口已关、隔离构建与复制库已删。

### Added（5.3 路 2026-10-26：任务队列页设计层 v2）
- 新增 static/tasks-design-v2.css（模型稿 12 条规则原文入仓，分 4 通、每通 3 条规则，tasks.html 在 v1 之后引用 1 行）：关闭 v1 已知保留——任务行底线、任务名与元数据字号颜色、进度条宽高、百分比字号颜色改由 CSS 接管，不再由行内样式写死。JS 机械迁移（编排落仓，非模型稿）：任务行渲染的行内 style 赋值全部改挂 task-row/task-top/task-left/task-status/task-name/task-progress-wrap/task-progress/task-pct/task-link/task-retry/task-meta/task-error 类；动态进度条宽度（数据驱动）与显隐切换仍留行内；v1 已有的进度条底色与圆角不重复写；百分比等宽字体由原字体栈改用 var(--mono) token；错误行颜色 var(--danger, #b0453f) 为原值逐字保留。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r19_20261026_call.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）4 通产出：API prompt 合计 96250 / completion 合计 476 / total 96726，reasoning_tokens 0，正文即入仓 12 条规则，零编排修正。括号 12/12 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体，选择器均以 #taskGrid 开头且真实存在于本页 DOM。
- 验收：新增 TasksDesignV2Test 3 例 + 设计层合跑 81/81 全绿（隔离构建），Maven 离线 BUILD SUCCESS；隔离构建真实服务（18204 端口，复制 H2 库，开放模式）+ 视口截图亲眼核对：项目/剧集/分镜下拉与 /api/projects、/api/episodes、/api/shots 对上（都市奇缘/第 1 集/镜号 1·中景）；任务行 1 条（任务 #1 已完成 100%）与 /api/shots/1/video-tasks 对上；计算样式实证页头 20/700、行底线 1px solid（浅色主题下计算色 rgb(255,255,255)，即 --surface 解析值）、任务名 14px、百分比 12px 等宽（样式表扫描证实唯一生效规则即 v2 的 var(--mono)，浅色主题下解析为 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace）、辅助信息 12px、进度条 120×4px、操作链接 13px 墨色（--accent 浅色值 #111111）、零 console 错误；截图存 docs/screenshots/tasks-design-v2.png。验收后服务按真实 java PID 停干净、18204 端口已关、隔离构建与复制库已删。
- 插曲（均据实记录）：①首轮合跑 TasksDesignV2Test 1 例失败：编排漏给 statusWrap 加 task-status 类（只删了行内样式），补类后单测与全量合跑均绿；②百分比计算字体栈初看与 --mono 深色默认值不符，经样式表扫描证实唯一生效规则即 v2 的 var(--mono)，浅色主题解析值即所见栈，非回归；③打包/测试撞车时走隔离构建，不要碰仓库 target/。
- 已知保留：本层不改布局；进度条动态宽度仍由行内 style 写（数据驱动）；本轮未动 canvas、deconstruct、chat、second-brain、docseek、linkshort、botstalk 在跑工人的未提交文件。

### Fixed（Flash 路 2026-10-26：Agent 机队页副标题计数纠错）
- 副标题由“管理 5 个专用 Agent 的提示词与模型”改为“管理 7 个专用 Agent 的提示词与模型”，同步改 agents.js 的 i18n 文案（中文同款、英文由 the 5 dedicated Agents 改为 the 7 dedicated Agents）；关闭 DESIGN_SYSTEM §19 已知保留的“页内文案与实际数据不一致”问题。计数实证：后端 AgentType 枚举共 7 项（编剧/分镜/视频生成/剪辑/质检/作词/作曲），与 v1 截图时的 7 条数据一致，5 是旧数。
- 新增 AgentsSubtitleCountTest 1 例：断言 agents.html 副标题数字等于 AgentType.values().length，且 agents.js 中英文案同数——枚举再增减时测试即报错，不再靠肉眼对数。
- 本轮为 3 行文案机械纠错，未走模型调用（额度消耗只计第 1 轮两通）；验收：新测 1/1 全绿，设计层合跑 91/91 全绿（含他路未提交的 tasks v2 测试 3 例，本轮不提交他路文件），Maven 离线 BUILD SUCCESS；内联截图亲眼核对副标题已是“管理 7 个专用 Agent 的提示词与模型”、零 console 错误，截图存 docs/screenshots/agents-subtitle-count.png（网格加载态是剥离脚本后的静态空态，非本轮问题）。
- 如实保留：复制库上的真实服务 /api/agents 回 409（未找到 LYRICS 的 Prompt 模板，库内模板仅 5 条），属既有种子缺口，本轮未扩范围补种子；故在线条数未以该接口实测，计数证据为枚举源码 + 单测 + 静态副标题截图三方一致。

### Added（Flash 路 2026-10-26：设置中心页设计层 v2）
- 新增 static/settings-design-v2.css（1 条规则，只覆盖 #settings-retry，不改 app.css/harness.css 与 v1 文件；settings.html 在 v1 之后引用 1 行）：关闭 v1 已知保留“重试按钮 #settings-retry 未入本层”——重试钮与保存钮同口径（13px/600、8px 圆角、8px 16px 内边距、1.4 行高），底色 var(--surface)、边框 1px solid var(--border)、文字 var(--text)，与成片质检页通过/打回次按钮同款；hover/focus/active 沿用 app.css 次按钮原样式，本层不碰；布局与定位一字不改。
- 模型稿由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 32000，新提示词，调用器为本轮现写最小新文件 relay-station/flash_call_n4.py、令牌经 SSH 现取不落盘、钉死 UserKnownHostsFile=/home/hatch/.ssh/known_hosts、未读任何现成调用脚本）产出：首通正文 0 字（API prompt 24086 / completion 1790 / total 25876，推理占大头未出正文，作废，按规不原样重发）；换新提示词（首行改写为 Do not reason、直接输出）第 2 通 1 通可用（API prompt 23862 / completion 1535 / total 25397，reasoning_tokens 0，无 429），正文即 1 条规则；编排修正 1 处（模型稿漏了 padding 与 line-height，按 v1 主按钮口径补 8px 16px 与 1.4，已如实注明）。括号 1/1 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无十六进制色，边框为 1px solid var(--border) 完整形式。
- 验收：新增 SettingsDesignV2Test 3 例全绿，设计层合跑 87/87 全绿（合跑含他路未提交的 skills v2 测试 3 例，本轮不提交他路文件），Maven 离线 BUILD SUCCESS；内联截图 + 计算样式亲眼核对：重试钮 13px/600、8px 圆角、白底、1px 发丝边、#111 文字、8px 16px 内边距、行高 18.2px（=13×1.4）、零 console 错误；截图存 docs/screenshots/settings-design-v2.png（harness 侧取消 error 容器隐藏以便实测，页面代码一字未动；加载态与空态同框是剥离脚本后的静态空态，非设计层问题）；隔离构建真实服务（18204 端口，复制 H2 库，开放模式，启动 137.7 秒）实测：settings.html 与 settings-design-v2.css 均 200，served 页内引用与层文件内容对上；验收后服务按真实 java PID 停干净、端口已关、隔离构建与复制库已删。
- 已知保留：本层不改布局；重试钮 hover/focus/active 沿用 app.css 次按钮原样式；本轮未动 skills v2、second-brain、docseek eval 在跑工人的未提交文件。

### Added（5.3 路 2026-10-26：Skill 市场页设计层 v2）
- 新增 static/skills-design-v2.css（模型稿 2 条规则原文入仓，skills.html 在 v1 之后引用 1 行）：关闭 v1 已知保留——已安装行底线由行内 !important 改由 CSS 接管；行间 1px solid var(--border-soft)、末行去底线。JS 机械迁移（编排落仓，非模型稿）：已安装行类名加 installed-row、删行内 style；实测发现 tabler 的 .border-bottom utility 自带 !important 会压住层规则（首拍末行仍有 1px 实线），故行类名同时去掉 border-bottom utility（py-2 与 flex 布局类保留），边线改由 v2 CSS 全权接管。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r19_20261026_call.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 24056 / completion 97 / total 24153，reasoning_tokens 0，正文即入仓 2 条规则，零编排修正。括号 2/2 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无十六进制颜色字面量，选择器均真实存在于本页 DOM。
- 验收：新增 SkillsDesignV2Test 3 例 + 设计层合跑 78/78 全绿（隔离构建），Maven 离线 BUILD SUCCESS；隔离构建真实服务（18203 端口，复制 H2 库，开放模式）+ 视口截图亲眼核对：市场 4 卡（短剧钩子开头/分镜大师/转场设计/爽点节奏）与 /api/skills 对上；已安装 2 行（验收库内现装分镜大师后复测）与 /api/skills/installed 对上；计算样式实证页头 20/700、市场卡 10px 圆角、首行底线 1px solid（浅色主题下计算色 rgba(0,0,0,0.06)，即 --border-soft 解析值）、末行 0px none、零 console 错误；截图存 docs/screenshots/skills-design-v2.png。验收后服务按真实 java PID 停干净、18203 端口已关、隔离构建与复制库已删。
- 插曲（均据实记录）：①18202 端口已被他路 canvas 服务占用（实测为他路 java 进程在听，未动），改用 18203；②首轮测试合跑进程中途消失（日志停在 testCompile，疑似 VM 争用），重跑后全绿；③SSH 令牌抓取首通因出口代理瞬时抖动报连接错，直接 SSH 复测即通，调用器已加令牌抓取 3 次重试。
- 已知保留：本层不改布局；详情弹窗模板 pre 的边线仍由 skills.js 另一处行内 !important 写死（与已安装行不同源），不在本轮范围；本轮未动 canvas、deconstruct、chat、second-brain、docseek、linkshort、botstalk 在跑工人的未提交文件。

### Added（Flash 路 2026-10-26：分镜画布页设计层 v1）
- 新增 static/canvas-design-v1.css（6 条规则，只覆盖，不改 app.css、内联 style 块与任何 JS；canvas.html 在内联 style 块之后引用 1 行）：本层只覆盖尚未统一口径的页面外框——页头 h1 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、卡片内副文案 13px 次文字、页头操作按钮 13px/600 8px 圆角（不改颜色）、工具栏下拉框 14px（不改内联已定的最小/最大宽度与布局）；时间轴、镜头卡片、弹窗、提示条等内联已覆盖的组件本层一字不碰；token 全部取自 app.css，全部边框均写成 1px solid var(--border) 完整形式。
- 模型稿由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 32000，新提示词，调用器沿用本轮现写最小新文件 relay-station/flash_call_n3.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 26544 / completion 2033 / total 28577，reasoning_tokens 0，无 429，正文即入仓的 6 条规则，零编排修正。括号 6/6 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter，全部选择器均真实存在于本页 HTML，禁区选择器（时间轴/镜头卡片/弹窗/提示条等）一条未犯。
- 验收：新增 CanvasDesignV1Test 3 例全绿，设计层合跑 74/74 全绿，Maven 离线 BUILD SUCCESS；内联截图 + 计算样式亲眼核对：页头 20/700、卡片白底 1px 边 10px 圆角零阴影、卡片标题 16/700、副文案 13px 次文字、页头按钮 13/600 8px 圆角、工具栏下拉 14px、零 console 错误，布局（页头 flex、工具栏 flex、镜头网格）原样未动；隔离构建真实服务（18202 端口，复制 H2 库，开放模式，启动 124 秒）实测：canvas.html 与 canvas-design-v1.css 均 200，served 页内引用与层文件内容对上；截图存 docs/screenshots/canvas-design-v1.png（时间轴与镜头网格为空是无 JS 数据的真实空态）。插曲：首起服务在 exec 会话中断时被连带杀掉（日志停在启动初期），改走 setsid nohup 脱离会话重起后正常；验收后服务按真实 java PID 停干净、端口已关、隔离构建与复制库已删。
- 已知保留：本层不改布局；镜头卡片、时间轴、弹窗、提示条沿用页内内联样式，本层不覆盖；agent-canvas 组件内部不动。

### Added（5.3 路 2026-10-26：视频拆解页设计层 v1）
- 新增 static/deconstruct-design-v1.css（14 条规则，只覆盖，不改 app.css、内联 style 块与任何 JS；deconstruct.html 在内联 style 块之后引用 1 行）：视觉逻辑“拆解台账”——眉标 11px/600 次文字、页头标题 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、表单标签 12px/600 次文字、下拉与输入框 13px 8px 圆角、按钮 13px/600 8px 圆角（主按钮沿用 app.css 胶囊形，见保留）、空态 13px 次文字、详情小节标题 14px/700、时间线条 1px 发丝边 8px 圆角、逐镜帧 8px 圆角、元数据 12px 次文字、提示词块 12px 等宽 surface-2 底 8px 圆角；token 全部取自 app.css（边框一律 1px solid var(--border) 完整形式）。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r18_call.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 24341（含上游缓存 24320）/ completion 2483 / total 26824，reasoning_tokens 0，正文即入仓的 14 条规则；编排修正 2 处：提示词块字体由通用 monospace 改为 var(--mono) token；眉标选择器由 .dc-kicker 提为 .page-head .dc-kicker（app.css 的 .page-head p 特异度更高，原稿 11px 被压回 12px，提后实测 11px/600/次文字色）。括号 14/14 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML。
- 验收：新增 DeconstructDesignV1Test 3 例全绿，设计层合跑 78/78 全绿（隔离构建，含本页 3 例），Maven 离线 BUILD SUCCESS；隔离构建真实服务（18199 端口，复制 H2 库，开放模式）+ 视口截图亲眼核对：计算样式实证页头 20/700、眉标 11/600、副标题 13px、卡片深色 surface 底 1px 边 10px 圆角、卡片标题 16/700、表单标签 12/600、下拉 13px 8px 圆角、主按钮 13px/500/999px（app.css 胶囊形，保留）、非主按钮 13px/600/8px、空态 13px 且真实可见（项目 6 个选项）、小节标题 14/700、时间线 1px 边 8px 圆角、提示词块 12px 等宽；逐镜帧 8px 与元数据 12px 为 harness 注入测量（空态无真实 DOM，注入后即删，截图仍为真实空态）；截图存 docs/screenshots/deconstruct-design-v1.png。验收后服务按真实 java PID 停干净、18199 端口已关、隔离构建与复制库已删。
- 已知保留：本层不改布局；主按钮胶囊形为 app.css 产品按钮语言，本层不压；逐镜帧与元数据空态无真实 DOM，见上；截图 harness 说明：deconstruct.js 的 api() 会给相对路径补 /api/projects/ 前缀，通用 /api/ 绝对化改写会把绝对路径调用拼成双段 URL（已改 harness 为只改写 api() 的 URL 构造行，脚本存 muse-build/shot/drama-deconstruct-shot.js）；setContent 下 about:blank 无 localStorage，页内主题脚本读 localStorage 抛 SecurityError 一条，属 harness 环境 artifact；本轮未动 canvas、chat、finals、second-brain、docseek、linkshort 在跑工人的未提交文件。

### Added（Flash 路 2026-10-26：AI 对话页设计层 v1）
- 新增 static/chat-design-v1.css（10 条规则，只覆盖，不改 app.css 与任何 JS；chat.html 在 app.css 之后引用 1 行）：视觉逻辑“对话台账”——页头 h1 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、表单标签 12px/600 次文字、下拉框 14px 8px 圆角、对话区 surface-2 底发丝边 8px 圆角、快捷提问 13px/600、费用提示 12px 弱文字、提示框 surface 底发丝边 10px 圆角；token 全部取自 app.css（本页不引 harness.css/auth.css）。
- 模型稿由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 32000，新提示词，调用器为本轮现写最小新文件 relay-station/flash_call_n3.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 24831 / completion 3314 / total 28145，reasoning_tokens 0，无 429，正文即入仓的 10 条规则，零编排修正。括号 10/10 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter，全部选择器均真实存在于本页 HTML，全部边框均写成 1px solid var(--border) 或 1px solid var(--border-soft) 完整形式。插曲：首通令牌 SSH 取数报 host key 校验失败（子 agent 以 root 身份跑、ssh 默认读 /root/.ssh/known_hosts 的过期条目），显式指定 UserKnownHostsFile=/home/hatch/.ssh/known_hosts 后恢复。
- 验收：新增 ChatDesignV1Test 3 例全绿，设计层合跑 71/71 全绿，Maven 离线 BUILD SUCCESS；隔离构建（源码拷到 relay-station 单独打包，避开他路在跑的仓库 target/）+ 复制 H2 库起真实服务（18201 端口，开放模式，启动 281 秒）实测：chat.html 与 chat-design-v1.css 均 200， served 页内引用与层文件内容对上；内联截图 + 计算样式亲眼核对：页头 20/700、卡片白底 1px 边 10px 圆角零阴影、标签 12/600 #555、下拉 14px 8px 圆角、对话区 #f4f4f5 底 1px 边 8px 圆角、快捷提问 13/600、费用提示 12px #999、提示框白底 1px 边 10px 圆角；截图存 docs/screenshots/chat-design-v1.png（下拉与对话区为空是无 JS 数据的真实空态；内联截图 1 条 favicon file:// 报错是 harness 剥离脚本所致，真页可正常加载 favicon）。验收后服务按真实 java PID 停干净、端口已关、隔离构建与复制库已删。
- 已知保留：本层不改布局；输入区定位与发送钮沿用 app.css 原样式，本层不重复覆盖；对话区原有最小/最大高度逻辑不动。

### Added（5.3 路 2026-10-26：成片库页设计层 v2）
- 新增 static/finals-design-v2.css（13 条规则，只覆盖，不改 app.css/harness.css 与 v1 文件；finals.html 在 v1 之后引用 1 行）：关闭 v1 已知保留“成片卡片本体沿用原样式”——卡片本体本是 finals.js 内联样式，覆盖层压不住，故本轮把卡片内联样式原样平移到 v2（数值逐字照搬，不 redesign、不改布局）：卡片 880px 宽弹性纵列、首末边线改由兄弟选择器与 :last-child 表达（与旧 idx 逻辑逐项等价：单张仅下边线、多张中间张有上边线、末张加下边线）、海报盒 400px 16/9 10px 圆角、正文区弹性列、标题 18px/600、元信息 13px 次文字、分隔点弱文字、说明 13px 次文字、操作行 16px 间距、操作控件 15px、播放视频黑底；JS 侧同步机械迁移（cssText 全部删除、改挂 final-poster/final-body/final-title/final-meta/final-sep/final-note/final-actions 类，卡片 article 与海报图、视频沿用结构选择器，btn-quiet 类保留），行为与渲染数值不变。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器沿用本轮现写最小新文件 relay-station/glm53_r17_call.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）5 通输出：API prompt 合计 120241 / completion 合计 1102 / total 121343，reasoning_tokens 0，正文即入仓的 13 条规则，零编排修正。括号 13/13 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji；两处十六进制色（海报盒 #211d1b、视频 #000）为旧内联原值逐字保留，非新选色，已如实注明。JS 迁移与测试文件由编排机械落仓（非模型稿）。
- 验收：新增 FinalsDesignV2Test 4 例，与成片 v1、图片 v1/v2 合跑 13/13 全绿，Maven 离线 BUILD SUCCESS；真实服务（18200 端口，复制 H2 库，开放模式）+ 内联截图亲眼核对：单张卡片首无上边线、末有下边线，海报盒 400px 16/9 10px 圆角 #211d1b，标题 18px/600，元信息 13px #555，分隔点 #999，操作行 16px 间距 12px 上内边距，操作控件 15px，零 console 错误；成片数据与库内记录对上（都市奇缘/重逢/第 1 集成片 0:09 已完成 待质检）；海报图因库内无 poster.jpg 触发原有 error 隐藏逻辑、显示海报盒深底（旧行为，非回归）；READY 卡无说明段落、多张卡片场景库内无数据，说明规则与第二张卡片上边线以 harness 注入节点实测补齐（说明 13px #555 下边距 8px、第二张上边线 1px、首张上边线 0px、末张下边线 1px）；截图存 docs/screenshots/finals-design-v2.png。验收后服务按 PID 停干净、端口已关、复制库与验收 jar 已删。
- 插曲（据实记录）：①截图首跑因脚本切到无剧集的项目导致等待超时，已改为利用页面自动首选加载（首个项目+首个剧集自动出卡）；②SSH 令牌抓取曾因 root 上下文读了 /root/.ssh/known_hosts 而校验失败，钉死 /home/hatch/.ssh/known_hosts 受信文件后恢复（未绕过校验，密钥指纹与服务端一致）；③API 曾回一次 500，按规等 90 秒重试成功；④本轮打包改走项目副本隔离（主树 target 曾被他路测试占用），验收 jar 复制到验收目录防覆盖。

### Added（5.3 路 2026-10-26：AI 音乐页设计层 v1）
- 新增 static/music-design-v1.css（13 条规则，只覆盖，不改 app.css/harness.css、内联 style 块与任何 JS；music.html 在内联 style 块之后引用 1 行）：视觉逻辑“音乐台账”——页头标题 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、表单标签 12px/600 次文字、输入框与下拉与多行框 13px 8px 圆角、模式分段按钮 13px、生成按钮 13px/600 8px 圆角（不改颜色）、提示 13px 次文字、BYOK 空盒 1px 虚线发丝边 8px 圆角、生成区上下 1px 发丝线；token 全部取自 app.css/harness.css 与本页内联块（边框一律 1px solid/dashed var(--border)）。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，纯 CSS 短提示词，max_tokens 4000）1 通入仓（API prompt 24474（含上游缓存 23744）/ completion 3699 / total 28173，正文 1061 字即 13 条规则，单围栏、零编排修正，括号 13/13 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML，全部边框均写成 1px solid/dashed var(--border) 完整形式）；测试文件 MusicDesignV1Test 由编排按 Settings 模式机械落仓（引用顺序断言含内联 style 块之后）。
- 验收：新增 MusicDesignV1Test 3 例全绿，设计层合跑 65/65 全绿，Maven 离线 BUILD SUCCESS；真实服务（18197 端口，复制 H2 库，开放模式）+ 视口截图亲眼核对：计算样式实证页头 20/700、副标题 13px #555、卡片白底 1px 边 10px 圆角、卡片标题 16/700、表单标签 12/600、输入框 13px 8px 圆角、生成按钮 13/600/8px、提示 13px、BYOK 空盒 1px 虚线边 8px 圆角、生成区上下 1px 发丝线；MUSIC 模型列表实测 []，截图中空模型提示与禁用态生成按钮为真实空态；截图存 docs/screenshots/music-design-v1.png。验收后服务按 PID 停干净、18197 端口已关、复制库与验收 jar 已删。
- 已知保留：本层不改布局；复选行 13px 未压成 12/600；模式分段激活态沿用内联 --ink 黑底；内联 padding 的卡片内层 div 不碰；截图 harness 说明：本页在 setContent 抓屏下文档 scrollHeight 约 75909px（去本层复测同样 75909px，属既有渲染 quirks、非本层所致），整页截图会把目标撑爆（首轮 fullPage 超时、次轮 Target crashed），故改用 1440x900 视口截图，表单全部内容均在首屏内；另有 1 条 console 错误（document.write 相关 SyntaxError，内联脚本中无 document.write 调用、来源未定位，不影响内容与样式）；打包插曲：共享 target 下的 jar 曾被他路构建截断为 18MB 残片致 repackage 两连败，删残片重打后 207MB 正常，验收 jar 复制到验收目录防覆盖；page.goto 直连 127.0.0.1 仍被 Local Network Access 拦截（符合既往结论），未绕过；本轮未动 chat、finals v2、second-brain、docseek eval 在跑工人的未提交文件。


### Added（Flash 路 2026-10-26：注册页设计层 v1）
- 新增 static/register-design-v1.css（12 条规则，只覆盖，不改 app.css/auth.css 与任何 JS；register.html 在 auth.css 之后引用 1 行）：视觉逻辑“注册台账”——页头 20px/700、副标题 13px 次文字、分段器 surface-2 底发丝边 8px 圆角、签页 13px/600（当前签页 surface 底发丝边，与登录页一致）、录入行 surface 底发丝边 8px 圆角、输入框 13px、密码提示 12px 弱文字、错误提示 13px 红色、主按钮 13px/600 8px 圆角、协议行 12px 弱文字；token 全部取自 app.css/auth.css。
- 模型稿由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 32000，新提示词，调用器沿用本轮现写最小新文件 relay-station/flash_call_n2.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 24762 / completion 6888 / total 31650，reasoning_tokens 0，无 429；编排修正 4 处（均与登录页口径对齐）：删模型稿给页头加的带边卡片框（登录页页头不装框）；当前签页由 accent 反白改回 surface 底发丝边（与登录页一致）；输入框删内层边框（录入行已有边框，防双线）；未选中签页颜色由 text-2 改 text-3（与登录页一致）。括号 12/12 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter，全部选择器均真实存在于本页 HTML 且均带 .auth-page 前缀（auth.css 规则全是 .auth-page 作用域，无前缀会被压住，登录页教训已写进提示词），全部边框均写成 1px solid var(--border) 完整形式。
- 验收：新增 RegisterDesignV1Test 3 例全绿，设计层合跑 65/65 全绿，Maven 离线 BUILD SUCCESS；磁盘内联截图 + 计算样式亲眼核对：页头 20/700、副标题 13px、分段器 8px 圆角、当前签页 13/600 白底、录入行 8px 圆角 1px 边、输入框 13px、密码提示 12px、主按钮 13/600/8px、协议行 12px、零 console 错误；截图存 docs/screenshots/register-design-v1.png（眼形图标为空框是 harness 剥离 lucide 脚本所致，真页有图标；注册按钮灰色是初始 disabled 真实态）。另用隔离构建（源码拷到 relay-station 单独打包，避开他路在跑的 target/）起真实服务（18098 端口，复制 H2 库）实测：register.html 与 register-design-v1.css 均 200，页内引用与层文件内容对上；验收后服务按真实 java PID 停干净、端口已关、隔离构建与复制库已删。构建教训：首轮直接在仓库 target/ 打包撞上他路测试/打包（jar 被截断损坏、PluginExecutionException），改走隔离构建才成；另有一次 exec 管道 tail 掩盖了 mvn 退出码，今后打包日志落文件再查。
- 已知保留：本层不改布局；注册按钮初始 disabled 态沿用原透明度，不单独覆盖。

### Added（5.3 路 2026-10-26：AI 图片页设计层 v2）
- 新增 static/images-design-v2.css（3 条规则，只覆盖，不改 app.css/harness.css、内联 style 块、v1 文件与任何 JS；images.html 在 v1 之后引用 1 行）：关闭 v1 已知保留“模型下拉、比例/尺寸下拉、参考图预览沿用原样式”——下拉框与 textarea 同一套表单控件语言（surface 底、10px 12px 内边距、14px、8px 圆角、1px 发丝边），参考图预览改块级布局并限高 280px 不裁剪（行内基线空隙消除），文件选择框字体与标签口径协调（12px/600 次文字）；token 全部取自 app.css/harness.css。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000，调用器为本轮现写最小新文件 relay-station/glm53_r17_call.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通输出：API prompt 24286 / completion 995 / total 25281，reasoning_tokens 0，正文即入仓的 3 条规则，零编排修正。括号 3/3 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML；v2 在内联 style 块与 v1 之后加载，同特异度规则压得住内联下拉规则（.fld select 与内联块同为一类一元特异度，后引用生效）。
- 验收：新增 ImagesDesignV2Test 3 例 + v1 合跑 6/6 全绿，Maven 离线 BUILD SUCCESS；真实服务（18198 端口，复制 H2 库，开放模式）+ 内联截图亲眼核对：计算样式实证下拉框 surface 底（浅色主题白底）、10px 12px 内边距、14px、8px 圆角，文件选择框 12px/600 次文字色 #555，零 console 错误；参考图预览因未选文件默认隐藏，harness 内取消隐藏并置入 1px 数据图后实测计算样式为块级显示、限高 280px、8px 圆角（截图本身仍为真实空态，未伪造参考图）；IMAGE 模型未接入（/api/providers?module=IMAGE 回 []），空模型提示与禁用态生成按钮为真实空态；截图存 docs/screenshots/images-design-v2.png。验收后服务按 PID 停干净、端口已关、复制库与验收 jar 已删。
- 已知保留：本层不改布局；文件选择框的浏览器原生按钮外观不动；本轮未动 music、register、ledger、second-brain、docseek eval 在跑工人的未提交文件。

### Added（Flash 路 2026-10-26：登录页设计层 v1）
- 新增 static/login-design-v1.css（15 条规则，只覆盖，不改 app.css/auth.css 与任何 JS；login.html 在 auth.css 之后引用 1 行）：视觉逻辑“登录台账”——页头 20px/700、副标题 13px 次文字、分段器 surface-2 底发丝边 8px 圆角、签页 13px/600、录入行 surface 底发丝边 8px 圆角、输入框 13px、主按钮 13px/600 8px 圆角、忘记密码/分隔/协议行 12px 弱文字、第三方钮 13px 8px 圆角、弹窗面板 surface 底发丝边 8px 圆角零阴影、弹窗标题 13px/600；token 全部取自 app.css/auth.css。
- 模型稿由 GLM-5.3-Flash（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 32000，新提示词，调用器为本轮现写最小新文件 relay-station/flash_call_n2.py、令牌经 SSH 现取不落盘、未读任何现成调用脚本）1 通产出：API prompt 24681 / completion 17217 / total 41898，reasoning_tokens 0，正文即入仓的 15 条规则与测试；编排修正 1 类：模型稿选择器未加 .auth-page 前缀，特异度会被 auth.css 同名规则压住，全部规则统一加 .auth-page 前缀（后引用的同特异度规则生效），规则数与测试断言不变。括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter，全部选择器均真实存在于本页 HTML，全部边框均写成 1px solid var(--border) 完整形式。
- 验收：新增 LoginDesignV1Test 3 例全绿，设计层合跑 59/59 全绿，Maven 离线 BUILD SUCCESS；真实服务（18096 端口，复制 H2 库）+ 内联截图亲眼核对：计算样式实证页头 20/700、副标题 13px、分段器 8px 圆角、签页 13/600、录入行 8px 圆角 1px 边、输入框 13px、主按钮 13/600/8px、第三方钮 13px 8px 圆角、协议行 12px、零 console 错误；截图存 docs/screenshots/login-design-v1.png（截图内眼形图标为空框是 harness 剥离 lucide 脚本所致，真页有图标，不属设计层缺陷）。验收后本路服务按 PID 停干净、复制库已删；18096 端口现为他路服务在听，本轮未动。
- 已知保留：本层不改布局；登录页本身无卡片容器，10px 圆角卡片口径本页不适用；密码显隐钮在真页显示 eye 图标，本层只给 6px 圆角细边。

### Added（5.3 路 2026-10-26：成片质检页设计层 v1）
- 新增 static/qc-design-v1.css（15 条规则，只覆盖，不改 app.css/harness.css 与任何 JS；qc.html 在 harness.css 之后引用 1 行）：视觉逻辑“质检台账”——页头 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、徽标 12px/600、信息 dt 12px/600 次文字、dd 13px、备注标题与表单标签 12px/600、textarea 13px 8px 圆角、通过/打回按钮 13px/600 8px 圆角、空态 13px 次文字；token 全部取自 app.css/harness.css。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，max_tokens 4000）2 通产出：首通正文 0 字（API prompt 24576 / completion 4000 / total 28576，思考耗尽未出正文，按规缩小目标不重发原提示词）；二通纯 CSS 入仓（API prompt 24095 / completion 2028 / total 26123，正文 1511 字即入仓的 15 条规则，分 3 个围栏、编排机械拼接）；测试文件 QcDesignV1Test 由编排按 Settings 模式机械落仓。括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML，全部边框均写成 1px solid var(--hairline) 完整形式。
- 验收：新增 QcDesignV1Test 3 例全绿，设计层合跑 56/56 全绿，Maven 离线 BUILD SUCCESS；真实服务（18197 端口，复制 H2 库，开放模式）+ 截图亲眼核对：计算样式实证页头 20/700、卡片白底 1px 边 10px 圆角、标题 16/700、徽标 12/600、dt 12/600、dd 13px、textarea 13px 8px 圆角、通过/打回 13/600/8px、零 console 错误；成片 id=1 数据与库内记录对上（第 1 集成片、待质检、00:09、2026-10-13 06:46、剧集 #1）；截图存 docs/screenshots/qc-design-v1.png。验收后服务按 PID 停干净、18197 端口已关、复制库与验收 jar 已删。
- 已知保留：本层不改布局；视频区只加边框圆角、不碰内联黑底与播放逻辑，截图时播放器为初始 0:00 态（无自动播放，/media/finals/1 实测 200）；18196 端口被另一路 drama 服务占用，本轮改用 18197，验收 jar 复制到验收目录防他路重打包覆盖；截图 harness 经验：setContent 的 url 选项带不过 location.search（首拍空态），后改为 harness 内把 qc.js 的 location.search 读数替换为固定 id 参数并把等待条件收紧为“标题非加载中且时长非 -”才放行，复拍一次通过；本轮未动 images v2、login、second-brain、docseek eval 在跑工人的未提交文件。


### Added（Flash 路 2026-10-25：数字人页设计层 v1）
- 新增 static/avatar-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；avatar.html 在 head 内联 style 块之后引用 1 行，同特异度下后者生效）：视觉逻辑“数字人台账”——页头 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片头 14px/20px 内边距加底发丝线、卡片标题 16px/700、表单标签 13px/600 次文字、输入框/下拉/多行框 13px 8px 圆角、提示 12px 弱文字、BYOK 空盒 surface-2 底 1px 虚线发丝边 8px 圆角、预览图 8px 圆角、文件名 13px 次文字、生成区顶发丝线、生成钮 13px/600 8px 圆角（不改颜色）；token 全部取自 app.css/harness.css。
- 模型稿 15 条规则，编排修正 2 类：副标题选择器由 .page-sub 加强为 .page-head .page-sub（app.css 同名分组选择器特异度更高，原规则会被压回 12px）；--hairline 全部换成 --border（两主题下值相同，且 --hairline 只在 harness.css 定义，截图内联漏掉自闭合 link 时会失效，换 token 后不再依赖 harness 加载顺序）。括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部边框均写成 1px solid/dashed var(--border) 完整形式。
- 验收：新增 AvatarDesignV1Test 3 例 + 旧设计层合跑 47/47 全绿，Maven 离线 BUILD SUCCESS；真实服务（18095 端口，复制 H2 库，开放模式）初验 + 磁盘内联复验截图亲眼核对：计算样式实证页头 20/700、副标题 13px 次文字、卡片白底 10px 圆角 1px 发丝边、BYOK 空盒 1px 虚线发丝边、生成区顶发丝线、零 console 错误；截图存 docs/screenshots/avatar-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；沙箱内未接任何数字人模型，截图中模型下拉为空、BYOK 空盒与“先在通道管理配置 API 后可用”提示为真实空态；本轮未动 images.html 在跑工人的未提交文件。

### Added（5.3 路 2026-10-25：AI 图片页设计层 v1）
- 新增 static/images-design-v1.css（8 条规则，只覆盖，不改 app.css/harness.css、内联 style 块与任何 JS；images.html 在内联 style 块之后引用 1 行）：视觉逻辑“图片台账”——页头 20px/700、副标题 13px 次文字、卡片标题 16px/700、表单标签 12px/600 次文字、输入框 13px 8px 圆角、生成按钮 13px/600 8px 圆角、生成区上下 16px 发丝底线、提示 13px 次文字；token 全部取自 app.css/harness.css。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000）1 通输出：API prompt 24082 / completion 1706 / total 25788，reasoning_tokens 0，正文 1255 字即入仓的 8 条规则；编排修正 3 处（见 DESIGN_SYSTEM 第 24 节已知保留），其余为模型原文，括号 8/8 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML，全部 token 均在 app.css/harness.css 里。
- 验收：新增 ImagesDesignV1Test 3 例 + 成片页测试合跑 6/6 全绿，Maven 离线 BUILD SUCCESS；真实服务（18196 端口，复制 H2 库，开放模式）+ 截图亲眼核对：计算样式实证页头 20/700、副标题 13px 次文字、卡片标题 16/700、表单标签 12/600、输入框 8px 圆角 14px、生成按钮 13/600/8px、生成区上下 1px 发丝线、零 console 错误；IMAGE 模型未接入（/api/providers?module=IMAGE 回 []），空模型提示“还没有接入图片模型”与禁用态生成按钮为真实空态，未伪造数据；截图存 docs/screenshots/images-design-v1.png。验收后服务按 PID 停干净、端口已关、复制库已删。
- 已知保留：本层不改布局；模型下拉、比例/尺寸下拉、参考图预览沿用原样式；本轮未动 second-brain、docseek eval、feedflow（另一路在跑）、avatar 页（另一路在跑）工人的未提交文件。

### Added（5.3 路 2026-10-25：成片库页设计层 v1）
- 新增 static/finals-design-v1.css（8 条规则，只覆盖，不改 app.css/harness.css 与任何 JS；finals.html 在 harness.css 之后引用 1 行）：视觉逻辑“成片台账”——页头 20px/700 加 1px 发丝底线、筛选条 surface 底发丝边、下拉 13px、生成按钮 13px/600 8px 圆角、提示 13px 次文字、成片列表纵向排列行距 12px；token 全部取自 app.css/harness.css。
- 模型稿由 GLM-5.3（BotsRouter，大写，令牌 id=5，渠道 20，单路串行，prompt 首行禁思考过程，max_tokens 4000）1 通输出：API prompt 24033 / completion 1349 / total 25382，reasoning_tokens 0，正文 1055 字即入仓的 8 条规则；编排修正 2 处（见 DESIGN_SYSTEM 第 23 节已知保留），其余为模型原文，括号 8/8 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 Inter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML，全部 token 均在 app.css/harness.css 里。
- 验收：新增 FinalsDesignV1Test 3 例全绿，Maven 离线 BUILD SUCCESS；真实服务（18195 端口，复制 H2 库，开放模式）+ 截图亲眼核对：计算样式实证页头 20/700、筛选条白底 1px 边、生成按钮 13/600/8px、提示 13px 次文字、零 console 错误；下拉 6 个真实项目（都市奇缘/最后一班地铁/验证用短剧/取消测试/冒烟测试项目/逐字稿演示项目）与 /api/projects 对上，剧集“重逢”与成片“第 1 集成片·时长 0:09·已完成·待质检”与库内数据对上；截图存 docs/screenshots/finals-design-v1.png。验收后服务按 PID 停干净、端口已关、复制库已删。
- 已知保留：本层不改布局；成片卡片本体（海报、标题、状态戳、操作行）沿用原样式，本轮未覆盖；本轮未动 second-brain、docseek eval、feedflow（另一路在跑）、avatar 页（另一路在跑）工人的未提交文件；18095 端口已被另一路 drama 服务占用，本轮改用 18195 验收。


### Added（Flash 路 2026-10-25：账号页设计层 v1）
- 新增 static/account-design-v1.css（只覆盖，不改 app.css/auth.css 与任何 JS；account.html 在 auth.css 之后引用 1 行，本页不引用 harness.css）：视觉逻辑“账号台账”——页头 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、资料标签 12px/600 次文字、资料值 13px、输入框 13px 8px 圆角、安全块上下发丝底线分隔、表单标签 12px/600 次文字、字段提示 12px 弱文字、行内错误 13px 红色、会话列表 13px 次文字、单选行 13px、个性化选项组发丝边 8px 圆角；token 全部取自 app.css/auth.css。
- 模型稿 18 条规则原文入仓，零编排修正：括号 18/18 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML，全部边框均写成 1px solid var(--border)/var(--border-soft) 完整形式；无设计层基线对照：本页此前无设计层。
- 验收：新增 AccountDesignV1Test 3 例 + 旧设计层合跑 44/44 全绿（含 Settings/Index），Maven 离线 BUILD SUCCESS；真实服务（18094 端口，复制 H2 库，开放模式）+ 截图亲眼核对：计算样式实证页头 20/700、卡片白底 10px 圆角 1px 发丝边、资料标签 12/600 #555、安全块发丝底线、个性化选项组 8px 圆角发丝边；截图存 docs/screenshots/account-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；沙箱内 auth-service 上游未起，/api/auth/me 返回上游不可用，故截图中昵称/邮箱/角色为占位“—”、会话区显示“账号服务暂时不可用”红字，属真实环境状态、非本层问题；截图 harness 下 2 条 502 console 记录为 auth 相关代理请求失败，与设计层无关；本轮未动 second-brain、mini-os、docseek eval 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：工作台首页设计层 v1）
- 新增 static/index-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；index.html 在 harness.css 之后引用 1 行）：视觉逻辑“工作台账”——问候语 20px/700、状态条 13px 次文字、上下文栏下拉 13px 8px 圆角、新建链接 13px 次文字、新建面板 surface 底发丝边 10px 圆角零阴影、新建块标题 15px/700、新建表单输入框 13px 8px 圆角、新建表单小按钮 12px/600 8px 圆角、对话区 13px 行高 1.6、快捷 chips 12px/600 8px 圆角、输入框 13px 8px 圆角、发送钮只留尺寸与圆角不改颜色、费用提示 12px 弱文字、最近动态标题 16px/700、空态 13px 次文字、最近动态区上下 16px 发丝底线；token 全部取自 app.css/harness.css。
- 模型稿 16 条规则原文入仓，零编排修正：括号 16/16 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里；边框写法正确（1px solid var(--hairline)）。
- 验收：新增 IndexDesignV1Test 3 例 + 旧设计层合跑全绿，Maven 离线 BUILD SUCCESS；真实服务（复制 H2 库，开放模式）+ 真实项目数据截图亲眼核对；截图存 docs/screenshots/index-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；发送钮颜色未动；本轮未动 second-brain、new-api-src、botstalk、sentinel、docseek eval、ledger 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：设置中心页设计层 v1）
- 新增 static/settings-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；settings.html 在 harness.css 之后引用 1 行）：视觉逻辑“配置台账”——页头 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、徽标 12px/600、主按钮 13px/600 8px 圆角、加载/空态/错误提示 13px 次文字、表单行上下 16px 发丝底线、表单标签 12px/600 次文字、输入框与下拉 13px 8px 圆角、开关文字 12px 次文字；token 全部取自 app.css/harness.css。
- 模型稿 15 条规则，编排修正 1 类（7 处）：模型把 --hairline（颜色 token）误当边框宽度写进 border 简写（`border: var(--hairline) solid …` 在浏览器里是无效声明），统一修正为 1px solid，颜色沿用模型稿的 --border-soft/--red；其余 15 条为模型原文，括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 SettingsDesignV1Test 3 例 + 旧设计层合跑全绿，Maven 离线 BUILD SUCCESS；真实服务（复制 H2 库，开放模式）+ 真实配置数据截图亲眼核对；截图存 docs/screenshots/settings-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；重试按钮 #settings-retry 未入本层，沿用原次按钮样式；本轮未动 second-brain、new-api-src、botstalk、sentinel、docseek eval、ledger 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：快捷工具页设计层 v1）
- 新增 static/tools-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；tools.html 在 harness.css 之后引用 1 行，本页无内联 style 块）：视觉逻辑“工具台账”——页头 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片内边距 16px、卡片标题 16px/700、表单标签 12px/600 次文字、输入框与下拉 13px 8px 圆角、主按钮 13px/600 8px 圆角（文字色与底色反转）、表头 12px/600 次文字、单元格 13px、状态戳 12px/600 发丝边 8px 圆角；token 全部取自 app.css/harness.css。
- 模型稿 18 条规则原文入仓，编排修正 1 处：#logs-body 模型稿写了 surface-2 底、边框与内边距，tbody 上这些声明不可靠，改回只留字号/行高/文字色。其余 17 条为模型原文，括号 18/18 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 ToolsDesignV1Test 3 例 + 旧设计层 3 页合跑 12/12 全绿，Maven 离线 BUILD SUCCESS；真实服务（18090 端口，复制 H2 库，开放模式）+ 真实工具数据截图亲眼核对：分镜表导出下拉 6 个真实项目（都市奇缘/最后一班地铁/验证用短剧/取消测试/冒烟测试项目/逐字稿演示项目）与 /api/projects 对上，导出剧集“第 1 集·重逢”与项目 1 的剧集对上；计算样式实证页头 20/700、工具卡 10px 圆角纯白底、卡片标题 16/700、零 console 错误；截图存 docs/screenshots/tools-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；复制库里资产为空（/api/assets 为 []），故批量打标区显示“暂无资产”、视频转换/音频提取下拉显示“暂无视频资产”，操作记录为空（/api/tools/op-logs 为 []）显示“暂无记录”，均为真实空态，未伪造数据；状态戳绿/红两档因空记录未在截图里出现，只由测试覆盖选择器；本轮未动 second-brain、new-api-src、botstalk、sentinel、docseek eval 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：Agent 机队页设计层 v1）
- 新增 static/agents-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；agents.html 在 head 内联 style 块之后引用 1 行）：视觉逻辑“机队台账”——页头 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、徽标 12px/600、通道切换钮 12px/600 8px 圆角、提示 12px 次文字、元数据键 12px/600 次文字、值 13px、模板摘要 13px/600、模板全文等宽 12px surface-2 底 8px 圆角；token 全部取自 app.css/harness.css。
- 模型稿 18 条规则原文入仓，编排修正 2 处：页头规则选择器由 .page-title 改为 .page-head .page-title（harness.css 的 .page-head h1 特异度更高，原规则字重会被压回 600，实测后修正）；模板全文 font-family 改用 --mono token。括号 18/18 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 AgentsDesignV1Test 3 例 + 旧设计层 6 页合跑 21/21 全绿，Maven 离线 BUILD SUCCESS；真实服务（18090 端口，复制 H2 库，开放模式）+ 真实 Agent 数据截图亲眼核对：/api/agents 实查 7 条（编剧/分镜/视频生成/剪辑/质检/作词/作曲）与截图卡片逐项对上，通道当前 Mock 与 /api/agents/channels 对上；计算样式实证页头 20/700、Agent 卡 10px 圆角纯白底、与无设计层基线（页头 20/600、卡 8px 圆角 surface-2 底）对比确认本层生效；截图存 docs/screenshots/agents-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；页内文案“管理 5 个专用 Agent”与实际 7 条 Agent 数据不一致，属既有文案未同步（本层只管样式，未改文案）；截图 harness 下 1 条 document.write console 报错在无设计层基线截图里同样出现，属 harness 产物、非本层回归；体外 style 块（弹窗/预设卡）选择器本层未碰，引用行放在 head 内联块之后即可；本轮未动 second-brain、new-api-src、botstalk、sentinel、docseek eval 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：Skill 市场页设计层 v1）
- 新增 static/skills-design-v1.css（只覆盖，不改 app.css 与任何 JS；skills.html 在 app.css 之后引用 1 行，本页不引用 harness.css）：视觉逻辑“技能台账”——页头 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、表单标签 12px/600 次文字、输入框 13px 8px 圆角、标签钮 12px/600 8px 圆角、市场卡片名 15px/700、徽标 12px/600、已安装名 14px/600、空态 13px 次文字；token 全部取自 app.css。
- 模型稿 16 条规则原文入仓，编排修正 1 处：标签钮模型稿写死 surface-2 底与次文字色，会把激活态主按钮也洗成灰色，改回只留字号/字重/圆角，激活态颜色沿用原按钮样式。其余 15 条为模型原文，括号 16/16 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css 里。
- 验收：新增 SkillsDesignV1Test 3 例 + 旧设计层 5 页合跑 18/18 全绿，Maven 离线 BUILD SUCCESS；真实服务（18089 端口，复制 H2 库，开放模式）+ 真实技能数据截图亲眼核对：市场 4 卡（短剧钩子开头/分镜大师/转场设计/爽点节奏）与 /api/skills 对上，已安装 1 条（短剧钩子开头）与 /api/skills/installed 对上；计算样式实证页头 20/700、市场卡 10px 圆角纯白底、卡片名 15/700、零 console 错误；标签激活态（全部标签黑底）未被设计层洗白，编排修正有效；截图存 docs/screenshots/skills-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局；已安装行底线颜色由 skills.js 行内 !important 写死，本层不硬压；本轮未动 cost-ledger.js、second-brain、docseek eval、botstalk、new-api-src 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：用量统计页设计层 v1）
- 新增 static/usage-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；usage.html 在内联 style 块之后引用 1 行，因该页内联 style 在样式表链接之后、放最后才能在同特异度下生效）：视觉逻辑“用量台账”——页头 20px/700、筛选下拉与刷新钮 6px 圆角、章节标题 16px/700、KPI 卡 surface 底发丝边 10px 圆角零阴影、KPI 大数字 24px/700 等宽数字、趋势条 surface-2 底 4px 圆角、空态卡 surface 底发丝边 10px 圆角、数据表头 12px/600 次文字、单元格 13px 等宽数字；token 全部取自 app.css/harness.css。
- 模型稿 19 条规则，编排删 3 条、改 1 类后入仓 16 条：删 .kpi-grid（模型误写成 flex，会破坏内联 4 列网格布局）、删 .section（套卡会与 KPI 卡双重嵌套）、删 .state-box.error（误把错误色写成墨色）；3 处 font-family monospace 改回只用 tabular-nums（数据表文字列不应用等宽字体）。其余 16 条为模型原文，括号 16/16 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 UsageDesignV1Test 3 例 + 旧设计层 4 页合跑 15/15 全绿，Maven 离线 BUILD SUCCESS；真实服务（18089 端口，复制 H2 库，开放模式）+ 真实用量数据截图亲眼核对：/api/usage/summary 实查 tokensTotal 65930、costCentsTotal 1404、requestCount 23，与截图 KPI“¥14.04 / 23 / 65,930”一一对上；计算样式实证页头 20/700、KPI 数字 24/700、KPI 卡 10px 圆角纯白底、表头 12/600、零 console 错误；截图存 docs/screenshots/usage-design-v1.png。验收后服务按 PID 停干净、复制库已删。
- 已知保留：本层不改布局（KPI 4 列网格与移动端 2 列、趋势条结构、数据表列维持原样）；本轮未动 cost-ledger.js、second-brain、docseek eval、botstalk 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：分镜板页设计层 v1）
- 新增 static/storyboard-design-v1.css（只覆盖，不改 app.css 与任何 JS；storyboard.html 在 app.css 之后引用 1 行，本页不引用 harness.css）：视觉逻辑“分镜台账”——页头 20px/700、筛选标签 12px/600 次文字、下拉与次按钮 8px 圆角、剧集元数据 13px 次文字、分镜行上下 16px 发丝底线、镜号等宽 12px 弱文字、描述 15px/700、对白 13px 次文字、元数据 12px 弱文字、操作按钮 8px 圆角、表单标题 16px/700、状态戳 12px/600 发丝边 8px 圆角、提示小字 12px 次文字；token 全部取自 app.css。
- 模型稿即入仓的 15 条规则原文，未做编排修正：括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css 里。
- 验收：新增 StoryboardDesignV1Test 3 例全绿，与 RunDetail/Runs/Tasks 合跑 12/12 全绿，Maven 离线 BUILD SUCCESS；真实服务 + 真实分镜数据截图亲眼核对（见下）；截图存 docs/screenshots/storyboard-design-v1.png。验收后服务已停、复制库与 jar 已删。
- 验收插曲：首版截图 0 行分镜，根因是 setContent 下 location 为空、页内相对接口 URL 解析失败，且 storyboard.js 用反引号模板写接口、旧 safeJS 只换了引号形式；截图脚本（muse-build/shot/drama-storyboard-shot.js，不入仓）补反引号改写后重拍，仓库代码一字未动；另：本轮曾先做生产看板页设计层，截图实证其统计区与管线表在 app.css 里已有故意的编辑杂志式设计、台账层只能半覆盖而不协调，已全部撤回未提交，改做分镜板页；审核队列页因 6 个项目队列全空、无法作门面验收，亦已放弃。
- 已知保留：本层不改布局（分镜行 flex 结构、操作按钮排列、表单面板结构维持 app.css 原样）；本轮未动 cost-ledger.js、second-brain、docseek eval、voxloom 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：运行详情页设计层 v1）
- 新增 static/run-detail-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；run-detail.html 在 app.css 与 harness.css 之后引用 1 行）：视觉逻辑“运行台账”——页头 20px/700、元数据行 12px 次文字、章节标题 16px/700、步骤行距 16px、步骤名 15px/700、步骤 Agent 12px/600、耗时等宽 12px 次文字、步骤标签 12px/600 次文字、摘要框等宽 12px surface-2 底 8px 圆角、工具表头 12px/600 次文字、产物卡 surface 底发丝边 10px 圆角零阴影、产物标题 15px/700、汇总卡 surface 底发丝边 10px 圆角 16px 内边距、抽屉标题 15px/700；token 全部取自 app.css/harness.css。
- 模型稿即入仓的 15 条规则原文，未做编排修正：括号 15/15 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体、无十六进制颜色字面量，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 RunDetailDesignV1Test 3 例全绿（引用顺序、括号与禁令、关键选择器）；真实服务 + 真实运行数据截图亲眼核对（见下）；截图存 docs/screenshots/run-detail-design-v1.png。验收后服务已停、复制库与 jar 已删。
- 已知保留：本层不改布局（时间线竖线、步骤圆点色、失败步骤红线、抽屉位置与动画维持 harness.css 原样）；截图 harness 侧注入 id=4（setContent 下 location 为空取不到 ?id=，仓库代码一字未动，数据走真实服务 API）；本轮未动 cost-ledger.js、second-brain、docseek eval、feedflow、linkshort 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：运行列表页设计层 v1）
- 新增 static/runs-design-v1.css（只覆盖，不改 app.css/harness.css 与任何 JS；runs.html 在 app.css 与 harness.css 之后引用 1 行）：视觉逻辑“运行台账”——页头 20px/700、页头按钮 8px 圆角、统计条 13px/600 加 12px 下距与发丝底线作总计线、全部运行标题 16px/700、运行行上下 16px、目标 15px/700、状态徽标 12px/600、空态 13px 次文字、向导卡纯白底发丝边 10px 圆角零阴影、向导标题 15px/700、向导标签 12px/600 次文字、目标输入框 13px 8px 圆角、错误框 13px 8px 圆角；token 全部取自 app.css/harness.css。
- 模型稿即入仓的 13 条规则原文，未做编排修正：括号 13/13 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css/harness.css 里。
- 验收：新增 RunsDesignV1Test 3 例全绿（引用顺序、括号与禁令、关键选择器）；真实服务 + 真实运行数据截图亲眼核对（见下）；截图存 docs/screenshots/runs-design-v1.png，另补点击“新建运行”后的向导截图 docs/screenshots/runs-design-v1-wizard.png（向导卡纯白底 10px 圆角零阴影、标题 15/700、标签 12/600 次文字、输入框 13px 8px 圆角计算样式全对）。验收后服务已停、复制库与 jar 已删。
- 已知保留：本层不改布局（行底线、悬停底色、徽标底色与文字色、网格列均维持 harness.css 原样）；本轮未动 cost-ledger.js、second-brain、docseek eval、feedflow v1.14 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：任务队列页设计层 v1）
- 新增 static/tasks-design-v1.css（只覆盖，不改 app.css 与任何 JS；tasks.html 在 app.css 与 harness.css 之后引用 1 行）：视觉逻辑“任务台账”——页头 20px/700、筛选卡纯白底发丝边 10px 圆角零阴影、筛选标签 12px/600 次文字、下拉与刷新按钮 8px 圆角、计数 13px/600、任务行上下 14px、状态徽标收窄为 12px/600 台账戳、进度条 surface-2 底 2px 圆角、空态 13px 次文字；全部左对齐，token 全部取自 app.css。
- 模型稿即入仓的 13 条规则原文，未做编排修正：括号 13/13 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css 里。
- 验收：新增 TasksDesignV1Test 3 例全绿（引用顺序、括号与禁令、关键选择器）；真实服务 + 真实任务数据截图亲眼核对（见下）；截图存 docs/screenshots/tasks-design-v1.png。验收后服务已停、复制库与 jar 已删。
- 已知保留：任务行底线、任务名与元数据字号颜色、进度条宽高、百分比字号颜色均由 tasks.js 行内样式写死，设计层不硬压，本层只管行距、徽标、进度条底色与圆角；本轮未动 cost-ledger.js、second-brain、docseek eval 在跑工人的未提交文件。

### Added（Flash 路 2026-10-25：提示词库页设计层 v1）
- 新增 static/prompts-design-v1.css（只覆盖，不改 app.css 与任何 JS；prompts.html 在 app.css 之后引用 1 行）：视觉逻辑“提示词档案柜”——页头 kicker 是柜签、搜索与标签芯片是索引抽屉、卡片是同行等高的档案袋（标题、摘要、来源元数据行、底部借阅条沉底对齐）、详情卡是抽出展开的档案全文（等宽字体换行）；全部左对齐，层级只靠字重、字号、线宽与留白，token 全部取自 app.css。
- 模型稿编排修正 1 处（已写进测试防回归）：删 .page .form-check.form-switch 的 margin-right: auto 规则（会把右对齐的只看收藏开关顶到左端，改布局不只改样式）；其余规则逐项核对：括号 47/47 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css 里。
- 验收：新增 PromptsDesignV1Test 4 例全绿（引用顺序、括号与禁令、关键选择器、开关对齐禁令）；真实服务 + 真实提示词库数据截图亲眼核对（见下）；截图存 docs/screenshots/prompts-design-v1.png。验收后服务已停、复制库与 jar 已删。
- 已知保留：长描述卡片的操作区在首屏折叠线下，属真实数据长度，不是布局缺陷；本轮未动 sentinel 在跑工人的未提交文件。

### Added（深耕轮 2026-10-25：成本账本趋势图颜色与尺寸收归设计层）
- cost-ledger.js 的 renderTrend 函数删掉 9 处 16 进制颜色属性（网格线 #e6e8eb、刻度文字 #6c7a91 两处、预估线 #a8b0bd 两处、实际线 #206bc4 两处、数据点 #206bc4、图例底色 #495057），几何属性（stroke-width、stroke-dasharray、font-size、r、points）与 polyline 的 fill="none" 全部保留；颜色现全部由 cost-ledger-design-v1.css 的 #trendChart 选择器接管，JS 不再是颜色来源。
- 设计层 #trendChart svg 规则补 width: 100% 与 height: auto：此前 harness.css 第 66 行全局 svg{width:15px;height:15px} 规则把趋势图压成 15×15 像素肉眼不可见（视觉验收实测），设计层以 ID 选择器特异性夺回尺寸，实测 SVG 恢复为 1008×308。
- x 轴最后一个日期标签改 text-anchor="end" 落在轴右端：此前居中标签右半边超出 720 宽 viewBox 被裁成“10-2!”，现完整显示“10-25”。
- 新增回归测试 CostLedgerTrendColorTest 4 例（无写死颜色、设计层覆盖 7 个颜色角色、几何属性保留、设计层定趋势图尺寸），连同既有 CostLedgerDesignV1Test 4 例共 8/8 全绿。
- 真实服务冒烟（18521 端口隔离库）：建项目/剧集/分镜后 mock 提交、任务 DONE，trend 接口 2026-10-25 返回预估 0.16/实际 0.16/1 笔；截图 docs/screenshots/cost-ledger-trend-colors.png 亲眼验收通过，计算样式实测实际线 #111111、预估线 #999999、网格线 rgba(0,0,0,0.08)，与设计层 token 一致。
- 诚实声明两句：①冒烟数据里预估与实际恰好相等（均为 0.16），两条线重合是数据真实情况，不是渲染问题；②harness.css 的全局 svg 尺寸规则未动，其它页面的 SVG 仍受它影响，留待后续轮次处理。

### Added（Flash 路 2026-10-25 约 19:50-20:20：成本账本页设计层 v1）
- 新增 static/cost-ledger-design-v1.css（只覆盖，不改 app.css 与任何 JS；cost-ledger.html 在 app.css 之后引用 1 行）：视觉逻辑“账本台账”——预算卡是总账（surface-2 底 + 2px 墨色顶线）、KPI 卡是分户、趋势与供应商是明细账页、最近明细表是流水；层级只靠字重、字号、线宽与留白，全部左对齐，token 全部取自 app.css；KPI 数字 tabular-nums，预算进度条实色填充，明细行 hover 只用淡底色。
- 模型稿编排修正 2 处（均已写进测试防回归）：删 .card-header.justify-content-between 改 flex-start 的规则（会把趋势卡标题与天数按钮挤到一端，改布局不只改样式）；删 #providerBars .d-flex 改 flex-start 的规则（会把供应商名与金额从两端对齐改成并排）。其余规则逐项核对：括号 59/59 平衡，无 linear-gradient、无 backdrop-filter、无 !important、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML/JS 渲染的 DOM，全部 token 均在 app.css 里。
- 验收：新增 CostLedgerDesignV1Test 4 例全绿（引用顺序、括号与禁令、关键选择器、两条布局禁令）；真实服务 + 真实成本账本数据截图亲眼核对（见下）；截图存 docs/screenshots/cost-ledger-design-v1.png。验收后服务已停、演示数据未入提交。
- 已知保留：趋势 SVG 的颜色与尺寸部分已于 2026-10-25 深耕轮关闭（颜色已全部移入设计层、设计层为唯一颜色来源，趋势图尺寸亦由设计层接管），详见本轮 Added（深耕轮 2026-10-25：成本账本趋势图颜色与尺寸收归设计层）条目；本轮未动 skillhub 在跑工人的未提交文件。

### Added（SkillHub 设计层 v1 + 已安装状态真修复，2026-10-25）
- 新增 static/skillhub-design-v1.css（只覆盖，不改 app.css；skillhub.html 在 app.css 之后引用 1 行，外层 div 加 skh-page）：视觉逻辑“索引台账”——纯白底、发丝边框、10px 圆角、零阴影；标题 16px/500 墨色、描述 14px 次文字、作者·许可证·版本·来源元数据行 13px 弱文字；卡片底部操作区顶部发丝线、按钮右对齐；同行卡片等高、操作沉底对齐。token 全部取自 app.css，无 linear-gradient、无 backdrop-filter、无阴影、无 Inter、无 emoji、无首字母 logo。
- 真问题修复 1：前端 skillhub.js 此前完全忽略后端 installed/installedVersion，renderActions 恒显示“安装”、doInstall/doUninstall 只弹 toast 不调接口（属假成功态）；现已安装显示淡绿“已安装”徽标（带版本时附版本）+ 卸载幽灵按钮调 DELETE /api/official-skills/installed/{id}，未安装显示安装主按钮调 POST /api/official-skills/install/{id}，成功后才 toast 并重拉列表、失败走 showError；同时修复 buildCard 无 col 包裹致网格失效（现包 col-12 col-md-6 col-lg-4 skh-col）、分页激活按钮加 active 类、api() 支持 options 且空体返回 {}。
- 真问题修复 2：SkillHubController.toItem 曾以 installedVersion 非空判断已安装，版本号本身为空的 skill（如 02ui-video-copy）装完后仍误报未安装；现以注册表 containsKey 为准，与 OfficialSkillController 的 inst != null 口径一致。新增 SkillHubIndexControllerTest.installedFlagFlipsAfterInstallForEmptyVersionSkill 回归用例。
- 验收：SkillHubIndex/InstallFlow/Pagination/QueryFilter 四类共 33 例全绿（含新增 1 例）；真实服务（18081 端口，隔离 H2 库，DRAMA_SKILLS_DIR 指仓库 data/skills）+ 真实索引数据（1373 条）截图亲眼核对：首屏 48 卡三列网格、计数“第 1/29 页，共 1373 个”、计算样式实证卡片纯白底、发丝边、标题 16px/500、前三列/卡片同高 715px；真实安装 02ui-video-copy 后复拍确认首卡“已安装”徽标 + “卸载”按钮、其余卡仍为“安装”，随后真实卸载还原（installed 列表已空）；截图存 docs/screenshots/skillhub-design-v1.png 与 skillhub-design-v1-installed.png。验收后服务已停、演示安装已卸载还原。已知保留：未登录烟雾环境下 /api/auth/me 回 502（账号服务不可用，真实服务原样行为，与设计层无关）；长描述卡片的操作区在首屏折叠线下，属真实数据长度，不是布局缺陷。

### Added（Flash 路 2026-10-25 约 19:18-19:46：官方 Skill 库页设计层 v1）
- 新增 static/official-skills-design-v1.css（只覆盖，不改 app.css 与任何 JS；official-skills.html 在 app.css 之后引用 1 行）：视觉逻辑“目录卡台账”——纯白底、发丝边框、10px 圆角、零阴影；标题 16px/600 墨色、描述 14px 次文字、作者/许可/版本行 13px 弱文字；卡片底部操作区顶部发丝线、按钮右对齐；搜索框 8px 圆角、聚焦墨色边框；已安装徽章淡绿底、字重 550。
- 模型稿编排修正 1 处：标题色由 var(--ink)（按钮底色）改 var(--text)，更合设计体系语义；其余规则逐项核对：括号 17/17 平衡，无 linear-gradient、无 backdrop-filter、无 emoji、无外来字体，全部选择器均真实存在于本页 HTML/JS，全部 token 均在 app.css 里。
- 验收：新增 OfficialSkillsDesignV1Test 3 例全绿（引用顺序、括号与禁令、关键选择器）；真实服务（18082 端口，复制 H2 库）+ 真实官方 Skill 数据（1373 条）截图亲眼核对：首屏 3 卡无重叠、无阴影、无渐变，计算样式实证卡片纯白底、10px 圆角、box-shadow none、搜索框 8px；截图存 docs/screenshots/official-skills-v1.png。验收后服务已停、复制库与 jar 已删。
- 已知保留：长描述卡片的操作区按钮在首屏折叠线下，属真实数据长度，不是布局缺陷；本轮未动 skillhub 在跑工人的未提交文件。

### Added（技能库增量 2026-10-25：zenstory-ai/drama-skills +12，原件收录）
- 官方技能库 1361 → 1373：新增 drama-skills-short-drama / -write / -develop / -assets / -image-prompts / -storyboard / -video-prompts / -produce / -edit / -review / -novel-analyze / -knowhow（上游 zenstory-ai/drama-skills，commit fdb7b7c，v0.9.2，MIT）
- 收录方式：整目录原件照搬（SKILL.md + references/scripts/assets/agents 共 204 个文件逐字节核对无差异），每目录另补仓库 MIT LICENSE；_index.json 新增 12 条（name/description 取 frontmatter 原文，frontmatter 无 version 故按既有规则记 1.0.0，author zenstory-ai，rewritten false）
- 核验：SkillRegistryTest / SkillLicenseComplianceTest / SkillReferenceIntegrityTest / SkillRegistryIndexDeepR2Test 共 24 例全绿（含 bundled 计数与索引一致性断言）；GLM-5.3 大上下文调用（prompt 59886 + completion 16000）本轮只产出推理 token、正文 0 字，索引与核对均以原文 bytes 与测试为准，未照抄模型输出

### Added（深耕轮 2026-10-25 17:15：HyperFrames --version 自检指标，关闭 2026-10-25 13:07 已知限制）
- DramaMetrics 新增 recordHyperFramesVersionCheck(long latencyMs, boolean ok)，暴露 Counter dramafactory_hyperframes_version_checks_total{result}（result=ok/error，与全站口径一致）与 Timer dramafactory_hyperframes_version_check_duration（负延迟截断为 0）
- HtmlRenderVideoProvider 经 @Autowired(required=false) setter 注入 DramaMetrics（另增 CommandRunner+DramaMetrics 测试构造器），在 resolveEngine 的 hyperframes --version 成功/非零退出/异常三处各记一次，metrics 为 null 时不记不报错，降级行为不变
- 新增 HtmlRenderVersionCheckMetricsTest 测试 5 例（直接记 ok/error 与负延迟截断、--version 成功记 ok、非零退出记 error、异常记 error、无 metrics 仍降级不抛 NPE）；关联旧类 HtmlRenderEngineSelectionTest 7 例、HyperFramesRenderMetricsTest 5 例全绿

### Added（深耕轮 2026-10-25 13:07：HyperFrames 渲染可观测性）
- DramaMetrics 新增 recordHyperFramesRender(String template, long latencyMs, boolean ok)，暴露 Counter dramafactory_hyperframes_renders_total{template,result}（result=ok/error）与 Timer dramafactory_hyperframes_render_duration{template}
- HyperFramesVideoProvider 经 @Autowired(required=false) setter 注入 DramaMetrics，于 runRender 结束时记一次，失败含非零退出码/无产物/异常三种情形，ok 按 failure==null 传
- 新增 HyperFramesRenderMetricsTest 测试 5 例（record_ok、record_normalization、provider_success_records_ok、provider_failure_records_error、provider_without_metrics_still_renders），指标由既有 /actuator/prometheus 端点直接可见，无需新增端点

### Added（深耕轮 2026-10-25 03:07：HyperFrames 可寻址时间线模板（关闭 TD-002））
- HyperFramesVideoProvider 新增 drama.video.hyperframes.template 开关：shot-timeline 模板含 bg/title/subtitle/accent 四个带 data-clip/data-start/data-duration 的可寻址 clip；节拍数学（S=seconds）：bg(0,S)、title(0,max(1,(2*S)/3))、subtitle(S/3,S-S/3)、accent((2*S)/3,S-(2*S)/3)；shot-card 仍为默认，老行为不变；非法值 submit 直接拒绝；测试 HyperFramesTimelineTemplateTest 7 例全绿；视觉验收：真实生成 HTML 抓屏亲眼通过（标题/副标题分开、底部 accent 条正常扫过，零 console 错误），验收中抓出并修复 1 个真问题：模板缺全局 margin 清零致 accent 条被 body 默认 8px 边距顶出视口之外。

### Added（深耕轮 2026-10-24 05:07：视频拆解「逐字稿（内嵌字幕提取）」）
- 深耕轮 2026-10-24 17:07，SkillHub 索引默认分页（关闭 TD-003）。GET /api/skillhub/index 始终分页，无参默认第 0 页、每页 50 条（此前无参返回全部条目）；total 仍为过滤后全量，totalPages 按 ceil(total/size) 计算；size 钳制 1 到 200 不变；前端 skillhub 页恒发 page/size 参数，不受影响；依赖无参返回全部的调用方须改传 page/size 或用 q 过滤定位单条。
- 深耕轮 2026-10-24 17:07，前端 skillhub.js 两处修复（视觉验收发现）：卡片描述字段由 desc 改为 description，之前卡片描述恒为空；补齐 skillhub 页 9 个缺失的 i18n 键并按同站既定做法注册词典，之前标题、副标题、搜索框等位置显示 skh.heading 之类裸键。
- 新服务 `SubtitleTranscriptService`：ffprobe 列字幕流（优先 chi/zho/zh）→ ffmpeg 抽取为 SRT → 解析为分段时间轴；无字幕轨道/提取失败时诚实降级（found=false），不炸拆解流水线。
- 流水线接入：`DeconstructionService.runPipeline` 在关键帧抽取后提取逐字稿；逐镜按时段重叠映射字幕文本（`video_deconstruction_shots.transcript_text`）；任务表新增 `transcript_status`（EMBEDDED/NONE）/`transcript_track_info`/`transcript_json`（Flyway V23）。
- 报告：`DeconstructionReportBuilder` 新增 4 参重载，报告新增「## 逐字稿（内嵌字幕提取）」节；口径说明更新——逐字稿改标注"内嵌字幕轨道离线提取"，ASR 语音转写仍未接入（诚实标注，不冒充）。
- API：`DetailDto` 新增 transcriptStatus/transcriptTrackInfo/transcriptSegments；`ShotDto` 新增 transcriptText；`SummaryDto` 新增 transcriptStatus。
- 前端 `deconstruct.html/js`：详情页新增逐字稿区（轨道信息+条数+时间戳列表，无字幕时诚实提示"未检测到内嵌字幕轨道；语音转写（ASR）尚未接入"），逐镜卡片新增"本镜字幕"行；中英双语。
- 测试 9 例全绿：`SubtitleTranscriptServiceTest` 6 例（SRT/VTT 解析：多行/坏块/空/CRLF/NOTE）+ `SubtitleTranscriptExtractIT` 2 例（真实 ffmpeg 生成带字幕/无字幕视频走 extract）+ `DeconstructionTranscriptApiTest` 1 例（MockMvc 全链路：上传带字幕视频→EMBEDDED→3 段→逐镜字幕→报告含逐字稿）；另修 `DeconstructionAnalyzerTest.reportContainsAllSections` 断言以匹配新口径。
- 附带修复生产启动阻断：`RunApproval`/`StepAttempt` 实体此前已存在但无建表迁移，`ddl-auto: validate` 下启动即报 missing table；新增 Flyway V24 补建 `run_approvals`/`step_attempts` 两表，生产 jar 真实启动验证通过。
- 视觉验收：`docs/screenshots/deconstruct-transcript.png`（真实 6 秒 3 镜带字幕视频：逐字稿区 3 条+逐镜本镜字幕+关键帧，零 console 错误）。

### Added（深耕轮 2026-10-20 晚：DoD 未通过项 F2/F3/F4 部署运维补齐）
- F4 依赖更新机制：`.github/dependabot.yml` 升级——maven / github-actions / docker 三生态，每周一（Asia/Shanghai）检查，open-pull-requests-limit 5，commit 前缀 `chore(deps)`，reviewer Wanfeng1028；新增 `spring-boot` 依赖分组（`org.springframework.boot:*` 同批升级）；springdoc 继续钉死 2.6.x（2.7+ 要求 Spring Framework 6.2，本项目 Spring Boot 3.3.5 对应 Spring 6.1.x，见 docs/DEPENDENCY_POLICY.md 附录 B）；npm 生态未启用（仓库无根 package.json，src/main/resources/skills-bundled/ 下约 90 个 package.json 均为 vendored 第三方模板，不适合 dependabot 跟踪）。
- F2 一键部署事实核验：`Dockerfile`（多阶段：maven:3.9-eclipse-temurin-21 构建 → eclipse-temurin:21-jre 运行，内置 ffmpeg；HEALTHCHECK 用 wget 探 http://localhost:8081/api/health）、`compose.yml`（单服务一键部署：docker compose up -d --build）、`docker-compose.yml`（auth + app + nginx 全栈）、`.env.example`（全部环境变量占位齐全）逐项与 `src/main/resources/application.yml`（端口 ${PORT:8081}，默认 8081）、`HealthController`（@RequestMapping("/api") + @GetMapping("/health") 即 /api/health）、`target/drama-factory-1.0.0.jar`（实际构建产物名）核对一致；`compose.yml` 的 healthcheck 由 curl 改为 wget（eclipse-temurin:21-jre 镜像不带 curl，与 Dockerfile 自带 HEALTHCHECK 一致）；`docker-compose.yml` 的 app 服务补 healthcheck（wget 探 /api/health）与 mem_limit: 1g。
- F3 本文件：即本次更新本身，补"已知限制"与"升级指南"两节。

### Added（OpenMontage 集成变更补记，2026-10-19）
- Java 源码 5 个：service/video/VideoProviderRouter.java（七维评分路由）、service/video/ProviderScoreCard.java、service/video/RoutingDecision.java、service/CutRhythmChecker.java、service/UsageService.java（计费台账）。
- 配置/资源：prometheus/prometheus.yml（抓取配置）、resources/pipeline-templates/ 下 animated-explainer / screen-demo / talking-head 三个 pipeline YAML 模板、resources/skills-bundled/ 下 OpenMontage skill 库收录（AGPL-3.0 来源如实标注）。
- 文档 5 篇：docs/OPENMONTAGE_RESEARCH.md、docs/PIPELINE_TEMPLATES.md、docs/SKILL_AUDIT_2026-10-19.md、docs/BACKUP_DRILL_AUTH_2026-10-19.md、docs/OPERATIONS.md、docs/OPERATIONS-AUTH.md。
- 注：HyperFrames 渲染双引擎（chromium/hyperframes，drama.video.htmlrender.engine）已记于本文件"深耕轮 2026-10-20 凌晨 lane A"条目，不重复记录。

### 已知限制（发版级声明，2026-10-20）
- 容器化一键部署已提供（Dockerfile / compose.yml / docker-compose.yml / .env.example），但未经本机实测、未做生产压测，生产上线前必须实测验证。
- 本轮 OpenMontage/HyperFrames 集成范围内无可观测性指标埋点代码（渲染时长、CLI 失败率等未暴露）；仓库既有基础业务指标见 v2.4 条目，Prometheus 抓取配置仅覆盖既有端点。
  注（2026-10-25 13:07 深耕轮部分关闭：渲染时长与渲染失败计数（含 CLI 渲染非零退出）已埋点；--version 自3检失败仍无单独指标，留待后续。
- 滚动更新/零停机未验证：当前升级动作为停机更新（见升级指南），不支持滚动更新。

### 升级指南
- 停服务：docker compose down（或 kill 掉 java 进程）。
- 备份：./scripts/backup.sh（没备份不许往下走；备份恢复详见 docs/OPERATIONS.md 第 4 节）。
- 拉代码并重建：git pull 后 docker compose build && docker compose up -d（裸 jar 方式：替换 target/drama-factory-1.0.0.jar 后重启；Flyway 启动时自动执行 src/main/resources/db/migration/ 下未执行的迁移脚本）。
- 验证健康端点：curl -s http://localhost:8081/api/health 返回 200 且 JSON 状态正常。
- 回滚：./scripts/restore.sh backups/<备份目录>，换回旧 jar 重启（详见 docs/OPERATIONS.md 第 5 节）。

### Added（视频通道硬约束前置校验，2026-10-20）
- `docs/OPERATIONS.md` 新增「视频通道硬约束」一节：`constraints` 字段含义、提交前校验流程、违规 400 错误体格式（`VIDEO_CONSTRAINT_VIOLATION` + `channel`/`field`/`value`/`allowed`/`source`）、新通道补约束的步骤（出处必须能查证）。
- `README.md` 视频生成任务章节补硬约束说明 + 4 个模型 × 核验值的约束表（agnes-video-2.5-flash / minimax music-3.0 / hyperframes / htmlrender（chromium）），核验日期 2026-10-20，每个值带出处。
- 约束值必须能查到出处，不许瞎填；出处变更先更表再改通道 `constraints`。

### Added（深耕轮 2026-10-20 下午：成本账本看板）
- 后端：`CostLedgerService.summarizeTrend(days)`（[1,90]钳制，含今天，按日期升序，每天一条）；`CostLedgerService.budgetStatus()`（budgetTotalUsd/spentUsd/reservedUsd/usableUsd/utilizationPct/mode/enabled，构造器注入 BillingProperties，reserve() 复用抽出的 usableBudget(BudgetPolicy)）；`CostLedgerController` 新增 `GET /api/cost-ledger/trend?days`（默认14，非法400，超限由 service 钳制）、`GET /api/cost-ledger/budget`；`GET /api/cost-ledger/entries` 新增 limit 参数（默认100、最大500，非法400）。
- 前端：`cost-ledger.html` 看板页（导航"运行"→"成本账本"，shell.js 接入+nav.costLedger 中英 key）：预算卡（总额/已花费/冻结中/可用+使用率进度条，70%/90% 变色）、今日/近7天/累计条目/供应商数 KPI、14 天趋势 SVG 折线图（7/14/30 天切换，手写 SVG 零依赖）、按供应商条形、当天明细表（limit=20，状态 badge）；中英双语（PAGE_I18N 38+18 key）；Tabler 原生组件，无自创配色。
- 测试：新增 6 个测试文件 24 例全绿；修 1 个 dpsk 测试 bug（failedCountsTowardSpentAndRefundedCountsTowardNothing 误调 complete，应调 refund，spent 口径以实现为准）。
- 文档：README 成本账本节升级（含 5 接口表与看板截图）、OPERATIONS.md 查询接口表补齐 5 行、截图 docs/screenshots/cost-ledger/dashboard.png（36 条跨 14 天种子数据，亲眼验收：KPI/趋势/条形/明细全对）。
- 附带修：shell.js 补 nav.prompts 中英 key（历史遗漏致导航显示 raw key）。

### Added（深耕轮 2026-10-20 凌晨，lane A：skillhub / HyperFrames 渲染 / Toonflow 二阶段）
- 自有 SkillHub：`GET /api/skillhub/index`（hub=playhouse-skillhub，全部内置+社区收录 skills，来源标注"官方出品"/"社区收录"，含 installed 状态；异常时返回空列表 200，不 500）+ 前端 `skillhub.html`（搜索/来源筛选/一键安装到 data/skills/，挂载"运行"分组导航，Tabler 风格）。测试：SkillHubIndexControllerTest 5 例。
- HtmlRenderVideoProvider 双引擎：`drama.video.htmlrender.engine=chromium|hyperframes`（默认 chromium）；hyperframes 引擎经 `--version` 探活后走 `hyperframes render -c composition.html -o out/video.mp4 --resolution 1080p --fps <fps> --no-browser-gpu`，CLI 不可用/渲染失败自动降级 chromium 并打 warn。测试：HtmlRenderEngineSelectionTest 7 例。运维：`scripts/hyperframes_probe.sh`（JSON 探活，输出 engine 推荐值）。文档：docs/DEGRADATION.md 新增"htmlrender 双引擎"小节；application.yml/.env.example 新增配置说明。
- Toonflow 二阶段：docs/TOONFLOW_DEEPSEEK_PROVIDER_EVAL.md（deepSeek 语言 provider 评估：能力事实/与 LlmScriptService 对照/价格待官网核验/并入建议走可配置 language-provider 注册表）；3 组 toonflow skills 合规复审 docs/TOONFLOW_SKILLS_REVIEW_2026-10-20.md（difflib 相似度 0.911–0.982，_index.json rewritten 标注失实已纠正，3 个目录补上游 MIT LICENSE）。
- 4 个 Toonflow provider 描述符 QA：docs/TOONFLOW_DESCRIPTORS_QA_2026-10-20.md（schema 一致性逐项核验）。

### Added（v3.0 审核流，2026-10-19）
- 剧本两级审核状态机：DRAFT → PENDING_L1 →（驳回回 DRAFT / 通过去 PENDING_L2）→ APPROVED / REJECTED。
- 分镜单级审核状态机：DRAFT → PENDING → APPROVED / REJECTED。
- Run 执行门：VIDEO 步骤执行前要求该集剧本为 APPROVED，未过审则 run 置 PAUSED 等待（日志"等待剧本过审"），过审后 resume 继续。
- 审核历史审计：review_history 表记录每次流转（谁、何时、事件、意见、版本号），只增不删。
- 审核队列页：review.html（Tabler 1.6.1），待审列表 + 批准/驳回按钮 + 意见输入。
- 自审透明标记：ReviewDetailResponse.selfReviewed 字段，前端醒目提示，不硬拦截同人提交与审批。
- REST API：/api/projects/{projectId}/episodes/{episodeId}/review/submit|l1|l2|reject|history，/api/projects/{projectId}/review/queue。错误码：非法流转 409、跨项目 403、kind 不匹配 404。
- Flyway V18__review_flow.sql：review_item / review_history 表，episode 删除级联。
- 新增测试：ReviewServiceTest 29 例、ReviewApiTest 9 例、RunExecutorReviewGateTest 3 例。
- 设计文档：docs/REVIEW_FLOW.md。

### Fixed（深测轮 r3，2026-10-18）
- PromptRecipeService.apply 并发丢更新：改为 `@Modifying` 原子自增 + `@Transactional`。
- UsageService.summary/requests 的"不限时间"查询：`LocalDateTime.MIN` 在 H2 上比较返回空，改用 1970-01-01 下界常量 `TIME_BEGIN`。
- GlobalExceptionHandler 新增 `DataIntegrityViolationException` -> 400 映射（超长入参不再 500）。

### Tests（深测轮 r3，2026-10-18）

- 41 个 `*DeepTest`、652 用例；全量失败+错误从 73 降至 61。
- 新增 `PromptTemplateServiceDeepTest` / `RunServiceDeepTest` / `PipelineServiceDeepTest` / `ChatServiceDeepTest` / `PresetServiceDeepTest`。
- 对齐了一批测试期望与产品真实语义的偏差（见 `docs/DEEPTEST_ROUND_R3.md`）。

### Known issues

- SkillService.install 并发同版本安装存在竞态（唯一约束冲突），测试暂为串行幂等验证，产品侧修复待排期。

### Added

- v2.32「flaky 收尾：ffmpeg 输出竞态 + 中断异常收敛 + 重试逃逸」（2026-10-17，关闭 `docs/FLAKY_ROOT_CAUSE.md` §7 残余风险 ③④⑥）：
  - `FfmpegService.run()`：`reader.join(2000)` 固定上限等待改为有上限循环 join + `reader.isAlive()` 守卫，
    预算耗尽仍未结束时 message 标注"可能不完整"，不再静默截断；新增
    `FfmpegInterruptedException extends FfmpegException`（`(String, Throwable)` → `super(m, t, false)`），
    三处中断 throw 点收敛为专用异常。
  - `FinalCutService.withFfmpegRetry`：新增 `catch (FfmpegInterruptedException)` 直接 throw（终止重试）；
    sleep 中断改抛专用异常（修复 cause=null）；`catch (RuntimeException)` 收敛为保守 transient 重试。
  - `VideoTaskService.processDueTasks()`：新增 `catch (FfmpegInterruptedException)`——恢复中断标志 +
    `failOrRetry(task, msg, true)`。
  - 测试 9 例：`FfmpegOutputRaceV232Test` 3 例（2.621s）+ `FfmpegInterruptV232Test` 3 例（12.92s）+
    `FfmpegRetryEscapeV232Test` 3 例（14.12s）。
  - 文档：`docs/FLAKY_ROOT_CAUSE.md` §7/§2/§6/§8/§9 同步；`docs/dod-v2.32.md` 为发版对照。
  - 验证：新测试 9/9；回归 13 类 64/64（既有 10 类 55/55 基线），无回归；
    全量 `mvn -o verify` 本轮未跑（只跑受影响的 13 类；铁律：不降 JaCoCo 门禁），
    v2.31 全量数据（2013 例，14 失败 + 11 错误，Qwen 相关）保持原样。
  - 诚实声明：残余风险 ⑤（多实例 CAS 单飞）本轮仍未关闭，留待多实例场景再议；
    概率性场景（输出竞态 / 中断路径）9/9 通过为当前样本量观测结果，不宣称已彻底消除。
- 发版对照报告：`docs/dod-v2.32.md`。

- v2.31「flaky 收尾：退避预算上限 + 启动异常精细分类」（2026-10-17，dod-v2.28 排期"flaky 残留 2 处代码漏洞"全交付）：
  - `FinalCutService`：单次成片构建内所有 ffmpeg 步骤共享退避预算，
    `drama.ffmpeg.retry-total-budget-ms`（`FFMPEG_RETRY_TOTAL_BUDGET_MS`，默认 20000ms）；
    `claimRetryBackoff(AtomicLong, long)` 认领睡眠；预算耗尽后仍尝试剩余次数但不再睡眠；
    13 参 `@Autowired` 构造器 + 保留 12 参委托构造器（默认 20000L），既有测试零改动。
  - `FfmpegService.isTransientLaunchFailure(IOException)`：正向识别 cannot allocate memory /
    too many open files / resource temporarily unavailable 为瞬时，其余保持永久（v2.29 行为）。
  - 测试 17 例：`FinalCutRetryBudgetV231Test` 7 例 + `FfmpegLaunchClassifyV231Test` 10 例（含真实缺失二进制端到端）。
  - 文档：新增 `docs/FLAKY_ROOT_CAUSE.md`（诚实根因报告）；`docs/dod-v2.31.md` 为发版对照；
    `application.yml` + `docs/FFMPEG_RELIABILITY.md` + `docs/OPERATIONS.md` 同步新配置键。
  - 验证：新测试 17/17；既有相关 8 类 38/38 无回归；testFullPipeline 基线 2/2 → 修复后 10/10 通过（耗时 161.8s~320.5s；VM 高负载下依然全绿）；
    全量 verify 2013 例，14 失败 + 11 错误，8 skipped，JaCoCo BRANCH 83.94%（门禁 0.94，红）、LINE 86.41%（门禁 0.92，红）；missed branches 的 70.9%（458/646）来自他人在途新代码（NovAI 105、CanvasProjectService 71、Doubao 64、ShotVideoRouter 58、Painted 56、HtmlRender 45、Qwen 36、CanvasMigration 23）。
- 发版对照报告：`docs/dod-v2.31.md`。

- v2.30「OpenAPI 接口分组 + 依赖治理」（DoD 第 4 轮排期）：
  - OpenApiConfig.java 新增 4 个分组 Bean：runs（运行管理）、videos（视频生产）、scripts（剧本与内容）、admin（系统管理），分组文档地址是 /v3/api-docs/{group}，用 @Order(1~4) 把顺序钉死。
  - OpenApiDocsTest.java 新增 2 个测试：四组文档都能打开（200 且 openapi 以 3. 开头）；每组关键路径都对得上（runs 有 /api/runs；videos 有 /api/video-tasks/{taskId}；scripts 有 /api/projects；admin 有 /api/health）。
  - 22 个 controller 把缺的 @Tag/@Operation/@Parameter/@ApiResponse 注解补齐了，已有的不动，只补缺的；@Parameter 用的是 io.swagger.v3.oas.annotations.Parameter。
  - README.md 加了「API 文档」章节，写了 /v3/api-docs、/swagger-ui.html、四组文档地址表、鉴权说明和公网暴露提醒。
  - .github/dependabot.yml 里 maven 条目加了 reviewers ["Wanfeng1028"]；加了 ignore 规则，org.springdoc:* 的 >=3 大版本不升（springdoc 2.7+ 要 Spring 6.2，本项目 Spring Boot 3.3.5 是 Spring 6.1.x）；头注释写清了为啥钉死。
  - 新增 docs/DEPENDENCY_POLICY.md，写了依赖更新节奏（Dependabot 每周一，PR 上限 5，合入前 mvn -o test 全绿）、扫描与抽查、紧急漏洞响应流程（高危 24 小时内出修复分支）、高危依赖清单维护，附录 A 是真实直接依赖清单（13 项，mvn -o dependency:list 实测），附录 B 说明 springdoc 为啥钉死 2.6.0。
- v2.29「testFullPipeline flaky 根因歼灭 + E2E 加固」（根因：ffmpeg 瞬时失败 × 三处生产代码缺口）：
  - `FfmpegService.FfmpegException` 增加瞬时/永久分类（`isTransient()`）：超时、非零退出码（含 137/143）、ffprobe 失败等为瞬时；`无法启动命令`（二进制缺失）、参数编程错误为永久；旧构造器默认瞬时（保守策略）。`run()` 增加慢命令 warn（>30s）。
  - `FinalCutService`：concat/burn-subtitles/probe-duration 三步对瞬时失败有界重试（默认 3 次，退避 2000ms×attempt），永久失败直接 FAILED；配置 `drama.ffmpeg.retry-attempts` / `drama.ffmpeg.retry-backoff-ms`（env `FFMPEG_RETRY_ATTEMPTS`/`FFMPEG_RETRY_BACKOFF_MS`）。
  - `VideoTaskService`：`processDueTasks` 单飞保护（重叠调用跳过，防对真实 provider 重复提交）；`failOrRetry` 对非瞬时 FfmpegException 直接标记 FAILED（`[永久失败，不再重试]`），不再空转指数退避。
  - 指标：`dramafactory_ffmpeg_retries_total{operation,kind,result}`、`dramafactory_video_poll_skipped_total`。
  - 测试 8 批：`FfmpegExceptionClassificationTest`、`FinalCutFfmpegRetryTest`、`FinalCutRealFfmpegRetryTest`（真实 ffmpeg）、`ProcessDueTasksSingleFlightTest`、`VideoTaskFailFastTest`、`VideoPipelineResilienceE2eTest`（E2E 韧性）、`FfmpegRetryMetricsTest`、`FfmpegServiceTest` 补强（probe/extractPoster）。
  - 脚本：`scripts/verify-flaky-fix.sh`（回归验证）、`scripts/ffmpeg-chaos-drill.sh`（故障演练：kill -9 ffmpeg 后任务经重试恢复）。
- 发版对照报告：`docs/dod-v2.29.md`。
- v2.29 第二阶段「覆盖率收尾 + flaky 根因验证」（2026-10-17）：
  - 基线：干净环境全量 1921 例，BRANCH 84.07% / LINE 87.95%（门禁已红，缺口 65.8% 来自他人在途新代码——视频管线轮次 + agent-canvas，按铁律不代写）。
  - 新增 11 个 *V229* 测试文件共 75 例（dpsk 生成），终版全量 1996 例全部通过，无新增失败：
    AuthProxyControllerV229Test(13) / V229D2Test(6)、LlmScriptServiceV229Test(4) / V229D2Test(4)、
    JwtAuthFilterV229Test(9)、SettingsEnvPostProcessorV229Test(2 skipped)、EpisodeServiceV229Test(7)、
    PromptTemplateServiceV229Test(8)、CharacterServiceV229Test(10)、RunExecutorV229Test(9) / V229D2Test(3)。
  - 覆盖率：BRANCH 84.07%→85.00%（+0.93%）、LINE 87.95%→88.75%（+0.80%）；3 个类清零（JwtAuthFilter/CharacterService/PromptTemplateService）。
  - flaky 验证结论：基本歼灭，有低概率残留（testFullPipeline 本轮 25.31s 通过；2 处结构性残留：退避总额无上限、pb.start IOException 误判永久）。
  - 诚实声明：门禁仍红（BRANCH 0.85/LINE 0.89）；Qwen 6 个测试类红（他人在途改动未同步）；11 处不可达分支已论证（见报告）。
  - 发版对照报告：`docs/dod-v2.29.md`（本轮重写）。

### Docs
- 新增 `docs/FFMPEG_RELIABILITY.md`（可靠性设计注记：分类表/重试矩阵/排障/告警）；`docs/OPERATIONS.md` 新增 8.7/8.8（ffmpeg 排障/单飞说明/告警示例）；`docs/DEGRADATION.md` ffmpeg 小节更新；README 增加可靠性小节。

## [v2.26] - 2026-10-16

### Added
- 账号体系 P0#3「auth-service 生产级补强」（dod-v2.25 排期第 1、3 项）：
  - Flyway 版本化迁移：`auth-service` 接入 `flyway-core`，`ddl-auto: update`→`validate`，`V1__baseline.sql` 由真实 Hibernate DDL 逐字导出（三表 + 真实 FK 约束名），`baseline-on-migrate: true` 兼容老库；`AuthFlywayMigrationTest` 2 例。
  - 指标：`actuator` + `micrometer-registry-prometheus`，`/actuator/prometheus`（无鉴权，靠网络隔离）；`AuthMetrics`（注册/登录/刷新/OAuth 回调 Counter + 用户数/活跃会话 Gauge 快照，`@Scheduled(30s)`）；`prometheus/rules/auth-service.yml` 3 条告警（5xx 错误率/实例宕机/登录失败激增）。
  - 备份恢复：`scripts/backup-auth.sh`（在线/离线双模式）+ `scripts/restore-auth.sh`（停服检查/manifest sha256/恢复前快照/完整性校验）+ `docs/OPERATIONS-AUTH.md` 运维手册。
  - 应用内在线备份端点：`POST /api/auth/admin/backup`（ADMIN 专用，`BackupService` 经 `JdbcTemplate` 执行 `BACKUP TO`，路径服务端生成防穿越）；修复 H2 嵌入式独占文件锁导致独立进程无法在线备份的真问题（主服务 `backup.sh` 同样受影响）。
- 测试：auth-service 全量 25 例通过（16 旧 + 2 Flyway + 4 指标 + 3 备份端点）。
- 发版对照报告：`docs/dod-v2.26.md`。

### Docs
- 新增 `docs/OPERATIONS-AUTH.md`（auth-service 运维手册）；`docs/dod-v2.26.md` 发版对照报告。

### Added
- AI MV 模式 v1：`POST /api/mv`（创建）/ `{id}/lyrics`（DeepSeek 作词）/ `{id}/compose`（BYOK 作曲）/ `{id}/storyboard`（分镜）/ `{id}/render`（wan2.5+ffmpeg 合成）/ `{id}/status`（轮询）/ `{id}/video` / `{id}/audio`；Run 类型新增 MV（作词→作曲→分镜→视频生成→剪辑→质检 6 步骤进时间线）；AgentType 新增 LYRICS/COMPOSE；AceStepMusicProvider（开源作曲渠道 BYOK）；mv.html 5 步创作页（深浅主题）；作曲渠道调研 docs/mv-music-providers.md。

## [v1.0] - 2026-10-14

### Added
- BYOK 真实生成调用（v1.0 最后一块）：`POST /api/byok/generate`（IMAGE/MUSIC/AVATAR 三模块，服务端阻塞轮询后落盘，返回本地 URL）+ `GET /api/byok/file/{module}/{filename}`（防路径穿越）。
- DashScope 万相文生图：`wan2.5-t2i-preview`，async 提交+轮询（`X-DashScope-Async: enable`）；连接探针 `GET /tasks/__connectivity_probe__`（零费用，404=密钥有效/401=密钥无效）；真实出图已验证（1024×1024 PNG）。
- MiniMax 音乐：`music-3.0` 同步调用（`base_resp.status_code==0` 成功）；探针非法 model 负向探测（4xx=密钥有效，零费用）。注：官方已公告 2026-08 起不对新用户开放、免费档停服，仅存量付费用户可用。
- D-ID 数字人：talks 提交+轮询（文案驱动 TTS 或音频 URL 二选一，人物图需公网 URL）；探针 `GET /credits`（零费用）。
- Key 解析顺序：通道卡片 → 设置中心（`dashscope.api-key`/`minimax.api-key`/`did.api-key`）→ surrogate（仅 DashScope，沿用现有白名单）。
- 前端三页接真实接口：生成中禁用按钮+进度提示，失败显示脱敏错误；图片页预览、音乐页音频播放器、数字人页视频播放器；空 Key 保持诚实空状态。
- 单元/契约测试 29 例（录制回放 + MockMvc），总数 515→544 全绿。

## [v2.9] - 2026-10-14

### Added
- AuthProxyController 可测性重构（生产级补强第 8 轮）：构造器内写死的 HttpClient 改为构造器注入（新增包可见重载供测试，原 public 构造器委托 + `@Autowired` 显式标记）；默认客户端配置（connectTimeout 5s、Redirect.NEVER）零变更。
- AuthProxyControllerTest 新建 20 例：T1~T10（透传/query/hop-by-hop 过滤/df_at cookie 补 Authorization/头优先于 cookie/refresh 401 与 body 替换/GET noBody/上游 500 透传/尾斜杠）+ T11~T20（login token 剥离写 cookie/expiresIn 缺失默认 3600/非 JSON 转 502/400 原样透传/oauth 回调剥离/logout 清 cookie/logout 500 透传/send 抛 IOException/InterruptedException/读 body 抛 IOException）；上游用 JDK HttpServer 绑 `::1` 随机端口。
- 分支覆盖冲 55% 达成：全量分支 52.7%→57.3%、行 71.0%→73.6%；AuthProxyController 单类分支 0%→79.5%、行 97.8%、方法 100%；测试总数 336→356 全绿。
- 覆盖率门禁收紧：LINE 0.65→0.70、BRANCH 0.45→0.55（棘轮，只升不降）。

### Docs
- 新增 docs/dod-v2.9.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.10 路线。

## [v2.8] - 2026-10-14

### Added
- 分支覆盖冲 45%（生产级补强第 7 轮）：新增 104 例测试，总数 232→336，`mvn -o verify` 全绿；行覆盖 58.5%→71.0%、分支 37.5%→52.7%。
- 覆盖率门禁收紧：JaCoCo check 新增 BRANCH 0.45；LINE 0.55→0.65（棘轮，只升不降）。
- LlmScriptServiceTest 8→34：validate() 9 例、parseScenes() 12 例、buildUserContent() 5 例（含捕获 body 断言 user 文本的 CapturingLlmScriptService）。
- RunServiceTest 15→33：planPreview() 12 例、createRun/pause/resume 6 例。
- ScriptSplitterServiceTest 15→35：parse/strip 6 例、replaceShots() 14 例。
- RunExecutorTest 10→36：advanceRun 与各 step 异常分支 13 例、QC 自动门/checkVideoStep/finalize 13 例（含 @TempDir 真实文件 QC 通过用例）。
- ProviderServiceProbeTest 新建 14 例：testConnection() 10 例（模块/名称匹配/鉴权失败透传/checkedAt 格式）、maskKey() 4 例。

### Docs
- 新增 docs/dod-v2.8.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.9 路线。

## [v2.7] - 2026-10-14


### Added
- stats() 多用户口径：ProjectService.stats() / RunService.stats() 按当前用户隔离（ownerId；开放模式全 local，行为与旧全局口径一致）；DramaProjectRepository 新增 countByOwnerId；RunService 构造器新增 CurrentUser/DramaProjectRepository 注入；@Operation 文案同步；API 路径与响应字段零变更。
- LlmTransport 可测性重构：ProxySpec + parseProxy/resolveProxy/toHttpHost/buildRequestConfig/buildPost 纯函数 + HttpExecutor 函数式 seam；4 参数编排逻辑（含预先代理认证）零变更。
- 测试 40 例：LlmTransportTest 17（代理纯函数/请求构建/状态码与异常契约/密码不泄露）、MockVideoProviderTest 6、RunExecutorTest 10（Mockito 编排：审批门/异常→FAILED/VIDEO 跨 tick/finalize 汇总/tick 吞异常）、StatsIsolationTest 2（MockMvc 多用户隔离）、CameraMoveTest 5。
- 覆盖率门禁收紧：JaCoCo minimum 0.51→0.55；实测行覆盖 51.3%→58.5%、分支 31.0%→37.5%。

### Changed
- CameraMove.fromLabel：非法非空标签由返回 null 改为抛 IllegalArgumentException（与 ShotSize.fromLabel 一致）；null/空白仍返回 null。parseShotsJson 路径非法运镜现在报错而非静默 null 落库。

### Docs
- 新增 docs/dod-v2.7.md 发版对照报告；docs/COVERAGE.md 更新基线/缺口表/v2.8 路线。

## [v2.6] - 2026-10-14

### Added
- 多用户地基：`DramaProject.ownerId`（JWT sub；开放模式回退 `local`）+ Flyway `V6__owner_id.sql`（老数据回填 `local`，列 NOT NULL）+ `config/CurrentUser` + 项目 API 全链路归属隔离（越权访问 403 `ForbiddenException`）；`ProjectResponse` 新增 `ownerId` 字段。
- 日志脱敏：新增 `util/SecretMasker`（纯函数）+ 11 例单测；`docs/SECURITY_DATA.md`（敏感数据清单/存储策略/日志脱敏/删除策略/缺口排期；经 grep 全量审计确认无直接打印密钥的日志）。
- 降级策略：新增 `docs/DEGRADATION.md`（6 子系统降级矩阵；ffmpeg 缺失与 auth-service 不可达诚实标注为"当前无降级"，不虚构）。
- 覆盖率门禁：JaCoCo 0.8.12 接入 pom（prepare-agent/report/check），`mvn verify` 强制行覆盖 ≥51%（实测 51.3%，基线 49.6%）；新增 `docs/COVERAGE.md`（目标/口径/基线/缺口表/v2.7 路线）。
- 测试：新增 36 例——`ProjectOwnerIsolationTest`（3）、`SecretMaskerTest`（11）、`ScriptSplitterServiceTest`（15，含一次行为不变重构抽出 `parseShotsJson` 可测缝）、`EpisodeStatusFlowServiceTest`（7）。

### Docs
- 新增 `docs/dod-v2.6.md` 发版对照报告；`docs/SECURITY_DATA.md`、`docs/DEGRADATION.md`、`docs/COVERAGE.md`。

## [v2.5] - 2026-10-14

### Added
- OpenAPI 文档：springdoc-openapi 2.6.0（Boot 3.3.x 官方兼容版本），GET /v3/api-docs（JSON/YAML）与 /swagger-ui.html，全部 Controller 补 @Tag/@Operation（注：注解在 v2.5 同轮另一批交付，此处先记条目）。
- 依赖自动更新：新增 .github/dependabot.yml（maven / github-actions / docker，每周一）。
- 运维手册实质补齐：docs/OPERATIONS.md 由 stub 补成完整手册（部署/配置/备份恢复/升级/日志/监控告警/API 文档/故障排查/已知限制）。
- 测试：新增 OpenApiDocsTest（/v3/api-docs 实质断言 + swagger-ui 可达）。

### Docs
- 新增 docs/dod-v2.5.md 发版对照报告。

## [v2.4] - 2026-10-14

### Added
- 指标采集：接入 Micrometer + Prometheus，暴露 `GET /actuator/prometheus`（无鉴权，`JwtAuthFilter` 仅拦 `/api/**`）。
- 业务指标：新增 7 类业务指标——`dramafactory_video_tasks_queued`、`dramafactory_runs_by_status{status}`（8 个 `RunStatus` 小写标签）、`dramafactory_runs_waiting_approval`、`dramafactory_script_llm_calls_total{model,result}`、`dramafactory_script_llm_duration_seconds{model}`、`dramafactory_finalcut_builds_total{result}`、`dramafactory_finalcut_build_duration_seconds`。Gauge 由 `@Scheduled(30s)` 刷新内存快照，抓取时不打 DB。
- 告警：新增 `prometheus/rules/drama-factory.yml`，含 `DramaFactoryHighErrorRate`（critical）、`DramaFactoryVideoQueueBacklog`、`DramaFactoryApprovalStuck`、`DramaFactoryRunFailures`（warning）。
- 抓取配置：新增 `prometheus/prometheus.yml` 示例（job `drama-factory`，15s 间隔，指向 `localhost:8081/actuator/prometheus`）。
- 备份恢复：新增 `scripts/backup.sh`（H2 `BACKUP TO` 在线备份 + `media/`、`settings/` 归档 + manifest + 保留最近 7 个）与 `scripts/restore.sh`（运行检查 → sha256 校验 → 恢复前快照 → H2 `Restore` → media/settings 恢复 → 冒烟），均已真实跑通。
- 运维手册：新增 `docs/OPERATIONS.md`（部署/备份恢复/升级/日志轮转/监控告警/6 条故障排查/已知限制）。
- 测试：新增 `MetricsEndpointTest` 3 例。

### Docs
- 初建 `CHANGELOG.md`，回填 v2 至 v2.3 历史。
- 新增 `docs/dod-v2.4.md` 发版对照报告。

## [v2.3] - 历史版本

### Added
- AI 编剧引擎：接入 DeepSeek-V4-Flash 真实模型调用。

## [v2.2] - 历史版本

### Added
- 结构化日志输出。
- request_id 贯穿请求链路，便于按 ID 检索。
- 接入 Resilience4j 熔断与限流（单实例内存级）。
- 新增 Docker Compose 部署配置。

## [v2.1] - 历史版本

### Added
- 接入 Flyway 数据库迁移。
- 提交幂等支持。
- 优雅关闭。

## [v2] - 历史版本

### Added
- 短剧生产管线：分镜、视频任务状态机、ffmpeg 剪辑。
- 生产看板。
