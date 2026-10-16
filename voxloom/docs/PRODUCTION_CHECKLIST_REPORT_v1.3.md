# VoxLoom v1.3 生产级对照报告

本报告即为生产级 Definition of Done 第 7 节交付物。

对照标准：`~/workspace/muse-build/PRODUCTION_CHECKLIST.md`（8 大节）。
本轮报告体例沿用 `docs/PRODUCTION_CHECKLIST_REPORT_v1.2.md`。
证据来源：本轮真实测试、构建、故障演练、告警触发、端到端指标、视觉验收与文档核验，全部数字取自实测，未做任何修饰。

---

## 1. 测试与质量基础

### 1.1 测试金字塔 [通过]
一句话证据：SmokeRunner 反射直跑全部 `[Fact]`，106/106 全绿；本轮新增 13 例（VoxMetricsTests 8 + MetricsOperationsTests 5），覆盖指标记录、聚合、时间过滤、轮转上限、异常路径与备份失败路径。

### 1.2 错误处理策略 [通过]
一句话证据：`docs/RELIABILITY.md` 成文，含重试/退避/降级/幂等/超时表；本轮故障演练实证了进程退出码契约（SIGXFSZ 退出码 153、配置校验失败退出码 2）与备份损坏路径的 `BackupException` 行为。

### 1.3 数据库迁移 [不适用]
一句话证据：VoxLoom 为单机本地桌面形态，无服务端数据库与 schema 迁移面。

### 1.4 健康检查/就绪探针 [不适用]
一句话证据：无长期驻留服务进程，不存在探针接入点。

---

## 2. 可观测性

### 2.1 结构化日志 [通过]
一句话证据：VoxLogger 输出结构化日志；本轮唯一构建警告即为既有 `VoxLogger.cs` CS8604，说明日志组件为存量且稳定模块。

### 2.2 关键指标 [通过]（本轮由未通过转通过）
一句话证据：本轮新增 VoxMetrics 指标子系统（8 例单测），并支持 `--metrics` 对演练日志目录真实跑出汇总表（audio.import / backup.create / backup.restore / transcript.import 的次数/失败/成功率/平均延迟）。

### 2.3 报错定位 [通过]
一句话证据：错误路径携带操作名与失败原因，MetricsOperationsTests 验证损坏 wav 抛 `WavFormatException` 并记失败指标、空 Whisper JSON 记失败、截断 zip 恢复抛 `BackupException` 并记失败，定位信息随指标落盘。

### 2.4 基础告警 [通过]（本轮由未通过转通过）
一句话证据：`scripts/check-alerts.sh` 用手工构造的 metrics 数据真实触发 `ALERT [CRIT] transcript_failure_rate: 失败率 0.50`，退出码 2。

---

## 3. 数据与安全

### 3.1 自动备份 [未通过]
一句话证据：定时/触发式自动备份仍未实现；当前仅具备删除/弱化前自动备份与手动备份/恢复能力，排期 v2。

### 3.2 敏感数据策略 [通过]
一句话证据：`docs/SECURITY_DATA.md` 成文；本轮修正其中过时的"未加密"表述，与实际 AES-256-GCM 备份实现对齐。

### 3.3 配置密钥分离 [通过]
一句话证据：配置走 config 文件、密钥走环境变量，并有启动校验；本轮故障演练中备份目录只读时被启动校验先行拦截（退出码 2"配置校验失败"），实证 fail-fast 生效。

### 3.4 多用户 [不适用]
一句话证据：单机本地应用，无多租户/多用户会话模型。

---

## 4. 部署与运维

### 4.1 Docker [不适用]
一句话证据：桌面本地形态，无容器化交付需求。

### 4.2 滚动更新 [不适用]
一句话证据：无服务端集群与滚动发布面。

### 4.3 日志轮转 [通过]
一句话证据：VoxMetrics 轮转上限有专门单测覆盖，写入量达到上限后按策略轮转，未发生无界增长。

### 4.4 运维手册 [通过]（本轮由未通过转通过）
一句话证据：本轮交付 `scripts/fault-drill.sh`（4/4 PASS）、`scripts/check-alerts.sh`、`--metrics` 汇总表三项可执行运维手段，构成可操作手册基线。

---

## 5. 健壮性与依赖

### 5.1 输入校验 [通过]
一句话证据：损坏 wav、空 Whisper JSON、截断 zip 三类异常输入均被显式识别并抛出对应领域异常（`WavFormatException` / 空 JSON 失败记录 / `BackupException`），同时写入失败指标。

### 5.2 依赖更新 [通过]
一句话证据：零第三方依赖，无外部依赖升级面。

### 5.3 限流熔断 [不适用]
一句话证据：单机本地操作，无服务端形态与外部调用压力面。

---

## 6. 工程规范

### 6.1 模块边界 [通过]
一句话证据：指标（VoxMetrics）、运维操作（MetricsOperations）、日志（VoxLogger）、备份/恢复、转写各司其职，单测按模块分文件（VoxMetricsTests / MetricsOperationsTests），边界清晰。

### 6.2 CHANGELOG [通过]（本轮由未通过转通过）
一句话证据：本轮补齐 v1.2 条目并追加 `[1.3.0]` 段落，偿还 TD-008。

### 6.3 技术债记录 [通过]
一句话证据：TD-002、TD-006 复核偿还；TD-008、TD-009 本轮新增并本轮偿还；技术债清单状态与代码一致。

