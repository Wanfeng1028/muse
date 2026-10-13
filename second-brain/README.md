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
- **主动复习引擎**（v0.2.0）：SM-2 间隔重复算法，笔记写完第二天自动进入复习流，抽认卡复习 + 每日回顾，详见下文。

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
| GET | `/api/review/queue?limit=` | 待复习队列（到期优先） |
| POST | `/api/review/{id}` | 提交复习评分（body `{"grade":4}`，0=忘记/3=困难/4=良好/5=简单） |
| GET | `/api/review/stats` | 复习统计（待复习数/连续天数/平均记忆强度） |
| GET | `/api/review/digest?n=` | 每日回顾（到期优先 + 最久未复习补足） |
| POST | `/api/preview` | Markdown 渲染预览 |

请求与响应均为 JSON。错误响应统一为 `{"error": "..."}` 结构。

## 主动复习引擎（v0.2.0）

笔记写完第二天自动进入复习流，快要忘记时推回来。

### 工作原理

笔记保存后不会立刻要你复习，而是先排进队列，第二天开始出现在复习页。每次你给出一个评价（忘记 / 困难 / 良好 / 简单），系统就按 SM-2 算法算出下一次该在什么时候再问你。评价越差，间隔缩得越短；评价越好，间隔拉得越长。如果某条笔记一直答得不错，它会慢慢从几天变成几周、几个月，最后基本不再打扰你。

SM-2 四档说明：

| 档位 | 含义 | 间隔影响 |
| --- | --- | --- |
| 忘记 | 完全想不起来，或答错了 | 间隔重置为 1 天，重新开始 |
| 困难 | 想起来了，但很吃力、不牢靠 | 间隔小幅增长（约 ×1.2），下次很快再见 |
| 良好 | 正常想起来，没什么卡顿 | 按标准倍数增长（约 ×2.5） |
| 简单 | 太容易了，几乎不用想 | 间隔大幅增长（约 ×3.5），并略微提前进入长间隔 |

### API

| 接口 | 说明 | 返回 |
| --- | --- | --- |
| `GET /api/review/queue?limit=20` | 取当前待复习的笔记队列，`limit` 控制条数（默认 20，上限 200） | JSON 数组，每项 `{id,title,body,snippet,tags,dueDate,overdueDays,ef,intervalDays,repetitions}` |
| `POST /api/review/{id}` | 提交某条笔记的复习评价，body 形如 `{"grade":4}` | `{ef,intervalDays,repetitions,dueDate,reviewedCount}`；grade 非法 → 400；笔记不存在 → 404 |
| `GET /api/review/stats` | 复习统计 | `{dueToday,totalNotes,reviewed7d,avgEf,streakDays}` |
| `GET /api/review/digest?n=5` | 每日回顾：到期优先，不足时用最久未复习的补足 | `{notes:[{id,title,snippet,tags,dueDate}]}` |

`grade` 取值：0 = 忘记，3 = 困难，4 = 良好，5 = 简单。

### 复习页使用说明

1. 打开复习页，页面显示一张抽认卡，正面是笔记标题或提示问题。
2. 想一下答案，点一下卡片翻到背面，核对全文内容。
3. 根据刚才的实际感受，点「忘记 / 困难 / 良好 / 简单」其中一个，系统自动排下一次复习时间，然后进入下一张。全部复习完会显示完成态。

### 截图

抽认卡正面：

![抽认卡正面](docs/screenshots/review-front.png)

翻面全文：

![翻面全文](docs/screenshots/review-back.png)

完成态：

![完成态](docs/screenshots/review-done.png)

### 已知限制

- 外部推送（邮件 / 微信）还没做，留到 v0.3，目前只能自己打开复习页。
- 只支持单用户，没有多账号和权限区分。

## 数据与备份

所有数据保存在 `SB_DATA_DIR` 下的 SQLite 文件中。备份方式：

- 停止服务后直接复制数据库文件；
- 或在服务运行中执行 `sqlite3 <db> ".backup '<target>'"` 进行在线备份。

恢复时用备份文件替换原数据库即可。由于是单文件存储，也可以直接纳入 Git、rsync 或对象存储的定期同步流程。

## 路线图

- **附件**：支持图片与文件上传，随笔记存储与引用。
- **导出**：导出为 Markdown 目录或 JSON，便于迁移与归档。
- **账号**：多用户与登录鉴权，支持在共享服务器上安全使用。
