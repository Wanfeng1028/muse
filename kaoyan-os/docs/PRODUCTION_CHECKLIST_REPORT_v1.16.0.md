# kaoyan-os v1.16.0「专注三接口非整数参数返回 400」发版前 Definition of Done 对照报告

## 背景
- 版本：v1.16.0（2026-10-27 深耕轮，轮换队列轮到 kaoyan-os）
- 核心交付：apps/server/src/routes/focus.ts 三接口参数收紧（limit/days 非整数返回 400，正则 /^-?\d+$/，错误体 limit 参数无效 / days 参数无效，钳制与缺省不变）；新增测试 focus-param-validation.test.ts（10 例）；更新 3 个旧测试文件的 abc 断言；docs/API.md 同步 8 处；CHANGELOG.md 新增 [1.16.0] 一节。

## 变更清单表
| 变更文件 | 类型 | 说明 |
| --- | --- | --- |
| apps/server/src/routes/focus.ts | 修改 | 三接口参数收紧（limit/days 非整数返回 400，正则 /^-?\d+$/，错误体 limit 参数无效 / days 参数无效，钳制与缺省不变） |
| apps/server/tests/focus-concurrency.deep3.test.ts | 修改 | 更新 abc 断言 |
| apps/server/tests/focus.deep.test.ts | 修改 | 更新 abc 断言 |
| apps/server/tests/focus-summary-by-subject-days.test.ts | 修改 | 更新 abc 断言 |
| docs/API.md | 修改 | 同步 8 处 |
| CHANGELOG.md | 修改 | 新增 [1.16.0] 一节 |
| apps/server/tests/focus-param-validation.test.ts | 新增 | 10 例参数校验测试 |
| docs/PRODUCTION_CHECKLIST_REPORT_v1.16.0.md | 新增 | 本报告 |

## 逐条对照

### 1 可靠性
判定：通过（部分）
说明：服务端 vitest 全量 132 文件 935 测全绿；定向集（focus/stats/weekly/heatmap/api 共 21 文件）163 测全绿（已包含在全量内）；服务端 tsc --noEmit 零错。失败注入未单独做，仅参数非法路径有覆盖。

### 2 可观测性
判定：未验证
说明：结构化日志、request_id、指标暴露、告警未涉及。

### 3 数据与状态
判定：通过（部分）
说明：DB 迁移版本化未涉及；多用户相关测试在全量套件内全绿。

### 4 部署与运维
判定：未验证
说明：限流/超时/熔断、DB 迁移版本化未涉及。

### 5 安全与健壮性
判定：通过
说明：用户隔离与未登录 401 由全局认证钩子保证，本轮未改动；多用户相关测试在全量套件内全绿。

### 6 可维护性
判定：通过
说明：新增 focus-param-validation.test.ts（10 例）；更新 3 个旧测试文件的 abc 断言；docs/API.md 同步 8 处；CHANGELOG.md 新增 [1.16.0] 一节。

## 未做清单
- web 与 shared 两包的 tsc 未跑
- vite build 未跑（本轮无前端改动）
- 真实网络冒烟未做（验证走 Fastify inject + :memory: SQLite 库，未起真实端口服务）
- 视觉验收不适用（无 UI 改动）
- 结构化日志、request_id、指标暴露、告警未涉及
- 限流/超时/熔断未涉及
- DB 迁移版本化未涉及
- 失败注入未单独做（异常路径由参数校验测试覆盖，属于通过（部分）或未通过——按报告体例判为通过（部分）并说明只覆盖参数非法路径）
