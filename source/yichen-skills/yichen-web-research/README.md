# 逸尘互联网研究 · Yichen Web Research

`yichen-web-research` 是一套互联网研究工作流的总入口：把研究目标拆成搜索发现、来源核验、按需归档、音视频转写和证据综合，再交给四个职责明确的子 Skill。

它适合“研究一个问题并形成有来源支撑的结论”，例如公司与产品研究、行业历史与现状对比、跨平台资料整理。只搜索、只读取已知链接、只导出收藏或只转写文件时，直接使用对应子 Skill 即可，无须跑完整研究流程。

> 本 README 介绍当前仓库的能力与用法；实际执行规则以各目录的 `SKILL.md` 和 references 为准。安装 Skill 不等于安装所有后端，也不意味着每个平台已经登录、可访问或有可用额度。

## 一眼看懂：总入口与四个子 Skill

| 入口 | 解决什么问题 | 输入 | 主要交付 |
|---|---|---|---|
| **[yichen-web-research](SKILL.md)** | 如何把多个研究阶段组织起来，形成可追溯的分析？ | 研究对象、目标、时间范围、地区和语言等 | 研究计划、来源与主张对应关系、分析结论、证据缺口 |
| **[yichen-unified-search](../yichen-unified-search/SKILL.md)** | 还不知道资料在哪里，需要先找到候选来源 | 关键词、目标平台、时间与数量范围 | 带来源的候选清单、实际覆盖、错误和限制 |
| **[yichen-content-archive](../yichen-content-archive/SKILL.md)** | 已经知道要处理哪些链接，需要读取、下载或归档 | 已知 URL、URL 文件、已确认候选或明确的有限容器 | 正文、元数据、获准下载的媒体、归档与失败清单 |
| **[yichen-bookmarks-export](../yichen-bookmarks-export/SKILL.md)** | 把自己的私人收藏或书签链接导出到本地 | 本轮明确授权的平台、范围和输出位置 | 分平台链接文件、数量核验、抽样结果与交接记录 |
| **[yichen-asr](../yichen-asr/SKILL.md)** | 已有音视频，需要文字、字幕或口播粗剪 | 本地媒体文件、输出需求、服务商偏好 | 转写文本、时间戳、SRT 或按后端能力生成的粗剪产物 |

四个子 Skill 可以单独使用，也可以按任务组合。总入口负责安排阶段和综合证据；各子 Skill 负责执行自己的步骤，不互相递归调用。

## 1. 统一搜索：yichen-unified-search

### 能做什么

从关键词出发发现公开资料，选择合适的搜索后端，整理不同平台返回的内容，并说明哪些信息已核验、哪些仍只是候选。

| 搜索方向 | 具体能力 | 使用限制 |
|---|---|---|
| 公共网页与垂直领域 | 通过 AnySearch 搜索概念、教程、产品、行业资料；支持批量查询与垂直搜索 | 垂直领域先确认可用子域和必填参数；通用搜索的时间条件仍需原文核对 |
| AI 最新动态 | 通过 AI HOT 查找近期 AI 新闻与发布动态，多主题合并、去重并记录各主题覆盖 | items 路线最多 7 天、最多 5 个主题；不会把滚动窗口当成精确日期筛选 |
| 平台站内发现 | 按路由使用 YouTube、GitHub、B站、公众号、小红书、抖音、头条、小宇宙、知乎、微博和 X 等适配器 | 各平台依赖不同；支持的平台名称不代表任意环境都可执行 |
| X Quick / Research | Grok 原生 X 搜索优先；Quick 做有界查询，Research 拆成多个聚焦查询并按波次补充与去重 | Quick 每个查询最多 20 条、1–7 天；Research 至少 3 个聚焦查询，最多 40 次外层搜索、最多补搜一轮 |
| 站点 URL Map | 显式要求时用 Firecrawl 枚举公开站点指定路径下的链接 | 最多 100 条同源、同路径范围候选；不等于抓取全文或归档 |
| 当前搜索候选核验 | 对本次搜索获得的候选做轻量原文核验；默认 AnySearch，显式指定时可用 Firecrawl | 候选回执与来源约束必须有效；打开原文后仍需逐项判断它是否支持结论 |

