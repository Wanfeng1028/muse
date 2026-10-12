# 考研指挥舱 Kaoyan OS

> 面向考研备考场景的全栈复习管理系统：把计划、专注、错题、单词、真题与全局进度收进同一块「指挥舱」仪表盘。

## 项目简介

考研备考的痛点不在于缺少工具，而在于工具太散：计划表在 Excel、计时器在手机 App、错题在笔记软件、单词在另一个应用，最终没人知道整体进度到底如何。Kaoyan OS 用一套自托管的全栈系统把这些环节串起来——所有数据经 REST API 落到服务端 SQLite，不再依赖浏览器本地存储，换设备、清缓存都不会丢进度。

系统默认内置**初试倒计时（2026-12-19）**与**西电杭州研究院备考场景**的科目常量，开箱即可用于真实复习节奏，而非一个需要大量配置才能用的空壳。

## 功能列表

| 模块 | 说明 |
| --- | --- |
| 复习计划排程 | 按科目与阶段编排任务，跟踪每日/每周完成情况 |
| 番茄专注计时 | 专注会话记录，累计有效学习时长并回流到仪表盘 |
| 错题本 | 按科目/知识点归档错题，记录错因与重做状态 |
| 单词 SRS | 基于 SM-2 简化算法的间隔重复调度，管理复习队列与到期词 |
| 真题计时与得分统计 | 套卷计时、按题型/科目录入得分，输出趋势统计 |
| 仪表盘 | 初试倒计时、今日任务、专注时长、待复习单词、错题与真题得分概览 |

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
│   │   │   ├── routes/      # plans / focus / mistakes / words / exams / settings
│   │   │   ├── db/          # node:sqlite 初始化与迁移
│   │   │   └── index.ts     # 服务入口
│   │   └── dist/            # 构建产物
│   └── web/                 # Vite 6 + React 18 前端
│       ├── src/
│       │   ├── pages/       # 仪表盘、计划、专注、错题、单词、真题
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
| plans | `GET/POST /api/plans`，`PATCH/DELETE /api/plans/:id` | 复习计划增删改查与完成状态 |
| focus | `GET/POST /api/focus` | 番茄专注会话记录与统计 |
| mistakes | `GET/POST /api/mistakes`，`PATCH/DELETE /api/mistakes/:id` | 错题归档、错因与重做状态 |
| words | `GET/POST /api/words`，`POST /api/words/:id/review` | 词条管理与 SRS 复习结果提交 |
| exams | `GET/POST /api/exams` | 真题计时记录与得分统计 |
| settings | `GET/PUT /api/settings` | 考试日期、科目等配置 |

## 开发说明与路线图

开发约定：

- 共享类型统一放在 `packages/shared`，前后端不得各自复制一份定义。
- 所有持久化只走 REST API + SQLite，禁止在前端引入 localStorage 作为数据源。
- 新增端点需补充对应的 vitest 集成测试。

后续路线图：

1. **账号体系**：多用户注册登录、数据按用户隔离，支持多设备同步。
2. **数据导入导出**：全量 JSON 备份与恢复，兼容常见错题/单词表格式导入。
3. **移动端**：面向手机浏览器的响应式优化，并评估轻量原生客户端方案。
