# 发版对照报告：Skill 列表 sort 参数收紧（drama-factory）
| 验收项 | 结论 | 理由 |
| 可靠性 | 通过（靶向范围） | 靶向 5 类 75/75 全绿：SkillListSortValidationTest 8/8、SkillServiceListBranchTest 10/10、SkillServiceV220BTest 17/17、SkillServiceDeepTest 20/20、SkillControllerDeepTest 20/20。 |
| 可观测性 | 符合预期 | 非法参数被全局异常处理器成功拦截并返回 HTTP 400，测试已验证状态码拦截机制生效。 |
| 数据与状态 | 无影响 | 本次迭代无 Schema 和版本变更，仅在接口边界处增加了请求参数校验。 |
| 部署与运维 | 无变更 | 前端未改动且仅发送合法值，后端变更为纯代码级校验逻辑，不增加部署负担。 |
| 安全与健壮性 | 提升 | 通过抛出 IllegalArgumentException 明确了异常边界，有效拦截了异常的排序参数，提升了接口健壮性。 |
| 可维护性 | 提升 | 集中定义合法值并拒绝其余选项，使得代码契约更加明确，降低了后续维护的心智负担。 |
## 已知限制
1. 全量测试套件本轮未执行，仅完成靶向测试类验证；
2. 真实服务冒烟本轮未开展，验证基于 MockMvc 全链路。
