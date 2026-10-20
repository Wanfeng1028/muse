# AC Director（Acheng Director）场景设计专业模块｜用户使用指南

用户简称是 AC Director，技术调用标识仍为 `acheng-director`；本场景支路是 AC Director assets 分支下的专业设计顾问，不是第二套生产真值。

这份指南给用户直接复制提示词。把方括号中的内容替换成项目事实；不需要的可选行可以删掉。模板会明确告诉 Acheng Director 何时调用 moodboard、scene-design、assets、shots、effects、model、continuity 和 QA。

## 先选你要的结果

| 你现在要什么 | 在提示词中保留的模式词 | 主要输出 |
| --- | --- | --- |
| 从想法或 moodboard 设计场景 | `direction` | 场景设计合同、空间逻辑、视觉方向 |
| 把已批准场景变成图像提示词 | `prompt` | 独立图像提示词、上传清单、QA |
| 修复已有场景图或提示词 | `repair` | 保留事实的局部修订 |
| 同一场景做多视图或时天气版本 | `multi_view` | 共用锚点的多视图提示词 |
| 找出场景或提示词的问题 | `critique` | 分项 QA、最小结构修复 |
| 交给 Acheng 资产和镜头流程 | `handoff` | 场景合同、事实采纳表、交接回执 |
| 场景直接进入完整短片 | `full-production` + `scene-design` | 主线、镜头、资产、H3、连续性和场景支路的合并结果 |

触发词建议直接写出来：`场景美术`、`环境概念图`、`背景板`、`场景设计合同`、`空间结构`、`场景修复`、`多视图场景包`、`moodboard 转场景`、`scene-design`、`handoff to Acheng assets`。只写“做一张漂亮的图”可能不会触发专业场景支路。

## 所有请求都适用的最短模板

适合第一次使用，也适合没有 moodboard、没有参考图的原创项目。

```text
调用 Acheng Director，并按需调用 scene-concept-art-director 场景设计专业支路。

模式：direction
项目类型：[电影动画 / 游戏 / 广告 / 建筑 / 其他]
场景名称：[场景名称]
场景用途：[概念图 / establishing shot / background plate / set design / game environment / layout]
一句话创意：[这个空间最重要的画面和叙事作用]
时间与环境：[时代、地点、季节、昼夜、天气；不知道就写“请原创，但标记假设”]
必须保留的事实：[已有剧情、角色、道具、几何、镜头或连续性事实]
不要出现：[排除的元素、风格、文化误读、错误时代物件]
参考图：[无 / 文件路径和用途]
moodboard：[无 / data.json 或摘要]

请输出完整 scene_art_direction.json 对应的场景合同、场景 thesis、空间边界、入口出口、地标、动线、前中后景、尺度锚点、材质和使用痕迹、光源方向、色彩角色、气氛、参考图保留/排除规则、未决项和独立图像提示词。
没有参考图时先做原创设计；不要调用付费媒体模型；visual_status 保持 UNVERIFIED。
```

## 1. direction：从想法或 moodboard 做场景设计

这是最常用的入口。它会先解决空间怎么成立，再写提示词。需要 moodboard 时，把 moodboard 的已确认方向和未知项一起交给模型。

```text
调用 Acheng Director 的 scene-concept-art-director，执行 direction 模式。

目标：为 [项目/集数/场次] 设计一个可生产、可连续使用的场景。
场景 ID：[例如 SCENE_PORT_01]
场景功能：[人物在这里做什么；空间服务什么剧情]
主视觉命题：[观众三秒内应该感到什么]
主要矛盾：[宏伟但被维护痕迹侵蚀 / 神圣但正在失效 / 拥挤却孤独 / 自定义]
世界事实：
- 地点：[ ]
- 时代或技术阶段：[ ]
- 季节、昼夜、天气：[ ]
- 近期发生的事件：[ ]
- 场景外仍然存在的世界：[ ]
空间事实：
- 边界：[ ]
- 入口：[ ]
- 出口：[ ]
- 地标：[ ]
- 人物和镜头的主要动线：[ ]
- 前景：[ ]
- 中景：[ ]
- 后景：[ ]
- 尺度锚点：[人、门、车辆、工具、栏杆等]
设计事实：
- 主材质及老化方式：[ ]
- 人如何使用、维护、控制或逃离这里：[ ]
- 标志性物件：[ ]
- 文化或地域逻辑：[不确定就标记不确定]
- 光源及方向：[ ]
- 色彩角色：[主色 / 辅色 / 一个焦点色]
参考来源：
- moodboard：[文件路径或“无”]
- 参考图：[文件路径、用途、必须保留、必须排除]
- 已确认生产事实：[ ]

请先列出采用的来源和假设，再输出 scene-art-v1 场景合同和独立图像提示词。不要把 moodboard 自动当作 STYLE_MOTHER，不要捏造地理、历史或参考文件。输出必须能交给 assets、shots、effects、model、continuity 继续使用。
```

