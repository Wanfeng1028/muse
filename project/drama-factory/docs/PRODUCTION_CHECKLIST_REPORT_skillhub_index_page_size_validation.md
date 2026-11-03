# 发版对照报告：SkillHub 索引 page/size 参数收紧（drama-factory）

| 验收项 | 结论 | 理由 |
|---|---|---|
| 可靠性 | 通过 | 定向测试 mvn -o test -Dtest=SkillHubPaginationTest,SkillHubIndexPaginationValidationTest,SkillHubIndexControllerTest 运行 Tests run 23, Failures 0, Errors 0, Skipped 0, BUILD SUCCESS；异常参数从静默钳制改为 HTTP 400，行为更明确。 |
| 可观测性 | 符合预期 | 未新增日志或监控；全局异常处理器沿用现有映射，错误通过 HTTP 400 暴露。 |
| 数据与状态 | 无影响 | 无 schema 变更；page/size 仅为查询参数，越界 page（99999）仍返回 200 空列表，未改变存储状态。 |
| 部署与运维 | 无变更 | 无部署步骤变更；变更为控制器入口校验，可随常规发布上线；本轮未运行全量测试套件。 |
| 安全与健壮性 | 通过 | 入口显式校验并抛 IllegalArgumentException，由全局处理器映射为 HTTP 400，非法参数（page < 0、size < 1 或 > 200、非整数）不再静默处理。 |
| 可维护性 | 通过 | 新增 SkillHubIndexPaginationValidationTest 6 例，更新 SkillHubPaginationTest 3 例，覆盖边界与异常值，降低回归成本。 |

## 已知限制
- 本轮未运行全量测试套件。
- 本轮未进行真实服务 HTTP 冒烟测试；验证仅为 MockMvc 全链路。
- 本轮无 UI 变更，故不适用视觉验收。