多个平台或多个关键词会保留各自执行记录，不能只返回其中一路就声称完成全部任务。X 按帖子 ID 与规范 URL 去重，其他平台主要按 URL 去重；缺失的作者、日期、互动量等字段保持未知。

小红书和抖音的公开只读搜索可按既有规则复用 Chrome 会话，单次上限分别为 20、30 条，单关键词串行执行、请求间隔至少 5 秒。微博优先匿名，只有访问门失败才允许一次有界只读回退。X 的浏览器登录态回退默认关闭，需要本轮明确授权；主链超时、未登录或零结果不能伪装成额度耗尽来切换后端。

### 输出与适用示例

搜索交付包含 `request`、`routes`、`candidates`、`coverage`、`errors` 和 `schema_version`，便于继续核验或交接。给用户的结果可以是易读的 Markdown，但必须保留来源、失败、截断和时间范围限制。

示例请求：

- “用 `$yichen-unified-search` 找最近 7 天 AI 编程工具的新进展，给出原始来源和日期。”
- “分别在 GitHub 和 YouTube 查找 Obsidian Agent 工作流，列出候选并说明各平台覆盖。”
- “只枚举这个公开文档站 `/docs/` 下最多 30 个 URL，先不要读取全文。”

**不负责：** 下载媒体、建立长期数据库、私人收藏导出，或直接读取用户已经给出的内容链接。最后一种情况应使用归档子 Skill 的 `read` 路线。

详见：[搜索路由](../yichen-unified-search/references/routes.md) · [候选结构](../yichen-unified-search/references/candidate-schema.md)。

## 2. 已知内容归档：yichen-content-archive

### 能做什么

处理用户已经确定的内容。可选择只读正文或元数据、下载指定媒体，或者将内容整理到本地新目录，并保留来源与失败记录。

支持四类常见输入：单个或多个已知 URL、本地 URL 清单、用户已经确认的搜索候选，以及带精确引用和范围的受支持播放列表或播客容器。批量处理只沿给定范围进行，不追加推荐内容或相似账号。

| 来源 | 可执行的内容处理 |
|---|---|
| 普通网页 | 用既有 Reader 读取指定页面的正文，不顺带爬完整站点 |
| X / Twitter | 读取已知 Post、Quote、Article；匿名 FxTwitter 优先，必要时用 Jina；明确要求时下载该帖公开返回的视频 |
| 小红书 | 读取已知笔记的 HTML 和元数据；明确要求时下载笔记图片或视频；写入飞书需要单独的明确请求 |
| 抖音 | 读取已知视频元数据，或按请求下载视频 |
| 微博 | 规范化单条内容链接后匿名读取或下载，不枚举账号视频页、热榜、评论或推荐 |
| 微信公众号 | 通过 `yichen-wechat-mp-batch-exporter` 处理已知公开文章 URL 或 URL 文件；不支持按账号名搜索、完整历史或最新 N 篇枚举 |
| YouTube | 读取视频信息、下载媒体、提取字幕及枚举明确给出的播放列表；不做搜索或浏览频道 |
| B站 | 读取已知 BV/AV/完整链接，按请求下载；已知播放列表先生成条目清单 |
| 小宇宙 | 读取或下载已知 episode；明确播客容器的条目枚举按对应授权规则执行 |
| 其他公开媒体 | 对明确给出的单条公开 HTTPS 内容 URL，尝试匿名 `yt-dlp --no-playlist` 下载；无法支持时如实标记 |
| 有界公开站点 | 指定 HTTPS 站点、精确路径、页数与深度；先生成 Map 签名预检，再经明确执行授权调用 Crawl |

