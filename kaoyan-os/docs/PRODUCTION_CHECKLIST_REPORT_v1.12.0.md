# kaoyan-os v1.12.0「排期 v2 + 错题组卷 + API 契约文档」发版前 Definition of Done 对照报告

## 背景

- **版本**：v1.12.0（2026-10-20 深耕轮 lane H）
- **核心交付**：
  1. 智能排期 v2：`GET /api/plans/range`、`GET /api/plans/overload`，前端 `/plans/gantt` 甘特周视图（拖拽改期、超负荷预警）；
  2. 错题组卷：`POST /api/mistakes/quiz/generate`、`POST /api/mistakes/quiz/grade`，前端 `/mistakes/quiz`；
  3. API 契约文档 `docs/API.md` + `tests/api-docs-sync.test.ts` 同步测试；
  4. 深色模式查漏（全 11 页走查，先修 3 个真 bug，走查后又追加修 3 处：color-scheme 声明、NavLink 双高亮、品牌字断行）。
- **判定依据声明**：本报告所有判定**仅**基于本次版本事实（交付内容、测试清单、真 bug 修复、变更文件、未做清单）。凡本次版本事实未覆盖的条目，一律标注「未验证」或「未通过」，不做任何推测或补全。
- **标准声明**：判定取值限定为 通过 / 通过（部分）/ 未通过 / 未验证 / 不适用。测试通过性以「服务端 vitest 全绿、server/web/shared tsc 零错、vite build 成功」为准。

## 变更清单

| 类别 | 文件 |
| --- | --- |
| 服务端（新增） | `apps/server/src/schedule-stats.ts` |
| 服务端（修改） | `apps/server/src/routes/plans.ts`、`apps/server/src/routes/mistakes.ts` |
| 共享包（修改） | `packages/shared/src/index.ts` |
| 前端（新增） | `apps/web/src/pages/ScheduleGantt.tsx`、`apps/web/src/pages/Quiz.tsx` |
| 前端（修改） | `apps/web/src/api.ts`、`apps/web/src/App.tsx`、`apps/web/src/index.css` |
| 文档（新增） | `docs/API.md` |
| 文档（修改） | `README.md`、`CHANGELOG.md` |
| 测试（新增） | `tests/plans-range-overload.test.ts`（21 例）、`tests/mistakes-quiz.test.ts`（16 例）、`tests/api-docs-sync.test.ts`（3 例） |

## 逐条对照

### 1. 可靠性

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| 测试金字塔（单元层） | 通过（部分） | `tests/plans-range-overload.test.ts`（18 例）含纯函数 `computeDayLoads` / `kindOf` 的单元测试；其余层未见独立单元测试拆分。 |
| 测试金字塔（集成层 / HTTP 覆盖） | 通过 | 排期 range/overload 与错题组卷 generate/grade 均有 HTTP 集成测试覆盖（`tests/plans-range-overload.test.ts` 18 例、`tests/mistakes-quiz.test.ts` 16 例），服务端 vitest 全绿。 |
| 测试金字塔（E2E） | 未通过 | 本次版本事实中未列出任何 E2E 测试，属于未做范围。 |
| 失败注入 / 异常路径测试 | 未通过 | 未做清单明确「失败注入测试」未做。 |
| 幂等性 | 通过（部分） | auto-schedule 既有去重逻辑保留；`POST /api/mistakes/quiz/grade` 为原子写库。未对全部新接口（如 quiz generate）逐一验证重复调用语义。 |
| 用户隔离 | 通过 | range / overload / quiz 全部按 `user_id` 过滤，且有测试覆盖（对应 `tests/plans-range-overload.test.ts`、`tests/mistakes-quiz.test.ts`）。 |
| 类型与构建门禁 | 通过 | server/web/shared 三包 `tsc` 零错，`vite build` 成功。 |
| 真 bug 修复闭环 | 通过 | 修复 quiz generate 双反斜杠正则恒 400、subjectLabel 读错字段、`SUBJECTS as Record` TS2352 三类缺陷。 |
| 深色模式回归 | 通过（部分） | 全 11 页走查并修 6 处（3 个真 bug + 3 处走查追加修复）；但走查为人工方式，未沉淀为自动化视觉/回归测试。 |

### 2. 可观测性

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| 结构化日志 | 未通过 | 未做清单明确「结构化日志 / request_id」未做。 |
| 请求链路标识（request_id） | 未通过 | 同上，未做。 |
| 指标暴露 | 未通过 | 未做清单明确「指标暴露」未做。 |
| 告警 | 未通过 | 未做清单明确「告警」未做。 |
| 超负荷预警（业务侧可观测） | 通过（部分） | `GET /api/plans/overload` 与甘特周视图超负荷预警已交付，具备业务层提示能力；但属于面向用户的功能，不替代运维侧监控指标。 |

