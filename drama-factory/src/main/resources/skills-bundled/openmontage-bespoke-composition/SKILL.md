---
name: openmontage-bespoke-composition
version: "1.0.0"
description: 从零手写合成而非拼装现成场景类型的工坊模式指南，涵盖艺术方向、场景独立性和引擎机制。适用于主角作品、品牌片、发布会等质量至上的单次交付物。
metadata:
  license: AGPL-3.0
---

# 定制合成（工坊模式）

本技能指导**从零手写合成**而非拼装现成场景类型。这是“每次手工缝制”的路径：主角作品的每个像素都是新写的，没有两部视频共享同一种视觉语言。

当你为某个作品选择了**工坊模式**时（参见“何时使用”）读本技能。它不提供组件——它把你路由到所需的*原则、引擎机制和工具接线*，确保你构建的东西既正确又独特。

> 统领以下一切的唯一规则：**复用引擎知识，绝不复用创意组件。** Remotion 如何解析资源是引擎知识——可以自由复用。上一部视频长什么样是创意决策——绝不复用。

## 何时使用本技能（创作模式是提案决策）

OpenMontage 分离三个正交轴，全部在提案阶段锁定：

- `renderer_family` — 创作语法
- `render_runtime` — 技术引擎（remotion / hyperframes / ffmpeg）
- **`composition_mode`** — **templated**（拼装现成 `cut.type` 场景）**vs. atelier**（手写）

**工坊模式**默认用于：营销、发布会、必须出彩的解说、品牌片、任何质量至上的单次交付物。**模板模式**用于：批量输出、本地化变体、快速草稿、低风险内部片段——可靠的一致性就够了，定制成本不划算的场景。在提案时向用户展示这个选择，并记入 `decision_log`（`category: "composition_mode"`），与展示运行时的方式相同。

### 工坊模式与两种运行时

两种运行时对“定制”的处理不同——在假设同一套法则适用之前先读这段：

- **Remotion** 提供 `cut.type` 现成场景注册表（`text_card`、`stat_card`、`bar_chart` 等），由 `Explainer`/`CinematicRenderer` 合成调度。这是模板化默认。**工坊模式是逃生舱**——`composition_mode: "atelier"` 将渲染路由到 `_render_via_atelier` 并完全绕过注册表，Agent 在 `projects/<slug>/` 下手写自己的 React 合成。
- **HyperFrames 本质就是工坊。** HF 中没有 cut-schema——每个合成都是手写的 `index.html`，带 `data-*` 计时属性和你自己写的 GSAP timeline。注册表（`hyperframes add`）是*块*注册表（颗粒覆盖、转场）——是你合成的可选输入，不是调度整个渲染的场景目录。**选择 `render_runtime: "hyperframes"` 时，作品已经是工坊风格；`composition_mode: "atelier"` 是隐含的。** 本技能的原则（艺术方向、场景独立性、无主角组件脊柱、独立性审查）同样适用。通过 `hyperframes_compose` 渲染（或对纯手写合成用 `npx hyperframes render`——参见第 5 节）。

所以：如果 `render_runtime == "remotion"` 且是主角作品，记录 `composition_mode: "atelier"` 决策。如果 `render_runtime == "hyperframes"`，工坊是默认行为，无需论证；本技能仍会在你编写合成之前引导你走同样的原则。

如果工坊模式生效（任一运行时），Remotion 现成 `cut.type` 目录、作为场景消费的 `hyperframes-registry` 成品块（而非原始输入）、fixtures 以及任何预制的创意组件都**不可用**——它们是冻结的外观，会重新引入同质化。

## 构建路径

按此顺序创作。每一步都把你路由到已有知识——不要跳过第一步。

### 1. 为*这个主题*确定艺术方向——分歧引擎

