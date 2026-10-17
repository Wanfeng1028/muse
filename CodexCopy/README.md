# CodexCopy

Codex 桌面应用前端的逆向复现。源码来自对 `Codex (Beta) 26.415.40636`（macOS arm64）
安装包的逆向分析（rea 静态重构），`web/` 下是字节一致的官方前端构建产物。

演示视频：[CodexCopy-demo.mp4](./CodexCopy-demo.mp4)（也存于谷歌云盘 `02项目/Reference/CodexCopy/`）

## 这是什么

- `web/`：Codex 官方 `app.asar` 中解包出的前端（Vite 构建：`index.html` + `assets/` 800+ JS chunk + `apps/` 图标）
- `shim.js`：Electron API 垫片。原应用通过 preload 注入 `window.electronBridge` 与主进程通信；
  垫片在浏览器环境提供最小实现（所有调用点均为可选链，UI 可正常启动）
- `server.mjs`：静态文件服务器（Node，无依赖）

## 运行

```bash
cd CodexCopy
node server.mjs        # http://127.0.0.1:8931/
```

用浏览器打开即可看到 Codex 前端启动（logo 屏）。

## 复现边界（诚实说明）

- 前端在浏览器中**零 JS 错误**启动，React 已挂载——这是真实的官方 UI 代码在运行
- 停在初始化屏：应用等待 Electron 主进程的 `persisted-atom-sync` 初始状态与登录态
- 完整工作区 UI 需要：Electron 主进程 + ChatGPT 登录 + `codex` Rust 后端二进制
  （macOS arm64 构建，无法在此 Linux 环境运行）——故本次复现止于前端启动验证
- `record.cjs`：录制演示视频的 Playwright 脚本（截图序列 + ffmpeg 合成，
  绕过 Chromium 152 本地网络访问检查：setContent + route 拦截 + 绝对 URL 改写）

## 逆向方法

见 `../analysis-targets/分析报告-Codex-OneviumAI.md`（报告已存谷歌云盘）。
