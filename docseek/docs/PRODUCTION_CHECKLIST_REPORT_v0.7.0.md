
# v0.7.0 发版对照报告（生产级 Definition of Done）

- 版本：v0.7.0
- 主题：搜索质量工程
- 日期：2026-10-16
- 本版改动范围：① `include/docseek/searcher.h` + `src/searcher.cpp`：新增 `SearchWeights{titleBoost, phraseBoost}`（默认 1.0/2.0），`Searcher` 新增双参构造/`setWeights`/`weights()`，重排序用权重替代硬编码 1.0/2.0；② `src/main.cpp`：`search` 新增 `--title-boost`/`--phrase-boost`（非法值 exit 1），`readWeightEnv` 读 `DOCSEEK_TITLE_BOOST`/`DOCSEEK_PHRASE_BOOST`（非法打警告回默认），`kVersion`→0.7.0；③ `src/service.cpp`：`GET /api/search` 新增 `title_boost`/`phrase_boost` 查询参数（显式非法值 400），`/api/health` 与启动日志版本号→0.7.0，补 `#include <cmath>`；④ `eval/` 新增评测集：42 篇中文语料（HTML 8/分词边界 12/问答 12/噪声 10）+ 44 评测对 + `run_eval.py`。
- 无 DB schema 变更（沿用 PRAGMA user_version 机制）；无新第三方依赖（FetchContent 列表不变）；新增 2 个环境变量（权重默认值，非密钥）。

## 1. 可靠性

- **通过（测试金字塔）**：`ctest` 实测 108 例运行、107 通过。本轮新增 test_hybrid 权重测试 5 例全过，覆盖：默认等价（不设置权重时行为与旧硬编码 1.0/2.0 一致）、标题零权重、短语零权重、短语缩放、`setWeights` 生效。检索质量门由 `eval/run_eval.py` 一键可复现，本版实测 Top-1 准确率 36/44 (81.8%)，分类 html 10/10 / tok 14/14 / qa 4/12 / noise 6/6 / neg 2/2。唯一未通过例为 WatcherTest.SubDir，属 inotify 时序 flaky，v0.5.0 已有，与本轮无关。
- **未验证（失败注入）**：本轮未做失败注入测试，沿用 v0.5.0/v0.6.0 结论。
- **未验证（重试降级幂等）**：本轮未做重试/降级/幂等专项验证，沿用 v0.5.0/v0.6.0 结论。
- **不适用（DB 迁移版本化）**：本版无 DB schema 变更，沿用 PRAGMA user_version 机制，无新增迁移动作需验证。
- **未验证（健康检查+优雅关闭）**：`/api/health` 版本号已更新为 0.7.0，但健康检查语义与优雅关闭流程本轮未做专项验证，沿用 v0.5.0/v0.6.0 结论。

## 2. 可观测性

- **未验证（结构化日志+request_id）**：本轮未改动日志结构，未做专项验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（关键指标）**：本轮未新增指标，未做专项验证，沿用 v0.5.0/v0.6.0 结论。
- **通过（报错定位）**：新增权重参数具备明确报错路径——`search` 命令行非法值 exit 1；`GET /api/search` 显式非法 `title_boost`/`phrase_boost` 返回 400；环境变量非法值打警告回默认。启动日志版本号已更新为 0.7.0，可据此定位运行版本。
- **未验证（基础告警）**：本轮未做告警相关改动与验证，沿用 v0.5.0/v0.6.0 结论。

## 3. 数据与状态

- **未验证（备份恢复）**：本轮未做备份恢复专项验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（敏感数据策略）**：本轮未做敏感数据策略专项验证，沿用 v0.5.0/v0.6.0 结论。
- **通过（配置密钥分离）**：新增 `DOCSEEK_TITLE_BOOST`/`DOCSEEK_PHRASE_BOOST` 两个环境变量，均为权重默认值，非密钥，与密钥配置分离。
- **未验证（多用户设计）**：本轮未做多用户设计专项验证，沿用 v0.5.0/v0.6.0 结论。

## 4. 部署运维

