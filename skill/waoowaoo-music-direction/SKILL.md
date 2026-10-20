---
name: waoowaoo-music-direction
description: 依据已锁定的剧情、成片时间线与剪辑事实，判断何处需要配乐并逐窗口撰写 Eleven Music v2 Composition Plan；在作品视觉就绪后发起配乐方向确认，输出可直接执行的音频生成批次。
metadata:
  version: "1.0.0"
  displayName: 音乐与配乐设计
  author: waooAI
  github: https://github.com/waooAI/waoowaoo
---

# 音乐与配乐设计

## 职责定位

本 Skill 依据项目内已经定稿的剧情内容、最终视频提示词、剪辑事实以及真实成片时间轴，判定哪些区段值得配置音乐、哪些区段应当保持无乐，并为每一个确定要配乐的时间窗口直接产出可落地的 Eleven Music v2 Composition Plan。cue 的取舍、音乐结构以及 Composition Plan 的撰写全部由本 Skill 独立完成；下游执行环节只做校验、冻结、生成与合成，不会代替你重写或补齐任何音乐设计内容。

## 事实来源与边界

- 读取顺序上，先取项目目录中最终视频提示词、源文本（剧本或脚本）、创作方向与成片 Resource。语义层面的理解来自这些已锁定文本；精确的时间起止点则取自 `score_timeline` 视频 Resource 的真实 duration。
- 若没有实际拿到视频帧或音轨，就不得声称自己看过或听过这些素材。允许依据最终视频提示词来规划剧情配乐，但必须如实区分“文本事实”与“实际视听观察”这两类依据。
- 引用一律使用 canonical Resource id 加 contentVersion。每个音乐 item 必须且只能引用一个 `channel: "context"`、`role: "score_timeline"` 的完整待配乐视频；该视频不会被上传给音乐 Provider，它的作用仅限于 lineage、时间边界以及最终确定性合成。
- Creative Direction 非空时，需要把其中与叙事、导演、剪辑、声音和视觉节奏相关的已采纳政策翻译成具体的音乐决定，而不是简单照搬其中的形容词。

## 先判断“音乐该出现在哪里”

- 从人物承受的压力、关系走向、信息揭示节点、风险程度、动作强度、对白密度、环境真实感以及段落之间的转换来判断某处是否具备配乐的叙事价值。
- 不预设全片必须铺满音乐，也不预设一定得有音乐。允许返回 `decision: "no_music"` 与空 `items`；也允许只为任意数量、彼此不连续的窗口撰写 cue。
- 一个 cue 代表一次独立生成、随后被放到时间轴上的完整乐段。十分钟的成片完全可以只在 2:00–3:00 和 7:00–8:00 各生成一个 cue；其余没有 cue 的区段由最终 mixer 维持数字静音，无需先生成十分钟音乐再裁剪。
- cue 的数量只由剧情走向与听觉连续性决定，不设“通常 1–3 个”这类创作上限。不要因为镜头切换就机械地切歌；若前后段落需要共用主题、音色、混响与运动惯性，应把它们放进同一个 cue 的多个 chunk。
- 不同的独立 cue 之间不共享生成状态。跨 cue 的统一感必须依靠兼容的调性世界、速度区间、配器家族、音色、空间与母题设计来营造，不能假定 Provider 会记住上一段内容。

## 收尾检查点

本 Skill 声明一个硬对齐检查点：**配乐决定**。触发时机是一部时长超过 15 秒的完整作品其视觉单元全部就绪、且用户尚未就配乐作出选择时。执行方式为：由主 Agent 发起一张卡，给出两到三个具体的配乐方向（推荐项排在最前），并额外提供一个明确的无配乐选项。作品是 16 秒、45 秒还是更长，都同样适用。此后的机械收尾——合成、混入已决定的配乐、打包——不再发起提问。

只有当用户明确选定了配乐方向之后，才应用本 Skill 生成 cue；只有当用户明确选择无配乐之后，才走 `no_music` 分支。绝不能从沉默、时长、题材或自身制作计划去推断 `no_music`。

## Cue 与 Composition Plan chunk 的区别

- 一个 item 就是一个 **cue**；`startMs` 决定这个 cue 在完整视频中的绝对起点。
- 一个 cue 的 `compositionPlan.chunks` 指的是同一次生成内部按顺序连续发生的若干音乐段落。chunk 不是八段提示词，也不是八次生成；它们共同构成一份 JSON Composition Plan，由一次 Provider 请求生成出一条连续音频。
- chunk 数量取决于这条 cue 内实际发生的音乐结构，可以是 1、2、8 或其他任何合法数量。不要为了“显得精细”而把每个镜头都拆成一个 chunk。
- cue 的时长只有唯一来源：全部 `chunk.durationMs` 之和。不要另写 `durationSeconds` 或结束时间。
- Composition Plan 能精确控制 chunk 的时长，但无法提供 chunk 内逐 beat、逐 hit 的确定性毫秒事件。需要短促节奏、重音或转折时，就在对应 chunk 的 `text` 与 styles 中描述音乐行为；不要承诺 Provider 会在某个具体毫秒命中画面。

