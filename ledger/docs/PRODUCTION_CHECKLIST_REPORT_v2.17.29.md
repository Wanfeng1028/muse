# 生产检查清单报告 v2.17.29

本轮只收紧 PUT /api/transactions/{id} 的 occurred_on 入参校验，无破坏性变更。

## 可靠性
- 非法 occurred_on 在入库前即被拦截：update_transaction 在构造 merged 之前先做与 POST 同款严格校验（strptime + 长度 10 + 第 5、8 位横杠），非法值返回 400，不会落库。
- 显式传 occurred_on: null 不再走到合并构造并返回 500，现统一返回 400，原值不变。
- 合法日期（含闰年 2024-02-29）照常放行，返回 200 且持久化；省略 occurred_on 不改原值。

## 可观测性
- PUT 非法值统一返回 400，detail 为“occurred_on 参数非法”，与 POST 创建接口及 GET 列表接口口径一致，便于日志检索与告警归类；此前 PUT 非法值由 pydantic 返回 422（detail 为校验错误数组）的情形不再出现。

## 数据与状态
- 无迁移、无新依赖、无新增端点；数据库 schema 与既有交易数据状态一字不动。

## 部署运维
- 无新增端点、无 UI 改动，视觉验收不适用；部署动作与 v2.17.28 相同，仅需替换代码与依赖版本后回归靶向测试。

## 安全与健壮性
- 严格边界校验（strptime + 长度 10 + 第 5、8 位横杠）在入库前拦截非法输入，杜绝脏日期写入；与 POST 同款校验避免接口间口径漂移。

## 可维护性
- 发版升版四处统一为 2.17.29：src/ledger/__init__.py、pyproject.toml、tests/test_version_consistency_v21715.py 的 EXPECTED_VERSION、CHANGELOG.md 顶条。
- CHANGELOG 顶条已更新为 v2.17.29；v2.17.28 CHANGELOG 中“PUT 更新路径一字不动”的表述自本节起作废（该路径现已收紧）。

## 冒烟结果
- 真实服务冒烟（18440 端口隔离库）：not-a-date、2024-13-01、空串、null 各返回 400 且 detail 为“occurred_on 参数非法”；2024-02-29 返回 200 且 GET 核对为 2024-02-29；冒烟完服务已停、端口已关、隔离库已删。

## 结论
- 靶向范围（PUT occurred_on 校验收紧）全部通过：新增 tests/test_transactions_update_occurred_validation.py 13 例全绿（8 例非法值参数化 400 且原值不变、null 400 且原值不变、合法值参数化 200 且持久化含闰日、省略 200 且原值不变），相关交易测试 42 项全绿（新测 + 创建校验 + transactions + deep2），ruff check 改动文件全洁。
- 全量回归在文档同步前：1525 通过、1 失败（仅版本一致性测试，系本文档批次同步内容）、1 跳过；同步后版本一致性测试通过。
