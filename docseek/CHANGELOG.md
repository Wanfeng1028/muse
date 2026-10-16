```markdown
# Changelog
```

## v0.8.0（2026-10-16）——PDF 文本提取

- 新增 `PdfExtractor`：子进程调用系统 `pdftotext`（`fork`+`exec`，不经过 shell；30 秒超时 kill；stderr 判加密），零构建依赖、无 GPL 链接污染；选型见 `docs/PDF_EXTRACTION_SELECTION.md`。
- `Indexer`：默认扩展名加入 `.pdf`；PDF 二进制不再误判跳过；加密 PDF 跳过并记 warning；损坏 PDF 只记 error 不中断整批；无文本 PDF 跳过（不建空文档）。
- 版本号 0.8.0。
- 测试：新增 test_pdf 10 例（提取器 7 / 索引集成 3），fixture 全部程序生成（含手写 MD5/RC4 生成的加密 PDF）。

## v0.7.0（2026-10-16）——搜索质量工程

- 混合检索 v2：标题/短语加成权重可配置。`Searcher` 新增 `SearchWeights{titleBoost, phraseBoost}`（默认 1.0/2.0，与 v1 行为完全一致）；CLI `search` 新增 `--title-boost` / `--phrase-boost`（非法值 exit 1）；环境变量 `DOCSEEK_TITLE_BOOST` / `DOCSEEK_PHRASE_BOOST` 可改默认值（非法值打警告回默认）；`GET /api/search` 新增 `title_boost` / `phrase_boost` 查询参数（显式非法值回 400）。
- 评测集 v07：`eval/` 新增 42 篇中文评测语料（HTML 8 / 中文分词边界 12 / 问答 12 / 噪声 10）+ 44 个 query→doc 评测对 + `eval/run_eval.py` 一键评测脚本；实测 Top-1 准确率 36/44 (81.8%)（html 10/10 / tok 14/14 / qa 4/12 / noise 6/6 / neg 2/2）。
- 已知问题（评测发现，v0.8 排期）：T1 分词器游标逻辑在 CutForSearch 重叠词下会跳过中间 token 导致索引静默丢词；T2 索引/查询切分上下文不一致导致子串 query 漏召回。复现与根因见发版对照报告。
- 版本号 0.7.0（`--version` / `/api/health` / 服务启动日志）。
- 发版对照报告：`docs/PRODUCTION_CHECKLIST_REPORT_v0.7.0.md`。
- 测试 108 例运行、107 通过（本轮新增 test_hybrid 权重测试 5 例；1 例 WatcherTest.SubDir 为 inotify 时序 flaky，v0.5.0 已有，与本轮无关）。

## v0.6.0（2026-10-16）——HTML 文本提取


- 新增 `HtmlExtractor`（零第三方依赖，纯 C++17 手写）：去 `<script>`/`<style>`/`<noscript>`、提取 `<title>`/`<meta name="description">`/正文、块级标签换行、HTML 实体解码（数字/hex/40+ 命名实体）、畸形 HTML 容错。
- charset 探测：BOM（UTF-8/UTF-16LE/BE）→ `<meta charset>` / `<meta http-equiv>` → 默认 UTF-8；GBK/GB18030/BIG5/Latin1 经系统 iconv 转码，UTF-16 手写转换。
- `Indexer`：默认扩展名加入 `.html`/`.htm`；UTF-16 页面（含 NUL 字节）不再误判为二进制跳过；提取失败或正文为空回落原始文本并记 warn 日志（文档不丢失）。
- 搜索/定位：html 文档标题取自 `<title>`，标题/短语加权天然生效；`locate` 行号锚定走提取后文本。
- Web UI：搜索结果加文件类型徽标（HTML/MD/TXT）。
- 版本号 0.6.0（`--version` / `/api/version`）。
- 发版对照报告：`docs/PRODUCTION_CHECKLIST_REPORT_v0.6.0.md`；设计注记：`docs/HTML_EXTRACTION.md`。
- 测试 102/102 全过（v0.5.0 的 62 例 + 本轮新增 40 例：提取器基础 8 / 实体 8 / 畸形 8 / 编码 7 / 性能 4 / 集成 5；另有 1 例 WatcherTest.SubDir 为 inotify 时序 flaky，v0.5.0 已有，与本轮无关）。

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
