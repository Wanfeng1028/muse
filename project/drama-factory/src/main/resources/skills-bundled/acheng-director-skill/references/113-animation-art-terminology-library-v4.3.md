# 113｜动画与原画专业术语库 v4.3

本库是 Acheng Director 的 advisory vocabulary。它帮助宿主模型从公开动画制作教育中选择少量有用术语，再把术语翻译成 H3 能看见、听见或验收的事实。它不是第二套分镜、动作、H3 或资产真值，也不替代 `production.json` 中的字段。

## 调度规则

每个 Segment 默认选择 3–12 个术语。模型先根据题材、镜头、表演、打戏、场景和视效选择术语，再逐个展开为：

1. 时间窗或帧窗；
2. 可见动作、姿态、位置、朝向、受力或材质变化；
3. 对应的镜头路径、布局或剪辑关系；
4. 声音、对白、尾态或机器验收证据。

术语本身不算证据。只写 `staccato`、`sakuga`、`cinematic`、`dynamic` 或 `high quality` 而没有可见事实，仍然视为未完成。宿主应读取 `data/animation-art-terminology.json`；`scripts/animation_term_catalog.py` 只用于显式 term/category 查询，自动模式先给候选类别，再由宿主结合 Segment 事实选择术语。最终把自然语言事实写入各专业模块的权属字段和 H3 正文。

`on ones`、`on twos`、`on threes` 是互斥的曝光策略；`straight-ahead` 和 `pose-to-pose` 是不同的设计方法。不能无条件同时启用。24 fps、120 fps、8K、无 BGM、特定软件或固定镜头语法也不能因为术语库出现而变成全局默认。

## 分类覆盖

JSON 主库位于 `data/animation-art-terminology.json`，包含九类：

- 时间与曝光：timing、spacing、on ones/twos/threes、hold、accent、snap、hang time、ease-in/ease-out、staccato、legato；
- 关键姿态与作画结构：key pose、extreme、breakdown、in-between、passing position、pose-to-pose、straight-ahead、line of action、gesture、silhouette、volume consistency；
- 表演与运动：anticipation、overshoot、settle、follow-through、overlap、drag、secondary action、head lead、eye trace、breath beat、blink、mouth-shape synchronization；
- 战斗与冲击：contact pose、recoil、impact frame、smear frame、stretch frame、motion arc、force transfer、resistance、redirection、attack line、axis lock、cut on action；
- 镜头与剪辑：staging、negative space、screen direction、eyeline、low tracking、overhead reveal、obstruction reveal、hard reframing、L-cut、J-cut、match cut、hold frame；
- 布局与环境：foreground/midground/background、multiplane、parallax、depth cue、establishing layout、perspective compression、vanishing point；
- 线条、色彩与合成：thin broken ink、line weight、rough painterly fill、flat cel shading、value grouping、color script、rim light、atmospheric perspective；
- 特效与碎屑：velocity stroke、hair arc、debris arc、dust burst、impact flash、anticipation-release-impact-decay、solid/gas/emissive channels；
- 验收与证据：fact-to-field mapping、continuity anchor、readability check、spatial consistency、audio-visual sync、tail state。

## 与模块的权属

术语选择由 Acheng Director 统一调度；事实仍由专业模块拥有：story 负责叙事和对白，shots 负责镜头和屏幕空间，performance 负责微动作和表演因果，combat 负责受力与攻应果续，effects 负责效果阶段，assets/scene-design 负责材质和环境设计，model 负责把已经批准的事实编译成 H3，continuity 负责边界状态，audit 负责证据门。多个模块可以对同一术语做交叉复核，但只有字段 owner 能写入生产真值。

术语库不会启动代理、调用付费媒体模型或创建新的生产字段。它只产生选择结果和展开建议；`write_paths` 为空。没有真实媒体时仍保持 `visual_status=UNVERIFIED`。

## 公开资料边界

词义来自传统二维动画、布局、作画监督、影视剪辑和视效制作中通用的公开术语。不同工作室对同一词可能有细微差异，因此 Acheng Director 采用“术语 + 本段自然语言证据 + QA”三件套，不把某一本词典或某个软件的用法冒充 MiniMax H3 官方字段。已核对的教学依据包括 Foundry Learn 对 key pose、extreme、breakdown/passing position、in-between、spacing chart 与 timing 的说明，以及 Toon Boom Learn 对 timing、keyframe/in-between、pose-to-pose/straight-ahead 和 follow-through/drag/overlap 的教学。

- [Foundry Learn: Spacing Chart](https://learn.foundry.com/modo/12.1/content/help/pages/animation/tools/spacing_chart.html)
- [Toon Boom Learn: Timing Principle](https://learn.toonboom.com/modules/animation-principles/topic/timing-principle)
- [Toon Boom Learn: Straight Ahead and Pose-to-Pose Principle](https://learn.toonboom.com/modules/animation-principles/topic/straight-ahead-and-pose-to-pose-principle)
- [Toon Boom Learn: Follow Through Principle](https://learn.toonboom.com/modules/animation-principles/topic/follow-through-principle)

这些来源用于核对动画制作术语的一般含义，不证明视频模型识别或执行某个术语的确定能力。具体 H3 字段、标签和顺序仍以已安装 `h3-prompt-writing` 的 base/ref 指南及 `references/70-minimax-h3-compiler.md` 为准。
