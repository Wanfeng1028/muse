# Drama Factory ROADMAP（对标 pix6 补齐轮）

> 用户总指令："人家有的我们缺的全部补齐，能超越的做好，同时打磨出自己的一套 UI 设计体系"。
> 模型接入走 **BYOK**：模型初始为空，用户在通道管理自填 API；入口全做。视觉只用自家设计体系（见 DESIGN_SYSTEM.md），不借 pix6 的 UI。

## 本轮已完成

- [x] 配色重做（纯白 / 中性灰黑）
- [x] Token 用量统计（聚合 API + 用量页，诚实口径）
- [x] 用量统计页改版（CC Switch 信息架构：KPI 卡片行 / 筛选器 / 三维度趋势图 / 请求日志表；新增 /api/usage/requests 逐请求明细 + /api/usage/filters；输入输出拆分与缓存数据后端未采集，页面诚实显示 —）
- [x] 供应商卡片制（按模块分组：视频/图片/音乐/TTS/数字人；单 Key，无号池）
- [x] 新模块入口页：AI 图片 / AI 音乐 / 数字人（模型选择器初始为空，空状态 + 置灰按钮）
- [x] UI 设计体系文档（docs/DESIGN_SYSTEM.md）
- [x] 2026-10-14 AI MV v2「时间轴对齐」（SOUL-mv.md 技术点 #1）：MvTimelineService（code-point 加权→按音频时长缩放→800ms 钳制→舍入吸收）+ V12 timeline_json；compose 持久化时间轴，storyboard 逐行出分镜，render 逐行 SRT、成片时长=音频时长；前端时间轴展示区（等宽时间码）+ 3 个 v1 真 bug 修复；冒烟全链路 SUCCEEDED（final.mp4=8.0s=音频时长，26 条逐行字幕）；63 个新测试，覆盖率行 0.823/分支 0.727 门禁通过；对照报告 docs/dod-mv-v2.md；截图 docs/screenshots/mv-v2-*.png。
- [x] 2026-10-14 AI MV「导入已有音频」（作词作曲非必需）：`POST /api/mv/import`（mp3/wav/m4a ≤100MB，入资产库）；V14 `mv_songs.source`（AI/IMPORT）；作词作曲步骤 SKIPPED（时间线注"已跳过作词作曲（用户导入音频）"）；歌词可选（有则字幕时间轴，无则纯音乐 10 秒切段、无字幕跳过烧录）；导入模式调 /lyrics//compose 拒绝；前端双模式选项卡+上传进度+试听+跳过态；缺参 400；8 个新测试；`mvn -o test` 892 全绿；说明 docs/mv-import.md。
- [x] 2026-10-14 AI MV 模式 v1：AgentType 新增 LYRICS/COMPOSE；MvSong 实体 + V8/V11 迁移；MvLyricsService（DeepSeek 作词）/ MvService（Run 编排：作词→作曲→分镜→视频→剪辑→质检）/ MvController（6 端点 + /status 轮询）；AceStepMusicProvider（BYOK 作曲渠道）；mv.html + mv.js（5 步创作流，深浅主题已验收）；侧边栏 AI MV 入口；测试 MvServiceTest(8)+MvControllerTest(5) 全绿；作曲渠道调研见 docs/mv-music-providers.md（MiniMax 存量可用，ACE-Step 推荐新用户，Suno 无官方 API）。

## 下一轮起，按优先级一轮一补

### P0（紧接下一轮）
1. **BYOK 生成调用**：用户配好 API 后，图片/音乐/数字人页选模型即真实可用。
   需要先定协议方案（OpenAI 兼容优先 + 自定义映射兜底），不许点出假成功。
   - [x] 2026-10-14 视频供应商连接自检落地：`POST /api/providers/{id}/test` + 卡片"测试连接"按钮；Agnes/Qwen 用"查询不存在任务"的负向探测（零费用，401=密钥无效/404=密钥有效，已核验官方文档），mock 恒 OK，未接入模块诚实返回 UNSUPPORTED；见 docs/connection-probe.md。
   - [x] 2026-10-14 图片/音乐/数字人真实生成调用落地：`POST /api/byok/generate`（服务端阻塞轮询后落盘，返回本地 URL）+ `GET /api/byok/file/{module}/{filename}`；DashScope 万相文生图（`wan2.5-t2i-preview`，async 提交+轮询，探针零费用 404=密钥有效）、MiniMax Music（`music-3.0`，同步调用；注：官方已公告 2026-08 起不对新用户开放，仅存量付费用户可用）、D-ID 数字人（talks 接口+轮询，探针 `GET /credits` 零费用）；Key 解析顺序 卡片→设置中心→surrogate（仅 DashScope）；前端三页接真实接口（进度态+结果展示），avatar 页 v1.0 改用公网 URL 输入；DashScope wan2.5 真实出图已验证（1024×1024 PNG）；测试 515→544 全绿。
