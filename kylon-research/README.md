# Kylon 调研笔记（2026-10-21）

> 结论先行：**Kylon 是闭源商业 SaaS，没有公开源码仓库**，无法 clone 存档。本笔记基于其官网、文档站与官方博客的公开资料整理其产品形态，供 BotsTalk 借鉴（借功能与信息架构，不抄 UI）。

## 一、代码可得性核实（证据）

| 渠道 | 核查结果 |
|---|---|
| 官方博客 kylon.io/blog/kylon-vs-buzz（2026-07-22） | 官方自述："Kylon will open-source skills and templates; **infrastructure remains platform-managed**"——即仅计划开源 skills/模板，基础设施闭源托管。 |
| GitHub 组织检索 | `kylon-ai`、`kylon-io`、`usekylon`、`getkylon`、`kylonhq`、`kylon-app` 均为 404 不存在；`github.com/kylon` 是无关个人账号（2013 年注册）。 |
| GitHub 仓库搜索 `kylon` / `kylon skills` | 51 条结果全为无关个人项目（Beat Saber 歌单、个人主页等）；`kylon skills` 0 结果。 |
| kylon.io 首页 HTML | 无指向自家 GitHub 仓库的链接（仅页面模板署名链接）。 |
| docs.kylon.io | 页面内无任何 github.com 链接。 |

结论：截至 2026-10-21，Kylon 无任何官方公开代码（含其承诺的 skills/templates 亦未见发布）。后续若其开源 skills，可再行收录。

## 二、Kylon 是什么

定位："Your first company harness"——把团队的人、AI agent、公司知识与工具放进同一个工作区（workspace），让人和 agent 在共享**房间（room）**里一起干活，卖点是共享上下文而非各自单聊。运行形态：Web / macOS / iOS / Android，托管 SaaS，注册即用。

## 三、产品形态要点（据官网 aios / bring-your-own-agent / alternatives 等公开页整理）

1. **房间制**：房间同时容纳人和多个 agent；agent 是有名有"岗位"的成员，不是需要单独打开的应用。请求、回复、审批都留在同一条线程里，下一个人可接续上下文。
2. **@ 提及派活**：像 @ 同事一样 @ agent，用自然语言说需求，无需学提示词语法。
3. **agent 之间公开交接**：一个 agent 读告警、把活交给另一个 agent 写修复，交接过程在房间里公开可见，可追溯。
4. **人工审批门（核心特征）**："Keep the last call with a person"——凡是要改变房间之外世界的操作（发消息、提交、对外动作），先停在审批：人看到草稿/diff/待发消息，由人放行后才执行。
5. **自带 agent 入驻（BYO agent）**：Claude Code、Codex 等跑在用户自己电脑上的 agent 可作为成员加入工作区：在工作区里建 agent（名字+专长+运行方式），把 Kylon 给的"连接提示词"粘到本地 agent 工具里完成绑定（凭据链接 30 分钟过期）；本地装后台服务，电脑关机/休眠即离线、恢复后自动重连；一台电脑可跑多个 agent，但一份电脑连接同一时间只属于一个工作区。agent 创建后默认私有、不属于任何房间，由管理员添加进房间并设定可达范围；agent 本身有 Admin/Member 角色，访问授权按 agent 粒度授予、可撤销，用的是它被授予的工作区连接而非共享密钥。
6. **记忆与上下文**：每个 agent 有自己的记忆与 skills；房间保留线程历史、文件与工作记录，下一次请求从团队已有结论出发。
7. **连接团队既有工具**：Gmail、Slack、HubSpot、Google Drive、GitHub 等账号可接入，按 agent 的岗位授予所需的那几个。
8. **工作流（workflows）**：可编排定时/触发式流程调用 agent 干活。官网案例：营销团队接入 GitHub 仓库后，每日工作流扫描 commits/PR/releases，过滤内部改动，由 agent 生成面向市场的更新摘要与视觉素材、排期社媒帖，每天早晨发到营销频道。
9. **房间内应用与记录**：agent 能在聊天里直接搭出小应用（如 Invoice Tracker：发票记录表，6 条记录、发布为独立 app），应用可关联到房间文件夹或单个聊天，记录由 agent 持续维护。

## 四、与 BotsTalk 的对照

BotsTalk（个人 AI 团队办公室：L0 用户 / L1 聊天室聚合层 / adapter 翻译层 / L2 agents 执行层）与 Kylon 的差异主要是**规模定位**（个人 vs 公司团队），产品骨架高度相似：房间、agent 成员、@ 派活、公开交接、房间上下文，BotsTalk 均已具备（协议 v1.3、网关、工作坊/娱乐厅、DeepSeek brain/body adapter、artifacts、游戏厅）。

对照后 BotsTalk 尚缺、且与 Kylon 特征直接对应的能力：

| Kylon 特征 | BotsTalk 现状 | 本次动作 |
|---|---|---|
| 人工审批门（对外动作先经人放行） | 无：task intent 派发后 adapter（尤其 body 模式，dsh 本体可真实执行）直接执行 | ✅ 本次集成：协议新增 approval_request/approval_decision 帧 + 网关审批门（见 botstalk 变更） |
| BYO agent（本地 agent 以成员身份入驻、连接提示词绑定、按 agent 授权/撤销） | adapter 均为服务端进程，无"用户电脑上的 agent 入驻"流程 | 未做：涉及本地后台服务与凭据协议，属下一阶段立项 |
| 定时/触发工作流调用 agent | 无工作流引擎（现有为即时派活） | 未做：与审批门组合后价值更大，下一阶段 |
| 房间内 agent 搭建应用/记录 | 有 artifacts（整份重传 v1），无结构化记录应用 | 未做 |

## 五、来源

- https://kylon.io/ （首页：company harness 定位、BYO agent、工具连接）
- https://kylon.io/aios （为什么把 agent 放进房间：房间/@ 提及/公开交接/人工审批四点）
- https://kylon.io/bring-your-own-agent （BYO agent 连接流程、本地运行语义、访问控制）
- https://kylon.io/alternatives/grok-bot （与 Grok Bot 对照表：成员模型、记忆、房间共享语义）
- https://kylon.io/blog/kylon-vs-buzz （开源状态官方表态出处；竞品 Buzz 为 Apache-2.0 全开源）
- https://kylon.io/use-cases/code-to-content （GitHub 接入 + 每日工作流案例）
- https://docs.kylon.io/agents/overview 等文档页（agent 创建与访问）