## 2. moodboard → 场景：让审美定调真正进入合同

如果有 moodboard，明确它只负责审美方向；场景几何、生产事实和连续性仍需单独确认。

```text
调用 moodboard-alignment 读取并总结以下 moodboard，再调用 scene-concept-art-director 执行 direction：

moodboard 文件或 data.json：[绝对路径]
项目场景：[场景名称和用途]
我确认可以采用的方向：[色板 / 构图 / 材质 / 气氛 / 风格节点]
我不希望继承的方向：[ ]
仍未确定的内容：[地点、时代、结构、功能、尺度等]
必须服从的生产事实：[ ]

请按以下顺序输出：
1. moodboard 中可采用、不可采用、待确认的方向，并保留来源；
2. 场景 thesis 和主要视觉矛盾；
3. 空间合同：边界、入口、出口、地标、动线、前中后景、尺度锚点；
4. 材质、使用痕迹、文化逻辑、光源和色彩角色；
5. scene_art_direction.json 对应对象；
6. 独立图像提示词和 unresolved；
7. 明确写出 moodboard 不是 STYLE_MOTHER，visual_status=UNVERIFIED。
```

## 3. prompt：从批准合同生成独立图像提示词

适合合同已经确定，只需要给 GPT Image、Flux 类或其他图像模型使用的独立文本。提示词和上传清单要分开。

```text
调用 scene-concept-art-director，执行 prompt 模式。

基准场景合同：[粘贴 scene_art_direction.json 或文件路径]
目标模型族：[gpt-image / flux-like / sdxl-like / midjourney-like / model-neutral]
输入模式：[text / edit / mixed]
输出用途：[概念图 / establishing shot / background plate / set design / layout]
画幅和尺寸：[只写已确认或留给模型适配器判断]
真实参考文件：[绝对路径、每个文件的作用]
每个参考必须写：role、preserve、exclude、approval 状态；有文件时计算 SHA-256。

请输出四个彼此独立的文件内容：
1. scene-<scene_id>.image.txt：只放模型可执行的场景描述，不放上传说明、不放内部 ID；
2. UPLOAD.md：上传顺序、槽位、用途、必须保留、禁止继承；
3. index.json：合同版本、输入模式、参考文件、模型适配参数、prompt_status；
4. qa.json：空间、材质、光线、尺度、文化逻辑和矛盾检查。

先使用正向场景事实，再单列排除项；不要把 8K、120fps、seed 或未验证的供应商参数写成场景事实。prompt_status 只有在文本和必需输入齐全时才能是 READY_TO_SUBMIT；visual_status 必须是 UNVERIFIED。
```

## 4. repair：只修一个问题，不重做整张图

必须写清保留什么、改变什么。没有真实输入图时，只能修提示词合同，不能声称完成图像修复。

```text
调用 scene-concept-art-director，执行 repair 模式。

场景合同或原提示词：[文件路径或粘贴内容]
真实输入图：[绝对路径；没有就写“没有真实图，仅修订提示词”]
问题只限于：[例如“入口方向与动线冲突”]
必须 PRESERVE_EXACTLY：[角色位置、建筑比例、地标、主材质、光源方向、色彩角色等]
允许 CHANGE：[只列本次允许变化的字段]
禁止改变：[剧情事实、已批准几何、镜头目标、连续性状态]

请用 CHANGE / PRESERVE_EXACTLY / REBUILD 三类记录完成一次局部修订：
- 先指出问题和证据；
- 给出最小结构修复；
- 重新输出受影响的 scene-art-v1 字段和独立图像提示词；
- 保留未受影响的事实；
- 若参考图真实存在，校验文件和 SHA-256；
- 没有真实输出时保持 visual_status=UNVERIFIED。
```