站点归档的上限为 **100 页、深度 3**，默认不含外域或子域。预检之后执行的范围必须一致且预检仍有效；Map 完成不会自动开始 Crawl。这是归档层的独立能力，不应与搜索层的 URL Map 或单页 Scrape 混为一谈。

### 输出与适用示例

归档通常包含：

```text
<archive-root>/
├── archive-manifest.jsonl  # 每条输入的来源、动作、状态与产物
├── run-summary.json       # 本轮数量与结果摘要
├── failures.json          # 失败与不支持项
├── handoff.json           # 后续阶段的范围和产物交接
└── <platform>/<item>/     # 按请求生成的正文或媒体
```

示例请求：

- “用 `$yichen-content-archive` 读取下面 5 篇文章并保存正文到一个新目录，不下载视频。”
- “下载这个 YouTube 视频已有的字幕，不转写、不下载视频。”
- “归档这个公开文档站 `/guide/` 下的内容，最多 30 页、深度 2；先给出预检结果。”

**边界：** 读取、下载、归档是不同动作，只执行请求中已经明确的部分。匿名访问失败不意味着可以自动读取 Cookie；不绕过登录墙、付费墙或验证码。已知链接也可能失效，不承诺全部可用。

详见：[平台路由](../yichen-content-archive/references/platform-routes.md) · [有界站点执行](../yichen-content-archive/references/bounded-site-execution.md)。

## 3. 私人收藏导出：yichen-bookmarks-export

### 能做什么

把用户本人当前有权访问的收藏、书签导出为本地链接清单，便于备份和后续挑选。它处理的是私人收藏中的链接，不是公开关键词搜索，也不是收藏内容下载器。

| 平台 | 导出方式 | 链接与核验 |
|---|---|---|
| 小红书 | 复用已登录 Chrome，在个人主页的收藏笔记页滚动并提取链接 | 保留可访问所需的完整笔记 URL；分别报告标签显示数量和实际导出数量 |
| 抖音 | 复用已登录 Chrome，在个人收藏页提取视频和图文链接 | 规范化 `/video/` 与页面实际出现的 `/note/` 链接，分别统计数量 |
| X / Twitter | 使用另行安装的 Field Theory GraphQL-only 兼容版本，分页导出本地书签索引 | 仅明确要求同步才执行同步，明确要求全量回溯才做全量同步；不附带分类 |

导出流程包括去重、空行和非法链接检查，以及首、中、末的抽样访问验证。滚动必须达到规定的稳定状态才可声称已到底；页面标签数与导出数不一致时会报告差值，不自行编造原因。

### 输出与适用示例

每个平台一个 `.txt` 链接文件，附带 `export-summary.json` 与 `handoff.json`。包含敏感参数的完整链接只保存在指定本地文件，不回显到聊天、普通日志或长期记忆。

示例请求：

- “用 `$yichen-bookmarks-export` 导出我当前可访问的全部小红书收藏链接，放到新的日期目录，只导出链接。”
- “同步并导出我的 X 书签，报告链接数、重复数与抽样结果。”

**边界：** 每次需要用户明确指定平台和范围；浏览器已经登录不能代替私人读取授权。导出后不会自动读取正文、下载媒体或分析收藏内容。后续归档要另行提出请求，再把链接文件交给 `yichen-content-archive`。平台 DOM 或非官方兼容接口变化时，可能导致导出不可用。

详见：[浏览器收藏导出](../yichen-bookmarks-export/references/chrome-collections.md) · [交接契约](../yichen-bookmarks-export/references/handoff-contract.md)。

## 4. 统一音视频转写：yichen-asr

### 能做什么

接收已有本地音频或视频，根据输出需求在 Step ASR 与火山引擎豆包 ASR 之间选择后端，先体检配置，再执行或恢复任务。它是转写路由层，不是第三套语音识别引擎。

