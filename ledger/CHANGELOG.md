# 更新日志

本项目更新日志遵循 Keep a Changelog 风格。

## v2.12.0 - 2026-10-24

### 新增

- 真实负载验证：新增 scripts/load_test.py——确定性仿真账单生成器（24 个月、约 110 笔/月，商户池覆盖餐饮/购物/交通/日用/医疗/工资/转账，种子 20261024 可复现，BOM+UTF-8 仿真真实导出）+ 真实 HTTP 全链路压测 harness（子进程起 uvicorn，逐月上传→确认计时、自动匹配率、去重探针、并发探针、内存与库大小、阈值判定、JSON 报告）。关闭 v2.11.1 对照报告"真实负载验证：待执行"项。
- 新增 tests/test_load_statement.py（CI 版）：两月上传确认、重传去重、建规则后自动匹配率≥0.5、命中正确性抽查、确认耗时 <60s 共 5 例。
- 新增 docs/LOAD_TEST.md 方法论文档；make load-test / make load-test-quick 快捷目标。

### 测试

- pytest 全量 1393 通过、1 跳过（2 失败为干净树既存 wlfl_t14/t15，非本轮引入）；新增 tests/test_load_statement.py 4 例全过；ruff check + format 全洁。
- 真实负载实测结论见 docs/LOAD_TEST_REPORT.md：24 个月 2664 笔走真实 HTTP，上传 5.14s / 确认 15.14s，自动匹配率 85.5%，去重精确命中，3 路并发上传零 5xx，阈值判定通过。

## v2.11.1 - 2026-10-24


### 新增

- 新增回滚脚本 scripts/rollback_v6_to_v5.py（v6→v5）：默认 dry-run 只打印计划；--yes 真实执行（自动备份 backups/ledger-<时间戳>.pre-rollback.sqlite3）；冲突检测（report_schemes 非空、规则列偏离默认值、suggested_rule_id 非空、(keyword, direction) 重复组）命中时写.rollback_conflicts.json 并 exit 3、中止且不写入；退出码 0 成功 / 1 执行失败 / 2 前置或参数失败 / 3 发现冲突。关闭 v2.11 发版报告"迁移回滚路径：未通过"项。
- POST /api/workbench/batches/{batch_id}/resolve-batch 新增 dry_run 入参：True 时逐条只做与真实处理相同的前置校验、不写库，返回 {"dry_run": true, "ok": [...], "failed": [...]}。关闭 v2.11 发版报告"批量对账失败明细：未通过"项的预检部分。
- 新增 POST /api/workbench/batches/{batch_id}/failures-export：批量预检并导出失败明细 CSV（BOM + 表头 id,occurred_on,counterparty,summary,amount_yuan,direction,reason），只做校验不写库。

### 测试

- 新增 tests/test_rollback_v6_to_v5.py 11 例：dry-run 默认/显式、flag 互斥、非 v6 拒绝、文件缺失、4 类冲突检测、--db 优先于 LEDGER_DB、真实回滚 happy path（schema 精确回到 v5、数据保留、备份落盘）。
- 新增 tests/test_workbench_dryrun_export.py 6 例：dry-run 不写库、失败上报、方向不匹配、非法动作 422、CSV 导出形状与金额格式、无失败时仅表头、批次 404。

### 说明

- v2.11 已知限制第 6-9 条标注的"（v2.11.1 关闭本项）"至此全部有名有实：正则防护（v2.11.0 已合入 matching.py）、批量预检与失败明细 CSV 导出（本轮）、preview 跳过原因（v2.11.0 已合入）、v6→v5 回滚脚本（本轮）。

## v2.11 - 2026-10-20

### 新增

