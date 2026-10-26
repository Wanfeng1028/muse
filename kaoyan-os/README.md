# 考研指挥舱 Kaoyan OS

> 面向考研备考场景的全栈复习管理系统：把计划、专注、错题、单词、真题与全局进度收进同一块「指挥舱」仪表盘。

## 项目简介

考研备考的痛点不在于缺少工具，而在于工具太散：计划表在 Excel、计时器在手机 App、错题在笔记软件、单词在另一个应用，最终没人知道整体进度到底如何。Kaoyan OS 用一套自托管的全栈系统把这些环节串起来——所有数据经 REST API 落到服务端 SQLite，不再依赖浏览器本地存储，换设备、清缓存都不会丢进度。

系统默认内置**初试倒计时（2026-12-19）**与**西电杭州研究院备考场景**的科目常量，开箱即可用于真实复习节奏，而非一个需要大量配置才能用的空壳。

## 功能列表

| 模块 | 说明 |
| --- | --- |
| 复习计划排程 | 按科目与阶段编排任务，跟踪每日/每周完成情况 |
| 番茄专注计时 | 专注会话记录，累计有效学习时长并回流到仪表盘；可关联今日复习计划，计划页显示每条计划的"已专注/计划分钟"达成率进度条 |
| 错题本 | 按科目/知识点归档错题，记录错因与重做状态 |
| 单词 SRS | 基于 SM-2 简化算法的间隔重复调度，管理复习队列与到期词 |
| 真题计时与得分统计 | 套卷计时、按题型/科目录入得分，输出趋势统计、本阶段汇总与各科汇总（场次/平均分/得分率/最高分/进步幅度） |

| 仪表盘 | 初试倒计时、今日任务、专注时长、待复习单词、错题与真题得分概览 |
| 数据导入导出 | 全量 JSON 备份与恢复（覆盖/合并）、单词 / 错题 / 真题 / 计划 / 专注 CSV 导入、错题/单词/计划/专注 CSV 导出（与真题导出同口径：BOM + RFC4180 转义） |
| 深色模式 | 浅/深主题一键切换，偏好存服务端多端同步，深色板为 slate 家族配色体系 |
| 自律热力图 | 近 1/3/6 个月专注热力图、当前/最长连续打卡与累计专注天数，点击格子查看当日专注、计划、错题、模考明细 |
| 周报 | 本周概览卡、7 天专注条形、计划完成率圆环、上周对比、连续打卡 |
| 排期周视图 | 甘特式 7 列周视图：新学/复习/手动三色块，拖拽改日期，单日超负荷预警 |
| 错题组卷 | 按科目/掌握度/时间范围组卷，自评答对错，打印友好，批改回写掌握度 |
| API 文档 | docs/API.md：全部端点参数/错误码表，测试强制代码文档同步 |


## 深色模式

v1.2.0 起支持浅色 / 深色两套主题。

切换入口在侧边栏底部，按钮文案跟着当前主题走：现在是浅色就显示"深色模式"，点一下变深色；现在是深色就显示"浅色模式"。没有 emoji 图标。

实现上不换组件、不换 class 名，靠 `document.documentElement` 上的 `data-theme` 属性驱动，`index.css` 里用 `[data-theme="dark"]` 覆盖全部设计 token。所以新增页面只要用了 token，就自动有深色。

深色板是 slate 家族，和既有侧边栏（#141824）同一族，不会出现"侧边栏是深色、内容区是纯黑"的割裂感：

- 页面底色 #161a23，卡片 #1e2430
- 正文文字 #e6e9f0，次要文字 #9aa0ae
- 边框 #2a3040
- 科目四色在深色下提亮一档，保证仍然可辨识
- 阴影改弱黑影，深色下不做大面积投影

偏好存在服务端的 settings 表里（key-value），换设备登录后主题跟着走，不用重新点。写入走 `PUT /api/settings {theme}`，theme 只接受 `light` / `dark`，其它值返回 400。

截图：

![深色仪表盘](docs/screenshots/dark-dashboard.png)

![深色单词页](docs/screenshots/dark-words.png)

浅色对照：

![浅色仪表盘](docs/screenshots/light-dashboard.png)

![真题分科汇总](docs/screenshots/exams-bysubject.png)

## 自律热力图

v1.3.0 起新增「自律热力图」页面（导航在"周报"之后）：把每天的专注分钟数画成 GitHub 贡献图式的热力图，格子越深代表当天专注越久。

- 数据：`GET /api/stats/heatmap?months=N` 按天聚合专注、计划、错题、模考，并算出当前连续打卡、最长连续、累计专注天数。
- 视觉逻辑：单色系蓝色五档（0/1~30/31~60/61~120/>120 分钟），浅色 `#c9e2fb → #2f74e0`，深色 `#1e4068 → #5b9bf3`，与 slate 深色板同族；月份标签、少→多图例；hover 显示当日明细（title 原生提示），点击格子展开当日详情卡（含当日专注会话列表）。
- 文案用大白话，不做营销腔。

![自律热力图（浅色）](docs/screenshots/light-heatmap.png)

![自律热力图当日详情（浅色）](docs/screenshots/light-heatmap-detail.png)

