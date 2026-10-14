# 文溯 DocSeek 检索质量评测（v0.3.0）

评测日期：2026-10-13
评测人：Muse 编排（dpsk 生成语料与代码，人工执行验证）

## 一、评测语料

`~/workspace/muse-build/docseek-eval/corpus/`（dpsk 生成，12 篇中文文档）：

| 类型 | 文件 | 说明 |
|---|---|---|
| 长文档 | ir-basics.md、inverted-index.md | 1000 字以上，全文检索/倒排索引原理 |
| 中英混合 | mixed-bm25.md、mixed-tfidf.md、mixed-sqlite.md | 英文术语 + 中文讲解 |
| 标点干扰 | punct-notes.md、punct-diary.md | 大量括号引号破折号 |
| 领域词汇 | tokenizer-deep.md、corpus-metrics.md、recall-precision.md | 分词器/召回率/准确率 |
| 噪声文档 | noise-cooking.md、noise-travel.md | 做菜、旅行（无关） |

## 二、Top-1 准确率（10 个查询）

| 查询 | Top-1 结果 | 是否符合预期 |
|---|---|---|
| 全文检索 | ir-basics.md | ✅ |
| 倒排索引 | inverted-index.md | ✅ |
| 中文分词 | tokenizer-deep.md | ✅（v0.2.0 时代无结果，v0.3.0 修复） |
| BM25 | mixed-bm25.md | ✅ |
| 召回率 | recall-precision.md | ✅ |
| SQLite | mixed-sqlite.md | ✅ |
| 切词 | tokenizer-deep.md | ✅ |
| 搜索引擎 | recall-precision.md | ✅（该文档讲搜索质量指标，合理） |
| 红烧肉 | noise-cooking.md | ✅ |
| 旅游 | 无结果 | ✅（语料中只有"旅行"没有"旅游"，无结果是正确行为；查"旅行"正确命中 noise-travel.md） |

**结论：10/10 符合预期。** v0.2.0（unicode61）下"中文分词""检索"类子串查询无结果的问题已解决。

## 三、混合检索 v1 行为验证

- AND→OR 回退：`search("苹果 香蕉")` 在 AND 无结果时回退 OR，两个文档都召回（单元测试 HybridTest.OrFallback）。
- Title 加成：标题命中查询词的文档排序提前（单元测试 HybridTest.TitleBoost）。
- 短语加成：标题/摘要包含完整查询串的 +2.0（见 src/searcher.cpp）。

## 四、性能抽查

- 语料：10000 个中文文本文件，共约 40MB（随机词拼接，每篇 30~80 词）。
- 索引：10000 文件全部新增，**耗时 267 秒**（约 37 文件/秒），DB 文件 7.4MB。
  - 瓶颈分析：当前每个文件独立事务（`BEGIN IMMEDIATE` per upsert），WAL 刷盘频繁；批量事务可大幅提速（记为技术债）。
- 检索：万级库 `search` 返回 3 条，**耗时 2.7 秒**（其中约 2 秒为进程启动时 cppjieba 词典加载；常驻 serve 模式下单次查询为毫秒级）。
- 测试机：2 核 VM（无 KVM 加速）。

## 五、已知问题（v0.5.0 更新）

1. ~~cppjieba 词典加载噪音~~ **已解决（v0.5.0）**：`src/jieba_tokenizer.cpp` 新增 `StderrSilencer`（RAII），在 `ensureJieba()` 构造期把 stderr 临时重定向到 `/dev/null`；`DOCSEEK_JIEBA_VERBOSE=1` 可恢复输出用于排障。实测 `docseek stats` 的 stderr 已无 `KeywordExtractor` 输出。
2. `WatcherTest.SubDir`（inotify 递归监控）为 flaky 测试，在 pristine v0.2.0 代码上同样偶发失败，与本次改动无关（v0.5.0 全量 62 例中其余全部稳定通过）。
3. ~~索引批量事务技术债~~ **已解决（v0.5.0）**：`Indexer::indexPaths` 改走批量事务（每 500 文件提交一次）；`Database` 新增 `beginBatch/commitBatch/abortBatch`（嵌套事务防护 + 异常回滚）。实测 1000 文件 6.8 秒（约 147 文件/秒，老基线 37 文件/秒，提升约 4 倍）。

## 六、灵魂定位（2026-10-13）

本地文件的 Google —— 真中文分词 + 混合检索 + 自然语言定位原文。技术含金量担当：FTS5 自定义分词器（jieba）、旧库自动迁移、混合检索 v1。

## 七、v0.4.0 自然语言定位评测

评测日期：2026-10-13；评测人：Muse 编排（真实构建 + 真实语料执行）
评测语料：v3 语料（12 篇）+ 新增 4 篇问答型中文文档（退款政策.md：含"七天无理由退款"段落；发货说明.md；会员权益.md；vision-pro.md）。

| # | 自然语言查询 | Top-1 实测 | 是否符合预期 |
|---|---|---|---|
| 1 | 退款流程写在哪一段 | 退款政策.md:4-7（0.529） | ✅ 行号覆盖"七天无理由退款"段落 |
| 2 | 七天无理由退款是真的吗 | 退款政策.md:4-7（0.258） | ✅ 段落文本含"七天无理由退款" |
| 3 | 发货要等多久 | 发货说明.md:4-6（0.287） | ✅ |
| 4 | 会员有什么权益 | 会员权益.md:1-2（0.458） | ✅ |
| 5 | 倒排索引的原理是什么 | inverted-index.md:1-4（0.683） | ✅ |
| 6 | 中文分词怎么做 | tokenizer-deep.md:1-4（0.850） | ✅ |
| 7 | BM25 是什么 | mixed-bm25.md:22-26（0.717） | ✅ |
| 8 | 红烧肉的做法在哪篇 | noise-cooking.md:1-4（0.750） | ✅ |
| 9 | xyzabc不存在的词 | 无结果（友好提示） | ✅ |
| 10 | "Vision Pro" 价格是多少（引号短语） | vision-pro.md:1-2 / :4-6 | ✅ 短语正确抽取（单元测试 QueryParser.QuotedPhrase），价格段落命中 |

**结论：10/10 符合预期。** 自然语言问句 Top-1 全部命中正确文档且行号落在目标段落；无结果时 CLI 给出换说法提示而非报错；引号短语端到端可用。
