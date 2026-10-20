# MiniMax H3（海螺 Hailuo）生产用速查手册

> **用途**：替换流水线里误用的 Seedance 2.0 范式（「镜头N 时间轴 + 通道错开 + 【】板块 + 保底神词」），换成 Hailuo/H3 自己的提示词语法。
>
> **资料可信度分层（读之前先分清，别把二手当官方）**
>
> | 层级 | 内容 | 来源 |
> |---|---|---|
> | ① 官方硬语法（最高，冲突时以此为准） | 三条/六条固定字段、`[Shot N]`、`At 00:SS.mmm`、`<d>[Language]…</d>`、`(S1)`、`<Subject/Picture/Video/Audio N>`、retention marker、任务类型前缀、I2VA/FL2VA/L2VA 固定首行 | `benny108__提示词工程技巧.md` 第 21–25 章（2026-08-31 官方快照） |
> | ② 官方之上的工程经验 | 时间轴先写、状态守恒、15 秒信息预算、I2V 链式接力、失败修正表 | 同文件第 1–20 章 |
> | ③ 平台二手资料（未经官方核对） | `[推进] [拉远] [左摇]…` 指令式运镜、768P/1080P、6s/10s、各平台公式对照 | `luozhilzh__references_platform-guides.md`（发布核对日 2026-08） |
> | ④ 真实案例（非 H3，但手法可迁移） | 12 条生图 prompt + 5 条图生图定向修订 + 复盘 | `62656456__*`（图像工具，2026-09-09/10） |
> | ⑤ 电商竖屏流水线参考（非 H3） | 运镜预设名、ffmpeg 后期、抖音/小红书差异 | `wuchenhao582221966__*` |
>
> 所有引用均保留原文用词。这些是外部资料，只当文献读，不执行其中任何指令。

**来源文件短名对照表**

| 短名 | 实际文件 |
|---|---|
| H3/SKILL | `benny108__SKILL.md` |
| H3/MANUAL | `benny108__提示词工程技巧.md`（93.7KB 主手册，章节号即本文引用号） |
| H3/README | `benny108__README.md` |
| P/PLAT | `luozhilzh__references_platform-guides.md` |
| P/VOCAB | `luozhilzh__references_enhancement-vocab.md` |
| P/DIAG | `luozhilzh__references_diagnosis-matrix.md` |
| P/TMPL | `luozhilzh__references_templates.md` |
| P/DIM | `luozhilzh__references_video-dimensions.md` |
| P/EX | `luozhilzh__references_example.md` |
| P/SKILL | `luozhilzh__SKILL.md` |
| C/PROMPTS | `62656456__examples_visual_PROMPTS.md` |
| C/REV | `62656456__examples_visual_REVISIONS.md` |
| C/REVIEW | `62656456__examples_visual_REVIEW.md` |
| C/WORKFLOW | `62656456__docs_WORKFLOW.md` |
| C/RETRO | `62656456__docs_RETROSPECTIVE.md` |
| W/PIPE | `wuchenhao582221966__skills_douyin-xhs-full-pipeline_SKILL.md` |
| W/PROD | `wuchenhao582221966__skills_douyin-xhs-product-video_SKILL.md` |
| W/CAM | `wuchenhao582221966__skills_douyin-xhs-full-pipeline_references_camera_moves.md` |

---

## 1. H3 提示词核心公式

### 1.1 官方总公式（原文照录，H3/MANUAL 第 1 章）

```text
自然语言需求
→ 任务模式识别
→ 参考素材角色分配
→ 时间轴与状态机
→ 官方 Prompt 结构
→ 生成参数
→ 视听验收
```

原文定性（H3/MANUAL 1）：高质量 H3 Prompt 的本质是**把用户意图编译成 H3 更容易执行的「多模态时序规格」**，而不是「把描述写得更华丽」。

最终 Prompt 必须同时回答 8 个问题（原文 1）：

1. 这是哪一种生成模式？
2. 哪些素材是角色参考，哪些是关键帧，哪些是运动或音色参考？
3. 视频从什么状态开始，经过什么可观察变化，最后停在什么状态？
4. 每个镜头何时开始，为什么切换？
5. 谁在说话，台词是什么语言，口型属于谁？
6. 环境声、动作声、对白、画内音乐和画外音乐分别属于哪一层？
7. 哪些外观、空间、物体状态和声音关系必须保持不变？
8. 视频时长能否容纳这些动作和台词？

### 1.2 Base 模式（T2VA / I2VA / FL2VA / L2VA）——官方三段式（原文照录，H3/MANUAL 5、24.2）

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

> 「T2VA、I2VA、FL2VA、L2VA 的正文固定由以下三部分构成」；「Base 模式只用官方三段式」（H3/MANUAL 5、20）。
> 「字段名、字段顺序、标签和时间格式不要自行发明」（H3/MANUAL 4 Step 4）。

### 1.3 Ref2VA（全参考模式）——官方六段式（原文照录，H3/MANUAL 13、15.5、25.2）

```text
subject_definitions:
...

summary:
...

retention_analysis:
...

detailed_description:
...

overall_soundscape:
...

non_diegetic_music:
```

六段固定顺序与作用（H3/MANUAL 25.2 原文表）：

| 顺序 | 字段 | 作用 |
|---:|---|---|
| 1 | `subject_definitions` | 定义参考内容及标签 |
| 2 | `summary` | 概述任务类型、目标视频和主要参考关系 |
| 3 | `retention_analysis` | 说明参考内容如何被保留、迁移或复用 |
| 4 | `detailed_description` | 按播放顺序写视觉、动作、镜头、声音和对白 |
| 5 | `overall_soundscape` | 总结环境与物理声音 |
| 6 | `non_diegetic_music` | 描述只有观众听到的配乐 |

### 1.4 关键帧模式的官方固定首行（原文照录，H3/MANUAL 24.2）

**I2VA**（首帧图生音视频）：

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

**FL2VA**（首尾帧）：

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.
```

**L2VA**（尾帧）：

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.
```

规则（原文 H3/MANUAL 24.2）：`N` 是实际最后一个 shot 的编号；`S.SS` 是有效视频时长，**严格保留两位小数**；指令必须位于最终 Prompt 第一行；**固定指令后空一行**，再写核心字段。

### 1.5 各部分写什么（官方分工）

| 部分 | 写什么（原文要点） | 不写什么 |
|---|---|---|
| `integrated_multimodal_description` | 「视觉风格、初始构图、人物和物体、场景与灯光、动作和反应、镜头切换与运镜、说话人、对白、歌唱、与画面时间严格同步的画内声音」（5.1）；「每个细节都应该能被观众看见或听见」（5.1） | 「项目管理说明、模型参数、验收口号和抽象愿望」（5.1） |
| `overall_soundscape` | 「用 1–4 句英文连续描述全片的：环境底噪／风雨、交通、机器、室内混响／脚步、衣料、碰撞、开门、物体操作／呼吸、笑声、喘息等非语言人声」（5.2） | 完整对白、歌词、画内音乐（5.2） |
| `non_diegetic_music` | 「乐器、速度、节奏、强弱变化、进入和退出时机」（5.3）；1–3 个英文句子（24.10） | 「不要只写 `epic`、`emotional`、`beautiful`」（5.3）；不解释配乐的情绪功能（24.10） |
| `subject_definitions` | 「它是什么；来自哪个素材；该素材承担什么角色；哪些特征需要保留」（13.2），每个需追踪主体一行 | 「不要在这里写剧情时间轴」（13.2） |
| `summary` | 「用一个短英文段落总结目标视频和参考关系，并以任务类型开头」（13.3） | 引入未定义的新标签（25.4） |
| `retention_analysis` | 「每个标签一行」，用固定 marker（13.4/25.5） | 改变 `subject_definitions` 里已定的职责（25.5） |
| `detailed_description` | 主时间轴；「先用 1–2 句英文定义总体风格，再进入 `[Shot 1]`」（13.5） | 剧情梗概（25.1） |

### 1.6 顺序与长度建议（原文数值）

| 项 | 建议值 | 出处 |
|---|---|---|
| 单次输出时长 | 4–15 秒 | H3/MANUAL 3、22.3 |
| 帧率 / 音频 | 24 FPS / 32 kHz 立体声 | 同上 |
| Base 输出 | 以 768p 为主要基准 | 同上 |
| `overall_soundscape` | 1–4 个英文句子，单段连续文字 | 24.9 |
| `non_diegetic_music` | 1–3 个英文句子；无则 `N/A` | 24.10、5.3 |
| `detailed_description`（Ref2VA 生成类） | 「通常可写约 350–500 个英文单词」；对白密集任务优先满足完整时间轴，不必机械凑字数 | 13.5、25.6 |
| 镜头数量预算 | 单镜头＝产品动作/情绪表演/首尾帧过渡；2 个镜头最稳（建立—结果）；3 个镜头（建立—行动—反应）；**4 个以上容易出现身份漂移、空间断裂和声音拥挤** | 7.4 |
| 每镜头动作量 | 「每个镜头最好只有一个主要动作目标」 | 7.4 |
| 15 秒内的禁忌组合 | 「不要同时要求多个地点、复杂打斗、长对白和连续变装」 | 6.1 |
| 语言规则 | 「所有重写字段使用英文；仅对白、歌词和真正可见的文字保留原语言」 | 13、25.1 |

### 1.7 状态机结构（官方给出的四种模式骨架，原文照录）

```text
T2VA ：初始世界状态 → 动作触发 → 可见变化 → 结果或反应
I2VA ：首帧锚点 → 动作开始 → 连续发展 → 结果或反应
FL2VA：首帧状态 → 可观察中间变化 → 差异逐步缩小 → 命中尾帧状态
L2VA ：合理前态 → 明确动作路径 → 最后镜头逐步收敛 → 命中尾帧
```

配套原理（原文 14.3）：**状态守恒**——「每个镜头结束时都形成下一镜头的初始状态：`State(N, end) ≈ State(N+1, start)`」。

---

## 2. ★ H3 与 Seedance 的范式差异（本次最关键）

### 2.1 总对照表

| 维度 | Seedance 2.0 范式（我们之前用的） | MiniMax H3 官方范式 | 冲突等级 |
|---|---|---|---|
| 顶层结构 | 中文自由板式：首句「画面无任何字幕。」+【风格】【时间轴】【声音】【参考】【约束】【一致性】 | **固定英文字段**：Base 三段 / Ref2VA 六段，字段名与顺序不可自创 | 🔴 硬冲突 |
| 描述语言 | 中文正文 | 「Rewrite section 使用英文」；只有 `<d>` 内对白/歌词、画面可见文字保留原语言 | 🔴 硬冲突 |
| 分段方式 | `镜头1 / 镜头2 / 镜头3`（不写时间戳） | `[Shot 1]` 无时间戳；后续 `[Shot 2] At 00:05.000, the camera cuts to …` | 🔴 硬冲突 |
| 秒数 | 官方已修正为「模型对精确时间支持不稳定」，通用场景不写秒数，只写「快速/缓慢/随即/片刻后」 | **必须写**：切点用 `MM:SS.mmm`；FL2VA/L2VA 首行写 `S.SS`（两位小数） | 🔴 硬冲突 |
| 运镜写法 | 标准术语直接写（`缓慢推进`、`希区柯克变焦`、`机位高度 0.5 米`、`变焦速度每秒 4.5 米`） | `运动类型 + 幅度 + 速度` 三件套，**写成自然英文动作句**，禁止句尾堆标签 | 🟠 写法则不同 |
| 情绪/表演 | 拒绝情绪名词，拆成帧级「通道错开」：视线/眼睑 → 眉 → 嘴/下颌 → 呼吸 → 头 → 肩 → 手 → 声音 | 允许写情绪**状态**，但必须绑定「触发 → 可见变化 → 结果」，靠状态守恒跨镜衔接；无「通道错开」概念 | 🟠 方法论不同 |
| 台词 | `{}` 包裹，嵌进对应镜头；小语种标语种 | `<d>[Language] 台词原文</d>`，只出现一次，`<d>` 外写谁说/音色/情绪 | 🟠 写法不同 |
| 台词跨镜/截断 | 无对应机制 | 跨切用 `<scenetrans>`；片尾截断用 `<cutoff>` | 🟢 H3 独有 |
| 说话人 | 角色名 + 情绪 | 稳定 ID `(S1)`/`(S2)`/`(S1,S2)`，按**首次实际发声顺序**分配 | 🟢 H3 独有 |
| 旁白 | 一般写「旁白：…」 | 固定短语 `says in an off-screen voiceover` + 立刻写画面人物 `lips remain completely closed` | 🟢 H3 独有 |
| 声音分层 | 【声音】一块：配乐 + 音效 + 各角色声线 | 四层：对白→`<d>`；同步画内声→当前 Shot；环境/物理声→`overall_soundscape`；画外配乐→`non_diegetic_music`（无则 `N/A`） | 🔴 硬冲突 |
| 素材引用 | `@图片1` + 「参考图片1的脸和发型」+「不要参考视频1的人物外貌」 | `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` + `subject_definitions` 定职责 + `retention_analysis` 定保留关系 | 🔴 硬冲突 |
| 负向约束 | 有独立「禁指向」层（≤3–5 条），且靠删负面词改正向规避审核 | **没有定义 negative 开关**；「不要把 Prompt 负面句当成确定性屏蔽器」；正向写 + 生成后 QA | 🔴 硬冲突 |
| 一致性 | CHAR_A 锚点 + **双锚定**（每镜重嵌 Original Lock + Prev-shot Token） | 素材职责狭窄 + 同一描述短语 + 状态守恒句（「他仍站在桌右侧，穿同一件藏青衬衫」） | 🟠 机制不同 |
| 保底神词 | 「画面稳定 · 不闪烁 · 不重影 · 动作流畅自然 · 高清画质 · 电影质感」这类词「稍加几个就能上一个档次」 | 官方明确反对抽象词：「比起抽象词 `cinematic`、`beautiful`，优先写具体可视、可听事实」 | 🔴 硬冲突 |
| 时长档位 | 4–15s，优先 10s | 4–15s（官方）；消费级海螺入口二手资料写 6s/10s | 🟡 版本差异 |
| 参考上限 | 图片/视频/音频合计 12 个文件；视频≤3、音频总时长≤15s | 同量级：图片≤9；视频≤3（每段 2–15s，总≤15s）；音频≤3（每段 2–15s，总≤15s）；混合≤12；**音频不能作为唯一输入** | 🟢 基本一致 |
| 音频生成 | 原生音效/环境音/配乐 + 口型同步（沉浸式短片） | 原生 32kHz 立体声，联合生成 video latent + audio latent | 🟢 一致 |

