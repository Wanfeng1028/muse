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