| 需求 | 默认路线 | 产物与说明 |
|---|---|---|
| 全文转写，供摘要或内容分析使用 | Step ASR | 以分块转写文本为主；兼容执行器支持 30 秒切片，失败片段可缩小为 10/5 秒重试 |
| 较细的时间戳与 SRT 字幕 | 豆包 ASR | 使用结构化 utterances 和时间信息生成文字与字幕 |
| 口播停顿、填充词分析及粗剪 | 豆包 ASR 配合既有 ffmpeg 链 | 可生成分析与剪辑命令；实际剪辑按请求执行，不等于完整的创意成片制作 |
| 明确指定“只用 Step”或“只用豆包” | 用户指定后端 | 失败后报告原后端的恢复路径，不静默换服务商 |

公开版不内置 Step 执行器，需要配置 `YICHEN_STEP_ASR_SCRIPT` 或安装兼容的同级执行器。豆包路线依赖 `yichen-volc-asr`、用户自己的凭据和适用的 ffmpeg 环境。

### 输出与适用示例

交接记录说明 `provider`、`mode`、输入文件、实际产物路径、`request_id`、`billing_status` 和错误。文字或字幕交付以实际选定后端为准；Step 的分块文本不能冒充精确 SRT。

示例请求：

- “用 `$yichen-asr` 把这段本地访谈转成全文，只需要文字。”
- “给这段本地口播视频生成 SRT 字幕，只用豆包。”
- “分析这段口播的停顿和填充词，先生成粗剪命令，不执行剪辑。”

**边界：** 不搜索和下载视频。媒体会按所选后端提交给服务商；批量或可能显著消耗额度时，先说明文件数、总时长和服务商。配置了 Token 不代表账户有余额；一旦某家已经接收任务或产生 request ID，就优先恢复原任务，不向另一家重复提交同一媒体。

详见：[ASR 执行规则](../yichen-asr/SKILL.md) · [豆包底层执行器](../yichen-volc-asr/SKILL.md)。

## 如何组合成一次研究

```text
研究目标 → 明确范围与证据要求 → 统一搜索 → 原文核验 → 综合分析
                                              │
                       明确要求保存或下载后 ────┘
                                  ↓
                             已知内容归档
                                  │
                         需要处理本地音视频时
                                  ↓
                              统一 ASR

私人收藏导出 → 本地链接文件 → 用户另行提出归档请求 → 已知内容归档
```

### 场景一：公司、产品或行业研究

> 用 `$yichen-web-research` 研究某个行业从 2020 年至今的发展，比较中国与美国的当前产品格局，核对关键事件来源，区分事实与推断，并列出证据缺口。先不下载或归档材料。

总入口先固定时间、地区、语言和目标，再安排纵向发展史与横向比较。搜索子 Skill 负责找来源，核验后把主张与原文对应起来，总入口综合时间线、对比矩阵和结论。研究不要求四个子 Skill 都运行。

### 场景二：从资料发现到素材整理

先搜索并核验候选；用户确定要处理的链接与保存范围后，归档子 Skill 读取或下载这些条目。只有需要分析已下载音视频、且已经明确转写需求时，才进入 ASR。最后交付来源清单、实际产物、分析与失败项。

### 场景三：整理个人收藏

先明确平台和导出范围，收藏子 Skill 交付链接清单。用户再选择要读取或归档的部分，归档子 Skill 才开始处理；不会因为“收藏导出成功”就把全部私人内容下载到本地。

## 安装与首次使用

建议将总入口与四个子 Skill 安装在同一个 Skills 根目录，保留各自完整目录：

```text
<skills-root>/
├── yichen-web-research/
├── yichen-unified-search/
├── yichen-content-archive/
├── yichen-bookmarks-export/
└── yichen-asr/
```

还需要按具体任务配置外部后端。只做普通网页搜索不要求同时配置 ASR 和私人收藏工具；缺少必要后端时报告该路线不可用，不自动安装或替换服务商。独立复制五个目录时，也应保留仓库根目录的第三方来源说明与相关 `licenses/`，以免丢失许可文件。

