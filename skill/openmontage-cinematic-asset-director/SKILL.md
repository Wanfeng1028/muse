---
name: openmontage-cinematic-asset-director
version: "1.0.0"
description: 为电影感剪辑准备可用素材，包括源片段选段、标题卡、可选补充素材、音乐、氛围音与字幕资源；适用于预告片、品牌片、蒙太奇等电影感项目的素材统筹阶段。
metadata:
  license: AGPL-3.0
---

# 电影感流程 · 素材总监

## 何时启用

本阶段为最终电影感剪辑准备所有可用媒体：源片段选段、标题卡素材、可选的补充插入镜头、音乐、氛围音，以及在有对白或旁白时需要的字幕资源。

## 标题与叠加层的动画创作

在创作标题卡、名牌条或 SVG 叠加层之前，先阅读 `skills/meta/animation-runtime-selector.md` 确定运行时路由。电影感作品通常依赖以下几种高质感运动模式：

| 电影感需求 | 推荐方案 |
|---|---|
| 主角标题的细微揭示 | Remotion `HeroTitle` 组件（已有） |
| SVG 上的 Logo 构建 / 电影感 sting | GSAP DrawSVG + MotionPath，参见 `.agents/skills/gsap-plugins/SKILL.md` |
| 在宽幅静帧或叠加层上的曲线运镜 | GSAP MotionPath，参见 `.agents/skills/gsap-plugins/SKILL.md` |
| 逐字标题揭示（颁奖/预告片风格） | GSAP SplitText，参见 `.agents/skills/gsap-plugins/SKILL.md` |
| 电影感缓动（Unreal 风格、抖动、加权） | GSAP CustomEase / EasePack，参见 `.agents/skills/gsap-plugins/SKILL.md` |
| 弹性落位的名牌下三分之一条 | Remotion `spring()` 通常足够；需要抖动时用 GSAP CustomEase |
| 胶片颗粒 / 粒子叠加 | Remotion `ParticleOverlay`（已有） |
| 调色 / LUT | `tools/enhancement/color_grade.py`（不属于动画范畴） |

**电影感是 GSAP 最能体现价值的领域**——该类型奖励精心设计的缓动和精确的曲线运动，这是原始 `interpolate()` 难以干净表达的。但也不要过度使用：对于简单的淡入标题，Remotion `spring()` 仍然优于引入整个 GSAP 依赖。

## 前置条件

| 层级 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 场景意图与节拍计划 |
| 工具 | `subtitle_gen`、`audio_enhance`、`image_selector`、`video_selector`、`pixabay_music`（免费，默认）、`freesound_music`（免费）、`music_gen`（ElevenLabs，付费）——选择器会自动从注册表发现所有可用提供商。**优先使用 `pixabay_music`，再考虑 `music_gen`。** | 可选补充素材创建 |
| Playbook | 当前风格 playbook | 品牌与排版一致性 |

## 流程

### 显式 3D 世界路径

当已批准的交付承诺是一个连续的自由视角 3D 世界时，`threejs_world` 能满足语义规划和浏览器原生运动：它创建真实的场景图和时间驱动的摄像机，而非静帧回退。阅读 `skills/creative/3d-world-generation.md` 和 `.agents/skills/threejs-world-generation/SKILL.md`，构建到 `projects/<id>/hyperframes/`，并在素材门禁前审查全局、区域、行走、语义和线框视图。保持 `render_runtime="hyperframes"` 和 `composition_mode="atelier"` 锁定，以交付浏览器原生作品。对于参考级视频，锁定 Blender 作为 3D 渲染器，`render_runtime="ffmpeg"` 仅作为图像序列/音频打包器。

对于主角/参考驱动的项目，`quality_tier="production"` 是强制要求。用 `threejs_asset_catalog` 安装授权目录，在有用时用 Atlas/fal 生成独特网格，在 Blender 中组装和渲染，如果仍存在主导图元、平坦无纹理地面、区域物体密度低或明显重复，则拒绝素材门禁。`blockout` 仅用于布局/摄像机审批。

### 1. 优先处理源片段选段

从以下开始：

- 源素材选段，
- 静帧，
- 标题卡背景，
- 任何已批准的提供音乐或氛围底。

这些是主要材料。其他一切都是补充。

如果 `proposal_packet.metadata.motion_required = true`，实际运动素材或生成的视频片段是强制性的。在这种情况下：

- 静帧只能作为参考材料或更大运动构图中的背景元素，
- 静帧不能替代计划的运动镜头，
- 静帧图像预告片不是可接受的回退方案，除非用户明确批准动画分镜。

### 1b. 样本预览（防止浪费开销）

在批量生成补充素材之前，为每种昂贵的生成类型制作一个样本并展示给用户：

1. **生成插入样本**（如果使用 `image_selector` 或 `video_selector`）：生成一个代表性视觉。确认它能补充源素材后再批量生成。
2. **音乐样本**（先尝试 `pixabay_music`——免费，可按情绪/BPM 搜索；回退到 `freesound_music` 获取提示音和氛围音；只有当搜索工具无法满足需求时才使用 `music_gen`）：采样或获取一个短片段。确认情绪和能量与节拍计划匹配。

如果 `motion_required = true`，代表性视觉必须是视频片段样本，而非静帧样本。

