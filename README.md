# Muse

这是 Muse 的实验场：一个文件夹代表一个项目。所有内容由 DeepSeek-V4-Flash 生成，由 Muse 负责编排与验收。

## 项目

| 项目 | 说明 | 状态 |
| --- | --- | --- |
| [kaoyan-os](./kaoyan-os) | 「考研指挥舱」——全栈考研复习管理系统。pnpm monorepo：Fastify 5 + TypeScript + SQLite 后端，Vite 6 + React 18 前端，packages/shared 共享类型。六大模块：复习计划、番茄专注、错题本、单词 SRS、真题统计、仪表盘。 | 工程化 v1 |
| [second-brain](./second-brain) | 「第二大脑」——个人知识库系统。Go 单二进制：net/http + modernc.org/sqlite（纯 Go SQLite）+ go:embed 内嵌 Web UI。功能：笔记 CRUD、标签、全文搜索相关性排序、[[双链]] 与知识图谱、Markdown 预览、统计。 | 工程化 v1 |
| [drama-factory](./drama-factory) | 「AI 短剧工坊」——短剧生产管理与剧本生成系统。Java 21 + Spring Boot 3.3 + Spring Data JPA + H2，企业级分层架构，内置 Web 控制台。功能：项目/剧集/角色/场景管理、基于大纲的四场式剧本自动生成（每场带英文视频生成提示词）、全局统计。 | 工程化 v1 |
| [mini-os](./mini-os) | 「网页操作系统」——浏览器里的桌面操作系统。Rust + Axum 0.7 + WebSocket + rusqlite（bundled SQLite）后端，原生 HTML/CSS/JS 可拖拽多窗口桌面。功能：虚拟文件系统 CRUD、应用注册表（文件管理器/编辑器/终端/设置/关于）、主题与壁纸持久化、WebSocket echo、统计。 | 工程化 v1 |

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

### drama-factory

进入项目目录并启动服务（需 JDK 21 与 Maven 3.9，或直接用项目自带 mvnw）：

```bash
cd drama-factory
mvn spring-boot:run
```

启动后打开 http://localhost:8081 即可使用控制台。构建、测试与 Docker 的完整说明见 [drama-factory/README.md](./drama-factory/README.md)。

### mini-os

进入项目目录并启动服务（需 Rust 工具链）：

```bash
cd mini-os
cargo run
```

启动后打开 http://localhost:8090 即可进入桌面。构建、测试与 Docker 的完整说明见 [mini-os/README.md](./mini-os/README.md)。

## 目录约定

- 每个项目一个文件夹，且自带 README。
- 根目录 `PROJECTS.md` 是项目登记册，记录各项目的定位、技术栈、状态与里程碑。
