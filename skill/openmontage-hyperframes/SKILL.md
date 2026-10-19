---
name: openmontage-hyperframes
version: "1.0.0"
description: 说明剧坊何时应选 HyperFrames 而非 Remotion/FFmpeg，如何映射产物到 HyperFrames 工程、如何驱动 CLI 校验渲染，并汇总实战踩坑与反模式。适用于动效图形、产品宣传、网页转视频等 HTML/GSAP 原生场景。
metadata:
  license: AGPL-3.0
---

# HyperFrames 技能（第二层）

本文件是剧坊针对 HyperFrames 的专属指南：讲清流水线何时应选它、产物如何映射到工程文件、compose 阶段如何驱动 CLI。原始 HyperFrames 知识（作者契约、`data-*` 属性、GSAP 时间线规则、CLI 参数、registry 块、网站转视频）请参阅第三层技能目录：

- `.agents/skills/hyperframes/`——总路由（0.7+ 拆分为下列细分技能）
- `.agents/skills/hyperframes-core/`——合成契约：`data-*` 时序、轨道、子合成、确定性渲染
- `.agents/skills/hyperframes-creative/`——非动画的创意方向：配色、字体、旁白、节拍规划
- `.agents/skills/hyperframes-media/`——TTS/BGM/音效/转写/字幕/抠像
- `.agents/skills/hyperframes-animation/`——所有运动知识（规则、蓝图、转场、运行时适配）
- `.agents/skills/hyperframes-cli/`——init、add、lint、validate、inspect、snapshot、preview、render、benchmark、lambda、doctor
- `.agents/skills/hyperframes-registry/`——`hyperframes add` 与块接线
- `.agents/skills/website-to-video/`——采集转视频流程
- `.agents/skills/music-to-video/`——基于 `hyperframes beats` 的卡点视频
- `.agents/skills/motion-graphics/`——短篇设计驱动动效模式
- `.agents/skills/media-use/`——`resolve` 动词解析 BGM/音效/图片/图标
- `.agents/skills/remotion-to-hyperframes/`——仅在用户明确要求迁移 Remotion 源码时使用

本文件只讲两者之间的桥接。

## 何时选 HyperFrames（对比 Remotion、FFmpeg）

剧坊把两个概念分开：

- **`renderer_family`**——创意语法（`explainer-data`、`cinematic-trailer`、`product-reveal` 等），在提案阶段确定。
- **`render_runtime`**——实现该语法的技术引擎（`remotion`、`hyperframes`、`ffmpeg`），同样在提案阶段确定。

两者都锁在 `proposal_packet.schema.json` 里，未经 `decision_log` 中记录 `render_runtime_selection` 决策，不得在 `edit_decisions` 中改动。静默切换运行时属于违约。

### 决策矩阵

| 场景 | 首选 | 理由 |
|------|------|------|
| 已有讲解类 React 场景组件栈（text_card、stat_card、图表场景、字幕叠加、TalkingHead、CinematicRenderer） | **Remotion** | 这些合成已在 `remotion-composer/` 中就绪，复用免费，用 HTML 重做不划算 |
| 逐词烧录字幕 / 卡拉 OK 字幕 | **Remotion** | `remotion_caption_burn` 是 Remotion 专有，HyperFrames 首日未对齐 |
| 虚拟人 / 口型同步主播 | **Remotion** | `TalkingHead` 合成在 Remotion，HyperFrames 暂无等价物 |
| 动态排版、重文字动效、GSAP 原生动画 | **HyperFrames** | HTML/GSAP 是天然载体，用 Remotion `interpolate()` 表达既慢又脆 |
| 产品宣传片 / 发布会短片 / 营销标题卡 | **HyperFrames** | CSS/GSAP 语法与设计师思路一致，模板（`kinetic-type`、`product-promo`、`swiss-grid`）起点扎实 |
| 网站转视频 / UI 驱动合成 | **HyperFrames** | `website-to-video` 流程专为此设计 |
| 需要 registry 块（数据图表、颗粒叠加、扫光、着色器转场） | **HyperFrames** | registry 为 HyperFrames 独有，Remotion 没有 `hyperframes add` |
| 合成 UI / 假终端 / 假浏览器演示 | 视现有覆盖而定 | 剧坊已有 Remotion `TerminalScene`；终端以外的 UI chrome 用 HyperFrames HTML 更省事 |
| 纯拼接裁切、无合成 | **FFmpeg** | 两个引擎都无增益 |
| 本机未装 Remotion | **HyperFrames**（若可用）或 **FFmpeg** | 不得静默降级，必须先告知用户 |

