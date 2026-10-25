# Drama Factory UI 设计体系（v1）

> 自然中性，不刻意做暖、不做旧、不做深蓝紫。一切页面照此验收，有据可查。
> 竞品（pix6）只借功能与信息架构，**视觉零借用**。

## 1. 色板（Design Tokens）

CSS 变量定义在 `static/app.css`（`:root` = 暗色默认，`[data-bs-theme="light"]` = 亮色）。

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--bg` | `#FFFFFF` 纯白 | `#16161A` 中性灰黑 | 页面底 |
| `--bg-elev` | `#F7F7F8` 极淡灰 | `#1C1C21` | 侧边栏 |
| `--surface` | `#FFFFFF` | `#202027` | 卡片底 |
| `--surface-2` | `#F4F4F5` | `#26262E` | 输入框/条形轨道 |
| `--border` | `rgba(0,0,0,.08)` 发丝 | `rgba(255,255,255,.08)` 发丝 | 边框 |
| `--border-soft` | `rgba(0,0,0,.06)` | `rgba(255,255,255,.06)` | 弱分隔 |
| `--text` | `#111111` | `#EDEDEF` | 主文字 |
| `--text-2` | `#555555` | `#A1A1AA` | 次文字 |
| `--text-3` | `#999999` | `#71717A` | 弱文字/占位 |
| `--ink` | `#111111` | `#FFFFFF` | 主按钮底（随主题反转） |
| `--ink-text` | `#FFFFFF` | `#111111` | 主按钮字 |
| `--green` / `--amber` / `--red` | `#16803C` / `#B45309` / `#DC2626` | `#4ADE80` / `#FBBF24` / `#F87171` | 成功/警告/危险 |

原则：**不偏暖、不偏蓝**。暖黄变量（`#F8F7F4`、`#F1EFEA`、`#2B2620` 等）已全部删除，发现即 bug。

## 2. 字体

- 正文：系统字体栈（`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`）。
- 等宽：`--mono`（`ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace`）——仅用于时间码、API 地址、Key 掩码、快捷键、数字。

## 3. 间距与圆角

- 页面：`.page` 内边距 24px；卡片 `.card` 内边距 `16px 20px`，圆角 `10px`（`--radius: 8px`，卡片 10px）。
- 按钮 pill：`border-radius: 999px`，主按钮 `padding: 8px 20px`。
- 输入框/下拉：圆角 `8px`，`padding: 8px 12px`。
- 卡片：**实色 + 发丝边框，零阴影**（`box-shadow: none`）。

## 4. 按钮规范（两款）

1. **主按钮** `.btn.btn-primary`：墨色 pill（亮色 `#111` 底白字，暗色反转为白底黑字），`font-weight: 500`。
2. **安静款** `.btn.btn-quiet`：透明底、`--text-2` 字，hover 时 `--surface` 底。

**铁律：每页最多一个 pill 主按钮**，其余操作（取消/编辑/删除/次级）全用安静款。
危险操作可用 `.btn-danger`（文字按钮样式，不做 pill）。

## 5. 图标

- 只用 **Lucide**（`/vendor/lucide.min.js` 本地包），`<i data-lucide="…">` + `lucide.createIcons()`。
- **禁用**：emoji 当图标、字母首字母当 logo/头像。

## 6. Badge 与状态色

- `.badge`：实色淡底（`--accent-soft`），`font-weight: 550`，无辉光。
- 状态：成功 `--green`、警告 `--amber`、危险 `--red`、进行中 `--accent`。
- 空值/未知：一律显示 `—`（em dash），**不许编数字、不许用假数据画图表**。

## 7. 空状态文案风格

- 一句克制陈述，不煽情、不 polished 四字词。例：
  - "还没有接入图片模型"
  - "暂无供应商，点击右上添加"
  - "暂无用量数据，先跑一次运行吧"
- 配一个安静款行动按钮（如"去通道管理添加 API"），不许放装饰性插画。

## 8. 文案红线

禁用：Unleash / Empower / Seamless / Next-generation 及其四字中文 polished 对应词。
禁用"工作台"一词（产品定位是 Harness）。

## 9. 黑名单（出现即 bug）

1. `backdrop-filter` / 玻璃拟态（全站零出现）
2. 渐变紫、深蓝紫调（`#6xxx`/`#7xxx` 蓝紫、`linear-gradient` 彩色）
3. emoji 当图标
4. 字母首字母 logo/头像（默认用几何/插画头像）
5. 暖黄/做旧配色变量
6. 卡片阴影（`box-shadow` 只允许 `none`）
7. 假数据、假成功态（未知显示 `—`；未实现的功能明确告知，不许点出假成功）

