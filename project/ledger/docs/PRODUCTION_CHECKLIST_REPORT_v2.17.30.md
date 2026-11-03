# 生产检查清单报告 v2.17.30

本轮只补 POST /api/bills/review/batch 逐条处理中非 HTTP 异常的隔离路径，无破坏性变更。

## 可靠性
_reject_one/_confirm_one 抛非 HTTPException 异常时不再穿出接口返回 500，改为回滚该条、记入 failed、继续后续条目、最终返回 200；此前已 commit 的成功项不再因后续条目内部错误而丢失结果；HTTPException 路径、成功项结构、commit 顺序一字不动。

## 可观测性
非 HTTP 异常分支各记一条 warning 日志，事件名 batch_item_failed，extra_data 含 action、review_id、error 的 repr；调用方收到的 failed error 固定为“处理失败”，内部错误详情只进服务端日志、不返回给调用方；HTTP 路径的 error 取值仍为原 detail。

## 数据与状态
无迁移、无新依赖、无新增端点；数据库 schema 与既有审核记录、交易数据状态一字不动；失败条回滚后仍为 pending，可重试。

## 部署运维
无新增端点、无 UI 改动，视觉验收不适用；部署动作与 v2.17.29 相同，仅需替换代码后回归靶向测试。

## 安全与健壮性
批量接口不再因单条内部错误整体 500，避免已成功项结果丢失与后续条目被跳过；内部异常不向调用方泄露详情。

## 可维护性
发版升版四处统一为 2.17.30：src/ledger/__init__.py、pyproject.toml、tests/test_version_consistency_v21715.py 的 EXPECTED_VERSION、CHANGELOG.md 顶条；CHANGELOG 顶条已更新为 v2.17.30。

## 冒烟结果
真实服务冒烟（18495 端口隔离库，冒烟后服务已停、端口已关、隔离库已删）：health 200、建账户 201、批量驳回 2 条 200、批量确认 1 条 200 且返回 transaction_id、非法 action 400，全过；冒烟时版本仍为 2.17.29（升版在冒烟后做）。

## 结论
靶向范围全部通过：新增 tests/test_bills_review_batch_nonhttp_isolation.py 2 例全绿，新测 2 例 + 既有批量测试 13 例 + 版本一致性测试 1 例合计 16 项全绿；ruff check 改动文件全洁（新测经 ruff format 与 import 排序修正）；全量 pytest 本轮未跑，记为已知保留；本轮未动并行工人的未提交文件（docseek/eval 零散文件保持原样）。
