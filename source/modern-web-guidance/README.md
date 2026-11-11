# Modern Web Guidance

来源：`https://github.com/GoogleChrome/modern-web-guidance-src`

性质：第三方开源项目 skill 归档（只存档，不改动）。

## 项目简介

Modern Web Guidance 是 Chrome、Edge、Firefox、MDN 团队联合维护的一套 agent skill：把现代 Web 平台的专家知识、最佳实践与浏览器兼容数据直接嵌进编码 agent 的上下文，引导 agent 远离老旧写法、改用原生高性能的现代 Web 能力。覆盖 250 个现代 Web 特性：CSS 布局（容器查询、subgrid、oklch）、用户体验（View Transitions、滚动驱动动画）、性能（INP 诊断、scheduler.yield）、表单与原生 UI（Popover API、Dialog、锚点定位）、无障碍、内置 AI（本地翻译/摘要/语言检测）等。

- 语言：TypeScript + Markdown 指南，命令行工具
- 许可证：Apache-2.0
- 维护方：Google Chrome 团队（联合 Microsoft Edge、Mozilla Firefox、MDN）
- 文档：https://developer.chrome.com/docs/modern-web-guidance
- npm：https://www.npmjs.com/package/modern-web-guidance

## 归档信息

- 归档日期：2026-11-11
- 上游 commit：`596acbc75a330508591b07cd9e198b219341f619`（main，浅克隆）
- 上游版本：1.0.0（npm，skill-version `2026_11_09-5bcc021b`）
- 包：`modern-web-guidance-1.0.0.tgz`（npm 官方发布包，8,794,985 字节，SHA-256 `bd7aa623ad10710a9ad6678fdbcc0b890c903c54fd6abfc126ff42de01f0e577`，含 skill 定义、250 篇指南与检索索引）
- 完整源码包：见 Google 云盘 `02项目/Github 源码/modern-web-guidance-src/modern-web-guidance-src-20261111-596acbc7.tar.gz`（上游仓库工作树，`.git` 已去除，75,939,972 字节，SHA-256 `d64e74c2c388c1103d6b74221c20b1d352bcbcd73dc1c8358747568d353d4969`；仓库含 78M 的 eval harness，未进 git，只存云盘）
- 解包：`tar -xzf modern-web-guidance-1.0.0.tgz`

## 安装与使用

```sh
npx modern-web-guidance@latest install          # 交互向导安装 skill
npx modern-web-guidance@latest search "animate a dialog modal backdrop"   # 按任务搜指南
npx modern-web-guidance@latest retrieve "animate-to-from-top-layer"       # 按 ID 取指南全文
npx modern-web-guidance@latest legacy-scan .     # 扫代码库里的老旧写法
```

本地 skill 副本：`~/workspace/custom-skills/modern-web-guidance/`（与本包同源）。

## 使用规矩（用户亲定，2026-11-11）

写项目之前先查 Modern Web Guidance：动手写前端/网页 UI、CSS 布局动画、客户端 JS 之前，先 `search` 取相关指南（2–5 词动作导向查询），再 `retrieve` 取全文；已有代码库先跑 `legacy-scan`。后端、基建、纯文案任务不触发。
