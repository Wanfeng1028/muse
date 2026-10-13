# Muse

这是 Muse 的实验场：一个文件夹代表一个项目。所有内容由 DeepSeek-V4-Flash 生成，由 Muse 负责编排与验收。

## 项目

| 项目 | 说明 | 状态 |
| --- | --- | --- |
| [kaoyan-os](./kaoyan-os) | 「考研指挥舱」——全栈考研复习管理系统。pnpm monorepo：Fastify 5 + TypeScript + SQLite 后端，Vite 6 + React 18 前端，packages/shared 共享类型。六大模块：复习计划、番茄专注、错题本、单词 SRS、真题统计、仪表盘。 | 工程化 v1 |
| [second-brain](./second-brain) | 「第二大脑」——个人知识库系统。Go 单二进制：net/http + modernc.org/sqlite（纯 Go SQLite）+ go:embed 内嵌 Web UI。功能：笔记 CRUD、标签、全文搜索相关性排序、[[双链]] 与知识图谱、Markdown 预览、统计；v0.2.0 灵魂功能「主动复习引擎」：SM-2 间隔重复 + 抽认卡复习流 + 每日回顾，笔记写完第二天自动进入复习。 | v0.2.0 |
| [drama-factory](./drama-factory) | 「AI 短剧工坊」——短剧生产管理与剧本生成系统。Java 21 + Spring Boot 3.3 + Spring Data JPA + H2，企业级分层架构，内置 Web 控制台（Tabler 1.6.1）。v2 打通剧本→分镜→AI 视频生成→ffmpeg 剪辑成片完整管线：分镜管理、视频任务状态机（mock/agnes 双 provider）→成片剪辑（拼接+SRT 字幕烧录）、生产看板。v2.1 生产级补强：Flyway 版本化迁移、提交幂等、优雅关闭。v2.2 生产级 DoD 第 2 轮：结构化日志+request_id 全链路、Resilience4j 熔断、提交限流、Docker Compose 一键部署。v2.3「AI 编剧引擎」：真实 DeepSeek-V4-Flash 接入剧本生成（大纲→严格四场式剧本，模板兜底），传输层 HTTP 主用 + CLI 回退双通道；分镜页三按钮（AI 生成/模板生成/查看剧本）+额度提示+来源/模型/耗时展示。 | 工程化 v2.3 |
| [mini-os](./mini-os) | 「网页操作系统」——浏览器里的桌面操作系统。Rust + Axum 0.7 + WebSocket + rusqlite（bundled SQLite）后端，原生 HTML/CSS/JS 可拖拽多窗口桌面。功能：虚拟文件系统 CRUD、应用注册表（文件管理器/编辑器/终端/设置/关于）、主题与壁纸持久化、WebSocket echo、统计。 | 工程化 v1 |
| [ledger](./ledger) | 「钱迹 · 个人财务管家」——个人财务管理系统。Python + FastAPI + SQLAlchemy 2.0（aiosqlite）+ SQLite，Jinja2 SSR Web UI（服务端渲染 SVG 图表）。功能：多账户记账、分类体系、月度预算与超支预警、统计分析、CSV 导入导出、周期账单提醒。 | 工程化 v1 |
| [sentinel](./sentinel) | 「哨兵 Sentinel」——站点可用性监控。Go 单二进制：HTTP(S)/TCP 双协议检查、证书到期天数、定时调度、状态翻转自动生成停机事件并 webhook 通知、可用率与延迟统计、内嵌 Web UI（三页：仪表盘/监控管理/事件）。 | 工程化 v1 |
| [docseek](./docseek) | 「文溯 DocSeek」——本地全文检索引擎 CLI + HTTP 服务。C++17 + CMake + SQLite FTS5（unicode61）。功能：递归目录索引、基于 mtime+size 的增量更新、BM25 相关性搜索与摘要片段、已删除文件自动清理、索引统计、JSON 输出；v2 新增 `serve` 常驻服务（自研 HTTP 服务器 + inotify 文件变更实时监控 + 内嵌 Web UI）。 | 工程化 v2 |
| [feedflow](./feedflow) | 「信流 FeedFlow」——自托管 RSS 阅读器。Python + Flask 3.1 + feedparser + trafilatura + APScheduler + SQLite FTS5（trigram 中文全文搜索）。功能：订阅源管理（分组/抓取间隔/启用开关）、APScheduler 后台定时抓取、trafilatura 正文提取（失败回落摘要）、三栏桌面式阅读器（未读/星标/全部过滤、快捷键 j/k/m/s）、FTS5 全文搜索、OPML 导入/导出、统计页；v1.2 灵魂功能：五维加权重要性排序 +「今日必读」页（每天最重要的 N 篇）+ 兴趣设置。 | 工程化 v1.2 |
| [linkshort](./linkshort) | 「短链 LinkShort」——自托管短链服务。Go 单二进制：chi v5 路由 + modernc.org/sqlite（纯 Go SQLite）+ go:embed 内嵌 Web UI + skip2/go-qrcode 二维码。功能：短链创建（自动 base62/自定义 slug）、302 跳转计数与访问日志、统计（总览/30 天曲线/Top 链接/Top Referer）、过期 410、启用开关、二维码 PNG、CSV 导入导出、API Key 鉴权、Web UI 四页（仪表盘/链接管理/详情/新建）。 | 工程化 v1 |
| [mortisedb](./mortisedb) | 「榫卯 MortiseDB」——NAS 玩家/小团队的本地多源数据拼装层。Go 单二进制：modernc.org/sqlite（纯 Go）+ go:embed 内嵌 Web UI。功能：YAML 声明式映射 SQLite/CSV/JSON/目录为表（schema 推断）、增量同步（updated_at 水位线+哈希兜底）、冲突策略（源优先级/手动）、类 SQL 视图（运行/导出 CSV）、定时任务+运行历史。 | 工程化 v1 |
| [interlude](./interlude) | 「幕间 Interlude」——分支叙事的 linter：给独立游戏叙事设计师/互动小说/剧本杀作者的开源桌面工具。Kotlin + Compose Desktop。自研叙事 DSL（行号精确报错）、一致性校验引擎（死路/不可达节点/变量未初始化/条件永假，5 条规则）、可视化分支图（层次化布局）、本地化文本抽取回填。 | v1 核心完成 |
| [stagecue](./stagecue) | 「舞监台 StageCue」——小剧场/脱口秀/校园演出的多端同步演出控台。Kotlin Multiplatform + Compose Desktop + Ktor：时间轴 cue 编排、WebSocket 毫秒级时钟同步（NTP 式）、幂等事件广播、离线操作日志。QLab 的开源跨平台中文平替。 |
| [voxloom](./voxloom) | 「声纹工坊 VoxLoom」——中文播客/有声书的文字剪辑工作站。C#/.NET 8 + Avalonia 跨平台桌面：转写稿当时间轴，文字删改自动生成音频剪辑（过零点防爆音），语气词一键弱化（-12dB），EDL 导出供 Premiere/Reaper 精修。自研 Core 库（WAV/波形金字塔/对齐/剪辑引擎）。 | v0.1.0 |

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

