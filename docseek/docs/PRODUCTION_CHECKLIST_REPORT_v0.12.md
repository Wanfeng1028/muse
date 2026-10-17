# docseek v0.12.0 发版对照报告

## 元信息

| 项目 | 内容 |
| --- | --- |
| 版本 | v0.12.0（次版本升级；对外版本号 0.12.0） |
| 主题 | 问句理解升级 |
| 日期 | 2026-10-17 |
| 对照基线 | docs/PRODUCTION_CHECKLIST_REPORT_v0.11.1.md |

## 改动范围（文件级）

新增文件：

- `eval/eval_pairs_v08.json`
- `docs/PRODUCTION_CHECKLIST_REPORT_v0.12.md`

修改文件：

- `src/query_parser.cpp`
- `src/passage_ranker.cpp`
- `src/locator.cpp`
- `src/searcher.cpp`
- `include/docseek/searcher.h`
- `tests/test_query_parser.cpp`
- `tests/test_locate.cpp`
- `tests/test_searcher.cpp`
- `include/docseek/version.h`（0.11.0→0.12.0）
- `README.md`（搜索质量小节）
- `CHANGELOG.md`

## 改动要点

1. `src/query_parser.cpp`：fillerWords 疑问词表清理（删除与 singleCharStopwords 重复的"的/了"，全表按长度严格降序排列）；新增 trailingPredicates 尾部谓语剥离（词表：写在哪/写在/说明/介绍/申请/开具/重置/阐述/写，只剥离尾部谓语、保留名词主题），parseNaturalQuery 步骤 2.5 接入。
2. `src/passage_ranker.cpp`：修复标题行断窗覆盖 bug（断窗后下一个窗口从标题行开始，保证每行必被某个窗口覆盖）；passageIntent=true 时，含标题行的窗口得分 +0.1。
3. `src/locator.cpp`：recallQuery 构造时跨 keywords/phrases 去重；问句（passageIntent 为真，或查询以"在哪里/在哪/哪里/吗/?/？"等问句尾缀结尾）走新的 searchQuestion 召回路径。
4. `src/searcher.cpp` + `include/docseek/searcher.h`：新增 Searcher::searchQuestion（问句 AND 与 OR 并集召回，按 doc_id 去重；重排逻辑抽取为共用函数 rerankHits，search() 行为零差异）。
5. 评测集：`eval/eval_pairs_v08.json`（71 对：56 个 v07 对逐字 + 15 个新增真实问法）。
6. 测试：`tests/test_query_parser.cpp` 新建 5 例；`tests/test_locate.cpp` 新增 4 例；`tests/test_searcher.cpp` 新增 1 例。

## 前后数字对照

| 指标 | v0.11.x（基线） | v0.12.0 |
| --- | --- | --- |
| v07 总准确率 | 48/56（85.7%） | 55/56（98.2%） |
| v07 qa | 4/12 | 11/12（91.7%） |
| v07 html | — | 10/10 |
| v07 tok | — | 26/26 |
| v07 noise | — | 6/6 |
| v07 neg | — | 2/2 |
| v08 总准确率（新增） | — | 66/71（93.0%） |
| v08 qa（新增） | — | 22/27（81.5%） |
| gtest | 157 | 168/168 全过（新增 10 例） |

## checklist 对照

### 1. 可靠性

- 测试金字塔——单元+集成+端到端：**通过**。本轮新增 10 例测试覆盖改动点：`tests/test_query_parser.cpp` 新建 5 例、`tests/test_locate.cpp` 新增 4 例、`tests/test_searcher.cpp` 新增 1 例；gtest 157 → 168/168 全过。
- 错误处理策略：**未改动，沿用既有结论**。
- 数据库迁移版本化：**不适用**（本轮无 schema 变更）。
- 健康检查端点：**未改动，沿用既有结论**。

### 2. 可观测性

- 结构化日志/指标/告警：**本轮未改动，未验证，沿用既有结论**。
- 报错定位：**未改动，沿用既有结论**。

### 3. 数据与状态

- 自动备份：**不适用**（本轮无数据层改动）。
- 敏感数据：**不适用**（本轮无数据层改动）。
- 配置密钥：**不适用**（本轮无数据层改动）。
- 多用户：**不适用**（本轮无数据层改动）。

### 4. 部署运维

- 无新第三方依赖，构建依赖集不变：**通过**。
- 构建告警：**通过**。cmake 零警告（自有文件；第三方 cppjieba 头文件警告为 pre-existing）。
- 运维手册/滚动更新：**未改动，沿用既有结论**。

### 5. 安全健壮性

- 本轮只动查询解析/排序/召回纯逻辑，未引入新的外部输入解析路径，无新增依赖、端点、权限变更：**通过**。
- 输入校验/限流熔断：**未改动，沿用既有结论**。

### 6. 可维护性

- 模块边界：**通过**。searchQuestion 新增于 Searcher 公共接口，重排逻辑抽取为共用 rerankHits，search() 零行为差异。
- CHANGELOG + 升级指南随版本更新：**通过**（本轮已更新 CHANGELOG.md、README.md、版本号 0.12.0）。
- 技术债记录：**通过**（未改善项在"已知问题与待办"诚实声明）。
- 代码与文档同步：**通过**。

### 7. 发版前对照报告

**通过**（本报告即是）。

### 8. 周期机制

- 技术债清理/真实负载验证/故障演练：**本轮未做，未验证，沿用既有结论**。

## 结论

本轮为次版本功能升级（问句理解）。v07 评测集 56 对：55/56（98.2%），基线 48/56（85.7%）；分类：html 10/10、tok 26/26、noise 6/6、neg 2/2、qa 11/12（91.7%，基线 4/12）。v08 评测集（eval/eval_pairs_v08.json：56 个 v07 对逐字 + 15 个新增真实问法，共 71 对）：66/71（93.0%），qa 22/27（81.5%）。gtest 168/168 全过。构建 cmake 零警告（自有文件；第三方 cppjieba 头文件警告为 pre-existing）。

## 已知问题与待办

1. v07-024 "安装步骤在哪里"未修复（期望 qa_04_install.md，实际 tok_12_verb.md；跨文档排序被干扰文档以 0.845 vs 0.688 压制；跨文档排序问题，超出本轮问句改写范围）。
2. v08 新增 4 个真实问法失败：v08-qa-03 "请问发货得几天啊"→t1_01_repair.md、v08-qa-09 "多久备份一次"→t1_01_repair.md、v08-qa-10 "有哪些套餐"→tok_04_ambiguity.md、v08-qa-15 "想找客服，联系方式在哪啊"→qa_08_invoice.md。
3. WatcherTest.SubDir flaky 照旧（v0.5.0 起已知的 inotify 时序问题，与本轮无关）。
4. T2 连续出现要求（v0.11.0 已记录）本轮未改动。
5. 本轮未对未改动维度做回归验证，相关结论沿用 v0.11.1 报告。