在编写任何组件之前，决定一个只适合**这个**主题的视觉语言。先读 **`skills/meta/taste-direction.md`** 并写 `taste_profile`：设计解读、`visual_variance`、`motion_intensity`、`information_density`、参考策略和反模式。然后用 **`visual-style`** Layer 3 技能（CREATE 模式）锁定：调色板、字体个性、运动特征、布局系统和本作品独有的**一个标志性装置**。视频之间的差异在这里得到保证——不是靠扣留组件，而是靠每次强制新的方向。写下来（项目中的简短 `art-direction.md`）并据此构建。

问自己：*什么视觉隐喻属于这个主题而我从没用过？* 如果答案像过去的某个作品，你还没找到方向。

### 1.5 每个场景规划为独立合成——无主角组件脊柱

最阴险的模板化会在*场景*层面溜回来：选一个醒目的视觉（蜡烛、浏览器框、评分环），然后每个场景都复用它，只是下面换文字。作品感觉定制因为主角是定制的——但每个场景机械地是同一个合成。那是品牌幻灯片，不是电影。**不要那样做。**

艺术方向中命名的标志性装置应该出现在**一个或至多两个节拍**——通常是高潮时刻——而不是每个场景的视觉脚手架。它靠稀缺赢得分量。

对计划中的每个场景，在写代码之前具体回答：

- **这个场景的主要视觉主体是什么？** 必须*不同于*前一个场景。一个角色。一张图表。一件证据。一片风景。一个排版时刻。标志性装置。一个虚空。每个场景的主要主体就是它的职责。
- **这个节拍为什么存在？** 它为故事做了什么其他节拍做不到的事？如果两个场景能合并而不丢意义，就该合并。
- **它跟前后的场景视觉上如何不同？** 不同构图（三分法 vs 居中 vs 分割）。不同尺度（亲密特写 vs 广袤视野）。不同运动寄存器（静止 vs 繁忙）。不同调色重点。不同字体处理。
- **如果从这个场景移除标志性装置，场景还成立吗？** 如果成立，标志性装置可能不属于这个场景——它是填充物。删掉。

审查者将此作为 "scene_distinctness" 检查强制执行（参见 `skills/meta/reviewer.md` → Composition Authoring Mode Review）：记录每个场景的主要主体 + 首帧清单，并明确回答“有没有两个场景共享主要视觉主体？”有 ⇒ CRITICAL ⇒ 重新规划。

推论：逐场景计划是*一等工件*，不是隐含的。在编写 `Composition.tsx` 之前写下来（在 `art-direction.md` 或同级的 `scenes.md` 中）。

### 2. 决定运动语言——原则，而非预设

使用**原则**技能，绝不用成品动画：
- **`framer-motion`** 和 **`lottie-bodymovin`** — 迪士尼 12 原则（预备、舞台、跟随、缓入缓出、弧线、节奏、夸张、吸引力）。运行时无关；在你自己的 Remotion `spring()`/`interpolate()` 代码中应用这些*原则*。
- HyperFrames 的 `references/motion-principles.md` — 缓动即情感，节奏即重量。

### 3. 仅在概念需要时使用更丰富的词汇

**在 Remotion 上** — 大多数场景是 Remotion 原语。当*创意*需要时才升级，而非默认：`gsap-*`（SplitText 动态排版、MorphSVG 形状变形、MotionPath 曲线运动、DrawSVG 线条绘制、自定义缓动）、`threejs-*`（3D）、`d3-viz`（数据驱动自定义图表——手工构建图表；**不要**使用现成的 `bar_chart`/`line_chart`）、`manim-*`（数学）、`canvas-procedural-animation`（粒子/天气）。

