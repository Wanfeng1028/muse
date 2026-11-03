# ledger v2.10 发版对照报告

**结论：可发版。** 本轮为纯加法交付：补齐 POST /api/bills/ocr 全路径埋点（关闭 v2.9 §8 遗留限制）、新增 pip 依赖定期扫描本地脚本与配套 workflow、完成 tesseract 真实安装实测并如实记录、同步 PROJECTS.md ledger 节、补 CHANGELOG v2.10 节并将版本号由 2.1.0 统一 bump 至 2.10.0。无 schema 变更、无 API 行为变更、无既有指标名/HELP 语义变更。测试与冒烟结果见占位符 pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract） / ruff check 全洁；本轮新增/改动文件 ruff format 全洁（10 个历史未格式化文件保持原样未动） / 真实服务冒烟（uvicorn 真实进程，mock provider，LEDGER_DB 独立）：建账户 201 → 记一笔 200 → POST /api/bills/ocr 有效 PNG → 200（review_id=1 入审核队列）→ 非图片 .txt → 422 → GET /api/metrics 验证 ledger_bills_ocr_requests_total{result="ok"}=1/{result="error"}=1、ledger_bills_ocr_failures_total{reason="unsupported"}=1、直方图 count=2 → POST /api/statements/ocr → 200（旧端点不受影响，ledger_ocr_* 照常渲染）→ /api/health version=2.10.0 → 备份 → 删库 → 恢复 → 账户/交易/review 数据一致。，tesseract 实测结论见 2026-10-17 实测：`apt-get update` 执行 10 分钟无任何输出（apt 源不可达，与已知 apt 源损坏一致），已终止；`which tesseract` 无 binary；全盘仅找到冒烟垫片 ~/workspace/muse-build/w2b/shim/tesseract（POSIX shell 脚本，输出固定 CSV，非真实识别）。结论：环境仍无真实 tesseract，ledger_ocr_confidence_avg / ledger_bills_ocr_confidence_avg 继续诚实为 0；OCR 识别率真实语料验证暂无法执行，仍为已知限制。。

## §1 可靠性

- 全量测试：pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract）。本轮新增 tests/test_bills_ocr_metrics.py，覆盖新端点埋点的成功/失败路径与两实例计数隔离断言。
- 失败路径覆盖：新 ocr_bill 包装采用前置变量 + finally 结构，不依赖 else 分支，确保异常路径下请求计数、失败计数与耗时观测均被写入，避免 v2.9 之前旧端点无埋点导致的观测盲区。
- 错误处理：_ocr_bill_impl 保持原有业务语义不变（校验、调用、返回结构逐字未动），包装层仅做埋点，不改变任何异常类型与 HTTP 状态码，失败原因归入固定 reason 枚举。
- 数据库迁移：本轮无 schema 变更，无迁移脚本，无数据回填。
- 兼容性：旧函数名与 ledger_ocr_* 指标名/HELP 逐字不变，v2.9 已发布的仪表盘与告警规则无需调整。

## §2 可观测性

- 结构化日志：本轮不新增日志字段，沿用既有结构化日志配置。
- 新增指标集（POST /api/bills/ocr 全路径）：
  - ledger_bills_ocr_requests_total{result="ok"|"error"}：请求总数，按结果维度拆分。
  - ledger_bills_ocr_failures_total{reason="unavailable"|"unsupported"|"invalid"|"oversize"|"internal"}：失败总数，按原因维度拆分，reason 为闭集。
  - ledger_bills_ocr_duration_seconds：请求耗时直方图。
  - ledger_bills_ocr_confidence_avg：OCR 置信度均值，无样本时保持 0。
- 暴露方式：沿用既有 /metrics 暴露路径。metrics.py 中新增独立 try/except 追加渲染，新指标渲染失败不影响既有指标输出，反之亦然。
- 改名说明：ocr_metrics.py 重构为 _OcrMetrics(prefix) 类，以 prefix 参数化实例；旧模块级函数名保持不变，旧指标名 ledger_ocr_* 及其 HELP 文本逐字不变，实现为旧实例与新实例分别持有各自计数器，两实例计数隔离，互不污染。

## §3 数据与状态

- 本轮无数据库 schema 变更，无字段增删，无索引调整。
- 无持久化状态迁移，无缓存键变更，无队列/任务语义变更。
- 指标为进程内计数，重启清零，属既有行为，本轮未改变（详见 §8）。
- 版本号状态：pyproject、health.py、测试断言、OPERATIONS.md 两处由 2.1.0 统一 bump 至 2.10.0，四处一致。

## §4 部署与运维

- 部署形态不变，无新增运行时依赖（deps_scan.py 仅使用标准库）。
- 新增运维入口：make deps-scan，调用 scripts/deps_scan.py。
- 新增定期任务：.github/workflows/deps-scan.yml，每周一 03:00 UTC 触发，continue-on-error，当前置于 ledger/.github，待 gh token 补齐 workflow 权限后迁移至仓库根目录（详见 §8）。
- 版本号统一 bump 至 2.10.0，OPERATIONS.md 两处同步更新。
- 本轮无停机要求，无回滚脚本变更需求。

## §5 安全与健壮性

- 依赖安全：scripts/deps_scan.py 读取 pyproject 依赖，调用 pip list --outdated 与 OSV querybatch 查询 CVE，退出码约定 0（无问题）/1（发现问题）/2（环境不可用，如网络或工具不可达），便于 CI 与本地一致判定。
- 端点健壮性：新埋点包装不改变原有输入校验与错误映射；reason 枚举为闭集，避免高基数标签膨胀。
- 指标渲染健壮性：metrics.py 中新增独立 try/except，单点渲染异常不导致整体 /metrics 不可用。
- 未新增外部网络调用至运行时路径；deps_scan 为离线/定期场景工具，不在服务请求链路中。

