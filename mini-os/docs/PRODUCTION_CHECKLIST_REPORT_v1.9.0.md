# mini-os v1.9.0 生产检查清单对照报告

日期：2026-10-20
版本：1.8.0 → 1.9.0
范围：lane E 深耕轮交付（终端纵深、文件管理 v2、桌面美学、笔记/日程联动）

## 1. 范围

### 1.1 终端纵深（真 PTY）

新增 `src/terminal.rs`，实现 `TerminalManager`，基于 portable-pty 0.8.1 使用真 PTY。
会话按用户隔离，每用户上限 8 个会话，空闲 30 分钟回收；Ctrl+C 向 master 写入 0x03，
经 ISIG 产生 SIGINT；会话随 WS 断开在服务端回收。

WS 协议：
- 客户端 → 服务端：`term_open{cols,rows}`、`term_input{session_id,data}`、
  `term_resize`、`term_signal{signal:"int"}`、`term_close`
- 服务端 → 客户端：`term_ready{session_id}`、`term_output`、`term_exited`、`term_error`

`term_open` 校验 FsWrite 权限，viewer 被拒；旧 echo 行为兼容保留。

测试：`tests/terminal_test.rs` 9/9 通过（隔离、限额 8、中断后 shell 存活、idle 回收）。
raw-socket WS 冒烟：未登录 401、hello、`term_open`→`term_ready`、真命令回显、
Ctrl+C 中断 `sleep 30` 后 shell 存活，全部通过。

前端：vendored xterm.js 5.3.0（`static/vendor/`），多标签页、canvas 测字宽 fit、
Ctrl+C→signal、Ctrl+D、断线重连、窗口关闭清理会话。

### 1.2 文件管理 v2

- `PATCH /api/fs/:id/move`：环检测（移入自身后代→400）、同名冲突 409、跨用户 404、
  幂等（目标相同→200 无操作）。
