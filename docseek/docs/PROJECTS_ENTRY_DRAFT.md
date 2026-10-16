## 粘贴位置：→ 功能模块列表末尾追加

8. HTML 文本提取（v0.6.0）：索引 `.html`/`.htm` 时自动 charset 探测（BOM → `<meta>` → 默认 UTF-8，GBK/GB18030/BIG5 经 iconv 转码）→ 去 `<script>`/`<style>`/`<noscript>` → 提取 `<title>`（入库为文档标题，搜索标题加权生效）、`<meta name="description">` 与正文；提取失败回落原始文本并记 warn 日志；Web 搜索结果文件类型徽标（HTML/MD/TXT）

## 粘贴位置：→ 状态行末尾追加

工程化 v6「HTML 文本提取」（2026-10-16）：html_extractor 新模块（HtmlExtractor：extract/detectCharset/decodeToUtf8/extractFromBytes，零第三方依赖，iconv 为 glibc 系统调用）+ indexer.cpp 接入（默认扩展名加 .html/.htm；UTF-16 含 NUL 不再误判二进制；提取失败/正文空回落原始文本 + warn 日志）+ 40+ 命名实体解码 + 畸形 HTML 容错 + web/index.html 文件类型徽标 + 版本号 0.6.0；构建零警告、测试 102/102 全过（新增 40 例；另有 1 例 WatcherTest.SubDir 为 inotify 时序 flaky，v0.5.0 已有）；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.6.0.md；设计注记 docs/HTML_EXTRACTION.md

## 粘贴位置：→ 里程碑记录末尾追加

- 工程化 v6「HTML 文本提取」（2026-10-16）：HtmlExtractor（去 script/style/noscript、提 title/meta description/正文、块级换行、实体解码、charset 探测<meta>/BOM/默认 UTF-8、畸形容错，纯 C++17 手写零第三方依赖）+ Indexer 集成（增量索引/统计/prune 全链路）+ 搜索/locate（标题加权天然生效）+ serve/Web 冒烟验证 + Web 文件类型徽标；README（支持格式章节）/CHANGELOG v0.6.0/发版对照报告齐备

## 粘贴位置：→ 后续计划行，把 "HTML/PDF/Office 文本提取" 整段替换为

PDF / Office 文档的文本提取

## 粘贴位置：→ 发版对照行末尾追加

v0.6.0：docs/PRODUCTION_CHECKLIST_REPORT_v0.6.0.md

## 粘贴位置：→ 状态行末尾追加

工程化 v7「搜索质量工程」（2026-10-16）：混合检索 v2（SearchWeights{titleBoost, phraseBoost} 默认 1.0/2.0；CLI search 新增 --title-boost/--phrase-boost，非法值 exit 1；环境变量 DOCSEEK_TITLE_BOOST/DOCSEEK_PHRASE_BOOST 改默认值；GET /api/search 新增 title_boost/phrase_boost 查询参数，显式非法值 400）+ eval/ 评测集（42 篇中文语料：HTML 8/分词边界 12/问答 12/噪声 10；44 个 query→doc 评测对；eval/run_eval.py 一键评测）实测 Top-1 准确率 36/44 (81.8%)（html 10/10、tok 14/14、noise 6/6、neg 2/2、qa 4/12）；版本号 0.7.0；测试 108/108 通过（新增 test_hybrid 权重测试 5 例；WatcherTest.SubDir flaky 本轮偶发通过，v0.5.0 已有备注）；发版对照报告 docs/PRODUCTION_CHECKLIST_REPORT_v0.7.0.md

## 粘贴位置：→ 里程碑记录末尾追加

- 工程化 v7「搜索质量工程」（2026-10-16）：混合检索权重可配置贯通 CLI/HTTP/环境变量三层 + 评测集 v07（42 篇语料 + 44 评测对 + run_eval.py）Top-1 36/44 (81.8%) + README 搜索质量小节 + CHANGELOG v0.7.0 + 发版对照报告；评测发现已知问题 T1（分词器游标逻辑在 CutForSearch 重叠词下跳过中间 token 致索引静默丢词）/T2（索引查询切分上下文不一致致子串漏召回）/qa 4/12（噪声关键词 OR 回退被干扰文档反超），v0.8 排期

## 粘贴位置：→ 发版对照行末尾追加

v0.7.0：docs/PRODUCTION_CHECKLIST_REPORT_v0.7.0.md

## 粘贴位置：→ 已知问题/技术债区追加

- T1（v0.8 排期）：src/jieba_tokenizer.cpp xTokenize 游标单调 find 在 CutForSearch 重叠词（如"计算/算机/计算机"）下会跳到后文同词出现处，中间 token 从索引静默丢失。复现：文档含两次"维修"时 search 维修 无结果。
- T2（v0.8 排期）：jieba 最长匹配受上下文影响，索引时"猫砂盆"→猫/砂盆、查询时"猫砂"→猫砂，子串/单字 query 漏召回。复现：search 猫砂 无结果，search 养猫 正常。
- OPERATIONS.md 待办：未同步 DOCSEEK_TITLE_BOOST/DOCSEEK_PHRASE_BOOST 环境变量说明。