## 10. 主题切换

- `document.documentElement` 的 `data-bs-theme`（`light`/`dark`），`localStorage` key `df-theme`。
- 每个 HTML 必须在 `<head>` 顶部内联主题脚本（防闪烁），与其他页一致：
  ```html
  <script>try{var t=localStorage.getItem('df-theme');document.documentElement.setAttribute('data-bs-theme',t==='dark'?'dark':'light');}catch(e){document.documentElement.setAttribute('data-bs-theme','light');}</script>
  ```
- logo 用 `currentColor`，28px 下深浅主题都清晰。

## 11. 官方 Skill 库页设计层 v1（2026-10-25，Flash 路）
- 文件：static/official-skills-design-v1.css，只覆盖，app.css 之后引用。
- 视觉逻辑：目录卡台账（纯白底、发丝边框、10px 圆角、零阴影；标题 16px/600、描述 14px、元信息 13px；操作区顶部发丝线；搜索框 8px 圆角、聚焦墨色边框）。
- 截图：docs/screenshots/official-skills-v1.png（真实服务 + 1373 条真实数据）。

## 12. 提示词库页设计层 v1（2026-10-25，Flash 路）
- 文件：static/prompts-design-v1.css，只覆盖，app.css 之后引用。
- 视觉逻辑：提示词档案柜（柜签 kicker、索引抽屉搜索与标签芯片、同行等高档案袋卡片、底部借阅条沉底对齐、详情卡为展开的档案全文，等宽字体换行）。
- 截图：docs/screenshots/prompts-design-v1.png（真实服务 + 真实提示词库数据）。

## 13. 任务队列页设计层 v1（2026-10-25，Flash 路）
- 文件：static/tasks-design-v1.css，只覆盖，app.css 与 harness.css 之后引用。
- 视觉逻辑：任务台账（筛选卡是台账眉、任务行是台账行、状态徽标是台账戳、进度条是细线尺、计数是台账行数；页头 20px/700、卡片 10px 圆角零阴影、行距 14px、徽标 12px/600）。
- 截图：docs/screenshots/tasks-design-v1.png（真实服务 + 真实任务数据）。
- 已知保留：行内样式已定的行底线、任务名与元数据字号颜色、进度条宽高、百分比字号颜色不在本层改动范围。

## 14. 运行列表页设计层 v1（2026-10-25，Flash 路）
- 文件：static/runs-design-v1.css，只覆盖，app.css 与 harness.css 之后引用。
- 视觉逻辑：运行台账（页头是台账眉、统计条是台账总计、运行行是台账行、状态徽标是台账戳、新建运行向导是台账录入单；页头 20px/700、统计条 13px/600 加发丝底线、运行行 16px 行距、目标 15px/700、徽标 12px/600）。
- 截图：docs/screenshots/runs-design-v1.png（真实服务 + 真实运行数据）。
- 已知保留：本层不改布局（行底线、悬停底色、徽标底色与文字色维持 harness.css 原样）。

## 15. 运行详情页设计层 v1（2026-10-25，Flash 路）
- 文件：static/run-detail-design-v1.css，只覆盖，app.css 与 harness.css 之后引用。
- 视觉逻辑：运行台账（页头是台账眉、元数据行是台账案头、章节标题是台账分册、步骤是台账行、产物卡是台账附件、汇总卡是台账结单、抽屉标题是台账附注；页头 20px/700、章节标题 16px/700、步骤名 15px/700、步骤行距 16px、产物卡与汇总卡 10px 圆角零阴影发丝边）。
- 截图：docs/screenshots/run-detail-design-v1.png（真实服务 + 真实运行数据）。
- 已知保留：本层不改布局（时间线竖线、步骤圆点色、失败步骤红线、抽屉位置与动画维持 harness.css 原样）。

## 16. 分镜板页设计层 v1（2026-10-25，Flash 路）
- 文件：static/storyboard-design-v1.css，只覆盖，app.css 之后引用（本页不引用 harness.css）。
- 视觉逻辑：分镜台账（页头是台账眉、筛选下拉是台账案头、分镜行是台账行、镜号是台账序号、描述是台账正文、对白是台账附注、元数据是台账小字；页头 20px/700、筛选标签 12px/600 次文字、下拉与次按钮 8px 圆角、分镜行上下 16px、镜号等宽 12px 弱文字、描述 15px/700、对白 13px 次文字、元数据 12px 弱文字、状态戳 12px/600）。
- 截图：docs/screenshots/storyboard-design-v1.png（真实服务 + 真实分镜数据）。
- 已知保留：本层不改布局（分镜行 flex 结构、操作按钮排列、表单面板结构维持 app.css 原样）；本轮曾先做生产看板页设计层，后因该页统计区与管线表在 app.css 里已有故意的编辑杂志式设计、台账层只能半覆盖而不协调，已全部撤回未提交，改做分镜板页。

