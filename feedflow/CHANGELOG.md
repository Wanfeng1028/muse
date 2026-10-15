# 更新日志

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
