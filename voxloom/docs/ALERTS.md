# VoxLoom 告警规则手册

本手册面向单机桌面用户，帮助你自己排查 VoxLoom 运行中的问题。VoxLoom 没有服务端，所有指标都以本地 JSONL 形式落盘，告警由配套脚本 `scripts/check-alerts.sh` 扫描日志后判定。

---

## 一、指标来源

- 指标文件：日志目录下的 `metrics-YYYYMMDD.jsonl`，每行一条 JSON 记录。
- 字段：`ts`（UTC ISO8601）、`op`、`duration_ms`、`success`、`error_type`、`items`。
- 操作名：`audio.import`、`transcript.import`、`align`、`edit.apply`、`export.edl`、`backup.create`、`backup.restore`。
- 日志目录：默认 `appdir/logs`，可用环境变量 `VOXLOOM_LOG_DIR` 覆盖。**实际取值以配置文件 / 环境变量为准**，请以你机器上的 AppConfig 为准。

---

## 二、运行方式

```bash
# 默认扫描日志目录（appdir/logs），窗口为近 24 小时
scripts/check-alerts.sh

# 指定日志目录
scripts/check-alerts.sh --dir /path/to/logs

# 指定回看小时数
scripts/check-alerts.sh --hours 24

# 组合使用
scripts/check-alerts.sh --dir "$VOXLOOM_LOG_DIR" --hours 24
```

定时巡检（cron 示例，每 30 分钟一次）：

```cron
*/30 * * * * /path/to/voxloom/scripts/check-alerts.sh >> /path/to/voxloom/logs/check-alerts.log 2>&1
```

---

## 三、退出码语义

| 退出码 | 含义 |
| --- | --- |
| `0` | 无告警 |
| `1` | 存在至少一条 warning |
| `2` | 存在至少一条 critical |

在 cron 中可结合 `||` 做进一步通知，例如 `... || mail -s "VoxLoom 告警" you@example.com`。

---

## 四、告警规则

### 规则 1：转写失败率

- **规则名**：转写失败率偏高
- **监控对象**：操作 `transcript.import`，统计窗口近 24 小时。
- **阈值**：
  - 样本数 ≥ 5 且失败率 ≥ 10% → warning
  - 样本数 ≥ 5 且失败率 ≥ 30% → critical
- **级别**：warning / critical（按上述阈值升级）
- **触发条件精确描述**：在近 24 小时窗口内，满足 `op == "transcript.import"` 的记录总条数记为 `n`，其中 `success == false` 的条数记为 `f`。当 `n ≥ 5` 且 `f / n ≥ 0.10` 时判 warning；当 `n ≥ 5` 且 `f / n ≥ 0.30` 时判 critical（critical 覆盖 warning）。
- **处置步骤**：
  1. 打开日志目录，检索近 24h 的 `metrics-*.jsonl`，过滤 `op == "transcript.import"` 且 `success == false` 的记录。
  2. 统计这些记录里 `error_type` 的分布，找出占主导的错误类型。
  3. 若 `error_type` 指向转写稿格式问题（如解析/编码类错误），用其它格式（如换成 UTF-8 纯文本或 SRT）重新导出转写稿后再导入。
  4. 若同一错误连续两次以上判定为 critical，把对应的 `metrics-*.jsonl` 与出错转写稿一起打包，到项目 issue 区提交并附上复现步骤。
  5. 若失败集中在某一次批量导入，先单独重试该文件，确认是否偶发。

---

### 规则 2：剪辑冲突率

- **规则名**：剪辑冲突率偏高
- **监控对象**：操作 `edit.apply` 且 `error_type == "EditConflictException"`，统计窗口近 24 小时。
- **阈值**：
  - 样本数 ≥ 10 且冲突占比 ≥ 5% → warning
  - 样本数 ≥ 10 且冲突占比 ≥ 15% → critical