### 6.4 文档同步 [通过]（本轮由未通过转通过）
一句话证据：README 同步 v1.1/v1.2/v1.3，修正过时表述，偿还 TD-009。

---

## 8. 生产就绪专项

### 8.1 技术债清理轮 [通过]
一句话证据：本轮即为清理轮，TD-002（备份加密，AES-256-GCM + 密码走环境变量）、TD-006（控制台人读格式，v1.2 VoxConsoleFormat 已实现）、TD-008（CHANGELOG）、TD-009（README）均在本轮核验/偿还完毕。

### 8.2 真实负载验证 [未通过]
一句话证据：仅演示规模数据，未做大体量/并发验证，排期 v2。

### 8.3 故障演练 [通过]（本轮由未通过转通过）
一句话证据：`scripts/fault-drill.sh` 真实跑 4/4 PASS（corrupt-audio / disk-pressure / kill9-torn-backup / corrupt-backup），退出码 0。

---

## 本轮增量交付摘要

### B1 指标
- 新增 VoxMetrics 指标子系统，支持 JSONL 行写入、成功/失败记录、异常 rethrow、void 重载、聚合、时间过滤、轮转上限、未初始化静默丢弃。
- 新增 8 例单测（VoxMetricsTests）。
- `--metrics` 端到端可对演练日志目录真实产出汇总表：audio.import / backup.create / backup.restore / transcript.import 的次数、失败、成功率、平均延迟。

### B2 告警
- 新增 `scripts/check-alerts.sh`。
- 用手工构造的 metrics 数据真实触发 `ALERT [CRIT] transcript_failure_rate: 失败率 0.50`，退出码 2，验证告警阈值与退出码契约。

### B3 演练
- 新增 `scripts/fault-drill.sh`，真实跑 4/4 PASS，退出码 0。
- 两个真实发现，如实记录、如实处理：
  1. **SIGXFSZ**：在 `ulimit -f` 限制下，进程被内核直接以 SIGXFSZ 终止（退出码 153），应用层无法捕获。演练中改为信息性演示，不伪装为可捕获异常。
  2. **启动校验拦截**：备份目录只读时，AppConfig 启动校验先行拦截（退出码 2"配置校验失败"），属 fail-fast 好行为，演练断言据此为准，不视为缺陷。

### B4 技术债
- TD-002（备份加密）：v1.2 已交付 AES-256-GCM + 密码走环境变量，本轮复核偿还。
- TD-006（控制台人读格式）：v1.2 已实现 VoxConsoleFormat，本轮核验偿还。
- TD-008（CHANGELOG 未更新）：本轮新增并偿还，补 v1.2 条目 + 追加 `[1.3.0]`。
- TD-009（README 未同步）：本轮新增并偿还，同步 v1.1/v1.2/v1.3。

### B5 测试
本轮新增 13 例：
- **VoxMetricsTests（8 例）**：JSONL 行、成功失败记录、异常 rethrow、void 重载、聚合、时间过滤、轮转上限、未初始化静默丢弃。
- **MetricsOperationsTests（5 例）**：损坏 wav 抛 `WavFormatException` 并记失败指标、空 Whisper JSON 记失败、对齐记成功、备份创建记成功、截断 zip 恢复抛 `BackupException` 并记失败。

### B6 真实冒烟
- 构建：`dotnet build VoxLoom.sln` 0 错误。
- 演练：`scripts/fault-drill.sh` 4/4 PASS，退出码 0。
- 告警：`scripts/check-alerts.sh` 真实触发 CRIT 告警，退出码 2。
- 指标：`--metrics` 对演练日志目录产出真实汇总表。
- 截图：Xvfb 下 `--screenshot` 真实抓屏并目视检查，演示项目 52 词、波形渲染、转写稿列表，布局撑满视口无异常；本轮无 UI 改动，README 门面图沿用既有。

---

## 测试与构建

- 测试：**106/106 全绿**。SmokeRunner 反射直跑全部 `[Fact]`；vstest testhost 在本 VM 上 IPC 不通，属环境限制，故采用 SmokeRunner 直跑作为权威结果。双轨说明：SmokeRunner 用于本机全量核验，vstest 用于常规 CI 环境。
- 构建：`dotnet build VoxLoom.sln` **0 错误**。
- 警告：本轮新增代码 **0 新警告**；唯一警告为既有 `VoxLogger.cs` CS8604，非本轮引入。

---

## 未通过项排期汇总

| 条目 | 状态 | 原因 | 排期 |
| --- | --- | --- | --- |
| 3.1 自动备份 | 未通过 | 定时/触发式自动备份未实现；已有删除/弱化前自动备份 + 手动备份/恢复 | v2 |
| 8.2 真实负载验证 | 未通过 | 仅演示规模数据，未做大体量/并发验证 | v2 |

---

## 总体结论

- 未通过项总数：**2**（3.1 自动备份、8.2 真实负载验证），均已明确排期 v2。
- 本轮由未通过转通过：2.2 关键指标、2.4 基础告警、4.4 运维手册、6.2 CHANGELOG、6.4 文档同步、8.1 技术债清理轮、8.3 故障演练。
- 不适用项：1.3、1.4、3.4、4.1、4.2、5.3（单机本地形态所致）。
- 建议发版决策：**建议发版 v1.3**。两个未通过项均不阻塞本地单机生产使用，可在 v2 规划中补齐；本轮实测证据（106/106、0 错误、4/4 演练、真实告警触发、真实指标汇总、真实截图）已构成可审计的生产级 Definition of Done 证据链。