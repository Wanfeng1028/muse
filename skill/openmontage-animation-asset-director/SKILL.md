---
name: openmontage-animation-asset-director
version: "1.0.0"
description: 动画管线的素材制作阶段，负责生成旁白、图表、数学渲染、动态背景、代码可视化以及可复用的字体与版式系统。适用于需要在批量生成前确定视觉系统、控制预算并保证风格一致性的动画项目。
metadata:
  license: AGPL-3.0
---

# 素材导演 — 动画管线

## 适用场景

本阶段产出动画所需的实际素材：旁白配音、结构化图表、数学动画、运动背景、代码画面，以及可反复使用的字体与版式体系。它位于场景规划之后、剪辑之前，是整条管线中花钱最集中的环节。

## 动画运行时选择

在动手写任何动效组件之前，先查阅 `skills/meta/animation-runtime-selector.md` 决定运行时。动画管线是最有可能需要 GSAP 插件的场景——标志变形、曲线路径运镜、动态文字、FLIP 布局过渡都属于这一类。

常见需求与推荐方案对照：

| 动效类型 | 推荐做法 |
|---|---|
| 两个 SVG 标志之间的形变 | GSAP MorphSVG，读 `.agents/skills/gsap-plugins/SKILL.md` |
| SVG 线条描边揭示 | GSAP DrawSVG，读同一插件文档 |
| 物体沿曲线路径移动 | GSAP MotionPath |
| 逐字或逐词的标题揭示 | GSAP SplitText |
| 自定义贝塞尔或弹性缓动 | GSAP CustomEase |
| 布局到布局的元素飞入（FLIP） | GSAP Flip |
| 多元素多步骤编排 | GSAP timeline，读 `.agents/skills/gsap-timeline/SKILL.md` |
| 粒子叠加或背景运动 | Remotion 现成的 `ParticleOverlay` 组件 |
| 数学动画（函数图像、公式） | Manim，读 `.agents/skills/manim-composer` 与 `manimce-best-practices` |
| 吉卜力／日式动画风格的静帧场景 | Remotion 的 `AnimeScene` 组件配合 FLUX 出图 |

**Remotion 确定性铁律：** 任何在 Remotion 组件内使用的 GSAP，都必须由 `useCurrentFrame()` 驱动时间轴进度，绝不能用 `requestAnimationFrame`。写法范例见 `.agents/skills/gsap-react/SKILL.md`。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 产物校验 |
| 上游产物 | `scene_plan`、`script`、`proposal_packet` | 工具路径与节拍图 |
| 工具 | `tts_selector`、`image_selector`、`video_selector`、`math_animate`、`diagram_gen`、`code_snippet`、`threejs_world`、`music_gen`、`fal_elevenlabs_music` | 选择器会自动从注册表发现所有可用供应商 |
| 风格手册 | 当前激活的 playbook | 视觉一致性约束 |

## 流程

### 1. 先做确定性素材

优先选择方差最低的可行路径：

- 结构化图表用 `diagram_gen`，不要直接交给通用出图；
- 代码画面用 `code_snippet`；
- 真实数学运动用 `math_animate`；
- 已有素材优先于新生成素材。

若需要真正的三维环境，先读 `skills/creative/3d-world-generation.md` 以及该工具的 `threejs-world-generation` 三层技能，再使用 `threejs_world`，且要排在图像或视频生成之前。构建电影感的可编辑工作区，同时跑一遍语义或线框诊断。把可编辑工作区注册为 `type: "3d_world"`；快照放进素材评审，最终 MP4 交给合成阶段。

### 1b. 样本预览（避免浪费预算）

批量生成前，先对每一类昂贵素材各出一个样本给用户看：

1. **TTS 样本**（旁白驱动型项目）：如果 `script.voice_performance.sample_section_id` 存在就生成该段；否则挑选情绪或节奏变化最明显的段落。确认音色、语速、停顿、重音与语气之后才能批量。
2. **视觉样本**：先出一张有代表性的场景画面（图表、插画或动态背景）。确认风格与质量后再批量。

若被否决，调整参数重试，最多 3 轮。未通过前不许批量。

### 1c. 图像驱动动画的多图生成（方案 A）

当 `animation_mode == "image_animation"` 时，每个场景需要 **2 到 3 张图**来做交叉淡入淡出——正是这一点让静帧看起来像在动。

**出图工作流：**

1. **定义视觉系统**——一组在整个项目里复用的锚点。它保证视觉连贯，又不会把每个镜头压成同一个提示词。把它存成可复用元数据。
   ```
   示例："手绘自然奇幻，苔绿与琥珀暖色调，
   柔和漫射光，笔触感植被纹理，温柔的惊奇感。"
   ```
   然后按场景做局部适配：
   - 场景 1：远景建立镜头，森林山谷，薄雾，日出
   - 场景 2：近景角色节拍，灯笼光晕，飘浮孢子
   - 场景 3：抽象魔法能量揭示，更亮的强调色对比

