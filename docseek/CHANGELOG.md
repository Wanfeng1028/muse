```markdown
# Changelog

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
