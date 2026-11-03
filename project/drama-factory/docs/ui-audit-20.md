# UI 审计 #20（drama-factory 全页面走查）

> 结论先行：21 个页面 × 深浅两主题共 42 张截图全部亲眼走查。**P0 无；P1 发现 2 个（设置页主题脚本缺失、登录页主按钮颜色违规）；P2 发现 7 个。** 黑名单（毛玻璃/渐变紫/emoji 图标/字母 logo/暖黄变量）全站零出现；深浅主题反转一致；空状态文案基本克制。

- 审计基线：`docs/DESIGN_SYSTEM.md` v1 + hallmark 去 AI 味标准
- 审计对象：`feat/ui-audit-dod` 分支 @ `60c7fad`（= main 最新）
- 截图方式：真实服务（worktree 构建的 jar，端口 8081）+ Playwright；静态走磁盘、`/api/*` 经 Node 直连真实服务；仅 `/api/auth/me` 被 stub（外部账号微服务本机不存在，报告中已注明；其余 API 全部真实返回，空状态为真实空库状态）
- 证据截图：`docs/audit-20-shots/`

## P1（必须修，影响主题/规范一致性）

### P1-1 settings.html 缺 `<head>` 主题脚本 —— 设置页在浅色模式下仍渲染深色
- 位置：`static/settings.html`（全站 22 个 HTML 中唯一缺失）
- 证据：`docs/audit-20-shots/settings-light.png` —— localStorage 已设 `light`，页面仍为深色
- 依据：DESIGN_SYSTEM.md §10 "每个 HTML 必须在 `<head>` 顶部内联主题脚本"
- 根因：`:root` 默认即暗色变量，缺脚本时 `data-bs-theme` 永远落不到 `light`
- 修复：把与其他 21 页相同的 1 行内联脚本补到 `<head>` 顶部（约 1 分钟工作量）

### P1-2 登录/注册页主按钮为蓝色 `#4176E6`，违反"墨色主按钮"规范
- 位置：`static/auth.css:26` —— `.auth-page .btn-primary { background: #4176E6; }`
- 证据：`docs/audit-20-shots/login-light.png`（深色主题下同样蓝色）
- 依据：DESIGN_SYSTEM.md §4 —— 主按钮墨色 pill（亮色 `#111` 底白字，暗色反转白底黑字）；色板中无蓝色
- 说明：第三方登录按钮（Google/Apple/GitHub 一竖线排列，图标标准）没问题；仅主按钮颜色违规
- 修复：改为 `var(--ink)` / `var(--ink-text)` 随主题反转（约 5 分钟工作量）

## P2（建议修，不阻塞提测）

### P2-1 pipeline.html 统计占位用 `-`，规范要求 `—`（em dash）
- 位置：`static/pipeline.html:42/50/58`（`statShotRate` / `statTaskRate` / `statRenderTime` 初始占位）
- 证据：`docs/audit-20-shots/pipeline-light.png`（"分镜完成率/任务成功率/累计渲染时长"上方为半字线）
- 依据：DESIGN_SYSTEM.md §6 "空值/未知：一律显示 `—`（em dash）"；同站 `index.html` 的 `ws-status-strip` 用的就是 em dash，属站内不一致

### P2-2 images.html 原生文件选择器显示英文 "Choose File / No file chosen"
- 位置：`static/images.html` 参考图上传 `<input type="file">`
- 证据：`docs/audit-20-shots/images-light.png`
- 中文产品页出现浏览器默认英文文案，观感未本地化；建议用 label 按钮样式包裹隐藏原生 input（与其他页"安静款按钮"风格统一）

### P2-3 上下文栏：剧集下拉零选项时渲染为空白方块
- 位置：`static/index.html`（`#episodeSelect`）、`static/chat.js`（`loadEpisodes` 提前 return 时不写占位）
- 证据：`docs/audit-20-shots/zoom-context.png`（"暂无项目"下拉旁的空白方块即零选项 select）
- 修复：无数据时写入 `<option value="">暂无剧集</option>` 或隐藏该下拉

### P2-4 oauth-callback 错误态是死胡同（无返回入口）
- 位置：`static/oauth-callback.html:31-33`（`授权信息不完整` / `该渠道未配置` 仅改文案）
- 证据：`docs/audit-20-shots/oauth-callback-light.png`
- 修复：错误态加"返回登录页"安静款链接（1 行）

### P2-5 usage 页口径：总请求数显示 `0`，成本显示 `—`
- 位置：`static/usage.html` 概览卡片
- 证据：`docs/audit-20-shots/usage-light.png`
- "Token 与费用 · 仅统计真实发生的调用"文案诚实，但 0 请求配 — 成本易被误读为"统计缺失"；建议卡片下加注"0 次调用时成本记 —"或统一为 `—`

### P2-6 agents 页文案缺量词："管理 5 专用 Agent"
- 位置：`static/agents.html` 副标题
- 改为"管理 5 个专用 Agent"

### P2-7 auth.css 登录页输入框/第三方按钮带 `box-shadow`
- 位置：`static/auth.css:18/20/32`（4 处）
- 依据：DESIGN_SYSTEM.md §9 黑名单第 6 条"卡片阴影（box-shadow 只允许 none）"
- 登录页为独立视觉区（auth.css 独立），且阴影极淡（`rgba(20,20,40,.05)`），定级 P2；如追求全站零阴影可一并去掉

## 通过项（抽查结论）

- 深浅主题：20/21 页反转正确（`index-dark.png`、`canvas-dark.png`、`mv-dark.png`、`pipeline-dark.png`、`login-dark.png` 亲眼确认）；色板无偏暖/偏蓝；卡片实色+发丝边框零阴影
- 空状态：runs/tasks/finals/qc/images/music/avatar/canvas/storyboard 文案克制（"暂无运行，点击下方按钮创建第一条"等），均配安静款行动按钮，无装饰插画
- 按钮铁律：抽查 storyboard（7 按钮仅 1 pill 主按钮"AI 生成剧本"）、mv、canvas 均合规
- 图标：全站 Lucide，无 emoji 当图标；logo 为场记板 SVG（currentColor），无字母 logo
- 文案红线：无"工作台"、无 Unleash/Empower 类 polished 词；"不断产线"经核对源码无笔误（截图小字误读，已排除）
- 鉴权相关诚实态：`account.html` 在账号微服务不可用时显示"账号服务暂不可用"（红字），不编造

## 未覆盖

- canvas 分镜编辑器弹窗（需真实项目数据，本轮为空库）、run-detail 有数据态（需 run id）、⌘K 命令面板展开态：建议有数据后补一轮走查
- 移动端窄屏未测（产品为桌面 Harness 定位，提测前可暂缓）
