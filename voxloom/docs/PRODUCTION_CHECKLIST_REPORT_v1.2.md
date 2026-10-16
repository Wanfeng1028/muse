# VoxLoom v1.2 生产级对照报告

> 本报告即为生产级 Definition of Done 第 7 节交付物。

## 1. 质量与可靠性

### 1.1 测试金字塔

[通过] 93/93 全绿，新增 18 例覆盖加密/预览/人读化关键路径。

本轮测试通过 SmokeRunner 反射直跑；vstest testhost 在本 VM 上 IPC 连不通，属环境限制，不影响本轮结论。新增 18 例构成如下：

- B1 6 例：加密往返、错密码、无密码需密码、无密码兼容旧格式、空密码拒绝、加密标记与旧 sidecar 兼容。
- B2 5 例：清单内容、加密清单需密码、预览打印并恢复、拒绝中止、`--yes` 跳过确认。
- B3 7 例：耗时人读、字节人读、行形状、表格 CJK 对齐、进度条、脱敏、颜色映射。

### 1.2 错误处理策略

[未通过] 仍无重试/退避/降级/幂等的成文策略。排期 v1.3。

本轮 B1/B2 在备份密码为空、密码错误、恢复被拒绝等路径上给出诚实报错文案，但这属于局部错误处理，尚不构成覆盖全链路的成文策略。

### 1.3 数据库迁移

[不适用] 无数据库。

### 1.4 健康检查/就绪探针/优雅关闭

[不适用] 单机桌面应用。

## 2. 可观测性

### 2.1 结构化日志

[通过] 文件日志 JSON 结构化（含 op/op_id 关联）；v1.2 补齐控制台人读渲染，脱敏不变。

`VoxLogger` 文件日志保持 JSON 不变，控制台改走人读行，脱敏逻辑不变。密码永不进日志（VoxLogger 对 password 字段脱敏为 `***`）。

### 2.2 关键指标暴露

[未通过] 无指标采集。排期 v2。

### 2.3 报错定位

[通过] op/op_id + 人读控制台行（含密码错误等诚实报错文案）。

新增 `VoxConsoleFormat.RenderLine` 输出形如 `[14:32:05] INFO  备份完成 op=backup id=a1b2c3d4 bytes=1.5 KB`，与 op/op_id 关联保持一致。

### 2.4 基础告警

[未通过] 无告警规则。排期 v2。

## 3. 数据与备份

### 3.1 自动备份+一键恢复

[未通过] v1.2 把手动备份/恢复链路加固（加密、清单预览确认、sidecar+manifest 双校验）并实测；但定时/触发式自动备份仍未实现。排期 v1.3。

本轮实际交付的加固内容：

- B1 备份加密：`BackupManager.CreateBackup` 新增三参重载（`string? password = null`，双参保留兼容）；密码经 PBKDF2-SHA256（200,000 轮）派生 AES-256-GCM 密钥；加密文件格式 `VXENC1` 魔数+salt(16)+nonce(12)+tag(16)+密文，扩展名保持 `.zip`，恢复时按魔数自动识别；空密码抛 `BackupException("备份密码不能为空")`；错密码恢复抛 `BackupException("备份密码错误，无法解密")`；无密码行为与旧格式完全兼容；`BackupRecord` 新增 `Encrypted` 属性（旧 sidecar JSON 反序列化默认为 false）。
- B2 恢复预览：新增 `BackupEntryInfo(Path, SizeBytes, ModifiedUtc)`；`ListBackupContents(backupId, password)` 按路径排序列出 zip 内文件；`RestorePreviewOptions{Password, AutoConfirm, Output, Confirmer}`；`RestoreWithPreview` 打印文件清单（路径/人读大小/修改时间UTC）→ 目标目录 → 确认（`--yes` 即 AutoConfirm 跳过；拒绝抛 `BackupException("已取消恢复")`，目标目录保持原样）→ 执行恢复。

### 3.2 敏感数据策略

[未通过] 实践已到位（密码只以 salt+nonce+密文落盘、日志脱敏），但成文策略文档仍缺。排期 v1.3。

### 3.3 配置密钥分离

[未通过] 备份密码由调用方传入、未落配置文件是现状，但无启动校验与成文规范。排期 v1.3。

### 3.4 多用户设计

[不适用] 单机单用户。

## 4. 部署与运维

### 4.1 Docker Compose

[不适用] 桌面应用走安装包分发。

### 4.2 滚动更新/零停机

[不适用] 安装包更新形态。

### 4.3 资源限制/日志轮转

[通过] VoxLogger 已有按体积轮转与保留份数（本轮未动）。

### 4.4 运维手册

[未通过] 无独立运维手册。排期 v1.3。

## 5. 安全

### 5.1 输入校验/防注入

[通过] 路径穿越防护、空密码拒绝、加密魔数识别；单机场景无鉴权需求。

### 5.2 依赖更新机制

[通过] 零第三方依赖（Spectre.Console 选型后明确拒绝引入），无更新负担。

