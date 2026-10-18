# Sentinel v0.8.1 发版对照报告（生产就绪检查）

## 对照标准
沿用 PRODUCTION_CHECKLIST.md，v0.8.1 增量为修复 incidents 并发竞态（v0.8 诚实记录的未修复 bug）。

## 结论口径声明
本报告结论以 v0.8.1 已实现并通过验证的功能事实为准；凡未在本轮变更的条目，均沿用 v0.8 口径，不重复举证。

## §1 可靠性
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 幂等 / 去重 | 通过 | 部分唯一索引 `uq_incidents_open_monitor ON incidents(monitor_id) WHERE ended_at IS NULL`（migration v10）约束同一监控最多一个 open 事件；`OpenIncident` 改为 `INSERT ... ON CONFLICT DO NOTHING` 返回 created 标志，重复并发不再插入第二条。 |
| 失败注入 / 并发 | 通过 | 新增 8 个测试（1 复现 + 4 store 幂等/索引/重开 + 3 scheduler 回归）全过；`go test ./... -race` 下 scheduler 包全过。 |
| 迁移版本化 | 通过 | migration v10，含历史重复 open 数据去重，脚本幂等可重入。 |
| 通知去重 | 通过 | `record()` 仅在真正新建事件时发 down 通知，并发重复不再重复告警。 |

§1 结论：本轮修复的并发竞态已闭环，可靠性相关条目通过。

## §2 可观测性
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 事件可追溯 | 沿用 v0.8 口径 | 本轮未动。 |

§2 结论：沿用 v0.8 口径。

## §3 安全性
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 依赖漏洞 | 部分通过 | Go 工具链升级后依赖复扫仍挂账，46 个标准库漏洞根因未清。 |
| 其余安全条目 | 沿用 v0.8 口径 | 本轮未动。 |

§3 结论：依赖复扫挂账，其余沿用 v0.8 口径。

## §4 性能
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 并发写入 | 通过 | 30 并发 POST /api/monitors/{id}/check 冒烟，GET /api/incidents 恰好 1 条 open，无重复。 |
| 其余性能条目 | 沿用 v0.8 口径 | 本轮未动。 |

§4 结论：并发写入去重通过，其余沿用 v0.8 口径。

## §5 运维
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 恢复 / 重开闭环 | 通过 | 冒烟：切健康地址 + check → 事件关闭（ended_at 非空，downtime_sec=432）；切回 down target + check → 新开事件（共 2 条，1 open）。 |
| 其余运维条目 | 沿用 v0.8 口径 | 本轮未动。 |

§5 结论：恢复重开闭环正常，其余沿用 v0.8 口径。

## §6 可维护性
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| CHANGELOG | 通过 | 新增 [0.8.1] 一节。 |
| 测试数变化 | 通过 | 新增 8 个测试（1 复现 + 4 store + 3 scheduler），全部通过。 |
| 代码整洁 | 通过 | `go vet` 全洁；经手文件 gofmt 全洁。 |
| 其余可维护性条目 | 沿用 v0.8 口径 | 本轮未动。 |

§6 结论：变更记录与测试覆盖补齐，代码整洁通过。

## §7 兼容性
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 数据兼容 | 通过 | migration v10 对历史重复 open 数据去重，幂等可重入。 |
| 接口兼容 | 部分通过 | `OpenIncident` 签名变为 `(id, created, err)`，属内部 API 变更。 |
| 其余兼容性条目 | 沿用 v0.8 口径 | 本轮未动。 |

§7 结论：数据兼容通过，内部 API 有签名变更。

## §8 文档
| 子项 | 结论 | 理由 |
| --- | --- | --- |
| 登记册 | 通过 | 新增 docs/PROJECTS_ENTRY_DRAFT_v0.8.1.md 草稿。 |
| README | 通过 | 新增事件幂等 bullet。 |
| 其余文档条目 | 沿用 v0.8 口径 | 本轮未动。 |

§8 结论：本轮文档补齐，其余沿用 v0.8 口径。

## 汇总

### 通过
- §1 可靠性：幂等/去重、失败注入/并发、迁移版本化、通知去重
- §4 性能：并发写入去重
- §5 运维：恢复/重开闭环
- §6 可维护性：CHANGELOG、测试数变化、代码整洁
- §7 兼容性：数据兼容
- §8 文档：登记册、README

### 部分通过
- §3 安全性：依赖漏洞复扫挂账
- §7 兼容性：内部 API 签名变更

### 不适用
- 无

### 未通过
- 无

### 本轮 v0.8.1 完成项
- 修复内容：SQLite 部分唯一索引 `uq_incidents_open_monitor ON incidents(monitor_id) WHERE ended_at IS NULL`（migration v10，含历史重复数据去重）+ `OpenIncident` 幂等化（`INSERT ... ON CONFLICT DO NOTHING`，返回 created 标志）+ `record()` 仅在真正新建事件时发 down 通知。恢复后重开不受影响。
- 测试证据：B1 复现测试 `TestManualAndTickConcurrent_DuplicateOpenIncident` 修复前 FAIL（open incident 数量 = 23，期望 1），修复后 PASS；新增 8 个测试全过；`go vet` 全洁；经手文件 gofmt 全洁。
- 冒烟证据：127.0.0.1:8201 独立 DB，30 并发 POST /api/monitors/{id}/check → GET /api/incidents 恰好 1 条 open；PUT target 切健康地址 + check → 事件关闭（ended_at 非空，downtime_sec=432）；切回 down target + check → 新开事件（共 2 条，1 open）；监控已删除清理。

### 本轮未做、改排期
- Go 工具链升级后依赖复扫（46 个标准库漏洞根因）。
- deliveries 表同类并发幂等缺口，建议下轮按本轮 incidents 方案同理修复。

### 遗留挂账
- Go 工具链旧，依赖复扫挂账（46 个标准库漏洞根因）。
- store/notify 包 7 个 pre-existing 测试失败，已在干净树（git stash）复现，与本轮无关：TestEnqueueDeliveryConcurrentSameKey（deliveries 表同类并发幂等缺口）、TestDailyBreakdown_IncludesEmptyDaysAndBoundaries（浮点精度）、TestMonthlySLA_WithClosedAndOpenIncident（时间炸弹测试）、TestWeComSendMarkdown_InvalidURL（错误文案包装前缀）+ 3 个 SMS/阿里云网络依赖测试（沙箱无外网）。
- deliveries 表存在同类并发幂等缺口，排期修。

## 诚实边界声明
本报告不声称全绿。`go test ./... -race` 下 store/notify 包有 7 个失败，已在干净树复现，确认为 pre-existing，与本轮修复无关，记入遗留挂账。依赖复扫挂账未清。deliveries 表同类并发幂等缺口未修，仅排期。