![自律热力图（深色）](docs/screenshots/dark-heatmap.png)

## 周报视图

v1.4.0 起 /weekly 周报页升级为完整周报视图。数据来自 GET /api/stats/weekly：本周专注、计划完成率、连续打卡、新增错题、模考场次，外加 7 天每日专注分钟。连续打卡口径和热力图一致：今日有专注就从今日往前数，否则从昨日往前数。视觉延续 v1.3.0 热力图体系（蓝五档：浅 #c9e2fb→#2f74e0 / 深 #1e4068→#5b9bf3），深色模式跟随 data-theme，没引入新配色和新字体。

![周报视图（浅色）](docs/screenshots/light-weekly.png)

![周报视图（深色）](docs/screenshots/dark-weekly.png)

## 排期周视图（甘特）

v1.12.0 起 /plans/gantt 排期周视图：把一周的计划铺成甘特式的 7 列（周一到周日），一眼看出哪天排多了。

- 色块按类型区分：新学=科目色实心白字，复习=科目色描边淡底，手动添加=中性灰；已完成的半透明加删除线。
- 列头显示日期、周几和当天总分钟数；当天总分钟超过"每日分钟数"时，列头标"超负荷"，页面顶部出预警条，直说超了多少分钟。
- 色块可以直接拖到另一天的列上，松开就改期（调 PATCH /api/plans/:id）。
- 数据：GET /api/plans/overload?weekStart=&dailyMinutes= 一次拿 7 天的负荷明细；GET /api/plans/range?from=&to= 按区间拉计划（最多 62 天）。
- 视觉就是信息密度优先的工具表：颜色只用科目四色加灰加警告橙红，深色模式跟 data-theme 走，没有写死的颜色。

![排期周视图（浅色）](docs/screenshots/gantt-light.png)

![排期周视图（深色）](docs/screenshots/gantt-dark.png)

## 错题组卷

v1.12.0 起 /mistakes/quiz 错题组卷：从错题本里按条件抽一套题，当场自测，测完掌握度自动回写。

1. 组卷条件：科目、只组未掌握（默认勾上）、错题创建日期范围、题数（1~100）。
2. 答题：每题显示题目内容，自己先做，然后点"答对了"或"答错了"；右上角"打印试卷"可打出纸质版（打印样式已适配）。
3. 成绩：正确率、答对/答错数，以及"回写了 N 道题的掌握度"；答对的标已掌握，答错的打回未掌握。
- 组卷接口故意不返回解析（analysis），做完之前看不到答案。

![错题组卷（组卷条件）](docs/screenshots/quiz-form.png)

![错题组卷（答题与成绩）](docs/screenshots/quiz-result.png)

## API 文档

v1.12.0 起 docs/API.md 为全部接口的契约文档：每章按方法/路径/认证/参数表/成功示例/错误码表写全，另有错误码速查附录。

- tests/api-docs-sync.test.ts 用 Fastify 的 onRoute 钩子把注册的路由全枚举出来，逐个断言文档里有对应的 `METHOD /api/xxx` 标题；以后加接口、改路径、删接口，必须同步改文档，否则测试挂掉。

## 技术栈


- **包管理 / 仓库结构**：pnpm workspace monorepo
- **后端** `apps/server`：Fastify 5 + TypeScript + SQLite（Node 内置 `node:sqlite`，无原生依赖）
- **前端** `apps/web`：Vite 6 + React 18 + TypeScript + React Router
- **共享层** `packages/shared`：跨端共享类型定义与科目常量
- **数据流**：前端 → REST API → SQLite，服务端为唯一数据源

## 目录结构

```
kaoyan-os/
├── apps/
│   ├── server/              # Fastify 5 + TypeScript 后端服务
│   │   ├── src/
│   │   │   ├── routes/      # plans / focus / mistakes / words / exams / settings / backup
│   │   │   ├── db/          # node:sqlite 初始化与迁移
│   │   │   └── index.ts     # 服务入口
│   │   └── dist/            # 构建产物
│   └── web/                 # Vite 6 + React 18 前端
│       ├── src/
│       │   ├── pages/       # 仪表盘、计划、专注、错题、单词、真题、数据导入导出
│       │   ├── api/         # REST 客户端封装
│       │   └── main.tsx
│       └── dist/            # 前端构建产物（由后端托管）
├── packages/
│   └── shared/              # 共享类型与科目常量
├── package.json
├── pnpm-workspace.yaml
└── Dockerfile
```

## 快速开始

**环境要求**：Node.js >= 20（`node:sqlite` 依赖），pnpm。

```bash
pnpm install
```

**一键启动前后端**：

```bash
pnpm dev
```

**或分别启动**：

```bash
pnpm dev:server
pnpm dev:web
```

默认地址：

- 前端：http://localhost:5173
- 后端：http://localhost:3001
- 前端 `/api` 请求经 Vite 代理转发到后端，无需额外配置跨域

## 构建与生产运行

```bash
pnpm build
node apps/server/dist/index.js
```

生产模式下通过 `WEB_DIST` 指定前端构建产物目录，由 Fastify 直接托管静态资源与 SPA 回退，单进程即可对外服务。

