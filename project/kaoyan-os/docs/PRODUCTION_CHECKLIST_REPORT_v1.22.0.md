# PRODUCTION_CHECKLIST_REPORT v1.22.0

## 变更
- `apps/server/src/routes/settings.ts` 新增 `isValidExamDate` helper，校验逻辑为格式正则匹配加 Date 往返比对。
- `PUT /api/settings` 的 `examDate` 分支改用新 helper：当请求传入不存在的日期（2024-02-30、2023-02-29、2026-04-31、2026-13-01）时，接口返回 400 状态码，错误体文案为 `{ error: 'invalid field: examDate' }`，且不执行写库操作。
- `GET /api/settings` 的 `readSettings` 分支改用新 helper：当数据库中已存有不存在的日期时，返回时会忽略该值并回退至 `DEFAULT_SETTINGS.examDate`。
- 闰年 2024-02-29 及所有合法日期行为保持不变。
- `theme` 与数字字段、错误体文案、upsert 事务逻辑均一字未动。

## 测试
- 新增 `apps/server/tests/settings-examdate-strict.test.ts`，包含 8 个测试用例。
- 靶向测试涉及 3 个文件共 22 个用例（新测试 8 + settings.deep 12 + settings-isolation 2），全部通过（全绿）。
- 服务端 `tsc --noEmit` 检查零错误。
- 本轮无前端改动。

## 视觉验收
- 不适用（无前端改动）

## 已知保留
- 全量套件本轮未跑。
- 真实服务冒烟未做（验证走 Fastify inject + :memory: 库）。

## 模型调用
- 本轮全部调用走 BotsRouter 讯飞星辰 spark-x2.6。