2. **账号体系**：邮箱注册登录（BCrypt）+ Google / Apple / GitHub OAuth；
   个人资料（几何/插画默认头像，禁字母头像）、账号与安全（改密码/改邮箱/会话管理）、
   个性化（主题/语言）；登录限流、密码强度、敏感操作二次验证。OAuth 无真实凭证前诚实标注未实测。

### P1
3. **用量采集补齐**：prompt/completion token 拆分、缓存命中统计（需改 VideoTask/AgentStep 采集管线 + DB 字段，工作量大，单独立项）。
   - [x] 2026-10-14 落地：VideoTask/AgentStep 加 prompt_tokens/completion_tokens/cached_tokens（V7 迁移，老数据默认 0）；LlmScriptService 解析 OpenAI 兼容 usage 并透传落库；BYOK 无用量返回诚实记 0；/api/usage/summary 加拆分 + 缓存命中率、/api/usage/requests 明细带拆分字段。
4. **画布**：分镜/成片的可视化编排画布（对标 pix6 画布）。
   - [x] 2026-10-14 落地：`canvas.html` 分镜画布页（项目/剧集联动下拉、横向时间轴条按时长成比例、卡片网格、拖拽排序调 `POST /episodes/{id}/shots/reorder`（乐观更新+失败回滚）、点击卡片弹窗编辑画面描述/视频Prompt/台词/景别/运镜/时长（`PUT /shots/{id}`）、状态徽标（video-tasks 最新状态直接用后端 statusLabel）、空状态、深浅主题；shell.js 导航注册 + layout-grid 图标映射。深浅主题+编辑器弹窗+空状态截图验收通过，真实拖拽冒烟通过（DOM 1,2,3→2,3,1，toast"顺序已更新"），`mvn -o test` 883 全绿。
4. **资产库**：图片/音频/视频素材统一管理（上传、打标、复用）。
   - [x] 2026-10-14 落地：Asset 实体 + V9 迁移；/api/assets 上传（50MB/类型校验/防穿越）/列表（筛选+搜索）/打标/删除/复用/文件流；BYOK 生成产物自动入资产库。
5. **模板/配方库**：提示词模板、风格配方一键复用。
   - [x] 2026-10-14 落地：PromptRecipe 实体 + V10 迁移；/api/recipes CRUD + render（{{变量}} 替换）+ apply（target=SCRIPT/BOARD，usageCount+1）；5 套风格配方预设（赛博/水墨/胶片/日系/写实）含模型参数。

### P2
6. **Skill 市场**：Agent 技能/工作流的发布与安装。
   - [x] 2026-10-15 落地：Skill/SkillVersion/SkillInstall/SkillRating 实体 + V15 迁移（含 agent_steps.skill_id）；4 个官方预设 Skill（分镜大师/短剧钩子开头/转场设计/爽点节奏）；/api/skills 发布/检索（搜索+tag+分类+排序）/详情/发版/安装（幂等，可升级降级）/卸载/评分/模板渲染；已安装 Skill 可在剧本（`POST /api/episodes/{id}/generate-script?skillId=`）与分镜（`POST /api/episodes/{id}/shots/from-script` body.skillId）生成时选用，prompt 模板注入大模型 system prompt（`【Skill 增强】`段）；Run 创建支持 scriptSkillId/boardSkillId，时间线记录"SCRIPT/BOARD 使用 Skill：名称 v版本"；`skills.html` 市场页（浏览/已安装/发布/详情弹窗，深浅主题）+ 分镜板 Skill 下拉框；docs/skill-market.md。新增测试 26 例（发布/安装/卸载/评分/版本升级全链路 MockMvc + prompt 透传单测），`mvn -o test` 917 全绿（含 26 例新增）。
   - [x] 2026-10-15 视觉验收补课：skills.html 之前**从未截图验收**（本轮亲眼验收通过）。抓出并修复 1 个真实 UI bug：已安装列表把 ISO 时间戳原文直接渲染（`安装于 2026-10-14T19:55:24.657036`）→ 加 `fmtDateTime` 格式化为 `YYYY-MM-DD HH:mm`（与 usage.js 风格一致）。截图 `docs/screenshots/skills-{light,dark,detail-light}.png`（4 官方 Skill 真实数据 + 已安装 1 个 + 5 星评价 1 条），已同步 README 界面预览。
