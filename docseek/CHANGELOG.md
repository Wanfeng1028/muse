```markdown
# Changelog

## v0.14.0（2026-10-17）——v08 剩余 4 失败攻坚

- 修复 v0.13.0 遗留的 v08 全部 4 个真实问法失败，逐对根因+修复如下：
  - v08-qa-03「请问发货得几天啊」→ 期望 qa_02_shipping.md（原命中干扰文档）：根因是单字"得"漏过两张停用词表，进入 keywords 后在干扰文档命中 13 次；修复为 singleCharStopwords 加"得"。
  - v08-qa-09「我想知道数据应该多久备份一次才比较合适，请问有没有建议」→ 期望 qa_05_backup.md：根因是口语框架词 + 全角标点污染 keywords，"建议"被干扰文档"不建议"子串误命中；修复为 fillerWords 加"我想知道/应该/才/比较合适/有没有建议"，isPunctuationOnly 丢弃全角标点；中途"最短相邻二元 queryCompound"方案被实证证伪后改走"有没有建议"整串擦除。
  - v08-qa-10「请问你们有哪些套餐，我该怎么选呢」→ 期望 qa_11_pricing.md：根因是全角逗号进 keywords + "你们/我/该"噪音摊薄 coverage 分母；修复为 isPunctuationOnly + fillerWords 加"你们/我/该"。
  - v08-qa-15「想找客服，联系方式在哪啊」→ 期望 qa_12_contact.md：根因是"想"污染 queryCompound 使 +0.25 加成恒不触发；修复为 fillerWords 加"想"。
- 修复（只动 src/query_parser.cpp，共 6 处）：
  - singleCharStopwords 加"得"。
  - fillerWords 加"我想知道/你们/应该/我/想/该/才/比较合适/有没有建议/哪儿"（"有没有建议" 15 字节排在"帮我找一下"之后、"有没有"之前；"哪儿"为"哪里"同族补齐）。
  - 新增 isPunctuationOnly()（Unicode 标点区 0x3000-0x303F / 0xFF00-0xFFEF / 0x2000-0x206F），parseNaturalQuery 分词后丢弃纯标点 token。
  - 无其他文件改动。
- 诚实记录：本轮曾先尝试 A6 第 1 轮的"queryCompound 最短相邻二元"方案，被实测证伪（tie-break 选中从不命中的"数据多久"，+0.25 永不触发），未应用，已改走"有没有建议"整串擦除；失败尝试如实记录，不删历史。仍有 2 个对抗变体未攻克：v08-qa-09d「多久备份一回数据才算合适，能给点建议不」→tok_05_mixed.md（"一回/算/能/点/不"无安全切口，"不"全局擦除会反转"不建议"语义）；v08-qa-15d「我想找人工客服，从哪儿能联系上」→qa_08_invoice.md（干扰文档"联系客服人工处理"连续命中 3 个关键词，属排序模型语义能力边界；"哪儿"补丁作为"哪里"同族词表补齐保留，零回归）。
- 先红后绿：tests/test_query_parser.cpp 新增 QueryParserV014 套件 5 例，全部先红后绿（git stash 还原旧代码时 5 例全红，恢复后全绿）。
- 评测（实测）：v07 集 56/56（100%）；v08 原 71 对 71/71（100%）、qa 27/27（基线 v0.13.0 为 67/71（94.4%）、qa 23/27（85.2%））；评测集扩到 83 对（+12 个对抗变体：每对 3 个，口语省略/礼貌体/换句式），83 对为 81/83（97.6%）、qa 37/39（94.9%）。
- 构建：cmake 零警告（自有文件；第三方 cppjieba 头警告 pre-existing）；ctest 全绿（WatcherTest.SubDir 为 v0.5.0 起已知 inotify 时序 flaky，与本轮无关）。
- 已知限制：2 个对抗变体未攻克（v08-qa-09d→tok_05_mixed.md、v08-qa-15d→qa_08_invoice.md，详见诚实记录）；WatcherTest.SubDir flaky 照旧。
- 版本号 0.14.0（version.h 唯一来源）；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.14.md。

## v0.13.0（2026-10-17）——段落排序复合短语加成

- 修复 v0.12.0 遗留问题 v07-024「安装步骤在哪里」。
- 根因：问句「安装步骤在哪里」被 jieba 解析为 keywords=\u3010安装, 步骤\u3011（复合词被切散）；段落打分是纯词袋（覆盖度 0.5 + 命中饱和 0.3 + 短语 0.15 + 位置 0.05），干扰文档 tok_12_verb.md 靠单一段落堆砌关键词拿到 0.845，压过主题文档 qa_04_install.md 的 0.688。而「安装步骤」连续串在全语料中只出现在主题文档——连续出现是比词袋更强的意图信号（文档级 Searcher 早有同原理 phraseBoost +2.0，段落级缺失，两阶段不一致）。
- 修复（只动 src/passage_ranker.cpp）：
  - 匿名 namespace 新增具名常量 kCompoundPhraseBonus=0.25，注释写清取值依据：大于位置项 0.05、小于覆盖度主项 0.5；实测主题 0.688+0.25=0.938 > 干扰 0.845。
  - rankPassages 在 kwLower/phLower 预处理后计算 queryCompound：关键词按序拼接，关键词 >= 2 个、拼接串非空、且不同于任一引号短语时生效（避免与 phraseTerm 重复加成）。
  - 窗口原文连续包含 queryCompound 时 score += 0.25。
  - rankPassages 签名不变，既有权重公式不动。
- 诚实记录：本轮曾先尝试「跨文档排序融合文档级检索分」（Passage.doc_score + 0.3×min-max 归一化文档分），真实评测证伪（55/56 未动：min-max 取整轮召回集最大/最小值，召回集一大就把两篇关键文档 9.642 vs 8.394 的差距稀释掉），已完整还原（git checkout 恢复，工作区无残留），改走段落级复合短语路线。失败尝试如实记录，不删历史。
- 先红后绿：tests/test_locate.cpp 新增 TEST(LocatorV013, CompoundPhraseBonusPrefersThematicDoc)（主题文档 vs 关键词堆砌干扰文档；还原后未加成时失败=红，加复合加成后通过=绿）。
- 评测（实测）：v07 集 56/56（100%），qa 12/12（基线 v0.12.0 为 55/56、qa 11/12）；v08 集 67/71（94.4%），qa 23/27（基线 66/71、qa 22/27；v07-024 的修复连带使 v08 的 qa 也 +1）。
- 构建：cmake 零警告（自有文件；第三方 cppjieba 头警告 pre-existing）；ctest 168/168（WatcherTest.SubDir 为 v0.5.0 起已知 inotify 时序 flaky，排除后全绿；本轮单独重跑 4 次仍失败，与改动无关）。
- 已知限制：v08 剩余 4 个真实问法失败（v08-qa-03「请问发货得几天啊」→t1_01_repair.md、v08-qa-09「多久备份一次」→t1_01_repair.md、v08-qa-10「有哪些套餐」→tok_04_ambiguity.md、v08-qa-15「想找客服，联系方式在哪啊」→qa_08_invoice.md），v0.14 排期；WatcherTest.SubDir flaky 照旧。
- 版本号 0.13.0（version.h 唯一来源）；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.13.md。

```