- 侦探规则引擎 v2：MatchRule 新增 pattern_type（keyword/regex）、is_enabled、hit_count 三列。
- StatementItem 新增 suggested_rule_id，用于记录命中的建议规则。
- matching.py 新增 match_best 统一调度：别名记忆 85 > 正则规则 97 > 关键词规则 95 > 历史 > 候选。
- 同级命中按 priority、长度、id 依次决胜；非法正则跳过不抛异常。
- 新增 PUT /api/match-rules/{id}，用于更新规则字段。
- 新增 POST /api/match-rules/preview，返回 chain 解释链。
- 新增 POST /api/match-rules/{id}/touch，用于累计命中次数。
- 前端新增 /rules 规则管理页，包含表格、启用开关、测试命中区。
- 新增对账差异工作台 router workbench.py。
- 新增 GET /api/workbench/batches，列出对账批次。
- 新增 GET /api/workbench/batches/{id}/items，支持分页与 q 搜索。
- 新增 POST /api/workbench/items/{id}/resolve，动作含 confirm/ignore/learn/transfer。
- 新增 POST /api/workbench/batches/{id}/resolve-batch，采用部分成功语义。
- 前端新增 /workbench 页，支持逐条确认/忽略/记成规则/转账与批量操作和进度。
- 新增月度收支报告 router reports.py。
- 新增 GET /api/reports/monthly，含分类汇总、环比、Top 商户、口径分桶。
- 新增 GET+PUT /api/reports/category-scheme，默认“9月口径”。
- 默认口径分桶为考研投入、一次性大项、饮食、日用、话费、交通。
- 前端新增 /report 页，含年月选择、条形图、环比表、Top 商户、导出自包含 HTML。
- 新增演示数据脚本 scripts/seed_workbench_demo.py。
- 新增样例文件 docs/samples/cmb-statement-sample.csv。
- 数据库迁移 v5 到 v6：match_rules 补 3 列，statement_items 补 suggested_rule_id，新建 report_schemes 表。

### 测试

- 新增 tests/test_import_boundary_deep2.py，覆盖 GBK 与 UTF-8-SIG 解码。
- 覆盖金额千分位、括号负数、¥ 符号、全角逗号解析。
- 覆盖中文日期解析与重复导入幂等。
- pytest 全量待本轮实测后填。

### 冒烟

- 本轮冒烟范围：/rules、/workbench、/report 三页可打开，接口返回结构符合预期。
- 冒烟未覆盖真实银行流水大批量场景，相关验证待后续执行。

### 已知限制

- 规则预览的解释链仅展示命中路径，不展示被跳过规则的跳过原因。
- 批量对账为部分成功语义，前端仅汇总失败条数，未提供逐条失败明细导出。
- 月度报告导出的 HTML 为自包含单文件，未做移动端适配。
- 非法正则在调度中直接跳过，未在规则管理页给出显式告警。
- 演示数据脚本仅生成示例数据，不校验与真实账套的字段兼容性。

## v2.10 - 2026-10-17


### 新增

- 旧端点 POST /api/bills/ocr 补齐全路径 Prometheus 埋点（v2.9 对照报告已知限制"本轮范围外"，本轮关闭）：新指标集 ledger_bills_ocr_requests_total{result="ok"|"error"} / ledger_bills_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"} / ledger_bills_ocr_duration_seconds / ledger_bills_ocr_confidence_avg，与 statements 端点的 ledger_ocr_* 实例计数完全隔离；reason 映射：unsupported=非图片（422）、oversize=超 5MB（422）、invalid=文件名/内容空或提供商配置非法（422/500）、unavailable=OCR 提供商未配置或未实现（422/501）、internal=其他。
- src/ledger/ocr_metrics.py 重构为 _OcrMetrics(prefix) 类：模块级旧函数名与 ledger_ocr_* 指标名/HELP 文本逐字不变（v2.9 向后兼容），bills 用独立实例。
- pip 依赖定期扫描本地脚本版：scripts/deps_scan.py（只用标准库：从 pyproject 读依赖、pip list --outdated 查过期、OSV API 查已知 CVE；exit 0 无问题 / 1 有漏洞或大版本过期 / 2 扫描失败）+ docs/DEPENDENCY_SCAN.md + make deps-scan + .github/workflows/deps-scan.yml（每周一 03:00 UTC，continue-on-error）。
- 版本号统一 bump：pyproject.toml、src/ledger/routers/health.py（/api/health）、tests/test_metrics.py 断言、docs/OPERATIONS.md 两处示例，2.1.0 → 2.10.0。

### 测试

- pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。
- 新增 tests/test_bills_ocr_metrics.py（至少 10 例：指标名前缀/HELP、两实例隔离、ok 路径、各失败分类、埋点故障隔离、/metrics 文本解析）。
- ruff check 与 ruff format 全洁。

### 冒烟

