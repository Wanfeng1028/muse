# 更新日志

本项目更新日志遵循 Keep a Changelog 风格。

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
