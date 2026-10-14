# Mini OS

一个运行在浏览器里的桌面操作系统。后端用 Rust 提供虚拟文件系统、应用注册表、设置与实时通信能力，前端是一套原生 JavaScript 实现的桌面环境：可拖拽窗口、开始菜单、文件管理器、文本编辑器、终端、设置与关于面板。所有文件与设置通过 SQLite 持久化，重启服务后状态不丢失。

项目位于 `mini-os/` 目录。

## 功能

- **虚拟文件系统**：文件夹与文件的增删改查，支持嵌套目录，数据落地 SQLite 表 `vfs_nodes`。
- **应用注册表**：内置 5 个应用——文件管理器、文本编辑器、终端、设置、关于。
- **设置持久化**：主题（theme）与壁纸（wallpaper）保存在 `settings` 表，刷新后保留。
- **统计面板**：文件数、文件夹数、占用字节数。
- **文件上传与下载**：`POST /api/files/upload?path=<目录>` 上传（multipart，单文件默认上限 50MB），`GET /api/files/download?path=<文件>` 流式下载；文件名消毒防路径穿越，二进制文件存 BLOB 列。



- **WebSocket 通道**：连接建立后服务端主动下发欢迎消息，文本消息原样回显。
- **桌面交互**：窗口拖拽、开始菜单、实时时钟、WebSocket 连接状态指示。

## 技术栈

| 组件 | 说明 |
| --- | --- |
| 语言 | Rust 2021 |
| Web 框架 | axum 0.7（含 ws） |
| 异步运行时 | tokio（full） |
| 序列化 | serde / serde_json（模型字段 camelCase） |
| 存储 | rusqlite 0.32（bundled，无需系统 SQLite） |
| 中间件 | tower 0.5、tower-http 0.5 |
| 前端 | 原生 HTML / CSS / JavaScript，无构建步骤 |

## 目录结构

```
mini-os/
├── Cargo.toml
├── src/
│   ├── main.rs          # 服务入口：读配置、初始化状态、绑定监听
│   ├── lib.rs           # AppState、init_state、build_app 路由装配
│   ├── config.rs        # 从环境变量读取 PORT / DATABASE_PATH / STATIC_DIR
│   ├── db.rs            # open_db 建表、seed 种子数据
│   ├── models.rs        # Node / AppInfo / Stats 等 serde 模型
│   └── handlers.rs      # health / apps / fs / settings / stats / ws 处理器
├── static/
│   ├── index.html       # 桌面外壳
│   ├── style.css        # 桌面与窗口样式
│   └── app.js           # 窗口管理、文件管理器、编辑器、终端等
├── tests/
│   └── api_test.rs      # 16 个集成测试



├── .env.example
├── .gitignore
├── Dockerfile
└── .github/
    └── workflows/
        └── mini-os.yml # CI：fmt / clippy / test / build
```

## 快速开始

需要安装 Rust 工具链（stable 即可，rusqlite 使用 bundled 特性，无需额外系统依赖）。

```bash
cd mini-os
cargo run
```

启动后打开浏览器访问：

```
http://localhost:8090
```

首次启动会自动创建数据库文件、建表并写入种子数据：根目录下生成 `Desktop/` 与 `Documents/` 两个文件夹，以及 `Desktop/welcome.txt`、`Documents/notes.txt` 两个文件；设置中预置 `theme=light`、`wallpaper=ocean`。

## 配置

配置全部通过环境变量读取，未设置时使用默认值：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8090` | HTTP 服务监听端口 |
| `DATABASE_PATH` | `data/mini-os.db` | SQLite 数据库文件路径，目录不存在时自动创建 |
| `STATIC_DIR` | `static` | 静态资源目录，提供 `index.html` 等前端文件 |
| `UPLOAD_MAX_BYTES` | `52428800`（50MB） | 单文件上传大小上限（字节） |




参考 `.env.example` 可以快速了解可用变量。若使用进程管理器或容器，直接在启动环境中注入即可。

## 构建与发布

```bash
cargo build --release
```

产物为单个二进制文件 `target/release/mini-os`。运行时需要与 `static` 目录同级部署，或通过 `STATIC_DIR` 指向实际静态资源路径；数据库位置通过 `DATABASE_PATH` 指定，建议指向一个持久化目录。

```bash
DATABASE_PATH=/var/lib/mini-os/mini-os.db STATIC_DIR=/opt/mini-os/static PORT=8090 ./mini-os
```

## 测试

```bash
cargo test        # 运行 16 个集成测试



cargo clippy      # 静态检查
cargo fmt         # 代码格式化
```

集成测试覆盖健康检查、应用列表、文件系统 CRUD、设置读写与统计、文件上传/下载（含超限 413、路径穿越拦截、同名 409、目录下载 400 等边界）等接口行为。CI（`.github/workflows/mini-os.yml`）会在每次提交时依次执行 fmt、clippy、test 与 build。




## Docker

```bash
docker build -t mini-os .
docker run --rm -p 8090:8090 -v mini-os-data:/app/data mini-os
```

容器内监听 8090 端口，数据卷挂载到 `/app/data` 以持久化 SQLite 文件。可通过 `-e PORT=...`、`-e DATABASE_PATH=...`、`-e STATIC_DIR=...` 覆盖默认配置。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/apps` | 应用注册表，返回内置应用列表 |
| GET | `/api/fs` | 列出节点，可按父目录查询 |
| POST | `/api/fs` | 新建文件夹或文件 |
| GET | `/api/fs/{id}` | 读取单个节点 |
| PUT | `/api/fs/{id}` | 更新节点（重命名、移动、写入内容） |
| DELETE | `/api/fs/{id}` | 删除节点 |
| GET | `/api/settings` | 读取设置 |
| PUT | `/api/settings` | 更新设置（theme、wallpaper） |
| GET | `/api/stats` | 统计信息：文件数、文件夹数、字节数 |
| POST | `/api/files/upload?path=<目录>` | 文件上传（multipart/form-data，字段名 `file`） |
| GET | `/api/files/download?path=<文件>` | 文件下载（流式，`Content-Disposition: attachment`） |
| GET | `/ws` | WebSocket 连接入口 |

## 界面截图

![文件管理器](docs/screenshots/files-manager.png)
![子目录浏览](docs/screenshots/files-folder.png)
![上传成功](docs/screenshots/files-uploaded.png)
![上传失败提示](docs/screenshots/files-error.png)




## WebSocket 协议

连接 `/ws` 后，服务端立即推送一条欢迎消息：

```json
{"type":"hello","message":"welcome to mini-os"}
```

客户端发送任意文本消息后，服务端按以下格式回显原文：

```json
{"type":"echo","message":"原文"}
```

前端利用该通道展示连接状态，并可作为后续实时功能的基础。

## 数据与备份

所有持久化数据都在一个 SQLite 文件里（默认 `data/mini-os.db`），包含 `vfs_nodes` 与 `settings` 两张表。备份时直接拷贝该文件即可；恢复时把文件放回 `DATABASE_PATH` 指向的位置再启动服务。SQLite 使用 bundled 版本，迁移到其他机器时无需额外安装数据库。

## 路线图

- 多用户与鉴权
- ~~文件上传与下载~~（v1.1.0 已完成）
- 应用商店，支持动态注册第三方应用




欢迎提交 issue 与 pull request。
