# Muse

这是 Muse 的实验场：一个文件夹代表一个项目。所有内容由 DeepSeek-V4-Flash 生成，由 Muse 负责编排与验收。

## 项目

| 项目 | 说明 | 状态 |
| --- | --- | --- |
| [kaoyan-os](./kaoyan-os) | 「考研指挥舱」——全栈考研复习管理系统。pnpm monorepo：Fastify 5 + TypeScript + SQLite 后端，Vite 6 + React 18 前端，packages/shared 共享类型。六大模块：复习计划、番茄专注、错题本、单词 SRS、真题统计、仪表盘。 | 工程化 v1 |
| [second-brain](./second-brain) | 「第二大脑」——个人知识库系统。Go 单二进制：net/http + modernc.org/sqlite（纯 Go SQLite）+ go:embed 内嵌 Web UI。功能：笔记 CRUD、标签、全文搜索相关性排序、[[双链]] 与知识图谱、Markdown 预览、统计。 | 工程化 v1 |

## 如何运行

### kaoyan-os

进入项目目录并安装依赖：

```bash
cd kaoyan-os
pnpm install
```

启动开发环境（同时运行前后端）：

```bash
pnpm dev
```

- 前端：http://localhost:5173
- 后端：http://localhost:3001
- `/api` 由 Vite 代理到后端

构建、测试与 Docker 的完整说明见 [kaoyan-os/README.md](./kaoyan-os/README.md)。

### second-brain

进入项目目录并启动服务：

```bash
cd second-brain
go run ./cmd/server
```

或使用 Makefile：

```bash
make run
```

启动后打开 http://localhost:8080 即可使用。

## 目录约定

- 每个项目一个文件夹，且自带 README。
- 根目录 `PROJECTS.md` 是项目登记册，记录各项目的定位、技术栈、状态与里程碑。
