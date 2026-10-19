---
name: openmontage-animation-runtime-selector
version: "1.0.0"
description: 根据视频需求选择合成运行时（Remotion、HyperFrames 或 FFmpeg）及对应动画库，并路由至正确的 Layer 3 技能。适用于提案阶段锁定 render_runtime、编写动画组件或不确定该用 GSAP 插件还是内建原语的场景。
metadata:
  license: AGPL-3.0
---

# 动画运行时选择器

本技能回答两个核心问题：

1. 这段视频应该用哪个合成运行时？—— Remotion、HyperFrames 还是 FFmpeg。
2. 这个场景应该调用哪些动画库 / Layer 3 技能？—— Remotion 原语、GSAP 插件、framer-motion、Lottie、Manim、D3。

在编写任何动画组件或合成之前、以及在提案阶段选择 `render_runtime` 时，先读本技能。它会把你路由到正确的 Layer 3 技能，避免手动重复造轮子。

> **创作模式优先于运行时选择。** 在决定运行时或库之前，先确定合成是**模板化**（拼装现成 `cut.type` 场景）还是**工坊模式**（从零手写）。主角作品默认走工坊模式，遵循 `skills/meta/bespoke-composition.md`。下面的路由在两种模式下都适用——但工坊模式下现成场景类型和注册表块不可用，必须自己写。“有没有现成的 cut-type 能用？”对主角作品来说不是有效的捷径。参见 `AGENT_GUIDE.md` → "Composition Authoring Mode"。

## 何时使用本技能

适用场景：
- **提案阶段**需要锁定 `render_runtime`（remotion / hyperframes / ffmpeg）
- 阶段导演（asset、edit、compose）需要编写动画组件
- Agent 即将为涉及文字揭示、SVG 运动、曲线相机路径、形状变形或多阶段编排的场景编写 Remotion JSX
- Agent 需要构建 HyperFrames 合成
- Agent 不确定该用 GSAP 插件还是内联 `interpolate()`/`spring()`

## 运行时选择（Remotion vs HyperFrames vs FFmpeg）

OpenMontage 将创作语法（`renderer_family`）与技术引擎（`render_runtime`）分离。两者都在提案阶段锁定，并通过 `edit_decisions` 原样传递。在 compose 阶段静默更换运行时属于合约违规。

### 硬性规则——两个运行时都要展示，不得静默默认

当机器上同时有 Remotion 和 HyperFrames 可用时（检查 `video_compose.get_info()["render_engines"]`），Agent 必须在锁定 `render_runtime` 之前向用户展示两个选项。下面的决策矩阵是 Agent 用于对话的输入，而不是静默选择“默认”项的许可。完整合约参见 `AGENT_GUIDE.md` → "Present Both Composition Runtimes"。

具体来说，在提案阶段：

1. 查询 `video_compose.get_info()["render_engines"]` 确定本机可用的运行时。
2. 如果 Remotion 和 HyperFrames 都可用，向用户展示两者：针对需求的一句话描述、一句诚实的取舍说明、Agent 的推荐及理由。
3. 等待用户明确批准。
4. 在 `decision_log` 中记录决策，category 为 `render_runtime_selection`，`options_considered` 中包含两个运行时。
5. 然后才将 `render_runtime` 写入 `proposal_packet.production_plan`。

如果两个运行时都可用但 `render_runtime_selection` 决策只考虑了一个选项，这是 CRITICAL 级审查发现。

