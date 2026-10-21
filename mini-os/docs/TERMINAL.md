# mini-os 终端（PTY）

## 1. 概述

mini-os 的终端是浏览器里的真 shell：服务端用 portable-pty 起一个 PTY，把用户的登录 shell 挂上去，前端用 xterm.js 渲染，中间通过 WebSocket 转发原始字节。不是模拟器，Tab 补全、命令历史、管道、Ctrl+C 都由真实 shell 和内核处理。

实现位于 `src/terminal.rs`，核心类型是 `TerminalManager`，依赖 `portable-pty` 0.8.1。

## 2. 会话模型

- 按用户隔离：会话挂在 `user_id` 下，一个用户只能操作自己的会话。
- 每用户上限 8 个会话。超限时服务端通过 WS 推送：
  `{"type":"term_error","message":"会话数量已达上限"}`
- 空闲回收：独立回收线程（reaper）每 60 秒检查一次，空闲超过 30 分钟的会话被回收。
- 断开清理：WS 连接断开时，服务端回收该连接对应的会话。
- shell：取用户的登录 shell（环境变量 `$SHELL`，缺省 `/bin/bash`）。
- 工作目录：用户的数据目录。

## 3. WS 协议

连接地址 `/ws`。连接前必须先完成 HTTP 登录（cookie 会话），未登录的连接会被拒绝。

### 3.1 客户端 → 服务端

| type | 字段 | 说明 |
| --- | --- | --- |
| `term_open` | `cols`, `rows` | 打开一个新会话。服务端成功回 `term_ready` |
| `term_input` | `session_id`, `data` | 发送输入。`data` 是原始字节流，终端输入是什么就透传什么；Tab 补全、命令历史都由 shell 自己处理 |
| `term_resize` | `session_id`, `cols`, `rows` | 调整 PTY 窗口大小 |
| `term_signal` | `session_id`, `signal` | 发送信号。`signal` 为 `"int"` 时向 PTY master 写 0x03 |
| `term_close` | `session_id` | 关闭会话 |

### 3.2 服务端 → 客户端

| type | 字段 | 说明 |
| --- | --- | --- |
| `term_ready` | `session_id` | 会话创建成功，返回会话 ID |
| `term_output` | `session_id`, `data` | PTY 输出，原样推送 |
| `term_exited` | `session_id`, `code` | shell 进程退出，附退出码 |
| `term_error` | `message` | 错误信息（限额、权限、会话不存在等） |

`term_open` 的响应示例：

```
{"type":"term_open","cols":80,"rows":24}
→ {"type":"term_ready","session_id":"..."}
```

## 4. 信号处理

Ctrl+C 不走应用层自定义逻辑，而是向 PTY master 写 0x03。这个字节进入 PTY 后，由终端驱动的 ISIG 机制转换为 SIGINT，投递给前台进程组。结果是前台进程被中断，shell 本身存活，提示符照常回来。

`term_signal` 的 `signal` 字段目前支持 `"int"`，即写 0x03。Ctrl+D 不通过 `term_signal`，前端直接发 0x04 作为输入。

## 5. 权限

`term_open` 要求 FsWrite 权限。viewer 角色发起 `term_open` 会被拒绝，服务端推送：

```
{"type":"term_error","message":"权限不足"}
```

## 6. 前端行为

- 渲染使用 `static/vendor/xterm.js`（5.3.0，vendored）。
- 多标签页，支持“+新标签”开新会话。
- 尺寸适配：用 canvas 测字宽做 fit，窗口变化时发 `term_resize`。
- Ctrl+C 被拦截，转为 `term_signal`（`signal: "int"`）；Ctrl+D 直接发 0x04。
- 断线自动重连，重连时保留标签页。
- 窗口关闭时发 `term_close`。

## 7. 测试与冒烟

- `tests/terminal_test.rs` 共 9 项，覆盖：用户隔离、会话限额、中断后 shell 存活、idle 回收。
- raw-socket WS 冒烟脚本，覆盖：401 未授权、hello、真命令回显、Ctrl+C 中断。

## 8. 运维指标

| 指标 | 类型 | 含义 |
| --- | --- | --- |
| `minios_terminal_opened_total` | counter | 累计打开的会话数 |
| `minios_terminal_sessions` | gauge | 当前会话数 |
| `minios_term_output_truncated_total` | counter | 终端输出被背压截断的累计次数 |

## 9. 已知限制

- Windows 下未验证。
- 超大输出背压（v1.10 已交付）：服务端按会话做输出预算（`read_chunk_limited`），超 `MINIOS_TERM_OUTPUT_LIMIT`（默认 1MiB）后截断推送并提示"[输出过长，已截断]"，持续排空 PTY 防子进程阻塞；客户端输入新命令重置预算。指标 `minios_term_output_truncated_total`。
