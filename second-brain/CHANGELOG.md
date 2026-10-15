# 更新日志

本项目的所有重要变更都会记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.5.0] - 2026-10-16

反向链接面板——打开一篇笔记就知道谁引用了它

### 新增
- 新增 `internal/store/backlinks.go`：`Backlink` 结构与 `Store.Backlinks(noteID)`，按引用者 id 倒序返回；`buildSnippet` 按 rune 提取 `[[标题]]` 所在行前后各 40 字上下文，中文不断字。
- 新增 API `GET /api/notes/{id}/backlinks`：笔记不存在返回 404，无人引用返回空数组 `[]`。
- 前端编辑区附件区下方新增「反向链接」区：引用者标题 + 引用上下文，点击标题跳转到引用者笔记；沿用附件区视觉体系，无新颜色。
- 真实截图 `docs/screenshots/backlinks.png` 已亲眼验收。

### 测试
- 全量 114 通过（v0.4.0 的 104 + 新增 10：store 6 + api 4），`go vet`、`gofmt` 全洁。
- store 6 例：基本查询、空返回非 nil、多条倒序、删源笔记、去掉链接后消失、先写 `[[Gamma]]` 再建 Gamma 回填生效。
- api 4 例：有引用者 200、空数组 `[]`、不存在 404、非法 id 非 200（真实 HTTP）。
- 真实冒烟：3 篇真实笔记 → 反向链接 2 条倒序，snippet 中文正确；Playwright 真实点击跳转验证通过。

## [0.4.0] - 2026-10-16

主动复习外部推送——到期提醒推出去

### 新增
- 新增 `internal/notify` 包：定义 `Sender` 接口，提供 SMTP 与 Webhook 两种通知通道。
- 新增 `SMTPSender`：基于标准库 `net/smtp`，支持 STARTTLS 与明文两种模式。
- 新增 `WebhookSender`：POST JSON，带 `X-Event: review.digest`，带 `X-Signature: sha256=<hex(hmac-sha256(secret, body))>`。
- 新增 `BuildDigestMessage` 纯函数：生成主题、纯文本正文和邮件客户端兼容 HTML（table 布局、内联样式，标题与摘要做 HTML 转义）。
- 新增 `internal/push` 包：`NextPushTime` 纯函数、30 秒 tick 的 `Scheduler`、`RunPush` 推送流程。
- 推送幂等：同一天同一通道只成功推送一次，靠 `push_log` 唯一索引加 `HasPushed` 检查。
- 新增推送 API：`GET/PUT /api/push/settings`、`POST /api/push/test`、`GET /api/push/history`。
- 新增推送设置页：侧边导航「推送设置」，含启用、时间、时区、收件邮箱、SMTP 主机、发件地址、Webhook 地址、保存、测试 SMTP、测试 Webhook、推送历史表。
- 新增 12 个推送配置项：`SB_PUSH_ENABLED`、`SB_PUSH_TIME`、`SB_PUSH_TZ`、`SB_SMTP_HOST`、`SB_SMTP_PORT`、`SB_SMTP_USER`、`SB_SMTP_PASS`、`SB_SMTP_FROM`、`SB_SMTP_TLS`、`SB_MAIL_TO`、`SB_WEBHOOK_URL`、`SB_WEBHOOK_SECRET`。

### 测试
- 全量 104 通过，v0.3.0 时 68，新增 36。
- notify 单元 8 条：标题、空队列、HTML 转义 XSS、webhook 成功与验签、非 2xx、超时、SMTP 不可达。
- push 调度单测：`NextPushTime` 当天未来、已过转次日、非法格式、时区；`RunPush` 幂等；单通道失败不影响另一通道。
- api 集成：webhook 接收端验 `X-Signature`；自研最小 fake SMTP 服务器走完 EHLO→DATA→QUIT 真实收信；settings 脱敏；PUT 非法 time 返回 400；body 含 password 返回 400。
- 真实冒烟（2026-10-16）：webhook 接收桩真实收到 `X-Event`、`X-Signature` 与完整 payload；调度器按配置时间真实触发，`push_log` 记 sent；`/api/push/test` 真实发出。

