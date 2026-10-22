# BotsTalk v0.3.0 运维手册

## 1. 架构与运行位置

BotsTalk 是单进程 Node 网关，内置 node:sqlite（WAL 模式）和 WebSocket 服务；Web 前端构建后的静态文件可以由网关直接提供（可选）。

- 进程：一个 node 进程，跑网关入口 `gateway/dist/index.js`。
- 端口：由 `GATEWAY_PORT` 决定，默认 `8765`。
- 数据目录：由 `DATA_DIR` 决定，默认 `./data`。
- 数据库文件：`DATA_DIR/botstalk.db`，WAL 模式下还会同时存在 `DATA_DIR/botstalk.db-wal` 和 `DATA_DIR/botstalk.db-shm`。
- 静态文件目录：由 `PUBLIC_DIR` 决定，可选；不设置时网关不提供静态文件，只提供 API 和 WebSocket。

## 2. 快速开始

### 2.1 Docker Compose 启动（推荐）

首次启动需要先构建镜像，再拉起容器：

```bash
docker compose build
docker compose up -d
```

之后日常启动只要：

```bash
docker compose up -d
```

compose 里用命名卷 `botstalk-data` 挂到容器内 `/data`，对应 `DATA_DIR=/data`，容器重启或重建不会丢数据。

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

### 2.2 本地跑

安装依赖（仓库用 npm workspaces，在仓库根目录执行）：

```bash
npm install
```

构建网关：

```bash
npm run build --workspace=botstalk-gateway
```

启动网关：

```bash
node gateway/dist/index.js
```

Web 前端有两种用法：

- 只用 API：不设 `PUBLIC_DIR`，网关不提供静态文件。
- 让网关直出前端：先把 Web 构建产物放到某个目录，再把 `PUBLIC_DIR` 指向它。

构建 Web：

```bash
npm run build --workspace=@botstalk/web
```

开发阶段可以起 Web 的开发服务器：

```bash
npm run dev --workspace=@botstalk/web
```

## 3. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GATEWAY_PORT` | `8765` | 网关监听的端口。 |
| `DATA_DIR` | `./data` | 数据目录，SQLite 数据库放在这里。 |
| `PUBLIC_DIR` | 无 | 静态文件目录。不设则不提供静态文件；设了则由网关直出该目录下的前端构建产物。 |
| `ROOM_MAX_MEMBERS_WORKROOM` | `50` | 工作坊房间成员上限（含 bot）。非法值（非正整数）网关启动直接报错退出。 |
| `ROOM_MAX_MEMBERS_PLAYROOM` | `200` | 娱乐厅房间成员上限。非法值网关启动直接报错退出。 |
| `GAME_BROADCAST_THROTTLE_MS` | `500` | 小游戏广播节流窗口（毫秒）。非法值网关启动直接报错退出。 |
| `TASK_APPROVAL_MODE` | `off` | 人工审批模式：`off` 直接派发；`all` 时所有任务先挂起待人工放行（Web 审批中心操作，TTL 5 分钟，过期自动取消）。非法值网关启动直接报错退出。 |

## 4. 备份与恢复

SQLite 在线备份优先用 `.backup`，不要直接 `cp` 正在写的库文件。WAL 模式下的 `-wal` / `-shm` 文件要跟主库一起考虑。

### 4.1 在线备份

在网关还跑着的时候，用 sqlite3 的 `.backup` 生成一致性快照：

```bash
sqlite3 "$DATA_DIR/botstalk.db" ".backup '$DATA_DIR/botstalk.db.bak'"
```

如果 `DATA_DIR` 就是默认的 `./data`：

```bash
sqlite3 ./data/botstalk.db ".backup './data/botstalk.db.bak'"
```

### 4.2 WAL 文件一并拷

如果走的是文件级拷贝（不是 `.backup`），必须把主库和 WAL 相关文件一起拷，否则恢复出来可能缺最近的事务：

```bash
cp ./data/botstalk.db ./data/botstalk.db-wal ./data/botstalk.db-shm /path/to/backup/
```

