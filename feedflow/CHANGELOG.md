
# 更新日志

## v1.14.0 — 2026-10-25

### 前端美化（设计层 + 空态导览文案，不改功能与后端）

- 关闭 v1.13.0 已知限制“阅读器空态仍是功能性提示，未做成导览页”一项：阅读器未选文章时，右栏不再只有一句提示——原提示句留作标题行，下方 1px 细线分隔出三步导览（左边订阅树选源 → 中间列表选篇 → 正文在此打开，可星标、标已读或查看原文），脚注给出去订阅管理 / 今日必读的入口。三步文案逐项对过真实行为：订阅树、文章列表、星标/已读/原文按钮均是既有功能；脚注初版“还没有订阅源？”与种子库已有 6 个源的实况不符，验收时已改成中性说法“要加新源去订阅管理”。
- 新增 `feedflow/static/css/design-v114.css`（base.html 在 v113 之后引用；原样式表、v112/v113 层、app.js、mobile.js 一字不动），模型稿 3 条规则原样落仓（`.reader-guide`、`.reader-guide li`、`.guide-step`）：导览去默认序号、顶线分隔、行距 1.8；步骤 15px 墨色字；数字徽标 13px 柿色字 + 浅柿底 + 2px 柿色左线。脚注行无专属规则，沿用 v112 层 `.reader-empty` 的次要色。
- 视觉逻辑“空态就是报纸的使用说明小卡”见 `docs/DESIGN.md` v1.14.0 一节。
- 测试：`tests/test_design_v114.py` 2 例（设计层引用与 served、三选择器、导览文案、三栏结构无覆盖、报纸 token）；v112/v113 设计测试同跑，全量 7/7 通过。
- 视觉验收：真实服务（18314 端口，应用自带种子库：6 源 33 篇）+ 截图亲眼核对 `docs/screenshots/reader-empty-guide.png`——未选文章的右栏导览、柿色数字徽标、细线分隔均实证可见，计算样式与规则一一对上（导览顶线 1px #E7E2D6、徽标底 #FBEDE6、左线 2px #C2410C）；冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v114-shot.js。

### 本轮已知限制

- 390px 下顶栏导航仍横向溢出（v1.13.0 已知限制，延续）。

## v1.13.0 — 2026-10-25

### 前端美化（设计层，不改功能与后端）
- 新增 `feedflow/static/css/design-v113.css`，base.html 在 design-v112.css 之后引用；原样式表、v112 层与 mobile.js 一字不动。关闭 v1.12.0 已知限制“移动端三栏切换样式未动”一项。
  视觉逻辑“切换栏就是报纸的页眉细线”见 `docs/DESIGN.md`：切换栏纸面底（#FAFAF7）加细线分隔（#E7E2D6）；未选中按钮 13px 次要色（#6B655A）、2px 透明下线；选中态照搬顶栏导航激活态——墨色字（#1C1A17）+ 浅柿底（#FBEDE6）+ 2px 柿色下线（#C2410C）。全部规则包在 `@media (max-width: 768px)` 里，桌面三栏不受影响。
- 测试：`tests/test_design_v113.py` 2 例（设计层引用与 served、切换栏三选择器、无渐变、无 !important、无桌面 .app-shell 覆盖、六个报纸 token 齐全）；v112 设计测试 3 例同跑，全量 5/5 通过。
- 视觉验收：真实服务（18312 端口，种子数据）+ Playwright 390px 截图亲眼核对两张——订阅态（订阅钮浅柿底 + 柿色下线、真实订阅树）与文章态（文章钮激活、真实文章列表），计算样式与规则一一对上；README 移动端门面图换成新文章态截图，订阅态另存 `docs/screenshots/reader-mobile-tree.png`。冒烟服务与演示库已删，截图脚本在 muse-build/shot/ff-v113-shot.js。

### 本轮已知限制
- 390px 下顶栏导航仍横向溢出（今日必读/聚类 Top 被截断），属既有问题，本轮只动切换栏，未动顶栏。
- 阅读器空态仍是功能性提示，未做成导览页（v1.12.0 已知限制，留待下轮）。

## v1.12.0 — 2026-10-25

