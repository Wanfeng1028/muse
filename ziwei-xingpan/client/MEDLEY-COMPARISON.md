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

---

## v3：7 条缺口逐项重做（2026-11-01，用户亲眼对比后下令，见 ../FIDELITY-GAPS.md）

对照基准：app/medley v1.10（tokens 与 v1.9 同值；picker-a 结构与 credits 字重修正不影响本小程序对照屏）+ photo-9 色彩层 + HD 原图条（4 屏中文条、5 屏条）。
新截图：H5 预览 `~/workspace/ziwei-h5-preview/shots-medley-v3/`（v2 证据目录 shots-medley-v2 未动），390×844 视口首屏为主证据（H5 页内滚动，fullPage 与视口同帧，已核实）；校准与 v2 相同（注入 font-size 20.8px，因子 0.52，PNG 像素 = pt）。
**底栏说明**：视口截图底部是 H5 原生底栏（深 #111518），故“四角”下角须在底栏上方取样（y=760，内边距带内），否则量到的是底栏本身；无底栏的命盘页直接取图片下角。以下四角值皆按此口径。

### v2 的根因（本轮先修根因，不只改数值）

- 环境光看不见：v2 把固定 px 尺寸椭圆写进页面背景，页面一高、椭圆 70% 衰减尾就到不了角。v3 改为视口 fixed 的 `<Ambient />` 层 + 角锚定渐变（角点本身即渐变中心），深色三页（首页/命盘/解读）与浅色两页（知识/我的）各一套。
- 标题折行：43pt 中文 10 字超宽。v3 改 38pt 一行（有意例外，见下）。
- 浅色无彩：v2 浅色页只有黑白灰 + 紫色星标。v3 按 Medley 色相补类色（浅底加深至 AA）。

### 逐项修前 / 修后（PIL 实测，色度口径：饱和度>0.25 且色差>30，排除近灰）

| # | 缺口 | 修前（v2 实测） | 修后（v3 实测） | 结论 |
|---|------|---------------|---------------|------|
| 1 | 环境光 | 首页四角 TL/TR (13,14,16)、BL/BR (17,21,24)，平色无晕染 | 首页 TL (32,48,65)、TR (35,54,74)，与暗底 (17,21,24) 差 (15,27,41)/(18,33,50)，蓝方向；底栏上方 BL (72,45,31) 差 (55,24,7) 暖方向、BR (30,62,54) 差 (13,41,30) 绿方向；命盘页图片下角 BL (74,48,33)、BR (30,65,56) 同方向；解读 TL/TR 与首页同值、底栏上方 BL (80,50,35)、BR (31,71,61) | 闭合（四角差皆 >10 且色相方向对；屏中部仍以暗色为主，与 Medley welcome 同理，角晕为设计值） |
| 2 | 首页标题 | 43pt 折 2 行 | 38.00px（38.0016）、宽 342、行数 1（Range rects 计 1 行）；光标 370–384（15px 宝石蓝），落点 < 390 屏宽，伸入右侧内边距区 | 闭合，有意例外：43pt Medley 拉丁标题一行，中文 9 字在 43pt 下必折行，一行完整标题比死守 43pt 更像 Medley |
| 3 | 卡片玻璃 | 单色平底 + 细线 | 深卡：上亮→下暗分层渐变 + 1px 内高光 + 1px 半透明边 + Medley 阴影；浅卡：白→#f3f4f6 渐变 + 内高光 + 淡阴影；气泡/composer 同法 | 闭合（逼近；无真实折射，见残留 R1''） |
| 4 | 浅色/深色补彩 | 知识彩色比 3.37%（旧口径含星标外其它像素）、我的 1.70%；浅色两页目视纯黑白 | 知识：分段器选中态按类着色 + 卡片 3pt 左色条 + 标题同色（星曜蓝/宫位绿/四化橙/格局粉，浅底对比度 4.89–5.20）；我的：档位/价格/积分增减/订单状态着色（代码已落，见下）；深色页：首页彩色比 4.03%→8.82%，解读 20.84%（含桃色强调） | 闭合（知识页；我的页主屏未配置态无真实价格/积分可着——不造假数据，见残留 R7''） |
| 5 | 图标 | 底栏未选中为细线轮廓 | 未选中 glyph 1px 膨胀：home 1051→1469px、chat 1315→1843px、book 1447→1957px、mine 851→1235px；选中态实心白填充不动；列表箭头 › 改 20pt 半粗 | 闭合 |
| 6 | 表单层级 | 标签/值同为 15pt，行高 49 | 标签 13pt medium、值 16pt semibold、行高 52.48（28 + 16×1.5 = 52，Medley token rowPaddingY 14）；列表主行 16pt 半粗；v2 R7'（49 vs 46.5）由 token 值取代 | 闭合 |
| 7 | 命盘盘感与星曜着色 | 均分方块、辅星全灰 #c3c7ce | 外框 plate（#16171a 底 + 1px 环线 + 圆角 20 + 10pt 内边距）收 12 宫为一盘；中央区暖色径向辉光；辅星 logo 蓝 #8fb0d8（7.35:1）、吉星 logo 绿 #5ec8a7（8.07:1）、煞星品牌橙 #fd6718（5.59:1），皆过 AA；四化沿用 v2 四色 | 闭合（颜色来源：Medley logo/品牌色原值，见 variables.scss 注释） |

