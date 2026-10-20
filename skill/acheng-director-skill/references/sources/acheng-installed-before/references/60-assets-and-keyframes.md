# 通用资产与关键帧设计规范 (Assets & Keyframes Guide)

当剧本与分镜确认后，需要建立角色三视图、场景概念图、关键道具设定图、**16 宫格分镜接触表 (16-Panel Storyboard Contact Sheet)** 以及提炼下游视频生成所需的“决定性瞬间关键帧 (Keyframes)”时读取本文件。
本文件生产的静态图像资产，是下游 **MiniMax H3** 运行 `I2VA (首帧生视频)`、`FL2VA (首尾帧生成)` 与 `Ref2VA (全参考模式)` 的绝对真值底座。

---

## 1. 资产真值源三支柱规范 (The Three Asset Pillars)

### 1.1 角色圣经 (Character Bible) 与四面设定图标准工程 (4-View Character Sheet)
深度吸收盛唐 900 资产大师标准，角色资产图必须满足“多面板为同一人物，不出现同风格不同脸”的工业底线：
- **四面基准图 (4-View Turnaround Sheet)**：严格拉平正视图 (Front)、3/4 侧视 (Three-Quarter Side)、纯侧视 (Profile)、背视图 (Back)。
- **水平基准标尺线 (Horizontal Registration Lines)**：四面图必须处于严格水平参考线上（头顶线、眼平线、下颌线、肩峰线、腰腹线、膝盖骨线、足底触地面完全拉齐）。
- **五官骨相与面相三维锁定协议 (3D Facial Landmark Lock)**：
  * **眉骨与眼眶骨**：眉弓高度、眼距（标准 1 眼睛宽度）、眼窝凹陷深度；
  * **鼻梁与鼻尖**：鼻梁骨节微突起伏、鼻翼基底宽度、鼻尖微翘或微鹰钩角度；
  * **人中与嘴唇**：人中沟深浅、上唇丘比特弓形态、嘴角下沉/微扬倾向、唇线清晰度；
  * **下颌轮廓与下巴**：下颌角转折点（耳垂下方 1.5-2.0cm）、下巴前突量与颏部平整度；
  * **面相绝对不可漂移项**：标志性疤痕深度、泪痣坐标、义肢接口锁钉，在不同角度严格保持三维自洽。
- **四面设定图专用提示词生成模板 (Turnaround Prompt Blueprint)**：
  ```text
  A professional character concept design turnaround sheet, 4-view model sheet (front view, three-quarter view, profile view, back view) aligned on the same horizontal baseline.
  - Subject: [Character Name], [Age], [Morphological Archetype from references/50-character-morphology.md], [Exact Facial Landmarks & Hair].
  - Costume & Rigging: [3-Layer Drape Logic: Inner, Mid-Armor, Outer Drape, Belt & Holsters].
  - Lighting: Studio neutral rim lighting for structure display, 5500K neutral color temperature, soft fill light, clean solid gray background (#808080), identical lighting across all four views.
  - Quality & PBR: PBR specular response, matte fabric weave, scratched alloy bevels, zero split face, photorealistic clean render --ar 16:9 --v 6.1
  ```

### 1.2 场景母图与关键帧五大工作模式 (The 5 Keyframe Work Modes)
完全继承盛唐 900 场景关键帧大师体系，制作场景资产与关键帧必须明确其工作模式：
1. **模式一：画风母图 (STYLE MOTHER)**：
   - **目标**：建立整部作品可迁移的统一视觉 DNA，优先表现建筑、光照、空气介质与色彩基调，不让单个人物抢占画面；
   - **规格**：单张 16:9 或 2.39:1 横版，24-35mm 广角，平视或微俯，主地标完整，人物仅作微小尺度参照。
2. **模式二：场景建立关键帧 (ESTABLISHING FRAME)**：
   - **目标**：锁定具体地理空间骨架、时间天气、统治主光与连续性锚点，供后续场次持续复用。
3. **模式三：叙事关键帧 (NARRATIVE KEYFRAME)**：
   - **目标**：锁定一个不可替代的剧情因果瞬间。人物、道具与光影共同讲故事，画面即使静态也能让人读懂前因后果。