### 新增
- 按簇标记已读：新增 POST /api/clusters/<cluster_id>/read，整簇未读文章一次标已读，返回 {"cluster_id": ..., "updated": ...}；solo 单篇（cluster_id 为 NULL）按自身 id 命中；已全部已读时 updated 为 0 且仍返回 200（幂等）；scope 可选 unread/starred/all，非法 scope 返回 400，不存在的簇返回 404。
- 聚类 Top 页（/digest/clusters）每张卡片新增“本簇标已读”按钮，点后整簇标已读并刷新页面。
- store 层新增 mark_cluster_read 与 cluster_exists（与 mark_all_read 一致，不写 last_read_at）。
- 测试：tests/test_cluster_mark_read.py（store 层 4 例 + API 层 5 例）。

### 已知限制
- 批量标记已读不写 last_read_at，与既有 mark_all_read 行为一致；Fever 的 unread_recently_read 仍以单篇 set_read 记录的时间为准。
- 本版关闭 v1.11.0 已知限制之外的独立缺口，不改动单用户密码门与登录锁定行为。

### 前端美化（设计层，不改功能与后端）
- 新增 `feedflow/static/css/design-v112.css`，base.html 在原 style.css 之后引用；原样式表不动。
  视觉逻辑“编辑室报纸”见 `docs/DESIGN.md`：纸面底、墨色正文、柿色单主色、细线分隔、左对齐、纯色无渐变。
- 顶栏高 60px，品牌前 10px 柿色方块，导航激活态浅柿底加底部 2px 柿色线，搜索框宽 240px、左内边距 32px 避开图标。
- 阅读器：订阅树底栏顶部细线、纸色底、始终可见；原样式表里根本没有 `.list-bar` 规则，本层补置顶白底列表栏；
  文章选中态浅柿底加左侧 3px 柿色线——此前 `openArticle` 只去未读、不加 active，选中态规则实际从未触发，本轮在 app.js 里补了 active 切换。
- 列表星标：字符 ★ 换成同色 12px SVG 星（app.js 列表渲染处；阅读区按钮文字星标未动）。
- 摘要：序号衬线 20px 柿色，标题 18px，理由 chip 米灰底；统计：卡片顶部内阴影 3px 柿色线。
- 模型稿编排修正（逐项核对后改，未照抄）：删模型稿 `.app-shell` flex 覆盖（原为 grid 三栏，会破坏三栏）、
  品牌字号回 18px、评分卡恢复 3px 柿色左线（border 简写会覆盖它）、摘要容器加 max-width/box-sizing 防窄屏溢出。
- 测试：`tests/test_design_v112.py` 3 例（设计层引用与 served、关键选择器、无渐变、无 app-shell 规则、列表星标为 SVG、打开文章加 active）。
- 视觉验收：真实服务（8312 端口，种子数据）+ Playwright 截图亲眼核对三张——阅读器空态、已打开文章（选中项浅柿底、评分卡柿色条）、
  今日必读（序号柿色衬线）；README 门面 reader.png/digest.png 换成新截图。冒烟服务与演示库已删，截图脚本在 muse-build/shot/feedflow-v112-shot.js。

### 本轮已知限制
- 阅读器空态仍是功能性提示，未做成导览页；移动端三栏切换样式未动。

## v1.11.0 — 2026-10-25

### 新增
- 登录失败锁定：密码门开启后，按客户端 IP 内存计数，默认窗口 15 分钟内连续失败 5 次即锁定 15 分钟；达到阈值的当次失败与锁定期间的提交（含正确密码）回 429 + "尝试次数过多，请稍后再试" + Retry-After 头；成功登录清零该 IP 计数；未达阈值的失败仍回 200 + "密码不正确"。可调环境变量：FEEDFLOW_AUTH_MAX_ATTEMPTS（默认 5）、FEEDFLOW_AUTH_LOCK_MINUTES（默认 15）、FEEDFLOW_AUTH_WINDOW_MINUTES（默认 15），非法值启动 fail-fast。
- 测试：tests/test_auth_lockout.py（锁模块单元 5 例：阈值/成功清零/窗口重置/锁定过期/非法参数；HTTP 集成 4 例：阈值锁定、成功清零、默认阈值 5 次、配置校验 fail-fast）。

### 已知限制
- 锁定计数只存内存，进程重启清零，单进程有效；反代后所有请求同 IP 时共享计数（与 HTTP 限流同款限制）；仍为单用户单密码，无多用户；登出支持 GET；会话 cookie 未设 Secure。
- 本版关闭 v1.10.0 已知限制中的"无登录失败锁定"一项。

