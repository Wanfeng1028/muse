# Codex Windows 前端说明

## 结论
Codex Windows 桌面应用**无官方直接下载**（微软商店独占分发），其前端与 mac 版为**同一份 `app.asar` JS 包**。

## 核验过程
1. `chatgpt.com/download` 主下载按钮为 JS 平台检测，仅暴露 Linux（.deb/.rpm）选项；
2. 页脚 Mac/Windows 链接指向旧版 ChatGPT Classic；
3. Windows 官方渠道仅微软商店（get.microsoft.com/installer/download/9PLM9XGG6VKS，经 strings 确认为 .NET 商店引导器，内含 `CodexProductId`）；
4. 官方 CDN appcast（codex-app-beta / codex-app-prod）仅含 macOS 构建。

## 为什么 mac 版分析适用于 Windows
Electron 应用跨平台前端一致：同一 `app.asar` 包同时分发 mac/Windows。
旁证：`app.asar.unpacked` 内同时含 darwin 与 win32 的 node-pty/better-sqlite3 预编译件。

mac 版前端逆向源码见 `Codex-mac前端-逆向源码.zip`，分析结论见《分析报告-Codex-OneviumAI.md》§二、§三。