## 5. multi_view：同一场景的多视图、布局和时天气版本

不要把每个视图当成新场景。先锁定 base contract，再声明每个视图的 delta。

```text
调用 scene-concept-art-director，执行 multi_view 模式。

基础场景合同：[文件路径或粘贴内容]
基础场景 ID：[ ]
需要的视图：[可多选：establishing / background_plate / layout / elevation / keyframe / time_weather]
每个视图的用途：[ ]
必须完全一致的共享锚点：[地点、空间语法、地标、入口出口、比例、主物件、材质家族、重力支撑、光源与受光关系]
允许变化：[镜头、天气、昼夜、人物姿态、损坏状态、前景简化等]
每个视图的新增事实：[ ]

请先建立 shared anchors，再为每个视图输出：view_id、purpose、preserve、deltas、prompt_status、visual_status、独立图像提示词和 QA。若视图之间发生几何、光线或连续性矛盾，指出冲突并交给 shots/effects/continuity，不要用新视图掩盖矛盾。
```

## 6. critique：批评场景或提示词，并做最小修复

适合已有 prompt、合同或真实图片。真实图片必须提供文件路径；只有文本时只做文本 QA。

```text
调用 scene-concept-art-director，执行 critique 模式。

待评对象：[scene_art_direction.json / image prompt / 真实图片绝对路径]
项目用途：[概念图 / 背景板 / 镜头场景 / 游戏环境 / 其他]
已确认事实：[ ]
我最担心的问题：[空间不成立 / 太泛 / 光线冲突 / 文化混搭 / 没有尺度 / 模型读不懂 / 其他]

请按 1–5 分检查：scene thesis、视觉焦点、空间一致性、文化具体性、材质逻辑、光源动机、色彩纪律、生产设计、人类尺度、原创记忆点。
输出：
1. 最高优先级的一个问题和证据；
2. 一个结构性修复；
3. 一个具体使用/维护/劳动细节；
4. 应删除的装饰噪声；
5. 修复后的受影响字段和独立提示词；
6. 如果没有真实生成图，明确 visual_status=UNVERIFIED。
```

## 7. handoff：把场景设计交给 Acheng assets

这是把专业场景结果纳入完整制作的关键模板。scene skill 提议事实，assets 决定是否采纳。

```text
调用 Acheng Director，并在 assets 分支中调用 scene-concept-art-director，执行 handoff。

请求 ID：[ ]
场景合同：[文件路径]
场景提示词和上传清单：[文件路径；没有就先生成]
来源：[brief / moodboard data.json / 既有 scene_registry / 真实参考图]
已批准生产事实：[ ]
必须冻结的事实：[空间几何、入口出口、地标、角色站位、镜头目标、连续性状态]
可供场景支路建议但不能直接写入的事实：[ ]

请输出：
1. 场景合同和所有独立提示词产物的路径、版本、SHA-256；
2. proposed_facts：每条注明 adopted / rejected / deferred、reason、source；
3. assets 最终可合并到 scene_registry 和 asset_cards 的事实；
4. shots、effects、model、continuity 各自可读取但不能越权写入的建议；
5. advisory_patch.write_paths=[]；
6. 未决项、阻塞项和 evidence；
7. prompt_status 和 visual_status，真实图像未人工验收时保持 UNVERIFIED。

不要直接修改 production.json、ShotSpec、VFX、H3 正文或 continuity ledger。
```

## 8. 和 Acheng 其他支路一起用

### 8.1 场景 + assets：资产依赖和图像提示词

```text
在本次 Acheng Director 任务中启用 scene-design 和 assets。
场景支路先输出 scene-art-v1 合同，再由 assets 合并批准的场景事实。
资产顺序：[角色身份 → 服装状态 → 伤势状态 → 场景 → 道具 → 特效 → 关键帧]
场景必须提供：[空间边界、入口出口、地标、材质、光源、尺度锚点、参考图保留/排除]
每个资产必须独立可用，并标记 READY_TO_SUBMIT 或 DRAFT_MISSING_REFERENCES。
不得把场景支路的建议直接当作最终 production 真值。
```

### 8.2 场景 + shots：让镜头能拍到、走得通