## 17. 用量统计页设计层 v1（2026-10-25，Flash 路）
- 文件：static/usage-design-v1.css，只覆盖，usage.html 内联 style 块之后引用（该页内联 style 在样式表链接之后，放最后才能生效）。
- 视觉逻辑：用量台账（页头是台账眉、筛选是台账案头、KPI 卡是台账格、趋势条是台账尺、数据表是台账明细；页头 20px/700、章节标题 16px/700、KPI 大数字 24px/700 等宽数字、KPI 卡 10px 圆角零阴影、表头 12px/600、单元格 13px 等宽数字）。
- 截图：docs/screenshots/usage-design-v1.png（真实服务 + 真实用量数据）。
- 已知保留：本层不改布局（KPI 网格、趋势条结构、数据表列维持原样）。


## 18. Skill 市场页设计层 v1（2026-10-25，Flash 路）
- 文件：static/skills-design-v1.css，只覆盖，skills.html 在 app.css 之后引用（本页不引用 harness.css）。
- 视觉逻辑：技能台账（页头是台账眉、搜索卡是台账案头、市场卡是台账格、徽标是台账戳、已安装行是台账已领单；页头 20px/700、卡片标题 16px/700、市场卡片名 15px/700、表单标签 12px/600、输入框 13px 8px 圆角、卡片 10px 圆角零阴影）。
- 截图：docs/screenshots/skills-design-v1.png（真实服务 + 真实技能数据）。
- 已知保留：本层不改布局；已安装行底线颜色由 JS 行内 !important 写死，本层不硬压。

## 19. Agent 机队页设计层 v1（2026-10-25，Flash 路）
- 文件：static/agents-design-v1.css，只覆盖，agents.html 在 head 内联 style 块之后引用（本页不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：机队台账（页头是台账眉、通道卡是台账案头、供应商区是台账名录、Agent 卡是台账格、元数据行是台账明细、模板全文是台账附录；页头 20px/700、卡片标题 16px/700、徽标 12px/600、元数据键 12px/600、值 13px、卡片 10px 圆角零阴影）。
- 截图：docs/screenshots/agents-design-v1.png（真实服务 + 真实 Agent 数据）。
- 已知保留：本层不改布局；页内“管理 5 个专用 Agent”文案与实际 7 条数据不一致属既有文案问题，本层未动。
- 已关闭（2026-10-26，Flash 路）：副标题 5→7 纠错已落地（agents.html + agents.js 中英文案），AgentsSubtitleCountTest 锁死副标题数字与 AgentType 枚举项数一致。

## 20. 快捷工具页设计层 v1（2026-10-25，Flash 路）
- 文件：static/tools-design-v1.css，只覆盖，tools.html 在 harness.css 之后引用（本页无内联 style 块，不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：工具台账（页头是台账眉、工具卡是台账格、表单是台账录入行、操作记录表是台账明细、状态戳是台账戳；页头 20px/700、卡片标题 16px/700、表单标签 12px/600、输入框 13px 8px 圆角、表头 12px/600、单元格 13px、卡片 10px 圆角零阴影）。
- 截图：docs/screenshots/tools-design-v1.png（真实服务 + 真实项目数据，资产与操作记录为真实空态）。
- 已知保留：本层不改布局；状态戳绿/红两档因空记录未在截图里出现。

## 21. 设置中心页设计层 v1（2026-10-25，Flash 路）
- 文件：static/settings-design-v1.css，只覆盖，settings.html 在 harness.css 之后引用（不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：配置台账（页头是台账眉、配置卡是台账格、表单行是台账录入行、开关文字是台账注脚；页头 20px/700、副标题 13px 次文字、卡片标题 16px/700、徽标 12px/600、主按钮 13px/600 8px 圆角、表单行上下 16px 发丝底线、表单标签 12px/600 次文字、输入框与下拉 13px 8px 圆角、卡片 10px 圆角零阴影）。
- 截图：docs/screenshots/settings-design-v1.png（真实服务 + 真实配置数据）。
- 已知保留：本层不改布局；模型稿 7 处把 --hairline（颜色 token）误当边框宽度写进简写，编排统一修正为 1px solid（颜色沿用模型稿的 --border-soft/--red）；重试按钮 #settings-retry 未入本层，沿用原次按钮样式。

