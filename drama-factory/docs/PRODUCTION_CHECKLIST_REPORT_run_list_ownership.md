# 生产检查清单报告：运行列表按用户归属过滤

| 验收项 | 结论 | 理由 |
| --- | --- | --- |
| 可靠性 | 通过 | 新增 `RunListOwnershipTest` 1 例，覆盖本人运行入选、他人运行与孤儿运行排除、stats 总数同口径，1/1 全绿；关联复验 `RunServiceDeepTest` 的 `listRuns` 与 `stats` 空库 2 例 + `RunControllerTest` 11 例，合计 13/13 全绿。过滤逻辑由 `stats()` 与 `listRuns()` 共用同一 private helper `currentUserOwnedProjectIds()`，不会出现两处口径漂移；排序规则（创建时间倒序、空值最后）保持不变。 |
| 可观测性 | 部分通过 | 接口语义已通过 `@Operation` summary 由“列出全部运行”改为“列出当前用户的运行”在 API 文档层面显式化，调用方可据文档预期结果。但本轮未在真实服务上做冒烟验证，运行时日志与指标侧未做额外观察。 |
| 数据与状态 | 通过 | 无 schema 变更、无数据迁移；过滤为查询期行为，不修改任何已有数据。`projectId` 为空或不在当前用户归属集合中的 Run 被排除，其余 Run 的返回内容与排序不变。 |
| 部署与运维 | 通过 | 无版本号升级、无配置项新增、无 schema 变更，属常规代码发布；回滚只需回退本次代码变更。 |
| 安全与健壮性 | 通过 | 列表不再露出他人项目运行：`listRuns()` 在排序前加入与 `stats()` 完全相同的归属过滤，`GET /api/runs` 只返回当前用户名下项目的 Run，孤儿运行（`projectId` 为空或项目已不在归属集合中）同样被排除。 |
| 可维护性 | 通过 | 归属判定逻辑集中在 private helper `currentUserOwnedProjectIds()`，`stats()` 与 `listRuns()` 复用同一实现，避免重复代码；`RunController` 的 `@Operation` summary 同步更新，文档与行为一致。 |

## 已知限制

- 全量测试套件本轮未跑，仅执行了新增用例与关联复验用例（合计 13/13 全绿）。
- 真实服务冒烟未做；验证方式为 MockMvc 之外的 Spring Boot 集成测试 + H2 内存库，未覆盖生产数据库与真实部署环境。
- 既有 `RunServiceDeepTest.listRuns_shouldReturnAllSortedByCreatedAtDesc` 用例名未改，但其夹具均为当前用户自建运行，断言在本次过滤逻辑下仍成立；用例名与实际语义的偏差留待后续整理。
- 模型链：代码与测试批走 BotsRouter 讯飞星辰 spark-x2.6；文档批（CHANGELOG 与本报告）走七牛免费版 qiniu/conatus-free；另有 1 通讯飞文档批 240 秒零字节超时、无用量回执、未记账。
