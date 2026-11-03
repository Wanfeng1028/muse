# 生产验收对照报告 v0.20.0

版本：v0.20.0「查询理解升级」
日期：2026-10-20

| 验收红线 | 结论 | 证据 |
| --- | --- | --- |
| t021-q12 修复 | 通过 | 期望文档 #4 0.65 变为 #1 0.975 |
| v07 保持 56 / 56 | 通过 | 56 / 56，基线 56 / 56 |
| v08 大于等于 81 / 83 | 通过 | 81 / 83，基线 81 / 83 |
| v09s 大于等于 197 / 200，目标 198 | 通过 | 198 / 200，基线 197 / 200 |
| gtest 全绿，除已知 flaky | 通过 | 437 通过 / 0 失败，438 运行，1 跳过 |
| CHANGELOG 齐备 | 通过 | CHANGELOG.md 含 v0.20.0 条目 |
| 评测报告齐备 | 通过 | docs/EVAL_V020.md |
| DoD 报告齐备 | 通过 | docs/PRODUCTION_CHECKLIST_REPORT_v0.20.0.md |
| 不许 commit 或 push，改动留工作树 | 通过 | 未执行 commit 与 push，改动保留在工作树 |

排除项说明：WatcherTest.SubDir、TokenizerPerf.* 为已知环境 flaky；TokenizerLong.VeryLongPunctuationQueryReturnsEmpty 经 pristine 基线树验证同样 hang，为预先存在的环境问题，非本轮引入。
