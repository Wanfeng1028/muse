---
name: music-direction
description: Plan narrative score windows and author precise Eleven Music v2 Composition Plans.
---

# 音乐与配乐设计

## 作用

根据项目中已经锁定的剧情、最终视频提示词、剪辑事实和真实成片时间线，决定哪里需要配乐、哪里不需要配乐，并为每个需要配乐的时间窗口直接写出可执行的 Eleven Music v2 Composition Plan。你是 cue 选择、音乐结构和 Composition Plan 的唯一创作者；执行层只校验、冻结、生成和合成，不会再替你改写或补全音乐设计。

## 事实边界

- 优先读取项目文件夹中最终视频提示词、源文本（剧本或脚本）、创作方向与成片 Resource；内容理解来自这些锁定文本，精确时间边界来自 `score_timeline` 视频 Resource 的真实 duration。
- 没有实际提供视频帧或音轨时，不声称观看或听取了它们。可以基于最终视频提示词规划剧情配乐，但必须如实区分文本事实与实际视听观察。
- 只使用 canonical Resource id + contentVersion。每个音乐 item 必须引用恰好一个 `channel: "context"`、`role: "score_timeline"` 的完整待配乐视频；该视频不会上传给音乐 Provider，只用于 lineage、时间边界与最终确定性合成。
- Creative Direction 非空时，把与叙事、导演、剪辑、声音和视觉节奏有关的已采纳政策转译为音乐决定；不能只照抄形容词。

## 先决定“哪里需要音乐”

- 从人物压力、关系变化、信息揭示、风险、动作强度、对白密度、环境真实感和段落转换判断音乐是否有叙事价值。
- 不默认全片铺满，也不默认一定要有音乐。可以返回 `decision: "no_music"` 与空 `items`；也可以只为任意多个不连续窗口创作 cue。
- cue 是一次独立生成并放到时间线上的完整乐段。一个十分钟成片可以只在 2:00–3:00 和 7:00–8:00 各生成一个 cue；中间没有 cue 的部分由最终 mixer 保持数字静音，不需要生成一条十分钟音乐再裁剪。
- cue 数量只由剧情与听觉连续性决定，不设置“通常 1–3 个”之类创作上限。避免因镜头切换机械切曲；如果前后需要共享主题、音色、混响和运动惯性，应放在同一个 cue 的多个 chunk 中。
- 独立 cue 不共享生成状态。跨 cue 的统一感要靠兼容的调性世界、速度范围、配器家族、音色、空间和母题设计，不得假装 Provider 能记住上一段。

## 收尾检查点

本 Skill 声明一个硬对齐检查点：**配乐决定**。时机是一部超过 15 秒的完整作品的视觉单元全部就绪、且用户尚未决定配乐时。做法：由主 Agent 发起一张卡，给出两到三个具体的配乐方向，推荐项在前，外加一个明确的无配乐选项。无论作品是 16 秒、45 秒还是更长都适用。机械收尾——合成、混入已决定的配乐、打包——不再提问。

只有用户明确选择了配乐方向后才应用本 Skill 生成 cue；只有用户明确选择无配乐后才走 `no_music` 分支。绝不从沉默、时长、题材或自己的制作计划推断 `no_music`。

## Cue 与 Composition Plan chunk 的区别

- 一个 item 是一个 **cue**；`startMs` 决定该 cue 在完整视频中的绝对起点。
- 一个 cue 的 `compositionPlan.chunks` 是同一次生成内部按顺序连续发生的多个音乐段落。chunk 不是八段提示词，也不是八次生成；它们共同组成一份 JSON Composition Plan，并由一次 Provider 请求生成一条连续音频。
- chunk 数量按这条 cue 内真正发生的音乐结构选择，可以是 1、2、8 或其他合法数量。不要为了“看起来精细”把每个镜头都拆成 chunk。
- cue 的时长只有一个来源：所有 `chunk.durationMs` 之和。不要另写 `durationSeconds` 或结束时间。
- Composition Plan 能精确控制 chunk 时长，但不能提供 chunk 内逐 beat、逐 hit 的确定性毫秒事件。需要短促节奏、重音或转折时，在对应 chunk 的 `text` 与 styles 中描述音乐行为；不要承诺 Provider 会在某个具体毫秒命中画面。

## 模型能力边界

音乐模型由设置固定，不填写 `model`。每个 item 主动遵守当前 `create_audio` 工具 schema 的 chunks 数量、单 chunk 和总计划时长、styles 数量及 `contextAdherence` 枚举，不依赖服务端报错后再修。

- 音乐时长不取用户或平台固定配置，只由 Composition Plan 的 chunk 时长之和决定。输出格式由系统固定为 MP3，不填写格式字段。
- styles 必须使用英文；歌词可以使用其他语言，但本系统的 BGM cue 默认必须是纯器乐，不写歌词。
- 不在 styles、段落文字或方向中点名真实艺人、乐队、受版权保护的歌曲或复制歌词；Provider 会以 `bad_composition_plan` 拒绝这类计划。

只读取当前工具声明的模型事实；这些值还会由 registry/schema 进行硬校验。若工具不可用或配置模型与当前计划不兼容，停止提交并说明缺口，不猜测、不截断、不自动更换模型。

## 写每个 chunk

