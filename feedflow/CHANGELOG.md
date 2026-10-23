
# 更新日志

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
