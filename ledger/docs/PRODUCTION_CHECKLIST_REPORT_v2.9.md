# ledger v2.9 发版对照报告

**结论：可发版。** 本版为纯加法可观测性交付，补齐真正的 `ledger_`-前缀全路径 OCR 指标集，无 schema 变更、无 API 行为变更。pytest 全量 279 通过、1 跳过；ruff check 与 ruff format 全洁。

## §1 可靠性

- 全量测试：pytest 全量 279 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。
- 失败路径覆盖：新增 tests/test_ocr_metrics_v29.py（14 例），覆盖指标名/HELP、归一化、置信度校验、直方图桶、全路径 e2e 各分类、故障隔离。
- 错误处理：src/ledger/ocr.py 新增 OcrEmptyError(OcrFailedError)；TesseractOcrProvider._word_confidence_avg（TSV 解析，best-effort 永不抛错）与 last_confidence 属性；src/ledger/ocr_metrics.py 自身异常只记 warning 永不外抛；src/ledger/routers/statements.py 埋点异常只 warning。
- 数据库迁移：不适用（本版无 schema 变更）。

## §2 可观测性

- 结构化日志继承：沿用既有结构化日志，无变更。
- `ledger_ocr_requests_total{result="ok"|"empty"|"error"}` counter：POST /api/statements/ocr 全路径计数（每次请求都记，含 400/413/415 前置校验拒绝）。
- `ledger_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"}` counter：unavailable=tesseract 不可用（503）；unsupported=非图片类型（415）；invalid=请求非法（400）；oversize=超 5MB（413）；internal=其他。
- `ledger_ocr_duration_seconds` histogram：全路径请求耗时，buckets (0.05,0.1,0.25,0.5,1,2.5,5,10,+Inf)。
- `ledger_ocr_confidence_avg` gauge：tesseract TSV 词级置信度均值（0~1），运行平均；无样本时为 0。
- 暴露方式：GET /api/metrics，手写 Prometheus exposition。
- 改名说明：排期名 `ledger_ocr_requests_total{provider,status}` 当时为占位名，v2.8.1 实际交付的是 `ocr_requests_total`/`ocr_duration_seconds`；v2.9 交付真正的 `ledger_`-前缀全路径指标集。

## §3 数据与状态

- 无 schema 变更。
- 图片不落盘继承。
- 配置无新增。

## §4 部署与运维

- 继承既有部署方式，无新增依赖与配置。

## §5 安全与健壮性

- 埋点故障隔离：src/ledger/ocr_metrics.py 自身异常只记 warning 永不外抛；src/ledger/routers/statements.py 埋点异常只 warning。
- 鉴权：不适用（本地单用户）。

## §6 可维护性

- API 契约无变更。
- 文档同步：OPERATIONS.md §5 监控表格已更新（新指标说明 + v2.9 改名注记）。
- 技术债（已知限制）：tesseract 未安装时 confidence_avg 恒为 0（无样本，诚实）；旧端点 POST /api/bills/ocr 未埋点（本轮范围外）；指标为进程内计数，重启清零（既有行为）。

## §7 本轮交付清单

| 批次 | 交付内容 | 测试数字 |
| --- | --- | --- |
| L1a | 指标模块（src/ledger/ocr_metrics.py 重写：新指标集；record_ocr_request/record_ocr_failure/record_ocr_confidence，自身异常只记 warning 永不外抛） | pytest 全量 279 通过、1 跳过 |
| L1b | ocr.py（新增 OcrEmptyError(OcrFailedError)、TesseractOcrProvider._word_confidence_avg（TSV 解析，best-effort 永不抛错）与 last_confidence 属性） | pytest 全量 279 通过、1 跳过 |
| L1c | 埋点包装（src/ledger/routers/statements.py 原函数改名 _ocr_statement_preview_impl，新 ocr_statement_preview 包装做全路径埋点：OcrEmptyError→422/result empty；HTTPException 按状态码分类；埋点异常只 warning） | pytest 全量 279 通过、1 跳过 |
| L2 | 测试+文档（新增 tests/test_ocr_metrics_v29.py 14 例；删除被取代的 tests/test_ocr_metrics.py；OPERATIONS.md §5 监控表格已更新） | 新增 14 例；pytest 全量 279 通过、1 跳过 |
| 冒烟 | 真实冒烟（uvicorn 真实进程，mock provider）：POST /api/statements/ocr 有效 PNG→200；.txt→415；魔数非法→400；超 5MB→413；/metrics 验证 ledger_ocr_requests_total{result="ok"} 1、{result="error"} 3，failures unsupported/invalid/oversize 各 1，直方图 count 4 | 直方图 count 4 |

## §8 已知限制

- tesseract 未安装时 confidence_avg 恒为 0（无样本，诚实）。
- 旧端点 POST /api/bills/ocr 未埋点（本轮范围外）。
- 指标为进程内计数，重启清零（既有行为）。
- 过程注记（诚实记录）：L1a/L1c 首批输出因丢失行首缩进被打回重做；L1c 的 try/except/else/finally 结构有 bug（try 内直接 return 会跳过 else，导致成功请求误记 result="error"），冒烟前被单元测试发现，已修复并回归全绿。