## 22. 工作台首页设计层 v1（2026-10-25，Flash 路）
- 文件：static/index-design-v1.css，只覆盖，index.html 在 harness.css 之后引用（不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：工作台账（问候语是台账眉、状态条是台账总计行、新建面板是台账录入格、最近动态是台账明细；问候语 20px/700、状态条 13px 次文字、下拉 13px 8px 圆角、新建面板 surface 底发丝边 10px 圆角零阴影、新建块标题 15px/700、输入框 13px 8px 圆角、小按钮 12px/600 8px 圆角、对话区 13px 行高 1.6、chips 12px/600 8px 圆角、费用提示 12px 弱文字、最近动态标题 16px/700、空态 13px 次文字）。
- 截图：docs/screenshots/index-design-v1.png（真实服务 + 真实项目数据）。
- 已知保留：本层不改布局；发送钮只留尺寸与圆角、不改颜色；模型稿边框写法正确（1px solid var(--hairline)，hairline 本就是颜色值），零编排修正。

## 23. 成片库页设计层 v1（2026-10-25，5.3 路）
- 文件：static/finals-design-v1.css，只覆盖，finals.html 在 harness.css 之后引用（不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：成片台账（页头是台账眉、筛选条是工具条面板、提示是台账注脚、成片列表是纵向台账列；页头 20px/700 加 1px 发丝底线、筛选条 surface 底发丝边、下拉 13px、生成按钮 13px/600 8px 圆角、提示 13px 次文字、列表纵向排列行距 12px）。
- 截图：docs/screenshots/finals-design-v1.png（真实服务 + 复制库真实项目与成片数据）。
- 已知保留：本层不改布局；成片卡片本体（海报、标题、状态戳、操作行）沿用原样式，本轮未覆盖；模型稿 2 处编排修正：.page 的 padding 20px 会覆盖 harness 已有的 24px 20px 64px，已删；#finalsList 的 surface 底发丝边内边距会让空列表渲出空框，已删，只留纵向排列与行距。

## 24. AI 图片页设计层 v1（2026-10-25，5.3 路）
- 文件：static/images-design-v1.css，只覆盖，images.html 在内联 style 块之后引用（不改 app.css/harness.css、内联 style 块与任何 JS；内联块在 harness.css 之后，本层必须在其后才压得住同特异度规则）。
- 视觉逻辑：图片台账（页头是台账眉、副标题是台账说明、生成卡标题是台账分栏题、表单标签是台账字段名、提示是台账注脚、生成区是台账主操作；页头 20px/700、副标题 13px 次文字、卡片标题 16px/700、表单标签 12px/600 次文字、输入框 13px 8px 圆角、生成按钮 13px/600 8px 圆角、生成区上下 16px 发丝底线、提示 13px 次文字）。
- 截图：docs/screenshots/images-design-v1.png（真实服务 + 复制库；IMAGE 模型未接入，空模型提示与禁用态生成按钮为真实空态，未伪造数据）。
- 已知保留：本层不改布局；模型下拉、比例/尺寸下拉、参考图预览沿用原样式与内联规则；模型稿 3 处编排修正：textarea 圆角 6px 改回全站输入框口径 8px、font:inherit 改回明确 14px（防继承字号漂移）、提示的 nowrap/省略改回完整显示（状态提示截断会丢信息）；副标题选择器由 .page-sub 改为 .page-head .page-sub——app.css 的同名双类规则特异度更高，原稿 13px 被压回 12px，改后实测 13px/次文字色。

## 25. 成片质检页设计层 v1（2026-10-26，5.3 路）
- 文件：static/qc-design-v1.css（15 条规则，只覆盖，qc.html 在 harness.css 之后引用 1 行；不改 app.css/harness.css 与任何 JS）。
- 视觉逻辑：质检台账（页头是台账眉、卡片是台账格、信息行是台账明细、备注区是台账附注、通过/打回是台账戳；页头 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、徽标 12px/600、信息 dt 12px/600 次文字、dd 13px、备注标题与表单标签 12px/600、textarea 13px 8px 圆角、通过/打回按钮 13px/600 8px 圆角、空态 13px 次文字）。
- 截图：docs/screenshots/qc-design-v1.png（真实服务 18197 端口 + 复制库真实成片 id=1：第 1 集成片、待质检、时长 00:09、创建 2026-10-13 06:46、剧集 #1、质检表单态）。
- 已知保留：本层不改布局；视频区只加边框圆角、不碰内联黑底与播放逻辑，截图时播放器为初始 0:00 态（无自动播放，/media/finals/1 实测 200）；模型稿 3 个 css 围栏拼接入仓、零编排修正（边框写法正确，1px solid var(--hairline)）；首轮模型正文 0 字（4000 tokens 被思考耗尽）后按规缩小目标为纯 CSS 二通入仓，测试文件由编排按 Settings 模式机械落仓；本轮未动 images v2、login、second-brain、docseek eval 在跑工人的未提交文件；验收服务按 PID 停干净、18197 端口已关、复制库与验收 jar 已删。

