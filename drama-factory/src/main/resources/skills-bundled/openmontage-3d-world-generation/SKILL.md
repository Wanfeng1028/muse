---
name: openmontage-3d-world-generation
version: "1.0.0"
description: 为动画或电影项目构建连续可编辑的 Three.js 三维场景，支持浏览器原生 HyperFrames 与 Blender/FFmpeg 两条交付路线，适用于需要真实立体空间感、统一坐标系与可复用制作资产的成片场景。
metadata:
  license: AGPL-3.0
---

# 三维世界生成

当项目需要的是连续、真实的三维环境，而非一堆静态图或拼接的生成片段时，启用本技能。

## 能力获取路径

1. 在注册表中检索 `3d_world_generation`、`3d_asset_acquisition`、`3d_asset_generation` 与 `3d_world_rendering` 四类工具。
2. 读取选中工具的 `agent_skills`；正式制作阶段必须同时加载 `.agents/skills/threejs-world-generation` 与 `.agents/skills/3d-asset-generation`。
3. 在提案阶段就确定交付路线：
   - 浏览器原生可编辑方案：`render_runtime="hyperframes"`，`composition_mode="atelier"`。
   - 离线渲染方案：`render_runtime="ffmpeg"`，由 Blender 输出编号 PNG 序列，再交由 FFmpeg 负责音视频封装。后者依旧是真实的三维运动，FFmpeg 只做打包。
4. 该能力同时服务于 `animation` 与 `cinematic` 两条流水线——三维世界属于可复用的制作能力，不是独立流水线。
5. 锁定精度等级。`blockout` 仅用于语义布局与机位试排；参考级/主角级画面必须使用 `production`，重复资产走授权素材库，独特资产按需调用 Atlas 或 fal，场景装配与渲染统一交给 `blender_world`。

## 各阶段产物约定

| 阶段 | 契约 |
|---|---|
| 提案 | 记录世界承诺、显式/推断策略、精度等级，并明确选择浏览器原生 Three.js/HyperFrames 路线还是 Blender/FFmpeg 路线。 |
| 剧本 | 采用节拍或稀疏字幕；旁白可选。 |
| 场景规划 | 在同一个连续坐标系中定义全局、区域、步行三个层级的机位节拍。 |
| 资产 | 用 `threejs_asset_catalog` 安装并清点重复资产；用 `atlas_3d` 或 `fal_3d` 采样独特主角资产；用 `blender_world` 装配并渲染全局/区域/步行静帧；网格登记为 `type="3d_asset"`，可编辑世界规格与 `.blend` 登记为 `type="3d_world"`。 |
| 资产评审 | 产出语义/线框诊断图与代表性快照；记录有界范围的返修项。 |
| 剪辑 | 沿用机位时间轴，不改动区域 ID 与随机种子。 |
| 合成 | 浏览器原生：对已编排的 HyperFrames 工作区调用 `video_compose`。Blender 路线：开启断点续渲输出编号 PNG 序列，再由 `video_compose`/FFmpeg 打包画面与音频，但不得宣称运动由 FFmpeg 生成。 |

## 资产元数据必填项

必须记录：

- `source_tool: "threejs_world"`；
- `provider: "threejs"`；
- `quality_tier`、`seed` 以及返回的模型标识；
- 素材库 ID、来源 URL、许可证、归档哈希、所选模型 ID、PBR 材质贴图；
- 工作区路径与 `world.json` 路径；
- 区域数、地标数、实例数、地形三角面数；
- 诊断告警与返修轮次；
- `layer3_skills_read: ["threejs-world-generation"]`。

## 评审关注点

- 地形连续，并确立大尺度剪影轮廓。
- 区域配色、起伏、散布与地标彼此符合同一套语义布局。
- 环境实例遵守坡度与接地约束。
- 全局、区域、步行三级画面保持空间一致。
- 机位不得穿透地形，也不得裁切远平面。
- 最终渲染保持可编辑性：世界、区域、地标、机位关键帧均为结构化文件。
- 正式帧在前景、中景、背景三个深度层使用带贴图的制作模型；大面积基础几何体或未贴图的平坦地面视为资产关卡不合格。

以下场景不要走本路径：孤立产品转台、CSS 视差风景、以及没有明确场景图的 AI 生成穿越镜头。
