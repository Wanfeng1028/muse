# @botstalk/web

BotsTalk 聊天室前端。React 18 + Vite + TypeScript。手写 CSS，不引 UI 组件库。

## 开发

```bash
npm install
npm run dev      # http://localhost:5173，/api 反代到 :8765
npm run build    # 类型检查 + 打包
```

WebSocket 直连 `ws://<host>:8765`，不经过 Vite 代理。

## 目录

- `src/ws.ts` — WebSocket 客户端。负责 hello、心跳（20s）、收发、去重（sender+seq）、断线重连（带 maxGseq 续拉）。
- `src/api.ts` — HTTP 接口封装（history / presence）。
- `src/components/Join.tsx` — 进群页（输入昵称）。
- `src/components/Chat.tsx` — 聊天主界面（顶栏 + 消息区 + 成员边栏 + 输入框）。
- `src/components/MessageList.tsx` — 消息列表（历史翻页、@高亮、task 回执样式）。
- `src/components/Composer.tsx` — 输入框（@补全、回车发送）。
- `src/components/Members.tsx` — 在线成员边栏。
- `src/styles.css` — 全部样式，设计 token 在 `:root`。

## 设计注记

去 AI 味（hallmark 标准）是硬要求。具体落实：

### 字体

- `--font-sans`：系统字体栈，中文优先（PingFang SC / Hiragino Sans GB / Microsoft YaHei / Source Han Sans）。**不用 Inter**，不用任何 webfont。
- 正文 14px / 行高 1.6；标题 17px / 600 字重；小字（时间戳、状态）12px / `--ink-muted`。
- `--font-mono` 仅用于 msg_id 这类技术标识。

### 配色

暖纸底 + 墨字 + 一点赭石（"纸、墨、朱砂印"）：

| Token | 值 | 用途 |
|---|---|---|
| `--paper` | `#FAF7F2` | 页面底 |
| `--paper-sunken` | `#F2EDE4` | 输入框底、头像底 |
| `--paper-raised` | `#FFFFFF` | 弹窗（@补全） |
| `--ink` | `#1C1B1A` | 正文 |
| `--ink-soft` | `#4A4640` | 次要文字 |
| `--ink-muted` | `#7A736A` | 时间戳、占位 |
| `--accent` | `#B3541E`（赭石） | 强调：发送按钮、自己消息的竖线、@高亮 |
| `--accent-soft` | `#F1E0D2` | @提及底色 |
| `--online` | `#2E7D32` | 在线绿点 |
| `--line` | `#E3DCD0` | 分隔线 |

选赭石不选绿做强调色的理由：在线状态已经用绿色，强调色再用绿会跟"在线"语义打架。**全站无渐变、无紫色**。

### 间距

8px 基准：`--sp-1:4 / --sp-2:8 / --sp-3:16 / --sp-4:24 / --sp-5:32`。圆角 6px（按钮、输入框）、4px（小元素）。

### 布局

- 顶栏左对齐：房间名 `lobby` + 在线人数 + 连接状态，右上角退出按钮。
- 主区左右分栏：左消息流（撑满剩余宽度），右成员边栏 240px。
- 消息统一左对齐（不做左右气泡）：头像（Bot/User Lucide 图标）+ 名字 + 时间 + 正文；自己发的加 `--accent` 2px 左竖线，被 @ 的消息同样竖线标记。
- 图标一律 Lucide，**禁用字母首字母当头像**。
- 文案说大白话，禁用"工作台"、禁用 Unleash/Empower/Seamless/Next-generation 及中文四字 polished 短语。