更稳的做法还是 4.1 的 `.backup`，它已经把 WAL 里的内容合进快照里了。

### 4.3 恢复步骤

恢复前先停服，避免有进程正在写库：

```bash
docker compose down
```

或者本地跑的话，先停掉那个 node 进程。

然后拿备份覆盖回数据目录：

```bash
cp /path/to/backup/botstalk.db ./data/botstalk.db
```

如果是用文件级拷贝的备份，`-wal` / `-shm` 也要一起放回去；如果只用 `.backup` 生成的单文件快照，就只放主库，删掉旧的 `-wal` / `-shm`，让 SQLite 重建：

```bash
rm -f ./data/botstalk.db-wal ./data/botstalk.db-shm
```

恢复完再启动：

```bash
docker compose up -d
```

## 5. 升级

数据在命名卷 `botstalk-data` 里，重建镜像不影响数据。升级流程：

```bash
git pull
docker compose build
docker compose up -d
```

compose 会用新镜像重建容器，`/data` 还是那个命名卷。

## 6. 排障

### 6.1 端口被占

现象：启动时报端口已被占用，进程起不来。

排查占用 `GATEWAY_PORT` 的进程，换端口或先停掉占用的进程，再重启。

### 6.2 WebSocket 被以 4400 关闭

含义：客户端握手首帧的 `protocol_version` 不等于 `"1.2"`。协议版本是 v1.2，网关只接受 `"1.2"`。

处理：升级客户端，让它发 `protocol_version: "1.2"`。

### 6.3 WebSocket 被以 4401 关闭

含义：握手首帧不是 `hello`。网关要求第一帧必须是 `hello`。

处理：检查客户端握手逻辑，保证连上之后第一帧就是 `hello`。

### 6.4 WebSocket 被以 4402 关闭

含义：同名顶号。同一个名字又连了一次，网关会关掉旧连接。

处理：检查是不是重复启动了一个 adapter（比如起了两个同名实例），关掉多余的。

### 6.5 `/healthz` 不通

`GET /healthz` 正常返回 `{"ok":true}`。不通时按顺序查：

- 进程是否活着。
- 端口是不是 `GATEWAY_PORT`，有没有被防火墙或反向代理挡住。
- 如果是容器，端口有没有映射出来。

### 6.6 任务一直停在 dispatched

含义：任务派下去了，但 adapter 那边没有推进。

常见原因：

- adapter 没连上网关（WebSocket 没连上，或者被 4400 / 4401 / 4402 关了）。
- adapter 连上了，但没有声明 task intent，网关不会把任务派给它。

处理：先看 adapter 的 WebSocket 连接状态，再看它握手时有没有声明 task intent。

## 7. 监控建议

- 存活探针：用 `GET /healthz`，返回 `{"ok":true}` 就算活着。
- 任务积压：用 `GET /api/tasks/stats?room=<room>` 看任务统计。如果 `dispatched + running` 长期不降，说明 adapter 卡住了，去看 adapter 的连接和 task intent。
- 单房间历史、在线、用量可以分别看 `GET /api/rooms/:room/history`、`GET /api/rooms/:room/presence`、`GET /api/rooms/:room/usage`。
- 未读数可以看 `GET /api/rooms/:room/unread?since_id=<id>`。
- 任务列表和单个任务可以看 `GET /api/tasks?room=&status=&limit=`、`GET /api/tasks/:task_id`；取消任务是 `POST /api/tasks/:task_id/cancel`，body 里带 `{requester}`。
- 待审批任务可以看 `GET /api/rooms/:room/approvals`（内存态，网关重启即丢；只返回元数据，不含原始任务帧）。审批操作在 Web 审批中心点按钮完成，走 `approval_decision` 帧；执行者不能给自己的任务放行（网关与 UI 双重拦截）。

## 8. 已知限制

- 单实例：数据库是 SQLite，只能跑一个网关实例，不要横向扩多个进程共享同一个 `DATA_DIR`。
- `PUBLIC_DIR` 没配时，直接访问网关根路径会 404，这是预期行为，API 照常工作。
