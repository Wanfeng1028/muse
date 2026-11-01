# 评估：motion studio 清单能否用在紫微星盘小程序前端

评估对象：X 帖子 @e1genqq 2026-10-31 的 motion studio 清单 20 项（归档见 prompt/x-post-e1genqq-motion-studio-20261101.md，仓库原件见本目录）。
评估目标：紫微星盘微信小程序前端，技术栈 Taro 4 + React 18 + TS。
评估原则：只评估，不改小程序代码；不为凑数硬说能用；接法写明到可执行程度，成本写明。

## 小程序硬约束（逐项评估的标尺）

1. 无 DOM：小程序 JS 环境没有 window/document，凡直接操作 DOM/SVG 的库不能直用。
2. 有 canvas：2D canvas 与 WebGL canvas 可用；Lottie 有小程序 canvas 适配路线。
3. 动画可用手段：CSS 动画、Taro createAnimation、以及纯 JS 的缓动与时间轴数学（不碰 DOM 的部分可抽取复用）。
4. 包体积：主包 2MB、总包 20MB 上限，动画库与素材都要计入。
5. 上架合规：代码须随包审计，不许运行时下载执行代码；GPL 代码不宜进闭源小程序包。
6. 产品现实：我方命盘是 2D 盘面，现有 6 个交互组件（水波纹、开关、粒子爆发、长按确认、按钮内加载、汉堡变叉）已覆盖基础微交互；评估只补真正缺的东西。

## 20 项评估表

| 序号 | 项目 | 结论 | 理由与接法 |
|---|---|---|---|
| 01 | remotion | 不适用 | React + Node 视频渲染管线，需 DOM 与服务端渲染；归剧坊视频生产，不归小程序 UI。另注意其自定义两档许可证，不是通用开源许可。 |
| 02 | remotion-dev/skills | 只能借 pattern | Agent skills 面向 Remotion 视频工程，不是前端代码；可借其“渲染—核验—修复”的工作纪律，用于小程序动效验收流程。 |
| 03 | anime | 只能借 pattern | 动画库直接操作 DOM/SVG，不能进小程序；可抽取其缓动曲线、时间轴编排、stagger 思想，用 CSS/Taro 动画实现，成本近零。 |
| 04 | motion | 只能借 pattern | React/DOM 动画库，含布局动画（FLIP）等小程序无对应引擎的概念；可借弹簧与缓动参数、过渡编排思想，手写实现。 |
| 05 | manim | 不适用 | Python 数学动画引擎，产出视频文件；可用于剧坊生产讲解视频，不进小程序 UI。 |
| 06 | lottie-web | 直接可用 | 走小程序 canvas 的 Lottie 播放适配路线（lottie-miniprogram 类适配器，接入时以 npm 最新版与 canvas 2d 接口在真机实测为准）。用于微交互、加载态、成功态、签到反馈等；JSON 素材小，须计包体积。 |
| 07 | mcp-for-blender | 不适用 | Blender 的 MCP 服务端插件，供 Claude 建改 3D 场景；桌面生产工具，归剧坊 3D 资产管线（若有），不进小程序 UI。 |
| 08 | three.js | 不适用（当前 UI） | 完整 3D 引擎；小程序虽有 WebGL，但包体积与低端机性能成本高，且命盘为 2D 盘面、无 3D 需求。若将来要 3D 星空/星球，再评估 threejs-miniprogram 适配路线。 |
| 09 | three-gpu-pathtracer | 不适用 | GPU 路径追踪需 WebGL2 与高端 GPU；小程序 WebGL 能力有限，且 UI 不需要真实光照渲染。 |
| 10 | JoltPhysics | 不适用 | 原生刚体/柔体物理引擎；小程序 UI 只需要弹簧/缓动，不需要碰撞仿真；引入 WASM 的成本与收益不成比例。 |
| 11 | postprocessing | 不适用 | three.js 后期特效（辉光、景深、调色）；我方光晕用 CSS 渐变已够，不需要 GPU 后期管线。 |
| 12 | three.quarks | 不适用 | three.js 粒子系统；我方粒子爆发已是 2D 实现，不需要 3D 粒子。 |
| 13 | tweakpane | 只能借 pattern（仅开发期） | DOM 调参面板不能进小程序；可借“隐藏调参页”做法：开发期做一个仅开发可见的参数页调动画数值，发布前剔除。 |
| 14 | ComfyUI | 不适用 | 节点式生图后端；若将来要 AI 封面/海报生成，走服务端调用，不进小程序前端代码；且 GPL-3.0 不宜进闭源包。 |
| 15 | CosyVoice | 间接可用（服务端） | 多语言 TTS 模型，不能在小程序端运行；可用作云端为 AI 解读生成语音，小程序用 InnerAudioContext 播放。这是后端能力，不是前端代码，成本为云端推理与音频托管；前置条件是云配置（envId 等）到位后才可排期。 |
| 16 | librosa | 间接可用（服务端/剧坊） | Python 音频分析（节拍检测等）；小程序端无音频分析需求；归剧坊 BGM/音画对齐管线。 |
| 17 | whisperX | 不适用（小程序 UI） | 语音转字幕（词级时间戳）；归剧坊字幕管线；小程序不录音转写。 |
| 18 | obs-studio | 不适用 | 桌面录屏/推流软件；归剧坊录制管线（若有）。 |
| 19 | lossless-cut | 不适用 | 桌面免重编码快剪；归剧坊剪辑管线。 |
| 20 | FFmpeg | 不适用（小程序 UI） | 编解码交付管线；归剧坊后端；小程序只用 video 组件播放，不编码。 |

