

# 技术债

机制：新出现的债记进下表，不口头记。每若干轮强制还一轮（v2 排期）。还掉一行就把状态改成"已偿还"并写上日期，行不删——留痕比表格好看重要。

| 编号 | 位置 | 描述 | 影响 | 偿还计划 | 状态 |
| --- | --- | --- | --- | --- | --- |
| TD-001 | AudioImporter/FfmpegDecoder | MP3/FLAC/M4A 依赖外部 ffmpeg，无纯托管解码 | 用户没装 ffmpeg 就导不进这三种格式 | v2 评估：MP3 用纯托管解码器替换（需先解决跨平台），或随安装包捆绑 ffmpeg | 待偿还 |
| TD-002 | BackupManager | 备份 zip 未加密，落盘明文 | 备份文件被拷贝即泄露音频内容 | v2：备份加密选项（密码走环境变量） | 待偿还 |
| TD-003 | FfmpegDecoder | 解码上限 1GB，一刀切拒绝 | 超长播客（>3 小时 48k 立体声）导不进 | v2：流式解码/分块载入 | 待偿还 |
| TD-004 | FfmpegDecoder | 只取第一条音轨（0:a:0），多音轨文件其余丢弃 | 少见，但用户可能困惑 | v2：导入时列出音轨让用户选 | 待偿还 |
| TD-005 | tests/VoxLoom.SmokeRunner | 本地测试走反射直跑（testhost IPC 在本 VM 不通），与 CI 的 vstest 双轨 | 本地跑法与 CI 不一致，[Theory] 在本地跑不了（已约束只用 [Fact]） | VM 环境修复后移除 SmokeRunner | 待偿还 |
| TD-006 | VoxLogger | WriteToConsole 输出原始 JSON 行，人读着费劲 | 排障时看控制台费眼 | v2：控制台用精简人读格式，文件保持 JSON | 待偿还 |
| TD-007 | MainViewModel.RestoreProjectAsync | 恢复目标目录必须为空，不支持合并恢复 | 用户想把备份并回现有项目时多一步 | v2：恢复前预览文件清单让用户选 | 待偿还 |
