# ledger v2.5 发版对照报告

**结论：进行中，不可发版。**

本轮（B1/B2/B3 三批）交付三项：OCR 抽象层、OCR 接口 + Mock 链路、拍照记账上传页。全量测试 209/209 通过，`ruff check` 全洁，视觉验收（真实服务截图 2 张）与 E2E（真实落一条交易）通过。

阻塞项：**真实 OCR 提供商未接入**——`LEDGER_OCR_PROVIDER=env` 且配置 key 后，`EnvOcrProvider.recognize` 诚实抛 `NotImplementedError`，不返回伪造结果。v2.5 完整里程碑的后续计划尚未排期，本轮只完成"抽象层 + Mock 链路 + 上传页"三项。

---

## 1. 可靠性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 全量测试 | 通过 | `pytest tests/` 209/209 通过；本轮新增 23 例（`tests/test_ocr.py` 11 例 + `tests/test_bills_ocr.py` 12 例） |
| 失败路径覆盖 | 通过 | 422（非法文件/超大文件/未配置 provider）、501（诚实桩）、500（非法 provider）各有测试用例 |
| 错误处理策略 | 通过 | 校验失败返回 422 且带明细消息；`EnvOcrProvider` 未实现时抛 `NotImplementedError` → 501，不伪造结果 |
| 数据库迁移 | 不适用 | 本轮无 schema 变更 |

## 2. 可观测性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 结构化日志 / request_id | 通过 | 复用既有机制（继承），本轮未改动 |
| OCR 专用指标 | 通过（v2.8.1 已交付） | 交付 `ocr_requests_total{result="ok"\|"unavailable"\|"error"}` 与 `ocr_duration_seconds`；排期名 `ledger_ocr_requests_total{provider,status}` 为占位名，实际交付名为 `ocr_requests_total` / `ocr_duration_seconds`；验证：`tests/test_ocr_metrics.py`、`GET /api/metrics` 真实冒烟 |

## 3. 数据与状态

| 项 | 结论 | 说明 |
| --- | --- | --- |
| schema 变更 | 不适用 | 本轮无 schema 变更 |
| 敏感数据（图片） | 通过 | 图片仅内存处理、不落盘：`await file.read()` 后直接传 provider，不写文件 |
| 配置密钥分离 | 通过 | `LEDGER_OCR_API_KEY` 走环境变量，`.env.example` 已新增该项注释 |

## 4. 部署与运维

| 项 | 结论 | 说明 |
| --- | --- | --- |
| docker-compose / 运维手册 | 通过 | 复用既有（继承），本轮未改动 |
| 环境变量样例 | 通过 | `.env.example` 已更新：新增 `LEDGER_OCR_PROVIDER` / `LEDGER_OCR_API_KEY` 两项注释 |

## 5. 安全与健壮性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 图片类型校验 | 通过 | content-type 非 `image/` 且扩展名不在 `.png/.jpg/.jpeg/.webp/.gif/.bmp` → 422"仅支持图片文件" |
| 图片大小上限 | 通过 | 空文件 → 422；>5MB → 422"图片超过 5MB 限制"，防内存耗尽 |
| 基础鉴权 | 不适用 | 本地单用户，README 已声明 |
| 限流 | 不适用 | 本地单进程 |

## 6. 可维护性

| 项 | 结论 | 说明 |
| --- | --- | --- |
| API 契约 | 通过 | `POST /api/bills/ocr`，multipart 字段 `file`；响应含 `mock`、`provider`、`merchant`、`amount_cents`、`occurred_on`、`candidates[{category_name, category_id, confidence}]`、`raw_text`；candidates 按名查库解析 `category_id`（命中"餐饮"/"购物"种子分类则带 id，否则 None），confidence 钳制 [0,1] |
| 文档同步 | 通过 | `README.md` 新增配置项与"### v2.5 账单图片 OCR 录入（进行中）"小节（写明真实 OCR 需用户自配外部 key、本轮只交付抽象层与 Mock）；`.env.example` 已更新 |
| 技术债 | 未通过 | ①真实 OCR 提供商接入未实现（阻塞项）；②OCR Prometheus 指标已在 v2.8.1 交付（实际指标名见上） |

## 7. 本轮交付清单

| 批次 | 交付物 | 测试数字 |
| --- | --- | --- |
| B1（OCR 抽象层） | 新文件 `src/ledger/ocr.py`（`OcrProvider` Protocol、`OcrResult` dataclass、`OcrError`/`OcrNotConfiguredError`/`OcrFailedError`、`MockOcrProvider`、`EnvOcrProvider`、`get_provider()`）；新文件 `tests/test_ocr.py`；`README.md` 更新；`.env.example` 更新 | 11 例全部通过 |
| B2（OCR 接口） | 新文件 `src/ledger/routers/bills.py`（`POST /api/bills/ocr`）；`src/ledger/main.py` 注册 bills.router；新文件 `tests/test_bills_ocr.py` | 12 例全部通过 |
| B3（拍照记账页） | 新文件 `src/ledger/templates/bills.html`；`main.py` 新增 `/bills` 页面路由；`base.html` 导航新增"拍照记账"；`static/app.js` 新增 `initBillsPage()`；`static/style.css` 新增 `.ocr-drop` 样式 | 视觉验收 2 张截图 + E2E 落一条交易（expense/招商银行/餐饮/6800 分/备注"拍照记账：星巴克臻选"） |

全量：`pytest tests/` 209/209 通过（本轮新增 23 例）；`ruff check` 全洁。

## 8. 已知限制与发版阻塞项

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 真实 OCR 提供商未接入 | 阻塞 | `LEDGER_OCR_PROVIDER=env` 且配置 key 后，`EnvOcrProvider.recognize` 抛 `NotImplementedError("真实 OCR 提供商接入尚未实现")`，不返回伪造结果。**v2.5 发版阻塞项，未排期** |
| Mock 返回固定结果 | 阻塞（受限） | `MockOcrProvider` 固定返回 merchant="星巴克臻选"/amount_cents=6800/candidates=[{"餐饮":0.92},{"购物":0.41}]/provider="mock"/mock=True，与输入图片无关；响应中 `mock: true` 明确标识 |
| OCR 可观测性指标缺失 | 已交付（v2.8.1） | 交付 `ocr_requests_total{result="ok"\|"unavailable"\|"error"}` 与 `ocr_duration_seconds`；排期名 `ledger_ocr_requests_total{provider,status}` 为占位名，实际交付名为 `ocr_requests_total` / `ocr_duration_seconds`；验证：`tests/test_ocr_metrics.py`、`GET /api/metrics` 真实冒烟 |
| v2.5 后续里程碑未排期 | 待办 | 本轮只完成"抽象层 + Mock 链路 + 上传页"三项，其余尚未排期 |