### 2.2 逐条回答你点名的 7 个问题

**① H3 偏好长结构化还是短句凝练？**
→ **长结构化**，但是「字段化的结构化」，不是「关键词堆叠的长」。官方 Base 三段式本身就是骨架；`detailed_description` 官方给的量级是 **350–500 英文单词**（H3/MANUAL 13.5/25.6）。同时官方明确反对标签堆叠，原文不推荐写法：

```text
cinematic, push in, zoom, pan, orbit, handheld, fast, epic
```

推荐写法（原文）：

```text
The camera pushes in with small amplitude at slow speed toward the letter in her hands.
```

一句话：**结构要长（字段齐全、时间轴完整、状态写清），句子要具体（可看可听），词藻要短（不堆形容词）。** 我们过去那种「一段中文 × 三个镜头号」既没有 H3 要求的字段，也没有 H3 要求的具体事实，两头不靠。

**② 要不要写「镜头1/镜头2」这种时间轴分段？**
→ 要分段，但**换名字、换格式**：
- 第一段固定写 `[Shot 1]`，**不写时间戳**（官原文：`[Shot 1] Live-action, cinematic, a medium shot frames ...`）。
- 后续写 `[Shot 2] At 00:04.500, the camera cuts to ...`（原文 7.2），时间必须严格递增、小于总时长。
- 官方允许的切镜动词（原文 24.5）：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`；cross-dissolve、fade、wipe **只有用户明确要求时才用**。
- 但更重要的一条：**切镜必须带来新信息**（新主体/新空间/新状态/新视角/新时间阶段/关键反应）；「若只是从中景轻微变近，优先使用 `Push In` 或 `Zoom In`，不要浪费一个 Cut」（原文 7.3）。
→ 所以我们原来那种「同一个固定机位、同一个动作，被切成镜头 1/2/3 来分装微表情」在 H3 里是**多余的切镜**，应该合成一个 Shot，用状态推进句写完。

**③ 要不要写秒数？**
→ **要写，但只在两个地方**：
1. **切点**：`At 00:03.500`（`MM:SS.mmm`，必须严格递增、落在总时长内；Shot 1 不写）。
2. **首尾帧对齐**：FL2VA/L2VA 首行里的 `S.SS`，严格两位小数。
→ **不要写**「0-3秒/3-6秒」这种分段时长标注，也不要写「镜头 1 持续 2 秒」。总时长走生成参数；H3 正文里唯一的时间语言就是切点时间戳。这跟 Seedance「不写秒数」正好相反——这是我们必须改回来的地方。

**④ H3 对运镜词的偏好（哪些有效、哪些无效）**
有效（官方 12 类，配合幅度+速度）：
`Zoom In/Out`、`Push In/Pull Out`、`Pan Left/Right`、`Truck Left/Right`、`Tilt Up/Down`、`Pedestal Up/Down`、`Arc Shot`、`Tracking Shot`、`Static Shot`、`Shake Slightly/Strongly`、`POV`、`Roll Clockwise/Counterclockwise`；幅度 `with small amplitude`/`with large amplitude`；速度 `at slow speed`/`at fast speed`（中等幅度与正常速度通常省略）。
**必须写成自然动作句**，且**每个时间段只指定一个主运镜**。
无效 / 易翻车（原文 8.3 运镜冲突）：
- 同一时间既 `Static Shot` 又 `Tracking Shot`；
- 摄影机向左平移，同时要求主体固定画面最左，却没有补偿逻辑；
- 一秒内同时推、拉、摇、环绕、翻滚；
- 硬切后仍要求上一镜头连续的单一物理运镜。
- 句尾堆标签（`cinematic, push in, zoom, pan, orbit, handheld, fast, epic`）。
消费级海螺入口另有一套指令式运镜（二手资料 P/PLAT）：`[左移] [右移] [左摇] [右摇] [推进] [拉远] [上升] [下降] [上摇] [下摇] [变焦推近] [变焦拉远] [晃动] [跟随] [固定]`；同组 `[]` 内多指令，建议 ≤3，如 `[左摇,上升]`；顺序运镜用「然后」，如 `…[推进], 然后…[拉远]`；「自然语言也支持，但标准指令更准」。—— 注意这是二手平台资料，未见于官方 H3 文档；官方 H3 文档里没有方括号运镜标签的说法。

**⑤ H3 对情绪/表演的处理方式与 Seedance 有何不同？**
- Seedance：**禁止情绪名词**，必须拆成帧级可见动作，并按固定通道顺序错开几帧（视线→眉→嘴→呼吸→头→肩→手→声音）。
- H3：**不禁止情绪词**（官方 Ref2VA 案例里直接写 `Her annoyance softens as she looks toward the Samoyed`、`He closes his mouth into an apologetic smile`），但要求每个细节「能被观众看见或听见」，且整段必须构成状态变化（初始状态 → 动作触发 → 可见变化 → 结果或反应）。
- H3 真正的跨镜机制不是「通道错开」，而是**状态守恒**：`State(N, end) ≈ State(N+1, start)`，要变就得写出触发动作（原文 14.3）。
- 结论：**表演还是照我们那套写「先…随后…接着…」的动作链，但去掉「第几帧错开」的教条，补上因果与状态守恒**；允许在结尾加一句结果态（如 `His face settles back into its usual flat tiredness.`）来锁定余韵。

**⑥ H3 对台词 / 口型 / 音频的处理方式？**
- 说话人：所有真实发声主体用稳定 ID `(S1)`；多人同时 `(S1,S2)`；**按目标视频中第一次实际发声的顺序分配**，并在所有镜头复用；不发声的角色不分配 ID（10.1）。
- 台词：只写在 `<d>[Language] …</d>` 内。中文写法原文：`The calm young man (S1) says: <d>[Chinese] 我们现在出发。</d>`。
  `<d>` 外写：谁说、音色、年龄感、语速、情绪、动作和表情；`<d>` 内只写 `[Language]` + 完整台词。「用户原词与标点必须逐字保留，不翻译、不改写」。
- 旁白：必须用 `says in an off-screen voiceover`，并紧随写明画面人物嘴唇闭合：
  `The man (S1) says in an off-screen voiceover: <d>[Chinese] 我仍然记得那条路。</d> while his lips remain completely closed.`
- 跨切：同一句跨 Cut 用 `<scenetrans>`，并写声音无缝延续（`continues seamlessly across the cut` 等），**不要在两个镜头各复制一遍完整台词，否则可能读两遍**。片尾截断用 `<cutoff>`。
- 口型稳定工程建议（10.6）：一段 15 秒里尽量少换说话人；一镜只让一个主体承担主要台词；台词期间不要同时要求高速跑动/遮脸/转身/大幅运镜；台词结束后明确 `closes his mouth naturally`；旁白场景锁住画面角色嘴唇。
- 音频分四层（12.1 原文表）：

| 声音 | 放置位置 | 示例 |
|---|---|---|
| 对白、歌唱 | 当前 Shot 的 `<d>` | 角色说话、旁白、歌词 |
| 同步画内声音 | 当前 Shot | 按钮点击、门铃、枪声、收音机 |
| 全片环境与物理声 | `overall_soundscape` | 雨声、风声、脚步、衣料 |
| 观众专属配乐 | `non_diegetic_music` | 钢琴、弦乐、鼓点 |

- 画内 vs 画外（12.2）：角色能听到的收音机、演奏、手机音乐属于**画内事件**，写在 Shot 中；只有观众听到的配乐写在 `non_diegetic_music`。
- 避免重复（12.3）：完整台词和歌词只在 `<d>` 中写一次，不在 `overall_soundscape`、`non_diegetic_music`、说明段或另一个 Shot 复制。
- 音色跨片段一致性优先级（12.4 原文）：① Ref2VA 用相同 `<Audio N>` 音色参考 → ② 固定说话人描述和 `(Sx)` → ③ 固定语言/性别/年龄感/音高/语速/口音/情绪基线 → ④ 每段避免突然改变录音环境和混响 → ⑤ 发布前做响度、底噪和声线一致性检查。
- 与我们流水线的对接：LingCut 里「MiniMax 生成配音 → 上传 → 建音频节点 → 连到视频节点」这套依然成立，但**在 H3 提示词里的表达方式变了**——音频节点对应 `<Audio N>`，写成 `<Audio 1> is the voice-timbre reference for <Subject 1> (S1).`，而不是 `【参考】@音频1 锁音色`（详见第 9 节）。

**⑦ H3 专属「魔法词」与禁忌词（原文列出）**

**魔法词（照抄即生效的固定 token / 句式）**

| 类别 | 原文 token / 句式 | 出处 |
|---|---|---|
| 字段名 | `integrated_multimodal_description:` / `overall_soundscape:` / `non_diegetic_music:` | 5、24.2 |
| 六段字段名 | `subject_definitions:` / `summary:` / `retention_analysis:` / `detailed_description:` | 13、25.2 |
| 镜头 | `[Shot 1]`（无时间戳）；`[Shot N] At 00:SS.mmm,` | 7.1、7.2 |
| 切镜 | `the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to` | 24.5 |
| 台词 | `<d>[Chinese] …</d>` / `<d>[English] …</d>` | 10.2 |
| 说话人 | `(S1)` / `(S2)` / `(S1,S2)` | 10.1 |
| 旁白 | `says in an off-screen voiceover` + `while his lips remain completely closed` | 10.3、24.7 |
| 跨切 / 截断 | `<scenetrans>` / `<cutoff>` | 10.4、10.5 |
| 参考标签 | `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` | 13.1、25.3 |
| 保留标记（视觉） | `fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference` | 13.4、25.5 |
| 保留标记（音频） | `fully_copy` / `partially_copy` / `reference` / `weak_reference` | 13.4、25.5 |
| 任务类型前缀 | `[keyframe completion]` / `[reference generation]` / `[video editing]` / `[video continuation]` / `[audio reuse]` / `[audio reference]`，用 ` + ` 合并 | 13.3、25.4 |
| 空配乐 | `non_diegetic_music: N/A` | 5.3 |
| 视频编辑固定句 | `The target video is an edited version of <Video 1>.` | 25.4 |
| 首尾帧对齐句 | `the shot begins from <Picture 1>` / `the shot's keyframe corresponds to <Picture 2>` / `the shot ends on <Picture 3>` | 25.7 |
| 运镜句模板 | `The camera pushes in with small amplitude at slow speed toward …` | 8.2、24.6 |
| 状态守恒句 | `He remains on the right side of the desk, wearing the same navy shirt; …` | 9.2 |
| 风格词（官方列举） | `Cinematic` / `live-action` / `2D-animated` / `3D CG` / `claymation` / `watercolor` / `vintage film` | 24.4 |
| 画面文字 | 用英文双引号包住可见文字：`A red neon sign reading "营业中" glows above the doorway.` | 11.1、24.8 |

**禁忌词 / 禁忌写法（原文明确点名）**

| 禁忌 | 原文依据 |
|---|---|
| 句尾堆运镜标签：`cinematic, push in, zoom, pan, orbit, handheld, fast, epic` | 8.2 不推荐 |
| 只写 `epic`、`emotional`、`beautiful` 当配乐描述 | 5.3 |
| 口号式一致性：`Keep everything consistent.` | 9.2 弱写法 |
| 用抽象词代替具体事实：官方点名 `cinematic`、`beautiful` | 23.4 官方效果建议 |
| 把表演说明塞进 `<d>`：「轻声地、悲伤地、用低沉男声」 | 10.2 |
| 同一句台词在多个区块/镜头重复（会读两遍） | 12.3、16 |
| 把台词当可见文字写进画面（会生成字幕） | 11.3、16 |
| 把负面句当屏蔽器（H3 无独立 negative conditioning） | 11.3 |
| Shot 1 写时间戳（`From 00:00.000 to 00:05.000`） | 7.1 不推荐 |
| 只写「综合所有参考」让模型自己决定 | 13.6 |
| 用同义词反复换同一人物的形容词 | 9.1（「同义词对人类相近，对模型可能意味着重新采样身份」） |
| 15 秒内同时要多地点、复杂打斗、长对白、连续变装 | 6.1 |
| 让模型生成长而小的文字（招牌、字幕） | 11.2、16 |
| 抽象愿望 / 验收口号混入正文 | 5.1 |

---

## 3. H3 提示词模板（原文全部照录，注明适用场景）

### 3.1 T2VA 模板（H3/MANUAL 15.1）— 适用：无任何参考素材，纯文本建片

```text
integrated_multimodal_description: [Shot 1] [Style], [initial composition]. [Subject identity, position, environment, lighting]. [Primary action]. [Speaker description] (S1) says: <d>[Language] Exact dialogue.</d> [Reaction and state change].
[Shot 2] At 00:SS.mmm, the camera cuts to [new information]. [Action, camera, synchronized sound, result].

overall_soundscape: [Ambient baseline]. [Physical and non-verbal sounds across the video].

non_diegetic_music: [Instrumentation, tempo, rhythm, dynamic development] / N/A
```

### 3.2 I2VA 模板（15.2）— 适用：分镜图/角色首帧作为 0.00 秒真实首帧

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] [Style], the subject shown in <Picture 1> remains in the same opening composition, preserving [identity, clothing, pose, objects, spatial layout]. [Observable motion begins]. [Continuous development]. [Result or reaction].

overall_soundscape: ...

non_diegetic_music: ...
```

### 3.3 FL2VA 模板（15.3）— 适用：两张图锁头尾（开门、合伞、转身、坐下、递物、表情转变、灯光日夜过渡、产品开合）

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the SS.SS-second mark of the target video.

integrated_multimodal_description: [Shot 1] [Style], the shot begins in the exact state and composition established by Picture 1. [Step-by-step physical path]. [Intermediate visible changes]. The motion gradually settles into the pose, object state, lighting, spacing, and final composition established by Picture 2.

overall_soundscape: ...

non_diegetic_music: ...
```

### 3.4 L2VA 模板（15.4）— 适用：片尾定格、产品最终姿态、角色最后站位、Ending Card 前的动作收束

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the SS.SS-second mark of the target video.

