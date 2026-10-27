# kaoyan-os v1.17.0「计划与真题分科汇总 days 参数收紧」发版前 Definition of Done 对照报告

## 背景
版本 v1.17.0（2026-10-27 深耕轮，轮换队列：上轮 botstalk 第 15 轮，本轮轮到 kaoyan-os）；核心交付：apps/server/src/routes/plans.ts 的 GET /api/plans/summary/by-subject 与 apps/server/src/routes/exams.ts 的 GET /api/exams/summary/by-subject 的 days 参数统一用正则判定整数，非整数返回 400，钳制与缺省语义不变；此前两接口对非法 days 静默回落为全部历史（并对 1.5 做截断），与 v1.16.0 专注三接口口径不一致，本轮对齐。

## 变更清单
| 文件 | 类型 | 说明 |
| --- | --- | --- |
| apps/server/src/routes/plans.ts | 修改 | 计划分科汇总 days 收紧 |
| apps/server/src/routes/exams.ts | 修改 | 真题分科汇总 days 收紧 |
| apps/server/tests/plans-summary-by-subject-days.test.ts | 修改 | 非法改 400，新增不传用例 |
| apps/server/tests/exams-summary-by-subject-days.test.ts | 修改 | 非法改 400，新增不传用例 |
| docs/API.md | 修改 | 计划与真题两处 days 描述同步 |
| CHANGELOG.md | 修改 | 新增 [1.17.0] 一节 |
| docs/PRODUCTION_CHECKLIST_REPORT_v1.17.0.md | 新增 | 本报告 |

## 实测数字
靶向测试 2 文件 12/12 全绿；服务端全量 vitest 132 文件 937 测全绿（耗时 887 秒，含 api-route-parity 5/5 与 api-docs-sync 3/3）；服务端 tsc --noEmit 零错。

## 逐条对照
### 1. 可靠性
- 判定：通过（部分）
- 说明：全量与靶向均全绿，tsc 零错；失败注入未单独做，仅参数非法路径有覆盖。

### 2. 可观测性
- 判定：未验证
- 说明：结构化日志、request_id、指标暴露、告警未涉及。

### 3. 数据与状态
- 判定：通过（部分）
- 说明：DB 迁移未涉及；多用户相关测试在全量套件内全绿；用户隔离与未登录 401 由全局认证钩子保证，未改动。

### 4. 部署与运维
- 判定：未验证
- 说明：限流、超时、熔断、DB 迁移版本化未涉及；Docker 与 Compose 未改动。

### 5. 安全与健壮性
- 判定：通过
- 说明：非法输入统一返回 400，不再静默回落；用户隔离与未登录 401 在测试内覆盖。

### 6. 可维护性
- 判定：通过
- 说明：CHANGELOG 与 API.md 已同步；技术债：热力图 months 仍用 Number 校验（"1.0"、"0x2" 等非纯数字串仍可通过），记为下一轮 kaoyan-os 待办，不在本轮扩面。

### 7. 发版前对照报告
- 判定：通过
- 说明：本报告即对照报告。

### 8. 周期机制
- 判定：未验证
- 说明：真实负载与故障演练本轮未做。

## 未做清单
无前端改动故无视觉验收；真实网络冒烟未做（验证走 Fastify inject 加 :memory: 库）；web 与 shared 两包 tsc 及 vite build 未跑；失败注入、真实负载、故障演练未做。