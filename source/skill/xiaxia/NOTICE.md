# Copyright and Attribution Notice

## 夏夏

Copyright (c) 2026 栾意

Contact: <luanyi824@outlook.com>

本项目仅按 CC BY-NC 4.0 提供非商业使用许可。未经另行书面授权，不得用于商业项目；具体说明见 `COMMERCIAL_USE.md`。

夏夏 Skill 的核心架构、工作流整合与实现由栾意制作，包括：

- 剧本事实与状态锁；
- 时长预算和段落判型；
- 导演分镜与生成组体系；
- 中文文本分镜交付格式；
- Seedance 2.5 任务编译层；
- 分镜格式与时间码自动校验闭环。

## 底层方法来源

夏夏的底层电影视觉方法基于并改编自：

**《造梦师：AI时代电影视觉指南》 / `zy-cinematic-realism`**  
Copyright (c) 2026 ZY / popopo-99  
Source: <https://github.com/popopo-99/zy-cinematic-realism>  
License: Creative Commons Attribution-NonCommercial 4.0 International（CC BY-NC 4.0）

采用和改编的基础方法包括 Scene Master、摄影机观看位置、真实光源、构图、连续性 Bible / Shot Delta、反 AI 清理和提示词编译思想。

夏夏不是 ZY / popopo-99 或《造梦师：AI时代电影视觉指南》的官方发行版。与原项目相比，夏夏面向中文剧本到导演分镜及 AI 视频制作，重新设计了生产流程、生成组规范、文本格式、Seedance 适配和验证工具。

官方平台资料及其使用边界见 `references/research-sources.md`。

SPDX-License-Identifier: CC-BY-NC-4.0
