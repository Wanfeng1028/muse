# 发版对照报告 shares file 模式 path 冲突 400（mini-os，2026-10-29 深耕轮）

可靠性：本次改动在 src/handlers.rs 的 create_share file 分支取 node_id 之前，判定 req.path 为 Some 且 trim 后非空即返回 400，文案固定为 "file 模式下不能指定 path"。空串与纯空白 path 仍视为未给，空 path 正常放行，且 Cargo.toml 与 Cargo.lock 版本已同步升为 1.19.16。

可观测性：测试用例 tests/share_file_path_conflict_test.rs 新增 5 例并全部通过，旧测翻转为 file_share_with_path_now_400 使该文件 6/6 全过。除 handlers_deep 外逐目标跑通 30 个目标，共 248 项通过、0 项失败（含 lib_deep 判为抖动），其余约 68 个远离改动面的目标列为已知缺口。

数据与状态：此前 file 模式会无声丢弃 path，现已契约变更为直接拒绝，调用方 file 分享只需给 nodeId。冒烟测试（18531 端口）确认分享列表恰 1 条且冒烟曾误写仓库 data/mini-os.db，测试结束后已将其彻底删除。

部署运维：冒烟验证显示 health 接口返回 1.19.16，注册返回 201，file 仅传 nodeId 返回 201 且 token 非空。冒烟收尾后服务已停止，端口已关闭，冒烟二进制与冒烟库均已彻底删除。

安全与健壮性：通过前置 trim 后的非空检查拦截了 file 模式携带非空 path 的调用，避免调用方误以为 path 生效而产生不一致的分享预期。type 非法校验、expires_at 校验、token 生成逻辑以及前端均未受本轮改动波及。

可维护性：src/models.rs 的 path 字段注释已同步修改为明确声明 file 模式下非空 path 返回 400，为后续开发者提供了准确语义。远离本轮 2501 行附近改动面的约 68 个测试目标缺口及 handlers.rs 与 notes.rs 的既有 clippy 警告被明确留待后续处理。另有 cargo test 全量被 tests/handlers_deep.rs:330 的既有 E0308 阻断（fs.parent_id 已是 Option<String>，旧断言仍写 Some(7)，该文件不在本轮改动之列），同样留待后续处理。

结论：本次发版在未引入数据库迁移及新依赖的前提下，精准修复了 shares file 模式下 path 冲突的潜在风险，完成了边界行为的收紧与版本交付。各项测试与冒烟验证充分证明了该改动的安全性与契约变更的有效性。

编排修正：首版测试 harness 系模型编造（不存在的 crate::app() 等），编排作废后以 tests/share_node_path_conflict_test.rs 前 93 行原文重派才通过。冒烟收尾时 pkill -f 误匹配自身 shell 而自杀，服务停止以后续端口已关为准确认。