| 需求特征 | `render_runtime` | 参考文档 |
|---|---|---|
| 已有 React 场景栈（text_card、stat_card、chart、caption overlay、TalkingHead、CinematicRenderer） | **remotion** | `skills/core/remotion.md` |
| 逐词字幕烧录 / 卡拉 OK 字幕 | **remotion** | `skills/core/remotion.md` |
| 虚拟形象 / 唇形同步 / 主持人 | **remotion** | `skills/core/remotion.md` |
| 动态排版、HTML/GSAP 原生动效、产品宣传、发布会片 | **hyperframes** | `skills/core/hyperframes.md` + `.agents/skills/hyperframes/SKILL.md`（路由）→ `hyperframes-core`（合约）、`hyperframes-creative`（调色/字体）、`hyperframes-animation`（运动） |
| 网站转视频、UI 驱动合成 | **hyperframes** | `.agents/skills/website-to-video/SKILL.md`（0.7 起从 website-to-hyperframes 更名） |
| 需要注册表块（data-chart、grain-overlay、shader 转场等） | **hyperframes** | `.agents/skills/hyperframes-registry/SKILL.md` |
| 可编辑的浏览器原生 3D 地形/世界与自由视点飞行 | **hyperframes** | `skills/creative/3d-world-generation.md` + `.agents/skills/threejs-world-generation/SKILL.md` |
| Blender 渲染的参考级 3D 世界影片 | **ffmpeg 打包 Blender 帧** | `skills/creative/3d-world-generation.md` + `.agents/skills/3d-asset-generation/SKILL.md` |
| 节拍同步音乐视频（音频驱动场景时间） | **hyperframes** | `.agents/skills/music-to-video/SKILL.md` — 用 `hyperframes beats` 检测 drop，按节拍网格排布帧 |
| 将已有 Remotion 合成移植到 HyperFrames | **hyperframes** | `.agents/skills/remotion-to-hyperframes/SKILL.md` — 迁移指南，仅用于明确的移植请求 |
| BGM / SFX / 图片 / 图标解析（任意管线、任意运行时） | 不适用 | `.agents/skills/media-use/SKILL.md` — `resolve` 动词，对项目缓存 + 全局缓存 + HeyGen 目录操作 |
| 短设计驱动动效图形（下三分之一、数据揭示、logo sting、标题） | **hyperframes** | `.agents/skills/motion-graphics/SKILL.md` |
| 纯拼接/裁剪源片段，无需合成 | **ffmpeg** | `skills/core/ffmpeg.md` |
| 所选运行时不可用 | **升级处理** — 不得静默替代 | `AGENT_GUIDE.md` → Escalate Blockers |

完整的 Remotion-vs-HyperFrames 决策矩阵和 Phase 1 中仅 Remotion 支持的功能列表，参见 `skills/core/hyperframes.md`。

## 动画库决策矩阵

| 动画需求 | 推荐运行时 | 先读 |
|---|---|---|
| 简单淡入/滑动/缩放/弹簧 | Remotion 原语（无插件） | `.agents/skills/remotion` |
| 双态物理弹簧 | Remotion `spring()` | `.agents/skills/remotion` |
| 多步序列带偏移 | Remotion `Sequence` + `interpolate()` **或** GSAP timeline | `.agents/skills/remotion` + 可选 `.agents/skills/gsap-timeline` |
| 逐词文字揭示与旁白同步 | Remotion `interpolate` 由词级转写驱动（现有 `CaptionOverlay` 模式） | `.agents/skills/remotion` |
| 逐字符动态排版（SplitText 风格） | Remotion 内使用 GSAP SplitText | `.agents/skills/gsap-plugins`（SplitText）、`.agents/skills/gsap-react` |
| SVG 两路径间形状变形 | Remotion 内使用 GSAP MorphSVG | `.agents/skills/gsap-plugins`（MorphSVG） |
| 沿自定义路径的曲线相机/物体运动 | Remotion 内使用 GSAP MotionPath | `.agents/skills/gsap-plugins`（MotionPath） |
| SVG 线条绘制/描边揭示 | GSAP DrawSVG | `.agents/skills/gsap-plugins`（DrawSVG） |
| 定制贝塞尔/弹性/抖动缓动 | GSAP CustomEase / EasePack / CustomWiggle | `.agents/skills/gsap-plugins` |
| 布局到布局过渡（FLIP） | Remotion 内使用 GSAP Flip | `.agents/skills/gsap-plugins`（Flip） |
| 迪士尼 12 动画原则用于 UI 运动 | framer-motion + Lottie | `.agents/skills/framer-motion`、`.agents/skills/lottie-bodymovin` |
| 从 After Effects / Figma 导出 Lottie | Lottie | `.agents/skills/lottie-bodymovin` |
| 合成终端 / CLI 演示 | Remotion TerminalScene | `.agents/skills/synthetic-screen-recording` |
| 数学/科学可视化 | Manim | `.agents/skills/manim-composer`、`.agents/skills/manimce-best-practices` |
| D3 数据驱动可视化 | D3 | `.agents/skills/d3-viz` |
| 数据图表（柱/线/饼/KPI） | Remotion 内建图表组件 | `remotion-composer/SCENE_TYPES.md` |
| HyperFrames 合成 — 动画知识（规则、蓝图、转场、运行时适配器） | HyperFrames + GSAP 默认 | `.agents/skills/hyperframes-animation` + `.agents/skills/gsap-core`、`.agents/skills/gsap-timeline` |
| HyperFrames 合成结构（data-* 计时、轨道、子合成） | HyperFrames | `.agents/skills/hyperframes-core` |
| 显式 Three.js 世界（地形、区域、地标、相机路径） | HyperFrames + `threejs_world` | `.agents/skills/threejs-world-generation` |
| 精细 Blender 世界影片（生成/目录网格、PBR、相机路径） | Blender + FFmpeg 打包 | `.agents/skills/3d-asset-generation` |
| HyperFrames 创意方向（调色、字体、旁白、节拍规划） | HyperFrames | `.agents/skills/hyperframes-creative` |
| HyperFrames 音频/媒体（TTS、BGM、SFX、转写、字幕、去背景） | HyperFrames | `.agents/skills/hyperframes-media` |
| HyperFrames 合成 CLI 工作（lint/validate/inspect/snapshot/benchmark/render/lambda） | HyperFrames CLI 0.7+ | `.agents/skills/hyperframes-cli` |
| HyperFrames 注册表块安装（`hyperframes add ...`） | HyperFrames 注册表 | `.agents/skills/hyperframes-registry` |

