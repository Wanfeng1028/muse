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

**后端 API 一字未动**，仅替换模板与样式层。自定义 `theme.css` 只做两件事：容器宽度约束、表格密度微调；不覆盖任何组件质感（圆角、阴影、配色一律走 Tabler 默认）。

## 四、禁玻璃拟态声明

全站**禁用 `backdrop-filter`**，按钮**全部实色**。v3 的手写 CSS 玻璃拟态按钮已整体删除，不再作为任何页面的可选风格。后续新增组件同样不得引入半透明模糊质感。

## 五、视觉概念

「剪辑室 / 场记板」仅保留在**文案层**：页面眉题（kicker）沿用该意象措辞。**无任何自定义装饰**——不加贴纸、不加纹理、不加插画，视觉表达全部由 Tabler 组件承担。概念服务于语气，不服务于像素。
