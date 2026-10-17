# 更新日志

本项目更新日志遵循 Keep a Changelog 风格。

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