## 给小程序前端的可用短名单（按优先级）

### P0：lottie-web（直接可用）

- 接法：小程序 canvas 的 Lottie 播放适配路线 + JSON 素材；先在真机实测 canvas 2d 播放性能与包体积，再批量铺开。
- 用途：加载态、成功态、签到反馈、空态微交互；替换现有部分手写 CSS 微交互中表现力不足的几处。
- 成本：适配器 + 若干 KB 级 JSON 素材；不引 DOM 渲染分支。
- 注意：只用 canvas 渲染路径，不用 SVG/HTML 渲染分支；素材须自制或有明确授权，不许直接挪用他人动画 JSON。

### P1：anime + motion（只借 pattern，不引库）

- 接法：不引入两个库本身；抄它们的缓动参数、弹簧参数、时间轴与 stagger 编排思想，用 CSS 动画与 Taro createAnimation 手写实现。
- 用途：统一全应用动效曲线、时长与编排节奏（现有 6 交互组件的动效参数可按此收敛一次）。
- 成本：近零（手写代码，无包体积增加，无许可证风险，MIT 思想借鉴不涉及代码复制）。

### P2：tweakpane（只借 pattern，仅开发期）

- 接法：开发期加一个隐藏调参页，调动画数值；发布前剔除，不进上架包。
- 用途：动效数值调试期提效。
- 成本：一个开发页；零上架成本。

### P3：CosyVoice（间接，服务端，非前端任务）

- 接法：云端 TTS 为 AI 解读生成语音，小程序用 InnerAudioContext 播放。
- 用途：解读语音播报（未来功能）。
- 成本：云端推理与音频托管；前置条件是云配置到位，不属于本轮前端工作。

## 明确不做的清单

- three.js 系（three.js、three-gpu-pathtracer、postprocessing、three.quarks）：无 3D 需求，成本高于收益。
- 物理与仿真（JoltPhysics）：UI 不需要碰撞仿真。
- 视频生产管线（remotion、manim、mcp-for-blender、ComfyUI、FFmpeg、obs-studio、lossless-cut、whisperX、librosa）：归剧坊生产管线，不归小程序 UI；其中 ComfyUI、obs-studio、lossless-cut 另有 GPL 约束，不宜进闭源包。

## 归档与许可证总览

- 全量 12 项：anime、manim、lottie-web、mcp-for-blender、three-gpu-pathtracer、JoltPhysics、postprocessing、three.quarks、tweakpane、CosyVoice、librosa、lossless-cut（本目录，.git 已剥离）。
- 索引 6 项：index/remotion、three-js、ComfyUI、obs-studio、FFmpeg、motion（LICENSE 原文 + NOTE.md）。
- 既有 2 项：muse-repo/remotion-skills/、muse-repo/whisperX/（本轮核验，未重克隆）。
- 许可证以各仓库 LICENSE/COPYING 原文为准，详见索引笔记。