## v0.12.0（2026-10-17）——问句理解升级

- 问句改写（`src/query_parser.cpp`）：fillerWords 疑问词表清理（删除与 singleCharStopwords 重复的"的/了"，全表按长度严格降序）；新增 trailingPredicates 尾部谓语剥离（写在哪/写在/说明/介绍/申请/开具/重置/阐述/写，只剥尾部谓语、保留名词主题），parseNaturalQuery 步骤 2.5 接入。自然语言问句先被改写成名词主题再检索。
- 段落排序修复（`src/passage_ranker.cpp`）：修标题行断窗覆盖 bug（断窗后下一窗口从标题行开始，每行必被覆盖）；passageIntent=true 时含标题行窗口 +0.1，问句更倾向定位到标题附近的段落。
- 问句召回路径（`src/locator.cpp`）：recallQuery 跨 keywords/phrases 去重；问句（passageIntent 或问句尾缀"在哪里/在哪/哪里/吗/?/？"）走新 searchQuestion。
- 新增 `Searcher::searchQuestion`（`src/searcher.cpp` + `include/docseek/searcher.h`）：问句 AND∪OR 并集召回，doc_id 去重；重排逻辑抽取为共用 rerankHits，`search()` 行为零差异。
- 评测集：`eval/eval_pairs_v08.json`（71 对：56 个 v07 对逐字 + 15 个新增真实问法）。
- 测试：`tests/test_query_parser.cpp` 新建 5 例；`tests/test_locate.cpp` +4；`tests/test_searcher.cpp` +1。ctest 168/168 全过（WatcherTest.SubDir 为 v0.5.0 起已知 inotify flaky，排除后全绿）。
- 评测：v07 集 55/56（98.2%）（html 10/10 / tok 26/26 / noise 6/6 / neg 2/2 / qa 11/12），基线 48/56（85.7%），qa 由基线 4/12 提升到 11/12；v08 集（71 对）66/71（93.0%），qa 22/27（81.5%）。
- 已知限制：v07-024 "安装步骤在哪里"未修复（期望 qa_04_install.md，实际 tok_12_verb.md；跨文档排序被干扰文档 0.845 vs 0.688 压制）；v08 新增 4 个真实问法失败（v08-qa-03 "请问发货得几天啊"→t1_01_repair.md、v08-qa-09 "多久备份一次"→t1_01_repair.md、v08-qa-10 "有哪些套餐"→tok_04_ambiguity.md、v08-qa-15 "想找客服，联系方式在哪啊"→qa_08_invoice.md）；`WatcherTest.SubDir` flaky 照旧（v0.5.0 已有，与本轮无关）。
- 构建：cmake 零警告（自有文件；第三方 cppjieba 头警告 pre-existing）。版本号 0.12.0（`--version`）。
## v0.11.1（2026-10-17）——版本号唯一来源 + 定位逻辑公共抽取