- `text` 用英文方括号写清段落功能，例如 `[Restrained Tension]`、`[Escalation]`、`[Unresolved Release]`。纯器乐段不写歌词；需要演奏行为时使用清晰的音乐语言。
- `positiveStyles` 具体描述流派边界、配器、音区、织体、节奏密度、速度或 BPM、调性/调式、动态、空间与演奏法。第一 chunk 的 styles 最重要，它会建立整条 cue 的总体音色与风格。
- `negativeStyles` 主动排除错误情绪、错误配器、俗套、过密频段和人声，例如 `vocals`、`choir`、`spoken word`、`trailer hits`、`heroic brass`、`triumphant cadence`。不要依赖一个笼统的 `instrumental` 词解决所有排除项。
- `contextAdherence` 决定该 chunk 对相邻上下文的跟随强度。需要连续主题和自然演化时通常使用 `high`；有意制造明显结构转向时才降低，且仍要保持整条 cue 的音乐逻辑。
- 相邻 chunks 应构成一条可听懂的弧线：建立、转化、加强、耗减、悬置或解决。明确哪些材料保持、哪些参数变化，避免每段另起新歌。

## 音乐理论与叙事

- 区分画面表面情绪与音乐应承载的深层立场：冷静旁观、主观压力、共情支持、程序性控制或最低存在感。
- 根据叙事决定速度、拍号、节拍显著度、音高组织、调式、关键音程、和声语法、终止策略与和声节奏，不机械追随每个剪辑点。
- 配器从故事、时代、空间、对白密度和情绪推导。为音色说明音区、角色和演奏方式，避免只写“电影感”“高级”“有氛围”。
- 高潮不等于预告片撞击、英雄铜管、凯旋节奏、浪漫弦乐膨胀或俗套终止；除非剧情明确支持，应主动排除。
- BGM 不替代环境声、拟音、对白或同步音效。不要把画面动作逐个字面配成音乐 hit。

## 对白安全与精确合成

- 为对白和旁白保留中频空间，控制打击瞬态、镲片、密集旋律与持续高能占用。
- 每个 item 显式填写 `fadeInMs`、`fadeOutMs` 和 `gainDb`。它们是最终 mixer 的确定性参数，不会发送给音乐 Provider。
- `fadeInMs` 与 `fadeOutMs` 都不能超过该 cue 的 Composition Plan 总时长。进入与退出方式应与剪辑、对白和原生声音关系一致。
- 多个 cue 可以重叠；重叠意味着 mixer 会真实叠加独立生成的音乐，只有在确实需要分层且音乐关系经过设计时才这样做。
- 最终 mixer 按 `startMs` 放置、按 plan 总时长裁掉编码 padding、在 cue 间保留静音，并对完成的 BGM 总线统一进行对白 ducking。不要在 Composition Plan 中补偿这些机械行为。

## 自检

- 是否先读了最终视频提示词与真实 `score_timeline`，再从剧情决定配乐窗口，而不是先生成一条全片音乐？
- 每个 cue 的 `startMs + sum(chunk.durationMs)` 是否没有越过视频真实 duration？
- cue 与 chunk 是否分工正确：独立时间窗口才是 cue，同一次连续音乐内部的结构变化才是 chunk？
- 是否主动遵守当前工具声明的 chunks、时长、styles 和枚举限制？
- 第一 chunk 是否建立了总体声音，后续 chunks 是否延续并有目的地变化？
- styles 是否为英文、纯器乐、无真实艺人/歌曲/版权歌词引用？
- 是否没有承诺 chunk 内逐 beat/逐 hit 的毫秒确定性？
- 是否为对白和原生声音留出频谱、动态和空间？
- `fadeInMs`、`fadeOutMs`、`gainDb` 与时间线放置是否明确且合理？

## 返回音频生成批次

- 判定不配乐时使用 `decision: "no_music"`、空 `items`，并在 `overview` 或 `warnings` 中说明叙事理由。
- 需要配乐时，每个 cue 对应一个 `mediaType: "audio"` item，包含一份完整 `compositionPlan`、绝对 `startMs`、淡入淡出、增益，以及恰好一个 `score_timeline` reference。不要输出根 `prompt`、`durationSeconds`、`vocalMode`、`genre`、`mood` 或 `bpm`；这些已由 Composition Plan 取代。
- 当前 BGM 默认 `schemaId` 为 `project.bgm_audio`。
- 把确切 items 交给 `create_audio`，并以确切的 ready 完整视频 Resource 作为 `score_timeline`；绝不把该视频上传给音乐 Provider。全部 cue Resource 就绪后，用同一个视频版本和全部确切 cue 版本（`musicCues`）调用一次 `merge_videos`，交付合成后的视频，而不是散装 cue 文件。
- 唯一专业结果是运行时注入 schema 约束的 `outputKind: "audio_generation_batch"` 严格 JSON。机器 Schema 是字段、必填项和层级的唯一权威；本 Skill 只说明创作方法和 Provider 真实规则，不复制一份可能漂移的 JSON 模板。

## 边界

本 Skill 负责剧情配乐判断、cue 窗口、Composition Plan、混音意图以及按当前工具 schema 填写每个 item 的创作参数；模型由系统配置决定。能力校验、Operation Plan、报价、Task、durable provider invocation、日志错误码、Resource 终态和最终合成全部由系统既有统一链路负责；不得调用 Provider 的自动 plan/video-to-music 能力另造第二个配乐决策者。
