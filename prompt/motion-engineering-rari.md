# Motion Engineering: Build a Video Studio Around Opus 5.5 — 拆解笔记

来源：rari（@0xwhrrari）X 长文，2026-10-01 发布，约 7 分钟阅读。原文：https://x.com/0xwhrrari/article/2105643919119696297
（本笔记为结构拆解与要点转述，非原文转载；原文请点链接看。Neon Jump 与 No After Effects 两份提示词包就是这套方法论的产物，已另存于本目录。）

## 核心论点

Opus 5.5 做视频的方式不是"想象画面"，而是写代码回答"在时刻 t，屏幕应该长什么样"。渲染器逐帧调用这个帧函数并编码成片。所以修改是局部的：改一个时间值、一条运动曲线、换一个素材，就能重渲。帧函数的形式大致是 frame = render(time, shot_list, assets, style_tokens, seed)，每帧可直接定位（seekable）、结果确定（不藏时钟、随机要播种）。

配套金句：单条提示词只能出 clip；要出 film，得先有 brief，再成 system。以及 Thariq（Claude Code 团队）拆穿的"one-shot 神话"：号称一发入魂的帖子，背后往往是一万字的提示词加上 skills、示例和 API key 的长期积累。

## 工作室五层（不能让模型把五层压成一步，否则出通用货）

1. DIRECTOR — 片子想说什么
2. REFERENCE — 观感与视觉依据
3. TIMELINE — 每个节拍发生什么变化
4. RENDERER — 每帧怎么生成
5. CRITIC — 哪里失败、为什么

## 十步流程

1. 写导演简报，不写氛围提示词：字段含 FILM（一句话/观众/时长/画幅）、ASSETS（logo、UI 截图、品牌字体颜色、音频）、VISUAL RULES（保留什么、避免什么、绝不虚构产品界面）、DELIVERABLES。
2. 给可检查的视觉参考，让模型先产出风格指南（色板、字体、构图、节奏、运动、质感）；素材缺失时让它停下来问，不许编造。
3. 把故事写成状态与节拍（如 00–02s HOOK、02–05s PROBLEM）；UI 动效先写状态链（SEARCH→RESULT→DETAIL→ACTION→CONFIRMATION）再谈动画。
4. 主动选渲染器（轻量 Canvas/SVG，或 Remotion/HyperFrames），硬要求：可寻址。
5. 按对象类别给运动定规矩，让运动有重量：微型 UI 快而少过冲、面板受控落定、镜头平滑、大标题强进入稳停留。
6. 声音和画面共用一条时间轴（BEAT GRID 打点），闭着眼听也该有形状。
7. 先看 contact sheet 再导出全片，按检查清单评审（含手机尺寸可读性、安全区、素材真实性等），一轮只修三个最大缺陷。
8. 多画幅从源工程分别导出：16:9 / 9:16 / 1:1 各自重新构图，不是裁剪。
9. 把工作室打包成文件：motion-studio/ 下放 brief.md、style-guide.md、shotlist.md、assets/、src/、reviews/、out/。
10. 长任务设六道评审门：批参考与素材 → 批风格指南与分镜 → 看静帧 → 粗剪 + contact sheet → 修三处最大缺陷 → 查音频/格式/交付物。

## 最后真正发给模型的提示词（要点转述）

让模型同时当导演和工程师：交代时长、产品、受众与"观众只需记住的一句话"；只许用提供的素材；先产出 style-guide.md 与 shotlist.md（带时间戳、进入/退出状态、每镜存在的理由）；选渲染器并说明原因；保证帧可寻址、确定性；运动/音频/转场共用一条时间轴；保留可编辑源码与可复现的渲染命令；按评审门推进：先示风格指南与分镜，再示 contact sheet，按 hook/可读性/连贯性/运动/音画同步打分，修最差三处后重渲；导出 16:9 与 9:16 两个独立构图版本；交付成片、海报帧、contact sheet、源码、素材清单与"仍需人工复核"的说明。

收尾公式：PROMPT → CLIP；BRIEF → SYSTEM → FILM → REVIEW → BETTER SYSTEM。

## 与我们已有沉淀的关系

- 与小政zzzzz 七步教程同构：签字门（风格指南/分镜先批）≈ 分镜签字，contact sheet ≈ 静帧检查，只修三处 ≈ "还不够"的定点返修，AI 评审打分两边都有。
- 与剧坊现状：分镜（shotlist）已有；缺的是 style-guide 作为一等产物、多画幅独立构图导出、以及六道评审门的显式状态机——可列入产品 backlog。
- 文中外部参考：Anthropic Opus 5.5 发布页、Remotion 文档、HyperFrames 开发者文档（heygen-com/hyperframes）。
