# 紫微星盘前端 Medley 对照与残留（2026-11-01，深色玻璃风重做轮）

对照基准：`DesignRepoForMuse/UIDesign/app/medley/` v1.9 画廊图
（`docs/verification/rounds/v1.9/welcome-dark.png`、
`chat-dark-lisbon-cn.png`、`pricing-dark.png`、`credits-light.png`、
`home-light-cn.png`）+ tokens（`src/tokens/index.ts`）+ 用户 photo-9 色彩层。
新截图：H5 预览（`~/workspace/ziwei-h5-preview/shots-medley/`），
2026-11-01 实测，默认盘 1995-06-15 午时男北京。

## 对照表（逐项，带数值）

| # | 对照项 | Medley 基准值 | 本轮实测 | 结论 |
|---|--------|--------------|---------|------|
| 1 | 页面底色 | 深底 #111518；welcome 底 #0D0E10 | page 底 #111518 + 三处环境光 | 对齐 |
| 2 | 环境光 | 暖 #482b1d@21%/76%、绿 #193d33@82%/92%、蓝 #1f2f46@78%/30%（photo-9） | 同三色同方位，alpha 0.45–0.55（home/mine 截图左下暖光、右下绿光可见） | 对齐 |
| 3 | 卡片 | 深卡 #1e1f23、圆角 16px、1px 玻璃边 | #1e1f23 + rgba(255,255,255,0.08) 边 + 16px 圆角 + 阴影 | 对齐（weapp 无 backdrop-filter，见残留 R1） |
| 4 | 品牌圆点 | 绿 #5ec8a7 / 蓝 #8fb0d8 / 粉 #d98cb4，8px | 首页顶栏、命盘中央、我的头像三处均为 8px 三色点 | 对齐 |
| 5 | 标题光标 | 宝石蓝 #6ea9dd、15px 圆点 | 首页标题后 15px #6ea9dd 圆点，截图可见 | 对齐 |
| 6 | 主按钮 | 白色胶囊 #ffffff、字 #111214、圆角 26px | 开始排盘为白胶囊黑字 26px | 对齐 |
| 7 | 次按钮 | 描边胶囊、边 #2d3134、圆角 26px | 应用真太阳时校正 / 查看上次命盘为描边胶囊 | 对齐 |
| 8 | 正文/次要 | #f5f5f7 / #9a9ba2 | 同值；卡片上对比度正文 15.12:1、次要 5.95:1 | 对齐，均过 WCAG AA 4.5:1 |
| 9 | 十二宫格可读性 | —（Medley 无此构件，本轮自定标准） | 主星 #f5f5f7 15px 加粗；辅星 #c3c7ce 9.71:1；神煞/大限 #9a9ba2 5.95:1；四化禄 #5ec88a 7.92:1、权 #e3ac45 8.04:1、科 #93c8f0 9.22:1、忌 #f08080 6.35:1；当前大限宫（夫妻）2px #e2a181 边 + 光晕 | 对齐（全部逐项验算） |
| 10 | 中央信息区 | — | #191a1e 气泡卡 + 三色点，含农历 1995-5-18、火六局、命主贪狼、身主天机、命宫子/身宫子 | 对齐 |
| 11 | 大运/流年/流月 | — | 大运 12 段 + 当前/本年所属 chip；流年干四化 + 流月 12 行齐全 | 对齐 |
| 12 | 解读页 | 深色聊天/卡片风；每处固定免责 | 格局卡 + 13 维卡片，格局项左 3px #e2a181 竖线（放大裁切已验）；免责出现 14 次 = 1 + 13，逐卡齐全 | 对齐 |
| 13 | 知识页 | 分段器 + 卡片 | 分段器 #1f2024 底 + #303135 选中 pill；星曜 14 / 宫位 12 / 四化 4 / 格局 3 条，切换探针全过 | 对齐 |
| 14 | 我的页 | — | 几何头像（圆环 + 三色点，无字母徽标）；会员/积分/邀请/订单/设置/反馈/关于 7 入口齐全，静态壳未变 | 对齐 |
| 15 | TabBar | 深底 + 白色选中 | 底 #111518、字 #9a9ba2/选中 #f5f5f7；8 张 81x81 PNG（房子/对话/书本/头像几何形，灰描边常态 + 白填充选中），weapp dist/app.json 与 dist/assets/tabbar/ 已验 | 对齐 |
| 16 | 字体 | SF 体系意境 | 字体栈 -apple-system、SF Pro Text、SF Pro Display、PingFang SC；零字体文件进仓 | 对齐（真机渲染见残留 R3） |
| 17 | 功能零回归 | — | 表单 5 字段、真太阳时/夏令时手动按钮 + 撤销、排盘计算、大运流年流月、知识文本、免责声明全部保留；引擎 0 文件改动 | 对齐 |