### 已知限制
- SMTP 密码与 webhook 密钥只能走环境变量，页面不可配置。
- 单用户，无多租户。
- 调度器按单实例假设工作，多实例部署会重复推送，需要外部保证单实例。
- SMTP 发送失败按次记录，可等次日或手动测试重发，没有自动重试队列。

## [0.3.0]
## [0.3.0] - 2026-10-15

附件与导出——笔记可以带图片和文件了，全库也能一键带走。

### 新增

- **附件支持**：`POST /api/notes/{id}/attachments` 上传附件（multipart，默认单个 ≤10MB，可用 `SB_ATTACH_MAX_MB` 调整）；扩展名白名单 + 文件名消毒 + 图片 MIME 嗅探校验；文件落 `<数据目录>/attachments/<笔记id>/`，元数据记 `attachments` 表（含 sha256）；`GET /api/notes/{id}/attachments` 列表、`GET /api/attachments/{id}` 下载、`DELETE /api/attachments/{id}` 删除；删笔记时附件目录一并清理。
- **Markdown 附件引用**：正文中 `![说明](attachment:123)` 渲染为内联图片，`[说明](attachment:123)` 渲染为下载链接，编辑预览与复习卡片共用同一渲染。
- **附件 Web UI**：编辑区新增附件区（上传入口、附件列表、图片缩略图预览、插入引用/下载/删除）。
- **导出**：`GET /api/export/markdown` 打包全库为 zip（`index.md` + `notes/` 下每篇一个带 front matter 的 `.md` + `attachments/` 原文件，引用改写为相对路径，条目名消毒防 ZipSlip）；`GET /api/export/json` 导出全库 JSON（含标签与附件元数据）；侧边栏新增导出按钮。

### 文档

- README 新增附件与导出章节、API 表与配置项，路线图移除已落地的两项。

## [0.2.0] - 2026-10-13

主动复习引擎——让笔记从“记录”走向“记忆”。

### 新增

- **SM-2 间隔重复算法**：新增 `internal/review` 纯函数包，实现 SuperMemo SM-2 调度算法，核心逻辑无副作用、可独立测试，包含难度因子（EF）更新、间隔递增与复习时间计算。
- **`reviews` 表与到期队列**：新增 `reviews` 数据表，记录每次复习的评分、时间与调度状态；提供按到期时间排序的复习队列，支持“今日待复习”查询。
- **复习统计**：新增学习统计能力，包括连续复习天数（streak）、近 7 日复习量、平均难度因子（平均 EF）等指标。
- **每日回顾 digest**：新增每日回顾摘要生成，汇总当日到期卡片与复习进度，帮助用户快速进入复习状态。
- **抽认卡复习 UI**：新增抽认卡（flashcard）复习界面，支持翻卡、四档评分（忘记 / 困难 / 良好 / 简单）与复习进度展示。

### 修复

- **Web 三件套一致性重建**：修复 HTML、CSS、JavaScript 之间元素 `id` 错位导致的事件绑定失效与状态渲染异常问题，重建三者一致的 DOM 契约。

### 变更

- 复习相关调度逻辑统一收敛至 `internal/review` 纯函数包，UI 与存储层仅负责编排与持久化，便于后续测试与替换算法。

## [0.1.0] - 2026-10-13

工程化 v1——从零搭建可用的第二大脑基础设施。

### 新增

- **笔记 CRUD**：支持笔记的创建、读取、更新与删除。
- **标签**：支持为笔记打标签，并按标签组织与筛选内容。
- **全文搜索**：基于 SQLite 的全文搜索能力，快速定位笔记内容。
- **双链与知识图谱**：支持笔记间双向链接，并据此构建知识图谱视图。
- **内嵌 Web UI**：提供内嵌于应用的 Web 界面，无需额外部署即可使用。
- **SQLite 持久化**：所有数据通过 SQLite 本地持久化，保证数据可迁移、可备份。
