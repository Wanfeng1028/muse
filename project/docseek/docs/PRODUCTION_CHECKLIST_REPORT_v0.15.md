# docseek v0.15.0 发版对照报告

## 1. 版本与日期

- 版本：v0.15.0
- 代号：搜索质量攻坚
- 日期：2026-10-18

## 2. 本轮改动清单

本轮共 7 项改动。

1. Fix A：认领失败不再整串退化。
   原理：`expandTokenOrQuery` 里词没被词典认领时，不再把整串退回原样，而是未认领的词各自 `quoteToken` 后用 AND 追加。
   改动文件：`src/searcher.cpp`

2. Fix B：子串召回精验改按切词逐个包含。
   原理：`substringRecallPass` 的子串召回精验，从"原文连续包含整串 token"改成按 `CutForSearch` 切词逐个包含。
   改动文件：`src/searcher.cpp`

3. fillerWords 补全。
   原理：往填充词表补了 知道/什么/什么时候/怎么办/的话/比较；"不"字永不入表。
   改动文件：`src/query_parser.cpp`

4. extractPhrases 提升为公开函数。
   原理：声明进 `include/docseek/query_parser.h`，定义从匿名 namespace 搬到 `docseek` 作用域。
   改动文件：`include/docseek/query_parser.h`、`src/query_parser.cpp`

5. GAP-PHRASE-001：引号短语查询落地。
   原理：`search`/`searchQuestion` 先剥离短语，rest 走三阶段召回，`filterByPhrases` 后过滤（title + 原文 `containsFolded` 连续包含），`rerankHits` 每短语 +phraseBoost；纯短语查询用短语展开 OR 召回。
   改动文件：`src/searcher.cpp`

6. GAP-STOPWORD-001：停用词过滤。
   原理：`search`/`searchQuestion` 入口过滤单字停用词 token，纯停用词查询直接返回空；引号短语不受影响。
   改动文件：`src/searcher.cpp`

7. GAP-TOK-001：单 token OR 放宽。
   原理：`expandTokenOrQuery` 重构为 `expandTokenWithJoiner(token, joiner)`，新增 `expandTokenOrSingle`（组间 OR）；`search` 阶段 2 条件放宽为 `!tokens.empty()`，单 token 时用 `expandTokenOrSingle`。
   改动文件：`src/searcher.cpp`

## 3. 验证结果

### E2E 实测（5 条）

| 查询 | 结果 | 改动前 |
| --- | --- | --- |
| `search '"人工智能"'` | 1 hit | 0 |
| `search '的'` | 0 hits | 1 |
| `search '了 在 的'` | 0 hits | — |
| `search '考研数学一'` | 1 hit | 0 |
| `search '人工智能'` | 仍 1 hit（无回归） | 1 |

### ctest 基线

Fix A/B + fillerWords 落地后、GAP 实现前：323 通过、0 失败。

排除项（均为 pre-existing，不计入）：

- `WatcherTest.SubDir`：已知 inotify flaky。
- `TokenizerPerf.EndToEndOneMegabyteTokenizeThenSearchHit`：本机 hang。

### 新增测试文件（6 个）

| 文件 | 用例数 |
| --- | --- |
| `test_v015_substring_recall.cpp` | 10 |
| `test_v015_expand_fix_a.cpp` | 8 |
| `test_v015_filler_words.cpp` | 10 |
| `test_v015_search_question.cpp` | 9 |
| `test_v015_phrase_edge.cpp` | 10+ |
| `test_v015_stopword_edge.cpp` | 8+ |

### 构建

cmake 零警告（自有文件；cppjieba 第三方头警告为 pre-existing）。

## 4. 评测状态（2026-10-18 实测）

- v07：56/56（100%）——零回归。
- v08（含 12 个对抗变体，共 83 对）：81/83（97.6%）——2 个失败为 v0.14.0 已记录的未攻克对抗变体
  （v08-qa-09d→tok_05_mixed.md、v08-qa-15d→qa_08_invoice.md），与 v0.14.0 基线一致，零回归。
- v09 样本：待跑（见下）。

本轮中发现并修复 1 个真实回归：单 token OR 放宽（GAP-TOK-001）曾导致 v07-038「超导材料制备」
误命中只含"材料"的 tok_06_number.md（OR 召回过宽）。修复：单 token OR 结果用 substringRecallPass
做精度过滤（只保留原文包含查询每个切词的文档），v07 回到 56/56。另补强：单 token 切词全为单字停用词
（如"的了在了"）视为纯停用词查询直接返回空。

## 5. 工单关闭清单

本轮关闭：

- GAP-PHRASE-001
- GAP-STOPWORD-001
- GAP-TOK-001

分词器 triage（29 个 pre-existing 失败）：

- 来源：e7eae08 提交引入，自提交起从未通过。
- 处理：14 个测试修正 + 15 个 `GTEST_SKIP` 建工单。
- 现状：本轮 15 个 SKIP 已全部移除（缺口已修复）。

## 6. 已知限制

- 多字 token 内部停用字未处理。
- 同义词鸿沟：尚未处理。
- C 类排序微调：未做。
- D 类长问句噪音：部分剩余。

## 7. 后续排期

- 本轮评测：v07 56/56、v08 81/83（2 个为已知未攻克），v09 样本待跑。
- 同义词鸿沟：待排期。
- C 类排序微调：待排期。
- D 类长问句噪音剩余部分：待排期。
- 多字 token 内部停用字：待验证影响范围，未排期。