## 残留表

| # | 残留项 | 具体差距 | 状态 |
|---|--------|---------|------|
| R1 | 真玻璃折射 | Medley welcome 用 Liquid Glass 位移滤镜（strength 5）；小程序 weapp 不可靠支持 backdrop-filter，本轮用 1px 半透明边 + 阴影模拟玻璃感，无真实折射 | 接受：平台限制，非本轮可修 |
| R2 | 浅色局部 | Medley 本身有浅色屏（home-light、credits-light）；本轮按任务方向 5 页全深色，未设浅色页 | 接受：任务方向已定深色贯穿 |
| R3 | 真机/低版本基础库 | H5 预览已验全部 5 页 + 高视口全量解读/知识；微信真机、开发者工具、低版本基础库 grid 表现未验；TabBar PNG 在真机 tabBar 栏的实际渲染尺寸未验 | 待真机复核 |
| R4 | 标题字号 | Medley welcome 标题 38px（v1.9）；本轮首页标题 38px semibold，但 H5 预览经 750 设计宽换算后视觉略小于 38pt 原生渲染 | 待真机复核（weapp 下为真实 38px 换算） |
| R5 | 交互动效 | Medley v1.9 有 iOS 曲线进场、光标闪烁、morphing 切换；本轮为静态样式重做，无进场/闪烁动效 | 未做：本轮范围外，可后续加 |
| R6 | 命盘中央区 grid | 2x2 跨格 grid 在低版本基础库的表现仍是已知缺口（沿用一期实现，未改） | 待真机复核 |

残留总数：6 项；其中平台/方向接受 2 项（R1、R2），待真机复核 3 项（R3、R4、R6），范围外未做 1 项（R5）。
最关键的三项：R3（真机 TabBar 与整机渲染是唯一未验大项）、R1（玻璃无真折射，观感上限）、R5（无动效，与 Medley v1.9 交互线有差距）。

## 验证收据

- `pnpm build:weapp`：通过（Taro 4.3.1，Sass @import 弃用警告与 vendors.js 832 KiB 体积警告各 1，不影响构建）。
- `pnpm typecheck`：通过。
- H5 截图：home / chart（点开始排盘真实流程）/ mine / knowledge / interpret 5 张 + interpret-full / knowledge-full 高视口全量 2 张。
- 截图取证方式：H5 用 hash 路由（`/#/pages/...`），旧 shot.js 的直访路径只会落在首页，已改 shot-medley.js 走 hash 路由重截并逐张目视确认。

---

## v2：严格按 Medley 重做（2026-11-01，用户铁律）

铁律原文：严格按照 Medley 项目来做，只是内容换成我们的；该有的组件都用人家的。组件、尺寸、布局、深浅搭配全部照搬，只换内容。不许自创组件、不许凭感觉放大、不许擅自改深浅。

### v1 的三处错误，逐项改掉

1. **尺寸换算错误（已修）**：v1 把 Medley pt 数直接写成源码 px，weapp dist 里变成同数 rpx，390pt 屏上只剩 0.52 倍（hero-title 38 → 19.8pt）。v2 全部按 `rpx = Medley pt × 750/390` 重写，dist wxss 逐项核对（见实测表与 dist 核对）。
2. **擅自全深色（已废除）**：v1 variables.scss 明文写 light set 不用。v2 废除该条：首页/命盘图/解读走 dark（welcome-dark、chat-dark），知识/我的走 light（home-light、credits-light）。v1 残留 R2（全深色方向）就此作废。
3. **自创组件（已删）**：v1 全宽长条大白“开始排盘”按钮删除，改为 Medley 真实组件：首页提交 = InputBar 单条（56 高 + 36 发送圆 + 20 箭头），卡片内操作 = Button（52 高）与 ModelPill（7/12 内边距、13 semibold），底部操作区 = credits 式按钮行。

另纠正 v1 文档两处错误：v1 R4 称“Medley welcome 标题 38px（v1.9）”是错的——v1.9 标题是 43pt（v1.5 由 38 按大写高度缩放至 43）；v1“ H5 换算视觉略小”的真正原因是 H5 换算因子与 weapp 不同（见校准方法），不是“略小”。

### 校准方法（截图与真机各说各话的根因，已闭合）

- H5 预览实测：源码 px 在 390 视口下渲染因子为 0.4（rem rootValue 40 × 16px 根字号），而 weapp 真实因子是 0.52（390/750）。旧 H5 截图（38px 标题渲成约 37px）与真机（38rpx 渲成 19.8pt）不一致，根源在此。
- v2 做法：截图前注入 `html{font-size:20.8px !important}`，因子变为 0.52，与 weapp 完全一致；DSF 1，PNG 像素 = CSS px = weapp pt。校准实测：标题 42.9988px、页边距 19.9992px、卡边距 16.0004px、composer 高 55.98px（≈56）。
- tsx 内联 px（如 marginTop '12px'）不受 pxtransform 处理，在 weapp 里 1px = 1pt，在校准后 H5 里 1px = 1px，两边一致，故内联值一律保留不改。

