# drama-factory 提示词库分页参数服务层收紧 发版对照报告

## 改动概述
- 改动：PromptLibraryService.list(q, tag, page, size) 服务层加校验：page < 0 抛 IllegalArgumentException("page 参数非法")，size < 1 或 size > 100 抛 IllegalArgumentException("size 参数非法")，全局处理器映射为 HTTP 400；控制器 GET /api/prompts/page 此前已按同口径返回 400，HTTP 行为不变；合法值、过滤、分页计算一字不动。
- 文件：改动 PromptLibraryService.java；新增 PromptLibraryServicePaginationValidationTest.java（7 例）；改写 PromptLibraryServicePagingTest.java（3 例）、PromptLibraryPagingBoundaryTest.java（3 例）、PromptControllerTest.java（1 处 Integer.MAX_VALUE 改为 100）。

## checklist 对照表
| 项目 | 结论 | 说明 |
| --- | --- | --- |
| 可靠性 | 通过 | 参数校验 fail-fast、全局 400 映射 |
| 可观测性 | 通过 | 异常消息含参数名、既有日志不变 |
| 数据 | 不适用 | 无 schema、无迁移 |
| 部署运维 | 不适用 | 无配置、无部署变更 |
| 安全 | 通过 | 非法输入不再静默接受 |
| 可维护 | 通过 | 改动面 5 个文件、文档同步 |

## 测试与验收
- mvn -o 靶向 PromptLibrary* 与 PromptControllerTest，160/160 全绿，BUILD SUCCESS。
- 新测 7/7、PagingTest 9/9、BoundaryTest 4/4、PromptControllerTest 4/4、分页 REST 边缘 11/11。

## 已知限制
- 本轮未跑全量测试套件。
- 未做真实服务 HTTP 冒烟（验证基于单元与 MockMvc/REST 边缘测试）。
- 无 UI 改动，视觉验收不适用。
- 无 schema 变更、无版本号升级。