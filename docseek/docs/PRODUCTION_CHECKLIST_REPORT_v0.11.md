# docseek v0.11.0 发版对照报告

- 版本：v0.11.0
- 主题：搜索质量 T1/T2 修复
- 日期：2026-10-17
- 对照基线：`docs/PRODUCTION_CHECKLIST_REPORT_v0.7.0.md`（v0.7.0 报告）与 v0.10.0 发版结论

## 改动范围（文件级）

- `src/jieba_tokenizer.cpp`：主循环由"单调游标 find"改为"全文 occurrence 扫描 + 已认领集合"；`+#include <set>`。
- `src/searcher.cpp`：新增第 3 阶段子串召回回退（`buildSubstringRecallQuery` + `containsFolded` + 逐 token 精验循环）；新增 `expandTokenOrQuery`（按起始字节位置分组）；`buildMatchQuery` 连接符由空格改为显式 ` AND `；`buildOrMatchQuery` 同理改用展开；`+#include <map>`、`+#include <set>`、`+#include <optional>`、`+#include "docseek/query_parser.h"`、`+#include "docseek/jieba_tokenizer.h"`。
- `include/docseek/query_parser.h` + `src/query_parser.cpp`：新增 `isSingleCharStopword`（由匿名 namespace 暴露供复用）。
- `src/main.cpp`：`kVersion` → `0.11.0`。
- `tests/test_tokenizer.cpp`：+2 个 T1 复现测试；`tests/test_searcher.cpp`：+1 个 T2 复现测试。
- `eval/gen_corpus_v07.py`：+2 篇语料（`t1_01_repair.md`、`t1_02_jishu.md`）；`eval/eval_pairs_v07.json`：+12 评测对（6 T1 + 6 T2）。
- 无 DB schema 变更（沿用 PRAGMA user_version）；无新第三方依赖。

## 1. 可靠性

通过（限本轮改动范围）。

- T1 根因（源自 v0.7.0 报告原文）：`src/jieba_tokenizer.cpp` 的 `jiebaXTokenize` 用单调游标 `cursor` + `input.find(w, cursor)` 定位 CutForSearch 的每个词。CutForSearch 输出重叠词时（如"计算机技术"=><计算><算机><技术><计算机><计算机技术>），排在后面的词其真实位置落在 cursor 之前，`find` 返回 npos → token 静默丢失；`find` 也可能跳到后文的同词出现处，导致游标大幅前跳、后续普通词被级联丢失。实测："计算机技术"丢了算机/计算机/计算机技术；"计算机算机维修"连"维修"都丢了。
- T1 修复：改为"全文 occurrence 扫描 + 已认领集合"——每个词在全文 `[0,n)` 独立枚举所有出现位置（`p+1` 字节推进，允许重叠），取第一个未被 `(词, 起始字节)` 认领的位置输出；不同词允许同位置重叠（如 计算/计算机 都在字节 0）。归一化回退路径（按码点逐个定位）保留，同样走认领集合。循环天然有界，不可能死循环。
- T2 根因（v0.7.0 报告原文）：jieba 最长匹配受上下文影响——索引时"猫砂盆"→<猫><砂盆>、查询时"猫砂"→<猫砂>，子串 query 漏召回。复现：`search 猫砂` 无结果。
- T2 修复（动查询侧，不动索引侧——索引侧加单字 token 要全量重建用户库且永久增大索引；查询侧回退是纯加法，只在精确 AND、OR 回退都为空时触发，不可能让任何已有查询退化）：`Searcher::search` 新增第 3 阶段"子串召回回退"——中文 token 拆单字 OR 粗筛（跳过单字停用词）+ 按原始 token 逐个子串精验（`containsFolded`，ASCII 大小写不敏感，查标题+正文）。只有原文确实连续包含每个查询 token 的文档才保留——这正是"子串查询"的定义，neg 类查询仍返回空。
- 查询构造修正：新增 `expandTokenOrQuery`，单个查询词经 CutForSearch 后按起始字节位置分组（与 `jiebaXTokenize` 同样的 occurrence 扫描定位，保证两边一致）——同一起始位置的重叠词 OR（如"咖啡豆"→`("咖啡" OR "咖啡豆")`，单个引号串会被 FTS5 当成要求相邻的短语而恒为 0），不同位置顺序 AND（如"超导材料制备"→`"超导" AND "材料" AND "制备"`）。另实测发现 FTS5 语法铁律：括号 OR 组与引号串隐式相邻会报 `syntax error near "OR"`，必须显式 AND——`buildMatchQuery` 的连接符已由空格改为 ` AND `（与原来语义等价，已实测 `"a" "b"` 即 AND）。
- 测试：新增 3 个复现测试（先红后绿已验证）：`TokenizerT1.DuplicateWordNotLost`（'计算机算机维修' 的"维修"被级联丢失）、`TokenizerT1.OverlappingWordNotLost`（'计算机技术' 的"计算机"丢失）、`SearchT2.SubstringQueryRecall`（`search 猫砂` 命中含猫砂盆的文档）。断言走 fts5vocab 直接读索引（本仓库 sqlite 的 `offsets()` 不可用；MATCH 查询串同样会被分词器切分，会掩盖索引侧丢词）。
- ctest：除 1 例已知 flaky（`WatcherTest.SubDir`，inotify 时序，v0.5.0 已有，本轮单独重跑 3 次 1 过 2 挂，确认与本轮无关）外全绿。

