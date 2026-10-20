# 70｜H3 分模式编译合同

## 指南权威与已修正的误称

同时遵守[独立提示词交付合同](72-standalone-prompt-delivery.md)。每个Segment是独立生成请求，人物／场景定义及当前道具／伤势必须在本段重建；“同上”“A身材”“EX编号”不能进入模型正文。生成完成的清单必须说明本段要上传什么，不能要求用户从整个剧本自行猜测。

必须使用安装的 `h3-prompt-writing`。本包保存其 [base-en](sources/h3/base-en.txt) 和 [ref-en](sources/h3/ref-en.txt) 快照以便离线复核。公开来源自称 community prompting Skill；没有厂商证据时不把社区写法称为“MiniMax 官方 API schema”，也不把 H3 等同 Video-01。模型入口实际支持的时长、分辨率、帧率和参考数量由执行适配器核实。

正文英文；用户提供的对白、歌词与屏幕文字保持原语种。结构字段顺序固定，但不属于 API 请求参数。JSON 生产数据和最终提示词文本是两个层，不把内部 camera/previs/ledger 字段直接假装成厂商字段。

最终写出前必须执行[H3 最终格式编译门](111-h3-final-format-pass-v4.md)。该步骤只整理字段、引用标签、Shot 标题、说话人和全局声音结构；工程参数、动作细节、空间事实、镜头路径和声音时序全部保留。格式门失败时不能通过摘要化、删除参数或伪造参考标签绕过。

## 五模式与顶层结构

| 模式 | 真实输入条件 | 输出 |
|---|---|---|
| T2VA | 无帧图锚定 | integrated_multimodal_description → overall_soundscape → non_diegetic_music |
| I2VA | Picture 1 为首帧 | 精确首行＋上述三字段 |
| FL2VA | Picture 1 首帧、Picture 2 尾帧 | 精确首尾对齐行＋三字段 |
| L2VA | Picture 1 为尾帧 | 精确尾帧对齐行＋三字段 |
| Ref2VA | 图／视频／音频提供明确参考角色；有真实参考资产时优先采用 | subject_definitions → summary → retention_analysis → detailed_description → overall_soundscape → non_diegetic_music |

I2VA 首行逐字采用：

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

FL2VA 首行按实际 N 与 S.SS 填入：

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.
```

L2VA：

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.
```

首行后空一行。S.SS 是切片有效时长，不是作品总时长。FL2VA 优先单镜；用户明确多镜时最后 `[Shot N]` 收敛至尾图。尾图锚点写有效结束时刻，但面板 frame 仍使用最后可见帧，二者属于不同语义。

## Shot、切镜与格子

`[Shot 1]` 不加时间戳。后续用 `[Shot 2] At 00:03.500, the camera cuts to ...`，切点严格递增并小于切片结束；不要使用每镜括号时间范围代替指南格式。只有真实切换机位／信息才开新 Shot。同镜头推进不能再用“cut to close-up”暗藏剪辑。

基础模式 style 放在 `[Shot 1]` 后；Ref2VA 的媒介用一两句写在 `[Shot 1]` 之前。每镜展开构图、当前主体、屏幕位置、场景地标、光线、起始状态、触发事实、按时间顺序的动作与反应、接触与重量、相机机位／镜头／方向／路径／幅度／速度、同步声音来源与时序、对白节拍和结束尾态。body 中必须实际消费表演、攻防、VFX 和尺度条目；把 metadata 填满但提示词遗漏不算通过。编译器会为每镜写入独立详尽指令，质量门还会拒绝未消费的角色／场景／状态和 Ref2VA Subject。

16 格不是 16 个参考文件。`<Picture 1>` 可定义为整表规划图；逐个列 Panel 01–16 的 frame/shot/phase 映射，在当前 shot 明确使用的格号。格图只证明位置时 retention 应是 weak_reference 或说明局部保留，不能声称人物脸和材质 fully_preserved。示例使用真实随包灰模图，明确只传递构图和时间顺序。

