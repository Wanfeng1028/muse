# kylon-cli（npm 公开包）静态分析报告

- 分析日期：2026-10-21
- 分析对象：npm 公开分发包 `kylon-cli@0.7.9`（Kylon / Pure Reason 的本地网关 CLI）
- 工具：rea v6.5.0（`analyze-javascript-application`）+ 包内公开文档与清单核对 + 字符串存在性指标
- 性质：功能级静态分析。本报告只写结构与结论，不收录该包的代码；服务端接口只做
  功能级描述，不做可克隆其服务的接口规格。

## 1. 分析对象与完整性

| 项 | 值 |
|---|---|
| 包名/版本 | kylon-cli 0.7.9（npm registry 当前 latest） |
| registry 地址 | https://registry.npmjs.org/kylon-cli/-/kylon-cli-0.7.9.tgz |
| npm 登记 shasum（SHA-1） | 9d6e54fd4292062885cff8a37e04635bd462f877（与本地 tgz 实测一致） |
| tgz SHA-256 | 4add09107608af17a4c110ada6137d58c28e38ab27e71ffd74856fc65c78da88 |
| 包内清单 | dist/kylon-bundle.mjs（5.6MB）、dist/kylon-core-bundle.mjs（2.4MB）、dist/kylon-bundle.manifest.json、package.json、README.md |
| bundle 指纹 | manifest 记 fingerprint 8d3713f0…bb46，与 kylon-bundle.mjs 的 SHA-256 实测一致；source_commit 413fb265… |
| 运行时要求 | ESM；Node >= 22.15.0；bin 名 `kylon` |

发布形态：单文件 bundle 分发（另附一份 core bundle），README 明确说明发布包经
minify + obfuscate（十六进制标识符、字符串编码），这也是下文 rea 保留失败的直接原因。

## 2. rea 分析结果（如实记录）

对解包目录执行三轮 `analyze-javascript-application`（默认上限、仅 core bundle、
节点上限拉满 1,000,000 并指定单文件），三轮均以工具错误结束：两个 bundle 都报
"did not retain required structure records"（工具完成了全量读取，但按其保留策略
未保留任何文件的结构记录），没有产出可用的语义图。

结论：rea 6.5.0 的静态重构对这种「minify + 字符串编码混淆」的发布 bundle 无法
保留结构。因此本报告的功能结论来自三条相互印证的证据线：

1. 包内随附的公开 README（73KB，产品级文档，与包一同公开发布）；
2. package.json / bundle manifest 等清单文件；
3. bundle 内字符串「存在性」指标（存在即证据，不存在不作反证——字符串池是编码的）。

未做任何动态执行：没有真实登录、没有连接其服务端、没有兑换任何链接。

## 3. 包结构与入口

- 入口：`kylon` -> `dist/kylon-bundle.mjs`；另有 `kylon-core-bundle.mjs` 承载
  核心逻辑，manifest 以指纹 + 源码提交号绑定发布件，安装脚本据此做校验与修复。
- 代码归属：package.json 的 repository 指向私有 monorepo（fre-so/p2 的
  packages/cli），与上一轮核查结论一致——产品源码不公开，本包是其唯一公开
  分发件。
- 安装：官方推荐托管安装脚本（装到 `~/.kylon`，无 Node 的机器会装一份私有
  校验过的运行时），npm 包是另一条等价分发渠道。

## 4. 命令面（据包内公开文档归纳）

核心命令（文档 Commands 表）：

| 命令 | 作用（功能级） |
|---|---|
| `kylon agent link --url <一次性链接> [-- <启动命令>]` | 推荐入驻路径：兑换链接、连接一个 agent 并启动其本地运行时；ACP 启动命令在同一步保存 |
| `kylon disconnect` | 遗忘本机运行时注册（纯本地，服务端 agent 配置不变） |
| `kylon gateway run` | 按已保存的连接运行本地运行时服务（服务入口） |
| `kylon gateway resume` | 长期无活动休眠后，以所有者保存的登录恢复本机运行时 |
| `kylon keep-awake [always\|while-busy\|off]` | macOS/Windows 防休眠策略 |

文档其余部分出现的其他命令族：`login` / `auth login|logout|status`（人类
工作区登录）、`connect --setup-token ... --intent computer`（应用内一键接入
本机）、`onboard`（从本机既有 agent 上下文新建工作区）、`gateway status /
service / supervise / auto-update / secret`（守护进程管理）、`workspace ...`
（以人类身份操作工作区的命令族，含 connection / secret / app 等）、
`provider update`（更新 provider CLI）、`diagnose`（本地诊断与证据收集）、
`upgrade`（CLI 自升级）。