## 26. AI 图片页设计层 v2（2026-10-26，5.3 路）
- 文件：static/images-design-v2.css（3 条规则，只覆盖，images.html 在 v1 之后引用 1 行；不改 app.css/harness.css、内联 style 块、v1 文件与任何 JS；v2 在内联块与 v1 之后加载，同特异度规则压得住内联下拉规则）。
- 视觉逻辑：图片台账续篇（下拉框与 textarea 同一套表单控件语言、参考图预览是台账附图、文件选择框是台账字段行；下拉框 surface 底、10px 12px 内边距、14px、8px 圆角、1px 发丝边，参考图预览块级显示、限高 280px 不裁剪、8px 圆角，文件选择框 12px/600 次文字）。
- 截图：docs/screenshots/images-design-v2.png（真实服务 18198 端口 + 复制库；IMAGE 模型未接入，空模型提示与禁用态生成按钮为真实空态，未伪造数据）。
- 已知保留：本层不改布局；文件选择框的浏览器原生按钮外观不动；本轮关闭 v1 已知保留的下拉与参考图预览缺口。

## 27. AI 音乐页设计层 v1（2026-10-26，5.3 路）
- 文件：static/music-design-v1.css（13 条规则，只覆盖，music.html 在内联 style 块之后引用 1 行；不改 app.css/harness.css、内联 style 块与任何 JS；内联块在 harness.css 之后，本层必须在其后才压得住同特异度规则）。
- 视觉逻辑：音乐台账（页头是台账眉、副标题是台账说明、生成卡是台账格、表单标签是台账字段名、模式分段是台账档位、提示是台账注脚、生成区是台账主操作；页头标题 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、表单标签 12px/600 次文字、输入框与下拉与多行框 13px 8px 圆角、模式分段按钮 13px、生成按钮 13px/600 8px 圆角（不改颜色）、提示 13px 次文字、BYOK 空盒 1px 虚线发丝边 8px 圆角、生成区上下 1px 发丝线）。
- 截图：docs/screenshots/music-design-v1.png（真实服务 18197 端口 + 复制库；MUSIC 模型未接入，空模型提示与禁用态生成按钮为真实空态，未伪造数据；视口截图，见已知保留）。
- 已知保留：本层不改布局；复选行 13px 未压成 12/600（复选行标签与字段名区分）；模式分段激活态（--ink 黑底）沿用内联规则，本层不改颜色；内联 padding 的卡片内层 div 不碰；截图 harness 说明：本页在 setContent 抓屏下文档 scrollHeight 约 75909px（无本层时同样 75909px，属既有渲染 quirks、非本层所致），整页截图会把目标撑爆，故改用 1440x900 视口截图，表单全部内容均在首屏内；另有 1 条 console 错误（document.write 相关 SyntaxError，内联脚本中无 document.write 调用、来源未定位，不影响内容与样式）；验收服务按 PID 停干净、18197 端口已关、复制库与验收 jar 已删。

## 27. 成片库页设计层 v2（2026-10-26，5.3 路）
- 文件：static/finals-design-v2.css（13 条规则，只覆盖，finals.html 在 v1 之后引用 1 行；不改 app.css/harness.css 与 v1 文件）。
- 视觉逻辑：成片台账续篇——卡片本体不再是内联样式，而是一套与旧内联数值逐字一致的台账卡片规则（卡片 880px 宽弹性纵列、海报盒 400px 16/9 10px 圆角、标题 18px/600、元信息 13px 次文字、操作控件 15px）；JS 侧同步把 cssText 换成 final-* 类，渲染与行为不变。
- 截图：docs/screenshots/finals-design-v2.png（真实服务 18200 端口 + 复制库真实成片数据：都市奇缘/重逢/第 1 集成片）。
- 已知保留：本层不改布局、不 redesign；海报盒 #211d1b 与视频 #000 为旧内联原值逐字保留；首末边线改由兄弟选择器与 :last-child 表达，与旧 idx 逻辑逐项等价。