## Ref2VA 标签与继承关系

Subject 表示可复用可见内容；Picture 表示具体图／帧／构图锚点；Video 表示编辑源、续写起点或全片节奏；Audio 表示独立音频或明确启用的视频音轨。视频含音轨不自动生成 Audio 标签。每个标签绑定确切 file 和 role，不允许无上传素材却写图片占位并声称可执行。

可见内容的 retention 标记为 fully_preserved、partially_preserved、attribute_transfer、weak_reference；音频为 fully_copy、partially_copy、reference、weak_reference。`fully_copy` 是完整最终音轨的 1:1 复用，若加任何新声音就不能用此标记。summary 任务前缀按真实关系选择 reference generation、keyframe completion、video editing、video continuation、audio reuse、audio reference，组合用 ` + `。

subject_definitions 中只因来源关系提到的 Picture 不一定需要独立条目，但必须在素材登记簿可解析。Ref2VA 的详细度要求见下方“Ref2VA 详细度、模式锁与续写”；不得把详细正文按 350–500 词的短模板压缩。

## H3 执行工序时序铁律（工序前置原则）

**严禁在资产图提示词未完成前抢跑撰写 H3 视频生成提示词！**
Acheng Director 严格规定工序时序：
1. **阶段一（资产图提示词全量完成与审核）**：首先必须将全套资产提示词全部撰写完成并输出交付包，包括风格母图（`STYLE_MOTHER.image.txt`）、各角色的纯粹四视图（`CHAR_*.image.txt`）、场景概念图（`SCENE_*.image.txt`）、核心道具图（`PROP_*.image.txt`）以及分段关键帧提示词（`KEYFRAME_*.image.txt`）。
2. **阶段二（H3 视频生成提示词撰写）**：在确认全套资产图提示词均已就绪且逻辑闭环后，方可启动 H3 视频生成提示词的编译。

## Ref2VA 详细度、字数极限值（2200-2900词）与模式锁

生成类 Ref2VA 的 `detailed_description` 是主要生产正文，不是摘要：
1. **动态密度与硬性上限（2200-2900 词）**：新任务按时长和复杂度计算动态密度，默认最低为 `max(2000, 时长秒数×200)`，目标为 `max(2400, 时长秒数×240, 最低词数+200)`（通常处于 2200+ 区间）。
2. **硬性上限 / 极限值 2900 词（彻底剔除无上限输出）**：**坚决杜绝“不设上限”规则！** 任何 Segment 的 `detailed_description` 词数极限值一律封顶在 **2900 词**。目标字数严格处于 2200-2900 词的安全精细区间。严禁无节制堆砌输出导致上万词爆仓，造成模型理解退化或上下文截断。
3. **内容展开质量**：combat、VFX、对白、多说话人、四镜头以上和多参考会增加有限复杂度预算（仍受 2900 词硬性封顶）。对白密度和具体指令优先；不得机械重复空话，但必须把每个镜头的主体外观、空间位置、朝向、光线、起始状态、触发事实、动作因果、微动作、微表情、接触／受力、相机路径、声音时序和尾态全部展开。不得把多个复杂镜头压成一段摘要。历史夹具只有显式 `prompt_detail_policy.profile=legacy_fixture` 才保留旧长度，新的用户任务不得使用该例外。

## H3 多参考图引用机制与【上传参考助手说明】（AI认知规范）

1. **视频 AI 认知特性与槽位代号**：
   视频生成模型（如 MiniMax H3）**完全不理解工程文件名或抽象ID**（如 `CHAR_LU_WUJIU.png` 或 `SCENE_CLIFF.png`），AI 在实际生成时只能理解并响应交互界面上传槽位对应的 `@图片1`、`@图片2`、`@图片3` 等标记。