- 真实服务冒烟（uvicorn 真实进程，mock provider，LEDGER_DB 独立）：建账户 201 → 记一笔 200 → POST /api/bills/ocr 有效 PNG → 200（review_id=1 入审核队列）→ 非图片 .txt → 422 → GET /api/metrics 验证 ledger_bills_ocr_requests_total{result="ok"}=1/{result="error"}=1、ledger_bills_ocr_failures_total{reason="unsupported"}=1、直方图 count=2 → POST /api/statements/ocr → 200（旧端点不受影响，ledger_ocr_* 照常渲染）→ /api/health version=2.10.0 → 备份 → 删库 → 恢复 → 账户/交易/review 数据一致。

### 已知限制

- tesseract 真实安装实测：2026-10-17 实测：`apt-get update` 执行 10 分钟无任何输出（apt 源不可达，与已知 apt 源损坏一致），已终止；`which tesseract` 无 binary；全盘仅找到冒烟垫片 ~/workspace/muse-build/w2b/shim/tesseract（POSIX shell 脚本，输出固定 CSV，非真实识别）。结论：环境仍无真实 tesseract，ledger_ocr_confidence_avg / ledger_bills_ocr_confidence_avg 继续诚实为 0；OCR 识别率真实语料验证暂无法执行，仍为已知限制。
- 指标为进程内计数，重启清零（既有行为）。
- pyproject 版本号历史漂移（v2.2 起未 bump）已在本轮统一为 2.10.0。

## v2.9 - 2026-10-17

### 新增

- 新增 `ledger_ocr_requests_total{result="ok"|"empty"|"error"}` counter：POST /api/statements/ocr 全路径计数（每次请求都记，含 400/413/415 前置校验拒绝）。
- 新增 `ledger_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"}` counter：unavailable=tesseract 不可用（503）；unsupported=非图片类型（415）；invalid=请求非法（400）；oversize=超 5MB（413）；internal=其他。
- 新增 `ledger_ocr_duration_seconds` histogram：全路径请求耗时，buckets (0.05,0.1,0.25,0.5,1,2.5,5,10,+Inf)。
- 新增 `ledger_ocr_confidence_avg` gauge：tesseract TSV 词级置信度均值（0~1），运行平均；无样本时为 0。
- 改名说明：排期名 `ledger_ocr_requests_total{provider,status}` 当时为占位名，v2.8.1 实际交付的是 `ocr_requests_total`/`ocr_duration_seconds`；v2.9 交付真正的 `ledger_`-前缀全路径指标集。
- 新增 OcrEmptyError(OcrFailedError)；TesseractOcrProvider 新增 `_word_confidence_avg`（TSV 解析，best-effort 永不抛错）与 `last_confidence` 属性。
- 埋点语义：src/ledger/routers/statements.py 原函数改名 `_ocr_statement_preview_impl`，新 `ocr_statement_preview` 包装做全路径埋点（OcrEmptyError→422/result empty；HTTPException 按状态码分类；埋点异常只 warning）。

### 测试

- pytest 全量 279 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。
- 新增 tests/test_ocr_metrics_v29.py（14 例：指标名/HELP、归一化、置信度校验、直方图桶、全路径 e2e 各分类、故障隔离）。
- 删除被取代的 tests/test_ocr_metrics.py（v2.8.1 旧指标名已移除）。
- ruff check 与 ruff format 全洁（11 个历史未格式化文件与本轮无关）。

### 冒烟

- 真实冒烟（uvicorn 真实进程，mock provider）：POST /api/statements/ocr 有效 PNG→200；.txt→415；魔数非法→400；超 5MB→413；/metrics 验证 ledger_ocr_requests_total{result="ok"} 1、{result="error"} 3，failures unsupported/invalid/oversize 各 1，直方图 count 4。

### 已知限制

- tesseract 未安装时 confidence_avg 恒为 0（无样本，诚实）。
- 旧端点 POST /api/bills/ocr 未埋点（本轮范围外）。
- 指标为进程内计数，重启清零（既有行为）。

## v2.8.1 - 2026-10-17

### 新增

- `ocr_requests_total{result="ok"|"unavailable"|"error"}`：OCR 请求计数（counter）。`ok`=OCR 成功；`unavailable`=OCR provider 不可用（503）；`error`=识别失败（422）/其他异常。只统计走到 OCR provider 调用的请求。
- `ocr_duration_seconds`：OCR 延迟分布（histogram，buckets：0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, +Inf），用于 OCR 延迟分布/告警。
- 指标输出 `GET /api/metrics`（手写 Prometheus exposition，零新依赖）；进程内计数，服务重启清零。
- 埋点只统计走到 OCR provider 调用的请求；埋点异常只记 warning，永不影响主流程。