### 动效（本轮新增，v2 R5' 闭合一半）

- 入场：hero 与卡片 0.6s 上升 8pt，iOS 曲线 cubic-bezier(0.32,0.72,0,1)；标题光标 1.6s 闪烁同曲线；`prefers-reduced-motion: reduce` 时全部关闭。截图等待 >1.5s，静态帧为最终态。
- 未做：Medley 式标题轮换、morphing 切换仍无（见残留 R5''）。

### dist wxss 核对（weapp 真实产物）

- hero-title 73.08rpx（38pt）+ nowrap + 不收缩；.ambient / .ambient-light 七层/三层角锚定渐变在位；.card 分层渐变 + 内高光 + border-box；input-row 内边距 26.92rpx（14pt）、input-label 25rpx（13pt）、input-value 30.77rpx（16pt）；chart-plate 38.46rpx 圆角、star-minor/lucky/sha 三色在位；know-cat-star 卡左 5.77rpx 蓝条、seg-tab-star 选中蓝字；mine-price #b4550d、mine-row-label 30.77rpx 半粗。

### 截图与并排（v3，左 ours、右 Medley 原图条裁切）

- 全量：home / chart / interpret / knowledge / mine / mine-points / demo / demo-3（演示页下半，5·6 项在位），皆 390×844。
- 并排 sbs/：sbs-home（↔ welcome-dark，4 屏条 (19,15,601,1260)）、sbs-interpret（↔ chat-dark-lisbon-cn，(1177,15,1753,1260)）、sbs-knowledge（↔ home-light-cn，(602,15,1152,1260)）、sbs-mine / sbs-mine-points（↔ credits-light，5 屏条 (2075,130,2431,975)）。右图缩放至 390 宽、按 390×844 居中裁切（已注明，非 v2“未缩放”口径）。
- H5 预览说明：Linux Noto 回退（非 SF）、headless AA 有红蓝镶边；真机 iPhone 渲染待验（沿用 R9'）。

### 功能零回归收据

- `pnpm typecheck` 通过；`pnpm build:weapp` 通过（仅既有 Sass 弃用与 vendors 体积警告）；`pnpm engine:smoke` 768 盘 0 失败。
- callFn 调用点与 HEAD 逐数一致：interpret 7、mine 17、chart 2、lib/cloud 2；cloudfunctions/、docs/、engine/ 零改动。
- logo 三处零改动：`git diff` 无 client/src/assets/logo/（star-mark.svg / star-mark.png / app-icon.png）、首页品牌行、我的页头像；改动文件清单见工作区 git status（样式 4 段 + 页面 5 段 + ui.tsx + 底栏 4 张未选中图标）。
- 演示页：6 组件全部目视在位（demo.png 首屏 1–4 项、demo-3.png 下半 5–6 项）。
- **不 commit、不 push**：本轮只留工作区改动，提交由协调方统一做。

### v3 残留表（带数，不藏）