integrated_multimodal_description: [Shot 1] [Style], [plausible earlier state compatible with Picture 1]. [Action path]. [Shot N] At 00:SS.mmm, [final convergence]. The subject and scene settle into the exact final pose, geometry, lighting, and composition established by <Picture 1>.

overall_soundscape: ...

non_diegetic_music: ...
```

### 3.5 Ref2VA 骨架（15.5）— 适用：多图角色 / 参考视频运镜 / 音色参考 / 编辑续写（**我们流水线最该用的一个**）

```text
subject_definitions:
<Subject 1> is ... from <Picture 1>, providing ...
<Subject 2> is ... from <Video 1>, providing ...
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary:
[reference generation + audio reference] The target video ...

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - ...
<Subject 2> (appears in [Shot 1]): weak_reference - ...
<Audio 1>: reference - ...

detailed_description:
The target video uses ...
[Shot 1] ...
[Shot 2] At 00:SS.mmm, ...

overall_soundscape:
...

non_diegetic_music:
...
```

### 3.6 中文对白示例（15.6）— 适用：中文台词 / 旁白

```text
A calm adult Mandarin narrator with a warm, measured delivery (S1) says in an off-screen voiceover: <d>[Chinese] 今天，我们从这里出发。</d> while the on-screen character's lips remain completely closed.
```

### 3.7 模式与基本信息的输出骨架（19 章「默认输出格式」原文）— 适用：交付给别人看/存档

````text
推荐模式：I2VA
时长：15 秒
画幅：16:9
参考关系：Picture 1 = 首帧与人物/场景锚点

最终 H3 Prompt：
```text
...
```

检查结果：
- 时间轴通过
- 说话人 ID 通过
- 音频分层通过
- 关键帧标签通过
````

### 3.8 官方给出的「风格词」清单（应用到 `[Shot 1]` 开头，24.4）

`Cinematic`、`live-action`、`2D-animated`、`3D CG`、`claymation`、`watercolor`、`vintage film`
原文示例：`[Shot 1] Live-action, cinematic, a medium-wide shot frames...`

### 3.9 时间轴先行草稿模板（3 Step 3 原文）— 适用：写 Prompt 之前先排节奏

```text
0.0–4.5 秒：建立人物和问题
4.5–10.0 秒：执行核心动作
10.0–15.0 秒：结果、反应和结尾锚点
```

补每一段时要写（原文）：当前景别和构图 / 主体位置与朝向 / 动作起点和终点 / 摄影机运动 / 同步声音 / 台词和口型 / 需要保持的状态。

### 3.10 素材角色表模板（Step 2 原文）— 适用：多参考素材防串味

| 素材 | 角色 | 允许继承 | 不应继承 |
|---|---|---|---|
| Picture 1 | 主角身份 | 脸、发型、服装、比例 | 背景文字、平台水印 |
| Picture 2 | 场景参考 | 建筑、布局、色彩 | 图片中的路人身份 |
| Video 1 | 运镜参考 | 镜头路径、剪辑节奏 | 原视频人物和品牌 |
| Audio 1 | 音色参考 | 音色、语速、情绪 | 原台词内容 |

### 3.11 客户侧质量门槛（13.5/25.6 原文数值，用于自查篇幅）

- 全参考生成任务的 `detailed_description` 通常 **350–500 个英文单词**；对白密集任务优先保证完整口播时间线，不机械追字数；视频编辑描述按源视频复杂度伸缩。
- **单镜头不等于描述可以很短**，应按信息负载分配细节。

---

## 4. 运镜与运动词表

### 4.1 H3 官方运镜：类型 + 幅度 + 速度（24.6 原文表，英文照录）

| 维度 | 官方表达 | 含义 |
|---|---|---|
| 类型 | `Zoom In / Zoom Out` | 机位不动，改变焦距 |
| 类型 | `Push In / Pull Out` | 相机前移 / 后移 |
| 类型 | `Pan Left / Pan Right` | 机位不动，镜头水平转动 |
| 类型 | `Truck Left / Truck Right` | 相机横向平移 |
| 类型 | `Tilt Up / Tilt Down` | 机位不动，镜头垂直转动 |
| 类型 | `Pedestal Up / Pedestal Down` | 整台相机上移 / 下移 |
| 类型 | `Arc Shot` | 围绕主体做弧线运动 |
| 类型 | `Tracking Shot` | 跟随移动主体 |
| 类型 | `Static Shot` | 机位与镜头保持静止 |
| 类型 | `Shake Slightly / Shake Strongly` | 轻微 / 强烈震动 |
| 类型 | `POV` | 主体主观视角 |
| 类型 | `Roll Clockwise / Roll Counterclockwise` | 围绕镜头轴顺 / 逆时针滚转 |
| 幅度 | `with small amplitude` | 小范围构图变化 |
| 幅度 | `with large amplitude` | 大范围构图变化 |
| 速度 | `at slow speed` | 慢速 |
| 速度 | `at fast speed` | 快速 |

> 原文注：**中等幅度和正常速度通常省略**；运镜要写成 shot 内自然英文动作，不要在句尾堆标签。

官方示范句（24.6 原文）：

```text
The camera pushes in with small amplitude at slow speed toward the folded letter in her hands.
The camera pans right with large amplitude at fast speed, revealing the open doorway.
The camera holds a static shot as the runner exits the frame.
```

用途归类（H3/MANUAL 8.1 原文「适用场景」列）：

| 官方词 | 适用场景（原文） |
|---|---|
| `Zoom In / Zoom Out` | 强调细节、制造压缩感 |
| `Push In / Pull Out` | 情绪推进、揭示空间 |
| `Pan Left / Pan Right` | 跟随横向信息 |
| `Truck Left / Truck Right` | 保持距离的横向运动 |
| `Tilt Up / Tilt Down` | 从脚到脸、从地面到天空 |
| `Pedestal Up / Down` | 高度变化、空间揭示 |
| `Arc Shot` | 英雄展示、关系变化 |
| `Tracking Shot` | 行走、奔跑、追逐 |
| `Static Shot` | 数字人、产品、稳定对白 |
| `Shake Slightly / Strongly` | 冲击、灾难、主观紧张 |
| `POV` | 代入、扫描、观察 |
| `Roll Clockwise / Counterclockwise` | 失衡、梦境、转场 |

### 4.2 H3 特别擅长 / 特别不擅长（原文归类）

**擅长**
- 「静态机位 + 焦点转移」叙事：官方 I2VA 案例「固定机位 8 秒，不靠移动摄影，而是用焦点转移制造叙事……焦点平滑转到家人，蒸汽持续作为前景动态层」（22.11）。
- 单一主运镜 + 明确幅度/速度（8.2、8.3）。
- 情绪表演类单镜头与首尾帧过渡（7.4）。

**不擅长 / 高风险**
- 运镜冲突四类（8.3，见 2.2 ④）。
- 4 个以上镜头（易身份漂移、空间断裂、声音拥挤，7.4）。
- 15 秒内多地点 + 复杂打斗 + 长对白 + 连续变装（6.1）。
- 硬切后仍要求上一镜头连续的单物理运镜（8.3）。

### 4.3 消费级海螺入口的指令式运镜（二手资料 P/PLAT，非官方 H3 文档）

指令全集（原文）：`[左移] [右移] [左摇] [右摇] [推进] [拉远] [上升] [下降] [上摇] [下摇] [变焦推近] [变焦拉远] [晃动] [跟随] [固定]`
用法（原文）：
- 组合运镜：同组 `[]` 内多指令（建议 ≤3），如 `[左摇,上升]`；
- 顺序运镜用「然后」，如 `…[推进], 然后…[拉远]`；
- 「自然语言：也支持，但标准指令更准」；
- 规格（二手）：768P/1080P，6s/10s；「擅情感表达、人物微表情、画面连贯」。

### 4.4 运镜意图 → 各平台原生控件映射（P/PLAT 第三节原文表）

| 运动意图 | 可灵 Kling | 海螺 Hailuo | 即梦 Jimeng | Runway | Veo / Sora |
|---|---|---|---|---|---|
| 推近 dolly in | Zoom 负值 / prompt "push in" | `[推进]` | "镜头前推" | Motion Brush / preset | "dolly in" / "push in" |
| 拉远 pull out | Zoom 正值 / "pull back" | `[拉远]` | "镜头后拉" | preset | "pull back" |
| 左摇 pan left | Pan 负值 | `[左摇]` | "镜头左摇" | preset | "pan left" |
| 右摇 pan right | Pan 正值 | `[右摇]` | "镜头右摇" | preset | "pan right" |
| 上升 crane up | Vertical 正值 / "rise" | `[上升]` | "镜头上升" | "crane up" | "crane shot up" |
| 下降 crane down | Vertical 负值 | `[下降]` | "镜头下降" | "crane down" | "crane shot down" |
| 环绕 orbit | prompt "orbit shot" | `[跟随]`+自然语言 | "环绕拍摄" | "orbit" preset | "orbit shot" |
| 手持晃动 handheld | prompt "handheld, slight shake" | `[晃动]` | "手持晃动" | preset | "handheld" |
| 固定锁定 static | prompt "static camera" | `[固定]` | "固定镜头" | preset | "locked-off shot" |
| 局部运动 localized | **Motion Brush** | 暂主要靠 prompt | 图生局部 | **Motion Brush** | prompt 描述局部 |

### 4.5 通用运动设计词表（P/DIM 「★ 运动设计维度」，一等维度）

**A. 运镜 Camera Movement（原文中英对照）**
`static 固定机位`（Portraits / 产品 / 对话，稳定不晃）、`pan 摇`（revealing landscape / following action）、`tilt 俯仰`（revealing height / dramatic reveal）、`dolly in/out 推拉`（building tension / establishing）、`tracking 跟拍`（action / walking）、`orbit 环绕`（product showcase / hero moment）、`crane/boom 升降`（establishing / dramatic reveal）、`handheld 手持`（documentary / urgency / intimacy）、`zoom 变焦`（dramatic emphasis）、`FPV 第一人称`（flying through，action / exploration / immersive）、`whip pan 快摇`（快速甩动转场）

**B. 时序 Timing**
`real-time 实时`、`slow-mo 慢动作`（强调细节/情绪，"放慢至1/6"）、`time-lapse 延时`（云/人流/生长）、`speed-ramp 速度渐变`（从慢到快/快到慢）、`freeze 定格`

**C. 主体运动 Subject Motion**
幅度：`still / small / large / extreme`；速率：`slowly / rapidly / fluidly`；方向/类型：`walk / rotate / flow / fall / interact / spin`；物理属性：`gravity-affected smoke / wind-blown flames / upward spiraling`

**D. 物理与连续 Physics & Continuity**
重力/流体/布料/毛发/火焰的真实感；连续感：`frame-to-frame stability`，避免 `flicker / morph / jitter`

### 4.6 状态动词（H3 官方对象状态机，9.3 原文）— 复杂物理动作必须拆成的写法

```text
门关闭 → 手接近把手 → 手掌握住把手 → 铰链方向旋转 → 门完全打开 → 手松开
```

原文说明：这样比「人物自然打开冰箱门」更容易避免穿模、反向开门和手穿过门板。失败修正里的对应话术是「把动作拆为接近、接触、施力、运动、停止」（16）。

### 4.7 摄影机之外的「切换」词（24.5 原文）

普通切镜：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`
仅在用户明确要求时使用：cross-dissolve、fade、wipe。

### 4.8 电商运镜预设（W/CAM 原文，非 H3 官方词，但可套进 `Static Shot`/`Arc Shot` 等官方句里）

| 预设名 | 中文名 | prompt_en（原文照录） |
|---|---|---|
| orbit_360 | 360° 环绕 | `slow 360 degree orbit around the product, smooth circular camera movement, product stays centered` |
| slow_push_detail | 慢推细节 | `slow cinematic push-in from medium shot to extreme close-up on product detail, smooth dolly movement` |
| lifestyle_handheld | 生活感手持 | `slight handheld camera movement, natural lifestyle feel, authentic documentary style, soft natural light` |
| product_fly_in | 产品飞入 | `product flying into frame from the side and settling in the center, dynamic but controlled motion, clean background` |
| top_down_reveal | 俯拍揭示 | `top-down bird eye view, slow downward camera movement revealing the product, elegant reveal` |
| side_profile_pan | 侧面平移 | `side profile tracking shot, smooth horizontal pan along the product silhouette, elegant lines` |
| macro_texture | 微距质感 | `extreme macro close-up, focusing on material texture and craftsmanship details, shallow depth of field` |
| before_after_slide | 前后对比 | `before and after comparison, smooth slide transition between two states of the product usage` |
| orbit_with_light | 光影环绕 | `360 orbit combined with moving light reflections on the product surface, premium commercial look` |
| pull_back_reveal | 后拉揭示 | `slow pull-back from close-up detail to full product reveal, cinematic reveal movement` |

平台顺序建议（W/PIPE、W/PROD 原文）：小红书 `lifestyle_handheld` → `slow_push_detail` → `macro_texture` → `orbit_360`；抖音 `product_fly_in` → `orbit_360` → `slow_push_detail` → `before_after_slide`。

---

## 5. 可直接抄用的完整范例（原文照录，未改写）

### 范例 1 ｜ T2VA 面包店（官方 Base Guide Case 1，H3/MANUAL 24.11）

- **场景类型**：文生音视频 / 无任何素材 / 双镜头「建立—结果」
- **亮点**：`[Shot 1]` 无时间戳；切点精确到毫秒 `At 00:05.000`；台词放在 `<d>` 内一次；用 `carry over from the previous shot` 处理跨切台词；配乐写乐器 + 速度 + 收尾。

```text
integrated_multimodal_description: [Shot 1] Live-action, cinematic, a medium-wide shot frames a baker opening the shutters of a small street bakery before sunrise. The camera pushes in with small amplitude at slow speed as the middle-aged baker with a calm, slightly raspy voice (S1) places a fresh loaf on the wooden counter and says: <d>[English] First batch of the morning.</d> [Shot 2] At 00:05.000, the camera cuts to a close-up of steam rising from the sliced bread while the baker's final words carry over from the previous shot.

overall_soundscape: Wooden shutters scrape open over a quiet street as trays clink softly inside the bakery. The doorbell rings once, followed by light footsteps and the crisp sound of bread being sliced.

non_diegetic_music: A soft acoustic-guitar pattern at a moderate tempo, joined by sparse upright-bass notes and a gentle fade at the end.
```

