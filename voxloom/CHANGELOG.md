# CHANGELOG

本文件记录 VoxLoom（声纹工坊）每个版本的用户可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### Added（v2）
- 定时自动备份：`AutoBackupService` 按配置间隔（默认 60 分钟）自动备份当前项目；桌面启动时运行、退出时停止；备份存 `backups/auto` 子目录、独立保留份数（默认 5 份）；无已加载项目时跳过；失败只记日志不阻断编辑
- 配置项 `autoBackupEnabled` / `autoBackupIntervalMinutes` / `autoBackupRetentionCount` + `VOXLOOM_AUTOBACKUP_*` 环境变量覆盖；备份密码只从 `VOXLOOM_AUTOBACKUP_PASSWORD` 环境变量读取
- 关闭 v1.3 发版报告 3.1 未通过项（定时/触发式自动备份）

### Added（v1.1）
- 音频导入：MP3 / FLAC / M4A 真实解码（WAV 继续走纯托管；压缩格式走外部 ffmpeg，缺失时给中文安装指引）
- 结构化日志：JSON 行日志 + op_id 全链路关联 + 敏感字段脱敏 + 体积轮转（5MB/保留 10 份）
- 自动备份 + 一键恢复：删除/弱化前自动备份，工具栏手动备份/恢复，zip + manifest + sha256 校验，保留最近 10 份
- 配置与密钥分离：config.json + VOXLOOM_* 环境变量覆盖，配置文件禁密钥（启动校验，违规则退出码 2）
- 运维手册 docs/OPERATIONS.md、可靠性策略 docs/RELIABILITY.md、敏感数据策略 docs/SECURITY_DATA.md、技术债 docs/TECH_DEBT.md
- Dependabot（NuGet，每周）：voxloom/.github/dependabot.yml（待 gh token 补权限后迁仓库根）

### Fixed（v1.1）
- 日志轮转保留数多一个的 bug（先裁剪后建新文件导致稳态为 N+1）
- NAudio 的 Mp3FileReader 在 Linux 上不可用（依赖 Msacm32.dll），MP3 改走 ffmpeg，移除 NAudio 依赖
### Added（v1.2）
- 备份加密：`BackupManager.CreateBackup` 三参重载（`string? password = null`，双参保留兼容）；PBKDF2-SHA256（200,000 轮）派生 AES-256-GCM，文件格式 `VXENC1` 魔数+salt(16)+nonce(12)+tag(16)+密文，扩展名保持 `.zip`，恢复时按魔数自动识别；空密码/错密码给中文报错；无密码行为与旧格式完全兼容；密码永不进日志
- 恢复前文件清单预览：`ListBackupContents` 列出备份内文件（路径/大小/修改时间 UTC），`RestoreWithPreview` 打印清单→确认（`--yes` 跳过，拒绝则目标目录保持原样）
- 控制台日志人读格式：新增 `VoxConsoleFormat`（耗时/字节人读、表格 CJK 对齐、进度条、级别配色、重定向自动禁用颜色），文件日志保持 JSON；VoxLoom.Core 保持零第三方依赖

## [1.3.0] - 2026-10-16

### Added
- 操作指标：`VoxLoom.Core.Logging.VoxMetrics` 记录转写导入/对齐/剪辑/EDL 导出/备份恢复的操作计数与延迟，落 `metrics-YYYYMMDD.jsonl`（字段 ts/op/duration_ms/success/error_type/items，复用 5MB/10 份体积轮转）；`VoxLoom.Desktop --metrics [--json] [--hours N]` 输出汇总
- 告警：`docs/ALERTS.md`（转写失败率/剪辑冲突率/磁盘空间不足/备份失败 4 条规则：阈值/级别/处置步骤）+ `scripts/check-alerts.sh`（扫描 metrics.jsonl，退出码 0=无告警、1=警告、2=严重）
- 故障演练：`scripts/fault-drill.sh`（损坏音频拒绝不崩溃、只读存储模拟磁盘满、kill -9 后半截备份拒绝恢复、位翻转备份拒绝恢复，每项 PASS/FAIL 明确输出；另附 ulimit -f 下 SIGXFSZ 行为的实测说明）
- 运维探针 CLI：`--probe-import/--probe-backup/--probe-restore`（成功 `OK` 退出 0，失败 `ERROR:` 退出 3，备份密码只读环境变量 `VOXLOOM_BACKUP_PASSWORD`）
- 运维手册：`docs/OPERATIONS.md` 补齐配置/日志/指标告警/备份恢复/演练/排障章节

### Fixed
- README 过时信息修正：测试数 44→93（SmokeRunner/CI 说明）、"备份 zip 未加密"改为可选加密说明、补 CLI/日志/指标章节（偿还 TD-009）
- CHANGELOG 补 v1.2 条目（偿还 TD-008）；TD-006（控制台人读格式）经核验已由 v1.2 的 VoxConsoleFormat 实现，标记已偿还

## [0.1.0] - 2026-10-13


首个可用版本：中文播客文字剪辑核心链路跑通。

### Added
- 音频导入（WAV）+ 多级 LOD 波形渲染，万级采样点流畅绘制
- 转写稿导入：Whisper JSON / LRC / 纯文本三种格式
- 规则对齐：转写稿时间轴按语音能量精修，文字↔音频双向定位
- 文字删除 → 音频剪辑：DeleteOp + 过零点拼接，防爆音
- 语气词（嗯/那个/对吧…）检测与一键弱化（-12dB，首尾 50ms raised-cosine 过渡）
- 导出 EDL（CMX3600），供 Premiere / Reaper 精修
- 演示模式：`--demo-wav` 生成演示音频与转写稿，`--screenshot` 离屏抓屏
- Avalonia 桌面 UI：录音棚深色风（#1C1A17 + 纸色波形 + 橙色高亮）
- 端到端链路测试：导入→对齐→删除→弱化→导出，44/44 全绿
- GitHub Actions CI（ubuntu + windows）
- 生产级对照报告：docs/PRODUCTION_CHECKLIST_REPORT.md（18 项未通过，v1.1/v2 排期）

### Known limitations
- 对齐为规则方案（能量检测），长音频/多人对话精度有限；v2 接 ONNX 本地语音模型
- 仅支持 WAV 导入；MP3/FLAC/M4A 待 v1.1
- 无结构化日志、无自动备份，见对照报告
