# kaoyan-os v1.19.0 发版前 Definition of Done 对照报告

## 1. 背景

2026-10-28 深耕轮。轮换队列：上轮 botstalk（OpenAgents 第 17 轮设备管理 Web UI，commit 6fe232d6），本轮按队列轮到 kaoyan-os；下一轮按队列轮到 drama-factory。

本轮核心交付：`apps/server/src/routes/mistakes.ts` 的 `GET /api/mistakes/:id/source-exams` 与 `apps/server/src/routes/exams.ts` 的 `GET /api/exams/:id/related-mistakes` 的 `windowDays` 由 `Number()` 口径改用正则 `/^-?\d+$/` 校验；`1.0`、`0x2`、`+7`、带空格、空串、`1.5`、`abc` 均返回 `400 { error: 'windowDays 非法' }`；缺省 7、范围 0~90、错误体、404 顺序、查询与排序逻辑不变；与 v1.16.0/v1.17.0/v1.18.0 的 days/months 严格口径对齐；此前 `Number()` 口径下 `1.0`、`0x2`、`+7`、空串会静默通过返回 200。

## 2. 变更清单表

| 文件 | 变更类型 | 变更内容 |
|---|---|---|
| `apps/server/src/routes/mistakes.ts` | 修改 | 3 行新增；`GET /api/mistakes/:id/source-exams` 的 `windowDays` 由 `Number()` 口径改用正则 `/^-?\d+$/` 校验 |
| `apps/server/src/routes/exams.ts` | 修改 | 3 行新增；`GET /api/exams/:id/related-mistakes` 的 `windowDays` 由 `Number()` 口径改用正则 `/^-?\d+$/` 校验 |
| `apps/server/tests/window-days-strict.test.ts` | 新增 | `windowDays` 严格口径测试 |
| `CHANGELOG.md` | 修改 | 新增 `[1.19.0]` 一节 |
| `docs/API.md` | 修改 | 两处 `windowDays` 说明行 |
| `docs/PRODUCTION_CHECKLIST_REPORT_v1.19.0.md` | 新增 | 本报告 |

无前端改动。

## 3. 实测数字

- 新测：4/4 全绿。
- 靶向合计：10/10 全绿（新测 4 例 + 既有 `mistakes-exams-link.test.ts` 6 例）。
- 关联隔离：3 文件 16/16 全绿（`isolation-source-exams.deep4`、`isolation-cross-user-404-related.deep4`、`cross-user-404.deep3`）。
- 服务端 `tsc --noEmit`：零错。
- 全量套件：本轮未跑。
- UI/视觉：无 UI 改动，视觉验收不适用。
- 冒烟：无单独真实服务冒烟，覆盖来自 Fastify inject + 真实内存库测试。
- 批次质量（诚实记录）：
  - 代码批：讯飞星辰 `spark-x2.6` 一次成功（prompt 549、completion 819）。
  - 测试批：首稿作废（模型输出读文件工具调用而非文件内容）；第二稿与第三稿在 140 秒处传输超时（无用量回执）；改切七牛免费版 `conatus-free` 一次成功（prompt 996、completion 19283）。
  - 文档批与报告批：均走 `conatus-free`。
  - 智谱 `glm-4.7`：本轮未用（周限额 429 至 2026-10-30 01:14:56 重置）。
  - `dpsk`：未探活，仍停用。

## 4. 逐条对照

### 4.1 可靠性

- 判定：通过（部分）
- 说明：新测与关联测试全绿、`tsc` 零错；全量套件未跑、失败注入未单独做。

### 4.2 可观测性

- 判定：未验证
- 说明：本轮未进行可观测性验证。

### 4.3 数据与状态

- 判定：通过（部分）
- 说明：DB 迁移未涉及，用户隔离与未登录 401 由全局认证钩子保证、关联隔离测试覆盖。

### 4.4 部署与运维

- 判定：未验证
- 说明：本轮未进行部署与运维验证。

### 4.5 安全与健壮性

- 判定：通过
- 说明：非法输入统一 400，不再静默通过；`windowDays` 由 `Number()` 口径改用正则 `/^-?\d+$/` 校验，`1.0`、`0x2`、`+7`、带空格、空串、`1.5`、`abc` 均返回 `400 { error: 'windowDays 非法' }`；缺省 7、范围 0~90、错误体、404 顺序、查询与排序逻辑不变；此前 `Number()` 口径下 `1.0`、`0x2`、`+7`、空串会静默通过返回 200。

### 4.6 可维护性

- 判定：通过
- 说明：CHANGELOG 与 API.md 同步，测试文件与既有脚手架约定一致。

## 5. 已知限制

- 全量套件未跑。
- 负整数外的边界如 `windowDays=00` 仍按正则通过为 0（与 days/months 口径一致，不属本轮范围）。
- 其余接口的 `Number()` 口径（如 settings、words 的 id 转换）不在本轮范围。