### 范例 2 ｜ I2VA 雨夜列车（官方 Case 2）

- **场景类型**：首帧图生音视频 / 人物情绪 + 台词
- **亮点**：官方固定首行 + 空行；先声明保留项（appearance, clothing, seat position, carriage layout）；运镜写成自然句 `trucks right with small amplitude at slow speed`；台词后用动作收束（`folds the letter along its existing crease`）。

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the young woman shown in <Picture 1> remains beside the rain-covered train window, preserving her appearance, clothing, seat position, and the carriage layout. The camera trucks right with small amplitude at slow speed as she lifts her gaze from the folded letter toward the passing city lights. Her reflection moves across the glass while the quiet, breathy young woman (S1) says: <d>[English] I get off at the next station.</d> She folds the letter along its existing crease.

overall_soundscape: The train wheels produce a steady metallic rhythm beneath a low ventilation hum. Rain ticks against the window while paper rustles softly in her hands.

non_diegetic_music: Sustained cello notes at a slow tempo with widely spaced piano tones, gradually decreasing in volume.
```

### 范例 3 ｜ FL2VA 雨中自行车与雨伞（官方 Case 3）

- **场景类型**：首尾帧插值 / 单镜头物理动作路径
- **亮点**：官方对齐句写 `S.SS`（这里 8.00）；动作被拆成可执行物理步骤（松手 → 举伞 → 推伞箍 → 伞面张开 → 迈步进入 → 转手柄 → 命中尾帧构图）；无配乐写 `N/A`。

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 8.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, a rain-soaked cyclist begins in the position and framing established by Picture 1, holding a closed black umbrella beside a silver bicycle. The camera pulls out with small amplitude at slow speed as she releases the bicycle handle, raises the umbrella above her shoulder, and presses the runner upward until the canopy opens. Water rolls from the expanding fabric while she steps beneath it, rotates the handle into the final angle, and settles into the pose, spacing, and composition established by Picture 2 at the end of the shot.

overall_soundscape: Rain falls steadily on the pavement, followed by the metallic click of the umbrella runner and the soft snap of the canopy opening. Water drips from the bicycle frame as distant traffic passes.

non_diegetic_music: N/A
```

### 范例 4 ｜ L2VA 玻璃杯破碎并落到尾帧（官方 Case 4）

- **场景类型**：尾帧收敛 / 快动作 + 结果定格
- **亮点**：先给「合理前态」（完好玻璃杯 + 同一只手从右侧接近）；撞击与碎片运动写清；最后一句专门写收敛（`lose momentum and settle into the exact broken arrangement…`）；配乐给了退出时机。

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot 1]) aligns with the 6.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, a close shot begins with an intact drinking glass near the edge of a dark wooden table, while the same hand and sleeve visible in <Picture 1> approach from the right. The camera pushes in with small amplitude at slow speed as the fingertips strike the rim. The glass tips, falls, and hits the floor with a sharp impact; cracks spread through it as fragments slide outward. Toward the end, the moving pieces lose momentum and settle into the exact broken arrangement, hand position, camera angle, lighting, and final composition established by <Picture 1>.

overall_soundscape: Fingertips tap the glass before it scrapes across the tabletop, falls, and breaks with a sharp crash. Small fragments scatter and gradually stop sliding across the floor.

non_diegetic_music: A low electronic pulse at a slow tempo, ending immediately after the glass breaks.
```

### 范例 5 ｜ Ref2VA 咖啡店 · 白色萨摩耶（官方完整六段式案例，H3/MANUAL 25.10）

- **场景类型**：全参考（场景图 + 动物图 + 两段人物视频 + 音色音频）/ 三镜头对话喜剧
- **亮点**：六段齐全；`(S1)`/`(S2)` 按首次发声顺序；音色参考写成 `<Audio 1>: reference`；画内「罐头笑声」写在 Shot 3 而不是 `non_diegetic_music`；每次台词后都写嘴唇闭合与后续动作。

```text
subject_definitions:
<Subject 1> is the coffee-shop environment in <Picture 1>, featuring an exposed brick wall, an orange tufted sofa with patterned pillows, a neon sign, and a wooden coffee table.
<Subject 2> is the fluffy white Samoyed in <Picture 2>, <Picture 3>, and <Picture 4>, with thick white fur, pointed ears, a dark nose, and a curved tail.
<Subject 3> is the young blonde woman in <Video 1>, with long blonde hair and a light-pink button-down shirt with rolled-up sleeves.
<Subject 4> is the young man in <Video 2>, with short wavy brown hair and a dark-grey hoodie with drawstrings.
<Audio 1> is the voice-timbre reference for <Subject 3> (S1), containing a spoken English vocal layer.

summary:
[reference generation + audio reference] The target video shows <Subject 3> eating a cookie in <Subject 1>. <Subject 4> enters with <Subject 2>, which lunges toward the cookie. The three-shot exchange uses <Audio 1> as the voice-timbre reference for <Subject 3> and ends with a canned audience laugh.

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2], [Shot 3]): fully_preserved - the exposed brick wall, orange tufted sofa, patterned pillows, neon sign, and wooden coffee table are retained.
<Subject 2> (appears in [Shot 1], [Shot 2]): fully_preserved - the Samoyed's thick white fur, pointed ears, dark nose, and curved tail are retained.
<Subject 3> (appears in [Shot 1], [Shot 2], [Shot 3]): fully_preserved - the blonde woman's identity, long hair, and light-pink shirt are retained.
<Subject 4> (appears in [Shot 1], [Shot 2]): fully_preserved - the young man's short wavy brown hair and dark-grey hoodie are retained.
<Audio 1>: reference - its vocal timbre guides the dialogue delivery of <Subject 3> without copying the original signal.

detailed_description:
The target video uses a realistic multi-camera sitcom style with warm indoor lighting.
[Shot 1] A medium shot establishes <Subject 1>, the coffee shop with its exposed brick wall, orange tufted sofa, patterned pillows, neon sign, and wooden coffee table. <Subject 3> (S1), the young woman with long blonde hair and a light-pink button-down shirt with rolled-up sleeves, sits on the sofa holding a chocolate-chip cookie. From the left, <Subject 4>, the young man with short wavy brown hair and a dark-grey hoodie with drawstrings, enters holding the leash of <Subject 2>, the thick-furred white Samoyed with pointed ears, a dark nose, and a curved tail. The dog lunges toward the cookie and pulls the leash taut. <Subject 3> (S1) jerks her hand back and, using the clear youthful voice timbre referenced from <Audio 1>, exclaims with light annoyance, <d>[English] Hey! Watch your dog!</d> She closes her lips and guards the cookie while <Subject 4> pulls the dog back.
[Shot 2] At 00:03.000, the shot cuts to a close-up of <Subject 4> (S2), the young man in the dark-grey hoodie from Shot 1, sitting beside <Subject 3> on the sofa and holding <Subject 2> securely in his arms. <Subject 4> (S2) says in a casual young male voice with a playful tone and an easy conversational pace, <d>[English] He just likes cookies more than me.</d> He closes his mouth into an apologetic smile and strokes the dog's thick white fur.
[Shot 3] At 00:05.000, the shot cuts to a close-up of <Subject 3> (S1), the blonde woman in the light-pink shirt from Shot 1. Her annoyance softens as she looks toward the Samoyed. <Subject 3> (S1) replies in the same clear youthful voice referenced from <Audio 1> with an amused cadence, <d>[English] Well, he has good taste at least.</d> She smiles and raises the cookie in a small toast-like gesture. A classic canned audience laugh begins immediately after the line and continues through the final frame.

overall_soundscape:
Soft indoor coffee-shop room tone continues throughout the scene.

non_diegetic_music:
N/A
```

### 范例 6 ｜ 中文旁白官方句式（H3/MANUAL 15.6 / 24.7）

- **场景类型**：中文旁白 + 画面人物不说话
- **亮点**：`says in an off-screen voiceover` 是硬句式；后半句必须锁嘴；`<d>` 内只有语言标签和原台词。

```text
A calm adult Mandarin narrator with a warm, measured delivery (S1) says in an off-screen voiceover: <d>[Chinese] 今天，我们从这里出发。</d> while the on-screen character's lips remain completely closed.
```

### 范例 7 ｜ T2VA 星舰舰桥（官方 Context-IR 案例语义，H3/MANUAL 22.11）

- **场景类型**：科幻双镜 / 文生音视频，10 秒 16:9
- **说明**：官方 README 给的是这段案例的**语义描述**（不是完整 prompt 原文），照录如下，用于学习官方 Context-IR 会补出哪些层。
- **亮点**：`Shot 1` 缓慢推进建立；`Shot 2` 在 `00:04.500` 切脸部特写 + 强烈震动；结尾用「闭眼」形成完整状态变化。

```text
Shot 1 从舰桥中景缓慢推进，女舰长背对镜头观察暗灰舰队；推进器蓝光增强。Shot 2 在 00:04.500 切脸部特写并强烈震动，跃迁白光、舰体应力声、舰长踉跄与最后闭眼形成完整状态变化。
```

### 范例 8 ｜ I2VA 日式家庭餐桌拉面（官方 Context-IR 案例语义，22.11）

- **场景类型**：首帧图生音视频，8 秒，静态机位
- **亮点**：**不靠移动摄影，用焦点转移制造叙事**；蒸汽作为持续的前景动态层。

```text
固定机位 8 秒，不靠移动摄影，而是用焦点转移制造叙事。开始拉面、叉烧、葱、海苔、筷子、茶杯清晰，七人家庭虚化；随后焦点平滑转到家人，蒸汽持续作为前景动态层。
```

### 范例 9 ｜ Ref2VA 视频 + 音频全参考（官方案例语义，22.11）

- **场景类型**：视频 + 音轨全参考，5 秒
- **亮点**：人物、原视频、同步 BGM、声音音色分别定义；对白结束时明确嘴唇闭合，并继续抚摸小羊。

```text
粉色西装男子抱黑色小羊；保留原视频与 BGM，参考另一音频的男声音色生成新对白。使用 subject_definitions → summary → retention_analysis → detailed_description → overall_soundscape → non_diegetic_music。人物、原视频、同步 BGM、声音音色分别定义；对白结束时明确嘴唇闭合，并继续抚摸小羊。
```

### 范例 10 ｜ 赛博朋克雨夜街道（P/EX 端到端样例，还原版 + 惊艳增强版）

- **场景类型**：10 秒竖屏 9:16 街拍跟拍
- **亮点**：还原版中英各给一版（事实层）；增强版是英文正文 + 负向串（这是**图/多平台通用范式**，落在 H3 上时须按第 9 节改造：负向串在 H3 无独立字段，只能正向化）。

```text
中文：夜晚雨后的赛博朋克街道，穿黑色长风衣的人物从画面左侧走向右侧、经过霓虹招牌，镜头缓慢向右摇移跟拍，湿地面有霓虹倒影，人物走入巷子后出画。9:16 竖屏，约 10 秒。

