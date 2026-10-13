# CHANGELOG

本文件记录 VoxLoom（声纹工坊）每个版本的用户可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

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
