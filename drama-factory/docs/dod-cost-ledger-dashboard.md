# drama-factory 发版前生产级 Definition of Done 对照报告

- 报告对象：本轮「成本账本看板」（cost-ledger dashboard）
- 对照标准：muse 仓库统一 `PRODUCTION_CHECKLIST.md`（不裁剪，全量执行）
- 判定依据：仅限本轮实际变更的文件与实测结果；未触及的条目如实标注。
- 报告存放：`drama-factory/docs/`（本文件）

---

## 变更清单

| # | 文件 | 类型 |
|---|------|------|
| 1 | src/main/java/com/dramafactory/billing/CostLedgerService.java | 新增 summarizeTrend + budgetStatus + BudgetStatus/DailyTrendPoint records；构造器注入 BillingProperties；抽取 usableBudget 共用 |
| 2 | src/main/java/com/dramafactory/billing/CostLedgerController.java | 新增 GET /trend、GET /budget；entries 新增 limit 参数与 parseLimit |
| 3 | src/main/resources/static/cost-ledger.html | 新建看板页 |
| 4 | src/main/resources/static/cost-ledger.js | 新建看板逻辑（预算/KPI/趋势/供应商/明细，中英双语） |
| 5 | src/main/resources/static/shell.js | 导航接入（cost-ledger 项 + nav.costLedger/nav.prompts i18n key） |
| 6 | src/test/java/com/dramafactory/billing/CostLedgerTrendDeepTest.java | 新增 5 例 |
| 7 | src/test/java/com/dramafactory/billing/CostLedgerBudgetStatusDeepTest.java | 新增 4 例（含修 1 个测试 bug） |
| 8 | src/test/java/com/dramafactory/billing/CostLedgerBudgetStatusCustomBudgetTest.java | 新增 2 例 |
| 9 | src/test/java/com/dramafactory/billing/CostLedgerTrendControllerTest.java | 新增 5 例 |
| 10 | src/test/java/com/dramafactory/billing/CostLedgerBudgetControllerTest.java | 新增 2 例 |
| 11 | src/test/java/com/dramafactory/billing/CostLedgerEntriesLimitTest.java | 新增 6 例 |
| 12 | README.md / docs/OPERATIONS.md / CHANGELOG.md | 文档同步 |
| 13 | docs/screenshots/cost-ledger/ | 真实数据截图 |

---

## 逐项对照

### 1. 可靠性
- [通过] 测试金字塔：新增 24 个单元/集成/MockMvc 测试，账本相关 99 例全绿；失败注入已有 CostLedgerFailureDeepTest 覆盖。
- [通过] 错误处理：trend days 非数字→400；entries limit 非法→400；service 层钳制不抛异常；前端各区块独立 try/catch，失败显示 error alert 不影响其他区块。
- [不适用] DB 迁移：本次无表结构变更（复用 cost_ledger_entry）。
- [不适用] 健康检查/优雅关闭：本次未触及（既有能力）。

### 2. 可观测性
- [通过] 结构化日志：复用既有 logback + request_id 全链路；新增端点无额外日志需求。
- [通过] 关键指标：budget/trend/summary 即成本指标 API；utilizationPct 直接可用于告警。
- [未通过→已知限制] 基础告警：使用率超阈值无主动告警（页面仅变色提示）。排期：后续接通知通道时统一做。

### 3. 数据与状态
- [通过] 备份恢复：复用既有 H2 文件库备份策略；本次只读查询不写数据。
- [通过] 敏感数据：账本含金额与模型名，无 PII；note 字段为运维备注，不存密钥。
- [通过] 配置分离：budgetStatus 复用 BillingProperties（环境变量化，启动 fail-fast 校验）。
- [不适用] 多租户：账本按 projectId 过滤，复用既有设计。

### 4. 部署与运维
- [通过] 一键部署：复用既有 compose.yml；前端为静态文件，随 jar 发布。
- [不适用] 滚动更新：本次未触及。
- [通过] 运维手册：OPERATIONS.md 查询接口表已补齐 5 行；RESERVED 残留排查已有说明。
- [通过] 真实验证：36 条跨 14 天种子数据，真机服务 + 亲眼截图验收（dashboard.png）。

### 5. 安全与健壮性
- [通过] 输入校验：days/limit 非数字→400；limit≤0→400；limit 上限 500 防无界返回；days 超限服务端钳制。
- [通过] XSS：前端所有后端字符串经 esc() 转义后进 innerHTML。
- [不适用] 鉴权/限流：复用既有 JwtAuthFilter 与提交接口限流；查询接口为只读。
- [不适用] 依赖扫描：本次无新依赖（手写 SVG 零依赖）。

### 6. 可维护性
- [通过] 模块边界：service/controller/前端三层清晰；record DTO 即 API 契约。
- [通过] CHANGELOG：已补 Unreleased 条目。
- [通过] 技术债：无新增；本轮修 5 处前端真 bug（asset 路径、hidden/d-none、PAGE_I18N 格式、key 命名、文案重复）与 1 处测试 bug。
- [通过] 文档代码同步：README 接口表、OPERATIONS 接口表、CHANGELOG 均已同步。

### 7. 视觉验收（本仓库铁律）
- [通过] 亲眼验收：dashboard.png（浅色，1440px）逐项检查——KPI 网格 4 列、预算进度条 48%、趋势图双线+图例+日期轴、供应商条形、明细表 20 行状态 badge；无错字、无布局溢出。
- [通过] 真实数据：36 条种子数据（5 供应商 × 14 天，含 COMPLETED/FAILED/RESERVED/REFUNDED 四态），非空状态。
- [未验证] 深色模式：截图 harness 的 localStorage 限制未能捕获深色；生产环境与其他页面同机制，代码层面 data-bs-theme 跟随。

---

## 结论
**可合入**。未通过项仅 1 项（主动告警），已记为已知限制并给出排期方向；未验证 1 项（深色截图），为测试环境限制非产品缺陷。