EN: Night, rain-soaked cyberpunk street after rain. A figure in a long black trench coat walks from left to right past neon signs. Camera slowly pans right, tracking the figure. Wet pavement reflects neon. The figure turns into an alley and exits frame. Vertical 9:16, ~10s.
```

```text
Cinematic cyberpunk tracking shot: a lone figure in a long black trench coat strides through a rain-slicked neon alley, magenta-cyan volumetric fog, glowing rim light, wet street reflections, slow right pan, shallow depth of field, anamorphic lens flare, teal-and-orange color grade, 24fps film look, subtle film grain. Smooth camera movement, stable continuity, realistic physics.
— no morphing, no flickering, no extra limbs, no identity drift, no text drift, no warping.
```

### 范例 11 ｜ 电商竖屏镜头提示词格式（W/PROD 原文模板）

- **场景类型**：9:16 电商产品镜头（可喂 Kling/Wan/MiniMax）
- **亮点**：格式里把「运镜英文描述 + 风格 + 画幅 + 商业摄影」固定成槽位；小红书/抖音各加一句平台风格词。

```text
A high-quality product video shot of [商品], [画面描述], [运镜英文描述], [风格], professional lighting, sharp focus, 9:16 vertical, commercial product photography style
```

小红书额外加：`natural daylight, lifestyle aesthetic, authentic feel`
抖音额外加：`dynamic commercial style, high contrast, attention-grabbing`
（出处：W/PROD「C. 每个镜头的视频生成提示词」原文）

### 范例 12 ｜ 单主体资产锁定 prompt（C/PROMPTS 01 原文，图像资产）

- **场景类型**：角色/道具**生图** prompt（不是 H3 视频 prompt）
- **亮点**：`exactly one` / `exactly three` / `no extra X` 的清单式锁量写法，可直接搬进 H3 的 `<Subject N>` 定义句与我们的生图阶段；这条是 12 条里首次通过的主要要求之一。

```text
Use case: stylized-concept. Asset type: single character reference image. Create exactly one original clay stop-motion fox postman, full body strict left side profile, facing left, on a seamless pale beige background. The fox has a compact ochre-orange clay body, cream muzzle, a wide heavy tail, and a small triangular notch missing from the left ear. It wears a short deep navy coat with exactly one round brass button on the chest and carries one worn brown mail satchel across the back; the strap presses naturally into the coat and the bag has believable weight. Preserve the strict side silhouette: do not turn the face or torso toward camera. Both feet touch the floor with a soft contact shadow; leave breathing room in front of the nose and behind the tail. Large soft light from upper left, matte clay with subtle hand-pressed irregularities, cloth and leather still interpreted as crafted clay with different surface response. Single image only, no grid, no alternate views, no extra buttons, badges, hat, letters, extra characters, text, logo, watermark, photoreal fur, glossy vinyl, duplicate limbs or duplicate tail.
```

---

## 6. 失败模式与修正

### 6.1 官方失败修正表（H3/MANUAL 16 原文照录 + 补我们的实际症状）

| 问题 | 常见原因 | 修正方向 |
|---|---|---|
| 人脸漂移 | 多个参考职责重叠；角色描述变化；镜头过多 | 缩窄参考职责；固定角色卡；减少切镜 |
| 服装变化 | 同一角色使用不同颜色或同义描述 | 保留同一服装短语；写清状态变化触发 |
| 首帧不像输入 | 未使用官方 I2VA 首行；重新设计了参考图 | 使用 `<Picture 1>` 固定首行；从图后动作写起 |
| 尾帧未命中 | 中间动作过多；最后才突然要求收敛 | 提前进入收敛阶段；减少末尾新动作 |
| 视频之间卡顿 | 片尾仍高速运动；编码拼接参数不一致；音频相位突变 | 片尾动作收束；统一 fps/编码；做音频淡化或连续参考 |
| 一帧一帧跳 | 镜头约束冲突；运镜过多；参考帧差异过大 | 每段一个主运镜；减少相互矛盾的构图要求 |
| 台词重复 | 同一句在多个区块或镜头重复 | 台词只在一个 `<d>` 中出现；跨切使用 `<scenetrans>` |
| 台词错语言 | 缺少 `[Language]`；文字在 `<d>` 外 | 使用标准 `<d>[Chinese] ...</d>` |
| 旁白绑定口型 | 没有使用官方 voiceover 句式 | 使用 `says in an off-screen voiceover` 并写嘴唇闭合 |
| 对白过快 | 台词量超过时长；同时动作过多 | 拆成多个片段；减少词数；给停顿时间 |
| 自动字幕 | 台词被当成可见文字；模型随机生成 | 不把台词写成可见文字；按官方结构重写；生成后 QA |
| 乱码招牌 | 让模型生成长而小的文字 | 文字后期完成；生成阶段预留安全区 |
| 手穿过物体 | 动作缺少接触与铰链路径 | 把动作拆为接近、接触、施力、运动、停止 |
| 多出人物/动物 | 群体描述模糊；参考图背景有额外主体 | 明确可见主体数量和进入路径；裁净参考素材 |
| 环境声混乱 | 声音在多个层重复；画内外音乐未区分 | 按 Shot、soundscape、music 三层重新分配 |
| 多图效果变差 | 每张图职责不清；身份、场景、动作互相竞争 | 建立素材角色表；一图一主职责；移除低价值参考 |

### 6.2 按症状查：H3 里到底该改哪一句

| 症状（你说的「糊/崩/不听话/画面不动/漂移/多字幕」） | H3 视角的根因 | 具体改法（可直接抄的句式） |
|---|---|---|
| **画面糊 / 一眼假** | 正文里堆了抽象愿望（`电影质感`、`光影细腻`），没有可执行的摄影事实；或者把 768p 当 1080p 用 | 删掉所有抽象词；改写成具体事实：`one practical tungsten pendant lamp from camera upper left`、`shallow depth of field on the near eye`、`fine restrained film grain`、`natural photographic blacks`。分辨率问题交给 `H3-Regenerate-2K`（官方口径：不等于普通超分，H3/MANUAL 14.6/22.6） |
| **画面不动 / 只有呼吸** | 未给出**可观察变化**；只写了状态名词没有动作触发 | 按官方状态结构补「动作触发 → 可见变化」：`He bends at the waist, lifts the last stool, sets its four legs onto the stack`；再加结果态 `his weight settles back onto his heels` |
| **人物漂移 / 换脸** | 参考职责重叠 + 用同义词换形容词 + 镜头数 >3 | ① 每条参考只留一个主职责（`<Subject 1> … <Picture 1> defines his face, hairstyle and wardrobe only.`）② 同一人物在所有 Shot 用**同一个短语**引用（不要这镜写「面馆老板」下镜写「中年男子」）③ 砍到 1–2 个 Shot；④ `retention_analysis` 写 `fully_preserved` 并列出要保的特征 |
| **不听话（写了不执行）** | 用了 H3 不认识的元标注（「第一优先级」）、中文板块名（【约束】）、或负面句 | ① 删元标注与板块名，只留 H3 字段；② 负面句改正向职责声明（见 6.3）；③ 把「要它做的事」变成 Shot 里的动作句 + 切点时间 |
| **多了字幕 / 乱码文字** | ① 台词被当可见文字写；② 让人物生成了招牌/门牌小字；③ 竖屏更易出字（Seedance 侧经验）；④ H3 没有 `subtitle=false` 开关 | ① 台词只放 `<d>`，不要在正文再引一遍；② 真需要可见文字时用英文双引号写并逐帧 OCR 检查，否则**正向描述画面下方实际应该出现的视觉内容**；③ 生成后质检原始像素——「字幕可能已经被生成进像素，不是可关闭的字幕轨」，只能重生成/局部修复/裁切/逐帧去字（11.3） |
| **环境声混乱 / 盖过对白** | 声音在多个层重复；画内外音乐没分开 | 按四层重排（12.1）；对白只在一个 `<d>`；画内收音机/电视/手机音乐写进 Shot，观众专属配乐写 `non_diegetic_music`；无配乐写 `N/A` |
| **台词读两遍 / 错语言 / 语速飙车** | 台词在多个 Shot 各写一遍；缺 `[Language]`；词数超过 4–15 秒承载 | 用 `<scenetrans>`；补 `[Chinese]`；减词或拆段——「宁可拆段，也不要强行加速」 |
| **首帧不像我们给的分镜图** | 没写官方 I2VA 首行；用新形容词重新设计了参考图 | 首行原样写 `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`；正文只写「图之后发生的变化」，并列出保留项 |
| **一镜到底的尾帧没落回去**（FL2VA/L2VA） | 中间动作太多；最后 1 秒才要求收敛 | 提前进入收敛；末尾不安排新信息；用范例 3/4 的收尾句 |
| **切镜后空间断裂** | 切镜没带新信息或没写轴线 | 记录屏幕轴线（人在左/右、面朝哪、主光来自哪侧）；跨镜头改轴线要写明「切到反打/新视角」（9.4） |
| **模型自己编台词**（我们第一版的真实事故） | 台词没进提示词 | H3 里 = 没有 `<d>`；有台词必须 `(S1) says: <d>[Chinese] …</d>`；无台词镜头正写「他不说话、嘴唇保持闭合」并**不分配 `(Sx)`** |

### 6.3 「禁指向」在 H3 里怎么落地（重要）

H3 官方没定义 negative 字段，原文：「不要把 Prompt 负面句当成确定性屏蔽器。若部署工作流没有独立 negative conditioning，文字中的否定概念仍然只是普通文本条件，遵循率不受保证。」（11.3）

所以把 Seedance 的「禁指向」翻译成 H3 的三种合法写法：

| Seedance 写法 | H3 合法替代 | 依据 |
|---|---|---|
| `不要出现多余人物` | 在 `subject_definitions` 写清主体数量与身份；在 Shot 里写「画面中只有 X 和 Y」；参考图裁净背景人 | 16、14.5 |
| `不要改变服装` | 在 `retention_analysis` 写 `fully_preserved - wardrobe … are retained`；正文用同一服装短语复述一次 | 9.1、25.5 |
| `禁止生成文字/水印` | 正向写画面下方实际内容（桌面/地板/衣料）；不把台词写成可见文字；生成后 QA 查像素 | 11.3 |
| `负向词：no morphing / no flicker …`（P/VOCAB 视频负向词库） | 只在**支持独立 negative 字段**的平台用；H3 上改用「物理路径写清 + 每段一个主运镜 + 状态守恒」来压 morph/flicker | P/VOCAB、H3/MANUAL 8.3、9.3 |

P/VOCAB 的视频专属负向词库仍值得存档（换平台时用）：
`no morphing, no flickering, no jitter, no melting, no warping, no temporal distortion, no extra limbs, no deformed anatomy, no blurry, no low quality, no watermark, no text overlay` / 运动：`no shaky camera (unless intended), no abrupt cuts, no frozen frames, no speed glitch, no reverse motion error, no sliding/scrolling fake motion` / 人物：`no identity drift, no face changing between frames, no inconsistent costume, no age/gender shift, no duplicate subject` / 文字：`no text drift, no garbled subtitles, no wrong spelling, no random signs morphing` / 音频：`no out-of-sync audio, no mismatched lip-sync, no abrupt sound cut, no silence gap, no overlapping noise (unless intended)`

### 6.4 生成前审计清单（H3/MANUAL 17 原文全项，照抄当 checklist）

**模式**
- [ ] 已明确 T2VA / I2VA / FL2VA / L2VA / Ref2VA
- [ ] 关键帧与普通身份参考没有混淆
- [ ] 没有把 Ref2VA 的六段式与 Base 三段式混用

**结构**
- [ ] 字段名和顺序符合官方格式
- [ ] I2VA/FL2VA/L2VA 固定首行正确
- [ ] 固定首行后有一个空行
- [ ] Shot 1 没有时间戳
- [ ] 后续 Shot 时间严格递增

**时间**
- [ ] 所有动作可在 4–15 秒完成
- [ ] 台词长度符合可用时间
- [ ] 末尾留有动作或情绪收束时间
- [ ] 尾帧任务给了足够的收敛时间

**主体**
- [ ] 角色身份、服装、发型和体型固定
- [ ] 主体数量明确
- [ ] 道具数量与状态明确
- [ ] 左右位置、视线和光线方向没有冲突

**对白**
- [ ] 每个真实发声源都有稳定 `(Sx)`
- [ ] ID 按首次实际发声顺序分配
- [ ] `<d>` 内只有语言标签和原台词
- [ ] 旁白使用官方句式
- [ ] 跨镜头台词使用 `<scenetrans>` 或明确连续关系
- [ ] 台词没有在 soundscape/music 中重复

**音频**
- [ ] 同步动作声写在对应 Shot
- [ ] 全局环境声写在 `overall_soundscape`
- [ ] 画外配乐写在 `non_diegetic_music`
- [ ] 没有配乐时使用 `N/A`

**参考素材**
- [ ] 每个参考素材职责明确且狭窄
- [ ] `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` 含义稳定
- [ ] Ref2VA 每个标签都有 retention 关系
- [ ] 没有意外继承水印、字幕、背景人或错误文字

### 6.5 生成后验收清单（H3/MANUAL 18 原文全项）

**文件层**：可解码 / 时长符合请求 / 24 FPS 或项目指定帧率一致 / 分辨率和画幅正确 / 音轨存在且无明显爆音、静音或截断

**画面层**：首尾帧锚点正确 / 角色脸、服装、身材未漂移 / 道具数量未变化 / 动作没有穿模、逆序或瞬移 / 没有冻结、黑帧和异常闪烁 / 没有多余字幕、乱码、Logo 或水印

**音频层**：说话人正确 / 台词完整且只读一次 / 语言、语速和情绪正确 / 口型与声音大致同步 / 环境声和配乐没有盖住对白 / 跨片段响度和底噪接近

**连续性层**：上一段结尾与下一段开头构图相容 / 镜头轴线没有无缘无故反转 / 动作状态能自然接续 / 情绪曲线连续 / 声音没有硬断或重复起句

### 6.6 六维诊断矩阵（P/DIAG 第二节原文表，用「先定位维度再改」代替整段重写）

| 维度 | 典型失败表现 | 快速定位问句 |
|---|---|---|
| **内容** | 主体错、场景错、元素缺失/多余 | 「画面里的人和东西对吗？」 |
| **运动** | 运镜没按意图、抖动乱晃、动作错/卡顿 | 「镜头动得对吗？主体动得自然吗？」 |
| **音频** | 缺音频、错位、人声不同步 | 「声音对吗？配乐/环境音到位吗？」 |
| **物理逻辑** | 变形 morphing、闪烁 flicker、多出肢体、穿帮 | 「有没有诡异变形或穿帮？」 |
| **人物真实感** | 脸漂移、身份不一致、表情僵 | 「人还是同一个人吗？脸稳吗？」 |
| **风格一致性** | 跨镜头色彩/光不对、质感跳变 | 「几个镜头风格统一吗？」 |

配套六维修订话术（P/DIAG 第三节原文要点，直接可用）：
- 内容：`clear focal subject: ___`、`setting: ___ (time+place+lighting)`、`no extraneous objects`
- 运动：海螺写原生控件 `[缓慢横移]`；抖动用 `stable camera, no handheld shake` 或 `locked tripod shot`（**注意：这两条在 H3 上要写成正向的 `The camera holds a static shot throughout`**）；卡顿加 `smooth continuous motion, natural physics`
- 音频：`with synchronized ambient sound`、`add subtle wind + city hum`；配乐指定 `score: tense strings`；静音模型跳过本维
- 物理：`physically plausible, no clipping, no floating objects`（H3 上转成物理路径句）
- 人物：`natural micro-expressions, subtle emotional shift`；跨镜头共用同一锚点文本
- 风格：`color grade: ___ , consistent across shots`、`uniform film grain / texture throughout`

分层验收顺序（P/DIAG 第四节原文）：`内容 ✓ → 运动 ✓ → 风格 ✓ → 音频 ✓`，任一层不通过就回对应维度改、**只重生该段**、锁 seed，再重新验收。

经验沉淀格式（P/DIAG 第五节原文，建议直接进我们的 PLAYBOOK）：

```markdown
- [片型] ___ → [失败维] ___ → [有效修订] ___ → [平台/seed] ___
```

---

## 7. 真实案例的前后对比经验（C 库：12 次首生成 + 5 次定向修订）

> **先说清楚边界**：C 库（`62656456__*`）用的是**图像工具**（原文：「模型为当时可用的内置 image_gen」「17 次图像工具调用」），不是 H3 视频；REVIEW 明确写「本批没有旧法同题 A/B，也没有跨次身份测试或视频测试」。所以下面提炼的是**文字层面的修订手法**，它对我们有两个直接用处：① 我们的**生图阶段**（LingCut 分镜图）可以照抄；② 迁移到 H3 的 `retention_analysis` + 「只改一句话」的迭代纪律。
>
> 另有两条必须继承的**证据纪律**：原文「不能把最终结果当首次成功」「历史统计保留为历史，新问题写在对应案例中」；发布前独立抽检时发现 12 号「人物目测约占画高 20%，明显超过首次输入的约 4%」，即**历史判定为「主要要求通过」的图，独立复核后仍有未通过项**。

### 7.1 手法 1：只改一处 + 其余全部「逐项点名保留」

**失败**：03 收音机首图出现六排孔（要求三排）；04 多出背景人物；07 脚印越过椅子；08 多出可读的墙面/门牌文字。

**修订词原文（03，C/REV）**：

```text
Edit the most recent generated portable radio image. Change only the speaker grille on the right side of the front face: it must contain exactly THREE horizontal rows of evenly spaced small circular holes, clearly three rows total, with no paired sub-rows and no additional holes above or below. Preserve everything else exactly: one cream-white rounded rectangular radio, one orange circular knob on the left, no screen, same body proportions, same slight three-quarter angle, same warm-gray plinth, same muted gray-green background, same soft upper-left studio light, same matte molded-plastic texture and contact shadow. Do not add text, labels, buttons, antenna, handle, cable, second radio, logo or watermark.
```

**可迁移到 H3 的写法**：
- 句式骨架 = `Change only <单点> … Preserve everything else exactly: <清单>`。
- H3 里的等价物 = `retention_analysis` 一行行写 `fully_preserved - …` + 正文只新增那一个变化。
- 「其余全保」必须**点名到材质、光位、角度、接触阴影**，不能只说 `Preserve everything else`（对应 H3 的 9.2：弱 `Keep everything consistent.` vs 强写法逐项列）。

### 7.2 手法 2：用「大写数字 + 显式排除 + 明确总数」锁数量

**原文词句**：
- `exactly THREE horizontal rows of evenly spaced small circular holes, clearly three rows total, with no paired sub-rows and no additional holes above or below`（03）
- `Keep exactly two people total.`（04）
- `Preserve … one cream-white rounded rectangular radio, one orange circular knob on the left, no screen`（03）
- 首生成阶段同款：`Create exactly one original clay stop-motion fox postman`、`exactly one round brass button on the chest`、`exactly three tall windows in a row`、`exactly one large round clock centered above one continuous row of worn wooden benches`（C/PROMPTS 01/02/03）

**可迁移到 H3**：`subject_definitions` 里写数量（`<Subject 2> is the single white Samoyed…`）、Shot 里写 `exactly two people are visible`；道具数量写进 `retention_analysis`。**经验**：模型对「一个/三个/两个」这种小整数能执行，对「精确占比 4%」这类连续量几乎不执行（见 7.8）。

### 7.3 手法 3：删除项必须给「替换成什么」

**失败**：04 多出一个背景人物；08 多出可读文字。

**修订词原文**：

```text
Edit this underground prosthetic-clinic image by removing only the unintended background person standing in the rear doorway. Replace that figure with the same empty lit corridor and doorway surfaces. … Do not add any new person, limb, object, text, logo, HUD, smoke or watermark.
```

```text
Edit this dockside accounting-office noir image by removing only the unintended readable environmental text: erase the wall sign text and the door words, replacing them with believable aged blank paper/panel and frosted glass texture. Keep the accountant, his expression and gaze, open ledger, burning wastebasket, wet handprint, rainy window, locked door, desk lamp, composition, lighting, colors and materials unchanged. The ledger may retain small natural accounting marks, but do not add any large readable words, captions, signage, logos or watermark.
```

**可迁移到 H3**：H3 没有负面屏蔽器，所以「不要出字幕」唯一可靠的写法就是**把那个位置的实际内容正向写出来**（`the lower third of the frame is the tabletop, scuffed wood with a wet ring from the bowl`），并按官方 11.3 做生成后像素级 QA。08 还给了一个重要让步技巧：**允许小自然标记，只禁大块可读文字**（`The ledger may retain small natural accounting marks, but do not add any large readable words`）——比一刀切「禁止所有文字」更容易被模型执行。

### 7.4 手法 4：给「起点 / 终点 / 清除区间」三段式锚定

**失败**：07 湿脚印越过了空椅子。

**修订词原文**：

```text
The wet bare footprints must begin at the closed back door, cross the dry wood floor, and END directly beneath the pulled-out empty chair. Remove every footprint between the chair and the foreground/woman/camera. There must be no footprints leading away from the chair and no footprint near the woman's feet. Keep the final footprint clearly visible beneath the empty chair.
```

**可迁移到 H3**：这就是官方**状态机**写法（门关闭 → 手接近把手 → … → 手松开，9.3）的同构版本：给运动一个**不可越过的终点**。视频里对应「动作必须在 X 秒前收束，不要延展到 Y」。C 库的问题是「首图脚印越过椅子」，视频里的等价失败是「动作演过头 / 走位出画 / 道具被多拿一个」。

### 7.5 手法 5：把「渲染感」拆成物理光与材质句

**失败**：12 仙侠台被判定为「亮天空轨迹 + 过多均匀细节削弱了实拍摄影感」（原文：`bright sky trails and excessive uniform detail weakened live-action photography`）。

**修订词原文（节录，未改写）**：

```text
Edit this xianxia armillary-platform image to make it read as a live-action large-format film still rather than a polished fantasy game render. … Remove the bright magical spiral trails from the sky. Simplify the giant bronze surfaces into calmer large structural planes with restrained shallow relief, real dark patina, uneven oxidation and narrow worn edges; avoid dense equal ornament everywhere. Make the physical foreground stone slightly imperfect, damp and weighty with believable contact, and the robe visibly woven with natural folds. Reduce sharpness, microdetail, contrast and saturation progressively through middle and far distance; distant buildings should have softer silhouettes, irregular atmospheric occlusion and uneven natural illumination, while remaining readable. Use one real high-altitude morning sun from camera right, natural photographic blacks, soft highlight roll-off, subtle lens halation and fine restrained film grain. Keep the four scale proofs, five layers and 40–60% content-bearing air. No global glow, no artificial HDR, no neon edges, no cloned figures, no text, no logo, no watermark.
```

**提炼出的可抄词块（H3 正文直接能用）**：

| 目的 | 原文字句 |
|---|---|
| 去游戏渲染感 | `rather than a polished fantasy game render`；`avoid dense equal ornament everywhere`；`no global glow, no artificial HDR, no neon edges` |
| 材质物理化 | `real dark patina, uneven oxidation and narrow worn edges`；`slightly imperfect, damp and weighty with believable contact`；`visibly woven with natural folds` |
| 纵深衰减 | `Reduce sharpness, microdetail, contrast and saturation progressively through middle and far distance`；`irregular atmospheric occlusion and uneven natural illumination` |
| 单一实光源 | `Use one real high-altitude morning sun from camera right`；`natural photographic blacks, soft highlight roll-off` |
| 留白与呼吸 | `Keep the four scale proofs, five layers and 40–60% content-bearing air` |

> 与我们手册的接口：这几句正好是 H3「写具体可视事实」的正面样板，可以替代我们惯用的「电影质感 / 光影细腻」（H3 官方点名反对的抽象词）。

### 7.6 手法 6：负向清单要短、具体、且只封「新增项」

**原文负向串**：
- `Do not add text, labels, buttons, antenna, handle, cable, second radio, logo or watermark.`（03）
- `Do not add any new person, limb, object, text, logo, HUD, smoke or watermark.`（04）
- `No gun, detective cliché hat, blinds pattern, smoke, exaggerated Dutch angle, dead-black face, unreadable clue, extra people, text overlays, logos or watermark.`（08 首生成）
- `No floating bodies, wire-fu pose, extra fighters, duplicated weapons, blade through hands, broken anatomy, random slow-motion debris, heavy fog, text, logos or watermark.`（11 首生成）

**共同点**（可复用规律）：
1. 全部是**名词型清单**，不是「不要 X 地 Y」的句子；
2. 每条只封 4–10 项，不写几十项；
3. 排在前面的都是**该题材最容易翻车的具体物**（收音机→天线/提手/线；义体诊所→多余人物/HUD；武打→钢丝/复制武器/刀穿手）；
4. 末尾固定收 `text, logos or watermark`。
> 在 H3 上，这套清单**不能照抄进正文当屏蔽器**，而应转成：`subject_definitions` 的主体清单 + Shot 里写「画面内只有这些物」+ 生成后 QA。

### 7.7 手法 7：先预演、分层验收、保留失败件（流程层经验）

C/WORKFLOW 原文要点：
- 「先做完整低清预演，同时查看关键事件**前中后**：抢线能否读清、手是否确实握住道具、受力之后是否有反应、换机位后空间有没有被镜像。」
- 「失败修订另存，**保留原输入和结果**。」
- 「局部修改还要检查**邻接切点**，最后才输出完整高清。」
- 「保存实际提示词、参考文件、时长/分辨率/模型版本中能核实的项目、输出与成本来源。**不可获知的设置留空，不从文件名猜模型。**」

C/RETRO 原文要点：
- 「把内部检查当成最终验收」是暴露的问题之一 → 「记录每层实际做过什么，不自动递增用户接受次数」。
- 「钥匙仍在正确手上，画面却看不到握点」→ 教训是「数据正确 ≠ 关键动作可读」，必须真的看图。
- 结论：**白模/预演只降低「某些镜头设计」的不确定性，不构成统计性成功率提升**；「复杂镜头按需使用白模」，不要推广到所有镜头。

### 7.8 手法 8：别用提示词锁连续量（百分比尺度 / 精确比例）

C/REVIEW 原文：12 号要求「人物约 4% 画高」，修订后独立抽检实测约 **20%** 画高，「精确尺度约束未通过」。

**结论**：提示词能可靠执行的是**离散量**（exactly one / three rows / two people）和**相对关系**（left of / behind / beneath / same side）；**连续量**（占画面 x%、色温精确值、光比数值）只能当方向性描述，不能当验收标准。这条直接适用于我们写光比和色温时的预期管理（H3 上同样成立：`约3000K`、`光比大` 是给模型的**倾向**，不是可验收的数值）。

---

## 8. 平台差异速查（P/PLAT 原文，2026-08 核对版）

> **时效声明（原文）**：「下列原生控件参数为 2026 年中公开文档核实值。视频平台迭代极快，正式投产前请以各平台当前官方文档为准（尤其版本号、参数范围、时长上限）。」

### 8.1 公式与控件总表

| 平台 | 提示词公式 / 结构（原文） | 运镜控制方式 | 音频 | 规格 / 时长 | 强项 |
|---|---|---|---|---|---|
| **海螺 Hailuo（MiniMax）** | 运镜指令语法直接写在 prompt 里：`[左移] [右移] [左摇] [右摇] [推进] [拉远] [上升] [下降] [上摇] [下摇] [变焦推近] [变焦拉远] [晃动] [跟随] [固定]`；「自然语言：也支持，但标准指令更准」 | 方括号指令；同组 ≤3，如 `[左摇,上升]`；顺序运镜用「然后」 | 支持（H3 官方：原生 32kHz 立体声） | 二手：768P/1080P，6s/10s；H3 官方：4–15s，768p，2K 需 Regenerate-2K | 情感表达、人物微表情、画面连贯 |
| **可灵 Kling（快手）** | `Subject(Details) + Movement + Scene(Background) + Cinematic Language + Lighting + Atmosphere` | 相机控制六轴（API/高级界面，范围 [-10,10]）：Horizontal/Vertical/Pan/Tilt/Roll/Zoom；Motion Brush 涂抹局部 | 2.6+ 支持 AI Audio Sync | std（快/省）vs pro（细节/1080p）；VIDEO 3.0 Omni 支持多镜头 storyboard；参考图最多 7 张（O1） | 物理/运镜强，国内首选，成本低 |
| **即梦 Jimeng（字节）** | 中文直接写，不必硬翻英文；运镜可给「机位高度 + 速度 + 焦段」 | 自然语言（如「镜头高度1.6米,匀速前推,速度0.8米/秒,焦段24毫米」）或指令式 | — | 支持首帧图 + 尾帧图；Seedance 2.0 最多参考 12 个文件 | 中文语义强、古风/山水意境 |
| **智谱清影 CogVideoX** | 基础：`主体 + 场景 + 运动`；进阶：`主体(描述) + 场景(描述) + 运动(描述) + 美学控制 + 风格化`；复杂：`[镜头语言] + [光影] + [主体(描述)] + [主体运动] + [场景(描述)] + [情绪/氛围/风格]`；简单：`[摄像机移动] + [建立场景] + [更多细节]` | 结构化标签块 | — | 约 6s；文生/图生 | 开源/免费、结构化 |
| **通义万相 Wan（阿里）** | 文生：`主体 + 场景 + 运动`；图生：`运动 + 运镜`；声音：`主体 + 场景 + 运动 + 声音描述`；多镜头：`总体描述 + 镜头序号 + 时间戳 + 分镜内容`（例：`第 1 个镜头[0-3秒]… 第 2 个镜头[4-6秒]硬切转场,固定机位…`）；参考生视频：`参考指代(图n/视频n) + 动作 + 场景 + 台词(可选) + 背景音乐(可选)`，用 `character1` 引用主角（最多 3 个） | 写「镜头推进」/「固定镜头」 | 人声 = 内容+情绪+语调+语速+音色+口音；音效 = 音源材质+行为+环境音；BGM = 配乐+风格；无台词写 `无台词`/`No dialogue.`，无 BGM 写 `无背景音乐`/`No background music.` | — | 多镜头/参考生视频/音频 |
| **Sora（OpenAI）** | `[Camera movement] shot of [subject] [action/motion] in [setting], [lighting], [mood], [style]` | 自然语言电影术语（aspect ratio / lens / film stock） | — | up to 60s | 电影感、复杂场景、物理与空间关系、理解 film terminology |
| **Runway（Gen-3/4.5）** | 通用公式 + Camera presets | **Motion Brush** 精确控制「什么在动」+ Camera presets | — | up to 10s per generation | 一致运动、迭代编辑、局部运动 |
| **Veo 3 / 3.1（Google）** | `camera, subject, action, setting, style and audio`（75–125 词，5 块）；对话用引号、命名 ≤2 个音频事件 | 自然语言 | **原生音频**一次生成 dialogue / SFX / ambient；要静音须显式说 `silent / no audio` | 8s base；Scene Extension 链式最长 140s；720p/1080p/4K；竖屏 9:16 原生；每段带 SynthID | 音频优先成片；Ingredients to Video 最多 3 张参考图锁角色 |
| **Luma** | 通用公式，强调 `smooth realistic motion` | 自然语言 | — | image-to-video / text-to-video | 自然运动与物理模拟 |
| **Pika 2.0** | 通用公式 | — | — | 3–5s（effects-focused） | 风格化/创意特效（inflate / melt / explode / crush） |

### 8.2 平台选择与路由（P/PLAT 第四节原文）

- **运镜控制 / 高性价比批量** → 可灵 Kling
- **情感叙事 / 人物微表情** → 海螺 Hailuo ← **我们这条线应该走这个理由**
- **中国风 / 中文语义** → 即梦 Jimeng / 智谱清影
- **多镜头连贯叙事 / 参考生视频** → 通义万相 Wan
- **原生音频 / 音频优先成片** → Veo 3
- **电影感 / 复杂场景 / 长片** → Sora
- **一致运动 / 迭代编辑 / 局部运动笔刷** → Runway
- **风格化特效** → Pika
- **一段一模型路由**：某段 A 模型做砸，路由到该项更强模型（如运镜段→可灵，音频段→Veo3）

### 8.3 可灵六轴数值建议（P/PLAT 原文）

「单轴强度先试 ±5~±7，避免 ±10 过猛导致失控；多轴组合 ≤2 个。」

### 8.4 平台差异化（W/PIPE 原文表，抖音/小红书）

| 项目 | 小红书 | 抖音 |
|---|---|---|
| 节奏 | 中慢，真实 | 快，前3秒钩子 |
| 运镜 | 生活感手持优先 | 飞入 + 强展示 |
| 文案 | 种草共鸣 | 强 CTA |
| 字幕 | 自然、可读 | 大字、冲击 |
| BGM | 轻柔不抢人声 | 可稍强，但仍要 ducking |

### 8.5 H3 各模式该选哪个（把上面的平台差异收回到我们这条线）

| 我们的场景 | H3 模式 | 理由（官方依据） |
|---|---|---|
| 只有剧本文字，还没有图 | T2VA | 无关键帧输入，由文本建立完整视听时间轴（6.1） |
| 分镜图当第一帧，往后演 | I2VA | `<Picture 1>` 是 0.00 秒真实首帧，属于 `[Shot 1]`（24.3） |
| 两张分镜图锁头尾（转身/开门/坐下/递物） | FL2VA | 官方倾向单镜头插值（6.3） |
| 只想指定结尾定格 | L2VA | `<Picture 1>` 属于最后 `[Shot N]`，不是 Shot 1（6.4） |
| 角色图 + 场景图 + 配音 + 参考运镜视频 | **Ref2VA** | 多图角色、参考视频、音色、动作、场景或编辑关系 → Ref2VA（Step 1 决策树） |

> 「不要因为『有一张角色参考图』就机械地选择 I2VA。若图片只定义人物身份、并不是第 0 秒的具体画面，应使用 Ref2VA 的 `<Subject N>` 关系。」（H3/MANUAL 4 Step 1）← **这一句直接命中我们的流水线：LingCut 里连的角色大头照是身份参考，不是首帧。**

---

## 9. 对我们流水线的具体改法

### 9.0 先定性：我们这条线在 H3 里属于哪种模式

LingCut 画布 → 生图 → 生视频，视频节点上连了：**分镜图 + 角色大头照 +（有对白时）音频节点**。按 H3 官方决策树（H3/MANUAL 4 Step 1）：

```text
需要多图角色、参考视频、音色、动作、场景或编辑关系？
└─ 是 → Ref2VA
```

并且官方专门点了一句：「不要因为『有一张角色参考图』就机械地选择 I2VA。若图片只定义人物身份、并不是第 0 秒的具体画面，应使用 Ref2VA 的 `<Subject N>` 关系。」

→ **结论：我们默认应该走 Ref2VA 六段式**（角色图/场景图 = `<Subject N>` 的来源；分镜图 = `[Shot 1]` 的 `<Picture N>` 首帧锚点；配音 = `<Audio N>` 音色参考）。只有当一条视频**只连了一张分镜图**时，才降级用 I2VA 三段式。

### 9.1 待改写的原文（Seedance 范式）

```text
画面无任何字幕。
老城区面馆深夜写实风格，5秒，16:9，克制的疲惫

