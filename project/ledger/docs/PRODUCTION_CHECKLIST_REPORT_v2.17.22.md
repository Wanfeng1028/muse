# ledger 发版对照报告：v2.17.22

## 改动摘要

- GET /api/transactions 的 date_from/date_to 参数校验收紧：非法值 400，detail 分别为“date_from 参数非法”与“date_to 参数非法”
- 合法格式为严格 YYYY-MM-DD：恰好 10 字符、短横线在第 4 与第 7 位、真实日历日期
- None 或空串表示不过滤
- 其余过滤与分页未动；创建/更新校验未动
- 不做 date_from 大于 date_to 的顺序校验

## 验收范围

### 靶向测试

- tests/test_transactions_date_validation.py 9/9 通过
- 与类型校验测、版本一致性测合跑 15/15
- ruff check 与 ruff format 在两处改动文件上全洁
- 全量 pytest 1476 通过、1 跳过、0 失败，耗时 254.96 秒
- 2 条警告均为既存 SAWarning，与本轮改动无关

### 真实服务冒烟

- 18431 端口隔离库实测，health 返回 version 2.17.22
- 建账户 201
- date_from=bogus 返回 400，detail 为“date_from 参数非法”
- date_to=2024-02-30 返回 400，detail 为“date_to 参数非法”
- date_from=2024-01-01 返回 200，total 为 0（冒烟库未播种交易，空列表为预期）
- 冒烟后服务已停、端口复查已关

## 对照表

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 可靠性 | 通过 | 日期校验靶向测试 9/9 通过、合跑 15/15，全量 pytest 1476 通过、0 失败。 |
| 可观测性 | 通过 | 冒烟实测 health 返回 version 2.17.22，非法参数 detail 分别精确返回“date_from 参数非法”与“date_to 参数非法”。 |
| 数据 | 通过 | date_from=2024-01-01 返回 200 且 total 为 0，与冒烟库未播种交易、空列表为预期一致。 |
| 部署 | 通过 | 18431 端口隔离库冒烟通过，冒烟后服务已停、端口复查已关。 |
| 安全 | 通过 | bogus 与 2024-02-30 均被严格格式校验拒绝并返回 400。 |
| 可维护性 | 通过 | ruff check 与 ruff format 在两处改动文件上全洁，改动范围仅限 date_from/date_to 参数校验。 |

## 已知限制

- 不做 date_from 大于 date_to 的顺序校验（超出本轮范围）
- 冒烟未播种交易，范围过滤命中由 pytest 的范围测试覆盖
- 全量 2 条警告为既存 SAWarning，非本轮引入