## 5. 本地 agent 桥接机制（功能级）

这是本包的核心职责：「connecting local agent providers to a P2 workspace」。

### 5.1 角色与约束

- CLI 在用户本机充当**网关守护进程 + 入驻客户端**：对内拉起/驱动本机
  agent 进程，对外维持一条到工作区的已认证会话。
- 一台机器的本地运行时同一时刻只注册到**一个**服务端 + 一个工作区；
  切换前必须先 `disconnect`（只清本地注册，不动服务端配置）。

### 5.2 四条入驻路径

1. **一次性链接（agent link）**：Web UI 在某个 external agent 的 Profile 页
   生成 `npx kylon-cli agent link --url '<link>'` 命令；链接内嵌短期凭据，
   30 分钟过期、只能兑换一次，同一安装中断后重跑同一命令是幂等的。CLI
   不开浏览器、不复用人类凭据；它校验所选 provider CLI 已安装且已认证，
   向用户展示将连接的 agent 与工作区供确认，然后连接并启动本地运行时；
   对 ACP agent，同一操作把启动命令一并保存。
2. **setup token（connect --intent computer）**：应用内生成单次、30 分钟、
   绑定单个工作区的 setup token；CLI 以 `intent: "computer"` 发起设备授权，
   取得**这台电脑自己的密钥**并写注册、装并启动网关服务。此路径不写人类
   凭据（`workspace-auth.json` 完全不碰），所以接入后 `kylon workspace`
   命令仍需单独 `login`。入驻过程有本地日志（enrollment journal，只记
   能力与密钥指纹、从不记密钥本身，中断后可续跑或先撤销）。
3. **人类登录（login）**：浏览器批准页选择工作区，供 `workspace` 命令族与
   部分恢复路径使用，与 agent 运行时凭据分离。
4. **onboard**：终端优先的新建工作区流程——发现本机 Claude Code / Codex
   的项目与会话元数据（项目上限 8 个），经浏览器确认后把所选项目的
   persona、skills、记忆导入新工作区，两个 agent 加入所选房间。

### 5.3 provider 执行模型

- **ACP 系**（Claude Code、Codex、Grok Build、Hermes、Gemini CLI）：经
  ACP（Agent Client Protocol，公开标准）以 stdio 驱动。文档描述的 ACP
  使用面包括：initialize 握手（个别 provider 的认证状态在首个真实回合
  成功前只记为「未验证」）、会话加载、流式文本/工具活动、取消。Grok 走
  用户显式安装的 `grok agent stdio`，Hermes 走 `hermes-acp`/`hermes acp`，
  Gemini 走 `gemini --acp` 且启动命令不可被配置覆盖。
  bundle 字符串存在性与此印证：`session/new`、`session/load`、`initialize`、
  `protocolVersion`、`clientCapabilities`、`mcpServers`、`tool_call` 均可检出。
- **一次性消息系**（OpenClaw）：用其 CLI 单次调用传 prompt（超长改走
  `--message-file` 文件投递），无 stdio 会话通道。
- **generic provider**：PATH 上任意名为 `kylon-provider` 的可执行文件，
  以换行分隔 JSON 事件通信；投递参数为 `--prompt/--workdir/
  --system-prompt/--resume`；超出平台命令行长度预算时改写临时文件并传
  `--prompt-file` 等，前提是该 wrapper 在 `--version` 输出里声明支持
  文件投递能力，否则超长任务以具名错误失败。这是一种「provider 适配
  契约」式的扩展点设计。
- Codex 的可执行文件发现有专门逻辑（优先桌面版自带 CLI 并跟随其更新，
  其次 PATH 上的独立 CLI，显式选择后不再改动）。

### 5.4 会话与状态模型（文档 State Model 节）

四层状态：InstalledAgentProfile（非秘密的 agent 身份、provider、工作目录
独占归属）、GatewaySession（单个 agent 到服务端的已认证连接）、
LogicalSessionState（按 (网关会话, agent) 绑定的当前工作目录与 provider）、
ProviderRuntimeEntry（按 (网关会话, 频道, agent, 作用域, provider, 工作目录)
键控的 provider 恢复缓存，可丢弃）。切换工作目录只更新逻辑会话，不新建
会话；切回旧目录会恢复旧的 provider 运行时。

## 6. 配置与状态存放（功能级）

- 安装根：`~/.kylon`（含可选的私有 Node 运行时子目录）。
- 配置目录：`~/.kylon` 或 `$XDG_CONFIG_HOME/kylon`。其中 `install.json`
  保存随机 `installId`（`cli_…` 形态），安装身份而非设备/个人身份；
  文件损坏时命令会停下并给出把记录改名留置、再恢复的指引，而不是静默
  覆盖（因为已保存的电脑连接引用着这个 id）。