## 测试

```bash
pnpm test
```

后端采用 vitest 编写集成测试，覆盖各 REST 端点与数据库读写路径。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `3001` | 后端监听端口 |
| `DATABASE_PATH` | `./data/kaoyan.db` | SQLite 数据库文件路径 |
| `WEB_DIST` | 未设置 | 前端构建产物目录，设置后由后端托管静态资源 |
| `NODE_ENV` | `development` | 运行环境标识 |

## Docker

```bash
docker build -t kaoyan-os .
docker run -d \
  --name kaoyan-os \
  -p 3001:3001 \
  -v kaoyan-data:/app/data \
  -e NODE_ENV=production \
  kaoyan-os
```

数据库文件位于容器内 `/app/data`，挂载数据卷即可持久化，重建镜像不丢数据。

## API 概览

| 分组 | 主要端点 | 说明 |
| --- | --- | --- |
| health | `GET /api/health` | 服务健康检查 |
| plans | `GET/POST /api/plans`，`PATCH/DELETE /api/plans/:id`，`GET /api/plans/summary`，`GET /api/plans/export` | 复习计划增删改查与完成状态；summary 返回逐计划 actualMinutes（关联专注分钟和）；export 按科目筛选导出 CSV |
| focus | `GET/POST /api/focus`（POST 可选 planId 关联计划） | 番茄专注会话记录与统计 |
| mistakes | `GET/POST /api/mistakes`，`PATCH/DELETE /api/mistakes/:id`，`GET /api/mistakes/summary`，`GET /api/mistakes/export` | 错题归档、错因与重做状态、掌握率汇总；export 按科目筛选导出 CSV |
| words | `GET/POST /api/words`，`POST /api/words/:id/review`，`GET /api/words/export` | 词条管理与 SRS 复习结果提交；export 按来源筛选导出 CSV（含 SRS 列） |
| exams | `GET/POST /api/exams`，`GET /api/exams/trend`，`GET /api/exams/summary`，`GET /api/exams/summary/by-subject`，`GET /api/exams/export` | 真题计时记录、得分率趋势、本阶段汇总统计与 CSV 导出 |
| settings | `GET/PUT /api/settings` | 考试日期、科目等配置 |
| stats | `GET /api/stats/weekly`，`GET /api/stats/heatmap` | 周报聚合（专注分钟/计划完成率/新增错题/模考场次/连续打卡 + 7 天每日专注分钟）；热力图聚合（专注/计划/错题/模考按天聚合 + 连续打卡统计） |
| 排期 | `GET /api/plans/range?from=&to=`，`GET /api/plans/overload?weekStart=&dailyMinutes=` | 区间计划查询（≤62 天）；周负荷明细与单日超负荷判定 |
| 组卷 | `POST /api/mistakes/quiz/generate`，`POST /api/mistakes/quiz/grade` | 按条件组卷（不含解析）；自评批改并回写掌握度 |

| 备份导入 | `GET /api/backup/export`，`POST /api/backup/import`，`POST /api/import/words`，`POST /api/import/mistakes`，`POST /api/import/exams`，`POST /api/import/plans` | 全量备份导出/恢复（覆盖·合并）、单词 / 错题 / 真题 / 计划 CSV 导入 |

## 开发说明与路线图

开发约定：

- 共享类型统一放在 `packages/shared`，前后端不得各自复制一份定义。
- 所有持久化只走 REST API + SQLite，禁止在前端引入 localStorage 作为数据源。
- 新增端点需补充对应的 vitest 集成测试。

后续路线图：

1. **账号体系**：多用户注册登录、数据按用户隔离，支持多设备同步。
2. **数据导入导出**：~~全量 JSON 备份与恢复，兼容常见错题/单词表格式导入。~~（2026-10-15 已交付 v1.1.0）
3. **深色模式**：~~浅/深主题切换 + 服务端偏好持久化。~~（2026-10-16 已交付 v1.2.0）
4. **考研核心 500 词库扩充**：~~500 个考研英语核心词 JSON 词库（word/phonetic/pos/meanings_zh/example_en/example_zh），POST /api/words/import 幂等导入（按 word 去重），单词表新增 source 来源字段（内置种子/核心500词库/手动录入/CSV导入），前端单词页支持按来源筛选与学习进度展示。~~（2026-10-16 已交付）
5. **移动端**：面向手机浏览器的响应式优化，并评估轻量原生客户端方案。
6. **周报视图**：~~GET /api/stats/weekly 周统计聚合（专注/计划/单词/错题/模考），前端 /weekly 周报页（本周/上一周切换、四科专注条、计划完成率、单词进度）。~~（2026-10-16 已交付）；v1.4.0（2026-10-16）深化：7 天专注条形、完成率圆环、上周对比、连续打卡
7. **自律热力图**：~~GET /api/stats/heatmap 按天聚合（专注/计划/错题/模考）+ 连续打卡统计，前端 /heatmap 热力图页（GitHub 贡献图式、1/3/6 个月切换、点击格子看当日详情）。~~（2026-10-16 已交付 v1.3.0）

