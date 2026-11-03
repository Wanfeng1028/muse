# drama-factory 设计规范

## 一、选型结论

**Tabler 1.6.1**。它是基于 Bootstrap 5 的管理后台 UI 套件，天生控制台气质，深色模式开箱即用——5 个候选中唯一为后台而生的库。

## 二、三步选型过程

| 步骤 | 动作 | 关键数据 | 结果 |
|---|---|---|---|
| 1. 候选 | dpsk 提名 5 个 | Bootstrap 5 / Tabler / Shoelace / Pico.css / Bulma | 进入核验 |
| 2. 核验 | Keenable 查证 | Tabler v1.6.1（2026-09-28 发布，~41k stars，活跃维护，MIT）；Bootstrap 5.3.8（~175k stars）；Bulma 维护节奏慢 | Tabler 胜出 |
| 3. 验证 | 本地 CDN 下载 + 无头浏览器渲染 | 页面渲染通过、深色模式生效、组件无破版 | 定稿 |

淘汰理由：Shoelace 偏 Web Components 通用组件、Pico.css 过于极简、Bulma 生态停滞。

## 三、落地方式

引入：`https://cdn.jsdelivr.net/npm/@tabler/core@1.6.1`，根节点 `data-bs-theme="dark"`。

五个页面——`index` / `storyboard` / `tasks` / `finals` / `pipeline`——**全部改用 Tabler 原生组件**：

- 按钮 `btn`、卡片 `card`、表格 `table`
- 状态 `badge`、进度 `progress`
- 表单 `form-select`
- 导航 `navbar`、弹窗 `modal`、提示 `alert`

**后端 API 一字未动**，仅替换模板与样式层。自定义 `theme.css` 做三件事：容器宽度约束、表格密度微调、**深色暖炭化主题变量覆盖（v4.1，见第六节）**；组件质感（圆角、阴影）一律走 Tabler，配色经暖炭化变量统一收敛。

## 四、禁玻璃拟态声明

全站**禁用 `backdrop-filter`**，按钮**全部实色**。v3 的手写 CSS 玻璃拟态按钮已整体删除，不再作为任何页面的可选风格。后续新增组件同样不得引入半透明模糊质感。

## 五、视觉概念

「剪辑室 / 场记板」仅保留在**文案层**：页面眉题（kicker）沿用该意象措辞。**无任何自定义装饰**——不加贴纸、不加纹理、不加插画，视觉表达全部由 Tabler 组件承担。概念服务于语气，不服务于像素。

## 六、深色暖炭化 v4.1（去"黑底霓虹"AI 味）

**诊断**：Tabler 默认深色 = 冷调近纯黑底 + 高饱和亮蓝主色 + 近纯白字，用户一眼判定"黑色系参数不对、有 AI 味"。
**修法**：只在 `theme.css` 里覆盖 `[data-bs-theme="dark"]` 的主题变量，不换库、不动结构、不动 API。

| 变量名 | 改前（Tabler 默认） | 改后（暖炭化） | 改动理由 |
|---|---|---|---|
| `--tblr-body-bg` / `-rgb` | `oklch(20.46% 0 0)` ≈ `#171717` | `#1c1917`（28,25,23） | 冷中性黑 → 带暖底调的炭色，去"机房感" |
| `--tblr-bg-surface` | `oklch(26.86% 0 0)` ≈ `#262626` | `#262220` | 保持明度分层，注入暖调与页面协调 |
| `--tblr-body-color` / `-rgb` | `oklch(92.19% 0 0)` ≈ `#e8e8e8` | `#ede8e2`（237,232,226） | 米白代冷白；对比度 14.36:1 ✅ |
| `--tblr-muted` / `-rgb` | `oklch(55.55% 0 0)` | `#b8b0a6`（184,176,166） | 柔和暖灰；对比度 8.16:1 ✅ |
| `--tblr-border-color` | `oklch(dark+0.08)` 冷灰 | `#3a3532` | 暖灰低对比，分割线不抢视觉 |
| `--tblr-primary` / `-rgb` | `oklch(54.6% 0.1724 254)` ≈ `#066fd1` | `#4a6fa5`（74,111,165） | chroma 减半去霓虹；白字按钮对比度 5.11:1 ✅ |
| `--tblr-success` / `-rgb` | `#2fb344` 亮绿 | `#5e8c61`（94,140,97） | 苔绿收敛 |
| `--tblr-danger` / `-rgb` | `#d63939` 亮红 | `#b5544c`（181,84,76） | 陶土红收敛 |
| `--tblr-warning` / `-rgb` | `#f59f00` 亮橙 | `#c98a3f`（201,138,63） | 赭橙，与暖调一致 |