**在 HyperFrames 上** — 词汇在 `/hyperframes-animation`：36+ 原子运动**规则**（`kinetic-beat-slam`、`3d-text-depth-layers`、`motion-blur-streak`、`physics-press-reaction`、`multi-phase-camera`、`depth-of-field-blur` 等）、15+ 场景**蓝图**（`kinetic-type-beats`、`comparison-split`、`dataviz-countup`、`constellation-hub`、`ticker-takeover`、`device-surface-showcase` 等）、16 个**转场**族（`css-distortion`、`css-destruction`、`css-radial`、`css-light`、`css-mechanical` 等），以及一个合成下的 **7 个运行时适配器**：GSAP 默认，外加 Lottie、Three.js、Anime.js、CSS keyframes、WAAPI 和 TypeGPU（GPU 计算）。头号能力是 `adapters/html-in-canvas-patterns.md`——将实时 HTML/CSS 捕获为 GPU 纹理并通过 WebGL/Three.js 渲染，实现电影感 bloom、破碎、液体、传送门效果。每部视频用于 1–3 个主角节拍，不是每个节拍。**每个节拍组合 2–4 个不同的原子规则**，并且**全片至少使用 3 种不同缓动**——这是动画技能内建的法则，不是可选的润色。

HF 创意方向（调色/字体/旁白/节拍规划）读 `/hyperframes-creative`。HF 资产（TTS/BGM/SFX/转写/去背景）读 `/hyperframes-media` 或 `/media-use`。HF CLI 工作流（init/lint/validate/inspect/snapshot/beats/render）读 `/hyperframes-cli`。`/hyperframes` 路由技能映射全部。

### 4. 把引擎机制搞对——坑点法典

这是唯一“复用”的地方：引擎已解决的问题。这些是关于框架如何工作的事实，不是外观。

**对于 Remotion**，研读 `.agents/skills/remotion-best-practices`（19 个规则文件：计时、转场、文字动画、透明视频、字体、音频、排序、文字测量）。你也可以读 `remotion-composer/src/components/` 中的现成组件**作为机制法典——学习惯用法，绝不导入或模仿外观。**

**对于 HyperFrames**，合成合约在 `/hyperframes-core`（`data-*` 计时属性——`data-start`、`data-duration`、`data-track-index`——加上必需的 `class="clip"`、`data-composition-id`、`window.__timelines` 注册、子合成挂载）。每次改动后运行 `npx hyperframes lint && npx hyperframes validate`——它们在渲染前捕获缺失根属性、缺失 clip id、GSAP 目标未解析、重叠 tween 和对比度失败。用 `npx hyperframes snapshot . --at <times>` 在提交完整渲染前目视抽查节拍。

不知道就会踩的常见机制：
- **确定性**：不要逐帧 `Math.random()` / `Date.now()`——用 Remotion `random(seed)` 或种子化辅助函数，否则粒子/缓动会在渲染中闪烁。
- **逐场景时长**：`useVideoConfig().durationInFrames` 返回的是*合成*长度，不是你的场景长度。场景局部计时用传入的 `durationInFrames`/`Sequence` 驱动，不要用全局值。
- **资源路径**：URL 和 `staticFile()`（public/）到处可用；**`<Audio>` 拒绝 `file://`**（只有 `<OffthreadVideo>`/`<Img>` 接受绝对 `file://`）。把音频/视频放在项目级 public 目录并通过 `staticFile` 引用。镜像 `resolveAsset` 辅助函数。
- **Remotion 中的 GSAP**：用 `paused` timeline 和 `.seek(frame/fps)`——绝不用 `requestAnimationFrame`——以便帧确定性渲染。
- **字体（Remotion）**：在模块作用域调用一次 `loadFont()`（来自 `@remotion/google-fonts/<Name>`）。
- **HF data-* 合约**：每个计时元素都需要 `data-start`、`data-duration`、`data-track-index` 和 `class="clip"`——没有 `clip` 框架不会管理可见性，元素会整条时间线都在屏幕上。根 `<body>` 需要 `data-composition-id`、`data-start="0"`、`data-duration`、`data-width`、`data-height`。每个 timeline 必须是 `gsap.timeline({ paused: true })` 并注册为 `window.__timelines["<composition-id>"]`。clip 和 GSAP 目标使用稳定的 `id` 属性——`nth-of-type` 选择器在 validate 时不稳定。
- **字幕 vs 屏幕文字——选一个角色，同一内容绝不用两者。** 每部作品在编写前决定一次：字幕是在添加口语无法承载的意义（数字、名字、翻译、引文出处），还是回显旁白的无障碍字幕？如果你的场景已经显示逐字读稿的 SerifLine，就不要再输出相同文字的字幕——重复短语即使场景其余部分很漂亮也显得业余。props 中 `captions=[]`，或只对屏幕文字与所说内容不同的场景限定字幕。