## §6 可维护性

- API 契约：无变更。POST /api/bills/ocr 的请求体、响应体、状态码、错误语义均与 v2.9 一致，本轮为纯埋点加法。
- 文档同步：新增 docs/DEPENDENCY_SCAN.md；CHANGELOG 增补 v2.10 节；PROJECTS.md ledger 节同步至最新，补记 v2.6/v2.7/v2.8.1/v2.9 状态与里程碑，追加 v2.8.1/v2.9 增量关系注记与版本号混乱史注记；OPERATIONS.md 版本号两处更新。
- 代码结构：ocr_metrics.py 由模块级函数重构为 _OcrMetrics(prefix) 类，消除重复实现，新增指标接入成本降低；bills.py 中 ocr_bill 拆分出 _ocr_bill_impl 并保留同名包装，调用方零改动。
- 技术债：workflow 暂置于 ledger/.github 待迁移（§8）；deps_scan 需联网（§8）；tesseract 未安装场景下 confidence_avg 恒为 0（§8）。

## §7 本轮交付清单

| 批次 | 交付内容 | 测试数字 |
| --- | --- | --- |
| L1 | POST /api/bills/ocr 全路径埋点：新增 ledger_bills_ocr_requests_total / ledger_bills_ocr_failures_total / ledger_bills_ocr_duration_seconds / ledger_bills_ocr_confidence_avg；ocr_metrics.py 重构为 _OcrMetrics(prefix)，旧函数名与 ledger_ocr_* 指标名/HELP 逐字不变，两实例计数隔离；bills.py 拆分 _ocr_bill_impl + ocr_bill 包装（前置变量 + finally）；metrics.py 独立 try/except 追加渲染；新增 tests/test_bills_ocr_metrics.py | pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract） |
| L2 | pip 依赖定期扫描本地脚本版：scripts/deps_scan.py（标准库，pyproject 依赖 + pip list --outdated + OSV querybatch，exit 0/1/2）；docs/DEPENDENCY_SCAN.md；make deps-scan；.github/workflows/deps-scan.yml（每周一 03:00 UTC，continue-on-error，暂置 ledger/.github） | pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract） |
| L2 | tesseract 真实安装实测（apt 源情况、是否装上、装不上时的诚实结论） | 2026-10-17 实测：`apt-get update` 执行 10 分钟无任何输出（apt 源不可达，与已知 apt 源损坏一致），已终止；`which tesseract` 无 binary；全盘仅找到冒烟垫片 ~/workspace/muse-build/w2b/shim/tesseract（POSIX shell 脚本，输出固定 CSV，非真实识别）。结论：环境仍无真实 tesseract，ledger_ocr_confidence_avg / ledger_bills_ocr_confidence_avg 继续诚实为 0；OCR 识别率真实语料验证暂无法执行，仍为已知限制。 |
| 文档 | PROJECTS.md ledger 节同步（补 v2.6/v2.7/v2.8.1/v2.9 状态与里程碑 + v2.8.1/v2.9 增量关系注记 + 版本号混乱史注记）；CHANGELOG v2.10 节；版本号统一 bump 2.1.0→2.10.0（pyproject/health.py/test 断言/OPERATIONS.md 两处） | pytest 全量 290 通过、1 跳过（跳过的是既有用例：环境无 tesseract） |
| 校验 | ruff 静态检查 | ruff check 全洁；本轮新增/改动文件 ruff format 全洁（10 个历史未格式化文件保持原样未动） |
| 校验 | 端到端冒烟 | 真实服务冒烟（uvicorn 真实进程，mock provider，LEDGER_DB 独立）：建账户 201 → 记一笔 200 → POST /api/bills/ocr 有效 PNG → 200（review_id=1 入审核队列）→ 非图片 .txt → 422 → GET /api/metrics 验证 ledger_bills_ocr_requests_total{result="ok"}=1/{result="error"}=1、ledger_bills_ocr_failures_total{reason="unsupported"}=1、直方图 count=2 → POST /api/statements/ocr → 200（旧端点不受影响，ledger_ocr_* 照常渲染）→ /api/health version=2.10.0 → 备份 → 删库 → 恢复 → 账户/交易/review 数据一致。 |

## §8 已知限制

- tesseract 未安装时，ledger_bills_ocr_confidence_avg 恒为 0：该值为无样本时的默认输出，不代表真实识别质量，属诚实呈现；tesseract 真实安装实测结论见 2026-10-17 实测：`apt-get update` 执行 10 分钟无任何输出（apt 源不可达，与已知 apt 源损坏一致），已终止；`which tesseract` 无 binary；全盘仅找到冒烟垫片 ~/workspace/muse-build/w2b/shim/tesseract（POSIX shell 脚本，输出固定 CSV，非真实识别）。结论：环境仍无真实 tesseract，ledger_ocr_confidence_avg / ledger_bills_ocr_confidence_avg 继续诚实为 0；OCR 识别率真实语料验证暂无法执行，仍为已知限制。。
- 指标为进程内计数，进程重启后清零：属既有行为，本轮未改变，长期趋势需依赖外部时序库按抓取周期累积。
- scripts/deps_scan.py 需联网：pip 索引或 OSV 服务不可达时，脚本以 exit 2 诚实退出并提示环境不可用，不伪造扫描结论。
- .github/workflows/deps-scan.yml 当前位于 ledger/.github，尚未迁移至仓库根目录：待 gh token 补齐 workflow 权限后迁移，迁移前该 workflow 不生效。
- 本轮无 schema 变更、无 API 行为变更，故无对应回滚演练项；回滚等价于回退代码版本。
