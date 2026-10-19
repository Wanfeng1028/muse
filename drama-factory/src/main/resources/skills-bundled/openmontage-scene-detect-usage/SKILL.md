---
name: openmontage-scene-detect-usage
version: "1.0.0"
description: 说明如何在 OpenMontage 中使用 scene_detect 工具进行镜头切分，涵盖三种检测算法选型、阈值调优流程、分内容类型预设与后处理规则，适用于解说视频、口播、动画、屏幕录制等素材的自动分场。
metadata:
  license: AGPL-3.0
---

# 场景检测使用指南

本技能说明如何在 OpenMontage 中用 `scene_detect` 工具自动识别镜头边界，为剪辑阶段提供分场依据。

## 速查卡

| 项目 | 取值 |
|------|------|
| 默认方法 | `content`（ContentDetector），适配多数内容 |
| 默认阈值 | 27.0（取值范围 0–255） |
| 最短场景 | 默认 1.0s，教学视频建议 2.0–3.0s |
| 调优方式 | 先导出统计 CSV，查看 content_val 列 |
| 硬切 | 用 content 检测器 |
| 淡入淡出黑场 | 用 threshold 检测器 |
| 混合内容 | 用 adaptive 检测器 |

## 算法选型

| 方法 | 默认阈值 | 适用场景 | 原理 |
|------|----------|----------|------|
| `content` | 27.0 | 镜头之间的硬切 | 比较相邻帧的 HSV 色彩差异（0–255） |
| `threshold` | 12.0 | 淡入/淡出黑场 | 基于平均像素亮度，检测经过黑场的转场 |
| `adaptive` | 3.0 | 含相机运动的混合内容 | 对帧差取滑动平均，随局部节奏自适应 |

## 阈值调优指南

### ContentDetector（默认，先从这里开始）

| 现象 | 处理 | 新阈值 |
|------|------|--------|
| 误切过多 | 提高阈值 | 35–45 |
| 漏掉真实切点 | 降低阈值 | 20–22 |
| 快节奏内容（MV、动作） | 提高 | 35–40 |
| 慢速/静态内容（口播、演示） | 降低 | 20–25 |
| 动画内容（Manim、动效） | 提高 | 30–35 |

### AdaptiveDetector

- 对滑动平均值施加倍数（默认 3.0）。
- 当快速相机运动导致误报时，表现优于 ContentDetector。
- 适合 OpenMontage 解说视频：Manim 片段静止，实拍片段有运动。

### ThresholdDetector

- 仅用于确有淡入淡出黑场转场的视频。
- 大多数 AI 生成视频不使用淡场，优先选 `content` 或 `adaptive`。

## 调优工作流

1. 先生成统计文件：

```bash
scenedetect -i video.mp4 --stats stats.csv detect-content
```

该命令对输入视频运行内容检测并将逐帧统计写入 CSV。

2. 检查 `stats.csv` 中的 `content_val` 列，峰值位置即场景变化点。

3. 将阈值设在最小真实峰值之下。

4. 设置 `min_scene_length` 抑制碎片场景：
   - 教学视频：最短 2.0–3.0s
   - 快节奏内容：0.5–1.0s
   - 默认：1.0s

### 分量权重（进阶）

ContentDetector 得分是 HSV 与边缘差异的加权和：

```
weights = (delta_hue, delta_sat, delta_lum, delta_edges)
默认值: (1.0, 1.0, 1.0, 0.0)
```

对于色彩变化多但真实切点少的动画内容：

```
weights=(1.0, 0.5, 1.0, 0.2), threshold=32
```

## 检测后处理

拿到场景列表后需做清理：

1. 合并过短片段：任何短于 `min_scene_length` 的场景并入相邻场景。
2. 校验边界：确认场景边界与解说停顿对齐（解说类视频）。
3. 标注场景：将检测结果映射到脚本段落，供剪辑阶段使用。

## 分内容类型预设

| 内容类型 | 方法 | 阈值 | 最短场景 |
|----------|------|------|----------|
| 单机位口播 | content | 22 | 3.0s |
| 多机位口播 | content | 27 | 1.0s |
| 屏幕录制 | content | 30 | 2.0s |
| 动画解说 | adaptive | 3.0 | 2.0s |
| 快节奏混剪 | content | 40 | 0.5s |
| 含淡场的纪录片 | threshold | 12 | 2.0s |

## 在 OpenMontage 中落地

使用 `scene_detect` 工具时：

1. 先用 `content` 方法、阈值 27，多数内容可直接适用。
2. 口播流水线：阈值降到 22，`min_scene_length` 设为 3.0s。
3. 动画解说流水线：使用 `adaptive`，沿用默认阈值 3.0。
4. 调参前务必先导出统计 CSV，不要凭感觉猜阈值。
5. 教学类内容把 `min_scene_length` 设为 2.0s，避免碎片场景。
6. 用检测出的场景为剪辑阶段提供依据，把场景映射到脚本段落。
7. AI 生成视频片段用 `content` 而非 `threshold`，这类素材极少出现黑场淡变。
