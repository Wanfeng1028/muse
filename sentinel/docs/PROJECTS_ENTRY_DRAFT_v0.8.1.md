### sentinel v0.8.1（2026-10-19）
- 增量：修复手动检查与调度 tick 并发时同一监控产生两个 open incident 的竞态——migration v10 部分唯一索引 `uq_incidents_open_monitor`（含历史重复 open 去重）+ `OpenIncident` 幂等化 + `record()` 仅真正新建事件时发 down 通知。
- 完成度：新增 8 个测试全过（复现测试先红后绿），go vet/gofmt 全洁，真实服务 30 并发冒烟无重复 open，恢复→重开闭环正常。
- 已知限制：Go 工具链旧（46 个标准库漏洞根因，排期升级复扫）；store/notify 包 7 个 pre-existing 测试失败（干净树复现，与本轮无关，排期修）；deliveries 表同类并发幂等缺口排期修。