选型实测：`dotnet add package Spectre.Console` 解析到 0.57.2 并还原成功（4.02 秒），但为保零依赖未引入。三步选型过程为：dpsk 候选对比 → Keenable 核验 Spectre.Console 0.57.2 仍在维护 → `dotnet add` 实测可装，结论选手工排版，VoxLoom.Core 保持零第三方依赖。

### 5.3 限流/超时/熔断

[不适用] 单机本地操作。

## 6. 工程与文档

### 6.1 模块边界/API 契约

[通过] BackupCrypto/BackupManager/VoxConsoleFormat 边界清晰，旧 API 签名全部保留兼容。

### 6.2 CHANGELOG+升级指南

[未通过] 本轮未更新 CHANGELOG.md。排期下轮（记入技术债）。

### 6.3 技术债记录

[通过] docs/TECH_DEBT.md 存在；本轮新增“CHANGELOG 未更新、README 未同步”两条。

### 6.4 文档代码同步

[未通过] voxloom README 尚未同步备份加密/恢复预览/人读日志说明。排期下轮。

## 7. 本轮增量交付摘要

### 7.1 B1 备份加密

`BackupManager.CreateBackup` 新增三参重载（`string? password = null`，双参保留兼容）；密码经 PBKDF2-SHA256（200,000 轮）派生 AES-256-GCM 密钥；加密文件格式 `VXENC1` 魔数+salt(16)+nonce(12)+tag(16)+密文，扩展名保持 `.zip`，恢复时按魔数自动识别；空密码抛 `BackupException("备份密码不能为空")`；错密码恢复抛 `BackupException("备份密码错误，无法解密")`；无密码行为与旧格式完全兼容；`BackupRecord` 新增 `Encrypted` 属性（旧 sidecar JSON 反序列化默认为 false）；密码永不进日志（VoxLogger 对 password 字段脱敏为 `***`）。

### 7.2 B2 恢复预览

新增 `BackupEntryInfo(Path, SizeBytes, ModifiedUtc)`；`ListBackupContents(backupId, password)` 按路径排序列出 zip 内文件；`RestorePreviewOptions{Password, AutoConfirm, Output, Confirmer}`；`RestoreWithPreview` 打印文件清单（路径/人读大小/修改时间UTC）→ 目标目录 → 确认（`--yes` 即 AutoConfirm 跳过；拒绝抛 `BackupException("已取消恢复")`，目标目录保持原样）→ 执行恢复。

### 7.3 B3 日志人读化

三步选型（dpsk 候选对比 → Keenable 核验 Spectre.Console 0.57.2 仍在维护 → `dotnet add` 实测可装）结论选手工排版，VoxLoom.Core 保持零第三方依赖；新增 `VoxConsoleFormat`（`FormatDuration` 如 `3.2s`、`FormatBytes` 如 `1.5 KB`、`RenderLine` 如 `[14:32:05] INFO  备份完成 op=backup id=a1b2c3d4 bytes=1.5 KB`、`RenderTable` CJK 宽字符按 2 列对齐、`RenderProgressBar`、`ColorFor` 级别配色、重定向输出时自动禁用颜色）；`VoxLogger` 文件日志保持 JSON 不变，控制台改走人读行，脱敏逻辑不变。

### 7.4 测试与构建

- 测试：93/93 全绿（SmokeRunner 反射直跑；vstest testhost 在本 VM 上 IPC 连不通，属环境限制）。其中本轮新增 18 例：B1 6 例（加密往返/错密码/无密码需密码/无密码兼容旧格式/空密码拒绝/加密标记与旧 sidecar 兼容）、B2 5 例（清单内容/加密清单需密码/预览打印并恢复/拒绝中止/`--yes` 跳过确认）、B3 7 例（耗时人读/字节人读/行形状/表格CJK对齐/进度条/脱敏/颜色映射）。
- 构建：`dotnet build VoxLoom.sln` 0 错误（6 个既有警告与本轮无关，位于 ScreenshotService/MainWindow）。
- 选型实测：`dotnet add package Spectre.Console` 解析到 0.57.2 并还原成功（4.02 秒），但为保零依赖未引入。

## 8. 未通过项排期汇总

| 条目 | 结论 | 排期 |
| --- | --- | --- |
| 1.2 错误处理策略 | [未通过] | v1.3 |
| 2.2 关键指标暴露 | [未通过] | v2 |
| 2.4 基础告警 | [未通过] | v2 |
| 3.1 自动备份+一键恢复 | [未通过] | v1.3 |
| 3.2 敏感数据策略 | [未通过] | v1.3 |
| 3.3 配置密钥分离 | [未通过] | v1.3 |
| 4.4 运维手册 | [未通过] | v1.3 |
| 6.2 CHANGELOG+升级指南 | [未通过] | 下轮（记入技术债） |
| 6.4 文档代码同步 | [未通过] | 下轮 |

## 9. 技术债

本轮新增两条技术债，已记入 docs/TECH_DEBT.md：

- CHANGELOG 未更新。
- README 未同步。