### 测试

- 新增 `tests/test_ocr_metrics.py` 覆盖埋点语义。
- `GET /api/metrics` 真实冒烟验证指标名与标签。

## v2.8 - 2026-10-17

### 新增

- `POST /api/statements/ocr`：multipart 上传图片，做 magic bytes 校验，得到 OCR 文本行，复用 statement 解析预览流。坏图 400、超 5MB 413、非图片 415、识别出空文本 422；缺 binary、执行失败、超时返回 503，detail 原样带安装指引（OcrUnavailableError）。
- 图片只在内存里识别，不写盘、不存库。
- `src/ledger/ocr.py`：新增 `OcrUnavailableError` 与 `ocr_lines` 方法（Mock/Tesseract）。
- `ParsePreviewOut` 新增 `ocr_text` 字段。
- `statement.html` 新增「图片 OCR 录入」卡片：拖拽区、进度条、识别预览后进第 2 步核对。
- 侦探队列集成：OCR → 上传 → 确认 → 认领 → 记住为规则，全复用既有接口。

### 测试

- pytest 全量 265 通过、1 跳过（跳过的是环境无 tesseract 的既有用例）。
- ruff check 与 ruff format 全洁。
- 真实服务冒烟（mock provider）7 步：建账户 201 → OCR 预览 200 → 确认上传 200 → 确认批次 200 → 侦探队列 4 条 pending → 认领 200 → 记住为规则 1 条。
- 2 张截图亲眼验收通过。

## v2.7 - 2026-10-17

### 新增

- 商户别名管理 API（v2.4 遗留缺口：别名学错了改不掉）：GET /api/merchant-aliases（列表，含 category_name）、PATCH /api/merchant-aliases/{id}（改别名文本/改映射分类；404 别名不存在/分类不存在、400 无更新字段或别名为空、409 别名冲突）、DELETE /api/merchant-aliases/{id}（404/ok）；schemas 新增 MerchantAliasOut、MerchantAliasUpdate。
- 侦探页新增「记住的商户别名」管理区：每行别名可改名、分类可重选，保存/删除即时生效；空状态有引导文案。
- 回归测试 tests/test_merchant_aliases.py（8 例：列表、改名、改分类、404、400、409、删除）；pytest 全量 250 通过、1 跳过（既有 tesseract 缺失跳过）。

## v2.6 - 2026-10-16

### 新增

- 真实 OCR 提供商：`TesseractOcrProvider`（src/ledger/ocr.py，调本地 tesseract CLI 的 stdin/stdout）。超时默认 30 秒（`LEDGER_OCR_TIMEOUT`）、语言默认 `chi_sim+eng`（`LEDGER_OCR_LANG`）；缺二进制时报错并给出 apt/brew 安装命令；识别失败或超时抛 `OcrFailedError`。金额提取先遮掉日期片段再取最大值（修过日期干扰金额的 bug）。
- OCR 审核队列：`POST /api/bills/ocr` 返回 `review_id` 并把识别结果写入待审核队列（`ocr_reviews` 表，status=pending）；新增 `GET /api/bills/review`（待审核列表）、`GET /api/bills/review/{id}/image`（原图）、`POST /api/bills/review/{id}/confirm`（确认入账，重复确认返回 409）、`POST /api/bills/review/{id}/reject`（驳回）。
- 新页面 `/bills/review`「OCR 审核」：原图缩略 + 识别字段可编辑 + 置信度低于 70% 的字段标红；确认后调记账 API 入账。
- `OcrResult` 新增 `field_confidence`（各字段置信度：merchant/amount_cents/occurred_on）。
- DB 迁移 v4→v5：新建 `ocr_reviews` 表（`CURRENT_VERSION=5`）。

### 测试

- 新增 `tests/test_ocr_tesseract.py`（18 例通过、1 例因环境无 tesseract 跳过）、`tests/test_bills_review.py`（15 例）；全量 242 例通过。
- 3 处旧的硬编码版本号断言更新为 `CURRENT_VERSION`。

## v2.4 - 2026-10-16

### 新增