2. **做种子管理**——同一场景的 A/B 变体使用相邻的种子值（例如 100 与 101）。相同提示词加不同种子等于相同构图加细微差异，正好形成自然的交叉淡变运动。

3. **先出一张测试图**——只渲染一个场景，确认视觉系统在 1920×1080 下效果合格，再开始全量生成。

4. **批量生成**——生成全部场景图。磁盘上已存在的文件直接跳过，保证幂等。

5. **合成 JSON**——每个场景写成 `type: "anime_scene"`，带 `images: ["path/a.png", "path/b.png"]`，外加镜头运动、粒子类型与光照配置。

**成本估算：** 每场景 2 到 3 张图，按供应商不同约 $0.03–$0.13 一张。

**参考：** 批量生成的成熟写法见 `projects/mori-no-seishin/generate_images.py`。

6. **拷贝到 Remotion 公共目录**——图片生成完后必须复制到 `remotion-composer/public/<项目名>/`，Remotion 才能通过 `staticFile()` 访问。合成 JSON 里的图片路径都相对于这个目录：
   ```
   remotion-composer/public/<项目名>/scene1-a.png   ← Remotion 从这里读
   remotion-composer/public/<项目名>/ambient-music.mp3  ← 音乐同理
   ```
   **跳过这一步，渲染就会因找不到文件而失败。** 这是新项目渲染失败的第一大原因。

### 2. 搭建可复用体系

只做一次的东西：

- 字体处理方案；
- 下三分之一条或标签样式；
- 反复出现的母题素材；
- 背景容器。

### 3. 旁白可选，但必须明确声明

若项目是旁白驱动，就产出或获取旁白。先读 `skills/meta/voice-performance-director.md`，再按 `script.voice_performance` 和各段落的 `delivery_cues` 构造 TTS 请求。存在 `provider_text` 时优先使用，把提示线索映射到供应商的控制参数，并把实际应用的设置记录在每个旁白素材上。若是文字驱动或音乐驱动，在元数据里写清楚。

### 4. 用元数据记录可行性真相

推荐元数据键：

- `tool_path_map`
- `reusable_assets`
- `narration_assets`
- `voice_performance`：样本审批路径、供应商设置、是否应用了表演提示
- `scene_asset_index`
- `blocked_assets`

### 5. 质量门

- 每个场景的素材路径明确；
- 可复用素材确实被复用；
- 缺失的能力如实上报；
- 每一个被引用的文件都真实存在；
- 旁白驱动型素材应用了已批准的语音表演设置。

## 制作中的事实核查

素材生成过程中遇到不确定时：

- 用 `web_search` 核实被拍摄对象的真实外观（例如这栋建筑实际长什么样）；
- 生成插画前先用 `web_search` 找参考图；
- 在决策日志中记录：`category="visual_accuracy_check"`。

视觉准确性很重要。脚本提到具体地点、人物或物件时，先核实其真实样貌再出图。不要依赖模型训练数据——它可能错误或过时。

## 常见坑

- 明明确定性素材更合适，却用了高方差生成。
- 反复重建同一套标题或标签系统。
- 把失败的素材路径藏起来而不上报。
- 把 TTS 当成纯粹的文字转语音。旁白驱动型动画需要把脚本里的停顿、重音和节奏线索带入生成的音频。
- 把"一致性"理解成"每次都用同一个提示词"。好的动画在保持可辨识世界的同时，让每个节拍仍然新鲜。

## 不会做的时候怎么办

遇到不确定的生成技术、供应商行为或提示词模式：

1. **上网搜**当前最佳实践——模型和 API 变化很快，训练数据可能已过时；
2. **查 `.agents/skills/`** 里已有的三层知识（供应商提示词指南、API 模式）；
3. **两者都帮不上**，就在 `projects/<项目名>/skills/<名称>.md` 写一份项目级技能，把学到的东西记下来；
4. **在技能里标注来源 URL**，让知识可追溯；
5. **写进决策日志**：`category: "capability_extension"`，`subject: "learned technique: <名称>"`。

以下情况尤其重要：

- **视频生成提示词**——模型对词汇的反应随版本变化；
- **图像模型参数**——FLUX、GPT Image、Imagen 的最优设置各不相同且在演进；
- **音频供应商怪癖**——声音克隆、音乐生成、TTS 各有模型专属的最佳实践；
- **Remotion 组件模式**——框架演进会带来新的合成技巧。

不要依赖过时知识。拿不准就先搜。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，展示摘要（Backlot 面板会渲染产物），然后**结束本轮对话**。不要在同一次回复里启动下一阶段。审批是逐门生效的——之前说过的一句"继续"不覆盖本门。