镜头1（第一优先级：他叠最后一张凳子时那半秒没忍住的泄气）
固定机位中景。暖黄吊灯为唯一实用光源，约3000K，光比大…
58岁中国男性面馆老板，灰白短发向后梳…他弯腰把最后一张红色塑料凳叠到凳堆上，动作缓慢，肩膀微塌。
镜头2 他直起腰，呼吸变浅；眉间松了一瞬又收拢…
镜头3 嘴角想提一下没提起来；嘴唇压紧半秒后随下颌松开而分开…
【声音】【参考】【约束】【一致性】
画面稳定不闪烁、光影细腻、电影质感
```

**一句话诊断**：这段文字里有 3 处**H3 根本不认识的语法**（中文板块名、【】：元标注、无时间戳的「镜头N」），4 处**H3 明确反对的写法**（抽象情绪词「克制的疲惫」、项目管理式括号、句尾保底神词、把时长画幅写进正文），2 处**该有却没有的官方结构**（三段/六段字段、台词与说话人机制），还有 1 处**结构性错误**（把一次连续表演切成 3 个 Shot）。下面重写。

### 9.2 版本 A｜官方 H3 严格版（Ref2VA 六段式，英文正文，直接可粘）

> 素材对应关系（按官方 25.3.2：只定义身份的图不单列 Picture 条目，在 Subject 里引用即可）
> - `<Picture 1>` = 角色大头照（只定义身份）
> - `<Picture 2>` = 场景图（只定义空间与光）
> - `<Picture 3>` = 分镜图 = `[Shot 1]` 的真实首帧（**这一张才单列 Picture 条目**）
> - 本镜无台词 → **不分配 `(Sx)`，不定义 `<Audio N>`**（官方：没有发声的角色不要分配 ID）

```text
subject_definitions:
<Subject 1> is the 58-year-old Chinese noodle-shop owner in <Picture 1>, with short grey-white hair combed back, a lean build, deep nasolabial folds, visible pores, uneven skin tone, and a faded dark-grey work shirt with the sleeves rolled to the forearms. <Picture 1> defines his face, hairstyle, body proportions and wardrobe only.
<Subject 2> is the late-night noodle shop in <Picture 2>, with worn formica tables, a wall price board carrying no legible characters, a half-lowered roller shutter over the shopfront, and one warm tungsten pendant lamp hanging above the stack of red plastic stools. <Picture 2> defines the room layout, the positions of the counter, the door, the tables and the stool stack only.
<Picture 3> is the first frame of [Shot 1], showing <Subject 1> bending over the stool stack in <Subject 2>, framed as a chest-height medium shot.