```text
启用 scene-design 和 shots。
scene-design 只提供空间几何、地标、动线、构图意图、遮挡和尺度约束；shots 负责景别、机位、焦段、运动、帧区间和切镜。
请检查每个镜头是否真的能看见所需地标，人物能否沿场景动线移动，前中后景和遮挡是否支持动作与叙事。
若场景建议与已确认 ShotSpec 冲突，保留 ShotSpec，记录 rejected/reason/source，不要静默改写。
```

### 8.3 场景 + effects：材质、空气、破坏和巨构尺度

```text
启用 scene-design 和 effects。
场景支路提供材质、空气、遮挡、光线和人类尺度；effects 负责 VFX、破坏、能量、尘雾、碎片和 scale_proofs。
请把每个特效的空间后果写清：影响哪个地标、遮挡哪条视线、改变哪种材质、留下什么尾态。
不要让 scene-design 直接写 VFX 字段，也不要让 effects 重写场景的基础几何。
```

### 8.4 场景 + continuity：跨镜头、天气和损坏状态

```text
启用 scene-design 和 continuity。
场景支路提出可见的天气、昼夜、损坏、物件位置和使用痕迹；continuity 决定哪些状态跨场景继承。
请建立 scene state ledger，至少记录：时间、天气、光源状态、入口出口可用性、地标损坏、道具位置、地面湿度/尘土、人物留下的可见痕迹。
任何未确认的状态写入 unresolved，不要假设它已经连续。
```

## 9. 场景 + MiniMax H3：把场景合同变成视频段输入

涉及 H3 时，提示词中明确要求加载 `h3-prompt-writing` skill。scene skill 提供场景事实，H3 skill 负责最终 H3 结构；不要在 scene prompt 中自行发明第二种 H3 格式。

```text
调用 Acheng Director 的 model 分支，并加载 h3-prompt-writing skill。
先读取 scene_art_direction.json 和已批准的 shots、performance、continuity 事实。

H3 模式：[T2VA / I2VA / FL2VA / L2VA / Ref2VA]
Segment ID：[ ]
时长：[4–15 秒内的具体时长；按项目合同执行]
起始状态：[角色、位置、朝向、道具、场景状态]
结束状态：[位置、朝向、速度相位、道具、场景状态]
场景事实：[完整写出空间、入口出口、地标、前中后景、材质、光线、尺度]
动作事实：[按时间顺序写预备、动作、反应、收势]
镜头事实：[景别、机位、运动类型、路径、方向、速度、目标]
声音事实：[环境声、动作声、对白；对白保留原文]
参考图：[真实文件路径和用途；没有就写无需上传]

请输出独立可复制的 H3 正文。基础模式严格使用并按顺序输出：
integrated_multimodal_description
overall_soundscape
non_diegetic_music

Ref2VA 严格使用并按顺序输出：
subject_definitions
summary
retention_analysis
detailed_description
overall_soundscape
non_diegetic_music

每个 Segment 重新写完整场景与主体事实，不使用“同上”“沿用上一段”。没有真实参考图时不要伪造 Picture/Video 标签；真实媒体未生成，visual_status=UNVERIFIED。
```

### H3 模式怎么选

| 模式 | 用户应该写什么 |
| --- | --- |
| T2VA | 没有参考帧，从文字生成完整场景和动作时间线 |
| I2VA | 提供真实首帧，写清首帧中必须保留的场景几何和主体状态 |
| FL2VA | 提供真实首帧和尾帧，写清两帧之间允许发生的连续变化 |
| L2VA | 提供真实尾帧，写清如何从合理前态收束到尾帧 |
| Ref2VA | 提供多类真实参考，写清每个 Subject/Picture/Video/Audio 的角色和保留关系 |

Ref2VA 是有真实参考图、角色、场景、动作或风格资产时的首选。锁定模式后，`detailed_description` 按片段时长与复杂度动态计算最低词数和目标词数（默认 10 秒简单段为最低 2,000、目标 2,400 个英文词），极限值 2900 词硬性封顶（处于 2200-2900 词区间，剔除无上限输出）；每个镜头都要展开主体外观、空间位置、朝向、光线、起始状态、触发事实、动作因果、微动作、微表情、接触／受力、相机路径、声音时序和尾态。若达到宿主单次输出上限，按字段和镜头续写并保留游标，不能摘要化、写“同上”或静默切换模式。

## 10. 没有参考图时的原创资产模板