### 实测表（Medley pt | 小程序 rpx | 390 画布实测 px，换算闭合）

| # | 项目 | Medley pt | 小程序 rpx | 390 画布实测 px | 备注 |
|---|------|-----------|------------|----------------|------|
| 1 | 大标题（welcome title） | 43 | 82.69 | 43.0（42.9988） | Semibold，行高 1.15；中文标语 10 字在 334 内容宽内折 2 行（见残留 R4'） |
| 2 | 正文字号（body） | 16 | 30.77 | 16.0（16.0004） | card-title 与 chat-bubble 同值 |
| 3 | 表单行高（input-row） | 46.5（推导值：py-12 内边距 24 + 15pt × 1.5 Tailwind 预设行高） | 94.23（内边距 46.15 + 内容 48.08） | 49（内边距 24 + 内容 25） | 差 2.5pt 为行高默认值差异，见残留 R7'；换算闭合：94.23 × 0.52 = 49.0 |
| 4 | composer 高（InputBar 单条） | 56 | 107.69 | 56（55.98） | 圆角 26，左 14 右 8，间距 10，发送圆 36，箭头 20 |
| 5 | 按钮高（Button 默认） | 52 | 100.00 | 52 | 字号 15 bold；border-box 后含 1.92 hairline 边框仍为 52（修前 H5 量得 54，见下） |
| 6 | 卡内边距（card padding） | 16 | 30.77 | 16.0（16.0004） | 卡圆角 16，阴影 0 10 26 |
| 7 | 页边距（page padding） | 20 | 38.46 | 20.0（19.9992） | |

附带实测：品牌点簇 22×15（对角布局：绿左下、蓝左 7 上 3.5、粉右上）、宝石蓝光标 15×15、宫头单行（头高 24，分支 13 + 宫名 15 同行）、宫格 gap 10、宫内边距 16/10。

### dist wxss 核对（weapp 真实产物）

- hero-title 82.69rpx；composer 高 107.69rpx、圆角 50rpx、内边距 0 15.38rpx 0 26.92rpx、阴影 0 19.23rpx 50rpx；btn-medley 高 100rpx、字号 28.85rpx、内边距 0 38.46rpx；card 内边距 30.77rpx、圆角 30.77rpx；page 内边距 38.46rpx；input-row 内边距 23.08rpx；chat-bubble 圆角 38.46rpx（右上 11.54rpx）、内边距 23.08rpx 30.77rpx、字号 30.77rpx、行高 1.35；brand-dots 42.31rpx × 28.85rpx、蓝点 left 13.46rpx top 6.73rpx；page-welcome 三层环境光（蓝 615.38×500 于 78%/30% α0.45、暖 576.92×461.54 于 21%/76% α0.55、绿 538.46×423.08 于 82%/92% α0.55，底色 #0d0e10）；知识/我的页面 json 含浅色导航栏（#f5f6f8 / black）。
- 旧 .btn / .btn-ghost / .btn-mini 规则在 dist 中为零残留。

### 改动说明（只动 client/，后端与路由零碰）

- 样式：variables.scss 全量 Medley token（深 + 浅两套，附 pt→rpx 换算注释）；index.scss：.page 深色平铺、.page-welcome 环境光、.page-light 浅色覆盖、.btn-medley / .btn-pill / .composer / .chip / .input-row（SuggestionRow）/ .brand-dots（对角）/ sihua；各页 scss 按屏重写。
- 组件：ui.tsx 新增 ComposerBar（InputBar 单条 + 箭头发送圆，箭头为手绘矢量 PNG `assets/arrow-up.png`）；Card 新增 light 属性；新增 `types/images.d.ts`（png 声明）。
- 页面：首页根加 page-welcome、提交改 ComposerBar、次要按钮改 outline、校正按钮改 pill；命盘图保存/查看改 credits 式按钮行；解读重构为 chat 流（meta + bubble + Disclaimer，问答改 composer 条）；知识/我的根加 page-light、Card 全加 light、按钮按深浅分流（深页白/描边、浅页黑/描边、行内操作 pill-black）；知识/我的加页面级浅色导航栏配置（构建产物已含，真机行为待验）。
- 两处非 Medley 组件尺寸的诚实调整（命盘格是内容网格，Medley 没有 12 宫格）：格 gap 12→10、宫横向内边距 12→10（皆用 Medley gap-2.5 token），使宫头分支 13 + 宫名 15 = 56pt 能装进 60pt 内容宽；修前内容宽 54.5pt，宫头折两行（截图实证，已修好复测为单行）。
- border-box：Medley/Tailwind 预设即 border-box；v2 给 btn-medley、btn-pill、composer、composer-send、avatar-geo、seg-tab 显式加 box-sizing，使含边框高度与 Medley 标称一致（修前 H5 量得描边按钮 54，修后 52）。