如果被拒绝，调整参数并重试（最多 3 次迭代）。未经批准不得批量生成。

在生成样本之前，准确告知用户将使用哪条生成路径：

- 工具，
- 提供商，
- 模型或变体，
- 生成模式，
- 选择原因。

如果该路径失败，停止并询问后再尝试不同的提供商、模型或生成模式。

### 2. 仅在需要处生成补充素材

可选生成素材应填补明确缺口：

- 缺失的过渡 B-roll，
- 概念驱动的插入镜头，
- 纹理或氛围卡片，
- 简单的纹理运动背景。

对于需要运动的项目，优先使用 `video_selector` 生成镜头。`image_selector` 可以支持外观开发、概念帧或嵌入式设计层，但它本身不满足运动要求。

### 3. 准备真实的音频方案

存储：

- 选定的音乐轨道或提示词，
- 氛围音层，
- 冲击音或过渡音，
- 如果有对白或旁白，则包含字幕资源。

### 4. 使用元数据记录版权与意图

推荐元数据键：

- `source_selects`
- `music_plan`
- `ambience_plan`
- `title_assets`
- `generated_support_assets`
- `rights_notes`

### 生成提示词的前/后自审

> 在向任何图像或视频生成工具发送提示词之前，执行基于 CHAI 监督循环的三步自审（"Building a Precise Video Language with Human-AI Oversight", arXiv 2604.21718v2）。成本很小（无额外工具调用）；收益很大（避免浪费的生成）。对于电影感项目，这最重要的是 **主角帧提示词**——一个糟糕的主角帧会毁掉整个作品，而主角帧是重新生成成本最高的镜头。
>
> **步骤 1——预描述。** 按当前方式编写提示词。不要过度编辑；目标是完整的初稿。
>
> **步骤 2——批评。** 对照 5 个方面（主体/主体运动/场景/空间取景/摄像机）为草稿打分。对每个方面：
> - 是否已指定？如果没有，遗漏是故意的（例如"无主体——风景镜头"）还是意外的？
> - 易混淆术语是否已消歧？（dolly vs zoom、pan vs truck、鸟瞰 vs 航拍、鱼眼 vs 桶形、全景 vs 特写）
> - 情感形容词（"史诗"、"忧郁"、"电影感"）是否已替换为其视觉成因（低调照明、缓慢推入、变形镜头光晕、深阴影）？
> - 对于多镜头提示词和身份锚定的主角帧：身份是否在镜头间逐字锚定？
>
> **步骤 3——后描述。** 重写，填补缺失的方面，修正易混淆术语，替换主观语言。后描述是发送给生成工具的内容。
>
> 将（预描述、批评、后描述）三元组记录在素材元数据中以供追溯。这呼应 CHAI 工作流，并创建审查者可审计的记录。

### 5. 质量门禁

- 源素材和补充素材有明确区分，
- 生成插入镜头有限且有目的，
- 音频方案与节拍图匹配，
- 每个引用的文件都存在。
- 如果需要运动，素材集中包含运动主导节拍的实际视频片段。

### 制作中的事实核查

如果在素材生成过程中遇到不确定性：
- 使用 `web_search` 验证主体的视觉准确性（例如这栋建筑实际长什么样？）
- 在生成插图前使用 `web_search` 查找参考图像
- 在决策日志中记录验证：`category="visual_accuracy_check"`

视觉准确性很重要。如果脚本提到特定地点、人物或物体，在生成图像前验证其实际外观。不要依赖 AI 模型的训练数据——它可能错误或过时。

## 常见陷阱

- 在证明源剪辑可行之前就生成额外镜头。
- 将音乐视为单一循环而非节拍感知元素。
- 忘记提供素材的版权或来源说明。
- 因为某个提供商或渲染器失败而悄悄从视频片段降级为静帧。
- 在用户批准生成路径后悄悄切换提供商或模型。

## 当你不知道怎么做时

如果遇到不确定的生成技术、提供商行为或提示模式：

1. **搜索网络** 获取当前最佳实践——模型和 API 变化频繁，代理的训练数据可能过时
2. **检查 `.agents/skills/`** 中的现有 Layer 3 知识（提供商特定提示指南、API 模式）
3. **如果两者都无帮助**，在 `projects/<project-name>/skills/<name>.md` 编写项目范围的 skill 记录你学到的东西
4. **引用源 URL** 在 skill 中，使知识可追溯
5. **记录** 在决策日志中：`category: "capability_extension"`、`subject: "learned technique: <name>"`

这尤其重要于：
- **视频生成提示**——模型响应随版本变化的特定词汇
- **图像模型参数**——FLUX、GPT Image、Imagen 的最佳设置各不相同且不断演进
- **音频提供商特性**——语音克隆、音乐生成和 TTS 各有模型特定的最佳实践
- **Remotion 组件模式**——随着框架演进出现新的合成技术

不要依赖过时知识。有疑问时，先搜索。

---

## 门禁提醒（约束性）

本阶段以人工批准为门禁（`human_approval_default: true`）。审查通过后：以 `status="awaiting_human"` 设置检查点，呈现摘要（Backlot 面板会渲染产物），并**结束你的回合**。不要在同一响应中启动下一阶段。批准是按门禁的——早先的"继续"不覆盖此门禁。