### 5. 通过运行时对应的工坊路径渲染

工坊合成是**一次性且项目本地**的——绝不进入任何共享注册表。

#### Remotion 工坊路径

- 在 `projects/<slug>/` 下编写（gitignored）。渲染工具自动通过 mtime-skip 复制将你的 `.tsx`/`.ts` 源码暂存到 `remotion-composer/projects/<slug>/`，让 webpack 解析 `node_modules`——你的真源留在 `projects/` 下。
- 用 `python scripts/scaffold_atelier_project.py <slug>` 脚手架——只生成引擎管道（entry / Root / 空白 `Composition.tsx` / `art-direction.md` / props 模板 / README）。零创意内容；占位符是故意丑陋的黑屏，让渲染后审查正确地拒绝交付未创作的脚手架。
- 媒体放在 `projects/<slug>/public/` 并作为 `bespoke.public_dir` 传入。
- 通过 `video_compose` 的 `operation="render"` 渲染：

```json
edit_decisions = {
  "render_runtime": "remotion",
  "composition_mode": "atelier",
  "bespoke": {
    "entry": "projects/<slug>/index.tsx",
    "composition_id": "<id registered in that entry's Root>",
    "props_path": "<absolute path to artifacts/props.json>",
    "public_dir": "<absolute path to projects/<slug>/public/>",
    "art_direction": "<short note or path to art-direction.md — REQUIRED>",
    "scale": 0.5,          // 0.5 用于快速草稿；最终 1080p 去掉此值
    "crf": 18,             // 清晰最终
    "concurrency": 8
  }
}
```

工坊模式下不需要 `asset_manifest` 或 `cuts`——合成拥有自己的资源。工具的 `_run_atelier_checks` 在源文件从现成注册表导入（`src/components`、`src/Explainer` 等）时使渲染失败，并在缺少 `art_direction` 时警告。

#### HyperFrames 路径

- 用 `npx hyperframes init <slug>` 脚手架（在 `projects/` 下运行）。HF init 生成 `index.html`、`meta.json`、`package.json` 和每项目 `CLAUDE.md`，自动将 Agent 路由到 `/hyperframes`——下个会话就知道该加载哪些子技能。
- 手写 `index.html`。每个 clip 需要 `class="clip"` + 三个 `data-*` 计时属性 + 稳定的 `id`。当一个文件的 timeline 超过 4 个 clip 时（lint 会捕获密度），通过 `data-composition-src` 挂载子合成。
- 音乐驱动作品，在把音轨放入 `assets/` 后运行 `npx hyperframes beats .`——它输出 `beats/<audio>.json`，包含每个节拍的 `{time, strength}`，让 Agent 落在真实 drop 上（不是猜测）。
- 渲染前验证：`npx hyperframes lint . && npx hyperframes validate . && npx hyperframes snapshot . --at <times>`。Snapshot 是 HF 的原生视觉抽查（选定时间戳的 PNG 帧接触表）——像工坊的 `final_review.visual_spotcheck` 一样使用。
- **渲染**：调用 `video_compose`，`render_runtime: "hyperframes"`、`composition_mode: "atelier"` 和已创作的 `workspace_path`。它路由到 `hyperframes_compose.render_existing`，保留 `index.html` 并运行统一检查门、严格渲染和渲染后审查。仅在管线外调试运行时时才直接调用 `npx hyperframes render`。

