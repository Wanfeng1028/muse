# 生产检查对照报告 v2.11.1
（版本 v2.11.1，日期 2026-10-24，范围一句话：关闭 v2.11 未通过项，把 CHANGELOG 曾纸面标注"（v2.11.1 关闭本项）"的四项补成实物）

## 可靠性
- 批量对账失败明细：通过。resolve-batch 新增 dry_run 入参 前置校验，不写库，新增 failures-export CSV 含 BOM 和七列。

## 可观测性

## 数据
- 迁移回滚路径：通过。scripts/rollback_v6_to_v5.py 纯标准库，默认试运行，--yes 先备份再执行，4 类冲突检测 → .rollback_conflicts.json（四键）→ exit 3，六真实场景全通过，已关闭“迁移回滚路径：未通过”。

## 部署运维
- 真实负载验证：待执行。v2.11 的真实负载验证尚未执行。
- 生产环境部署验证：待执行。v2.11 的生产环境部署验证尚未执行。

## 安全

## 可维护性
- 测试覆盖率：通过。test_rollback_v6_to_v5.py 11 例、test_workbench_dryrun_export.py 6 例全通过，全套 1393 通过、1 跳过（tesseract 缺失）。
- 文档一致性：通过。CHANGELOG v2.11.1 条目、OPERATIONS.md 文件名修正、MIGRATION_RUNBOOK 引用脚本已存在，本轮此前 CHANGELOG 6-9 条纸面关闭现已名实相符。

## 诚实声明
- 回滚脚本续写部分：通过。因模型两轮只交思考过程，编排将已核验的精确规格通过 API 落盘。
- 测试文件 bug 修正：通过。9 处测试侧 bug（编造分类名、漏 item_ids、字段名错等）由编排机械修正。
- 全量套件抓出脚本 bug：通过。LEDGER_DB 环境变量优先级高于显式 --db，已修为 --db 优先并加回归测试。
- workbench.py UP045 一致性：通过。2 处 UP045 与文件既有 Optional 风格一致，未改（ruff 未钉版本属已知技术债）。
- dry_run 预检范围：通过。dry_run 预检只覆盖前置校验，不覆盖 _apply_claim 内部 flush 级失败。