summary:
[reference generation + keyframe completion] The target video holds one static shot inside <Subject 2>, where <Subject 1> stacks the last red plastic stool and lets half a second of fatigue show before he covers it again. No dialogue is spoken in this shot.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the grey-white hair combed back, the face, the lean build, and the faded dark-grey shirt with rolled sleeves are retained.
<Subject 2> (appears in [Shot 1]): fully_preserved - the room layout, the half-lowered roller shutter, the wall board without legible characters, and the single warm pendant lamp are retained.
<Picture 3> ([Shot 1] first frame): fully_preserved - the opening framing, the chest-height camera position, and the subject's placement beside the stool stack are retained.

detailed_description:
The target video is live-action, cinematic and restrained, at 24 fps, lit only by one warm tungsten practical lamp inside a closed noodle shop at night.
[Shot 1] The shot begins from <Picture 3> and holds a static chest-height medium shot for the entire take. <Subject 1> stands on the right of the frame beside the stack of red plastic stools. <Subject 2> recedes behind him: the counter on the left, the door in the back wall, and the wall board above the counter carrying no legible characters. The warm pendant lamp above the stool stack is the only practical light; it falls from above and slightly camera-left, and the far side of the room stays in deep shadow. He bends at the waist, lifts the last red plastic stool with both hands, and sets its four legs onto the top of the stack; the plastic knocks once against the stool beneath it and settles. As his hands leave the stool, his shoulders drop and his weight settles back onto his heels. He straightens up and pulls one slow breath in through his nose; the breath leaves him shorter than it went in. The muscles between his brows loosen for less than a second, then draw back together. The corner of his mouth starts to rise and stops; his lips press together for half a second, then part as his jaw slackens. He looks once across the empty tables, then down at his own hands. He says nothing, and his lips remain completely closed for the rest of the shot. He stays standing beside the stool stack, facing the counter, while steam from the pot on the counter keeps drifting upward through the lamp light. The camera never moves and no cut occurs.

overall_soundscape:
A low room tone continues underneath, with the hum of a refrigerator and a faint electric buzz from the pendant lamp. The plastic stool knocks softly against the stack, and the stack creaks once as his hands leave it. Fabric shifts at his shoulders, one slow breath passes through his nose, and a bicycle rolls past in the street outside.

non_diegetic_music:
N/A
```

**如果这一镜要加一句台词**（把上面三处补丁打上即可，其余不动）：

```text
subject_definitions:  追加一行
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary:  任务类型前缀追加 + audio reference
[reference generation + keyframe completion + audio reference] ...

detailed_description:  在对白时间点插入（<d> 外写音色/语速/情绪，<d> 内只放语言与台词）
<Subject 1> (S1) says in a low, slow, slightly hoarse voice: <d>[Chinese] 打烊了。</d> He closes his mouth naturally and looks down at his own hands.
```
> 注意：`(S1)` 只在**真的有台词**时才分配；无台词镜头不要给 ID（10.1）。台词结束必须写 `closes his mouth naturally`（10.6）。

**要配乐时的 `non_diegetic_music` 写法**（替换 `N/A`）：

```text
non_diegetic_music: Sparse upright-bass notes at a slow tempo, entering after the stool settles on the stack and fading out before the final frame.
```

### 9.3 版本 B｜只连一张分镜图时（I2VA 三段式）

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, restrained, 24 fps. The 58-year-old Chinese noodle-shop owner shown in <Picture 1> remains in the same opening composition, preserving his grey-white hair combed back, his lean build, his faded dark-grey shirt with rolled sleeves, the stool stack, the counter, the door, the half-lowered roller shutter and the single warm pendant lamp. He bends at the waist, lifts the last red plastic stool, and sets its four legs onto the top of the stack; the plastic knocks once and settles. As his hands leave the stool, his shoulders drop. He straightens up, pulls one slow breath in through his nose and lets it out shorter than it went in; the muscles between his brows loosen for less than a second and then draw back together; the corner of his mouth starts to rise and stops. He looks once across the empty tables, says nothing with his lips completely closed, and stays beside the stack. The camera holds a static shot for the entire take, and steam from the pot keeps drifting upward through the lamp light.

overall_soundscape: A low room tone with a refrigerator hum and a faint lamp buzz. The plastic stool knocks softly against the stack, fabric shifts at his shoulders, one slow breath passes through his nose, and a bicycle rolls past outside.

non_diegetic_music: N/A
```

### 9.4 版本 C｜中文正文折中版（字段名 / 标签 / 时间格式保持英文原样）

> **定位**：这是**工程妥协**，不是官方规范。官方明确要求「Rewrite section 使用英文」（13、25.1）。只有当你确认中文入口对英文正文的遵循率更差时才用这一版；结构、字段名、`[Shot N]`、`<d>[Chinese]`、`(Sx)`、标签一律保持官方原样，只把描述句改成中文。

```text
subject_definitions:
<Subject 1> 是 <Picture 1> 中的 58 岁中式面馆老板：灰白短发向后梳、偏瘦、法令纹深、可见毛孔与肤色不均，穿洗旧的深灰工装衬衫、袖口卷到小臂。<Picture 1> 只负责脸、发型、体型与服装。
<Subject 2> 是 <Picture 2> 中的深夜面馆：旧福米卡桌面、一块无可辨识文字的价目板、半落的卷帘门、凳堆上方一盏暖色钨丝吊灯。<Picture 2> 只负责空间布局：柜台、门、桌子与凳堆的位置。
<Picture 3> 是 [Shot 1] 的首帧：胸高中景，<Subject 1> 正弯腰在 <Subject 2> 的凳堆前。

summary:
[reference generation + keyframe completion] 目标视频为单镜头固定机位：<Subject 1> 叠好最后一张红色塑料凳，在那半秒里泄出疲惫，随后又收了回去。本镜无台词。

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - 保留向后梳的灰白短发、脸型、偏瘦体型与卷袖的深灰衬衫。
<Subject 2> (appears in [Shot 1]): fully_preserved - 保留空间布局、半落卷帘门、无可辨识文字的价目板与唯一一盏暖色吊灯。
<Picture 3> ([Shot 1] first frame): fully_preserved - 保留开场构图、胸高机位与人物在凳堆右侧的位置。

detailed_description:
目标视频为写实电影感、克制调性，24 fps，夜间打烊后的面馆，只有一盏暖色钨丝实用光源。
[Shot 1] 镜头从 <Picture 3> 开始，整条固定为胸高中景，机位不动、无剪切。<Subject 1> 位于画面右侧的凳堆旁，<Subject 2> 在其身后纵深展开：柜台在左，门在后墙，柜台上方的价目板不出现任何可辨识文字。凳堆上方的暖色吊灯是唯一实用光源，光从上方略偏镜头左落下，房间远端留在深影里。他弯腰，双手抬起最后一张红色塑料凳，把四条腿放到凳堆最上一层；塑料碰到下面那张凳子发出一声轻响后落定。手离开凳子时，他的肩膀向下沉，重心落回脚跟。他直起腰，用鼻子慢慢吸进一口气，呼出的气比吸进的短。眉间的肌肉松开不到一秒，随后又收拢。嘴角想提起又停住；嘴唇压紧半秒，随下颌松开而分开。他朝空桌扫了一眼，然后低头看自己的手。他不说话，嘴唇在余下时间里保持完全闭合。他一直站在凳堆旁，面朝柜台，柜台上锅里的蒸汽继续在灯光里缓慢上升。

overall_soundscape:
底层是一段低房间底噪，冰箱嗡鸣与吊灯轻微的电流声叠在上面。塑料凳轻碰凳堆，凳堆在手下离开时吱呀一声。肩部衣料摩擦，一次缓慢的鼻息，门外有一辆自行车骑过。

non_diegetic_music:
N/A
```

### 9.5 逐条改动理由