## 28. AI 对话页设计层 v1（2026-10-26，Flash 路）
- 文件：static/chat-design-v1.css（10 条规则，只覆盖，chat.html 在 app.css 之后引用 1 行；不改 app.css 与任何 JS；本页不引 harness.css/auth.css，token 全部取自 app.css）。
- 视觉逻辑：对话台账（页头是台账眉、卡片是台账格、表单标签是台账字段名、对话区是台账纸面、快捷提问是台账便签、费用提示是台账注脚；页头 h1 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、表单标签 12px/600 次文字、下拉框 14px 8px 圆角、对话区 surface-2 底发丝边 8px 圆角、快捷提问 13px/600、费用提示 12px 弱文字、提示框 surface 底发丝边 10px 圆角）。
- 截图：docs/screenshots/chat-design-v1.png（隔离构建真实服务 18201 端口验 200 + 内联截图核计算样式；下拉与对话区为空是无 JS 数据的真实空态）。
- 已知保留：本层不改布局；输入区定位与发送钮沿用 app.css 原样式；对话区原有最小/最大高度逻辑不动；验收服务按真实 java PID 停干净、18201 端口已关、隔离构建与复制库已删。

## 29. 视频拆解页设计层 v1（2026-10-26，5.3 路）
- 文件：static/deconstruct-design-v1.css（14 条规则，只覆盖，deconstruct.html 在内联 style 块之后引用 1 行；不改 app.css、内联 style 块与任何 JS；本页不引 harness.css，token 全部取自 app.css）。
- 视觉逻辑：拆解台账（页头是台账眉、卡片是台账格、表单标签是台账字段名、详情小节是台账章节、逐镜网格是台账附图、提示词块是台账底稿；眉标 11px/600 次文字、页头标题 20px/700、副标题 13px 次文字、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、表单标签 12px/600 次文字、下拉与输入框 13px 8px 圆角、按钮 13px/600 8px 圆角（主按钮除外，见保留）、空态 13px 次文字、详情小节标题 14px/700、时间线条 1px 发丝边 8px 圆角、逐镜帧 8px 圆角、元数据 12px 次文字、提示词块 12px 等宽 surface-2 底 8px 圆角）。
- 截图：docs/screenshots/deconstruct-design-v1.png（隔离构建真实服务 18199 端口 + 复制库真实项目数据：都市奇缘/第 1 集/无视频素材，本项目拆解为空态是真实空态，未伪造数据；视口截图）。
- 已知保留：本层不改布局；主按钮（.btn-primary）沿用 app.css 胶囊形（999px/500），本层不改产品按钮语言，非主按钮实测 13px/600/8px；逐镜帧与元数据在空态下无真实 DOM，计算样式为 harness 注入测量（注入后即删，截图本身仍为真实空态）；模型稿 1 处编排修正：提示词块字体由通用 monospace 改为 var(--mono) token；眉标选择器由 .dc-kicker 提为 .page-head .dc-kicker——app.css 的 .page-head p（0,1,1）会压住单类选择器，提后实测 11px/600/次文字色；截图 harness 说明：deconstruct.js 的 api() 会给相对路径补 /api/projects/ 前缀，通用 /api/ 绝对化改写会把绝对路径调用拼成双段 URL（已改 harness 为只改写 api() 的 URL 构造行）；setContent 下 about:blank 无 localStorage，页内主题脚本读 localStorage 抛 SecurityError 一条，属 harness 环境 artifact、真实源站不受影响；验收服务按真实 java PID 停干净、18199 端口已关、隔离构建与复制库已删；本轮未动 canvas、chat、finals、second-brain、docseek、linkshort 在跑工人的未提交文件。

## 30. Skill 市场页设计层 v2（2026-10-26，5.3 路）
- 文件：static/skills-design-v2.css（2 条规则，只覆盖，skills.html 在 v1 之后引用 1 行；JS 机械迁移：已安装行类名加 installed-row、去掉行内 style 与 tabler border-bottom utility，边线改由本层全权接管；不改 app.css 与布局）。
- 视觉逻辑：技能台账续篇（已安装行是台账明细行：行间 1px solid var(--border-soft) 发丝底线、末行不留尾线）。
- 截图：docs/screenshots/skills-design-v2.png（隔离构建真实服务 18203 端口 + 复制库真实技能数据：市场 4 卡、已安装 2 行；视口截图）。
- 已知保留：本层不改布局；详情弹窗模板 pre 的边线仍由 skills.js 另一处行内 !important 写死，不在本轮范围；验收服务按真实 java PID 停干净、18203 端口已关、隔离构建与复制库已删；本轮未动 canvas、deconstruct、chat、second-brain、docseek、linkshort、botstalk 在跑工人的未提交文件。

