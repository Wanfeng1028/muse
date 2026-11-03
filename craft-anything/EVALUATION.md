# EVALUATION：storytold/craft-anything（归档员评估，非上游文件）

## 它是什么

Craft Anything：一个纯 Rust 的 clean-room 复现引擎——指着任何网站、App
或游戏，先用真实检查工具研究原件，再由 coding agent 从头建一个自己的版本，
最后把成品与原件逐项比对、 refine 到接近为止。口号：understand how any
software works, and craft your own。

工作流四步：Study（研究原件）→ Build（agent 建新项目）→ Check（比对原件，
列出不匹配项）→ Ready（打开/试玩/继续改）。

- 两种模式：Clean room（默认，只用访客可见的证据：截图、可见文本、实测布局、
  颜色字体间距，不读原件代码与文件）与 Deep（全量逆向：内置反汇编/反编译，
  可接 Ghidra，仅供私人使用）。
-  builder：用户自己的 Claude Code（首选，未改动过的 claude 程序与用户自己的
  登录），或 ACP 协议 agent（Gemini CLI、Qwen Code、opencode、goose、Hermes、
  Maki；仅 Maki 实测跑通过）。
- Check（网站）：成品在 loopback 上起服务，与原件在 1440/768/390 三宽下逐页
  比对，相似度 = 布局分与感知细节分（SSIM）的均值；原件自身会变的部分先拍
  三次照片排除；最多 6 轮 refine，或达到 90% 相似度为止。
- 314 个工具（引擎层约 299 + AI/搭建层），每个工具同时是 CLI 子命令与 MCP 工具，
  agent 不用 App 也能驱动同一引擎。（口径注：tools.md 称引擎 299 个，README
  称 298 个，上游文档自身略有出入；总数 314 两处一致。）
- 三个应用：桌面 App（egui）、CLI（craft-anything-cli）、Web（Trunk/WASM）。
  13 个 crate：ai、analysis、disasm、engine、engines、evidence、formats、js、
  mcp、platform、setup、testkit、ui-egui。
- 多语言 README（英/日/简中/韩），中文 UI 已有简繁 catalog。

## 关键事实（2026-11-03 核查）

- Stars：4145；Forks：682；Open issues：134
- License：MIT OR Apache-2.0（双许可，两文件全文保留）
- 版本：0.3.0，状态 early alpha；Rust 1.97+
- 创建：2026-10-31；最后推送：2026-11-03（归档当天仍在活跃推送）
- 基线审计（上游 STATUS.md，2026-10-23）：923 测试通过，clippy/fmt/密钥扫描干净
- 归档：上游原文 621 个文件、15M，main 分支 2026-11-03 快照（另加归档员文档 2 份）

## 集成结论：只归档，不落地代码

理由（按分量排序）：

1. 栈不匹配：它是纯 Rust 整机引擎，不是库。剧坊是 Java/Spring Boot，
   BotsTalk 是 TypeScript，没有可 import 的 1-2 个模块；要接只能整机跑，
   不属于“落 1-2 项”的范畴，硬塞违反不硬塞原则。
2. 太新太动：0.3.0 early alpha，创建仅 3 天，归档当天还在推送，134 个 open
   issue；现在基于它构建等于追一个每天变的目标。
3. 模型路线走不通：它的 builder 要求用户自己的 Claude Code 登录（或 ACP
   agent），不走本站 BotsRouter 渠道；流水线模型 lane 驱动不了它。
4. 是重叠不是缺口：用户已有等价能力——measured_visual_replication（逐元素
   实测复现）、Playwright 单屏截图验收 harness、Observe 证据纪律（源自
   ai-website-cloner-template 的评估）。它的 Check 步骤（多宽比对 + 不匹配
   清单 + refine 循环）是同一思想的引擎化，不是缺失的能力。

## 可借鉴的思想（仅作参考，不抄代码）

1. Check 验收 rubric：相似度取布局与感知细节均值、多页平均；先拍三次排除
   原件自变部分；失败条件清单（横向滚动、新控制台报错、缺 landmark、
   菜单打不开）——可用于丰富视觉复现 skill 的验收标准。
2. 证据记录格式：每条证据带置信度/覆盖度/局限性 + 未知项台账
   （core_unknown_add）——与 Observe 证据纪律同源，可丰富复现 skill 的证据格式。
3. Clean room / Deep 的合规分层：默认只用访客可见证据——与本站“参考不等于
   照抄”的边界一致，可作为复现工作的合规表述参考。

## 何时重新评估

- 上游出稳定版（1.0 或 API 稳定）；
- 拆出可独立使用的库 crate（不依赖整机引擎与 Claude Code 登录）；
- 用户明确下令把它当独立工具跑某次具体复现任务（不集成，只使用）。

## 归档位置说明

本仓库惯例是一文件夹一项目；skill/prompt 合集类才放 prompt/ 下。
craft-anything 是单个软件项目（不是 skill/prompt 合集），故放在仓库根目录
`muse-repo/craft-anything/`，与 mini-os、docseek 等项目并列，不放 prompt/。