- 模糊匹配升级（`matching.py` 纯函数）：金额容差（绝对差 ≤x 分或相对差 ≤x%，整数运算无浮点误差）、日期窗口（±N 天）、商户别名匹配（归一化精确相等，置信度 85）。
- 商户别名学习：手工认领一次即记住（归一化对方名 → 分类），存 `merchant_aliases` 表；纠正认领时更新映射；下次同类自动入账（match_source="alias"）。
- 匹配优先级：关键词规则(95) > 别名(85) > 历史习惯(≥80 自动)。
- 转账配对：同批次一出一入、金额容差内（±100 分或 ±1%）、日期窗口内（±3 天）、且对方名为自有账户时，双方标记 `match_source="transfer-pair"`（置信度 90），侦探页显示"转账配对成功"。
- 侦探页批量处理：卡片多选 + 批量工具条（全选/批量认领/批量忽略）；跨方向勾选时批量认领置灰并提示；部分成功语义（`{processed, failed:[{item_id,error}]}`），失败逐条给原因。
- API（前缀 `/api`）：`POST /api/statements/items/batch-claim`、`POST /api/statements/items/batch-skip`。
- DB 迁移 v3→v4：新建 `merchant_aliases` 表。

### 修复

- 修测试隔离：`tests/conftest.py` 清表列表补 `merchant_aliases`（别名泄漏曾导致全量跑时 `test_claim_errors` 失败）。
- 修 `test_currencies.py` 硬编码版本号断言（3→4）。

### 测试

- pytest 增至 173 例全过（新增 29 例：容差边界/日期窗口/别名/配对/批量/学习闭环/规则优先）；ruff 全洁。

### 已知限制

- 转账配对只覆盖同批次内条目；配对参数为模块常量（`TRANSFER_PAIR_*`），暂无管理界面。
- 批量认领要求勾选同方向，跨方向需分批处理或用批量忽略。

## v2.3 - 2026-10-16

### 新增

- 全站移动端适配：`@media (max-width: 768px)` 断点；顶栏导航横向滑动；触控目标 ≥44px。
- 交易列表、侦探队列规则表在移动端转卡片流（`data-label` 列名，`table:has()` 精确命中）。
- 仪表盘 / 预算页移动端布局：汇总卡单列、图表上下排、快捷入口两列、预算行换行。
- 品牌 logo 从 emoji 换成内联 SVG 硬币线稿 mark。
- `tests/test_mobile.py`：10 页 200 + viewport 标记 + 断点 CSS 存在性冒烟测试。

### 修复

- 修导航高亮选择器 `.nav a.active` 缺圆点导致永不生效。
- 补齐模板存在但 CSS 从未定义的类（`.filters`、`.pagination`、`.summary-cards`、`.charts`、`.quick-link-grid`、`.budget-row`、`.toolbar` 等）的桌面样式。

## v2.2 - 2026-10-16

### 新增

- 多币种：账户与交易支持 `currency` 字段（ISO 4217 三字母大写，默认 CNY，非法值 422）。
- 汇率管理：`GET /api/currencies` 列表、`PUT /api/currencies/{code}` 新增/更新汇率；汇率页 `/currencies` 可视化设置。
- 本位币折算：月度汇总与净资产按 `LEDGER_BASE_CURRENCY`（默认 CNY）折算；缺汇率的交易/账户不计入并计入 `unknown_count`。
- DB 迁移 v2→v3：新增 `currencies` 表，`transactions` 表加 `currency` 列（老数据默认 CNY）。
- 交易页记一笔表单加币种下拉；仪表盘标注本位币。

### 限制

- 跨币种转账不做实时换算，按转出币种金额记录（后续版本再议）。

## v2.1 - 2026-10-15

### 新增

