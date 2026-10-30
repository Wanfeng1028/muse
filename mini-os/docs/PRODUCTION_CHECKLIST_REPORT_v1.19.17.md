# mini-os v1.19.17 生产级检查对照报告

## 改动摘要
- src/handlers.rs：create_fs 在 kind 校验后、内容解析前、DB 加锁前新增冲突检查：bytes 为 Some 且 content 为 Some 且 trim 后非空时返回 400，文案逐字为“bytes 与 content 不能同时指定”，不创建节点；bytes 空数组加非空 content 同样 400；bytes 单独、content 单独、两者都不给、content 为空串或纯空白加 bytes 行为不变。此前 bytes 与 content 同时给时 content 被无声丢弃。
- src/models.rs：CreateNodeRequest 的 content 与 bytes 两行注释同步说明该 400 口径。
- Cargo.toml 与 Cargo.lock：mini-os 版本由 1.19.16 升为 1.19.17。
- 新增测试：tests/fs_create_bytes_content_conflict_test.rs，6 例。

## 对照表
| 检查项 | 结论 | 理由 |
| --- | --- | --- |
| 测试金字塔 | 通过 | 新增 6 例靶向测试，关联回归 28/28 通过；本轮仅运行靶向与关联目标，未声称全量测试通过。 |
| 错误处理 | 通过 | bytes 与 content 同时给时返回 400，文案逐字相符，不创建节点。 |
| 迁移 | 不适用 | 本轮无迁移。 |
| 健康检查 | 通过 | 真服务 health 返回 1.19.17。 |
| 日志指标 | 不适用 | 本轮未改动日志与指标。 |
| 备份恢复 | 不适用 | 本轮未改动备份与恢复。 |
| 配置密钥 | 不适用 | 本轮未改动配置与密钥。 |
| 多用户 | 不适用 | 本轮未改动多用户逻辑。 |
| 部署 | 不适用 | 本轮未改动部署流程。 |
| 限流超时 | 不适用 | 本轮未改动限流与超时。 |
| 安全校验 | 通过 | 冲突检查在内容解析前、DB 加锁前执行，阻止无效写入。 |
| 文档同步 | 通过 | CHANGELOG 已新增 [1.19.17] 节，版本号同步至 Cargo.toml 与 Cargo.lock。 |
| Clippy（既存项） | 未通过 | --all-targets 在既存 tests/handlers_deep.rs:330 报 E0308（parent_id 期望 Option<String> 却给 Option 整数），属既存已知限制，本轮未扩范围修复。 |

## 已知限制
- clippy --all-targets 在既存 tests/handlers_deep.rs:330 报 E0308（parent_id 期望 Option<String> 却给 Option 整数），与本轮改动无交集，属既存已知限制。

## 验证证据
- 新增测试：tests/fs_create_bytes_content_conflict_test.rs，6 例（both_bytes_and_content_400、bytes_only_201、content_only_201、empty_content_plus_bytes_201、whitespace_content_plus_bytes_201、empty_bytes_plus_content_400），6/6 通过。
- 关联回归：fs_create_parent_conflict_test 6、fs_parent_id_validation_test 6、fs_v2_test 15、vfs_path_r2 1，合计 28/28 通过。
- cargo fmt --all --check 干净。
- clippy：--lib 与新测试目标无归属到改动文件的告警；--all-targets 在既存 tests/handlers_deep.rs:330 报 E0308，与本轮改动无交集。
- 真服务冒烟（18533 端口、隔离库）：health 返回 1.19.17；注册 201；bytes+content 返回 400 且文案逐字相符；bytes 单独返回 201 且 size 为 3；列表恰 1 条（冲突未建节点）；冒烟后服务已停、端口已关、冒烟库已删。
