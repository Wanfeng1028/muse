# 真实负载验证方法论文档

## 1. 为什么做
v2.11.1 对照报告遗留“真实负载验证：待执行”，本次 v2.12.0 正式补全该验证项，通过真实 HTTP 全链路压测暴露潜在性能瓶颈与并发问题。

## 2. 数据集设计
- 时间跨度：24 个月仿真账单。
- 笔数规模：约 110 笔/月（商户池 monthly 合计，±20% 抖动）。
- 商户池覆盖：餐饮、购物、交通、日用、医疗、工资、转账。
- 确定性种子：20261024，保证数据可复现。
- 文件格式：BOM + UTF-8，仿真真实支付宝导出格式。

## 3. 压测阶段
1. 预置账户/分类/规则。
2. 逐月 upload 计时，实测耗时（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
3. confirm 计时，实测耗时（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
4. 自动匹配率统计，实测匹配率（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
5. 去重探针：重传同一文件，验证去重效果，实测结果（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
6. 并发探针：多路并行上传，验证并发处理能力，实测耗时（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
7. 内存与库大小记录，实测占用（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。

## 4. 阈值说明
- CONFIRM_S_PER_300：单次 300 笔确认耗时阈值 30s，实测耗时（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
- 5xx 错误数：阈值 0，实测数量（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。
- 去重精度：要求精确去重，实测结果（本轮实测后填入 docs/LOAD_TEST_REPORT.md）。

## 5. 运行方法
- 全量 24 个月压测：`make load-test`
- 6 个月快速版：`make load-test-quick`
- 自定义参数：`python scripts/load_test.py --months N --concurrency 4 --out <report_path>`

## 6. 报告 JSON 结构说明
- `meta`：元信息（版本、种子、运行时间等）。
- `phases`：各阶段（upload、confirm 等）详细耗时与统计。
- `totals`：汇总数据。
- `dedup`：去重探针结果。
- `concurrency`：并发探针结果。
- `memory`：内存占用情况。
- `thresholds`：各项阈值判定结果（通过/未通过）。

## 7. 已知限制
- SQLite 单写者限制。
- 并发探针可能暴露锁等待，属预期行为。
- VM 硬件较弱时，数字仅供纵向对比，绝对值参考意义有限。
- CI 版测试（`tests/test_load_statement.py`）用小规模数据，非全量压测。

## 8. 与 tests/test_load_statement.py 的关系
`tests/test_load_statement.py` 作为 CI 常驻回归，保障每次提交的核心负载链路基本正确。
