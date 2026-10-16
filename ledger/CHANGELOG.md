# 更新日志

本项目更新日志遵循 Keep a Changelog 风格。

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
