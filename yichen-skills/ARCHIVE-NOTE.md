# ARCHIVE-NOTE：mcncarl/yichen-skills

- 来源：https://github.com/mcncarl/yichen-skills
- 归档 commit：ed6200f81ff1fddd1482ad6cae7f4a75de5ffc75（2026-10-28，docs(wechat): clarify Windows full local parsing support）
- Stars：4,912；Forks：2,817（2026-10-29 核实）
- 规模：240 个文件，约 4.9MB；无 >50MB 单文件，无排除项（.git 已排除，不进仓）
- 入口：用户给的是其中 yichen-wechat-local-vault 的 README 链接，按惯例全仓归档

## 许可证（重要：不是开源许可证）

- GitHub API 显示 NOASSERTION（无 SPDX 标识），但仓内 LICENSE 是自定义的
  Personal Learning and Non-Commercial Use License（2026，Copyright repository owner）。
- 许可范围：仅限个人学习、研究、非商业个人工作流；可查看、clone、学习、修改。
- 明确禁止（无著作权人事先书面许可）：商业使用（出售、出租、转授、付费访问、
  收入产品或服务、客户交付、任何创收或业务运营用途）；以竞争性或打包产品形式
  公开再发布、镜像、打包、营销本仓或衍生作品（公开 skill 合集、模板包、
  市场条目、SaaS 组件、机构交付物、课程资产、公司内部工具包均在内）。
- 商业授权须联系著作权人微信 yichen365ai，验证消息注明 Commercial Authorization，
  仅收到明确书面授权后才可用。
- 必须保留本 LICENSE 与 THIRD_PARTY_NOTICES.md；第三方部分仍受各自原始许可证约束。
- 子目录自带许可证已原样保留：yichen-codex-chatgpt/LICENSE（指向仓级许可证）、
  yichen-x-article-draft-uploader/LICENSE（同款个人学习与非商业许可证，另注明
  不改变另行分发的 Ailu 项目的 GNU AGPL-3.0-or-later）。
- 影响：本次为私人学习归档与技能库原文收录；任何商业使用或把本批 skill 作为
  公开产品/服务的一部分提供，均须先取得书面许可，否则不得做。

## 仓内 skill（17 个，已全部原文入库）

- yichen-agent-memory：Agent Memory Vault 共享记忆系统的安装/升级/检索/维护
- yichen-asr：统一音视频转写入口（StepFun Step ASR 与火山豆包 ASR 路由）
- yichen-bookmarks-export：当轮授权后只读导出小红书/抖音收藏、X 书签为本地链接文件
- yichen-chatgpt-web-research：用已登录的 ChatGPT 官网账号做调研（Chrome 插件路线优先）
- yichen-codex-chatgpt：ChatGPT 官网 + Codex 协作环（ChatGPT 设计/审查，Codex 本地写代码）
- yichen-content-archive：已知链接/URL 清单的有界归档（不做关键词发现）
- yichen-mac-wechat-dual-open：macOS 微信双开（复制微信、改 bundle id、ad-hoc 重签名）
- yichen-unified-search：统一编排公共网页/AI 动态/垂直领域/社交平台搜索
- yichen-volc-asr：火山引擎音视频转写 + 口播自动粗剪
- yichen-web-research：互联网研究总入口（多阶段系统深度研究，分发给子 skill）
- yichen-wechat-local-vault：微信本地数字资产库（见下）
- yichen-wechat-mp-batch-exporter：微信公众号文章批量下载（见下）
- yichen-wecom-local-vault：企业微信 macOS 本地数据库 vault
- yichen-wecom-operations：企业微信官方 wecom-cli 操作入口（文档/待办/会议）
- yichen-x-article-draft-uploader：本地 Markdown 上传到 X Articles 草稿
- yichen-x-slicer：公开 X 推文/Thread 转 1080x1440 图片切片与 MP4
- yichen-grok-consult：插件内 skill，用 GPT 主导的 Codex 对话调用 xAI Grok
  （注意：只入库了 plugins/yichen-grok-consult/skills/ 下的 skill 目录；
  其 MCP 服务器 plugins/yichen-grok-consult/mcp/server.mjs 仅留在全仓归档里，
  未单独拆进技能库）

## 重点 skill：yichen-wechat-local-vault（用户给的链接）

- 干什么：微信本地数字资产库，macOS / Windows 本地全量解析——本地全库采集、
  认证解密、聊天记录读取/搜索/导出、朋友圈与收藏正文解析；Mac 另支持增量刷新、
  漏看/待回复检查；Windows 已实测本机采集与离线快照查询。
- 设计上只动本地数据：密钥与配置只放本机私有配置区，明文库与解密清单只放本机
  私有 vault，查询输出默认隐藏 username 与微信号；文档明确要求不得把明文数据库
  同步、分享或复制到项目目录、桌面、网盘或聊天回复里。
- 安全判断：本 skill 不向外传数据，但它要抓取本机微信密钥并解密本地数据库，
  属于高敏感本地工具。只可在用户自己的机器与数据上、在用户明确授权后使用；
  绝不用于他人数据，绝不连接任何微信账号做线上操作（本次归档全程未碰微信账号
  与真实聊天数据）。

## @gengdaJ X 帖子（2026-09-10，来源之二）的微信生态 4 skill 与风险提示（作者原话，如实记录）

1. 微信数据 Skill → yichen-wechat-local-vault：聊天记录、联系人、朋友圈、收藏夹
   可被 Codex 读取，支持增量。作者原话：只有首次重签名有一定风险，后续基本无风险。
2. 微信公众号文章下载 Skill → yichen-wechat-mp-batch-exporter：公开仓版本以给链接
   下载 Markdown 为准。作者原话：按公众号名批量导出上千篇的上游仓库已关闭，
   他自己维护的批量版只对 TradeWinds 社群成员开放——不要把 TradeWinds 专属的
   批量版写成公开版的功能。
3. 微信双开 Skill → yichen-mac-wechat-dual-open：作者原话：有一定风险，自己经常
   被弹出登录，现在没用了。
4. 企微微信数据 Skill → yichen-wecom-local-vault：同微信 Skill。

## 融合判断（本轮只归档 + 入库，未改动剧坊/BotsTalk 代码）

- 最值得对照：yichen-wechat-local-vault（本地库解析路线，与我们走微信 ChatAPI
  的线上路线是两条不同路子；只读 vault 与 digest 素材包工作流可作参考）与
  yichen-wechat-mp-batch-exporter（公众号文章批量下载，与我们 Keenable 绕过
  反爬的路子不同，可作对照）。
- 只归档、不主动推：yichen-mac-wechat-dual-open（作者已明说有风险且自己不用了）、
  其余通用研究/转写/ASR 类 skill（与现有能力重叠或需对方账号/服务商配置）。
- 集成须用户另行下令；且受上文非商业许可证约束，商业化前须先取得书面许可。