- 每 agent 状态：`~/.kylon/agents/<agent-id>/`（或 XDG 等价路径）；
  人类工作区认证在配置目录顶层（`workspace-auth.json`）。
- 日志：守护进程日志在配置目录（gateway.log）；macOS 的 launchd 启动
  日志独立放在 `~/Library/Logs/KylonGateway/`（0700 目录、0600 文件，
  10MiB 轮转）；诊断收集时对日志做脱敏。
- bundle 字符串检出 `launchd`、`systemd`、`auto-update`、`setup-token`、
  `.kylon`、`XDG_CONFIG_HOME`、`install.json`，与上述文档描述一致。

## 7. 与服务端通信的功能级形态

（只记形态与事件类别，不记可克隆其服务的接口清单。）

- **网关长连接**：每个 agent 维持一条已认证的网关会话连接（bundle 检出
  WebSocket 与 reconnect 相关字符串，未检出 socket.io）。文档的遥测事件
  清单从侧面给出连接上的事件类别：连接建立/关闭、连接失败与重连调度、
  任务（assignment）的接收与接受、provider 执行、取消、结果投递、
  outbox 重放——即「服务端下发任务、本机执行、结果回传，断线后有
  outbox 补发」的存储转发模型。另有休眠语义：14 天无真实本地活动后
  进入保留的休眠意图，`gateway resume` 需重新验证所有者授权才恢复。
- **遥测通道**：独立的 HTTPS 批量上报（按机器身份/用户身份/匿名三档走
  不同端点与字段白名单；本地队列上限 200 条、每 5 秒一批最多 20 条、
  失败指数退避、401/403/404 后本进程内停用；可用环境变量整体关闭）。
  上报字段有键数与长度上限，命令路径从不上传路径、prompt、argv 或任意
  错误原文。
- **环境变量面**（只记名字）：检出 `KYLON_API_KEY`、`KYLON_API_TOKEN`、
  `KYLON_GIT_TOKEN`、`KYLON_AGENT_ID`、`KYLON_GATEWAY_SESSION_ID`、
  `KYLON_ASSIGNMENT_SESSION_ID`、`KYLON_CHANNEL_ID` 等，说明守护进程会
  向 provider 子进程注入作用域化的上下文。变量值未读取、未记录。

## 8. 安全与凭据观察（红线内）

- 对 bundle 做常见密钥前缀的**计数型**扫描：`sk-ant-`、`sk-proj-`、
  私钥头（BEGIN RSA/OPENSSH）、`xoxb-` 均为 0；`ghp_` 计数 1、`AKIA`
  计数 2——在字符串整体编码的混淆包里，这类短子串命中与编码数据假阳性
  一致；按红线要求未提取、未记录任何上下文或值。可读字符串中未发现
  明文的第三方 API 密钥。
- 设计层（据公开文档）：一次性凭据 30 分钟单次有效；入驻日志不保存
  密钥本体；配置与日志文件权限 0600/0700；诊断与遥测在收集端脱敏、
  服务端有速率与字段限制。这些是可借鉴的工程做法，与第 10 节的独立
  实现相互独立。

## 9. 未及事项与限制

- rea 未能保留混淆 bundle 的结构图，因此**没有**调用图、控制流级证据；
  功能结论以包内公开文档为主证据，字符串指标为辅证（编码字符串池下
  「检出」是证据、「未检出」不是反证，如 `session/prompt`、
  `session/update`、`agent_message_chunk` 在明文扫描中未检出，但其功能
  由文档明确描述）。
- 未做动态验证（不登录、不连服务端），守护进程的实际线协议细节
  （帧格式、心跳参数等）不在本报告范围内。
- 服务端私有接口只按文档与事件清单做了功能级归类，未枚举其路径全集，
  不构成可克隆其服务的规格。

## 10. 对 BotsTalk 的启示与本次集成（独立实现）

Kylon 与 BotsTalk 的形态差异先说清：Kylon 的 CLI 是「中心化 SaaS 的本机
网关」，BotsTalk 是自建网关 + adapter 体系。两者相通的是同一个问题——
**怎么让跑在用户本机的 agent 以成员身份进房间干活**。Kylon 的答案里可
迁移的概念有四个：一次性入驻链接、每 agent 独立的本地 profile、经 ACP
驱动本机 agent、任务的流式回传与取消。本次按这些概念在 BotsTalk 里
**独立实现**了 BYO 入驻桥接（新包 `@botstalk/adapter-byo-bridge`），
没有复制 kylon-cli 的任何代码，线协议用 BotsTalk 自己的 v1.3，
agent 驱动用公开标准 ACP 的客户端子集。