### 硬规则：两个运行时都可用时必须同时呈现

上表是对话的输入，不是默认选项的许可。当 Remotion 与 HyperFrames 都可用时，提案阶段必须：

1. 结合 brief 向用户呈现两者及各自利弊。
2. 依据 `delivery_promise` 与 `visual_approach` 推荐其一并说明理由。
3. 等待用户批准。
4. 在 `render_runtime_selection` 决策的 `options_considered` 中记录两者。

完整契约见 `AGENT_GUIDE.md` 的「Present Both Composition Runtimes（HARD RULE）」，强制方式见 `skills/meta/reviewer.md` 的 CRITICAL 级发现。

### 硬规则：要求运动感的交付物

若 brief 的 `delivery_promise.motion_required` 为 `true`（科幻预告、电影感先导、燃剪等），则提案阶段选定的运行时是承诺而非提示。compose 阶段不得降级为 FFmpeg 的 Ken Burns。若所选运行时失败（Remotion 未安装、`npx hyperframes doctor` 报错），按 `AGENT_GUIDE.md` 的「Escalate Blockers Explicitly」上报并等待用户批准后再切换。

## 第一阶段仍属 Remotion 专属的部分

首日不要尝试移植以下内容，它们需要专门的对齐工作：

- `remotion_caption_burn`（逐词烧录字幕）
- `TalkingHead` 合成（虚拟人/口型同步）
- 现有纪录片混剪片尾叠加层（依赖特定 Remotion 组件）
- 任何假设素材放在 `remotion-composer/public/` 并由既有 React 场景组件消费的逻辑

以上保持 `render_runtime = "remotion"` 照旧处理。

## 工程工作区结构

HyperFrames 需要独立工作区。不要复用 `remotion-composer/public/`——那是 Remotion 的共享暂存目录，混用会导致跨项目冲突。

```
projects/<project-name>/
├── artifacts/
├── assets/
│   ├── images/
│   ├── video/
│   ├── audio/
│   └── music/
├── hyperframes/                ← HyperFrames 运行时工作区（选中时）
│   ├── index.html              ← 根合成
│   ├── compositions/           ← 子合成与 registry 块
│   │   └── components/         ← registry 组件（颗粒叠加等）
│   ├── assets/                 ← 项目素材的软链或拷贝
│   ├── hyperframes.json        ← CLI 配置（registry URL、安装路径）
│   ├── DESIGN.md               ← 由 playbook 派生的视觉简报（可选）
│   └── narration.wav           ← TTS 输出（适用时）
└── renders/
    └── final.mp4
```

模板化工作区由 compose 阶段的 `hyperframes_compose` 依据 `edit_decisions` + `asset_manifest` + 当前 playbook 生成；Atelier 工作区在素材阶段手工编写，通过 `hyperframes_compose.render_existing` 原样传入。两者都在 `projects/` 下，并随生产工作区一同被 gitignore。

### 为什么每个项目要独立工作区

- HyperFrames 相对项目根解析 `data-composition-src`、`src=` 与 registry 块，共享目录会破坏解析。
- `npx hyperframes lint | validate | render` 都针对工程目录操作，不接受类似 Remotion 的抽象 composition ID。
- 素材与引用它的 HTML 同目录，符合 `website-to-video` 的参考流程。

## 产物到 HyperFrames 的映射

当 `render_runtime = "hyperframes"`，compose 阶段把剧坊产物翻译为工程文件：

| 剧坊产物字段 | HyperFrames 目标 |
|---|---|
| `edit_decisions.cuts[]` | `index.html` 时间线，每个 cut 一个 `<div data-composition-id data-composition-src>` |
| `cuts[i].in_seconds / out_seconds` | 片段元素上的 `data-start` / `data-duration` |
| `cuts[i].type`（场景类型） | 经 `hyperframes add` 安装的 registry 块，或手写子合成模板 |
| `asset_manifest.assets[]` 路径 | 拷贝/软链到 `projects/<p>/hyperframes/assets/`，以相对 `src=` 引用 |
| `audio.narration.segments[]` | `<audio>` 元素，配对的 `data-start` / `data-duration` |
| `audio.music` | 第二个 `<audio>`，`data-volume` 更低 |
| `subtitles`（开启且有源） | registry 的 `captions` 块或手写逐词 span——不要用 `remotion_caption_burn` |
| 选定的 playbook | `:root` CSS 自定义属性 + `DESIGN.md`，见 `lib/hyperframes_style_bridge.py` |
| `renderer_family` | 决定使用哪个顶层 HTML 模板、预装哪些 registry 块 |

