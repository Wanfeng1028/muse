# VoxLoom 运维手册

本文档描述 VoxLoom 单机桌面应用的运维操作：目录结构、配置与密钥、日志、指标与告警、备份与恢复、故障演练、常见故障排查、升级与卸载。

VoxLoom 是单机 Avalonia 桌面应用，VoxLoom.Core 零第三方依赖，目标框架 net8.0。应用以安装包形式分发，**无 Docker 镜像、无容器编排、无滚动更新、无集群形态**；下述所有运维动作均在单台机器的用户会话与文件系统内完成。

---

## 1. 目录结构

数据目录默认为 `~/.config/VoxLoom/`（即 ApplicationData），可用环境变量覆盖。

```
appdir/
  config.json      配置文件
  logs/            日志目录（默认 logDirectory）
  backups/         备份目录（默认 backupDirectory）
  projects/        项目目录（默认 projectsDirectory）
```

- `appdir` 是数据目录根，默认 `~/.config/VoxLoom/`。
- `config.json` 位于 `appdir` 根下，保存全部可配置项。
- `logs/`、`backups/`、`projects/` 的物理位置由 `config.json` 中的 `logDirectory`、`backupDirectory`、`projectsDirectory` 决定，默认分别为上述三个子目录；也可以被环境变量覆盖，覆盖后实际路径以覆盖值为准。

---

## 2. 配置与密钥

### 2.1 config.json 键表

配置文件为 `appdir/config.json`。

| 键 | 含义 |
| --- | --- |
| `ffmpegPath` | ffmpeg 可执行文件路径 |
| `logDirectory` | 日志目录 |
| `backupDirectory` | 备份目录 |
| `projectsDirectory` | 项目目录 |
| `backupRetentionCount` | 备份保留份数 |
| `autoBackupEnabled` | 定时自动备份开关（默认 true） |
| `autoBackupIntervalMinutes` | 自动备份间隔分钟数（默认 60，1~1440） |
| `autoBackupRetentionCount` | 自动备份保留份数（默认 5，存 backups/auto 子目录） |


### 2.2 环境变量覆盖表

环境变量优先级高于 `config.json` 中对应键。

| 环境变量 | 覆盖的配置键 |
| --- | --- |
| `VOXLOOM_FFMPEG_PATH` | `ffmpegPath` |
| `VOXLOOM_LOG_DIR` | `logDirectory` |
| `VOXLOOM_BACKUP_DIR` | `backupDirectory` |
| `VOXLOOM_PROJECTS_DIR` | `projectsDirectory` |
| `VOXLOOM_BACKUP_RETENTION` | `backupRetentionCount` |
| `VOXLOOM_AUTOBACKUP_ENABLED` | `autoBackupEnabled` |
| `VOXLOOM_AUTOBACKUP_INTERVAL_MINUTES` | `autoBackupIntervalMinutes` |
| `VOXLOOM_AUTOBACKUP_RETENTION` | `autoBackupRetentionCount` |

### 2.3 禁密钥规则与退出码

`config.json` 中禁止存放密钥。任何键名包含 `password`、`passwd`、`secret`、`token`、`apikey` 的条目都会触发 `ConfigValidationException`，应用启动失败并**退出码 2**。

处置方式：删除违规键，或将其值移出配置文件（例如备份密码改为运行时通过只读环境变量 `VOXLOOM_BACKUP_PASSWORD` 提供）。

### 2.4 形态限制声明

VoxLoom 是桌面应用，以安装包分发，**无 Docker 形态**。不存在容器镜像、容器内数据卷、容器健康检查、容器编排滚动更新等概念；所有运维动作直接作用于本机数据目录与进程。

---

## 3. 日志

### 3.1 文件位置与格式

日志文件位于日志目录下，命名 `logs/voxloom-YYYYMMDD.log`，每行一条 JSON。

