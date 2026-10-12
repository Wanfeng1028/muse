# 第二大脑 Second Brain

## 简介

第二大脑（Second Brain）是一套面向个人的知识库系统，用于记录、组织和检索长期积累的笔记与想法。系统以单个 Go 二进制文件交付，内嵌 Web UI 与纯 Go 实现的 SQLite 驱动，无需外部依赖即可运行，适合在个人电脑、家用服务器或容器中自托管。

设计目标：

- **简单**：一条命令启动，数据落在本地文件，随时可备份、可迁移。
- **快速**：单进程服务，全文搜索带相关性排序，交互无明显延迟。
- **结构化**：标签体系与 `[[双链]]` 并存，既能扁平检索，也能构建知识图谱。

## 功能

- **笔记 CRUD**：创建、读取、更新、删除笔记，支持 Markdown 正文。
- **标签体系**：为笔记打标签，按标签聚合与筛选。
- **全文搜索**：关键词切分 + 标题/正文加权打分的相关性排序。
- **双向链接**：正文中书写 `[[笔记标题]]` 即建立链接，自动生成反向链接。
- **知识图谱**：以图谱形式展示笔记之间的链接关系，识别孤立节点与核心节点。
- **Markdown 渲染预览**：编辑时实时预览渲染结果。
- **统计概览**：笔记总数、标签分布、链接密度等指标一览。

## 技术栈

| 组件 | 选型 |
| --- | --- |
| 语言 | Go（>= 1.23） |
| HTTP | 标准库 `net/http` |
| 数据库 | SQLite，驱动为 `modernc.org/sqlite`（纯 Go，无 CGO） |
| 前端 | 原生 HTML/CSS/JS，通过 `go:embed` 内嵌进二进制 |
| 构建 | Makefile + `go build` |

不引入 Web 框架与 ORM，路由与 SQL 均直接编写，降低依赖面与升级成本。

## 目录结构

```
.
├── cmd/
│   └── server/          # 程序入口
├── internal/
│   ├── config/          # 环境变量配置
│   ├── store/           # SQLite 访问层与双链/图谱
│   ├── search/          # 关键词切分与相关性排序
│   ├── markdown/        # Markdown 渲染
│   ├── api/             # HTTP 路由与处理器
│   └── web/             # 用 go:embed 内嵌 static 前端资源
│       └── static/      # index.html / style.css / app.js
├── Makefile
├── Dockerfile
├── go.mod
└── README.md
```

## 快速开始

要求：Go >= 1.23。

```bash
go mod tidy
make run
# 或
go run ./cmd/server
```

启动后打开 <http://localhost:8080> 即可使用。首次运行会在数据目录自动创建数据库并完成初始化。

## 配置

通过环境变量配置，均有合理默认值：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `SB_ADDR` | HTTP 监听地址 | `:8080` |
| `SB_DB` | SQLite 数据库文件路径 | `<SB_DATA_DIR>/second-brain.db` |
| `SB_DATA_DIR` | 数据目录，存放数据库与后续附件 | `./data` |

示例：

```bash
SB_ADDR=127.0.0.1:9000 SB_DATA_DIR=/var/lib/second-brain go run ./cmd/server
```

## 构建与发布

```bash
make build
```

产物为单个可执行文件（默认输出到 `bin/`），前端资源已内嵌，可直接拷贝到目标机器运行，无需附带静态文件或运行时依赖。

交叉编译示例：

```bash
GOOS=linux GOARCH=amd64 make build
```

## 测试

```bash
go test ./...
go vet ./...
```

测试覆盖存储层、搜索排序与双链解析等核心逻辑。提交前建议同时运行 `go vet` 以捕获常见静态问题。

## Docker

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY . .
RUN go mod tidy && make build

FROM gcr.io/distroless/static
COPY --from=build /src/bin/second-brain /second-brain
VOLUME ["/data"]
ENV SB_DATA_DIR=/data SB_ADDR=:8080
EXPOSE 8080
ENTRYPOINT ["/second-brain"]
```

```bash
docker build -t second-brain .
docker run -d -p 8080:8080 -v sb-data:/data second-brain
```

数据卷 `sb-data` 即全部持久化状态，删除容器不影响数据。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查，返回服务与数据库状态 |
| GET/POST | `/api/notes` | 列出或创建笔记 |
| GET/PUT/DELETE | `/api/notes/{id}` | 读取、更新、删除单条笔记 |
| GET | `/api/search?q=` | 全文搜索，按相关性排序 |
| GET | `/api/tags` | 标签列表及计数 |
| GET | `/api/stats` | 统计概览 |
| GET | `/api/graph` | 知识图谱节点与边 |
| POST | `/api/preview` | Markdown 渲染预览 |

请求与响应均为 JSON。错误响应统一为 `{"error": "..."}` 结构。

## 数据与备份

所有数据保存在 `SB_DATA_DIR` 下的 SQLite 文件中。备份方式：

- 停止服务后直接复制数据库文件；
- 或在服务运行中执行 `sqlite3 <db> ".backup '<target>'"` 进行在线备份。

恢复时用备份文件替换原数据库即可。由于是单文件存储，也可以直接纳入 Git、rsync 或对象存储的定期同步流程。

## 路线图

- **附件**：支持图片与文件上传，随笔记存储与引用。
- **导出**：导出为 Markdown 目录或 JSON，便于迁移与归档。
- **账号**：多用户与登录鉴权，支持在共享服务器上安全使用。