| # | 残留项 | 具体差距 | 状态 |
|---|--------|---------|------|
| R1'' | 真玻璃折射 | 与 R1' 相同：分层渐变 + 内高光逼近，无 Liquid Glass 位移折射 | 接受：平台限制 |
| R2'' | TabBar 全局深色 | 与 R2' 相同：微信 TabBar 单一全局配置，浅色页仍配深色底栏 | 接受：平台限制 |
| R3'' | 真机复核 | H5 已验全部 6 页 + 演示页；微信真机、开发者工具、低版本基础库 grid、TabBar 实际尺寸、页面级浅色导航栏真机行为、.ambient 的 pointer-events 与 fixed 表现均未验 | 待真机复核 |
| R4'' | 标题字号例外 | 首页标题 38pt（非 Medley 43pt），理由见上；光标伸入右侧内边距区 | 接受：内容差 |
| R5'' | 交互动效未全 | 仅入场 + 光标闪烁；标题轮换、morphing 切换、分段器滑动仍无 | 未做：范围外 |
| R6'' | 命盘中央区 grid | 与 R6' 相同：2×2 跨格在低版本基础库的表现仍是已知缺口（沿用一期实现，未改） | 待真机复核 |
| R7'' | 我的页主屏着色受限 | 未配置态（无会员/积分/订单真实数据）下主屏无价格与积分可着色；着色代码已落于会员/积分/订单分屏，有真实数据即显；绝不为截图造假数据 | 待用户给值（envId 后自验） |
| R8'' | 浅色页行图标 | Medley 浅色屏每行有彩色小图标；本小程序知识/我的行首无图标，以卡片色条 + 彩色标题代替 | 接受：内容结构差 |
| R9'' | H5 预览非真机 | 与 R9' 相同：Linux Noto 回退、headless AA 镶边；真机 SF 渲染待验 | 待真机复核 |
| R10'' | 出生地只到地级市 | 与 R11' 相同，沿用一期缺口 | 待源码/数据 |
| R11'' | 流量主与云配置 | 与 R12' 相同：envId/AppID/商户号/广告位仍占位，未配置入口一律显示未配置 | 待用户给值 |

残留总数 11 项；其中平台/内容接受 4 项（R1''、R2''、R4''、R8''），待真机复核 3 项（R3''、R6''、R9''），范围外未做 1 项（R5''），待数据 1 项（R10''），待用户给值 2 项（R7''、R11''）。
最关键的三项：R3''（真机是唯一未验大项，尤其 .ambient 的 fixed + pointer-events 在真机上的表现）、R1''（玻璃无真折射，观感上限）、R7''（我的页着色需真实数据复验）。

## v4：产品化一轮（2026-11-01，用户纠正：Medley 是底色不是唯一来源）

用户原话：用 Medley 前端不等于只能用 Medley 的组件，其他好的组件也要用；现在的东西不像给用户用的小程序，黑乎乎的，黑白（深色与浅色）都要做好；功能和界面都要做好。本轮不是纯样式轮，是产品化轮：组件体系（Vant Weapp / TDesign MiniProgram pattern，手写，不硬装不兼容的原生库）+ 排盘标杆（宫垣 Kairos、文墨天机可读性）+ iOS 质感，逐项过全部功能。

### 4 条验收（用户 13:12 亲眼看过的原图，逐项对齐，不是“已参考”）

1. **宫垣 g1 表单页**：深色分层卡 + 大标题 + 性别胶囊分段器 + 表单下方真太阳时预览卡。
   - 首页性别由纯文字 Picker 改为分段胶囊（深色：金色 pill + 黑字，复刻宫垣金色选中男；浅色设置页同款，紫色 pill + 白字）。
   - 表单下方新增“计算结果预览”卡：出生地经度、钟表时间、真太阳时（金色值）、修正量（经度修正/均时差）、夏令时状态，随输入实时重算；只展示结果，不改动输入，采用仍需到时间校正卡点按钮（与一期“绝不自动改”铁律一致）。
   - 证据：shots-prod/home.png、crop-home-form.png（男金 pill、预览卡紧贴表单均可见）。