具体流程：`hyperframes_compose` 写入工作区文件，依次运行 `lint → validate → render`，返回带 MP4 路径的 `render_report`。参见 `tools/video/hyperframes_compose.py`。

### 工作区内的编写文件

上游 `website-to-video` 使用 `DESIGN.md`、`SCRIPT.md`、`STORYBOARD.md` 作为分步文件。剧坊不用它们替换正式产物契约——`brief`、`script`、`scene_plan`、`edit_decisions` 仍是 `projects/<p>/artifacts/` 下的唯一真源。把上游文件当作写进 HyperFrames 工作区的**便利副本**：

- `DESIGN.md`——由选定 playbook 派生，`hyperframes_compose` 或 `lib/hyperframes_style_bridge.py` 写入，可当工作简报使用。
- `SCRIPT.md`——供人审阅的旁白副本，正式脚本仍以 `artifacts/script.json` 为准。
- `STORYBOARD.md`——按节拍的创意方向副本，正式分镜仍以 `artifacts/scene_plan.json` 为准。

若副本与正式产物冲突，以正式产物为准。

## 运行时选择规则

1. **提案阶段**选定 `render_runtime`，并以 `render_runtime_selection` 类别记入 `decision_log`，需参考决策矩阵与各运行时的实际可用性。
2. **预检**报告可用运行时。不可用的运行时不得作为提案选项，除非用户明确同意安装。
3. **剪辑阶段**原样透传 `render_runtime`。
4. **compose 阶段**读取 `edit_decisions.render_runtime`，经 `video_compose` 路由到 `hyperframes_compose` 或既有 Remotion 路径。无新的 `render_runtime_selection` 决策不得换引擎。
5. **终审**记录 `render_runtime_used`，若与提案不同则置 `runtime_swap_detected = true`。

## 预检——HyperFrames 可用性

预检时，provider 菜单报告 HyperFrames 可用性。`hyperframes_compose` 的 `get_info()` 返回：

```json
{
  "runtime_available": true,
  "node_major": 22,
  "ffmpeg_available": true,
  "doctor_ok": true,
  "install_instructions": "…"
}
```

`runtime_available: true` 的最低要求（全部满足）：

- Node.js 主版本 ≥ 22
- PATH 上有 `ffmpeg`
- PATH 上有 `npx`（随 Node.js 附带）
- `npx hyperframes doctor` 退出码为 0，或等价轻量检查通过

不要求 `bun`——HyperFrames 通过 `npx hyperframes` 使用即可（公开 npm 包名为 `hyperframes`；仓库内部的 `@hyperframes/cli` 未上公开 registry，会返回 404）。

当 `runtime_available: false` 时，预检必须说明原因与安装指引。按 `AGENT_GUIDE.md` 的 Setup Offer Protocol 按成本归类：

- 缺 Node 22 → 约 5 分钟安装，说明能解锁什么
- 缺 FFmpeg → macOS/Linux 约 1 分钟，Windows 更久
- `doctor` 报问题 → 原样展示 doctor 输出

## 校验流程

HyperFrames 自带真实校验栈。宣布渲染完成前必须全部通过：

1. **`npx hyperframes lint`**——静态契约检查（重复 id、轨道重叠、缺 `data-composition-id`、未注册时间线），渲染前必须通过。
2. **`npx hyperframes validate`**——浏览器运行时检查：在暂停的合成中 seek、截图、采像素、计算 WCAG 对比度、校验 `window.__timelines` 注册与定时元素的 `class="clip"`。渲染前必须通过（迭代期可用 `--no-contrast` 推迟对比度，但终版不行）。
3. **`npx hyperframes render --quality standard`**——产出 MP4。
4. **渲染后终审**——用 ffprobe 探测、抽帧、转写音频、与脚本比对，契约同 Remotion 路径，参见 `final_review.schema.json`。

