# 生产检查清单报告：UsageService.byRun limit 参数服务层收紧

## 1. 改动摘要
- 服务层 UsageService.byRun 收紧 limit 参数校验：当 limit 小于 1 或大于 500 时抛出 IllegalArgumentException，错误消息逐字为“limit 参数非法”。
- 删除 effectiveLimit 中间变量与不再使用的 DEFAULT_RUN_LIMIT 常量。
- byRun 的 Javadoc 增加 limit 范围说明。
- 控制器与前端代码无改动。

## 2. 验收范围
- **单元与靶向测试**：
  - 新增 UsageServiceByRunLimitValidationTest：5 例全绿。
  - 改写 UsageServiceTest（D1）与 UsageServiceByRunDeepTestR4（2 个旧语义用例）：断言改为验证抛出异常，全绿。
  - 靶向合跑范围：UsageServiceByRunLimitValidationTest（5 例）、UsageServiceTest（39 例）、UsageServiceByRunDeepTestR4（12 例）、UsageControllerDeepTest（20 例），合计 76 例全绿，0 失败。
- **真实服务冒烟**：本轮未做。

## 3. 对照表
| 维度 | 结论 | 理由 |
|---|---|---|
| 可靠性 | 通过 | 服务层参数校验收紧并删除无效回退逻辑，消除上下游行为不一致，提升系统整体可靠性。 |
| 可观测性 | 不适用 | 本轮仅调整服务层参数校验与删除常量，未涉及日志、监控或指标埋点改动。 |
| 数据 | 不适用 | 本轮无数据库表结构变更、无数据迁移、无接口 schema 变更。 |
| 部署 | 不适用 | 纯代码逻辑修改，无新增依赖或外部服务配置变更，不影响部署流程。 |
| 安全 | 通过 | 服务层拒绝非法 limit 参数并抛出明确异常，防止异常参数导致的资源滥用或内部状态泄露。 |
| 可维护性 | 通过 | 删除未使用的中间变量与常量，补充 Javadoc 范围说明，降低后续维护认知负担。 |

## 4. 已知限制
- 全量测试套件本轮未跑，仅完成上述靶向合跑验证。
- 真实服务冒烟本轮未做。
- UsageService.requests 服务层 limit 非正返回全量的旧口径本轮未动。
- UsageService.byDay 的 days 等于 0 默认 30 天的旧口径本轮未动。
- 前端 usage.js 只发 limit=20，不受本次服务层校验收紧影响。