### 3. 数据与状态

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| 数据读写正确性 | 通过 | quiz grade 原子写库；quiz generate 恒 400 的正则缺陷已修复；range/overload 计算逻辑有 18 例测试覆盖。 |
| 共享类型契约 | 通过 | `packages/shared/src/index.ts` 更新，`SUBJECTS as Record` TS2352 已修复，三包 tsc 零错。 |
| DB 迁移版本化 | 不适用 | 未做清单说明 SQLite 无迁移框架，本次未引入。 |
| 备份恢复实测 | 未验证 | 存在备份导出 API，但本次未实测恢复流程。 |
| 状态一致性（拖拽改期） | 通过（部分） | 甘特周视图支持拖拽改期，属交付内容；但无 E2E 或失败注入覆盖，异常中断下的一致性未验证。 |

### 4. 部署与运维

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| 构建产物可用 | 通过 | `vite build` 成功，server/web/shared tsc 零错。 |
| 一键部署（Docker Compose） | 未通过 | 未做清单明确「Docker Compose」未做；README 有 Docker 节但非 Compose。 |
| 滚动更新 | 未通过 | 未做清单明确「滚动更新」未做。 |
| 限流熔断 | 未通过 | 未做清单明确「限流熔断」未做。 |
| 部署文档 | 通过（部分） | README 含 Docker 节，可支撑基础部署说明；但未提供 Compose 一键编排。 |

### 5. 安全

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| 用户数据隔离 | 通过 | range / overload / quiz 全部 `user_id` 过滤，且有测试覆盖。 |
| 输入校验（防止畸形入参） | 通过（部分） | quiz generate 正则缺陷修复消除了恒 400 的输入处理错误；但未做失败注入测试，边界与恶意输入未系统验证。 |
| 限流 / 防滥用 | 未通过 | 未做清单明确「限流熔断」未做。 |
| 密钥与敏感信息管理 | 未验证 | 本次版本事实未涉及密钥管理相关变更或验证。 |

### 6. 可维护

| 条目 | 判定 | 依据说明 |
| --- | --- | --- |
| API 契约文档 | 通过 | 新增 `docs/API.md`，覆盖本次新接口。 |
| 文档与实现同步保障 | 通过 | `tests/api-docs-sync.test.ts`（3 例）提供文档与实现的同步测试。 |
| 变更记录 | 通过 | `CHANGELOG.md` 已更新。 |
| 代码组织 | 通过 | 排期统计逻辑抽至 `apps/server/src/schedule-stats.ts`，前端新增独立页面组件 `ScheduleGantt.tsx`、`Quiz.tsx`。 |
| 技术债登记 | 通过（部分） | 未做项（E2E、失败注入、结构化日志/request_id、指标、告警、迁移版本化、Compose、滚动更新、备份恢复实测、限流熔断）已如实列出，构成本轮技术债清单；尚未见独立技术债文档沉淀。 |
| 前端样式一致性 | 通过（部分） | `index.css` 更新并完成 11 页深色模式查漏、修 6 处；无自动化视觉回归保障。 |

## 总体结论

**结论：有条件发版。**

本版本四项核心交付（排期 v2、错题组卷、API 契约文档与同步测试、深色模式查漏）均已落地，且具备可验证的通过性证据：服务端 vitest 全绿（40 例新增测试：21 + 16 + 3），server/web/shared tsc 零错，vite build 成功，用户隔离与新接口契约均有测试与文档支撑。在此范围内质量可接受。

**未通过项清单**（不允许发版后长期挂账）：

1. 失败注入测试 — 未通过
2. E2E 测试 — 未通过
3. 结构化日志 / request_id — 未通过
4. 指标暴露 — 未通过
5. 告警 — 未通过
6. Docker Compose 一键部署 — 未通过
7. 滚动更新 — 未通过
8. 限流熔断 — 未通过

**未验证项清单**：

1. 备份恢复流程实测（仅有备份导出 API）
2. 密钥与敏感信息管理（本次未涉及验证）
3. 拖拽改期在异常中断场景下的一致性（缺 E2E / 失败注入）

**后续计划**：

1. 补齐失败注入与关键路径 E2E，覆盖排期拖拽改期、quiz 生成/判分主链路；
2. 引入结构化日志与 request_id，作为指标与告警的前置基础；
3. 暴露核心指标（接口延迟、错误率、超负荷命中率）并配置最小告警规则；
4. 提供 Docker Compose 一键编排，补滚动更新方案；
5. 完成一次备份恢复实测，形成可复现的恢复演练记录；
6. 评估限流熔断方案并在网关或应用层落地；
7. 将本轮技术债（含 SQLite 无迁移框架问题）沉淀为独立技术债文档并排期。
