# 发版对照报告 notes limit/offset 400（second-brain，2026-10-28 深耕轮）

范围：GET /api/notes 的 limit/offset 参数校验收紧 + 15 子用例新测与既有测试同步改动。无 UI 改动，视觉验收不适用；无迁移、无新依赖、无新增端点。

- 可靠性：limit/offset 缺失或为空保持既有默认值（50/0），存量前端调用路径不变；非整数输入由静默回退改为显式 400，行为可预期且已在 CHANGELOG 注明契约变更与回滚方式；负值 clamp、超大 limit 返回全部行的既有语义均保持不变。
- 可观测性：400 响应携带明确错误文案（"limit 参数非法" / "offset 参数非法"），调用方可直接定位非法参数；未改动现有日志与监控路径。
- 数据与状态：改动仅发生在 handler 参数解析层，不触碰 store 与数据模型；ListNotes 调用、nil 转空 slice 处理均未变。
- 部署运维：无迁移、无新依赖、无新增端点，改动集中于 internal/api，可随常规发布上线；前端不传 limit/offset，不受本次契约变更影响。
- 安全与健壮性：对畸形输入显式拒绝（400），避免非预期默认值掩盖调用方错误；超大 limit 未新增上限，保持原返回全部行的语义，未引入新的资源放大风险面。
- 可维护性：parseIntDefault 定义保持不动，handler 侧改用严格解析以区分"缺省"与"非法"，语义更清晰；新增 15 子用例覆盖 limit/offset 各类输入，TestNotesListLimitOffsetClamp 同步更新，回归防护更完整。

结论：定向验证 TestNotesListLimitOffsetClamp 9/9 PASS、TestNotesList_LimitOffsetValidation 15/15 PASS、gofmt 本轮改动文件干净、go vet internal/api 无告警；全量结果：全量 go test ./... 各包均 ok（api/log/markdown/metrics/notify/push/ratelimit/review/search/store），gofmt 本轮三文件全洁（review_deep4_test.go 的 gofmt 差异为既有文件、本轮未动）
