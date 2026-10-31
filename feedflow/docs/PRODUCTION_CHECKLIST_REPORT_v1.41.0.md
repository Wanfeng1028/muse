# feedflow 创建订阅源 interval_min 布尔/浮点返回 400 发版对照报告

## 改动概述
- feedflow/feedflow/api.py 的 create_feed 对 interval_min 新增 bool/float 校验，返回 400“interval_min 非法”；其余行为一字不动。
- 改动文件：api.py。
- 新增文件：tests/test_feed_interval_bool_float_v141.py（7 例）。

## checklist 对照表
| 维度 | 检查项 | 预期标准 | 状态 | 说明/备注 |
|---|---|---|---|---|
| 可靠性 | 非法输入 fail-fast | 校验并快速失败 | 通过 | 对 create_feed 的 interval_min 新增 bool/float 校验并返回 400 |
| 可观测性 | 400 错误文案明确 | 文案清晰 | 通过 | 返回 400“interval_min 非法” |
| 数据 | 无 schema、无迁移 | 无变更 | 不适用 | 无 schema 变更 |
| 部署运维 | 无配置、无部署变更 | 无变更 | 不适用 | 无配置、无部署变更 |
| 安全 | 消除静默重解释 | 非法类型不通过 | 通过 | bool/float 校验避免静默重解释 |
| 可维护 | 改动面控制、文档同步 | 文档一致 | 通过 | 改动面 2 个文件、文档同步 |

## 测试与验收
- 涉及文件：feedflow/feedflow/api.py；tests/test_feed_interval_bool_float_v141.py（新增）。
- 测试结果：新 7 例 + v1.40.0 folder_id 10 例，17 passed。
- 静态检查：ruff check 两变更文件全洁。

## 已知限制
- 本轮未跑全量 pytest。
- 未做真实服务冒烟。
- update_feed 的 interval_min/enabled/position 仍用 plain int() 转换。
- 负 folder_id 仍透传。
- 无 UI 改动，视觉验收不适用。
- 无 schema 变更。