7. **快捷工具**：批量处理、格式转换等小工具集。
   - [x] 2026-10-15 落地：`tools.html` 卡片式 5 工具（资产批量打标/重命名、视频 mp4↔webm 转码+压缩、音频提取 mp3/wav、分镜表 CSV 导出、操作记录）；`POST /api/tools/*` + `GET /api/tools/op-logs`；`tool_op_log` 表（V16）；ffmpeg 复用 FfmpegService；产物自动入资产库。18 例测试全绿，深浅主题截图验收通过。详见 docs/quick-tools.md。
   - [x] 2026-10-15 视觉验收返工：上一轮截图是**空数据状态**（"暂无资产/暂无视频资产/暂无项目"，不符合门面截图必须带真实数据的铁律），且截图未入仓。本轮造演示数据（图片+视频资产各 1、《霓虹夜行》项目+第 1 集）重拍深浅主题，已入 `docs/screenshots/tools-{light,dark}.png` 并同步 README。重拍时抓出并修复 1 个真实功能 bug：`tools.js` 的 `loadProjects()` 请求了带尾斜杠的 `/api/projects/`（Spring Boot 3 默认不匹配尾斜杠 → 404 → 下拉永远"暂无项目"，分镜表导出工具 UI 上不可用）→ 去掉尾斜杠。另修复 shell.js 顶栏标题缺失：`pageTitle` 映射漏了 `mv/tools/account` 三个 id（AI MV/快捷工具/账号三页顶栏错误显示"AI 短剧工坊"）→ 已补齐。
8. **创作者计划**：创作者主页、分成/激励（需商业方案先行，技术后置）。
   - [x] 2026-10-27 落地主页 v1：`CreatorProfile`/`CreatorFollow` 实体 + V25 迁移；`/api/creators` 列表（搜索/最新/关注最多/Skill 最多排序）/详情（真实 Skill 统计 + 技能列表）/创建（201）/编辑（仅所有者，否则 403）/关注与取消关注（幂等）；`creators.html` + `creators.js`（侧边栏运行分组注册，中英双语）；文档见 docs/creator-program.md。分成/激励仍待商业方案，v1 不含任何收益数字（页面仅诚实提示规则待公布）。
   - [x] 2026-10-27 落地关注动态 v2（非收益后续）：`GET /api/creators/feed`（limit 1–50 默认 20，已关注创作者的 Skill 按发布时间倒序、按 id 去重）；`creators.html` 关注动态卡片 + `creators.js` 的 `loadFeed()`（加载与关注切换后自动刷新 + 手动刷新，诚实空态，中英双语）；无 schema 变更、无收益数字。文档见 docs/creator-program.md 第 5 节。
   - [x] 2026-10-27 落地我的关注列表 v3（非收益后续）；
   - [x] 2026-10-27 落地为你推荐 v4（非收益后续）：`GET /api/creators/recommended?limit=10`（limit 1–50，非法 400；排除已关注与本人主页；按粉丝数倒序、技能数倒序、创建时间倒序；含技能数/粉丝数/最新 Skill）；`creators.html`「为你推荐」卡片 + `creators.js` 的 `loadRecommended()`/`followRecommended()`（卡片内关注后推荐、我的关注、关注动态、创作者列表四处刷新）；无 schema 变更、无收益数字。文档见 docs/creator-program.md 第 7 节。：`GET /api/creators/following`（按关注时间倒序、含技能数/粉丝数/最新 Skill、缺失档案跳过）；`creators.html`「我的关注」卡片 + `creators.js` 的 `loadFollowing()`/`unfollowFollowing()`（卡片内取消关注后关注列表、关注动态、创作者列表三处刷新）；无 schema 变更、无收益数字。文档见 docs/creator-program.md 第 6 节。
   - [x] 2026-10-27 落地创作者排行榜 v5（非收益后续）：`GET /api/creators/leaderboard?limit=10`（limit 1–50，非法 400；覆盖全部创作者，不排除已关注与本人；按粉丝数倒序、技能数倒序、创建时间倒序排列并截断至 limit，截断后按序赋予 1 起的名次 rank；含技能数/粉丝数/最新 Skill）；`creators.html`「创作者排行榜」卡片 + `creators.js` 的 `loadLeaderboard()`/`followLeaderboard()`（卡片内关注后排行榜、为你推荐、我的关注、关注动态、创作者列表五处刷新）；无 schema 变更、无收益数字。文档见 docs/creator-program.md 第 8 节。

## 差异化（超越 pix6 的点，本项目独有）

- Harness 定位：Run 全生命周期管理（目标→计划→步骤时间线→暂停/重试/审批→产物归档→成本统计）
- Token 用量统计（诚实口径：只显示真实数，未知显示 —）
- 开源（万 star 标准打磨）
