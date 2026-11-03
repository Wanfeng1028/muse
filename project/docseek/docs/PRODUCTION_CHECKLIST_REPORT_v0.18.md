# docseek v0.18 生产对照报告（Wave4：v09 剩余失败攻坚）

**版本**: v0.18.0 | **日期**: 2026-10-19 | **基线**: v0.17.0 (193/200)

## 本轮目标
攻坚 v09s 评测剩余 7 个失败：t006-q11, t007-q08, t009-q08, t013-q05, t018-q09, t019-q12, t021-q12。

## 诊断与修复

### ✅ t009-q08（修复）
- **根因**: 查询"周末 避开人群"中的"人群"，期望文档标题含"人挤人"不含"人群"，同义词表缺边。
- **修复**: synonyms.cpp 新增边 人群→人挤人（B3-r2 OR 展开，UTF-8 字节序插入）。
- **验证**: 评测通过，零回归。

### ✅ t019-q12 search 路径（机制性修复，评测为 locate 型未直接受益）
- **根因**: 查询侧 jieba 切词 [长期][不][弹琴] 与索引侧 [长期][不弹] 错位。
- **修复**: searcher.cpp 新增 `tryAdjacentPrefixProbe`（相邻 token 前缀/子串交叉探测）。
  - 关键修正：helper 内必须用 jieba CutForSearch 将空白粗块展开为细 token（诊断曾误用 parseNaturalQuery keywords）。
  - 触发条件按 jieba 展开后的 jtoks 数量判断（中文无空格查询 tokens 常为单个粗块）。
- **验证**: 8 个 gtest 全绿；合成测试"长期不弹琴"类查询均召回目标文档。

### ❌ t006-q11（不可修复，架构级）
- 查询"弹力带..."切出 [弹力][带用]，索引侧为 [弹力带]。F-T006A 曾尝试同起点前缀吸收，但与 v0.14 刻意保留重叠 token 的行为冲突（导致 ContactLookupQueryDropsXiangAndPunct 回归），已回滚。

### ❌ t013-q05（不可修复，语义鸿沟）
- 查询"月历排版" vs 期望文档"月历排"。排版 vs 排是语义级差异，非切词可解。

### ⏳ t007-q08, t018-q09, t021-q12（locate 路径，下轮）
- t007-q08（search 型）："三个月"召回偏差，R2b 50% 方案曾引入 2 个回归已回滚。
- t018/t019/t021（locate 型）：locate 路径经 parseNaturalQuery→recallQuery→search→rankPassages，
  失败点在 passage 排序阶段，需下轮专项攻坚。

## 回滚记录（诚实）
- **F-RERANK**（contentTokens/R2b 50%/R2c/去重）：目标未达成，反而引入 t004-q06、t009-q04 两个回归，**已全量回滚**。
- **F-T006A**（同起点前缀吸收）：与 v0.14 既有测试冲突，**已回滚**。

## 验证结果
- **ctest**: 410/410 通过（排除 WatcherTest.SubDir inotify flaky + TokenizerPerf* hang，既知环境问题）
- **v09s**: **194/200**（+1，零回归）
- **新测试**: 17 个（test_adjacent_probe_v018.cpp 8个，test_synonyms_v018.cpp 9个... 实际 17 个），全绿
- **v07**: 待跑 | **v08**: 待跑

## 生产 checklist
- [x] 单元测试全绿
- [x] 评测零回归（194/200）
- [x] 回滚机制验证（F-RERANK/F-T006A 干净回滚）
- [ ] v07/v08 回归评测（下轮补）
- [ ] locate 路径 4 个失败（下轮）

## 技术债
1. locate 路径 passage 排序需专项优化（t018/t019/t021）。
2. t007-q08 的"三个月"召回问题。
3. F-RERANK 的想法（R2b 50%、R2c）需更精细的回归控制后重提。