## v1.10.0 — 2026-10-24

### 新增
- 可选单用户密码门：默认关闭，不设密码相关环境变量时行为与旧版完全一致；设 `FEEDFLOW_AUTH_PASSWORD_HASH`（推荐，werkzeug 哈希）或 `FEEDFLOW_AUTH_PASSWORD`（启动时当场哈希，不落盘）即开启，开启时必须同时设 `FEEDFLOW_SECRET_KEY`，否则启动 fail-fast 退出。门禁覆盖全部 Web 页与 `/api/*`（登录会话），放行 `/healthz`、`/metrics`、`/login`、`/logout`、`/static/*`、`/fever/*`；Fever 仍用自己的 api_key 鉴权；`feed.xml` 需登录会话，RSS 阅读器请走 Fever。登录失败重渲提示“密码不正确”；next 只接受站内相对路径。
- 登录页（`/login`）与顶栏退出入口（登录后显示）；登出 `/logout`（GET/POST 均可）。
- 测试：`tests/test_auth.py` 8 例（默认关闭行为、门禁 401/302、探针放行、登录登出全流程、next 站外跳转拦截、配置 fail-fast）。

### 已知限制
- 单用户单密码，无多用户、无登录失败锁定（防爆破只靠 HTTP 限流）；登出支持 GET；会话 cookie 未设 Secure。

## v1.9.1 — 2026-10-24

### 技术债清理
- `requirements.txt` 钉版本：`pytest==9.1.1`、`ruff==0.17.0`（2026-10-23 轮记录的"ruff 未钉版本"技术债关闭）。
- ruff 0.17.0 全量问题清零：从 197 处降到 0（`ruff check` 全洁）。143 处走 ruff 安全自动修复（未使用 import/导入排序/PEP585 注解/datetime.timezone.utc 等）；剩余 59 处机械修复：UP031 printf→f-string（28）、ISC004 隐式拼接合并（5）、RUF059 未使用解包变量改 `_` 前缀（9）、F841 未使用局部变量改 `_` 前缀（2）、PERF102 只用值时改 `.values()`（2）、RUF015 单元素切片改 `next()`（2）、FURB192 `sorted()[-1]` 改 `max()`（1）、BLE001 三处确为意图内全捕获加 `noqa` 注释（2 脚本+1 线程错误收集）、PLR0124 `x != x` 改 `math.isnan`（1）、PLW1510 subprocess 显式 `check=False`（1）、RUF012 可变类属性默认值加 `ClassVar` 注解（1）、EXE001 两脚本加执行位（2）。语义零改动，pytest 全量通过。
- `scripts/loadtest.py` / `scripts/loadtest_phase6.py` 加执行位（shebang 与权限对齐）。

## v1.9.0 — 2026-10-23

### 新增
- 阅读器文章详情区新增"为什么排前面"评分卡片：打开文章后按需拉取 `GET /api/articles/<id>/score`（v1.8 端点），展示重要性总分、时效 / 事件热度 / 来源权重 / 关键词 / 未读加成五个因子条、大白话理由列表与发布时间小字；后端请求失败时卡片静默消失，不影响阅读。旧报纸视觉（纸白底、柿色左侧竖线、左对齐），去 AI 味约束延续。
- `tests/test_article_score_api.py`（8 例）：v1.8 评分端点的 HTTP 契约测试——响应形状、五因子 0~1 有界、已读文章未读因子为 0、多成员簇 cluster_size、与 `ranking.score_article` 纯函数一致性、404。

### 文档
- README"快速开始"补全：安装 / 运行 / 手动抓取 / 测试 / Docker 一把梭，含默认监听 127.0.0.1:8300 与./data 持久化说明（2026-10-16 v1.6 发版报告遗留项关闭）。

## v1.8.0 — 2026-10-22

### 新增
- 排序可解释性端点：`GET /api/articles/<id>/score` 返回单篇文章的重要性评分与五个因子的得分明细（`score`/`parts`[heat/keyword/recency/source/unread]/`reasons`/`cluster_size`/`age_hours`），文章不存在返回 404。真实服务冒烟验证通过。

## v1.7.0 — 2026-10-20

