# 打包清单（kylon-cli 静态分析 + BotsTalk BYO 桥接集成）

打包日期：2026-10-21

## 分析对象清单

| 项 | 值 |
|---|---|
| 包名 | kylon-cli |
| 版本 | 0.7.9（npm registry latest，2026-10-21 核对） |
| registry 地址 | https://registry.npmjs.org/kylon-cli/-/kylon-cli-0.7.9.tgz |
| npm 登记 shasum（SHA-1） | 9d6e54fd4292062885cff8a37e04635bd462f877 |
| tgz SHA-256 | 4add09107608af17a4c110ada6137d58c28e38ab27e71ffd74856fc65c78da88 |
| 发布者 | Kylon / Pure Reason（闭源 SaaS kylon.io 的官方 CLI） |

## 本包内容

- `kylon-cli-npm-analysis-2026-10-21.md`：静态分析报告（结构与结论、命令面、
  本地 agent 桥接机制、配置存放、服务端通信功能级形态、文件清单与哈希）。
  同步存于 GitHub 仓库 Wanfeng1028/muse 的 `kylon-research/` 目录。
- `kylon-cli-0.7.9.tgz`：npm registry 公开发布的原始包（存档原件，未改动）。
- `MANIFEST.md`：本文件。

## 本次集成提交说明

- 仓库：Wanfeng1028/muse，提交 `f64a3de`（已 push 至 origin/main，
  `git branch -r --contains f64a3de` 核实含 origin/main）。
- 内容：新增 BotsTalk 适配器包 `botstalk/adapters/byo-bridge`
  （`@botstalk/adapter-byo-bridge`）——借鉴 Kylon 的一次性入驻链接与
  ACP 本机 agent 驱动概念、按 BotsTalk 既有 adapter 模式独立实现；
  决策记录写入 `botstalk/docs/DECISIONS.md`（2026-10-21 条）。
- 验收：新包测试 28/28 全绿；BotsTalk 全量回归不回退（protocol 159、
  gateway 681、adapter-base 85、adapter-deepseek 84、web 228 全绿，
  root npm test 退出码 0）。
- 红线执行：未绕过任何登录/付费/加密；未提取或记录任何凭据值
  （密钥模式仅计数）；未逐字复制 kylon-cli 代码；服务端接口仅功能级描述。