**验收**：5 页重截亲眼对比，AI 味消除；WCAG 正文对比度全部 ≥4.5:1；全站零 `backdrop-filter`（注释文本除外）；JS 零错误。

## 七、默认亮色暖白主题（用户指令"默认亮色吧"，后经"高级感打磨轮"降饱和）

- `data-bs-theme` 默认 `light`；深色暖炭主题完整保留，侧边栏底部太阳/月亮切换钮，`localStorage('df-theme')` 记住选择；`<head>` 内联预置脚本防闪烁。
- 亮色走克制暖白路线（高级感打磨轮：`#F5F4EE` 米黄显廉价 → `#F8F7F4` 几乎看不出黄；高级感 = 低对比和谐 + 留白 + 字距，不靠颜色跳）。

| 变量 | 深色值 | 亮色值 | 说明 |
|---|---|---|---|
| `--bg` | `#1c1917` | `#F8F7F4` | 暖白底，几乎看不出黄 |
| `--bg-elev` | `#242019` | `#F1EFEA` | 侧边栏/顶栏 |
| `--surface` | `#292524` | `#FFFFFF` | 卡片纯白，靠暖调阴影分层 |
| `--surface-2` | `#2e2a26` | `#F4F2ED` |  |
| `--border` / `--border-soft` | `#2e2a26` / `#292524` | `rgba(30,25,15,.14)` / `rgba(30,25,15,.08)` | 发丝线 |
| `--text` | `#e7e5e4` | `#201C16` | 暖墨正文，对比度 ~14:1 ✅ |
| `--text-2` | `#a8a29e` | `#6E665A` | 次要，~5.7:1 ✅ |
| `--text-3` | `#78716c` | `#9A917F` | 辅助装饰 |
| `--accent` / `--accent-hover` | `#4a6fa5` / `#5a7fb5` | `#4a6fa5` / `#3E5F92` | 主行动点专用；hover 亮底加深 |
| `--green` / `--amber` / `--red` | `#5f8a5f` / `#b98a3e` / `#b0564a` | `#4E7A51` / `#9E742E` / `#A6493F` | 纸面加深保证对比度 |
| `--ink` / `--ink-text` / `--ink-hover` | `#EDE8E2` / `#201C16` / `#FFFFFF` | `#2B2620` / `#FFFFFF` / `#342E26` | 主按钮：亮色墨底白字，深色反转为暖纸底墨字 |
| `--shadow-card` | — | `0 1px 2px rgba(60,50,30,.05)` | 卡片暖调阴影 |
| `--tblr-body-bg` / `--tblr-body-color` / `--tblr-bg-surface` / `--tblr-border-color` | 见第六节 | `#F8F7F4` / `#201C16` / `#FFFFFF` / `rgba(30,25,15,.14)` | Tabler 暖白同步 |

**验收**：7 页亮色重截亲眼验收（真实数据《最后一班地铁》）；深色抽查 2 页无回归；全站零 `backdrop-filter`。

## 八、高级感打磨轮（用户反馈：单调/米黄廉价/按钮四方/无真 Logo）

1. **按钮去方形**：`.btn-primary` → 深墨 `#2B2620` + 白字 + 全圆角 pill（999px），hover 只做 4% 明度变化；`.btn-secondary` → 透明底 + hairline 边框 + 10px 圆角；chips → hairline + pill；Tabler 默认 4px 方按钮全局覆盖。
2. **真 Logo**：场记板简化几何线条 + 内嵌播放三角（SVG mark，单色暖墨 `#2B2620`，`currentColor` 随主题反白；无字母缩写、无渐变）。3 选 1：稿 A（板条播放）28px 下最清晰，稿 B 胶片齿孔太碎、稿 C 交叠负形太抽象。落地：sidebar 28px + `favicon.svg`。
3. **去单调**：首页 composer 下方加「最近动态」安静列表，调现有 API（episodes/final-cuts）取最近 5 条真实记录（状态圆点 + 相对时间），空数据时一句克制空状态。修过 2 个 bug：质检枚举按 `PENDING/APPROVED/REJECTED` 映射（初版误用 PASSED/FAILED）；切换项目时列表不刷新。

**验收**：7 页亮色 + logo 特写亲眼验收；深色抽查 2 页（主按钮深色变量缺失导致透明，被抓出并修复）；`mvn test` 38/38 全绿。