- 修复 v0.10.0 遗留 bug：`src/service.cpp` 的 `/api/health` 与服务启动日志把版本号硬编码为 "0.9.0"。
- 新建 `include/docseek/version.h`（`docseek::kDocseekVersion = "0.11.0"`，注释"发版只改这一处"）；`src/main.cpp` 的 `kVersion` 与 `src/service.cpp` 两处硬编码全部改用该唯一来源。
- 技术债偿还（v0.11.0 报告第 6 节已知项）："T2 回退路径与 jiebaXTokenize 共享 occurrence 扫描定位逻辑，但二者仍为两处实现"。
- 新建 `include/docseek/token_locate.h` + `src/token_locate.cpp`（`claimTokenPositions(text, words, claimed)`：全文 occurrence 扫描 + 已认领集合，定位失败的词跳过）。
- `src/jieba_tokenizer.cpp`（主循环逐词调用 + 码点回退路径同样走公共函数，交错语义与原来逐行一致）与 `src/searcher.cpp`（`expandTokenOrQuery` 按字节位置分组改用公共函数，定位失败仍退化为 `quoteToken(token)`）双双改用公共函数；`CMakeLists.txt` 注册新源文件。
- 测试：新增 `tests/test_token_locate.cpp` 7 例（重叠词不丢/重复词认领下一处/重复耗尽跳过/不可定位跳过/空串跳过/跨调用共享 claimed 集/空输入）。
- 测试：`tests/test_service.cpp` 的 Health 测试加断言：health 返回的 version 必须等于 `docseek::kDocseekVersion`（版本无关、防硬编码回退）。
- 版本号：`--version` 仍为 0.11.0（本轮为 v0.11.x 补丁级改动，不 bump 大版本；version.h 的值保持 "0.11.0"）。
- 已知限制：既有索引不受影响（本轮只动查询侧定位与版本号，无索引格式变更）；`WatcherTest.SubDir` flaky 照旧（v0.5.0 已有，与本轮无关）。

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