2. **宫垣 g2 命盘页**：三方四正连线 + 选中宫位金边 + 盘下宫位详情卡。
   - 选中态：默认命宫，点任意宫位切换；金色 inset 影（不改布局尺寸，避免量测漂移）；与现有的当前大运边（.current）并存，互不复用。
   - 连线：运行时 createSelectorQuery 量测 12 宫中心（grid 行高随内容走、非正方形，百分比坐标必错，故不用）；三合碧色三角（#5ec8a7，Medley logo 绿）+ 对宫金色对角线（#e3ac45）。H5 实测顶点：辰 (37,471)、申 (291,154)、午 (122,154)、子 (206,1095)，段长 406/945/945 与中心距逐项对上（DOM 量测值，非目测）。
   - 详情卡：盘下直接跟选中宫卡（主星 + 亮度 + 四化 + 借对宫注 + 三方四正宫名 + 大运年龄 + 复用解读维度的 body，不新编内容）+ 切换提示。
   - 流年/小限：按通行口径推算（流年支 = 农历年 −4 取余，2024 甲辰 → 辰验算通过；小限男顺女逆，从生年支起数虚岁，代码与文档均标“通行口径”）；对应宫位贴 流年（金）/ 小限（蓝）角标。默认数据（1995-06-15，今农历 2026 年）下两者恰好同落午宫，双标同格，数学复核无误。
   - 全屏查看：专注看盘覆盖层（同 grid + 同选中 + 同详情卡，独立量测）；诚实标注：是专注视图，不是捏合缩放（Taro MovableView 缩放链路在 H5 不可靠，不谎称）。
   - 证据：shots-prod/chart.png、crop-chart-plate.png、crop-chart-detail.png、chart-fullscreen.png。
3. **s6 生活社区（浅色标杆）**：去分割线大留白、一个主题色贯穿、图片卡、浅色底栏彩色激活。
   - 我的主页服务列表由满屏分割线改为间隔白卡（色点 + 粗标题 + 一行副标题 + 紫色 ›），无分割线；主题色紫 #6d28d9（白底 AA 7.1）贯穿浅色页（激活态、箭头、分段器、价格/积分色）。
   - 图片卡：本程序无图库、外链不可上架，故知识封面为矢量渐变 + 抽象装饰（圆 + 点，纯 CSS，不挪用 logo 作装饰），标题层级加粗；此为诚实替代，不是假照片。
   - 证据：shots-prod/mine.png、crop-mine-cards.png。
4. **s5 新闻资讯**：深浅双主题一等公民、图片 + 粗标题撑视觉。
   - 知识页：分类封面（星曜蓝 / 宫位绿 / 四化橙 / 格局粉渐变 + 粗标题 + 副标题）+ 分段器 + 色条卡片 + 粗标题 + 正文层级；深色页（首页/命盘/解读）同步分层（环境光 + 亮卡 + 彩色层级），不再黑乎乎一片。
   - 证据：shots-prod/knowledge.png、crop-knowledge-cover.png；深色见 home/chart/interpret。

### 悬浮圆角底栏（自定义 tabBar，Taro 4.x 实测结论）

- 微信自定义 tabBar 是 weapp 专属能力（Taro 文档支持矩阵：custom 列仅微信小程序 ✔，H5 ✘）；H5 下 custom:true 直接不出栏（实测 dist 含 custom:true 但 bundle 无组件代码）。
- 落地：weapp 由框架原生注入 src/custom-tab-bar/（dist/custom-tab-bar/ 已验，index.js/json/wxml/wxss 齐全）；H5 预览由 4 个 tab 页 + 我的 11 个分屏 return 以 WEB-only 分支同组件挂载（weapp 上该分支恒为 null，不双份）。
- 图标不用图片导入：两条实测陷阱——① Taro 会把 custom-tab-bar 内的小图 import 内联为 base64，而微信 <image> 不显示 base64；② v3 的 tabBar PNG 是画在 #111518 底上的不透明方块，不是透明字形，无法换色。最终图标为纯 View 矢量形（描边 = 未选中，填充 = 选中），深色 pill 白激活、浅色 pill 紫激活。
- 选中推导必须 mount + show 双跑：只 mount 会在 tab 切换时读到旧路由，只 show 会在我的分屏切换（同路由内新实例挂载、无 show 事件）时停在默认深色；双跑后深浅与激活态在 tab 切换、分屏切换、直链进入三路皆对（member 分屏深色栏 bug 即由此闭合）。
- .page 底部留白 230.77px（56pt 栏 + 12pt 底边距 + 安全区 + 呼吸）。