| 字段 | 含义 |
| --- | --- |
| `ts` | 时间戳 |
| `level` | 日志级别 |
| `op` | 操作名 |
| `op_id` | 操作关联 ID，全链路关联 |
| `msg` | 消息 |
| `data` | 结构化附加数据 |
| `ex` | 异常信息 |

敏感字段在写入前脱敏为 `***`。

### 3.2 人读控制台

控制台输出使用 VoxConsoleFormat 人读行；输出被重定向时自动去色，便于落盘与检索。

### 3.3 轮转策略

单文件上限 5MB，保留 10 份。

### 3.4 op_id 排障示例

一次操作的所有日志行共享同一 `op_id`。按 `op_id` 过滤即可还原该次操作的完整链路：

```bash
grep '<op_id>' logs/voxloom-*.log
```

若需跨天排查，使用通配符覆盖多个日志文件；先定位失败行的 `op_id`，再用上述命令拉出该 `op_id` 的全部行。

---

## 4. 指标与告警

### 4.1 metrics.jsonl 字段表

指标文件位于日志目录下，命名 `logs/metrics-YYYYMMDD.jsonl`，每行一条 JSON。

| 字段 | 含义 |
| --- | --- |
| `ts` | 时间戳 |
| `op` | 操作名 |
| `duration_ms` | 耗时（毫秒） |
| `success` | 是否成功 |
| `error_type` | 错误类型 |
| `items` | 处理条目数 |

操作名取值：`audio.import`、`transcript.import`、`align`、`edit.apply`、`export.edl`、`backup.create`、`backup.restore`。

### 4.2 `--metrics` 用法

```bash
VoxLoom.Desktop --metrics [--json] [--hours N]
```

- 默认统计近 24 小时。
- `--json` 输出 JSON。
- `--hours N` 指定统计窗口为近 N 小时。

### 4.3 ALERTS.md 规则摘要

`docs/ALERTS.md` 定义 4 条规则，含阈值与级别。

| 规则 | 关注对象 |
| --- | --- |
| 转写失败率 | 转写相关操作失败比例 |
| 剪辑冲突率 | 剪辑应用冲突比例 |
| 磁盘空间不足 | 数据目录所在磁盘可用空间 |
| 备份失败 | 备份创建/恢复失败 |

具体阈值与级别以 `docs/ALERTS.md` 为准。

### 4.4 check-alerts.sh 用法与退出码

```bash
scripts/check-alerts.sh [--dir 日志目录] [--hours N]
```

| 退出码 | 含义 |
| --- | --- |
| 0 | 无告警 |
| 1 | 仅 WARN |
| 2 | 有 CRIT |

### 4.5 cron 示例

```cron
*/30 * * * * /path/to/check-alerts.sh --dir /home/user/.config/VoxLoom/logs >> /var/log/voxloom-alerts.log 2>&1
```

---

## 5. 备份与恢复

### 5.1 自动备份时机

在删除或弱化数据之前，自动触发备份。

### 5.2 手动备份与恢复

工具栏提供手动备份与恢复入口。

### 5.3 加密

备份支持加密，算法 AES-256-GCM；备份密码通过环境变量提供，配置文件与命令行中不出现明文密码。

### 5.4 恢复预览

恢复前展示文件清单预览并要求确认；使用 `--yes` 可跳过确认。探针路径下若需密码，只读环境变量 `VOXLOOM_BACKUP_PASSWORD`。

### 5.5 保留策略

备份保留最近 10 份，保留份数由 `backupRetentionCount` / `VOXLOOM_BACKUP_RETENTION` 决定。

### 5.6 备份格式

备份为 zip + manifest + sha256。

### 5.7 探针 CLI 用法

```bash
VoxLoom.Desktop --probe-import <音频>
VoxLoom.Desktop --probe-backup <项目目录> <项目名>
VoxLoom.Desktop --probe-restore <backupId> <目标目录>
```

约定：