### 新增
- 新增“聚类 Top”视图（`/digest/clusters`）：去重聚类后的 Top N 事件卡片流，每卡片展示聚类主题、来源数、来源标题（至多 5 个）、重要性分（可解释，拆出 `cluster_score` 计算依据）、每篇成员的 `score_info`、“还有 N 篇已折叠”。导航栏新增“聚类 Top”入口。
- 新增 `ranking.get_digest_clusters(db_path, n=10, now=None)`：未读文章经 `rank_articles` 排序后按 `cluster_id` 分组（NULL `cluster_id` 各自成 solo 组），返回 `cluster_id`/`topic`/`members`/`sources`/`source_titles`/`unread`/`representative`（含 `score_info`）/`cluster_score`/`cluster_reasons`/`latest_at`。
- 种子数据加 `CLUSTER_DEMO`（3 事件 x 3 来源=9 篇，验证真实聚类 3 簇 x 3 篇）。

### 修复
- 修复阅读器 `app.js` 与 CSS 类名失配（`renderItem` 吐 `art-title`/`art-meta`/裸星号，CSS 写的是 `.title`/`.meta`/`.star`）：改回 `title`/`meta`/`<span class="star">`，未读加粗+红点+星标着色恢复。

### 测试
- 新增 `tests/test_digest_clusters.py`（9 例）、`tests/test_digest_clusters_page.py`（6 例）；本轮 pytest 全绿（3 个 flaky 失败已修：`rank_articles` 签名、`read_at` 列不存在、NULL 分组契约）。


## v1.6.1 — 2026-10-17

### 修复

- 修 PUT /api/folders/<id> 历史 bug（v1.6 遗留）：处理器调用的 store.get_folder 与 store.update_folder_position 根本不存在，导致改分组名/排序直接 500。补上 feedflow/store.py 的 get_folder(db_path, folder_id)（无则 None，返回 {id,name,position,unread}，形状与 list_folders 一致）与 update_folder_position（直接设置 position）；api.py 行为契约未动。
- 回归测试 tests/test_folders_put.py（7 例：改名、调序、404、空名 400、非法 position 400、名+序同改、404 无副作用）；pytest 136/136 全绿。

## v1.6 — 2026-10-16

### 新增

- 阅读器键盘快捷键：`j`/`k` 上下篇、`o` 新标签页打开原文、`r` 标已读/未读、`s` 加星/取消星标、`?` 快捷键帮助浮层（`Esc` 关闭）；`m` 标已读/未读保留兼容。
- 阅读进度记忆：滚动位置按文章持久化到 SQLite（`articles.scroll_pos`，DB 迁移 v4），重进文章自动恢复到上次读到的位置；新增 `POST /api/articles/<id>/progress` 接口。
- OPML 导出加固：标题/网址为 None 的脏数据不再导致导出 500；head 新增 `dateCreated`；分组嵌套与未分组直挂结构保持 OPML 2.0 标准形态。
- tests/test_progress.py（8 例）与 tests/test_opml.py 新增 6 例。

测试：pytest 129 例全过、ruff 全洁。

## v1.5.1 — 2026-10-16


### 变更

- 依赖升级：trafilatura 2.2.0 → 2.3.1。2.3.1 是当前 PyPI 上的最新版本；上游 2.3.0 的发版说明里写了没有破坏性变更，主要是下载和解压部分的代码重构、文档处理逻辑的简化。本地 venv 里换成 2.3.1 后跑了一遍测试，pytest 115/115 全过。

## v1.5 — 2026-10-16

### 新增

- 全文 RSS 输出：`GET /feed.xml`，正文优先用抓取时 trafilatura 提取的 content_text，无正文时回落摘要去标签文本；支持 `?feed_id=` / `?folder=` 过滤，最多 50 篇；ETag + If-None-Match 304 缓存。
- HTTP 层 IP 限流：内存令牌桶，默认 60 req/min（`FEEDFLOW_RATE_LIMIT_RPS=1.0` + `FEEDFLOW_RATE_LIMIT_BURST=60`），超限 429 + Retry-After；`/healthz` 与 `/metrics` 免限流；Prometheus 新增 `feedflow_http_rate_limited_total`；开关 `FEEDFLOW_RATE_LIMIT_ENABLED`。
- tests/test_feedxml.py（8 例）与 tests/test_ratelimit.py（5 例）；运维手册新增第 9 节"限流调参"。