### 功能清单表（功能 → 界面状态 → 截图，全部实拍，无假数据）

| 功能 | 界面状态 | 截图 |
|---|---|---|
| 排盘表单 | 性别分段胶囊 + 实时预览卡 + 校正按钮（手动可撤销） | home.png、crop-home-form.png |
| 十二宫命盘 | 连线 + 金边选中 + 流年/小限角标 | chart.png、crop-chart-plate.png |
| 宫位详情卡 | 盘下详情卡 + 切换提示 | chart.png、crop-chart-detail.png |
| 全屏查看 | 专注覆盖层（同盘同选中） | chart-fullscreen.png |
| 大运流年流月 | 大运卡 + 流年/流月卡（今年农历年、虚岁） | chart.png（下半） |
| 13 维解读 | 格局 5 条 + 13 维 + 每处免责 | interpret.png |
| AI 解盘 / 问答 / 配图 | 诚实未配置态（需 envId，不展示假解读） | interpret.png（下半） |
| 知识库 | 分类封面 + 分段器 + 色条卡片 | knowledge.png、crop-knowledge-cover.png |
| 合盘对照 | 诚实缺口态（需 ≥2 保存盘 + 云配置） | mine-compare.png |
| 命盘历史 | EmptyState + 去首页排盘入口 | mine-charts.png |
| 会员中心 | 诚实未配置态 + 积分兑换按钮 | mine-member.png |
| 积分中心 | 规则 + 胶囊按钮 + 账本 EmptyState | mine-points.png |
| 邀请中心 | 绑定码 + 结算 + 小程序码入口 | mine-invite.png |
| 分享海报 | 浅色卡 + 深色画布作品 + 生成/保存按钮（此前深卡深字 bug 已修） | mine-poster.png |
| 我的订单 | EmptyState | mine-orders.png |
| 设置 | 性别分段胶囊 + 未成年人 Toggle + 指纹注 | mine-settings.png |
| 意见反馈 | 表单 + 提交 + 反馈 EmptyState | mine-feedback.png |
| 关于 / 隐私 / 条款 | 4 tab + 全文 | mine-legal.png |
| 组件演示 | 6 组件全部在位 | demo.png |
| 底栏 | 深色 pill（首页/解读）+ 浅色 pill（知识/我的） | 各页底部 |

并排对比（shots-prod/sbs/）：sbs-home（↔ welcome-dark）、sbs-interpret（↔ chat-dark-lisbon-cn）、sbs-knowledge（↔ home-light-cn）、sbs-mine（↔ credits-light），左为本轮新拍、右为 Medley 原图 390 宽缩放。

### 本轮修掉的既有 bug（顺带，不在原验收内但逐项过时撞见）

- 分享海报卡在浅色我的页里用深卡，导致 .page-light 文本重映射下深字压深底、按钮近乎不可见；PosterCard 仅用于我的海报分屏，改为浅色卡（画布本身仍是深色海报作品，属有意设计），重拍闭合。

### 验证收据

- `tsc --noEmit` 通过；`taro build --type weapp` 通过（仅既有 mini-css-extract chunk 警告）；`taro build --type h5` 通过；`engine:smoke` 768 盘 0 失败。
- callFn 调用点零改动（本轮未动 lib/cloud 与 cloudfunctions/）；engine/ 零改动；logo 三处零改动（assets/logo/、首页品牌行、我的头像 diff 为空）；6 交互组件 + 演示页零改动；v3 闭合 7 条零回退（环境光、标题一行、星曜着色、卡片玻璃、图标加粗、表单层级、命盘 plate 均在位）。
- H5 截图法说明：Taro H5 在 .taro_page 内滚动（overflow scroll，文档高恒 844），Playwright fullPage 只拍视口；截图时以 JS 临时放开滚动链（仅截图用，不改产品代码），再 fullPage 拍全页；像素本身未动过。

### v4 残留表（接 v3，带数）