### ledger

进入项目目录，安装依赖并启动服务（需 Python 3.11+）：

```bash
cd ledger
make install
make dev
```

启动后打开 http://127.0.0.1:8100 即可使用。构建、测试与 Docker 的完整说明见 [ledger/README.md](./ledger/README.md)。

### sentinel

进入项目目录并构建启动服务（需 Go 1.23+）：

```bash
cd sentinel
make build
./sentinel
```

启动后打开 http://127.0.0.1:8200 即可使用。构建、测试与 Docker 的完整说明见 [sentinel/README.md](./sentinel/README.md)。

### docseek

进入项目目录并构建（需 CMake 3.28+ 与支持 C++17 的 GCC；首次配置需联网拉取 GoogleTest）：

```bash
cd docseek
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

建索引并搜索：

```bash
./build/docseek index ~/docs
./build/docseek search "关键词"
./build/docseek stats
```

启动 HTTP 检索服务（inotify 实时监控目录变更并自动增量索引，附带 Web 界面）：

```bash
./build/docseek serve --port 8080 --watch ~/docs
```

测试、Docker 与命令详解见 [docseek/README.md](./docseek/README.md)。

### feedflow

进入项目目录，安装依赖并启动服务（需 Python 3.11+）：

```bash
cd feedflow
make install
make run
```

启动后打开 http://127.0.0.1:8300 即可使用。手动抓取一次、OPML 导入、构建、测试与 Docker 的完整说明见 [feedflow/README.md](./feedflow/README.md)。

### linkshort

进入项目目录，构建并启动服务（需 Go 1.23+，首次启动会自动生成管理 API Key 并打印到日志）：

```bash
cd linkshort
make run
```

启动后打开 http://localhost:8080/ui/ 即可使用。配置、API 表、测试与 Docker 的完整说明见 [linkshort/README.md](./linkshort/README.md)。

### mortisedb

进入项目目录，构建并初始化（需 Go 1.23+）：

```bash
cd mortisedb
go build -o mortisedb ./cmd/mortisedb
./mortisedb init      # 生成 mortise.yaml 与示例数据源
./mortisedb sync      # 按配置同步所有源
./mortisedb serve     # 启动 Web UI，默认 http://localhost:8421
```

配置、API 表、发版对照报告见 [mortisedb/README.md](./mortisedb/README.md) 与 [mortisedb/docs/PRODUCTION_CHECKLIST.md](./mortisedb/docs/PRODUCTION_CHECKLIST.md)。

### voxloom

进入项目目录，构建并运行桌面端（需 .NET 8 SDK）：

```bash
cd voxloom
dotnet build VoxLoom.sln
dotnet run --project src/VoxLoom.Desktop
```

启动后点「载入演示」即走完 导入→对齐→删除→弱化→导出 全链路。测试用 SmokeRunner 直跑：`dotnet run --project tests/VoxLoom.SmokeRunner`。完整说明见 [voxloom/README.md](./voxloom/README.md)，发版对照报告见 [voxloom/docs/PRODUCTION_CHECKLIST_REPORT.md](./voxloom/docs/PRODUCTION_CHECKLIST_REPORT.md)。

### stagecue

需 JDK 21。启动同步服务与桌面导演台：

```bash
cd stagecue
./gradlew :server:run          # 同步服务 :8080
./gradlew :desktopApp:run      # 桌面导演台（自动连接 localhost:8080）
```

完整说明见 [stagecue/README.md](./stagecue/README.md)，发版对照报告见 [stagecue/docs/PRODUCTION_REPORT_v0.1.0.md](./stagecue/docs/PRODUCTION_REPORT_v0.1.0.md)。

## 目录约定

- 每个项目一个文件夹，且自带 README。
- 根目录 `PROJECTS.md` 是项目登记册，记录各项目的定位、技术栈、状态与里程碑。
