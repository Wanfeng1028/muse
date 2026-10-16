```markdown
# Changelog
```

## v0.11.0（2026-10-17）——搜索质量 T1/T2 修复

- T1 修复（`src/jieba_tokenizer.cpp`）：`jiebaXTokenize` 的单调游标 `find` 在 CutForSearch 重叠词下静默丢词（如"计算机技术"丢算机/计算机/计算机技术、"计算机算机维修"连"维修"都被级联丢失）。改为"全文 occurrence 扫描 + 已认领集合"：每个词独立定位，`(词, 起始字节)` 去重，不同词允许同位置重叠；归一化回退路径保留。
- T2 修复（动查询侧，不动索引侧）：`Searcher::search` 新增第 3 阶段"子串召回回退"——中文 token 拆单字 OR 粗筛（跳过单字停用词）+ 按原始 token 逐个子串精验（ASCII 大小写不敏感），只保留原文确实连续包含每个查询 token 的文档；只在精确 AND、OR 回退都为空时触发，不影响已有查询。`search 猫砂` 现可命中含"猫砂盆"的文档（之前无结果）。
- 查询构造修正（`src/searcher.cpp` 新增 `expandTokenOrQuery`）：单个查询词的 CutForSearch 结果按起始字节位置分组，同一起始位置的重叠词 OR（如"咖啡豆"→`("咖啡" OR "咖啡豆")`，单个引号串会被 FTS5 当成要求相邻的短语而恒为 0），不同位置顺序 AND；`buildMatchQuery` 连接符由空格改为显式 ` AND `（FTS5 括号 OR 组与引号串隐式相邻会报 syntax error）。
- `isSingleCharStopword` 从 `query_parser.cpp` 暴露到头文件供查询展开复用。
- 测试：新增 3 个先红后绿的复现测试（`TokenizerT1.DuplicateWordNotLost` / `TokenizerT1.OverlappingWordNotLost` / `SearchT2.SubstringQueryRecall`，断言走 fts5vocab 直接读索引）；ctest 除已知 flaky（WatcherTest.SubDir，inotify 时序，v0.5.0 已有）外全绿。
- 评测：语料 42→44 篇、评测对 44→56（新增 12 对：6 T1 + 6 T2，其中 5 对已在修复前验证为 FAIL 的真回归对），Top-1 从基线 36/44（81.8%）到 **48/56（85.7%）**；8 个失败与基线同一集合（qa 自然语言问句，独立已知问题）。
- 已知限制：T2 要求查询 token 在文档中连续出现（语义级子串不在本轮范围）；单字 OR 粗筛极端情况下候选集可能较大（未压测）；qa 4/12 未改善；`service.cpp` 的版本字面量仍为 0.9.0（v0.10.0 遗留待办）。
- 版本号 0.11.0（`--version` / 服务启动日志）；发版对照报告：`docs/PRODUCTION_CHECKLIST_REPORT_v0.11.md`。

## v0.10.0（2026-10-17）——多用户支持

- 多用户：`database.h` 新增 `kDefaultUser = "local"` 与 `checkUserValid`（非法 user 抛 `std::runtime_error`）；`Document` 新增 `user` 字段。
- 多用户：`upsert` / `removeByPath` / `list` / `findByPath` / `searchFts` / `docCount` / `totalBytes` 全部新增 `user` 参数（默认 `kDefaultUser`），保持旧调用兼容。
- 多用户：新增 `removeByUser(user)`，删除该用户全部文档并返回删除条数；用户不存在返回 0，不抛异常。
- Schema：v3 → v4，`documents` 表新增 `user` 列；老库自动迁移，旧数据统一归属 `local`。
- 测试：新增 6 例多用户测试全过（用户隔离、同路径多版本、检索隔离、`removeByUser`、`checkUserValid` 校验、默认用户），ctest 全过。
- Bugfix：`DocxExtractor` 页眉页脚判断 `n.compare(0, 12, "word/header")` 恒为假（11 字符前缀误比 12 位），已修正为 11，`OfficeDocxTest.ExtractChineseTableHeader` 通过。
- Bugfix：`TokenizerTest.MigrateOldSchema` 期望版本由 3 更新为 4（过时断言），已同步 schema v4。

## v0.9.0（2026-10-16）——Office 文档文本提取

- 新增 `office_extractor` 模块：纯自研 zip 解析（central directory + local file header，支持 stored/deflated，防 zip bomb 上限）+ 系统 zlib 解压（zlib license，非 GPL），零第三方 zip 库、零 GPL 污染；选型见 `docs/OFFICE_EXTRACTION_SELECTION.md`。
- `DocxExtractor`：提取 `word/document.xml` 的 `w:t` 文本（段落换行、表格、XML 实体解码、`xml:space="preserve"`），附带 `word/header*.xml` / `word/footer*.xml`。
- `XlsxExtractor`：解析 `xl/workbook.xml` + rels 得工作表顺序与表名，`xl/sharedStrings.xml` 查表；单元格支持共享字符串/数字/公式字符串/inlineStr；输出按工作表分组（`[工作表:表名]` + 行文本，保留"表名:行"定位信息）。
- `PptxExtractor`：按 `ppt/presentation.xml` 放映顺序（经 rels 解析，缺失时诚实降级为文件名数字排序）提取各 `slideN.xml` 的 `a:t` 文本，输出 `[第 N 页]` + 页文本、页间换页符分隔。
- `Indexer`：默认扩展名加入 `.docx`/`.xlsx`/`.pptx`；Office 二进制不再误判跳过；损坏文件只记 error 不中断整批；无文本跳过。
- 搜索结果文件类型标签新增 DOCX/XLSX/PPTX。
- 构建：`find_package(ZLIB REQUIRED)`，`docseek_core` 链接 `ZLIB::ZLIB`。
- 版本号 0.9.0（`--version` / `/api/health` / `/api/version`）。
- 测试：新增 test_office_docx / test_office_xlsx / test_office_pptx / test_office_index，fixture 全部由测试内手写 zip 构造器程序生成（含中文、表格、页眉、多工作表、乱序 sldId、损坏文件）。

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