2. **H3 多参考图组合原则（非单一风格图，画风在关键帧中继承）**：
   - H3 提示词**严禁只引用风格锚点图**！
   - **核心总领锚点：关键帧图（@图片1）**。因为画风、质感、光影基调在关键帧阶段已经完整继承了风格母图并得到落实，因此在 H3 阶段**画风直接对照关键帧即可**！提示词正文必须明确写出：“画风与画面整体基调严格对照@图片1（关键帧）的渲染质感与光影分布”，无需在 H3 中重复上传风格母图占槽位。
   - **场景图（@图片2）**：提供空间结构、环境纵深与建筑透视。
   - **主体角色四视图（@图片3）**：提供人物纯粹面容五官、发型与服装细节。
   - （**第二角色四视图（@图片4）**）：若有多人对手戏同框时引入。
   - （**核心关键道具图（@图片5）**）：**特殊规则**：一般情况下无需上传道具图，除非本段有特殊法宝、重要机制武器特写或关键交锋争夺；严禁滥用道具槽位导致上传混乱。
3. **【上传参考助手说明 / Upload Reference Guide】强制标配**：
   在输出每个 H3 提示词（`.h3.txt`）以及交付卡片时，提示词正文顶部必须配备清晰的上传指引：
   ```markdown
   【上传参考助手说明 / Upload Reference Guide】
   - @图片1: [关键帧文件名/ID] (职责: 关键帧起始锚点，统领首帧构图、光影及艺术画风基准)
   - @图片2: [场景设计图文件名/ID] (职责: 场景空间底板，提供环境空间纵深与光路透视)
   - @图片3: [主角人设图文件名/ID] (职责: 角色形象基准，提供纯粹面容、发型与服饰细节)
   - (@图片4: [第二角色人设图] / 可选: 对手戏角色)
   - (@图片5: [核心关键道具图] / 仅在有特殊道具特写或关键交锋时上传)
   ```
   并在正文中严格使用 `@图片1`、`@图片2`、`@图片3` 等指派对应职责。

每个 Segment 必须显式锁定 `mode`、`mode_lock` 与 `mode_selection_reason`。Ref2VA 是默认优先模式，但只能在真实参考文件存在时使用；续写和版本升级不得静默切换模式。达到宿主单次输出上限时按字段／镜头边界分段续写，保存 `current_cursor`，不得用短版替代长版。

## 声音、对白与显示文字

实体说话人在本次独立请求第一次实际发声时获得 `(S1)`；本段跨镜保持编号，下一独立切片重新按首次发声分配。作品身份使用内部character_id/姓名保持，导出index另存speaker_map；引用音色定义同步映射，不能因作品中的旧S2让新请求从S2起步。非发声角色不加 ID。首次说明年龄类型、声线和语速，身份、动作和声线在 `<d>` 外，里面只放语言和原台词：

```text
Lu Chuan (S1), an adult operator with a low, slightly rough voice, says: <d>[Chinese] 现在你来。</d>
```

旁白用 `says in an off-screen voiceover`，紧接 `</d>` 明确对应画内人物 lips remain completely closed。跨切镜一句话按指南在两端用 `<scenetrans>` 并说明 continues seamlessly；片尾截断用 `<cutoff>`。只有本来允许截断才使用标签，不能为窗口不足吃掉对白。

跨切镜对白的数据使用同一utterance_id、完整source_text和分配到连续镜头的原文text片段；拼接必须逐字还原，离镜片段结束在切点，入镜片段从0开始。编译器添加scenetrans，源台词不手写标记。cutoff仅在片段allow_speech_cutoff:true且最后一镜明确请求时启用。跨独立生成请求的连续录音需要另行声音制作，不能假装模型共享上一段音轨。

overall_soundscape 用 1–4 句连续英文描述环境、物理拟音和非语言人声，不重复对白或歌词；完全静音只有用户明确要求才 N/A。non_diegetic_music 用 1–3 句说明观众才能听到的器乐、速度、节奏、动态；没有配乐写 N/A。现场收音机音乐进入主体时间线，不放进非叙事配乐。

