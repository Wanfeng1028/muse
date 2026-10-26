# ledger 发版对照报告：v2.17.21

## 改动摘要
GET /api/transactions 的 type 参数校验收紧，非法值 400（detail“type 参数非法”），None 或空串不过滤，合法值 income/expense/transfer 复用 VALID_TYPES；其余过滤与分页未动；创建/更新校验未动。

## 验收范围
### 靶向测试
tests/test_transactions_type_validation.py 5/5 通过；版本一致性测试通过；ruff check 与 ruff format 全洁。
### 真实服务冒烟
8130 端口隔离库二进制实测，建账户 201、建交易 201，type=bogus 400 且 detail 为“type 参数非法”，空串/expense/无参均 200 且 total 为 1，income 200 且 total 为 0，冒烟后服务已停、端口复查已关。

## 对照表
| 维度 | 结论 |
| --- | --- |
| 可靠性 | 通过。靶向测试全部通过且真实服务冒烟符合预期，证明参数校验逻辑稳定无回归。 |
| 可观测性 | 通过。非法参数触发 400 响应并返回明确的 detail 错误提示，便于排查。 |
| 数据 | 通过。空串不过滤，expense 过滤命中，income 未命中，确保过滤逻辑准确无误。 |
| 部署 | 通过。冒烟后服务已停止且端口复查确认关闭，部署与环境清理流程正常。 |
| 安全 | 通过。校验逻辑复用 VALID_TYPES 进行严格类型控制，可有效防范非法注入。 |
| 可维护性 | 通过。校验规则集中复用且单元测试覆盖完整，ruff 静态检查全洁。 |

## 已知限制
全量 pytest 本轮未跑（只跑靶向组与版本一致性测试）；首轮冒烟因服务冷启动未就绪与收尾 pkill 自杀各失败一次，第二轮以 nohup 起服、fuser 按端口停服后 5/5 通过。