4. **模式四：动作关键帧 (ACTION KEYFRAME)**：
   - **目标**：锁定动作最具戏剧势能的单一相位（蓄力极限、即将接触前 0.1 秒、接触碰撞冲击瞬间、反作用分离）。严禁用大面积运动模糊掩盖结构错误。
5. **模式五：连续分镜组 (CONTINUITY SERIES)**：
   - **目标**：多张图共享同一 Visual Bible，保持同一角色、同一场景、同一光源高度与色温连贯递进。

### 1.3 电影级场景灯光架构四重奏 (The 4-Tier Lighting Architecture)
场景母图与分镜关键帧严禁平光，必须严格架构四层光学光路：
1. **第一层：统治性主光 (Key Light)**：单一物理光源（日暮斜射、探照灯束、暴风雨闪电），决定全图 80% 的受光朝向与投影矢量；
2. **第二层：侧逆光/轮廓光 (Rim Light)**：冷硬的高反差边缘光，精准勾勒出主体肩颈、发丝与装甲边缘，将主体从复杂深色背景中利落剥离；
3. **第三层：环境漫反射补光 (Ambient Bounce)**：由地面与周围墙体反弹的柔和弱光，控制暗部细节可读性，严禁暗部死黑糊死；
4. **第四层：局部物理点光 (Accent / Foley Light)**：仪表盘微弱 HUD 辉光、枪口残焰、刀刃寒芒，仅作高光点缀，绝不抢夺主光统治权。

### 1.4 道具与载具圣经 (Prop & Vehicle Bible)
- 涉及战斗的武器（枪械口径、战刃反光、机械外骨骼握把）、剧情核心信物（怀表、钥匙、加密芯片）必须具备单独特写资产图，锁定微观刻线与材质成色。

---

## 2. 16 宫格分镜接触表生成规范 (16-Panel Storyboard Sheet)

在 MiniMax H3 高阶 Ref2VA 工作流中，最强大的参考资产是 **4x4 格式的 16 宫格分镜接触表 (`<Picture 1> 16-panel storyboard contact sheet`)**。它在一张高分辨率图像中同时锁定连续 14 秒内的机位景别、视线轴线、角色构图与动作演进。

### 2.1 16 宫格排版与镜头切片规划
- **4x4 网格布局**：
  ```text
  [Panel 01] [Panel 02] [Panel 03] [Panel 04]  ──▶ 对应 Shot 1 (00:00 - 00:03.5)
  [Panel 05] [Panel 06] [Panel 07] [Panel 08]  ──▶ 对应 Shot 2 (00:03.5 - 00:07.0)
  [Panel 09] [Panel 10] [Panel 11] [Panel 12]  ──▶ 对应 Shot 3 (00:07.0 - 00:10.5)
  [Panel 13] [Panel 14] [Panel 15] [Panel 16]  ──▶ 对应 Shot 4 (00:10.5 - 00:14.0)
  ```
- **景别推进曲线**：通常遵循经典电影叙事曲线：
  `Panel 01 建立大远景 ──▶ Panel 02-04 主体进场与中景 ──▶ Panel 05-08 心理反应特写与反打 ──▶ Panel 09-12 冲突爆发与动作攻防 ──▶ Panel 13-16 高潮对峙与悬念定格`。

### 2.2 16 宫格图像提示词编写标准 (MJ / FLUX Prompt Syntax)
```markdown
A professional 16-panel storyboard contact sheet, 4x4 grid layout, cinematic movie sequence, Hollywood sci-fi blockbuster aesthetic.
- Character: Lin Yuan (consistent 32-year-old male soldier, scarred cheek, modular titanium exoskeleton armor).
- Scene: Destroyed industrial titan hangar, cracked concrete floor reflecting cyan floodlight, rainy atmosphere.
- Panels progression:
  Panel 01: Extreme wide establishing shot of the destroyed hangar entrance in deep fog.
  Panel 02-04: Medium low-angle tracking shots of Lin Yuan walking in with plasma carbine.
  Panel 05-08: Close-ups of Lin Yuan discovering severed cables, jaw tightening in realization.
  Panel 09-12: Upper catwalk reveal of cybernetic Renaud stepping into light with smoking arm.
  Panel 13-16: Two-shot dynamic tension, weapons drawn simultaneously, cinematic standoff.
2.39:1 aspect ratio per cell, consistent lighting, clean grid borders, high definition, photorealistic finish --ar 16:9 --v 6.1
```