## 2. 可观测性

未验证，沿用 v0.10.0 结论。

- 本轮未改动日志、指标、追踪相关代码路径。

## 3. 数据与状态

通过（限本轮改动范围）。

- 无 DB schema 变更（沿用 PRAGMA user_version）。
- 索引格式未变；T2 选择只动查询侧，未新增索引侧 token，故不需要全量重建用户库。
- T1 修复改变的是索引构建时的 token 定位逻辑，修复后新建/重建的索引在重叠词场景下不再丢词；既有索引的修复依赖重建（本轮未自动触发重建）。

## 4. 部署运维

未验证，沿用 v0.10.0 结论。

- 本轮未改动部署脚本、服务编排、迁移流程。
- `src/main.cpp` 的 `kVersion` 已更新为 `0.11.0`（`--version` / 服务启动日志）。
- 遗留：`service.cpp` 的 `/api/health` 与一处版本字面量仍为 0.9.0（v0.10.0 遗留，未在本轮动，记为待办）。

## 5. 安全健壮性

通过（限本轮改动范围）。

- T1 新主循环天然有界（`p+1` 字节推进），不可能死循环。
- T2 回退为纯加法，只在精确 AND、OR 回退都为空时触发，不可能让任何已有查询退化；neg 类查询仍返回空。
- `expandTokenOrQuery` 修正 FTS5 语法（括号 OR 组与引号串隐式相邻报 `syntax error near "OR"`），消除一类查询构造崩溃/报错面。
- 未新增第三方依赖。

## 6. 可维护性

通过（限本轮改动范围）。

- `isSingleCharStopword` 从 `src/query_parser.cpp` 匿名 namespace 暴露到 `include/docseek/query_parser.h` 供复用，消除重复实现。
- 新增 3 个先红后绿复现测试，回归有守护（5 对真回归对 + 7 对回归守护对）。
- 已知：T2 回退路径与 `jiebaXTokenize` 共享 occurrence 扫描定位逻辑以保持一致，但二者仍为两处实现，后续可考虑抽取公共工具。

## 7. 周期机制

不适用。

- 本轮未涉及定时任务、清理周期、后台作业等周期机制改动。

## 结论

- 评测：语料 42→44 篇（新增 `t1_01_repair.md`、`t1_02_jishu.md`），评测对 44→56（新增 12 对：6 T1 + 6 T2），最终 **48/56（85.7%）**；基线（v0.7.0 报告）为 36/44（81.8%）。分类：html 10/10、tok 26/26、neg 2/2、noise 6/6、qa 4/12。
- 8 个失败与基线是同一集合（qa 自然语言问句），属独立已知问题（TECH_DEBT P1-2，qa 召回排序），本轮未动。
- 新增 12 对中 5 对已在修复前验证为 FAIL（真回归对）：v11-t1-02（算机维修）、v11-t1-03（计算机维修）、v11-t1-04（计算机技术）、v11-t1-05（电脑维修→tok_09）、v11-t2-01（猫砂）；其余 7 对为回归守护对。
- 中间曾出现两次回退均已修复并如实记录：① 初版 T2 单字 OR 无精验，neg 对 37/38 被误召回（34/44）；② T1 修复后查询"咖啡豆"因 FTS5 短语语义从 PASS 变 FAIL（35/44），由 `expandTokenOrQuery` 解决。
- 测试：ctest 除已知 flaky（`WatcherTest.SubDir`）外全绿。

## 已知问题与待办

1. T2 第 3 阶段要求查询 token 在文档中**连续**出现；同义/语义级子串（如搜"电脑"期望命中只写"PC"的文档）不在本轮范围。
2. 单字 OR 粗筛对极常见单字可能产生较大候选中介集合（单字停用词已过滤，但其他常见字仍可能），性能未做专项压测。
3. qa 4/12 未改善：自然语言问句理解是独立问题，不属 T1/T2。
4. `service.cpp` 的 `/api/health` 与一处版本字面量仍为 0.9.0（v0.10.0 遗留，未在本轮动，记为待办）。
5. qa 召回排序（TECH_DEBT P1-2）：8 个失败与基线同一集合，本轮未动。
6. `WatcherTest.SubDir` flaky（inotify 时序，v0.5.0 已有）：本轮单独重跑 3 次 1 过 2 挂，确认与本轮无关。
