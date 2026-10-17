# ledger v2.8 账单图片 OCR 录入发版对照清单

日期：2026-10-17

## 1. 可靠性

- [通过] pytest 全量结果：265 通过、1 跳过，跳过的是既有 test_ocr_tesseract.py 里 1 例"环境无 tesseract"，属既有用例，不是本轮改动引入。
- [通过] 本轮新增测试 15 例：tests/test_ocr_lines.py 8 例 + tests/test_statements_ocr_api.py 7 例，全部通过。
- [通过] 失败路径覆盖：坏图 400、超 5MB 413、非图片 415、识别空文本 422、缺 binary 503（含安装指引断言）、env 桩 501，均有用例。
- [通过] ruff check 与 ruff format 对本轮碰的文件全洁，无告警、无格式问题。
- [通过] 真实服务冒烟（mock provider）7 步全过：建账户 201 → OCR 预览 200（模板自动命中微信支付、4 行）→ 确认上传 200 → 确认批次 200 → 侦探队列 4 条 pending → 认领 200 → 记住为规则 1 条。
- [通过] 2 张截图亲眼验收：OCR 卡片态、识别预览态 4 行真实数据，均符合预期。

## 2. 可观测性

- [通过] 结构化日志与 request_id 沿用 v2.1 实现，本轮未动，行为不变。
- [通过] metrics 沿用 v2.1 实现，本轮未动。
- [未通过] OCR 专用 Prometheus 指标本轮未加。已知限制，排期：沿用 v2.5 报告里的排期，后续单独一轮补 OCR 识别耗时/成功失败计数指标。

## 3. 数据与状态

- [不适用] schema 变更：本轮无 schema 变更，无迁移脚本，此项不适用。
- [通过] 图片仅内存处理，不写盘、不存库，代码路径里没有落盘或入库分支。

## 4. 部署与运维

- [通过] OPERATIONS.md 本轮新增第 7 节 OCR，含 tesseract 安装指引、环境变量、不可用行为、图片限制。
- [通过] compose 配置沿用既有版本，本轮未改，无新增服务、无新增挂载。
- [通过] 备份恢复与优雅关闭沿用 v2.1 实现，本轮未动。

## 5. 安全与健壮性

- [通过] 上传校验：magic bytes 校验、5MB 大小上限、类型白名单，对应 415/413/400 失败路径均有用例。
- [通过] 缺 binary 时返回 503 并带安装指引，走 OcrUnavailableError，是本轮一等需求，不是降级路径。
- [不适用] 鉴权：单用户本地应用无鉴权，README 已声明，此项不适用。

## 6. 可维护性

- [通过] OCR 结果复用既有 statement 解析流，侦探队列集成复用既有接口（upload/confirm/claim/save_rule），无新表。
- [通过] 测试分层：ocr_lines 单元层 8 例 + statements OCR API 接口层 7 例，共 15 例。

## 7. 发版结论

- [通过] 结论：可发版。mock provider 链路完整，失败路径覆盖齐全，冒烟 7 步全过。
- [未通过] 真实 tesseract 路径待补冒烟：本机无 tesseract 二进制，TesseractOcrProvider.ocr_lines 的真实图片识别路径未在本机实测，只在单元测试里用 fake subprocess 覆盖了超时/非零退出/空文本分支。列为已知限制，排期：有 tesseract 的环境补一次真实图片冒烟。
- [未通过] OCR 专用 Prometheus 指标未加，列为已知限制，排期见第 2 节。

## 8. 本轮交付清单

- 新增接口：POST /api/statements/ocr（图片 OCR 预览，返回识别行）。
- 新增方法：ocr_lines（provider 侧识别入口）。
- 新增异常：OcrUnavailableError（缺 binary 时对应 503 + 安装指引）。
- 新增字段：ocr_text（确认上传时携带的识别文本）。
- 新增前端：statement.html 卡片态（OCR 卡片态、识别预览态）。
- 新增测试：tests/test_ocr_lines.py（8 例）、tests/test_statements_ocr_api.py（7 例）。
- 文档更新：OPERATIONS.md（新增第 7 节 OCR）、CHANGELOG、本清单 docs/PRODUCTION_CHECKLIST_v2.5.md。