## 31. 任务队列页设计层 v2（2026-10-26，5.3 路）
- 文件：static/tasks-design-v2.css（12 条规则，只覆盖，tasks.html 在 v1 之后引用 1 行；JS 机械迁移：任务行渲染的行内 style 赋值全部改挂 task-row/task-top/task-left/task-status/task-name/task-progress-wrap/task-progress/task-pct/task-link/task-retry/task-meta/task-error 类，动态进度条宽度与显隐切换仍留行内；不改 app.css 与布局）。
- 视觉逻辑：任务台账续篇（任务行是台账明细行：行间 1px solid var(--surface) 底线、任务名 14px 截断、百分比 12px 等宽右对齐、进度条 120×4px、辅助信息 12px 次弱文字、操作链接 13px 墨色）。
- 截图：docs/screenshots/tasks-design-v2.png（隔离构建真实服务 18204 端口 + 复制库真实任务数据：都市奇缘/第 1 集/镜号 1·中景/任务 #1 已完成 100%；视口截图）。
- 已知保留：本层不改布局；进度条动态宽度仍由行内 style 写（数据驱动，非样式）；验收服务按真实 java PID 停干净、18204 端口已关、隔离构建与复制库已删；本轮未动 canvas、deconstruct、chat、second-brain、docseek、linkshort、botstalk 在跑工人的未提交文件。

## 29. 分镜画布页设计层 v1（2026-10-26，Flash 路）
- 文件：static/canvas-design-v1.css（6 条规则，只覆盖，canvas.html 在内联 style 块之后引用 1 行；不改 app.css、内联 style 块与任何 JS；本页不引 harness.css/auth.css，token 全部取自 app.css）。
- 视觉逻辑：画布台账外框（只统一尚未统一的外框，内联已覆盖的组件一律不碰；页头 h1 20px/700、卡片 surface 底发丝边 10px 圆角零阴影、卡片标题 16px/700、卡片内副文案 13px 次文字、页头操作按钮 13px/600 8px 圆角、工具栏下拉框 14px）。
- 截图：docs/screenshots/canvas-design-v1.png（内联截图核计算样式 + 隔离构建真实服务 18202 端口验 200；时间轴与镜头网格为空是无 JS 数据的真实空态）。
- 已知保留：本层不改布局；时间轴、镜头卡片、弹窗、提示条沿用页内内联样式；agent-canvas 组件内部不动；验收服务按真实 java PID 停干净、18202 端口已关、隔离构建与复制库已删。

## 31. 设置中心页设计层 v2（2026-10-26，Flash 路）
- 文件：static/settings-design-v2.css（1 条规则，只覆盖，settings.html 在 v1 之后引用 1 行；不改 app.css/harness.css 与 v1 文件）。
- 视觉逻辑：配置台账续篇——关闭 v1 已知保留的重试钮缺口（重试钮与保存钮同口径：13px/600、8px 圆角、8px 16px 内边距、1.4 行高；surface 底、1px 发丝边、主文字色；hover/focus/active 沿用 app.css 次按钮原样式）。
- 截图：docs/screenshots/settings-design-v2.png（内联截图核计算样式 + 隔离构建真实服务验 200；harness 侧取消 error 容器隐藏以便实测，页面代码一字未动）。
- 已知保留：本层不改布局；重试钮 hover/focus/active 沿用 app.css 次按钮原样式。

## 32. 成本账本页设计层 v2（2026-10-26，5.3 路）
- 文件：static/cost-ledger-design-v2.css（1 条规则，只覆盖，cost-ledger.html 在 v1 之后引用 1 行；JS 机械迁移：供应商明细金额 span 与最近明细表时间/预估/实际 td 统一挂 cl-num 类、删行内样式；动态进度条宽度仍留行内；不改 app.css 与布局）。
- 视觉逻辑：账本台账续篇——数字列全部等宽对齐，金额与时间在纵向上一眼可比。
- 截图：docs/screenshots/cost-ledger-design-v2.png（隔离构建真实服务 18205 端口 + 复制库真实数据：最近明细 1 条、供应商今日真实空态；视口截图；td 计算样式实证 tabular-nums）。
- 已知保留：本层不改布局；页内 inline style 块的 .kpi-value 等宽规则与本层无关，不碰。

## 33. 运行页设计层 v2（2026-10-26，5.3 路）
- 文件：static/runs-design-v2.css（2 条规则，只覆盖，runs.html 在 v1 之后引用 1 行；JS 机械迁移：直接删 3 处行内 style 属性、不加新类；不改 app.css/harness.css 与布局）。
- 视觉逻辑：运行台账续篇——错误提示图标统一 15px 对齐、计划区空态内边距 24px（压住 harness 全局 48px 20px，只限 #planArea 内）。
- 截图：docs/screenshots/runs-design-v2.png（隔离构建真实服务 18206 端口 + 复制库真实数据：3 条运行；视口截图；错误图标与空态计算样式以注入节点实证）。
- 已知保留：本层不改布局；#planArea 容器自身的 margin-top:16px 行内样式与本轮无关，不碰；错误态与空态均为条件态，计算样式以注入节点实测（注入后即删，截图仍为真实态）。