在仓库根目录可先运行本地只读体检：

```bash
python3 yichen-web-research/scripts/doctor_yichen.py
```

体检检查本地可识别的依赖与配置状态，不证明在线接口一定可用，不查询财务余额，也不授权私人读取。具体配置变量、验证命令与上游来源见下方技术参考。

## English technical reference

### Research modes

Single-stage search still routes directly to `yichen-unified-search`. Known-link
reading or archiving, private bookmark export, and existing-media transcription
continue to use their dedicated child Skills.

For requests that require both historical development and a current
cross-sectional comparison, `yichen-web-research` adds a bounded
horizontal-and-vertical research protocol:

1. Normalize a dated research brief and build a canonical plan before browsing.
2. Search by bounded longitudinal and cross-sectional workstreams, with explicit
   geography and language coverage.
3. Verify claims against opened original sources and record a claim-source
   ledger; search snippets and AI summaries remain discovery aids only.
4. Assemble the evidence offline, reject structurally invalid bundles, and stop
   valid but incomplete bundles with `blocking` when scope, coverage,
   contradictions, cross-axis synthesis, or scenario gates fail.

From the repository root, the deterministic helpers are:

```bash
python3 yichen-web-research/scripts/plan_hengzong_research.py --brief brief.json
python3 yichen-web-research/scripts/assemble_hengzong_evidence.py --bundle bundle.json
```

The complete contract is in
[`references/hengzong-research.md`](references/hengzong-research.md). Search does
not authorize persistence: the archive route is used only when the user
explicitly requests it and supplies a bounded scope.

### Provenance

