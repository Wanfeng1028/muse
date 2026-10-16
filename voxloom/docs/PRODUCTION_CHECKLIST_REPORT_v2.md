
# voxloom v2 定时自动备份 发版对照报告

## 元信息

| 项 | 内容 |
| --- | --- |
| 版本 | v2（定时自动备份） |
| 日期 | 2026-10-17 |
| 关闭项 | v1.3 报告 3.1 [未通过] |
| 报告状态 | 代码审查 + 构建 + 控制台冒烟实测；xunit 在本机 testhost 挂起未能执行（环境问题，已如实记录） |
| 依据来源 | 本轮改动清单、设计要点、构建与测试记录（编排侧提供） |

## 改动范围（文件级）

| 文件 | 变更类型 | 说明 |
| --- | --- | --- |
| `src/VoxLoom.Core/Backup/AutoBackupService.cs` | 新建 | 定时自动备份服务主体 |
| `src/VoxLoom.Core/Config/AppConfig.cs` | 修改 | 新增 `autoBackupEnabled` / `autoBackupIntervalMinutes` / `autoBackupRetentionCount` 三项配置，含环境变量读取、校验逻辑，并新增 `ReadBool` helper |
| `src/VoxLoom.Desktop/App.axaml.cs` | 修改 | 启动与退出接线（启动注册、退出停止 Timer） |
| `src/VoxLoom.Desktop/ViewModels/MainViewModel.cs` | 修改 | 新增 `TryStageAutoBackupSnapshot` |
| `tests/VoxLoom.Core.Tests/Backup/AutoBackupServiceTests.cs` | 新建 | 7 个用例 |
| `docs/OPERATIONS.md` | 修改 | 配置表、环境变量表 |
| `CHANGELOG.md` | 修改 | Unreleased / Added v2 |

### 设计要点

- 独立 `BackupManager`：使用 `backups/auto` 子目录，保留份数独立于手动备份，默认 5。
- 密码仅从环境变量 `VOXLOOM_AUTOBACKUP_PASSWORD` 读取，不落配置文件。
- Timer 回调全程 `try/catch`，异常经 `BackupFailed` 事件上报，绝不向 Timer 抛出。
- 无已加载项目时跳过本次备份。
- Timer 为进程内定时器，应用退出即停止（已在 Exit 路径接线）。

## 1. 可靠性

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| Timer 回调异常不外泄 | 通过（代码审查） | 回调全程 try/catch，异常走 `BackupFailed` 事件 |
| 重复 Start 防护 | 通过（代码审查 + 用例设计） | 用例“重复 Start 抛” |
| Stop 幂等 | 通过（代码审查 + 用例设计） | 用例“Stop 无操作” |
| 空项目场景 | 通过（代码审查 + 用例设计） | 无已加载项目时跳过；用例“空项目跳过” |
| 备份函数异常路径 | 通过（代码审查 + 用例设计） | 用例“备份函数抛异常走事件” |
| 周期触发 | 通过（代码审查 + 用例设计） | 用例“周期触发 75 秒” |
| 进程退出后不再触发 | 通过（代码审查） | Timer 为进程内；已接 Exit 停止 |
| 构建 | 通过 | `dotnet build VoxLoom.sln -c Release` 成功；本轮新增代码零警告（已修一处 CS0419 cref 歧义） |

说明：`dotnet build VoxLoom.sln -c Release` 成功，本轮新增代码零警告。xunit `AutoBackupServiceTests` 在本 VM 无法执行——vstest testhost 进程挂起（4 次尝试：连接超时/执行挂起，与代码无关，系沙箱环境问题）；改用控制台冒烟程序直验真实构建 DLL，6 项全过（非法间隔抛 BackupException/重复 Start 抛 InvalidOperationException/未 Start 直接 Stop+Dispose 无操作/禁用 3 秒零备份调用/配置默认值 Enabled=true·60 分钟·保留 5 份）。xunit 7 例已随代码提交，待可用环境补跑。

## 2. 可观测性

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 失败可观测 | 通过（代码审查） | 备份异常经 `BackupFailed` 事件上报，不静默吞掉 |
| 配置项可见 | 通过 | 三项配置纳入 `docs/OPERATIONS.md` 配置表 |
| 环境变量可见 | 通过 | `VOXLOOM_AUTOBACKUP_PASSWORD` 等纳入 `docs/OPERATIONS.md` 环境变量表 |
| 变更可追溯 | 通过 | `CHANGELOG.md` Unreleased / Added v2 |
| 跳过行为可解释 | 通过（代码审查） | 无已加载项目时跳过，属既定设计而非异常 |

## 3. 数据与安全

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 密码来源单一 | 通过（代码审查） | 仅从 `VOXLOOM_AUTOBACKUP_PASSWORD` 环境变量读取 |
| 密码不写入配置 | 通过（代码审查） | 三配置项中不含密码字段 |
| 自动备份与手动备份隔离 | 通过（代码审查） | 独立 `BackupManager`，`backups/auto` 子目录 |
| 保留策略独立 | 通过（代码审查） | 自动备份保留份数独立，默认 5 |
| 保留份数可配置 | 通过（代码审查） | `autoBackupRetentionCount` 配置项 + 校验 |
| 配置校验 | 通过（代码审查 + 用例设计） | 非法间隔抛异常；用例“非法间隔抛” |
| 禁用开关 | 通过（代码审查 + 用例设计） | `autoBackupEnabled`；用例“禁用不备” |

## 4. 部署运维

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 环境变量接入 | 通过 | `AppConfig` 支持环境变量读取，文档已列表 |
| 配置读取健壮性 | 通过（代码审查） | 新增 `ReadBool` helper，用于布尔配置解析 |
| 运维文档更新 | 通过 | `docs/OPERATIONS.md` 配置表 / 环境变量表已更新 |
| 发布记录更新 | 通过 | `CHANGELOG.md` Unreleased / Added v2 |
| 退出清理 | 通过（代码审查） | `App.axaml.cs` 退出接线停止 Timer |
| 第三方告警归因 | 通过 | 构建警告仅为第三方 Avalonia 分析器版本提示与既有 CS8604（`VoxLogger.cs`），非本轮引入 |

## 5. 结论

- 本轮交付 v2 定时自动备份，改动覆盖服务主体、配置、桌面接线、ViewModel、测试与文档。
- 关闭 v1.3 报告 3.1 [未通过] 项。
- 构建通过；本轮新增代码零警告。
- `AutoBackupServiceTests` 共 7 例，覆盖禁用、非法间隔、重复 Start、Stop、空项目、周期触发、异常事件路径；xunit 在本机 testhost 挂起未能执行（环境问题），已改用控制台冒烟直验 DLL 6 项全过，xunit 待可用环境补跑。
- 已知限制见下节，未作隐瞒。

## 已知限制

1. 定时备份最小间隔为 1 分钟；该下限面向桌面场景，未针对更高频需求设计。
2. 自动备份保留份数与手动备份保留份数相互独立，二者不会合并计数或统一淘汰。
3. Timer 为进程内定时器，应用退出即停止；已接入 Exit 路径，但不存在跨进程或系统级调度能力。