- **未验证（Docker Compose）**：本轮未做 Docker Compose 相关改动与验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（滚动更新）**：本轮未做滚动更新专项验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（资源限制/日志轮转/数据卷）**：本轮未做资源限制、日志轮转、数据卷专项验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（运维手册）**：OPERATIONS.md 本轮未更新，手册未同步新增环境变量（`DOCSEEK_TITLE_BOOST`/`DOCSEEK_PHRASE_BOOST`）说明，记为待办。

## 5. 安全健壮性

- **通过（输入校验防注入）**：`--title-boost`/`--phrase-boost` 非法值 exit 1；`GET /api/search` 显式非法 `title_boost`/`phrase_boost` 返回 400；`readWeightEnv` 对环境变量非法值打警告回默认。输入校验路径明确。
- **未验证（基础鉴权）**：本轮未做鉴权相关改动与验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（依赖更新机制）**：本轮无新第三方依赖（FetchContent 列表不变），未做依赖更新机制专项验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（限流超时熔断）**：本轮未做限流、超时、熔断专项验证，沿用 v0.5.0/v0.6.0 结论。

## 6. 可维护性

- **通过（模块边界与 API 契约）**：`SearchWeights{titleBoost, phraseBoost}` 定义于 `include/docseek/searcher.h`，`Searcher` 暴露双参构造/`setWeights`/`weights()`，重排序用权重替代硬编码 1.0/2.0；命令行、HTTP 查询参数、环境变量三层配置入口契约清晰。
- **通过（CHANGELOG）**：CHANGELOG v0.7.0 经编排验收确认。
- **通过（技术债记录）**：新增 T1、T2 两条技术债并记录复现命令，沿用 WatcherTest.SubDir flaky 备注（inotify 时序，v0.5.0 已有，与本轮无关）。
- **通过（文档代码同步）**：CHANGELOG v0.7.0、README（版本/权重文档/搜索质量小节）、本报告三项经编排验收确认为通过。

## 7. 周期机制

- **未验证（真实负载验证）**：本轮未做真实负载验证，沿用 v0.5.0/v0.6.0 结论。
- **未验证（故障演练）**：本轮未做故障演练，沿用 v0.5.0/v0.6.0 结论。

## 结论

v0.7.0 以"搜索质量工程"为主题，完成权重可配置化（`SearchWeights` 默认 1.0/2.0）贯通 CLI/HTTP/环境变量三层，新增评测集与 `run_eval.py` 检索质量门，`ctest` 108/107，Top-1 36/44 (81.8%)。可靠性、可观测性、数据与状态、部署运维、安全健壮性、周期机制中大量维度本轮未做专项验证，一律沿用 v0.5.0/v0.6.0 结论或标注未验证；OPERATIONS.md 未同步新增环境变量说明，记为待办。本版可发，但上述未验证项与待办需在后续版本持续补齐。

## 已知问题与 v0.8 排期

- **T1（v0.8 排期）**：`src/jieba_tokenizer.cpp` 的 `xTokenize` 用游标单调 `find` 定位 CutForSearch 的词，当 CutForSearch 输出重叠词（如"计算/算机/计算机"）时，`find(算机, cursor)` 会跳到后文的同词出现处，导致中间 token 从索引中静默丢失。复现：文档含两次"维修"时 `search 维修` 无结果。
- **T2（v0.8 排期）**：jieba 最长匹配受上下文影响，索引时"猫砂盆"→猫/砂盆、查询时"猫砂"→猫砂，子串 query 漏召回。复现：`search 猫砂` 无结果，`search 养猫` 正常。
- **qa 4/12**：自然语言问句的噪声关键词（如"写在哪一段"中的"写"）经 OR 回退后被干扰文档（如含多处"写"的分词边界文档）反超，属召回排序改进方向，v0.8 排期。
- **WatcherTest.SubDir flaky**：inotify 时序问题，v0.5.0 已有，与本轮无关，沿用备注。
- **OPERATIONS.md 待办**：手册未同步新增环境变量（`DOCSEEK_TITLE_BOOST`/`DOCSEEK_PHRASE_BOOST`）说明。
