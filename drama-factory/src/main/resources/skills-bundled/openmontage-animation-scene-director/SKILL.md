---
name: openmontage-animation-scene-director
version: "1.0.0"
description: 动画分镜导演技能，将剧本转化为可执行的动画分镜计划，适用于需要统一镜头语言、转场体系与工具路径的动画制作场景。
metadata:
  license: AGPL-3.0
---

# 动画分镜导演

## 何时使用

本阶段负责把剧本转成一份可落地的动画计划。项目最终是"设计感强"还是"杂乱无章"，几乎全看这一步。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | 校验产出物 |
| 前置产出 | `state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 提供节拍图与工具路径 |
| Playbook | 当前启用的风格 playbook | 统一调色板、字体与运动风格 |

## 流程

### 1. 以"动态分镜（animatic）"思路规划

为每个场景明确四件事：

- 最先出现的是什么；
- 中间发生什么变化；
- 哪些画面被保持（hold）；
- 场景如何退出。

### 2. 限制转场家族

只挑少量有明确语义的转场：

- cut（硬切）
- fade（淡入淡出）
- slide（滑动）
- transform（变形）

### 3. 按场景类型匹配工具路径

对应关系如下：

- `diagram` 场景 → 用于结构化讲解；
- `animation` 场景 → 用于以运动为主的段落；
- `text_card` → 用于高冲击力的纯文案时刻；
- `generated` → 仅在确有必要时使用。

**若采用 `image_animation` 路径（动漫/插画风格）：**

每个场景使用 `anime_scene` 类型，并规划以下内容：

- **单场景图片数量**：2–3 张，须来自同一视觉系统、使用相近的随机种子，以便做交叉淡入淡出；
- **镜头运动**：从 `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static` 中选择，逐场景切换以免单调；
- **粒子类型**：从 `fireflies`、`petals`、`sparkles`、`mist`、`light-rays` 中挑选，与场景情绪匹配；
- **光照**：可选 `lightingFrom`/`lightingTo` 渐变，用于场景内的氛围过渡；
- **暗角**：`true` 为电影感构图（默认），`false` 用于明亮开阔的场景；
- **场景时长**：每场景 4–7 秒。场景越长，需要越多图片来支撑交叉淡入的变化。

**image_animation 的场景多样性规则：**

- 相邻场景不得使用相同的镜头运动；
- 冷/暖色粒子类型交替使用；
- 特写与广角建立镜头交替出现；
- 用叠加层（`hero_title`、`section_title`）来补充叙事结构。

**JSON 字段名映射**（合成 JSON 中必须使用以下准确字段名）：

| 概念 | JSON 字段 | 示例取值 |
|------|-----------|----------|
| 镜头运动 | `animation` | `"zoom-in"`、`"pan-right"`、`"ken-burns"` |
| 粒子效果 | `particles` | `"fireflies"`、`"sparkles"`、`"mist"` |
| 粒子颜色 | `particleColor` | `"#FFE082"` |
| 粒子密度 | `particleCount` | `20`（范围 1–50） |
| 粒子亮度 | `particleIntensity` | `0.5`（范围 0–1） |
| 光照起点 | `lightingFrom` | `"rgba(255,200,100,0.15)"` 或 `"transparent"` |
| 光照终点 | `lightingTo` | `"rgba(255,107,157,0.08)"` 或 `"transparent"` |
| 电影感边缘压暗 | `vignette` | `true` / `false` |
| 场景背景色 | `backgroundColor` | 由主题派生的值，如 `"#0A0A1A"` 或 `"#F6F1E8"` |

参考样例：`remotion-composer/public/demo-props/mori-no-seishin.json`，共 6 个场景，均按此模式编写。
参考样例：`remotion-composer/public/demo-props/deep-ocean.json`，共 6 个水下场景，配色方案不同。

### 4. 用 Metadata 记录时间规则

建议使用的 metadata 键：

- `animatic_rules`
- `transition_rules`
- `hold_rules`
- `tool_path_map`
- `reusable_motifs`

### 5. 五要素场景计划清单

> 每个场景都必须写明全部五个要素，但侧重点随场景的 `animation_mode` 变化。Manim 等图示/程序化场景最看重 **Subject** 与 **Spatial Framing**——电影意义上的 Camera 与 Subject Motion 常写 N/A 或抽象等价物。AI 视频 / `image_animation` / `anime_scene` 场景五个要素全都要写，行为上等同电影镜头。允许把某要素标为 N/A，但必须逐场景显式标注；沉默省略一律禁止。
>
> 1. **Subject（主体）**——类型 + 关键视觉属性；Manim 中是被推到前景的公式/对象/图表；`anime_scene` 中是聚焦的角色或环境。
> 2. **Subject Motion（主体运动）**——Manim 中写明 `Create`/`Transform`/`FadeIn` 的先后顺序及各自传达的含义；AI 视频中按时间顺序写明动作与交互。
> 3. **Scene（场景）**——叠加层（单列！）+ POV + 环境 + 时间 + 场景动态。Manim 中"环境"指画布背景与坐标轴样式；`anime_scene` 中指环境与光照渐变。
> 4. **Spatial Framing（空间构图）**——景别 + 画面位置 + 景深（前/中/后景）+ 相对机位高度；以及这些量如何变化。Manim 关注布局网格与元素坐标；AI 视频关注完整的电影化构图。
> 5. **Camera（镜头）**——播放速度 → 镜头畸变 → 高度 → 角度 → 对焦/景深 → 稳定性 → 运动。Manim 与纯动态图形默认写 N/A，除非用到虚拟镜头运动（`MoveCamera`、`self.frame`）。`anime_scene` 与 AI 视频必须写全。
>
> 与场景 metadata 中的 `animation_mode` 对齐：Manim 场景若把 Camera 写满属于过度指定；AI 视频场景若漏掉 Camera 属于指定不足。原语词表见 `skills/creative/video-gen-prompting.md`。

> **叠加层提示。** 叠加层（标题、字幕、HUD、水印、边框图形、下三分之一条、`hero_title`、`section_title`、`provider_chip`）不属于场景的前/中/后景深度轴。请在场景 metadata 中用 `overlays: [...]` 单列，并写明内容与位置。切勿把叠加层描述为"位于前景"——那会同时误导下游工具与重新分析成片的视频理解模型。

### 6. 质量闸门

- 每个场景都有明确的时间意图；
- 五要素清单按该场景的 `animation_mode` 满足（该写 N/A 的要显式写）；
- 叠加层一律归入 `overlays:`，绝不出现在构图描述里；
- 转场体系有限且语义明确；
- 工具路径写清楚；
- 整段序列看起来像一个被设计过的系统。

## 常见陷阱

- 每个场景都引入一种新的转场想法。
- 规划出没有现实制作路径的场景。
- 在文字密集的场景里过度动画化。

---

## 闸门提醒（强制）

本阶段默认需要人工审批（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 做 checkpoint，展示摘要（Backlot 看板会渲染产出物），然后**结束本轮**。不得在同一轮回复中启动下一阶段。审批按闸门独立生效——先前一次"可以继续"不覆盖本闸门。