## “保持简单”原则

在动用 GSAP 之前先问：**Remotion 的原语 API 能否在 20 行以内解决？**

- 淡入/滑动/缩放/旋转 → `interpolate(frame, [inFrame, outFrame], [from, to])`
- 自然的弹跳感 → `spring({ frame, fps, config: { damping, stiffness } })`
- 逐词字幕高亮 → 遍历转写，按 `frame / fps` 过滤

如果是，用 Remotion 原语。如果否，那才是升级到 GSAP 插件的信号。

GSAP 是强大的逃生舱，不是默认选项。每个插件都会增加打包体积、注册样板和一份需要阅读的技能文档。

## 在 Remotion 中确定性地运行 GSAP

标准 GSAP 基于 `requestAnimationFrame`——不确定，开箱即不兼容 Remotion。以下三种模式是 Remotion 安全的：

```jsx
// 模式 1：暂停的 timeline，按进度 seek
const tl = useRef(gsap.timeline({ paused: true })).current;
useEffect(() => {
  tl.to('.x', { x: 500 }).to('.y', { opacity: 0 });
}, []);
tl.progress(frame / durationInFrames);

// 模式 2：暂停的 timeline，按时间 seek
tl.seek(frame / fps);

// 模式 3：GSAP 仅作为值计算器
const easeFn = gsap.parseEase('power2.out');
const t = frame / durationInFrames;
const easedValue = easeFn(t);
```

完整分析参见 `.agents/skills/gsap-react/SKILL.md`。

## 对照管线的阶段导演检查

每条管线的 asset-director 都有动画相关的指导。如果你在：

- **animated-explainer** → 读 `skills/pipelines/explainer/asset-director.md`——它引用了动态排版的文字/SVG 选项
- **animation** → 读 `skills/pipelines/animation/asset-director.md`——它引用了 MorphSVG 和 MotionPath 用于 logo/动效图形
- **cinematic** → 读 `skills/pipelines/cinematic/asset-director.md`——它引用了 MotionPath 用于电影感相机运动

asset-director 告诉你在该管线上下文中*建什么*。本选择器告诉你*怎么建*。

## 禁止事项

- ❌ 只需淡入/滑动的场景引入 GSAP——用 Remotion 原语。
- ❌ 在 Remotion 内用 `requestAnimationFrame` 运行 GSAP——渲染将不确定。
- ❌ 插件被指示使用时跳过对应的 Layer 3 技能——每个插件的提示指导很重要。
- ❌ 在组件体内注册 GSAP 插件——在模块作用域或应用入口处注册一次。