| # | 残留项 | 具体差距 | 状态 |
|---|---|---|---|
| R2'' | TabBar 全局深色 | 已闭合：自定义悬浮 pill 深浅双 variant，真机尺寸与 H5 一致性仍待真机看一眼 | 待真机复核 |
| R7'' | 我的页主屏着色受限 | 部分闭合：服务卡已着色；会员/积分/订单真实数据着色仍待 envId 后自验，绝不造假 | 待用户给值（envId 后自验） |
| R12'' | 命盘连线真机行为 | H5 量测 + DOM 几何已验；微信真机上 pointer-events:none 透传与 createSelectorQuery 表现未验 | 待真机复核 |
| R13'' | 全屏非捏合缩放 | 覆盖层专注视图，标题与文档均诚实标注，不谎称捏合缩放 | 接受：诚实标注 |
| R14'' | 知识封面非照片 | 矢量渐变 + 抽象装饰代替照片（无图库、外链不可上架），已在文档与代码注释中明说 | 接受：诚实替代 |
| R3''、R6''、R9''、R10''、R11'' | 沿用 v3 | 见 v3 残留表 | 未变 |

### v4 补充：OCR 审查与证据重拍（2026-11-01 晚）

- OCR delegation 审查（ocr delegate preview → rule → workspace diff 逐文件，
  coverage：preview 20 项 = 本轮 16 项 reviewed + docseek 1 项 skipped（他人
  工作，不属本轮范围）+ 工具排除 3 项（md/log/db），100% accounted）：
  - F1（Medium，文档）：app.config.ts 注释称自定义栏用
    `src/assets/tabbar/float/` 透明重着色图——该目录已删，实际为代码绘制
    矢量形。已修注释。
  - F2（Medium，可维护）：详情卡 JSX 在主视图与全屏遮罩重复，且全屏版已
    漂移（缺三方四正/大运/流年/小限行）。已抽为 ChartPage 内 renderDetail
    （compact）渲染方法（不用内层组件，合项目惯例）；全屏 compact 版仅
    主星 + 维度正文，差异有注释。
  - F3（Low，健壮）：Cover 无兜底背景，未知 kind 会白字落浅底不可见。已
    给 .cover 加默认渐变（已知 4 类视觉不变）。
  - F4（Low，规则字面）：currentPath 与 createSelectorQuery 回调的 any
    补了一行注释（Taro API 本身弱类型 + try/catch 防护）。
  - 不修：静态内联 margin（沿用文件既有写法）、useEffect 依赖（derive
    只读 Taro API + setState，行为正确）、真机未验（见 R12''）。
  - 修复后重验：tsc 通过、weapp 构建成功（仅既有 chunk-common 警告）、
    引擎 smoke 768/0、图表与全屏重拍确认重构输出一致（详情卡内容、
    金边、三合/对宫线均在）。
- 证据事故与恢复（诚实记录）：OCR 修复后的一次 `rsync --delete` 同步
  （client → H5 预览目录）误删了预览目录下全部 v4 证据（shots-prod/、
  shots-medley-v2/、shots-medley-v3/、shots-interactions/）与拍摄/服务
  脚本（shot-prod.js、shot-crops.js、sbs-prod.py、server.js），并导致
  H5 构建产物 dist/index.html 丢失、旧服务 404。已全部重建：server.js
  （SPA 回退读预览根目录 spa-index.html，不再依赖 dist/index.html，
  故后续构建不再丢壳）、shot-prod.js、shot-crops.js、sbs-prod.py；17 张
  全页 + 6 张验收裁切 + 4 张 sbs 全部重拍，均为修复后代码的真实渲染。
  v2/v3 历史证据未恢复（仅 v4 证据重建；如需历史对比以仓库 CHANGELOG
  与 MEDLEY-COMPARISON.md 各章节文字记录为准）。教训：预览目录同步
  一律不用 --delete，只同步 src/config，工具与证据不进同步路径。
- 全页截图说明：position:fixed 的悬浮底栏在 Playwright fullPage 拼接图
  里会落在拼接中部（拼接产物，非产品行为）；真机上底栏恒在屏底，页底
  230.77px 留白保证末尾内容不被遮挡。验收裁切一律用视口截图，底栏位
  置真实。
