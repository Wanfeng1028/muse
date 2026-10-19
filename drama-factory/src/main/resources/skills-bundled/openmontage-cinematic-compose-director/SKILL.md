---
name: openmontage-cinematic-compose-director
version: "1.0.0"
description: 以调色、音频动态和画框处理为重点渲染电影感作品；适用于预告片、品牌片等需要精细后期合成与输出的电影感项目。
metadata:
  license: AGPL-3.0
---

# 电影感流程 · 合成总监

## 何时启用

以对调色、音频动态和画框处理的细致关注来渲染电影感作品。这不是通用的导出步骤。

## 运行时路由（强制第一步）

阅读 `edit_decisions.render_runtime`。电影感作品路由到：

- **`render_runtime="remotion"`**——使用 `CinematicRenderer` 的视频主导预告片默认选项。将视频片段、转场和氛围叠加层保持在一次基于 React 的渲染中。
- **`render_runtime="hyperframes"`**——用于动态标题卡、HTML/GSAP 驱动的预告片、发布卷轴风格合成或显式 Three.js 世界飞行浏览。参见 `skills/core/hyperframes.md`。渲染前 `hyperframes check` 必须通过。
- **`render_runtime="ffmpeg"`**——无合成的简单源素材拼接。

对于 Blender 世界影片，FFmpeg 是编号 Blender 图像序列和音频的批准打包器。它不得合成摄像机运动或用平移/缩放效果替代缺失的 Blender 帧。

### 快速全曲节拍蒙太奇（BMTS-Lite）

当已批准的简报要求从一条提供的音乐轨道和已选视频片段快速制作蒙太奇——无需参考匹配、旁白、标题或语义片段选择——使用 `bgm_montage_lite` 作为完整渲染路径。传入源音频、所有预期源片段、项目目录和请求的宽高比（默认 `auto`）。该工具在流、尺寸、时长和全解码检查后返回 MP4、时间线、音频图和 OpenMontage 渲染报告。

这与专业参考引导的 BGM Montage 集成不同：Lite 不需要参考视频或 API 密钥，并有意保留 BMTS-Lite 源重用和自动取景。不要为此路由添加语义选择、严格重用限制、代理视觉审查依赖或第二渲染引擎。对于作者化场景和混合媒体工作，使用现有合成运行时；专业 BGM Montage 路由仍然是参考风格匹配及其更严格质量门禁的选择。

`delivery_promise.motion_required=true` 意味着锁定的运行时是承诺。静默切换到另一个运行时（包括 FFmpeg Ken Burns）是严重治理违规。如果锁定的运行时失败，按 AGENT_GUIDE.md > "Escalate Blockers Explicitly" 升级。

**将 `proposal_packet` 传给 `video_compose.execute()`**，使工具的 `runtime_swap_detected` 检查直接与 `proposal_packet.production_plan.render_runtime` 比较。没有它，交换检查在工具内被跳过，只有审查 skill 能捕获漂移。

## 前置条件

| 层级 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 剪辑计划与媒体素材 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`video_trimmer`、`color_grade`、`audio_enhance` | 渲染与后期 |
| Playbook | 当前风格 playbook | 后期一致性 |

## 流程

### 0. 渲染前检查硬性要求

如果已批准的简报或场景计划将运动作为硬性要求，验证渲染路径仍保留该承诺。

- 如果需要 Remotion 但不可用或失败，立即停止并将问题上报给用户。
- 不要为运动主导的预告片、先导片或代理视频切换到仅 FFmpeg 的静帧回退。
- 除非用户明确批准降级，不要将作品转换为动画分镜。
- 如果渲染引擎发生实质性变化，在渲染前告知用户并解释原因。

**强制 Remotion 预检（当场景计划包含任何 Remotion 场景类型——标题卡、数据卡、anime/hero_title、结束标签、叠加层——每次渲染前运行）：**

```bash
python -c "
from tools.tool_registry import registry
registry.discover()
info = registry.get('video_compose').get_info()
print('Render engines:', info.get('render_engines'))
print('Remotion note:', info.get('remotion_note'))
"
```
该命令查询工具注册表，确认 Remotion 是否在可用渲染引擎列表中。

如果 Remotion 不在可用渲染引擎中，按决策沟通契约停止并向用户报告。未经批准不得替换为降低保真度的渲染路径。

### 1. 有意识地使用画框处理

只有在有助于作品时才使用信箱、24fps 意图或重度调色。不要因为流程名称叫电影感就应用它们。

### 2. 保留音频动态

混音应允许：

- 安静时刻，
- 冲击时刻，
- 清晰的对白或旁白，
- 受控的音乐渐强。

### 3. 验证最终情绪

检查：

- 开场帧，
- 揭示节拍，
- 最终落点，
- 相关处的字幕可读性。

### 4. 使用渲染元数据

推荐元数据键：

- `frame_treatment`
- `grade_profile`
- `mix_notes`
- `variant_outputs`

## 常见陷阱

- 将音频压平使作品失去动态。
- 对需要每个像素的素材应用信箱。
- 让调色或锐化损坏面部或文字。
- 悄悄将被阻止的 Remotion 渲染替换为低保真度静帧导出。
