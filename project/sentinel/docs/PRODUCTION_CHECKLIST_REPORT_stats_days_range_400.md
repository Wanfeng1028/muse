# sentinel 监控统计 days 越界返回 400 发版对照报告

## 改动概述
- internal/handlers/handlers.go 的 handleStats 调整：days<1 或 days>90 返回 400“days 参数非法”，不再静默钳制为 1 或 90；默认值 7、非数字 400、404、统计字段均保持原样不变。
- 测试：改写 handlers_deep2_test.go 中 1 个锁定旧语义的用例，改名为 TestHandleStatsDaysOutOfRangeReturns400Deep3；覆盖 days=0、-3、91、9999，断言均为 400。

## checklist 对照表
| 领域 | 判定 | 说明 |
| --- | --- | --- |
| 可靠性 | 通过 | 越界参数由静默钳制改为 fail-fast 返回 400，行为更可预期。 |
| 可观测性 | 通过 | 400 错误文案明确为“days 参数非法”；既有 logErr 不变。 |
| 数据 | 不适用 | 无 schema 变更、无迁移。 |
| 部署运维 | 不适用 | 无配置变更、无部署流程变更。 |
| 安全 | 通过 | 非法输入不再被静默接受，明确拒绝。 |
| 可维护 | 通过 | 改动面为 2 个文件（handlers.go、handlers_deep2_test.go）；文档同步。 |

## 测试与验收
- 命令：go test ./internal/handlers/ -run 'TestHandleStatsDays|TestHandleStatsNotFound'
- 结果：3 个测试函数全绿。
- go vet：全洁。
- gofmt：全洁。

## 已知限制
- 本轮未跑 handlers 全包与全量套件。
- 未进行真实服务 HTTP 冒烟。
- 无 UI 改动，视觉验收不适用。
- 无 schema 变更、无版本号升级。