This mode is based on, inspired by, and extends the `hv-analysis` Skill from
[KKKKhazix/khazix-skills](https://github.com/KKKKhazix/khazix-skills/tree/7a5c4934be4106ac740ffdb95280bb81b3f4b83c/hv-analysis),
authored by 数字生命卡兹克 and pinned at upstream commit
`7a5c4934be4106ac740ffdb95280bb81b3f4b83c`. The upstream MIT license is
preserved in
[`licenses/KKKKhazix-khazix-skills-LICENSE.txt`](../licenses/KKKKhazix-khazix-skills-LICENSE.txt),
with the adaptation record in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Optional backends

The family can use capabilities that are not bundled here:

- AnySearch for general, batch, and vertical public search
- Firecrawl for explicit bounded site Map or current-candidate Scrape in the search
  layer; separately, the archive child supports bounded Crawl after a signed
  preflight and explicit execution authorization. It is never an implicit fallback
- a separately installed Zhihu Open Platform CLI-compatible runtime for public
  `search` and explicit `hot` discovery through the bundled allowlisted adapter;
  this repository does not independently verify that runtime's vendor provenance,
  and account and answer commands are excluded
- `gh`, `yt-dlp`, `bili`, OpenCLI, Grok CLI, and `xreach`
- the `yichen-grok-consult` plugin for Grok-first native X search, with anonymous
  FxTwitter fallback only after explicit Grok account-quota exhaustion
- `yichen-wechat-mp-batch-exporter`; private bookmark collectors are bundled in
  `yichen-bookmarks-export`, while Xiaohongshu and Douyin known-link fetchers are bundled in `yichen-content-archive`
- `yichen-volc-asr`, `ffmpeg`, and an optional compatible Step ASR executor
- WeChat public-article processing through `yichen-wechat-mp-batch-exporter` for
  known article URLs only; account-name search and account-history enumeration
  are unsupported

Missing optional backends reduce coverage; they do not relax authorization
rules or trigger automatic installation.

Known public X status and Article URLs are handled by the bundled
`yichen-content-archive/scripts/x_known_url.py` adapter. It uses anonymous
FxTwitter first, adds Jina only when needed, and returns OpenCLI/xreach merely
as authorization-gated fallback plans.

## Portable configuration

The public version contains no personal absolute paths, App IDs, tokens,
cookies, proxy credentials, or fixed Keychain items. Configure only the
backends you use:

| Variable | Purpose |
|---|---|
| `YICHEN_SKILLS_ROOT` | Override the directory containing the sibling Skills |
| `YICHEN_ANYSEARCH_RUNTIME_CONF` | Override the AnySearch `runtime.conf` path |
| `OPENCLI_HOME` | Override the OpenCLI state directory |
| `YICHEN_XIAOYUZHOU_CREDENTIAL_FILE` | Override the Xiaoyuzhou OpenCLI credential-file location |
| `YICHEN_STEP_ASR_SCRIPT` | Path to an independently installed Step ASR executor |
| `FIRECRAWL_API_KEY` | Optional Firecrawl API key; the doctor checks only whether it is non-empty |
| `FIRECRAWL_KEY_FILE` | Optional private Firecrawl key file; the doctor checks metadata only and never reads it |
| `ZHIHU_CLI` | Override the separately installed Zhihu CLI-compatible executable path |
| `YICHEN_DOUBAO_ASR_SCRIPT` | Override the bundled `yichen-volc-asr` executor path |
| `VOLC_ASR_TRIAL_APP_ID` / `VOLC_ASR_PAID_APP_ID` | User-owned Volcengine application IDs |
| `VOLC_ASR_TRIAL_TOKEN` / `VOLC_ASR_PAID_TOKEN` | User-owned Volcengine tokens |
| `WECHAT_ARTICLE_EXPORTER_KV` | Local exporter state directory |
| `GROK_CLI` | Override the Grok executable path |
| `GROK_AUTH_FILE` | Override the Grok local authentication-status file path |
| `YICHEN_GROK_CONSULT_ROOT` | Optional local source path used only by the doctor |
| `YICHEN_GROK_CONSULT_ENABLED=1` | Optional doctor hint that the plugin is enabled |
| `CODEX_CONFIG` | Optional Codex config path used to detect an enabled Grok plugin when no explicit hint is set |

Never commit the values of credential variables or local state files.

## Safety model

- Search never automatically turns into download or archive.
- Social-platform actions are read-only.
- Bounded public read-only Xiaohongshu and Douyin search may reuse an existing
  Chrome session without per-run authorization: one keyword, serial execution,
  at least five seconds between requests, and at most 20/30 results respectively.
- Writes, private-scope reads, account changes, and verification-code handling
  still require explicit current-turn authorization.
- Firecrawl Map is limited to an explicit public origin and input path, with at
  most 100 same-origin in-path URLs; Map results remain unverified candidates.
- Firecrawl Scrape accepts only a current AnySearch candidate with a valid
  short-lived receipt; it is not a Crawl or archive route.
- The Zhihu doctor runs only offline metadata commands, removes environment
  credentials from the child process, and accepts Keychain-only authentication.
- WeChat desktop or mobile UI is never controlled.
- Private bookmark authorization does not transfer to media download.
- An ASR job already submitted to one provider is never silently resubmitted to
  another provider.
- Existing artifacts are not overwritten or deleted by default.

The Xiaoyuzhou helper accepts only HTTPS episode pages on
`xiaoyuzhoufm.com` and audio on `xyzcdn.net`. The legacy local WeChat helper is
a fail-closed compatibility stub, not a login, search, or download backend.

## Validation

From the repository root:

```bash
python3 -m unittest discover -s yichen-web-research/tests -p 'test_*.py'
python3 yichen-web-research/scripts/validate_family.py
python3 yichen-web-research/scripts/validate_family.py --doctor
```

The first command is fully offline. `--doctor` performs read-only local
availability checks and may invoke installed CLI help/auth-status commands; it
does not authorize a private read, read a Firecrawl key, issue a Zhihu search,
or call an ASR billing endpoint.