- `GET /api/fs/search?q=`：LIKE 转义（`\`、`%`、`_`）防注入，返回面包屑 path。

测试：`tests/fs_v2_test.rs` 13/13 通过。

前端：右键菜单（重命名 / 移动到…文件夹选择器 + BFS 后代排除 / 删除二次确认）、
可点击面包屑、文件名搜索框（防抖 300ms，结果双击导航或打开编辑器）。

### 1.3 桌面美学打磨

- 窗口：双击标题栏最大化/还原、右下角拖拽缩放、任务栏窗口按钮高亮、
  `window-resize` 自定义事件（xterm fit 监听）。
- `docs/DESIGN.md` 新增纸墨桌面视觉注记：浅色纸 #F6F1E7 / 赭石 #B4552D，
  深色夜墨 / 琥珀 #D8A24A；禁紫渐变。
- 应用图标换成 Lucide SVG（真实 path 数据）；终端应用描述改为“真 PTY 终端”。

### 1.4 笔记/日程联动

- 迁移 007：`notes`（id/user_id/title/body/pinned/updated_at）、
  `events`（id/user_id/title/starts_at/ends_at/all_day/done/created_at）。
- 8 个接口：GET/POST `/api/notes`、PUT/DELETE `/api/notes/:id`、
  GET/POST `/api/events`、PUT/DELETE `/api/events/:id`。
  全部按 user_id 隔离（跨用户 404）；title 非空校验；时间格式校验
  （YYYY-MM-DD 或 YYYY-MM-DDTHH:MM，非法→400；ends_at<starts_at→400）。
- RBAC：新增 `Permission::NotesRead` / `NotesWrite`；Admin 读写、Editor 读写、
  Viewer 只读（写→403）。
- 测试：`tests/notes_test.rs` 9/9 通过（CRUD、隔离、viewer 只读、日期范围过滤）。
- 桌面小组件：今日日程（列表/勾选完成/删除/快捷输入“10:00 开会”）、
  速记便签（textarea，防抖 800ms 自动保存到置顶便签）；
  数据全部走后端 API，不用 localStorage 做唯一存储。

## 2. DoD 逐项对照表

| 需求 | 交付 | 证据 | 状态 |
| --- | --- | --- | --- |
| 真 PTY 交互 | `src/terminal.rs` + WS 协议 + xterm.js 5.3.0 | `tests/terminal_test.rs` 9/9；raw-socket 冒烟：term_open→term_ready、真命令回显、Ctrl+C 中断 `sleep 30` 后 shell 存活 | ✅ |
| 会话隔离 | 按用户隔离、每用户上限 8、空闲 30 分钟回收、WS 断开服务端回收 | `tests/terminal_test.rs` 覆盖隔离、限额 8、idle 回收 | ✅ |
| cargo test 覆盖 | 全绿（lib 58 + 各集成测试，含 terminal 9、fs_v2 13、notes 9） | `cargo test`；`cargo clippy --lib` 零警告；`cargo fmt --check` 通过 | ✅ |
| 拖拽上传 | 整份重传；分片/断点续传未做 | 需求明确不做分片/续传 | ✅ |
| 右键菜单 | 重命名 / 移动到… / 删除二次确认 | `docs/screenshots/v19-contextmenu.png` | ✅ |
| 面包屑 + 搜索 | 可点击面包屑、防抖 300ms 搜索框、LIKE 转义防注入 | `tests/fs_v2_test.rs` 13/13 | ✅ |
| 真实文件操作冒烟 | `PATCH /api/fs/:id/move` 环检测/同名 409/跨用户 404/幂等 | `tests/fs_v2_test.rs` 13/13 | ✅ |
| 窗口管理（拖拽/缩放/最小化/任务栏） | 双击标题栏最大化/还原、右下角缩放、任务栏高亮、`window-resize` 事件 | `docs/screenshots/v19-desktop-widgets.png` | ✅ |
| 壁纸 + 主题切换 | 浅色纸 #F6F1E7 / 赭石 #B4552D；深色夜墨 / 琥珀 #D8A24A | `docs/screenshots/v19-theme-dark.png` | ✅ |
| 设计注记 | `docs/DESIGN.md` 纸墨视觉注记（禁紫渐变） | 文档已更新 | ✅ |
| 真实截图 | 3 张亲眼验收截图 | `docs/screenshots/v19-desktop-widgets.png`、`v19-contextmenu.png`、`v19-theme-dark.png` | ✅ |
| 小组件（今日日程/速记便签） | 今日日程（增删/勾选完成/快捷输入）+ 速记便签（防抖 800ms 自动保存） | 截图 `v19-desktop-widgets.png` | ✅ |
| 后端持久化（禁 localStorage 唯一存储） | notes/events 表（迁移 007），8 个 REST 接口，数据全部走后端 API | `tests/notes_test.rs` 9/9；迁移 007 落库验证（7 条） | ✅ |

## 3. 未做/降级项

- 拖拽上传的分片/断点续传未做。需求明确不做，保持整份重传。
- xterm.js 的 `attachCustomKeyEventHandler`（`allowProposedApi`）Ctrl+C 拦截行为
  待真实浏览器长期实测确认。

## 4. 风险与已知限制

- 迁移 007 的 `migrate` 单测期望值为手工同步（更新为 007，7 条）。后续新增迁移时
  需同步更新该期望值，否则单测失败。
- viewer 角色变更后吊销会话需要重登才能生效。
- 终端会话上限为每用户 8，空闲 30 分钟回收；极端情况下并发多标签可能触顶。

## 5. 回滚建议

- 版本回滚：将 `Cargo.toml` 从 1.9.0 回退到 1.8.0，回滚前端 vendored xterm.js
  与终端/文件管理/笔记日程相关代码。
- 数据库：迁移 007 新增 `notes`、`events` 表，回滚时可保留表（无破坏性），
  或按需 DROP；不影响既有数据。
- WS 协议：旧 echo 行为兼容保留，回滚终端功能后旧客户端不受影响。
- 建议回滚前先导出 notes/events 数据，避免用户内容丢失。
