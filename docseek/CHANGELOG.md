```markdown
# Changelog

## v0.5.0（2026-10-15）——生产级补齐

- 结构化日志：stderr JSON Lines，`request_id` 全链路（`X-Request-Id` 响应头），`DOCSEEK_LOG_LEVEL` 控制级别。
- `GET /api/metrics`：查询量/延迟/Top 查询词/慢查询（阈值 `DOCSEEK_SLOW_MS`）/限流拒绝数。
- `backup` / `restore` 子命令：SQLite backup API 在线热备；恢复先校验有效性再原子替换（旧库 `-wal`/`-shm` 一并清理），垃圾文件拒绝（exit 2）。
- `/api/locate` 并发限流：默认 4 并发，拿不到槽位超 `DOCSEEK_LOCATE_WAIT_MS` 回 429。
- 索引批量事务：`Database::beginBatch/commitBatch/abortBatch`（嵌套防护 + 异常回滚），`indexPaths` 每 500 文件提交一次；实测 1000 文件 6.8 秒（约 147 文件/秒，老基线 37 文件/秒）。
- cppjieba 词典加载噪音重定向到 `/dev/null`（`DOCSEEK_JIEBA_VERBOSE=1` 恢复）。
- Docker：运行镜像补拷词典（之前漏了，serve 起不来）；新增 `docker-compose.yml` 一键部署。
- 运维手册 `docs/OPERATIONS.md`；仓库级 `.github/dependabot.yml`（GitHub Actions 周检；CMake FetchContent 走季度人工检查）。
- 发版对照报告：`docs/PRODUCTION_CHECKLIST_REPORT_v0.5.0.md`；对照报告 13 项全部通过。
- 测试 62 例全过（含新增 tests/test_ops.cpp 14 例：日志/指标/备份恢复/失败注入/批量事务/并发守卫）。

## v0.4.0（2026-10-13）——自然语言定位原文

- 新增 `locate` 子命令：自然语言提问直达文件:行号锚点（`docseek locate "退款流程写在哪一段"`），终端输出带行号原文段落 + 命中词 ANSI 高亮，支持 `--json`。
- 新增 `GET /api/locate`：返回 `{query, keywords[], anchors[{doc_id,path,line_start,line_end,score,matched_terms[],text}]}`。
- Web UI 新增"自然语言定位"卡片（延续现有视觉系统）。
- 新增核心库：query_parser（中文疑问句规则解析 + jieba 关键词抽取）、passage_ranker（段落滑动窗口重排序 + 行号锚定）、locator（混合召回 → 段落重排）。
- Database 新增 `getContentById`；jieba 单例新增只读访问接口。
- 灵魂一页纸：docs/SOUL.md；发版对照报告：docs/PRODUCTION_CHECKLIST_REPORT_v0.4.0.md。
- 修 bug：web/index.html 的 `<script>` 自 v2 起被截断（`btn.dis`），导致整页 JS 失效；本轮补全并补上事件绑定与初始化。
- 测试 48 例全过（含新增 test_locate.cpp 9 例）。

## v0.3.0（2026-10-13）——真中文分词 + 混合检索 v1

- cppjieba（v5.6.2）FTS5 自定义分词器；旧库自动迁移（user_version 2→3）。
- 混合检索 v1：BM25 + AND→OR 回退 + 标题/短语加成。

## v0.2.0（2026-10-13）——serve 常驻服务 + Web UI + inotify 实时监控

## v0.1.0（2026-10-13）——CLI 初版（index/search/stats/prune）
```