### 2.3 全盘深度接入 im2-image-skills (IM2 Clean Image) 工业级生图总控引擎

在影视工业管线中，静态资产图与 16 宫格分镜接触表是下游视频大模型（MiniMax H3 / FLUX）的绝对真值底座。若静态图存在“塑料反光、脏 AO 污圈、纹理密恐、结构飘轻”，下游视频生成必将全盘崩溃。
本系统全盘深度接入红猴子开源体系 **`im2-image-skills`**（开源项目源于 [https://github.com/q2522879285-source/im2-image-skills](https://github.com/q2522879285-source/im2-image-skills)，本地对应已装载全局技能 `im2-clean-image`），作为所有角色设定图、场景母图、分镜接触表与首尾关键帧生图的强制底层协议。

#### 2.3.1 7 步标准提示词构建序列 (Default 7-Step Prompt Order)
所有静态资产提示词必须严格按照以下 7 步时序逐层装配，严禁颠倒逻辑：
1. **主体与动作环境 (Subject, Identity, Pose, Action, Setting)**：锁定角色/道具主体、体态比例、核心动作相位与所在环境。
2. **视觉媒介与流派风格 (Style or Medium)**：锁定目标摄影机/底片（如 ARRI ALEXA 65 IMAX 70mm）或艺术媒介（如写实 CG、厚涂、水墨）。
3. **摄影构图与视觉层级脚手架 (Camera, Composition & Hierarchy Scaffold)**：锁定镜头景别、视线轴线、主导形体块面、视线引导线与呼吸留白区。
4. **真实光路链与英雄材质层 (Light Path & Hero Surfaces)**：先解算完整物理光路，再赋予主体英雄材质的精确物理响应。
5. **距离与信息密度衰减层 (Distance & Information-Density Falloff)**：明确焦点机制微观细节，强制非关键区域与远景信息衰减。
6. **受控细节与洁净渲染层 (Controlled-Detail Clean Layer)**：采用专业受控材质语言，彻底替换 AI 浮躁噪点与塑料反光。
7. **负向提示词卫生层 (Negative Hygiene Layer)**：靶向防御伪影、杂色、解剖畸变与劣质材质，杜绝旧项目污染与反向召唤。

#### 2.3.2 英雄材质分级与标准句式骨架 (Hero Surfaces & Physics Skeleton)
严禁使用单一生硬的 `glossy / shiny / reflective / ultra realistic`，必须指明主材质类别与光敏响应：
- **英雄材质句式金标准骨架 (Sentence Skeleton)**：
  ```text
  The [hero material] shows [physical behavior] under [lighting condition], with [local imperfections/topology] visible at [camera scale]; [specific areas] remain [matte/dry/absorbing] while [specific edges/surfaces] catch [soft/sharp/specular/anisotropic] highlights.
  ```
- **典型材质物理响应分配**：
  * **哑光钛合金/机甲装甲**：`matte porous response, worn edges catching narrow anisotropic highlights, oxidized flats absorbing light, no uniform chrome gloss`。
  * **皮肤与面部微观拓扑**：`natural facial planes, matte skin with soft specular highlights, subtle pores visible only at close range, clean eye catchlights, no waxy gloss`。
  * **布料与战术服**：`geometry-aware weave structure, raised fibers catching grazing rim light, natural fabric drape following gravity, no flat printed texture`。
  * **吸光粗糙地面与油污**：`porous concrete absorbing light, shallow puddles carrying controlled specular reflections, strict wet/dry boundaries, no global oily wetness`。

#### 2.3.3 真实光路守恒链 (Physical Light-Path Conservation Chain)
场景与资产图严禁随处乱设光源，在撰写提示词前必须闭环推演一条物理光路：
```text
光源位置与尺寸 (Source Position & Size)
       │
       ▼
遮光物与透光开孔 (Aperture / Occluder)
       │
       ▼
参与介质 (Participating Medium: 雾气/粉尘/湿度/烟气)
       │
       ▼
第一受光面 (First Receiving Surface)
       │
       ▼
投射阴影矢量 (Cast-Shadow Direction & Contact Grounding)
       │
       ▼
反弹与反射光路 (Bounce / Reflection Path)
       │
       ▼
曝光与高光滚降 (Exposure & Highlight Rolloff)
```
- **统治主光唯一性**：锁定单一主光源，补光与轮廓光绝不可喧宾夺主，所有阴影矢量与反射亮点必须与主光源几何完全自洽。
- **体积光与介质物理性**：丁达尔光束与体积光绝非凭空装饰，必须有明确参与介质（如悬浮粉尘、雨后水汽），且光束必须被实体障碍物真实遮挡。

#### 2.3.4 信息密度分配律与缩略图自检门禁 (Density Allocation & Thumbnail Acceptance)
画面信息必须呈层级分布，严禁“满屏处处是细节”：
- **焦点区 (Focal Zone)**：只在角色双眼、枪口/刀尖接触点、动力咬合关节集中高频边缘对比与微观刻线。
- **支撑区 (Support Zone)**：中等尺度形体，仅保留足以交代空间结构与动态趋势的几何轮廓。
- **呼吸静音区 (Quiet / Depth Zone)**：背景穹顶、暗部阴影底盘、远景地貌，强制降低纹理频度与对比度，让形体自然融入空气散射或阴影中。
- **缩略图 4 维自检门禁 (Thumbnail Check)**：
  1. 缩放到 10% 缩略图尺寸时，全图存在且仅存在 1 个绝对视觉视觉锚点；
  2. 至少保留 1 处大面积平滑低频呼吸静音区，无细碎填料噪点；
  3. 背景边缘频率与明暗对比度显著低于焦点区；
  4. 绝无死黑糊死或死白过曝，阴影底盘结构清晰可辨。

#### 2.3.5 高危生词审查与专业词汇替换表 (Risky Phrase Replacements)
在大模型提示词中，堆砌口水形容词会导致画面质感油腻发脏，必须强制执行以下替换映射：

| 严禁使用的口水污染词 | 强制替换的专业工业级描述 | 替换原因与画质提升机制 |
|---|---|---|
| `ultra detailed / hyper detailed` | `clear focal/support/quiet detail hierarchy, selective fine detail` | 消除 AI 在非焦点区域胡乱生成的密恐噪点与多余刻线 |
| `micro detail everywhere` | `detail concentrated only on meaningful surfaces` | 将计算算力聚焦于核心构件，保留大块面呼吸空间 |
| `wet glossy / super shiny` | `subtle reflections with strict wet/dry boundaries` | 消除全图涂抹劣质甘油般的“塑料反光”，建立真实物理干湿边界 |
| `cinematic bokeh everywhere` | `organized low-frequency background with selectively softened depth layers` | 防止暴力模糊算法抹杀场景空间纵深，转为自然光学景深递进 |
| `dark atmospheric background` | `smooth dark tones with readable shadow floor, low texture background` | 防止暗部产生脏噪点与死黑，确保阴影底盘细节通透可读 |
| `realistic texture` | `physically distinct material response with natural texture only` | 指明材料本身的粗糙度与反射各向异性，杜绝伪纹理 |
| `no blur / no clutter` (负向乱用) | 转换为正向约束：`sharp hero silhouette, clean negative space` | 避免因提到“blur/clutter”而在潜空间中意外激活模糊与杂乱概念 |

---

### 2.4 im2-image-skills 6 大电影级出图专精配方库 (The 6 Production Clean Prompt Recipes)

本库提炼自 `im2-image-skills` 核心资产库（`references/clean-prompt-recipes.md`），为不同题材的 2D 资产图提供开箱即用的工业级装配模式：

#### 配方 1：角色人像专精配方 (Portrait Recipe)
```text
[subject and identity], [pose/expression], [wardrobe/environment/style]. Natural facial planes, clean eye catchlights, matte skin with soft specular highlights, subtle pore texture and peach fuzz visible only at close camera distance, hair grouped into readable natural strands, fabric weave visible only on close visible cloth, protected highlight texture, smooth highlight rolloff, soft diffused key light with gentle bounce, clean rendering, focal detail concentrated on face and gesture, broad calm support masses, controlled material rendering, clean gradients, organized low-frequency background with selectively softened depth layers, minimal repetitive patterns.
Avoid: waxy skin, dirty pore noise, hidden face marks, ghost texture, latent artifacts, noisy bokeh, low-contrast residual textures, watermark-like marks, uniform plastic gloss, dirty AO halos.
```

#### 配方 2：黑暗/夜戏/低照度专精配方 (Dark Scene Recipe)
```text
[subject and action] in [dark environment]. Smooth dark tones with readable shadow floor, clean value separation around the hero silhouette, low texture background, controlled rim light, localized contact shadows in seams, protected highlight texture, subtle reflections only on intended surfaces, clean rendering, one clear focal detail cluster, broad quiet shadow masses, natural texture only, controlled highlights, minimal repetitive patterns.
Avoid: muddy shadows, noisy bokeh, background artifacts, ghost texture, latent artifacts, hidden marks, low-contrast residual textures, over-sharpened grime, dirty AO halos, crushed blacks, milky reflections.
```

#### 配方 3：奇幻/高密度宏大场景专精配方 (Fantasy & Dense Architectural Scene Recipe)
```text
[hero subject] in [fantasy environment], 3–7 large readable shape groups, one or two focal detail clusters, continuous calm masses, detail strictly reserved for the hero mechanism, supporting forms simplified, distant terrain progressively lower-contrast and softer with selected contours dissolving into atmosphere, physically distinct stone/metal/fabric/skin responses, protected highlight texture, localized contact shadows in seams and overlaps, natural texture only where the camera can read it, clean gradients, controlled highlights, minimal repetitive patterns.
Avoid: repeated micro ornaments, random tiny symbols, dirty texture buildup, hidden marks, ghost texture, latent artifacts, low-contrast residual textures, muddy background noise, identical roughness across all surfaces.
```

#### 配方 4：载具/重装机甲/硬表面专精配方 (Vehicle & Hard-Surface Mecha Recipe)
```text
[vehicle or mecha object] in [environment]. Intact readable silhouette, matte and satin panels separated by roughness and highlight width, worn edges only where hands, boots, airflow, hydraulic joints, or road contact would touch, micro-scratches and dust trapped in focal seams only, localized contact shadows under chassis and armor plates, protected highlight texture, controlled reflections obeying distance and roughness, clean rendering, clear focal/support/quiet detail hierarchy, broad low-frequency environment masses, natural texture only.
Avoid: random damage, chaotic grime everywhere, uniform glossy metal, showroom-plastic surface, dirty AO halos, ghost texture, latent artifacts, repeated micro-pattern noise, floating parts without weight.
```

#### 配方 5：传统国风水墨/非写实绘画专精配方 (Painterly, Ink & NPR Recipe)
```text
[subject], [composition], [chosen painterly or ink style]. Intentional brush edges, clean negative space, controlled pigment texture, readable silhouette, material response preserved through value and edge behavior, selective fine detail on focal forms only, broad quiet pigment masses, supporting and distant contours selectively incomplete, smooth tone transitions, controlled highlights, clean rendering.
Avoid: random speckle, muddy texture buildup, repeated micro-patterns, dirty ink residue, ghost texture, latent artifacts, hidden watermark-like marks, pasted texture.
```

#### 配方 6：同色调/纯色/极简质感分离配方 (Same-Color / Monochrome Recipe)
```text
Although the palette is restrained, every major surface remains distinct through physical response: [surface A] is [value/temperature/material/roughness], [surface B] is [different response], and [surface C] is [different response]. Separate them with grazing light, controlled highlight width, contact shadows, edge response, and depth-dependent contrast rather than new colors or heavy outlines. Add clean rendering, clear focal/support/quiet detail hierarchy, broad calm masses, natural texture only, minimal repetitive patterns.
Avoid: objects merging into one plastic mass, identical roughness, identical highlight width, random accent colors, black outlines around every object, dirty texture buildup, latent artifacts.
```

#### 配方 7：脏输出一键清洗重铸模板 (Clean-Slate Rewrite Pattern for Dirty Outputs)
当 AI 初次生图产生“脏杂噪点、暗印水印感、低反差残留污渍”时，**严禁使用图生图 (Image-to-Image) 二次迭代去脏**（因为反复迭代只会放大潜空间脏纹理）。必须采用白板重铸语法：
```text
Regenerate the same concept as a clean-slate image: [lock subject, pose, composition, style, palette]. Preserve the main design and mood, but rebuild the rendering with 3–7 dominant shape groups, one or two focal detail clusters, at least one continuous calm area, progressively simplified non-focal and distant forms, physically distinct material classes, clean material separation, protected highlight texture, smooth highlight rolloff, localized contact shadows, details faithful to the selected visual medium and style, natural texture only where that medium calls for it, controlled highlights, clean gradients, and minimal repetitive patterns.
Avoid: ghost texture, latent artifacts, hidden watermark-like marks, dirty texture buildup, repeated micro-pattern noise, muddy shadows, noisy bokeh, low-contrast residual textures, uniform plastic gloss, pasted-on texture, dirty AO halos.
```

---

### 2.5 重型场景结构锁定与单变量 8 重排错闭环 (Structure Lock & Single-Variable Retry Loop)

源自 `im2-image-skills/references/heavy-scene-structure-and-mass.md`，面向机甲、巨构、基地、战舰等硬表面资产，建立不可动摇的物理承重与排错机制：

#### 2.5.1 硬表面结构 4 大物理锁定 (The 4 Structural Locks)
1. **开孔深度锁定 (Opening Depth)**：所有门窗、通风隔栅、检修舱口必须具备可见的内壁厚度与深度阴影，严禁平贴在表面像贴纸。
2. **构件承重支撑 (Structural Support & Mass Grounding)**：每根悬臂、重炮、推进器必须具备可见的液压挺杆、三角桁架或强化铰链支撑；着地点必须有受力接触阴影与微下沉感，严禁悬空漂浮。
3. **构件前后遮挡穿插 (Occlusion & Overlap)**：主体与背景建筑之间必须有清晰的前后层级穿插，通过空气散射与轮廓反差拉开纵深。
4. **表面接缝与局部 AO (Seam AO Grounding)**：仅在装甲咬合缝、螺栓沉孔、线缆凹槽处产生深色闭塞阴影，严禁在开阔平坦表面产生脏光晕。

#### 2.5.2 单变量 8 重诊断排错循环 (The Single-Variable Retry Protocol)
当资产图生成未达预期时，**绝对禁止推倒全部提示词重写**（全盘重写会导致已确认的优良构图与角色特征丢失）。必须锁定其他要素，**单次只微调以下 8 个变量中的 1 个**：
- **变量 1：比例基准物 (Reference Scale)** ➔ 补充护栏、标准门框或地砖尺度；
- **变量 2：地基咬合 (Ground Contact)** ➔ 强化接触阴影与地面碎屑；
- **变量 3：阴影底盘 (Shadow Floor)** ➔ 提升暗部通透度，防止死黑；
- **变量 4：遮挡穿插 (Overlap & Occlusion)** ➔ 增加前景遮挡构件拉开层次；
- **变量 5：开孔深度 (Opening Depth)** ➔ 强化壁厚与内壁阴影；
- **变量 6：介质浓度 (Medium Density)** ➔ 调节空气粉尘/雾气浓度；
- **变量 7：高光宽度 (Highlight Width)** ➔ 缩窄金属倒角高光反差；
- **变量 8：呼吸留白 (Quiet Mass)** ➔ 清除支撑区域的多余碎纹理。

---

### 2.6 负向提示词卫生守则 (Negative-Prompt Hygiene)
源自 `im2-image-skills/references/negative-prompt-hygiene.md`，负向提示词是安全约束槽，**绝非旧失败的记忆垃圾桶**：
1. **正向锁定优先**：在写 `no X` 之前，先在正向提示词中指明应该出现什么（如用 `single subject, empty surrounding space` 替代 `no extra people`）。
2. **严防旧项目特定名词污染**：绝不得把上一个失败镜头里的道具、人物、武器写进通用负向词中（如写 `no sword, no red car`），这会导致模型在当前镜头中意外激活剑或红车的联想。
3. **保持简短 targeted**：负向词集中防御“AI伪影、死黑、油腻塑料、脏光圈、肢体畸变、水印残影”等通用物理失真，通常控制在 2-3 行以内。

通用工业级负向标准块 (Universal Safe Avoid Block)：
```text
Avoid: dirty texture buildup, random micro-pattern noise, hidden watermark-like marks, ghost texture, latent artifacts, muddy shadows, noisy bokeh, low-contrast residual textures, over-sharpened grime, uniform plastic gloss, pasted-on texture, milky reflections, clipped highlights, crushed blacks, dirty AO halos, malformed anatomy when people are present, stray text or logo unless requested.
```

---

## 3. 电影级关键帧提炼四法则 (Keyframe Selection Heuristics)

视频大模型并不能无中生有，首尾关键帧的力学势能决定了视频生成的质感。关键帧挑选必须符合行业公认法则：

1. **决定性瞬间法则 (The Decisive Moment)**：
   - 挑选戏剧冲突最高潮、蓄力最饱满或攻击即将爆发的前 0.1 秒；或者命中后受力形变最剧烈的瞬间。
2. **状态突变交接点 (State Mutation Boundary)**：
   - 角色从平静到暴起、从人类常态到机甲面罩锁死、从完整无缺到战损甲胄碎裂的临界帧。
3. **单帧单相位铁律 (Single Phase Principle)**：
   - 一张静态关键帧只能定格一个动作相位！严禁在一张图中试图表现“他正拔枪同时开枪并将敌人击飞”，必须锁定为“枪口微火喷薄、套筒后坐弹出的决定性一瞬”。
4. **首尾帧拓扑对齐 (FL2VA Topology Match)**：
   - 若用于首尾帧生成，首帧与尾帧的机位景别跨度不能超过两级（如中景到全景可行，但特写直接跨到大远景会导致模型空间解算崩溃）；且首尾两张图的角色服饰与场景光源必须严格同源。

---

## 4. 静态图像提示词生成器标准协议 (Image Prompt Standard)

在调用图像生成模型（如 GPT Image、FLUX、Midjourney 或 ComfyUI）制作资产图与关键帧时，提示词必须遵循严密的五段式结构装配：

```markdown
**[Prompt 结构规范]**：
[画风预设与画质锚点] + [主体人物/机甲详细物理规格] + [单相位动作与微表情外化] + [场景空间几何与环境材质] + [单一统治主光与光学摄影机参数]

**[好莱坞工业写实实战范例]**：
ARRI ALEXA 65 IMAX 70mm cinematic live-action film still, 2.39:1 anamorphic ratio. A battle-hardened 32-year-old male soldier (Lin Yuan), broad shoulders, wearing scratched titanium-alloy heavy exoskeleton armor with visible hydraulic lines and carbon-fiber plates. Lin Yuan's right hand tightly grips a tactical plasma carbine pointed forward, jaw clenched with intense resolve, subtle bead of sweat tracing down his temple, high facial micro-expression tension. Standing in a destroyed industrial titan hangar, cracked concrete floor reflecting pools of oil and rain puddles, shattered steel girders in the midground, dark smoking horizon in background. Single dominant high-angle 45-degree cool cyan floodlight cutting through volumetric haze and dust motes, casting long dramatic deep shadows, horizontal blue anamorphic lens flare streaks, photorealistic PBR metallic texture, ultra-high dynamic range, 8k resolution.
```

---

## 5. 下游 MiniMax H3 生成模式匹配路由

完成资产图与关键帧生成后，根据已有资产形态自适应路由下游视频生成模式：

| 输入资产具备情况 | 目标生成模式 | 调用参考规范 | 核心生成机制 |
|---|---|---|---|
| **仅具备 1 张起始关键帧图** | **I2VA** (Image-to-Video) | `references/70-minimax-h3-compiler.md` | 以首帧为绝对真值，向前演化 5s-10s 动态物理与对白 |
| **同时具备起始与终末 2 张关键帧** | **FL2VA** (First-Last Frame) | `references/70-minimax-h3-compiler.md` | 严格在首尾拓扑之间解算连续运动轨迹与形变 |
| **具备 16 宫格分镜表 + 角色设定图** | ★ **Ref2VA** (Full Reference) | `references/70-minimax-h3-compiler.md` | 6 大模块结构，16-Panel 逐格映射，双声场与台词同步 |
| **仅具备尾帧关键帧图** | **L2VA** (Last Frame Inversion)| `references/70-minimax-h3-compiler.md` | 从终局状态逆推合理的起手动作与运动收敛 |
| **无任何图像，纯文本创意** | **T2VA** (Text-to-Video) | `references/70-minimax-h3-compiler.md` | 纯文本构建完整视听时间线、环境与声场 |
