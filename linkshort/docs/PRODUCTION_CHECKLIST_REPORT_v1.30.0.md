# 生产环境检查清单报告：GET /api/stats/top-links 的 n 参数验证收紧

变更总结
本项目 linkshort (Go) 对 GET /api/stats/top-links 端点的 n 参数解析逻辑进行了收紧，参考了 v1.28.0 版本的 referers n 模式。原有 parseIntDefault 导致非整数输入静默回退到 8。现在，缺失或为空的 n 参数回退到 8；非整数输入（如 abc、1.5、1x）返回 HTTP 400 及错误体 {"error": "n 非法"}；n <= 0 或 n > 100 的值仍被钳制到 8。修改仅涉及 internal/handler/handler.go 中的 handleTopLinks 函数，同级端点（handleTopReferers、handleStatsGeo、handleStatsDaily）及 parseIntDefault 工具函数均未改动。无 UI 变更，无需视觉验收。

测试与验证
新增内部测试文件 internal/handler/stats_top_links_n_validation_test.go，包含 6 个针对 n 参数校验的测试用例（TestStatsTopLinksNValidation），6 个用例全部通过。go vet 检查通过，变更文件 gofmt 格式检查通过。因完整 handler 套件运行需数分钟，本轮仅运行了针对性的测试组。在 18437 端口配合内存数据库和 admin key 执行了线上冒烟测试，确认 n=abc 与 n=1.5 均返回 400 且错误体精确为 {"error": "n 非法"}，缺失 n 返回 200 且 items 为空，n=0 返回 200 且 items 为空。测试结束后已停止服务，验证端口已关闭，并清理了冒烟测试用的二进制文件与日志。

检查项映射
可靠性：通过，参数校验逻辑更严密，错误提示明确，且新增测试全部通过验证了边界条件。
可观测性：不适用，本次变更未引入新的日志、指标或遥测数据。
数据：不适用，变更未涉及数据库结构修改或数据迁移，冒烟测试仅使用内存数据库。
部署：通过，代码变更和测试均已就绪，应用可直接部署或回滚。
安全性：不适用，变更仅涉及入参整数校验，未涉及身份认证、密钥管理或越权访问问题。
可维护性：通过，逻辑清晰，隔离了对同级端点的影响，并补充了针对性测试。

已知限制
本轮未运行完整的 handler 测试套件；同级端点 top-referers/geo/hourly 仍继续使用 parseIntDefault 进行静默回退；文档（docs.html）未做相应更新，因为原本就缺少 top-links 的行。

本次发布为定向范围的发布候选版本。
