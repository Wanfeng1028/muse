# Chinese audiovisual video prompt template

## Contents

1. Settings block
2. Control-density choice
3. Copyable prompt
4. Audio syntax
5. Final frame
6. Negative prompt

## 1. Settings block

Keep settings outside the model prompt:

```text
时长：10秒
画幅：16:9
帧率：24fps
模型：Seedance 2.0
参考图：4张
```

## 2. Control-density choice

Use the compact form for simple reactions, inserts, dialogue coverage, and atmospheric shots. For action, dance, music sync, multiple subjects, unusual gravity, or continuity-sensitive staging, read [higgsfield-cinematic-prompting.md](higgsfield-cinematic-prompting.md) and add only the useful control layers: atmosphere, location map, first-frame blocking, format mode, optics, physics, and positive locks.

## 3. Copyable prompt

For dialogue-led clips, first read [dialogue-and-screenplay-continuity.md](dialogue-and-screenplay-continuity.md). Every spoken line must come from `dialogue-ledger.json` and use a stable utterance ID plus an exact named speaker. Put braces around spoken words only.

Use one fenced code block per clip:

```text
[类型、场景和本片段目的的一句话。]

本段引用素材：[角色名或用途]@[filename]；[场景用途]@[filename]；[动作或分镜用途]@[filename]。

[角色]角色参考@[filename]定义唯一的[角色名]：[可见身份标记]。只提取[面孔、发型、服装等]；不要使用[灰色背景、分栏、设定图布局]。成片中只有一个[角色名]。

[场景]参考@[filename]定义[布局、时间、天气、光线]。只提取[需要的属性]；不要提取[人物、文字或排版]。

氛围系统：[风、雾、雨、尘土、烟、花瓣或人群如何贯穿全片，并与主体和光线一致互动]。

空间地图：[固定地标、前中后景、主体起点、朝向、入口、出口和屏幕方向]。
首帧站位：[承接上一段的已发生事件；人物和物体的位置、接触、动作阶段、运动方向和速度；不得重演的动作]。
衔接意图：[本段如何回应上一段；末尾由什么动作、视线、声音或信息引出下一段；首段/末段按需省略]。

主体：[人物、外貌和完整服装重述]。
场景：[空间、时间、天气和背景状态]。
风格：[光线、颜色、材质、颗粒和情绪]。
拍摄模式：[单一连续镜头/受控多镜头序列；剪辑、实时或慢动作政策]。
镜头与光学：[机位高度、距离、路径、焦段或视场角、景深、运动模糊；分段内是否锁定焦段]。
摄影：[设备/手持质感、物理移动路径、与主体的关系、服务的戏剧目的]。

对白与声源锁定：[本段说话人名单；每个 utterance ID 唯一属于谁；谁发声时其他可见人物闭嘴；是否允许画外音。]

表演任务：[本段主角此刻想让谁做什么；什么可见/可听的刺激改变其策略；听者如何延迟回应。用手、视线、重心、距离或具体道具动作写可表演的行为，不堆情绪形容词。]
对白制作路径：[此句采用单人可见口型／后期配音与专项对口型／明确声源的画外对白；对应台词ID与镜头覆盖。不要在不支持的模型上承诺后期工序。]

0—3秒：[可见动作和屏幕方向]。[景别、角度和运镜。] <声音>
3—7秒｜[c01-u01] 说话人：[精确角色名]；受话人：[精确角色名]；[说话人可见位置、嘴唇同步、表演动作和单人覆盖]说：{只放实际说出口的台词}。[听者闭嘴、反应与是否离画。]
7—10秒：[可见动作和屏幕方向]。[镜头如何延续运动或有动机地停下。] <声音>

物理：[质量、重力、惯性、接触、后坐/跟随动作、材质形变，以及头发、服装、饰品和环境反馈]。

声音：环境声、动作音效和音乐政策。对白语言：[普通话/方言/其他语言]。各角色声线固定；不交换台词；不让听者替说话人动嘴。无旁白。无字幕。

最终画面：[对白结束后的嘴唇闭合状态、人物位置、姿势、灯光状态、镜头是否静止]。此处不得重复任何台词或使用 `{}`。不得出现文字、字幕、标志和水印。

正向锁定：[唯一角色/物体数量、身份、动作顺序、道具政策、空间连续、拍摄模式和物理质量]。

负面提示词：[身份、服装、结构、动作、背景、文字和风格禁止项]。
```

For a simple clip, omit empty sections. For a complex clip, prefer clear headings and operational statements over decorative film terminology. Keep generation settings outside the fenced block.

## 4. Audio syntax

- music: `(低沉弦乐逐渐增强)`
- effect: `<远处传来钟声>`
- dialogue: `{别回头。}`
- subtitle: `【三年前】`

Always name dialogue language before the line. Do not overlap narration and dialogue unless the user explicitly wants layered speech.

Never use an action, pronoun, screen position, or costume as the only speaker label. Bad: `门口回头：{台词}`. Good: `[c03-u02] 说话人：高峰；受话人：陈默；高峰在门口回头，单人近景说：{台词}。陈默闭嘴。`

When two characters speak, give each a separate time range and shot/reverse-shot coverage. Do not compress `甲：{...} 乙：{...}` into one undivided beat. Keep every utterance ID and brace pair unique; do not repeat it in the final frame or sound summary.

For music-led work, map cuts, choreography, lip-sync, hero gestures, and the final pose to musical beats or lyric phrases. For diegetic action, attach each important sound to its visible cause.

## 5. Final frame

Every clip needs a destination. State subject position, action phase, lighting, subject/camera motion or motivated rest, and text prohibition. A clip ending mid-action must preserve motion rather than close in a frozen pose. The final frame should support the next edit or close the story.

## 6. Negative prompt

Include only plausible failures:

- identity and costume drift;
- duplicate characters;
- anatomy failures relevant to the action;
- reference background or grid bleed;
- location and lighting changes;
- unwanted text, logos, subtitles, or watermark;
- unwanted genre or rendering style.

Keep the complete copyable prompt under 5000 characters when possible. If it cannot fit, split the clip.

### Prompt conversion check

Before copying the screenplay into a model prompt, remove internal motivations that cannot be photographed. Replace them with the ordered trigger, action, listener response, and resulting physical state. Keep only references actually supplied to the job; a reference map is not proof that the provider ingested every named image. Make the prompt internally consistent: a silent/SFX-only shot must not also request a spoken line, and a locked single camera cannot also perform an unannounced cut. Technical slogans such as “8K IMAX,” “Hollywood acting,” or “everyone moves from frame one” do not repair missing action, identity control, or sync.