## 模型能力边界

音乐模型由设置固定，不填写 `model`。每个 item 都要主动遵守当前 `create_audio` 工具 schema 所声明的 chunks 数量、单 chunk 与总计划时长、styles 数量以及 `contextAdherence` 枚举，不依赖服务端报错后再补救。

- 音乐时长不取用户或平台的固定配置，只由 Composition Plan 的 chunk 时长之和决定。输出格式由系统固定为 MP3，不填写格式字段。
- styles 必须使用英文；歌词可以使用其他语言，但本系统的 BGM cue 默认必须是纯器乐，不写歌词。
- 不在 styles、段落文字或方向描述中点名真实艺人、乐队、受版权保护的歌曲，也不复制歌词；Provider 会以 `bad_composition_plan` 拒绝此类计划。

只读取当前工具声明的模型事实；这些值还会由 registry/schema 做硬校验。若工具不可用，或配置的模型与当前计划不兼容，就停止提交并说明缺口，不猜测、不截断、不自动更换模型。

## 如何撰写每个 chunk

- `text` 用英文方括号写清段落功能，例如 `[Restrained Tension]`、`[Escalation]`、`[Unresolved Release]`。纯器乐段不写歌词；需要描述演奏行为时，使用清晰的音乐语言。
- `positiveStyles` 具体描述流派边界、配器、音区、织体、节奏密度、速度或 BPM、调性/调式、动态、空间与演奏法。第一 chunk 的 styles 最为关键，它会奠定整条 cue 的总体音色与风格。
- `negativeStyles` 主动排除错误情绪、错误配器、俗套、过密频段与人声，例如 `vocals`、`choir`、`spoken word`、`trailer hits`、`heroic brass`、`triumphant cadence`。不要指望一个笼统的 `instrumental` 词解决所有排除项。
- `contextAdherence` 决定该 chunk 对相邻上下文的跟随强度。需要连续主题与自然演化时通常使用 `high`；只有在有意制造明显结构转向时才降低，并且仍要维持整条 cue 的音乐逻辑。
- 相邻 chunks 应构成一条可听懂的弧线：建立、转化、加强、耗减、悬置或解决。明确哪些材料保持、哪些参数变化，避免每段另起一首新歌。

## 音乐理论与叙事

- 区分画面的表面情绪与音乐应当承载的深层立场：冷静旁观、主观压力、共情支持、程序性控制或最低存在感。
- 根据叙事决定速度、拍号、节拍显著度、音高组织、调式、关键音程、和声语法、终止策略与和声节奏，不机械追随每一个剪辑点。
- 配器从故事、时代、空间、对白密度和情绪推导而来。为音色说明音区、角色和演奏方式，避免只写“电影感”“高级”“有氛围”。
- 高潮不等于预告片撞击、英雄铜管、凯旋节奏、浪漫弦乐膨胀或俗套终止；除非剧情明确支持，应主动排除。
- BGM 不替代环境声、拟音、对白或同步音效。不要把画面动作逐个字面配成音乐 hit。

## 对白安全与精确合成

- 为对白和旁白保留中频空间，控制打击瞬态、镲片、密集旋律与持续高能占用。
- 每个 item 显式填写 `fadeInMs`、`fadeOutMs` 和 `gainDb`。它们是最终 mixer 的确定性参数，不会发送给音乐 Provider。
- `fadeInMs` 与 `fadeOutMs` 都不能超过该 cue 的 Composition Plan 总时长。进入与退出方式应与剪辑、对白和原生声音的关系保持一致。
- 多个 cue 可以重叠；重叠意味着 mixer 会真实叠加独立生成的音乐，只有在确实需要分层且音乐关系经过设计时才这样做。
- 最终 mixer 按 `startMs` 放置、按 plan 总时长裁掉编码 padding、在 cue 之间保留静音，并对完成的 BGM 总线统一进行对白 ducking。不要在 Composition Plan 中补偿这些机械行为。

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
- 把确切 items 交给 `create_audio`，并以确切的 ready 完整视频 Resource 作为 `score_timeline`；绝不把该视频上传给音乐 Provider。全部 cue Resource 就绪后，用同一个视频版本和全部确切 cue 版本（`musicCues`）调用一次 `merge_videos`，交付合成后的视频，而不是散装的 cue 文件。
- 唯一专业结果是运行时注入 schema 约束的 `outputKind: "audio_generation_batch"` 严格 JSON。机器 Schema 是字段、必填项和层级的唯一权威；本 Skill 只说明创作方法与 Provider 真实规则，不复制一份可能漂移的 JSON 模板。

## 边界

本 Skill 负责剧情配乐判断、cue 窗口、Composition Plan、混音意图，以及按当前工具 schema 填写每个 item 的创作参数；模型由系统配置决定。能力校验、Operation Plan、报价、Task、durable provider invocation、日志错误码、Resource 终态和最终合成全部由系统既有统一链路负责；不得调用 Provider 的自动 plan/video-to-music 能力另造第二个配乐决策者。
