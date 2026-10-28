# PRODUCTION_CHECKLIST_REPORT v1.21.0

## 变更
- GET /api/stats/weekly 新增 start 参数与日历往返校验；不存在日期返回 400 { error: 'start 日期无效' }；其余逻辑不变。
- 代码改动：apps/server/src/routes/stats.ts（+4 行）。

## 测试
- 新增 weekly-start-strict.test.ts（7 例）。
- 靶向 4 文件 36 例全绿。
- 全量 136 文件 964 例全绿。
- tsc --noEmit 零错。

## 视觉验收
- 不适用（无前端改动）。

## 已知保留
- 此前 2024-02-30 透传 200 的旧语义已由两处测试更新纠正；无其他保留。

## 模型调用
- BotsRouter / 讯飞星辰 spark-x2.6