## 防止适得其反的护栏

- **独立性审查（替代合规审查）。** 最终渲染前问：*这可能是任何其他产品的视频吗？它复用了我以前做过的外观吗？* 如果是，艺术方向失败了——回到第 1 步。这是“它匹配参考吗”的反面。
- **不得静默回退到现成。** “保持简单”适用于*机制*（10 行弹簧没问题），绝不适用于*设计*（简单 ≠ 用 `text_card`）。如果你发现自己在主角作品里加现成 `cut.type`，停下来。
- **成本诚实。** 工坊比模板化消耗更多 Agent token 和迭代。在提案时说明，让用户知情选择。没有现成基线时质量波动更大——用强原则技能（见上）和独立性审查来缓解，而不是重新引入复用。
- **检查点节奏。** 遵循 `skills/meta/checkpoint-protocol.md`：在生成资源之前提交脚本 + 场景计划审批，然后是**资源门**，再是首渲染检查点。不要在签核之前批量生成，**不要为了获得资源审查而渲染草稿**——资源门在 compose *之前*（见下）。

- **在资源门用逐场景静帧填充胶片条。** 工坊场景的“资源”是 `.tsx` 合成——无法缩略图化——所以静帧存在之前看板无法展示。合成编译后，为每个场景在代表帧渲染一张静帧到 `projects/<slug>/snapshots/<scene_id>.png`，让资源门胶片条显示真实帧而非“◆ BESPOKE”占位符。用 Remotion 静帧渲染器（快——每场景一帧），由 scene_plan 计时驱动：

  ```bash
  # 每场景一张静帧，位于场景中段帧（fps * mid_seconds），输出到 snapshots/<scene_id>.png
  npx remotion still projects/<slug>/index.tsx <CompositionId> \
    projects/<slug>/snapshots/<scene_id>.png \
    --frame=<mid_frame> --props=<abs artifacts/props.json> --public-dir=<abs public/>
  ```

  读取 scene_plan 并渲染所有静帧的辅助脚本在 `scripts/atelier_snapshots.py`（`python scripts/atelier_snapshots.py <slug>`）。然后在资源门停下。完整/草稿渲染是**compose**阶段，在批准之后。

## 已有先例（学*工作流*，不是外观）

两个参考作品——每个运行时一个——研读**流程**，绝不研读视觉语言：

- **Remotion 工坊** — Phantom Reach 解说（`projects/phantom-reach-explainer/`）：Playwright 捕获的应用画面加 PII 模糊层 → 逐句 TTS 用静默节拍拼接 → 免费 Pixabay 音乐 → 手写 Remotion 场景（自定义 intro、评分环、agentic 流程、CTA），一次性紫色主题。Compound Snowball（`projects/compound-snowball/`）和 Library of Alexandria（`projects/alexandria-fire/`）另外两个——三个 Remotion 工坊作品，三种完全不同的视觉语言。

- **HyperFrames** — `in-a-hurry`（`projects/in-a-hurry/`）：音乐驱动动态排版作品，用 HF 0.7 的 `beats` 命令将场景计时锁定到真实 drop。演练了 `/hyperframes-animation` 的 **5 个类别**：`kinetic-beat-slam`、`3d-text-depth-layers`（堆叠挤出）、`motion-blur-streak`（回声残影）、`transitions/css-distortion`（色差 RGB 分离）和 `adapters/html-in-canvas-patterns`（Three.js + UnrealBloom 用于主角 punchline）。每个节拍用不同缓动（`expo.out`、`back.out(2)`、`circ.out`、`sine.inOut`）。

**不要复现其中任何视觉语言**——下一部作品必须看起来完全不像它们。这才是重点。只研读*流程*（决策、排序、门、验证）。

另见：`skills/meta/animation-runtime-selector.md`（运行时 + 库路由）、`AGENT_GUIDE.md` → "Composition Authoring Mode"、`/hyperframes`（HF 路由和能力图）。