lint 或 validate 失败时**不要**渲染。修好再跑。明知合成有问题却静默渲染属于违约——validate 能捕捉 FFmpeg 与 Remotion 抓不到的问题，这正是它存在的意义。

## 风格桥（playbook → CSS）

剧坊 playbook 目前翻译为 Remotion 的 `themeConfig`。对应 HyperFrames 的输出为：

- `:root` 上的一组 CSS 自定义属性（`--color-bg`、`--color-fg`、`--color-accent`、`--font-heading`、`--font-body`、`--ease-primary`、`--duration-primary` 等）。
- 一份简述视觉系统的 `DESIGN.md`。
- 可选的字体 `@import`（仅限 HyperFrames 字体编译器支持的字型）。

见 `lib/hyperframes_style_bridge.py`。playbook 无需分叉——现有 schema 已携带驱动两个引擎所需的信息。

## 成本模型

HyperFrames 本地渲染：API 成本为 $0，但 CPU 密集（无头 Chrome + FFmpeg）。通过 `cost_tracker` 跟踪：

- `estimate`——基于合成时长 × 分辨率 × `--workers`
- `reserve`——0（无 API 支出）
- `reconcile`——实际墙钟渲染时长

与 Remotion 同一模式。

## 实战踩坑

以下问题上游文档不提示，但会让你花 60 分钟渲染才发现。请在编写时规避，而不是渲染时。

### 全屏背景视频：源分辨率陷阱（不是框架 bug）

现象：背景视频渲染成居中的小方块，四周黑边，尽管你告诉 HyperFrames 素材是 1920×1080。六次渲染排查后确认：**这几乎总是源质量问题，不是 HyperFrames 框架 bug。** 改输入，不要改 CSS。

根因（在 Pexels + Pixabay 素材上观察到）：许多免费素材即便选「大」尺寸档，实际只有 640×360 或 960×540。若你的预处理写成 `scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:...`，就会得到 1920×1080 的文件、但可见内容只有居中的 640×360 加黑边。HyperFrames 忠实地播放这个文件——你看到的「黑框里的小视频」其实是正确的信箱化输入。

先诊断：在怪 CSS 之前，对源片与预处理后的片子跑 `ffprobe -v error -select_streams v -show_entries stream=width,height`。若预处理后的文件已是 640×360 有效区嵌在 1920×1080 内，问题在上游。

修法：预处理改为「缩放至铺满再裁切」，而非「缩放至适配再加边」：

```
-vf "scale=1920:1080:force_original_aspect_ratio=increase,\
     crop=1920:1080,unsharp=3:3:0.6"
```

这样会把小素材放大到至少覆盖 1920×1080、裁掉溢出、再用 unsharp 弥补观感上的软。输出为满屏，HyperFrames 会铺满渲染。

经典的 wrapper-div 模式（见 `patterns.md`）仍是背景的推荐 HTML 结构：

```html
<div style="position:absolute;top:0;left:0;width:1920px;height:1080px;overflow:hidden;">
  <video
    data-start="0" data-duration="60" data-track-index="0"
    src="..." muted playsinline
    style="width:100%;height:100%;object-fit:cover;"
  ></video>
</div>
```

使用它的原因是：wrapper 上的 `overflow: hidden` 能在视频宽高比与 16:9 略有差异时优雅裁切；内层 `<video>` 的 `object-fit: cover` 能处理源宽高比不是 16:9 的（罕见）情况。它**不是**框架布局 bug 的绕行方案——只要源文件本身铺满整帧，框架也能正确给 `<video class="clip">` 定尺寸。

视觉处理（`filter`、`border-radius` 等）加在 wrapper 上，或用 `.bg-slot video { filter: ... }` 这类限定选择器。

隐蔽与显形的差别：当叠加暗滤镜（`brightness(0.25–0.35)`）或满屏文字时，这个坑会被掩盖——黑边看起来像「氛围暗」。一旦改成画面主导（brightness > 0.5、下三分之一文字），它立刻显形。若一开始就打算走画面主导路线，素材阶段就该探测源分辨率。

确实拿不到高清素材时，换流水线：用 FFmpeg 混合合成（外部 B-roll 卷先 scale-to-cover + crop + unsharp，再用色键叠加 HyperFrames 文字）。`projects/quantum-willow-multiverse/` 在用 640×360 Pexels 素材渲染六次后最终选择了这个方案。

### 画面主导场景渲染前务必预览扫片

