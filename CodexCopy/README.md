# CodexCopy

Codex 桌面应用前端的**干净复刻**（clean-room reimplementation）：根据对
`Codex (Beta) 26.415.40636` 的逆向分析（rea 静态重构，见分析报告），用
Vite + React + 手写 CSS 从零实现与其一致的界面与交互。

演示视频：[CodexCopy-demo.mp4](./CodexCopy-demo.mp4)（也存于谷歌云盘 `02项目/Reference/CodexCopy/`）

## 复刻依据（逆向参数）

- 布局：左侧 280px 侧栏（New thread / 搜索 / 按时间分组的会话列表 / 底部用户栏）+ 主会话区 + 底部 composer
- 深色主题 token：`--bg-main #212121`、`--bg-sidebar #171717`，文字三级灰阶，边框 `rgba(255,255,255,0.1)` 体系
- 组件：用户气泡（右对齐圆角）、agent 消息（Codex logo 头像）、可折叠 Thought 块、tool call 卡片（read/edit/bash，done 状态）、代码块、模型选择器、发送按钮
- 交互文案：`New thread`、`Filter threads ⌘K`、`Ask Codex to do something…` 等均取自逆向出的 i18n

## 运行

```bash
cd CodexCopy
npm install
npm run dev      # http://127.0.0.1:8931/
```

## 说明

- 数据为本地 mock（`src/data/mock.js`），发送消息会触发模拟的 agent 回复（思考 → 工具调用 → 回复）
- 后端执行能力（Rust `codex` 二进制）不在复刻范围内
- `record.cjs`：Playwright 交互录制脚本（截图序列 + ffmpeg 合成）