- **级别**：warning / critical（按上述阈值升级）
- **触发条件精确描述**：在近 24 小时窗口内，满足 `op == "edit.apply"` 的记录总条数记为 `n`，其中 `error_type == "EditConflictException"` 的条数记为 `c`。当 `n ≥ 10` 且 `c / n ≥ 0.05` 时判 warning；当 `n ≥ 10` 且 `c / n ≥ 0.15` 时判 critical（critical 覆盖 warning）。
- **处置步骤**：
  1. 先明确：`EditConflictException` 是应用对重叠/越界编辑的保护行为，**不是 bug**。
  2. 回看自己最近的操作，检查是否误选了重叠的词段或跨段选区。
  3. 缩小选区范围，确认时间轴无重叠后重新执行 `edit.apply`。
  4. 若同一素材上冲突仍频繁出现，改为分段编辑：把长片段拆成若干互不重叠的小段，逐段应用。
  5. 若分段后依旧高发，记录该素材的时间码区间，保留日志以便进一步定位。

---

### 规则 3：磁盘空间不足

- **规则名**：磁盘空间不足
- **监控对象**：日志目录与备份目录所在分区（用 `df` 查看）。
- **阈值**：
  - 可用空间 < 5 GiB → warning
  - 可用空间 < 1 GiB → critical
- **级别**：warning / critical（按上述阈值升级）
- **触发条件精确描述**：对日志目录和备份目录分别执行 `df -h`（或 `df -k` 并换算），取对应挂载点的可用空间 `avail`。当 `avail < 5 GiB` 时判 warning；当 `avail < 1 GiB` 时判 critical（critical 覆盖 warning）。两个目录落在同一分区时按同一分区判定。
- **处置步骤**：
  1. 用 `df -h` 确认日志目录与备份目录各自所在分区及当前可用空间。
  2. 清理旧日志：`metrics-*.jsonl` 按 10 份轮转，可手动删除更早的日期文件（保留最近 10 份）。
  3. 清理旧备份：只保留最近 10 份备份，其余删除。
  4. 若清理后仍不足，把日志目录或备份目录迁移到空间更大的分区，并同步更新配置 / 环境变量。
  5. 迁移后重新运行 `scripts/check-alerts.sh` 确认告警解除。

---

### 规则 4：备份失败

- **规则名**：备份失败
- **监控对象**：操作 `backup.create` 与 `backup.restore`，统计窗口近 24 小时。
- **阈值**：
  - 出现 1 次 `success == false` → warning
  - 出现 ≥ 3 次 `success == false` → critical
- **级别**：warning / critical（按上述阈值升级）
- **触发条件精确描述**：在近 24 小时窗口内，满足 `op == "backup.create"` 或 `op == "backup.restore"` 且 `success == false` 的记录条数记为 `b`。当 `b == 1` 时判 warning；当 `b ≥ 3` 时判 critical（critical 覆盖 warning）。
- **处置步骤**：
  1. 过滤出上述失败记录，读取其 `error_type`。
  2. 若 `error_type == "BackupException"`，读其 message 并按分支处理：
     - 密码错误：重新输入正确密码后重试。
     - 目录不存在：创建目标目录（或改回存在的目录）后重试。
     - 磁盘满：先按规则 3 清理空间，再重试。
  3. 用备份功能的 `--metrics` 选项，结合失败记录的 `ts` 定位到具体时间点，确认当时正在处理哪个备份。
  4. 手动执行一次备份，确认成功。
  5. 若同一错误连续出现 3 次以上，保留对应日志与命令输出，到项目 issue 区提交。

---

## 五、误报说明

- **样本不足不告警**：规则 1 要求 `transcript.import` 样本 ≥ 5，规则 2 要求 `edit.apply` 样本 ≥ 10；低于阈值一律不告警，避免小样本抖动导致误报。
- **窗口滚动**：所有比率类规则都按近 24 小时滚动计算，跨零点时结果可能短暂波动，属正常现象。
- **备份规则不设最小样本**：备份本身低频，1 次失败即值得关注，因此不设样本下限。
- **磁盘规则独立于指标**：由 `df` 实时读取，与 `metrics-*.jsonl` 无关，日志文件缺失时仍会判定。

---

## 六、与运维文档的关系

日常巡检、日志轮转、备份保留策略等操作细节，请参见 `docs/OPERATIONS.md`；本手册只负责"什么情况算告警、告警后怎么动手"。