60 分钟一次的渲染很贵。正式渲染前打开 Launch 预览面板（或 `npx hyperframes preview`），至少扫到每章一个 B-roll 主导场景。小视频 bug 以及「1080p 下下三分之一文字跑出画面」这类布局问题，在预览阶段是 2 秒的目视检查，到渲染阶段就是 60 分钟的返工。

### 提升素材可读性靠局部处理，不靠降不透明度

在 B-roll 上叠字时，不要简单压低视频不透明度——那会同时弄脏两层。正确做法：

- 视频保留 `filter: brightness(0.55) saturate(0.85)`，可见但压暗。
- 在具体文字下方加局部 CSS scrim（`radial-gradient` 或带 `rgba(7,7,12,0.5)` 的 `linear-gradient`），尺寸贴合文字块。
- 文字本身加 `text-shadow: 0 2px 24px rgba(0,0,0,0.8)`，形成与背景无关的局部光晕。

这样画面仍有生气，字幕与标题在任何帧上都清晰。

### 素材需先加密关键帧

当素材的关键帧间隔 > 5s 时，渲染会报 `video_heavy_parallel_timeout` 或出现帧冻结。下载的素材先重编码再放入工作区：

```bash
# 重编码素材，将关键帧间隔压到 1 秒，便于并行捕获
ffmpeg -i input.mp4 -c:v libx264 -r 30 -g 30 -keyint_min 30 -sc_threshold 0 -movflags +faststart output.mp4
```

参见 `hyperframes_compose` 现有的工作区准备流程——它目前尚未自动完成这一步。

### 视频密集的合成用 `--workers 1` 渲染

默认并行捕获在大量视频同时加载时会压垮无头 Chrome。任何含 >5 个背景视频元素的合成，一律给 `hyperframes render` 传 `--workers 1`。

### 字体用 Outfit / Inter / JetBrains Mono，别用 Space Grotesk

HyperFrames 的确定性字体编译器只会内联它有映射的字型。`Space Grotesk` 即便通过 Google Fonts 加载，也会落到回退字体（通常是 Arial）。查看编译器警告或 `deterministicFonts.ts` 映射表。安全选择：`Outfit`、`Montserrat`、`Inter`、`JetBrains Mono`、`Poppins`、`Playfair Display`。

## 反模式

- ❌ 现有 schema 已带颜色、字体、动效，却为 HyperFrames 分叉 playbook 数据。
- ❌ HyperFrames 合成引用 `remotion-composer/public/`——HyperFrames 工作区独立自足。
- ❌ 从剧坊编排器运行 `hyperframes init`。`init` 会创建自己的工程语义并安装 agent 技能，是给人手工引导项目用的，不是给流水线用的。`hyperframes_compose` 直接生成工程文件。
- ❌ 把 HyperFrames 当成「没有 Remotion 的 React」。它是 HTML 优先 + GSAP。若场景以 React JSX 写成，就该放 Remotion。
- ❌ 在 HyperFrames 的 GSAP 里用 `repeat: -1`。无限补间会破坏确定性的 seek-and-capture 渲染，始终用有界重复。
- ❌ 在 `async` 上下文、`setTimeout` 或 Promise 中构造时间线。页面加载后 `window.__timelines` 必须同步填充完毕。

## 采用 HyperFrames 的流水线

| 流水线 | 状态 |
|--------|------|
| `animation` | 第一批——动效图形重的 brief 中 HyperFrames 是一等选项 |
| `animated-explainer` | 第一批——概念是 HTML/GSAP 原生时可用；数据图表重的讲解仍默认 Remotion |
| `screen-demo` | 第一批——合成产品 UI 可用；终端类演示仍优先 Remotion 的 `TerminalScene` |
| `cinematic` | 第二批 |
| `hybrid` | 第二批 |
| `documentary-montage` | 第二批 |
| `talking-head` | 延后——依赖 TalkingHead 对齐 |
| `avatar-spokesperson` | 延后——依赖 TalkingHead 对齐 |
| `clip-factory`、`podcast-repurpose`、`localization-dub` | 延后——现有 compose 路径依赖 Remotion 字幕烧录 |
| `framework-smoke` | 不适用（测试流水线） |

已采用流水线的提案与 compose 导演需明确描述运行时选择，参见各流水线的 `proposal-director.md` 与 `compose-director.md`。