概念对照：

| Kylon 概念 | BotsTalk 本次实现 |
|---|---|
| agent link 一次性链接（30 分钟、单次、幂等重跑） | `src/link.ts`：BotsTalk 自有链接格式（gateway/room/agent/token/exp），兑换只落盘令牌 sha256 摘要；同链接同安装幂等返回 already，异链接报 link_already_used，过期报 link_expired |
| InstalledAgentProfile（每 agent 独立本地档案） | `src/profile.ts`：`~/.botstalk/byo/<agentId>/profile.json`（BOTSTALK_BYO_DIR / XDG 可覆盖，0600），存网关、房间与 provider 启动命令 |
| 经 ACP 拉起本机 agent（initialize/session/prompt/取消、流式更新） | `src/acp.ts`：NDJSON JSON-RPC 2.0 的 ACP 客户端子集；`src/bridge.ts` 把 session/update 的 agent_message_chunk 转成 BotsTalk stream 帧，stopReason 映射 task 状态 |
| 网关守护进程常驻 + 任务下发/结果回传 | 不新建守护层：桥接复用 adapter-base 的 AdapterClient（hello/capability/心跳/重连/gseq 补发），任务台账与人工审批门都是网关既有机制，BYO agent 与其他 adapter 一视同仁 |

CLI 形态：`byo-bridge link --url <link> -- <启动命令...>` /
`byo-bridge run [--agent <id>]` / `byo-bridge status`；无 profile 时也支持
纯环境变量运行（BYO_COMMAND 等），与 echo/deepseek adapter 的约定一致。

v1 边界（有意不做）：不响应 agent 侧反向请求（fs/*、
session/request_permission 等，统一回 -32601）；单桥接实例复用单个 ACP
会话，不按发送者分会话；不做 Kylon 式的服务端入驻协议（BotsTalk 的
链接兑换目前是纯本地记账，服务端签发/吊销链接是下一阶段）。

测试与回归（2026-10-21 实跑）：新包 28 例全绿（link 12、profile 8、
acp 5、bridge 3，含假 ACP agent 与假网关的端到端任务流）；BotsTalk
全量回归不回退——protocol 159、gateway 681、adapter-base 85、
adapter-deepseek 84、web 228 全绿，root npm test 退出码 0。决策记录见
botstalk/docs/DECISIONS.md 2026-10-21「BYO agent 入驻桥接」条。

代码生成通道说明：按仓库纪律先走 dpsk——实测仍返回 429（与 10-20 起的
状态一致）；改走 step193plan 后，其输出出现已知的思考过程泄漏与截断
（link.ts 一稿在 readRedemption 中途断掉），不满足整文件交付标准。最终
实现由编排侧按事先写死的规格文本逐字落盘（规格即本包各文件的 API 与
行为定义），并以类型检查 + 上述全量测试验收。kylon-cli 报告部分不涉及
代码生成。

## 附录 A：分析对象文件清单与哈希

| 文件 | 大小 | SHA-256 |
|---|---|---|
| kylon-cli-0.7.9.tgz（registry 原件） | - | 4add09107608af17a4c110ada6137d58c28e38ab27e71ffd74856fc65c78da88 |
| dist/kylon-bundle.mjs | 5.6MB | 8d3713f0ae69fe7bb5cecd97072aa4efa588843355f1ed1be9de87e80929bb46 |
| dist/kylon-core-bundle.mjs | 2.4MB | aeb55c9275a492ff1eb611a6e39210f23e702a6d040c227342755edd5015355e |
| dist/kylon-bundle.manifest.json | 4KB | 1e2f01c7b5a00561d082cc4946bfe1912a3db0904f0bcd62a37f9edb8b8a7c95 |
| package.json | - | 282b81e434487e80196531d03428d94f8ce015b8074f3f6e598df2414afd1bd3 |
| README.md | 73KB | 3eab2b1714d6f9f96921a16c78fcd1543dfc848155ca1c1a7ae2fb440b9f9157 |

## 附录 B：rea 执行记录

命令：`node ~/workspace/rea-tool/scripts/rea.mjs analyze-javascript-application
<解包目录>`（三轮：默认参数；`--source-path dist/kylon-core-bundle.mjs`；
节点上限 1000000 双参数）。三轮均无保留文件（见第 2 节），原始输出保存在
分析工作区 `~/workspace/kylon-ai-analysis/rea/`。