说话含糊时不能只增加“清晰”“自然”等形容词。每个说话人必须有稳定 `(Sx)`、年龄/类型、声线、音高、语速和发声方向；对白必须使用 `<d>[Language] 原始台词</d>`，动作声和对白的先后、重叠、停顿、重音与口型必须写在标签外。最终格式门会检查每个结构化对白是否实际出现在独立 H3 正文中，并把全局声音限制在规范句数内。

35 Hz 是可听低频／sub-bass，不是低于约 20 Hz 的次声。机械样例可用 35 Hz 作为声音设计目标，文戏不必人为加低频。`audio.low_frequency_hz:null` 配 no-low-frequency-intent 原因可通过适用性检查。提示词不保证频谱，真实成片需要音频分析或后期声音制作证明。

## 负向字段与执行设置

本机指南不包含第七个 `Negative constraints` 字段，不能捏造“官方负向行”。必要约束改为正向画面事实，或放到目标入口已验证的独立执行设置。动画不能默认被 `no cartoonish rendering` 否定。画幅、像素、采样、种子和原生 fps 在 execution settings，不能写“8K/120fps”冒充已完成母版。

## 契约 B 与编译流程

4.3.6 的实际文件与展示流程以[114 合同](114-reference-binding-delivery-v4.3.6.md)为准。缺参考可输出保留全部创作的 `.h3.draft.txt` 和逐段待素材卡，但不能正式通过；正式 `.h3.txt` 必须连同绑定、卡片和 manifest 联合验收。本地已核实文件可用于绑定，不要求先假装平台已经上传。

### Combat timing extension

当任一镜头 `features.combat` 为 true 时，`combat.timing` 是 H3 的必填动作层，不是可选的风格形容词。它必须逐帧覆盖从支点建立、加速承诺、接触／受力、结果传播到收势继承的完整区间，并独立写出屏幕轴线与主体位移方向、速度曲线、相机如何与动作锚点同步。`slow_motion` 必须声明 enabled、触发事实、使用理由、退出条件和播放比例；禁用时也要明确不添加无因慢动作。该层会被展开进每镜正文，不能只写在全局标题或内部表格里。

3.5.3 的执行字段为：`direction_facts`（origin、target、screen_direction、body_orientation、weapon_direction、support_point、result_direction）、`speed_profile`（support、acceleration、contact_read、recovery），以及每阶段的 `positions`、`orientation`、`action`、`combat_logic`、`camera`、`dof`、`composition`、`dynamics`、`tail_frame`。`combat_logic` 必须逐项给出 attacker、target、target_point、intent、defender_state、response、result 和 next_authority；`camera` 必须给出 framing、movement、motion_vector 和 action_anchor。脚本校验这些事实，编译器把它们逐阶段写入 `integrated_multimodal_description` 或 `detailed_description`，因此独立提交某段 H3 时仍能读懂起点、目标、接触、受力和尾态。

方向校验优先于华丽运镜：冲刺、投掷、飞跃和受击滑行要同时说明出发点、目标点、屏幕方向、身体朝向、脚下支点和尾态。镜头不能为了“速度感”跨越未交代的 180 度轴线；切镜后继续动作时，入镜姿态、速度相位和接触结果必须与上一镜尾态相容。

输入是已验证 production 中一个 Segment，包含 mode、duration、连续 shots、真实 references、summary/retention/style、soundscape/music。角色与场景登记中的prompt_description、每镜state_description必须完整英文且已展开。脚本先跑十维契约及最终正文检查，失败不生成提示词；成功逐段输出 `.h3.txt`、上传说明、素材副本和索引。只有 metadata 无真实图的 Ref2VA 会阻止就绪验收，不偷偷退回 T2VA。

模式选择、时间轴、speaker、图片存在性、16 格映射、台词逐字性和六／三字段顺序是可执行检查。标签是否符合参考图的真实内容、动作是否自然、声音是否达到目标属于实际生成与人工核验，不由字符串检查宣称满分。