## 36. 分镜板页设计层 v2（2026-10-26，5.3 路）
- 文件：static/storyboard-design-v2.css（3 条规则，只覆盖，storyboard.html 在 v1 之后引用 1 行；JS/HTML 机械迁移：对白 div 由行内 white-space:pre-wrap 改挂 sb-dialogue 类、技能下拉删行内 max-width:200px 改由 #skillSelect 规则接管、提示容器删行内 z-index:1080 改挂 sb-toast-wrap 类；不改 app.css 与布局）。
- 视觉逻辑：分镜台账续篇——对白换行保留、技能下拉宽度 200px、提示层级 1080 压住页面内容。
- 截图：docs/screenshots/storyboard-design-v2.png（隔离构建真实服务 18207 端口 + 复制库真实数据：项目 3“验证用短剧”第 1 集 4 场、4 场全带对白；探针：对白 white-space=pre-wrap、skillSelect maxWidth=200px、toast zIndex=1080、console 0 错误；另有 1 条 pageerror，setContent 下 document.write SyntaxError，与音乐页、成本账本页同款 harness 环境 artifact，不影响内容与样式）。
- 已知保留：本层不改布局；§34/§35 为 Flash 路预留（skills v3、run-detail v2 的文档补推归 Flash 路，本路不代写）；验收服务已停、18207 端口复查无监听、隔离构建与复制库已删。

## 34. Skill 市场页设计层 v3（2026-10-26，Flash 路，文档补推）
- 文件：static/skills-design-v3.css（模型稿 6 条声明原文入仓，skills.html 在 v2 之后引用 1 行；JS 机械迁移：详情弹窗模板 pre 改挂 skill-detail-pre 类、删行内 style 与 tabler p-2/border/rounded 类，边线改由本层全权接管，关闭 v2 已知保留）。
- 视觉逻辑：详情弹窗模板块——padding 8px、1px solid 浅色边线、圆角 8px、pre-wrap、12px、等宽字体栈。
- 截图：docs/screenshots/skills-design-v3.png（隔离构建真实服务 18205 端口 + 复制库真实数据；点开首张卡片详情弹窗实测 pre 计算样式与之一致，零 console 错误）。
- 已知保留：本层不改布局；圆角由 tabler rounded 的 4px 变为本层惯例 8px（与弹窗内其他控件同口径），非回归。

## 35. 运行详情页设计层 v2（2026-10-26，Flash 路，文档补推）
- 文件：static/run-detail-design-v2.css（模型稿 2 条规则原文入仓，run-detail.html 在 v1 之后引用 1 行；JS 机械迁移：无分镜空行挂 rund-empty-text 类、视频与成片两处无预览盒挂 rund-no-preview 类、删行内样式，dim 类保留，关闭 v1 未覆盖的 3 处空态行内样式）。
- 视觉逻辑：空态小字 13px、无预览盒 24px 居中。
- 截图：docs/screenshots/rundetail-design-v2.png（隔离构建真实服务 18206 端口 + 复制库；空态片段内联截图 + 计算样式亲眼核对，零 console 错误）。
- 已知保留：本层不改布局、dim 类保留。

## 38. Agent 机队页 providers 行设计层 v2（2026-10-26，Flash 路）
- 文件：static/agents-design-v2.css（模型稿 12 条规则原文入仓，agents.html 在 v1 之后引用 1 行；JS 机械迁移：providers.js 12 处行内样式改挂 pv-preset-row/pv-name/pv-head-actions/pv-meta/pv-model-add-row/pv-test-result/pv-model-row/pv-model-id/pv-model-name/pv-model-id-text/pv-model-actions/pv-test-fail 类，pv-test-result 的 hidden 属性保留；数据驱动 badge（entry[0]/entry[1] 拼背景与文字色）保留行内，不为其写规则）。
- 视觉逻辑：供应商卡片行——模型行 flex、gap 10px、上下 8px、顶线 1px solid；模型名 13px/600、模型 id 12px 次文字色；元数据 12px、gap 12px、上边距 8px；操作区 margin-left:auto 右对齐；预设行 flex、gap 8px、上边距 4px。
- 截图：docs/screenshots/agents-providers-v2.png（隔离构建真实服务 18207 端口 + 复制库；库内 providers 为空，注入 1 供应商 + 1 模型经真实 API 实测后即删，截图仍为真实态；计算样式与之一致；唯一 console 错误为 /api/agents 的 409，属既有 LYRICS 模板种子缺口，与本层无关）。
- 已知保留：本层不改布局；数据驱动 badge 保留行内；§37 为 5.3 路对话页 v2 预留，本节顺延为 §38。
