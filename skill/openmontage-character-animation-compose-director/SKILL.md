---
name: openmontage-character-animation-compose-director
version: "1.0.0"
description: 角色动画管线的合成环节，按锁定运行时渲染已批准的角色动画并留下评审证据，适用于运行渲染、浏览器质检与最终验收的场景。
metadata:
  license: AGPL-3.0
---

# 合成导演（角色动画管线）

## 目标

渲染已批准的角色动画，并证明它经过了评审。

## 运行时路由

首先读取 `edit_decisions.render_runtime`。它必须与提案中锁定的运行时一致，除非有 `render_runtime_selection` 决策明确变更过。

- `remotion`：把资产暂存到 `remotion-composer/public`，构建 composition JSON，经 `video_compose` 渲染。
- `hyperframes`：物化一个 HyperFrames 工作区，让 `video_compose` 委派给 `hyperframes_compose`。`hyperframes lint` 与 `validate` 必须通过。
- `ffmpeg`：仅用于后期处理或简单拼接；单靠它不足以支撑角色表演。

## 评审工作流

1. 运行 `character_rig_renderer`，产出或刷新 HyperFrames 包。浏览器预览只作为质检/调试产物，不是渲染路径。
2. 确认渲染器输出了 HyperFrames 的 `workspace_path`、composition HTML、`asset_manifest`，以及 `edit_decisions.render_runtime: "hyperframes"` 交接信息。
3. 针对骨骼、姿势、时间线与预览运行 `character_animation_reviewer`。
4. 通过 `video_compose` 渲染成片，使用渲染器交接产物或已批准的 Remotion/HyperFrames 包。交付路径为 `projects/<project-name>/renders/final.mp4`，符合 OpenMontage 项目惯例。
5. 执行标准 `final_review`：ffprobe、抽帧、画面抽查、音频抽查、承诺一致性核对。

## 浏览器质检

Playwright 可用时：

- 打开预览，
- 抓取开头/中间/结尾帧，
- 检查控制台报错，
- 确认角色可见，
- 比较帧间差异以确认存在运动。

Playwright 不可用时，改用静态产物检查与 FFmpeg 抽帧，并说明置信度降低。

## 质量门槛

当 `character_qa_report.status` 为 `revise` 或 `fail` 时，不得把产物当作完成品呈现。