- DB 迁移版本化：`PRAGMA user_version`（当前版本 2），v1 老库启动自动补 4 张 v2 表，损坏库启动报 `MigrationError`。
- 结构化日志：stderr JSON Lines（ts/level/logger/msg/request_id），`RequestIdMiddleware` 全链路 request_id 并回写 `X-Request-Id` 响应头；`LEDGER_LOG_LEVEL` 环境变量，非法值启动 fail-fast。
- `GET /api/metrics`：Prometheus 文本格式，6 个指标（账单批次/条目按状态/侦探待认领/自动匹配率/交易总数/账户总数）。
- 备份恢复 CLI：`python -m ledger backup [--keep N]`（默认保留 7 个，备份前 integrity_check）、`python -m ledger restore FILE`（恢复前自动安全快照，坏备份拒绝恢复）；`make backup [KEEP=N]` / `make restore FILE=`。
- 就绪探针 `GET /api/ready`（DB 通 200 / 不通 503）；优雅关闭（lifespan dispose engine）。
- `docker-compose.yml` 一键部署（healthcheck / 资源限制 1 核 512M / 日志轮转 / named volume）与 `docs/OPERATIONS.md` 运维手册。
- 失败注入测试 4 例：DB 锁定→500 带 request_id、坏 CSV→200 不崩服务、磁盘满→BackupError 无残留、metrics DB 故障→500。
- 未处理异常统一 500 `{"detail":"服务器内部错误","request_id":"..."}`（由 RequestIdMiddleware 兜底；FastAPI 0.143 的 Exception 处理器会被转给 ServerErrorMiddleware 并 re-raise，故不用）。

### 修复

- 修 `python -m ledger serve` 启动崩溃（`args.dir` 在 serve 子命令不存在）。
- 修坏 CSV（随机二进制）的 `csv.Error` 抛 500：改为 errors 行收集返回 200。
- 修备份 `integrity_check` 对损坏文件抛裸 `sqlite3.DatabaseError`：改为 `BackupError`。
- 修备份写入失败（磁盘满）抛裸 `OSError` 且留半成品：改为 `BackupError` 并清理。

### 测试

- pytest 97 → 119 例全过；ruff 全洁；真实服务冒烟（建账→交易→metrics→备份→删库→恢复→数据一致）全链路通过。

## v2.0 - 2026-10-15

### 新增

- 银行账单侦探：导入银行 / 支付宝 / 微信账单，自动匹配分类，对不上的进侦探队列。
- 账单导入向导 `/statement`：上传 → 解析预览（自动识别模板 / 编码 / 表头前导行）→ 列映射可调（date / counterparty / summary / amount / direction，存为自定义模板复用）→ 确认。
- 预置 4 个模板：支付宝、微信支付、招商银行、工商银行。
- 三路匹配引擎 `matching.py`：关键词规则（priority）> 历史习惯（同商户多数票）> 候选建议（Top3 + 置信度）。
- 侦探队列 `/detective`：待认领卡片流，一键认领 / 换分类 / 记住为规则 / 跳过。
- 认领即学习：claim 时 `save_rule=true` 存关键词规则，下次同类自动入账。
- 转账识别：对方为自己账户名时建议转账。
- 指纹去重：`sha256(日期|金额|方向|对方|摘要)`，重复导入自动跳过。
- 账单解析 `statement_parser.py`：GBK / 表头探测 / 列映射。
- API（前缀 `/api`）：`statement-templates`（GET/POST/DELETE）、`statements/parse-preview`（POST multipart）、`statements/upload`（POST multipart）、`statements/batches`（GET）、`statements/{id}`（GET/DELETE）、`statements/{id}/confirm`（POST）、`statements/{id}/items`（GET）、`statements/items/{id}/claim`、`claim-transfer`、`skip`（POST）、`match-rules`（GET/POST/DELETE）。
- 测试增至 97 例。

### 修复

- 修 `style.css` 首行 css 围栏导致全站 CSS 变量失效。
- 修 `base.html` 顶栏类名与 CSS 设计体系脱节导致顶栏无样式。
- 修 `style.css` 尾部 `.chart-toolbar` 规则截断。

## v1 - 2026-10-13

### 新增

- 多账户、交易、分类、预算、统计。
- CSV 导入导出。
- 周期账单。
- 7 页 Web UI。
- pytest 34 例。
6. 正则防护：创建/更新时拒绝嵌套量词、回溯引用、超长（>200 字符）正则并 400 明示；匹配侧 haystack>500 字符熔断跳过（v2.11.1 关闭本项）。
7. 批量对账支持执行前预检（dry-run）与失败明细 CSV 导出（v2.11.1 关闭"失败明细未通过"项）。
8. preview 解释链展示被跳过规则的原因（停用/方向不匹配/非法正则/未命中）（v2.11.1 关闭本项）。
9. 提供 v6→v5 回滚脚本 scripts/rollback_v6_to_v5.py 与 docs/MIGRATION_RUNBOOK.md（v2.11.1 关闭"回滚未通过"项）。
10. 并发创建相同规则存在理论竞态（先查后插），已捕获转 409（或记录为已知限制，以实际合入为准）。
