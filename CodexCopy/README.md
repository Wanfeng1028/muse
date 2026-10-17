# CodexCopy

Codex 桌面应用前端的**干净复刻**（clean-room reimplementation）：根据对
`Codex (Beta) 26.415.40636` 的逆向分析（rea 静态重构，见分析报告），用
Vite + React + 手写 CSS 从零实现与其一致的界面与交互。

演示视频：[CodexCopy-demo.mp4](./CodexCopy-demo.mp4)（也存于谷歌云盘 `02项目/Reference/CodexCopy/`）

## 复刻依据（逆向参数）

- 布局：macOS 窗口 chrome（红绿灯）+ 左侧 280px 侧栏（New thread / 搜索 / 按时间分组的会话列表 / 底部用户栏）+ 主区 + 底部 composer
- 深色主题 token：**逆向自 `codex-dark-xFLf7JPn.js` 官方主题（24 色逐字提取）**：`#111111` 主背景、`#131313` 侧栏、`#fcfcfc`/`#8f8f8f` 文字、`#0169cc` 强调色（按钮/链接）、`#00a240` 成功、`#e02e2a` 错误
- 交互文案：`New thread`、`Filter threads ⌘K`、`Ask Codex to do something…` 等均取自逆向出的 i18n

## 功能面（14 个组件）

| 区域 | 组件 | 说明 |
|---|---|---|
| 桌面壳 | `App.jsx` | 视图路由（会话/设置/自动化）+ Cmd+K 全局快捷键 + 窗口 chrome |
| 侧栏 | `Sidebar.jsx` | New thread / 会话搜索过滤 / 时间分组列表 / 底部用户+设置+自动化入口 |
| 会话 | `thread/ThreadView.jsx` | 消息列表容器 |
| | `thread/Message.jsx` | UserMessage / AgentMessage / StreamingMessage |
| | `thread/ThinkingBlock.jsx` | 可折叠 Thought 块 |
| | `thread/ToolCard.jsx` | 工具调用卡片（bash/read/edit/write/diff，done 状态） |
| | `thread/CodeBlock.jsx` | 代码块（语言标签 + 复制） |
| | `thread/DiffBlock.jsx` | Diff 审查卡片（Unified/Split 切换 + Accept/Reject） |
| 输入 | `composer/Composer.jsx` | 自适应高度输入框 + 模型选择器 + 发送 |
| 设置 | `settings/SettingsView.jsx` | 6 页：General / Appearance / Models / Git / MCP Servers / Extensions |
| 命令面板 | `palette/CommandPalette.jsx` | Cmd+K，键盘导航 |
| 自动化 | `schedules/SchedulesView.jsx` | 定时任务列表（暂停/恢复/删除） |
| 基础 | `icons.jsx` | 24 个手写 SVG 图标 |

## 运行

```bash
cd CodexCopy
npm install
npm run dev      # http://127.0.0.1:8931/
```

## 说明

- 数据为本地 mock（`src/data/mock.js`），发送消息会触发模拟的 agent 回复（思考 → 工具调用 → 文本/Diff 回复）
- 后端执行能力（Rust `codex` 二进制）不在复刻范围内
- `record.cjs`：Playwright 交互录制脚本（截图序列 + ffmpeg 合成）