| # | 原文写法 | 为什么在 H3 上是错的 | 改成了什么 | 依据 |
|---:|---|---|---|---|
| 1 | `画面无任何字幕。` 放在首句 | H3 官方**没有** `subtitle=false` 这类开关；这句对 H3 是无效文本，而「字幕」这个词还可能被当成画面内容条件。官方唯一给的做法是：台词只进 `<d>`、不把台词写成可见文字、生成后查像素 | 删除该句；在 Shot 里正向写「价目板不出现任何可辨识文字」，并在生成后 QA 查像素 | 11.2、11.3、24.8 |
| 2 | `5秒，16:9` 写进正文 | H3 正文只接受**可看可听的事实**；时长与画幅是生成参数，写进正文属于「模型参数混入正文」 | 时长在 LingCut 面板选 `5`；画幅在面板选 `16:9`；正文只写 `The camera holds a static shot for the entire take` 与 24 fps 这类摄影事实 | 5.1、H3 规格 4–15s |
| 3 | `老城区面馆深夜写实风格` | 风格本身没问题，但 H3 要求风格写在 `[Shot 1]` 开头的**英文风格词**位置，并且不能替代空间事实 | 保留为 `[Shot 1]` 开头：`Live-action, cinematic and restrained, at 24 fps…`，另在 `<Subject 2>` 里写死空间 | 24.4、6.1 |
| 4 | `克制的疲惫` | 抽象情绪标签；H3 需要的是**状态变化链**，不是形容词 | 拆成：肩膀下沉 → 呼吸进出不等长 → 眉间松开又收拢 → 嘴角想提又停 → 嘴唇压紧再分开 → 低头看手 | 14.2、24.4 |
| 5 | `镜头1 / 镜头2 / 镜头3`（无时间戳分段） | ① 格式错：H3 用 `[Shot 1]`、且 Shot 1 **不写**时间戳；② 更重要的是**这三段不构成有效切镜**——同一机位、同一动作的连续微表情，官方明确说这种情况优先用运镜而不是切镜 | 合并为**单个 `[Shot 1]`**，三组微表情按「触发 → 可见变化 → 结果」串成一句句连续动作；若真要切，写成 `[Shot 2] At 00:02.500, the camera cuts to …` | 7.1、7.2、7.3、24.5 |
| 6 | 没有写镜头切换时间点 | H3 的时间语言只有切点时间戳；不写 = 放弃时间控制 | 本版单镜头，明确写 `no cut occurs`；多镜时用 `At 00:SS.mmm` | 7.2 |
| 7 | `（第一优先级：他叠最后一张凳子时那半秒没忍住的泄气）` | H3 正文禁止「项目管理说明、验收口号和抽象愿望」；括号里的元标注对模型无效，还占注意力 | 删除元标注；**把「第一优先级」变成写作纪律**（整条只围绕这一个表演目标），在正文里只保留那句表演本身 | 5.1 |
| 8 | `固定机位中景` | 中文景别/机位词不是 H3 官方运镜语言 | `a static chest-height medium shot` + `The camera holds a static shot for the entire take and no cut occurs`（`Static Shot` 官方适用：稳定对白/产品/人物） | 8.1、24.6 |
| 9 | `暖黄吊灯为唯一实用光源，约3000K，光比大…` | 方向对，但缺方位、软硬、阴影行为；且「约3000K + 光比大」是数值化描述，H3 只能当倾向 | 补全为：`The warm pendant lamp above the stool stack is the only practical light; it falls from above and slightly camera-left, and the far side of the room stays in deep shadow.` | P/DIM 通用片、PERFORMANCE 光位五要素（工程经验） |
| 10 | `58岁中国男性面馆老板，灰白短发向后梳…` 写在正文里 | 人物长描述只应定义一次；写在正文里，跨镜时容易被换同义词 → 身份重采样 | 全部上移到 `<Subject 1>`，正文只引用 `<Subject 1>`；并在 `retention_analysis` 写 `fully_preserved` 列出要保的项 | 9.1、13.2、25.5 |
| 11 | `他弯腰把最后一张红色塑料凳叠到凳堆上，动作缓慢，肩膀微塌` | 写得对，但缺少**接触/施力/落定**的物理段落 | 拆成状态机：弯腰 → 双手抬起 → 四条腿放到最上层 → 塑料碰响一声 → 落定 → 手离开 → 肩膀下沉、重心回脚跟 | 9.3、16（手穿物体的修正） |
| 12 | `镜头2 他直起腰，呼吸变浅；眉间松了一瞬又收拢` | 「呼吸变浅」是内部感受，不可见 | 改为可见的呼吸行为：`pulls one slow breath in through his nose; the breath leaves him shorter than it went in` | 5.1、14.2 |
| 13 | `镜头3 嘴角想提一下没提起来；嘴唇压紧半秒后随下颌松开而分开` | 表演本身很好，保留；但它是「结果段」，需要有落点 | 保留原句意，并补余韵：`He looks once across the empty tables, then down at his own hands. He says nothing, and his lips remain completely closed for the rest of the shot.` | 14.3 状态守恒、PERFORMANCE 余韵（工程经验） |
| 14 | `【声音】` 一整块 | H3 是**四层声音**：对白→`<d>`；同步画内声→当前 Shot；环境/物理声→`overall_soundscape`；画外配乐→`non_diegetic_music` | 拆开：凳子碰响写进 Shot；冰箱嗡鸣/灯电流/自行车写进 `overall_soundscape`；配乐写 `N/A`（或给低音贝斯句） | 12.1、12.2、24.9、24.10 |
| 15 | `【参考】@图片1 …` | `@图片N` 是 Seedance/即梦语法；H3 用 `<Subject N>`/`<Picture N>` 并在**定义段**声明职责；写「综合参考」会让模型平均化脸型、混服装、复制错误背景 | `<Subject 1>`（角色图，只定义脸/发型/体型/服装）、`<Subject 2>`（场景图，只定义布局）、`<Picture 3>`（分镜图，单列为首帧锚点），并在 `retention_analysis` 逐条写保留关系 | 13.1、13.6、14.5、25.3 |
| 16 | `【约束】不要改变人物年龄与五官比例，不要出现多余人物…` | H3 **没有 negative conditioning**；官方原文：「不要把 Prompt 负面句当成确定性屏蔽器」 | 改成职责声明（Subject 只负责什么）+ `retention_analysis: fully_preserved` + 正文 `He says nothing…` 这类正向事实；生成后按 6.5 清单查像素 | 11.3、16 |
| 17 | `【一致性】全片锁定面部比例、发际线、特征记号、服装` | 「锁定」是口号，H3 里属于弱写法（官方：弱 `Keep everything consistent.`） | 改成逐项状态守恒：`<Subject 1>` 固定描述 + `retention_analysis` 列保留项 + 跨镜复用同一短语 | 9.2、14.3 |
| 18 | `画面稳定不闪烁、光影细腻、电影质感` | 这是 Seedance 的「保底神词」；H3 官方**点名反对抽象词**（`cinematic`、`beautiful`），也不会执行「不闪烁」这种否定愿望 | 删除；换成具体摄影事实：`at 24 fps`、单一实用光源、`deep shadow`、`the camera never moves`；画面稳定性靠「每段一个主运镜 + 无冲突约束」保证，靠 QA 验证 | 23.4 官方效果建议、8.3 |
| 19 | 缺失：模式与固定首行/六段字段 | 没有字段结构，模型拿不到「谁是参考、哪张是首帧、哪段是环境声」 | 补 Ref2VA 六段（版本 A）；只有一张分镜图时用 I2VA 固定首行（版本 B） | 4 Step 4、24.2、25.2 |
| 20 | 缺失：说话人与台词机制 | 我们的历史事故就是「台词没进提示词 → 模型自己编」；H3 里等价于没有 `<d>` | 有台词时 `(S1) says: <d>[Chinese] …</d>`（`<d>` 外写音色/语速/情绪），说完 `closes his mouth naturally`；无台词时不分配 ID 并写 `lips remain completely closed` | 10.1、10.2、10.6 |
| 21 | 缺失：音色参考的 H3 写法 | 我们连了音频节点但提示词里写 `@音频1`，H3 不认 | 写 `<Audio 1> is the voice-timbre reference for <Subject 1> (S1).` + `retention_analysis: <Audio 1>: reference - …` | 25.3.4、25.5 |
| 22 | 5 秒里塞了 3 个「镜头」 | H3 的时长承载是硬约束：4–15 秒；每个镜头最好只有一个主要动作目标 | 5 秒只保留「叠凳 + 那半秒泄气 + 收回」这一个动作目标，不加新信息 | 7.4、6.1 |

### 9.6 落地到 LingCut 的操作改动（对着现在的流程逐条改）

| 现在怎么做 | 改成怎么做 | 依据 |
|---|---|---|
| 视频节点提示词 = 中文板式（首句「画面无任何字幕」+ 镜头1/2/3 + 【】块） | 提示词 = H3 六段式（Ref2VA）或三段式（只有一张分镜图时 I2VA）；字段名英文 | 5、13、24.2、25.2 |
| 台词用 `{}` 嵌进镜头、【声音】块写声线 | 台词用 `(S1) says: <d>[Chinese] …</d>`；声线/语速/情绪写在 `<d>` **外**；环境声与配乐拆到 `overall_soundscape` / `non_diegetic_music` | 10.2、12.1 |
| 角色一致性靠「【一致性】全片锁定…」 | 角色一致性靠 `<Subject N>` 固定描述（**逐字复用同一短语**）+ `retention_analysis: fully_preserved` + 每条视频都重贴 | 9.1、9.2、25.5 |
| 靠「【约束】不要多余人物」防串味 | 靠 `<Subject N>` 只给一个主职责 + 参考图裁净背景人 + 生成后 QA | 13.6、14.5、16 |
| 靠「画面稳定不闪烁、光影细腻、电影质感」提升观感 | 删掉；改为具体摄影事实（光源方位/软硬、景深、颗粒、24 fps + 每段一个主运镜） | 23.4、8.3 |
| 音频节点连上后只在提示词里写「@音频1 锁音色」 | 写成 `<Audio 1> is the voice-timbre reference for <Subject N> (S1).`，让 H3 知道它参考的是**音色**而不是台词内容 | 25.3.4 |
| 一条 15 秒里排 5–7 个镜头号 | 一条视频 1–3 个 Shot（2 个最稳）；4 个以上必然漂移，宁可拆条 | 7.4 |
| 时长按对白句数 ×1.3s 估 | 同公式估完再对 H3 上限复核（4–15s）；面板可选 5/8/10/12，台词宁可拆段不要加速 | 10.6、LingCut 面板限制 |
| 生成后用 2fps 抽帧看 | 保持，并按 H3 官方四层验收清单逐层过（文件层/画面层/音频层/连续性层） | 18 |

### 9.7 替换用骨架（把手册里第 8 节的模板换成这个）

**骨架 1：单人/单场景镜头（我们最常用）**

```text
subject_definitions:
<Subject 1> is <角色名> in <Picture 1>, with <脸型/发型/体型/服装写死>. <Picture 1> defines <身份要素> only.
<Subject 2> is <场景名> in <Picture 2>, with <6~10 个相互支持的环境元素>. <Picture 2> defines <空间要素> only.
<Picture 3> is the first frame of [Shot 1], showing <主体> in <场景>, framed as <景别>.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).     ← 只有真的有台词时才写

summary:
[reference generation + keyframe completion + audio reference] <一段话说清目标视频与参考关系>

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - <逐项列要保的>
<Subject 2> (appears in [Shot 1]): fully_preserved - <逐项列要保的>
<Picture 3> ([Shot 1] first frame): fully_preserved - <构图/机位/站位>
<Audio 1>: reference - <只参考音色，不复制原信号，不带入原台词>

detailed_description:
<1–2 句总体风格：live-action, cinematic, 24 fps, 光线条件>
[Shot 1] The shot begins from <Picture 3> and <机位：Static Shot / Push In with small amplitude at slow speed…>. <主体站位>。 <空间与光：光源方位+软硬+阴影行为>。 <动作状态链：触发 → 可见变化 → 结果>。 <台词：<Subject 1> (S1) says in <音色/语速/情绪>: <d>[Chinese] 台词</d> 说完 closes his mouth naturally>。 <余韵与结尾状态>。 <主体运动/环境移动细节>。
[Shot 2] At 00:0S.SSS, the camera cuts to <必须带新信息：新主体/新空间/新状态/新视角/关键反应>。…

overall_soundscape:
<1–4 句：环境底噪 + 物理动作声 + 非语言人声；不重复对白/歌词>

non_diegetic_music:
<1–3 句：乐器+速度+节奏+进入退出时机> / N/A
```

**骨架 2：只有一张分镜图（I2VA）**

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] <风格词>, the subject shown in <Picture 1> remains in the same opening composition, preserving <身份/服装/姿态/道具/空间布局>. <动作启动>. <连续发展>. <结果或反应>.

overall_soundscape: ...
non_diegetic_music: ...
```

**骨架 3：首尾帧（FL2VA，例如「他从站着到坐下」这类可插值动作）**

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 5.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] <风格词>, the shot begins in the exact state and composition established by Picture 1. <分步物理路径>. <中间可见变化>. The motion gradually settles into the pose, object state, lighting, spacing, and final composition established by Picture 2.

overall_soundscape: ...
non_diegetic_music: ...
```

### 9.8 改完之后的自检（贴完提示词、点生成之前，30 秒过一遍）

- [ ] 模式对不对？（有角色图/场景图/音频 → Ref2VA；只有一张首帧图 → I2VA）
- [ ] 字段名与顺序是不是官方那三/六个？（没自创、没中英混排字段名）
- [ ] `[Shot 1]` 有没有手滑写时间戳？（不能写）
- [ ] 后续 Shot 是不是 `At 00:SS.mmm`，且严格递增、小于总时长？
- [ ] 台词是否只在 `<d>[Chinese] …</d>` 里出现**一次**？`<d>` 外有没有塞表演说明？
- [ ] 有台词的说话人有没有稳定 `(Sx)`？没台词的镜头有没有**误分配** ID？
- [ ] 旁白是不是 `says in an off-screen voiceover` + `lips remain completely closed`？
- [ ] 声音是否分到四层里了？配乐没有就写 `N/A`？
- [ ] 每个 `<Subject N>` 是不是只有一个主职责？同一人物有没有换同义词？
- [ ] 抽象词（`电影质感`/`光影细腻`/`克制的疲惫`/`画面稳定不闪烁`）清干净了吗？
- [ ] 5–15 秒里塞了几个动作目标？超过一个就砍。
- [ ] 生成后：2fps 抽帧 → 查「同一个人 / 表情是活的 / 口型对得上配音 / 没有模型自编台词 / 没有多余字幕文字水印 / 没有多余人物 / 动作连贯 / 运镜在节拍处停下」。