- 成功：stdout 以 `OK` 开头，退出码 0。
- 失败：stderr 输出 `ERROR: <message>`，退出码 3。
- 缺参数：退出码 2。
- 备份密码只读环境变量 `VOXLOOM_BACKUP_PASSWORD`。

---

## 6. 故障演练

```bash
scripts/fault-drill.sh [--dll 路径] [--work 工作目录]
```

4 项演练：

| 演练项 | 说明 |
| --- | --- |
| `corrupt-audio` | 损坏音频应被拒绝，且进程不崩溃 |
| `disk-pressure` | 用 `ulimit -f` 配额模拟磁盘满 |
| `kill9-torn-backup` | `kill -9` 造成半截备份，应拒绝恢复 |
| `corrupt-backup` | 位翻转备份，应拒绝恢复 |

每项输出 `DRILL <名>: PASS/FAIL - <原因>`。

- PASS：该演练预期行为成立（拒绝、不崩溃、拒绝恢复等）。
- FAIL：预期行为未成立，按 `<原因>` 定位。

演练工作目录通过 `--work` 指定，与真实数据目录隔离，演练产物不写入生产数据目录。

---

## 7. 常见故障排查

| 现象 / ERROR 文案 | 原因 | 处置 |
| --- | --- | --- |
| `ERROR: 缺少 RIFF 标识，可能不是 WAV 文件。`（或`文件过小…`） | 音频文件损坏或路径不可读 | 用 `VoxLoom.Desktop --probe-import <音频>` 复现；确认文件可读、格式受支持；损坏则更换源文件后重试 |
| `ERROR: Whisper JSON 内容为空。`（或 LRC/纯文本解析报错） | 转写稿格式不符合预期 | 核对转写稿字段与分隔符；修正后重新执行 `transcript.import`；可用同一 `op_id` 在 `logs/voxloom-*.log` 中查看解析失败行 |
| `EditConflictException`（剪辑冲突） | 剪辑应用时检测到冲突 | 在 `logs/metrics-*.jsonl` 中过滤 `op=edit.apply` 与 `success=false` 行确认冲突；回退冲突编辑后重新应用 |
| `ERROR: 备份密码错误，无法解密` | 备份密码错误或未提供 | 确认只读环境变量 `VOXLOOM_BACKUP_PASSWORD` 已设置为正确密码；重设后重试 `--probe-restore` |
| 备份/日志写入失败（磁盘满或目录不可写） | 数据目录所在磁盘空间不足 | 用 `df -h <数据目录>` 确认剩余空间；清理 `logs/` 旧文件或迁移 `backupDirectory`、`projectsDirectory` 到空间充足的磁盘 |
| 启动失败，退出码 2，`配置校验失败`（`ConfigValidationException`） | `config.json` 中存在含 `password`/`passwd`/`secret`/`token`/`apikey` 的键，或备份/日志目录不可写 | 编辑 `config.json` 删除违规键；密码类信息改由环境变量提供；重启应用 |
| `ERROR:` 恢复时报备份校验失败（manifest/sha256 不匹配或 zip 损坏） | 备份校验失败（manifest 或 sha256 不匹配） | 用 `VoxLoom.Desktop --probe-restore <backupId> <目标目录>` 复现；选取通过校验的其他备份；若怀疑备份损坏，用 `scripts/fault-drill.sh` 的 `corrupt-backup` 项确认拒绝行为 |
| `--metrics` 无数据 | 统计窗口内无指标写入，或日志目录指向错误 | 用 `VOXLOOM_LOG_DIR` 或 `config.json` 的 `logDirectory` 核对日志目录；确认 `logs/metrics-YYYYMMDD.jsonl` 存在且时间落在 `--hours N` 窗口内；扩大 `--hours` 重试 |

---

## 8. 升级与卸载

升级：覆盖安装即可，数据目录保留。卸载：删除 appdir。
