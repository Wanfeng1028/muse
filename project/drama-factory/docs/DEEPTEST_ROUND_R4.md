# 深测轮 R4（2026-10-19 晚）：Run 状态机交互 + 审批门 + CostLedger 预算守卫纵深

## 范围
- 收敛上一轮遗留：ShotContinuityChecker null 元素过滤加固 + 6 个 deep test 修正 + 2 个新增测试（CostLedgerFailureDeepTest、PipelineTemplateServiceDeepTest）+ docs/OPERATIONS.md 222 行新增。指定三件套 59/59 全绿。
- 本轮新增 3 个深测文件（dpsk 生成，编排验收修 2 处编造）：
  - `RunStateMachineInteractionDeepTest`（12 例，Mockito）：Run 暂停/继续/取消/重试与 RunExecutor.tick 的交互。
  - `ApprovalGateDeepTest`（10 例，Mockito）：人工审批门状态流转 + approve→RUNNING→tick 闭环。
  - `CostLedgerBudgetGuardDeepTest`（15 例，SpringBootTest+H2）：预算守卫数学（reservePct 钳制、null policy 默认、usable 计算、WARN/CAP）+ summarize 边界（时间闭区间、组合过滤、空库）+ 非法迁移全矩阵。

## 锁定的语义（回归保护）
1. `tick()` 只查 RUNNING：PAUSED / WAITING_APPROVAL 的 run 永不被推进。
2. `cancel()` 只清 PENDING step（RUNNING 的 step 保持不动）；video task 只有 PENDING/PROCESSING → FAILED（errorMessage="运行已取消"），DONE 不动；SUCCEEDED run 上 cancel 抛 IllegalStateException。
3. `retryStep()` 只有 FAILED/CANCELLED 的 run 才重开为 RUNNING；WAITING_APPROVAL/SUCCEEDED/RUNNING/PAUSED 保持原状态。
4. `approve()`：note 可为 null（QcRequest 的 note 无 @NotBlank）；approved→QC step SUCCEEDED+endedAt、run RUNNING；rejected→QC step FAILED+errorMessage=note、run FAILED。
5. `reserve()`：reservePct 截断到 [0,0.9]；null policy 等价于 WARN+0 预算；usable = budget - spent(COMPLETED+FAILED 的 actual) - reserved - budget*reservePct；超预算判定用 `>`（等于不触发）；WARN 只追加 `[BUDGET-WARN]` note 照样 RESERVED；CAP 抛 BudgetExceededException（带 estimated/usable）；refund 释放冻结额度。
6. `summarize()`：from/to 为闭区间（含等于边界）；countByStatus 预置 5 个状态全 0；COMPLETED/FAILED 的 actualUsd 为 null 按 0 计不 NPE。

## 修的 dpsk 编造（2 处）
- A/B 两批均编造 `com.dramafactory.repository.ProjectRepository`（实为 `DramaProjectRepository`），编排按源码替换 3 处（import/字段/mock）。

## 产品缺口（诚实记录，排期）
- **审批门无超时机制**：WAITING_APPROVAL 可永久卡住，代码里无任何 timeout/stale 逻辑（grep 确认）。prometheus 告警规则里有"审批卡住"告警（v2.4），但无自动超时策略。排期：`drama.approval.timeout-hours` 配置 + 超时后自动转人工提醒/升级，待产品确认超时语义（自动拒绝 vs 仅告警）。
- docs/TECH_DEBT.md 仍不存在（2026-10-16 轮计划建但 step193plan 文风不达标未收录）；本轮缺口清单暂记于此。

## 验证
- 指定三件套：59/59 全绿（ShotContinuityCheckerDeepTest 17 + CostLedgerFailureDeepTest 15 + PipelineTemplateServiceDeepTest 27）。
- 全量 `mvn test`：见 PROJECTS.md 本轮条目（数字以实际跑完为准）。
- 新测试 3 文件：待全量跑完后单独跑（37 例）确认。