### 截图（v2，shots-medley-v2；左 ours、右 Medley 画廊屏裁切）

- 全量：home.png（1160 高）、chart.png（2750 高）、interpret.png（3575 高）、knowledge.png（2225 高）、mine.png（1115 高）、mine-points.png（1175 高），皆 390 宽、校准后 PNG 像素 = pt。
- 并排：sbs/sbs-home.png（↔ welcome-dark）、sbs-chart.png（↔ chat-dark-lisbon-en）、sbs-interpret.png（↔ chat-dark-lisbon-en）、sbs-knowledge.png（↔ home-light-en）、sbs-mine.png（↔ credits-light）、sbs-mine-points.png（↔ credits-light）；并排左图取全量图前 852 行、右图取画廊屏裁切（2,2,392,854），皆未缩放。
- H5 预览说明：截图为 H5 预览渲染的同一套组件，不是微信客户端本身；Linux 字体为 Noto 回退（真机 iPhone 走系统 SF），见残留 R9'。

### 功能零回归收据

- `pnpm typecheck` 通过；`pnpm build:weapp` 通过（仅既有 Sass 弃用与 vendors 体积警告）；`pnpm engine:smoke` 768 盘 0 失败。
- callFn 调用点与 HEAD 逐数一致：interpret 7、mine 17、chart 2、lib/cloud 2；cloudfunctions/、docs/ 零改动。
- 5 字段表单、真太阳时/夏令时手动可撤销按钮、排盘计算、大运/流年/流月、知识条目、免责声明全部保留（grep 锚点：校正处理器 6 处、大运流年流月 12 处、Disclaimer interpret 5 / chart 2 / mine 10 处、知识 4 类条目）。

### v2 残留表（带数，不藏）

| # | 残留项 | 具体差距 | 状态 |
|---|--------|---------|------|
| R1' | 真玻璃折射 | Medley 用 Liquid Glass 位移滤镜；小程序 backdrop-filter 不可靠，v2 仍用半透明边 + 阴影模拟，无真实折射 | 接受：平台限制 |
| R2' | TabBar 全局深色 | 微信 TabBar 是单一全局配置，无法按屏切换深浅；知识/我的浅色页仍配深色 #111518 底栏，Medley 浅色屏无此底栏 | 接受：平台限制 |
| R3' | 真机复核 | H5 已验全部 5 页全量；微信真机、开发者工具、低版本基础库 grid、TabBar 实际尺寸、页面级浅色导航栏真机行为均未验 | 待真机复核 |
| R4' | 标题折行 | 43pt 中文标语 10 字（430pt）超 334 内容宽，折 2 行（8+2）；Medley 拉丁标题 14 字同 43pt 恰好 1 行——字号相同，折行是内容长度差，不是尺寸差 | 接受：内容差 |
| R5' | 交互动效 | Medley v1.9 有 iOS 曲线进场、光标闪烁、morphing 切换；v2 仍为静态样式，无动效 | 未做：本轮范围外 |
| R6' | 命盘中央区 grid | 2×2 跨格在低版本基础库的表现仍是已知缺口（沿用一期实现，未改） | 待真机复核 |
| R7' | 表单行高行高差 | ours 49 vs Medley 推导 46.5，差 2.5pt：Taro Text/Input 默认行高约 1.67，Tailwind 预设 1.5 | 接受：平台默认值差 |
| R8' | 中央区农历行孤字 | 中央区内容宽约 138pt，农历行约 150pt（13pt），“日”孤字折行；宫头已修，中央区多行信息格未再缩字 | 接受：内容密度 |
| R9' | H5 预览非真机 | Linux 渲染用 Noto 回退（非 SF）、headless 亚像素 AA 有红蓝镶边；真机 iPhone 渲染待验 | 待真机复核 |
| R10' | 标题轮换未做 | Medley welcome 标题轮换多句；小程序标题为固定内容；仅观测到的一句为 "Let's discover"，未观测句一律不编 | 内容差，不做 |
| R11' | 出生地只到地级市 | 源码无县级表，沿用一期缺口 | 待源码/数据 |
| R12' | 流量主与云配置 | 与一期相同：envId/AppID/商户号/广告位仍占位，未配置入口一律显示未配置、不造假数据 | 待用户给值 |

残留总数 12 项；其中平台/内容接受 6 项（R1'、R2'、R4'、R7'、R8'、R10'），待真机复核 3 项（R3'、R6'、R9'），范围外未做 1 项（R5'），待数据 1 项（R11'），待用户给值 1 项（R12'）。