```text
当前没有任何参考图。请不要等待我上传，也不要伪造参考文件。
先原创设计并输出：
1. 场景合同；
2. 场景独立图像提示词；
3. 若需要角色/道具/关键帧，按资产顺序分别输出独立提示词；
4. 每个产物写清“无需上传参考图，可原创生成”；
5. 记录哪些事实是原创假设；
6. 不把原创设计标成已生成或已人工验收；visual_status=UNVERIFIED。
```

## 11. 参考图、文件和批准状态怎么写

不要只说“参考这张图”。每张图都用下面的行描述：

```text
参考文件：[绝对路径]
role：[scene_geometry / material / lighting / composition / character / prop / keyframe]
preserve：[必须保留的具体事实]
exclude：[禁止继承的姿势、文字、背景、光线、品牌或错误细节]
approval：[approved / provisional / rejected]
用途：[生成指导 / 编辑输入 / 首帧 / 尾帧 / 仅风格参考]
```

编辑、重建和混合模式必须提供真实文件。模型不确定文件是否存在时，应返回 `DRAFT_MISSING_REFERENCES` 或 `BLOCKED`，不能假设文件存在。

## 12. 长输出、续写和局部修改

把以下规则放在任何可能很长的请求末尾：

```text
如果单次输出接近上限：不要总结代替正文，也不要重新开始。
保存 continuation_required=true、current_cursor、已完成产物路径、当前 scene/segment/view 和下一节名称。
下一次从 current_cursor 继续，并保持已经锁定的场景事实、参考关系和版本号。
只有缺少用户决策、不可替代素材、权限或外部能力时才暂停，并说明最小阻塞信息。
```

## 13. 最终交付检查模板

```text
交付前请执行一次场景专业验收：
- 能否从提示词画出边界、入口、出口、地标和动线；
- 建筑或自然空间是否能站立、使用或被维护；
- 前景、中景、后景、尺度锚点和遮挡是否支持镜头；
- 材质、老化、文化逻辑和人类使用是否属于同一世界；
- 光源方向、颜色角色和空气透视是否一致；
- 参考图是否有 role、preserve、exclude、approval 和 hash；
- image prompt 是否脱离聊天仍然可用；
- H3 段落是否使用正确模式、字段顺序、参考标签、对白和尾态；
- 是否存在 shorthand、矛盾、未决项或未经授权的生产事实；
- prompt_status、visual_status、evidence 和 artifact 路径是否诚实。

请只修复最高优先级的结构问题，然后重新输出受影响产物和 QA 回执。不要把机器 PASS 写成真实媒体已经通过人工验收。
```

## 14. 一次完整场景生产的推荐模板

需要从创意一路做到 Acheng 合并时，直接使用这一段：

```text
调用 Acheng Director，按需调度 story、shots、performance、scene-design、assets、effects、model、continuity 和 audit。

本次明确启用：scene-design、assets、shots、model、continuity。
本次不需要：[effects / combat timing / Ref2VA / STYLE_MOTHER / 其他]

项目：[ ]
故事或场次：[ ]
场景用途：[ ]
视觉命题：[ ]
角色和动作：[ ]
场景事实：[ ]
moodboard：[无 / 文件路径]
参考图：[无 / 文件路径和用途]
总时长与 Segment：[ ]
目标 H3 模式：[ ]
必须冻结的事实：[ ]

执行顺序：
1. 先输出能力触发图和总控台；
2. scene-design 生成场景合同和独立场景提示词；
3. assets 审核并采纳场景事实，生成角色、道具、场景和关键帧资产提示词；
4. shots 把场景空间转成可拍摄的镜头和时间轴；
5. model 调用 h3-prompt-writing，按每个 Segment 输出独立 H3；
6. continuity 检查天气、损坏、道具、入口出口和尾态继承；
7. audit 输出机器验收、人工验收边界、证据和未决项。

所有资产和 H3 必须脱离聊天独立可用。不要使用“同上”“见前文”“根据需要调整”。不要调用付费媒体模型。真实媒体未生成，visual_status=UNVERIFIED。
```

这套模板的关键是明确“场景支路负责设计合同，Acheng 负责合并与生产事实”。这样既能让 scene skill 展开空间、材质、光线和人类使用逻辑，也不会抢走 assets、shots、effects、model 或 continuity 的权属。