## v1.4 — 2026-10-16

### 新增

- Prometheus 指标（`GET /metrics`，9 个指标系列）。
- 失败注入测试。
- 运维手册补全，共 8 章。
- Fever 运维章节。
- 移动端阅读优化。

### 修复

- 纠正 `docs/OPERATIONS.md` 中环境变量默认值错误。

测试：pytest 102 例全过（新增 18：指标 6 + 失败注入 12）、ruff 全洁。

## v1.3 — 2026-10-15

### 新增
- Fever API 兼容：第三方 RSS 客户端（Reeder、Unread 等支持 Fever 协议的）可以直接连 FeedFlow 同步订阅、文章和已读/星标状态。接口挂载在 `/fever/`，鉴权用 POST 提交的 `api_key`（md5(邮箱:密码) 十六进制），用 `feedflow fever-key` 命令生成后写入环境变量 `FEEDFLOW_FEVER_API_KEY` 启用。支持 groups/feeds/favicons/items（since_id/max_id/with_ids 分页，各 50 篇封顶）/unread_item_ids/saved_item_ids 读取，以及单篇标记已读/星标、按源/按组标记已读（需 before 时间戳）、unread_recently_read 写操作。未实现 favicon 抓取，返回 1x1 透明占位图；无 spark 概念，is_spark 恒为 0；未分组的源归入 group 0。
- 正文提取超时收敛：新增环境变量 `FEEDFLOW_EXTRACT_TIMEOUT`（默认 15 秒），单篇卡住的文章页不再拖慢整个源的抓取，超时自动回落用 RSS 摘要。
- 新增 `feedflow fever-key` 命令：交互式输入邮箱和密码（密码不回显），输出可直接用的 api_key。
- 新增 tests/test_fever.py（22 个用例），覆盖鉴权、分组/源/文章读取、分页、已读/星标/分组标记、unread_recently_read 及参数校验。

### 改进
- `store.set_read` 标记已读时同步记录 `last_read_at`（迁移 v3 新增列），供 Fever 的 unread_recently_read 使用。

## v1.2 — 2026-10-13

### 新增
- 新增重要性排序：综合时效衰减（半衰期 48 小时）、事件热度（同簇文章数）、来源权重（手动权重 × 按已读/星标学习）、关键词命中、未读加成五个维度加权算分，让真正重要的文章排前面。
- 新增「今日必读」页（/digest）：直接看当天最值得读的 N 篇，每篇都能展开分数明细，一眼看懂"为什么排前面"。
- 新增兴趣设置页（/settings/interests）：可以增删关键词、手动调来源权重、设置每日篇数 N。
- 数据库迁移到 v2：新增 keywords、feed_weights、settings 三张表。
- 新增环境变量 FEEDFLOW_DIGEST_N，用来控制「今日必读」默认篇数，默认 20。
- 新增 tests/test_ranking.py，共 16 个测试用例覆盖排序逻辑。

### 改进
- 排序分数支持拆解展示，不再是黑盒。

## v1.1 — 2026-10-13

### 新增
- 抓取支持重试和失败分类，网络抖动或源站报错时不再一挂到底。
- 调度状态持久化，重启后不会丢抓取计划。
- 新增结构化日志，排查问题更方便。
- 新增 /healthz 健康检查接口。
- 新增备份恢复 CLI，数据可以备份和还原。
- 新增 SimHash + Jaccard 去重聚类，重复文章折叠显示，不再刷屏。

### 改进
- 视觉返工：改成三栏全幅布局，阅读区更宽敞。
- 演示数据改成真实命名，看起来不再像占位符。
- 搜索页短词改走 LIKE，避免 FTS5 对短词不生效的问题。

### 修复
- 修复阅读管理页分组列的竞态问题。
- 修复搜索页模板变量错误。

## v1.0 — 2026-10-13

### 新增
- 首个可用版本。
- 订阅管理：添加、编辑、删除订阅源。
- APScheduler 定时抓取，自动拉取新文章。
- trafilatura 正文提取，尽量还原干净的文章内容。
- 三栏阅读器，左边订阅、中间列表、右边正文。
- FTS5 全文搜索，快速找到看过的文章。
- OPML 导入导出，方便迁移订阅。
- 统计页，查看订阅和阅读情况。
