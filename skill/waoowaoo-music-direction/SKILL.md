---
name: waoowaoo-music-direction
description: 依据锁定剧情与真实成片时间线，判定配乐窗口并撰写 Eleven Music v2 作曲方案，产出可合成音频批次。
metadata:
  version: "1.0.0"
  displayName: 音乐与配乐设计
  author: waooAI
  github: https://github.com/waooAI/waoowaoo
---

# 音乐与配乐设计

## 职责定位

本环节负责回答两个问题：成片里哪些区段该有音乐、哪些区段该留白；以及每一段该有音乐的地方，具体写成什么样的 Eleven Music v2 Composition Plan。cue 的取舍、乐曲的结构安排、Composition Plan 的撰写，全部由本环节产出。下游执行链路只做校验、冻结、调用生成与混音合成，不会回头替你补写或润色音乐设计。

## 可用素材与事实纪律

- 首要依据是项目目录中已定稿的视频提示词、源文本（剧本或脚本）、创作方向，以及成片 Resource。叙事理解取自这批锁定文本；具体的时间起止取自 `score_timeline` 视频 Resource 上报的真实 duration。
- 手头没有视频帧或音轨时，不要宣称自己看过画面、听过声音。允许依据定稿视频提示词来规划配乐，但文本推断与真实视听观察必须分开表述，不得混为一谈。
- 引用一律走 canonical Resource id 加 contentVersion。每个音乐 item 绑定且只绑定一个完整的待配乐视频，其 `channel: "context"`、`role: "score_timeline"`。这个视频不会被送去音乐 Provider，它只承担 lineage 追溯、时间边界界定与最终确定性合成的职责。
- 当 Creative Direction 有内容时，把其中已被采纳的、涉及叙事、导演、剪辑、声音与视觉节奏的政策，翻译成音乐层面的取舍。只摘抄形容词不算完成这一步。

## 先判定配乐范围

- 判断依据包括：人物承受的压力、关系走向的变化、关键信息的披露、风险等级、动作强度、对白疏密、环境真实感，以及段落之间的过渡需求。
- 既不默认全片铺音乐，也不默认必须有音乐。可以返回 `decision: "no_music"` 配空 `items`；也可以只挑若干互不相连的窗口写 cue。
- cue 的含义是：一次独立生成、随后被放到时间线上的完整乐段。一部十分钟成片，完全可以只在 2:00–3:00 与 7:00–8:00 各产出一个 cue，其余时段不生成任何音乐，由最终 mixer 维持数字静音——不需要先做一条十分钟的曲子再剪。
- cue 的个数由剧情走向和听觉连贯性决定，不存在“一般 1–3 个”这类创作上限。不要因为镜头切换就机械地切歌；如果前后段需要共用主题、音色、混响与运动惯性，那它们应当落在同一个 cue 的多个 chunk 里。
- 不同 cue 之间不共享生成状态。想让跨 cue 的听感统一，只能靠彼此兼容的调性世界、速度区间、配器家族、音色、空间感与母题设计来实现，不能假设 Provider 记得上一段。

## 收尾检查点

本 Skill 声明一个硬对齐检查点：**配乐决定**。触发条件是一部时长超过 15 秒的完整作品，其全部视觉单元已经就绪，而用户尚未对配乐表态。做法是由主 Agent 发起一张卡，列出两到三个具体配乐方向，推荐项排最前，另外必须附带一个明确的无配乐选项。作品是 16 秒、45 秒还是更长，一律适用。之后的机械收尾——合成、把已定配乐混入、打包——不再向用户提问。

只有当用户明确选定了某个配乐方向，才应用本 Skill 去生成 cue；只有当用户明确选择无配乐，才走 `no_music` 分支。绝不能凭沉默、时长、题材或自己的制作计划去推断 `no_music`。

## cue 与 Composition Plan chunk 的关系

- 一个 item 对应一个 **cue**，其 `startMs` 是该 cue 在完整视频中的绝对起点。
- 一个 cue 的 `compositionPlan.chunks`，是同一次生成内部按时间顺序接连发生的若干音乐段落。chunk 既不是“八段提示词”，也不是“八次生成”；它们共同拼成一份 JSON Composition Plan，由一次 Provider 请求产出一条连续音频。
- chunk 的数量取决于这条 cue 内部实际发生的音乐结构，1 个、2 个、8 个或其他合法数量都可以。不要为了显得精细就把每个镜头都切成一个 chunk。
- cue 的时长只有一个来源：所有 `chunk.durationMs` 相加。不要再写 `durationSeconds`，也不要写结束时间。
- Composition Plan 能精确规定 chunk 时长，但无法保证 chunk 内部逐 beat、逐 hit 的毫秒级命中。需要短促节奏、重音或转折时，把音乐行为写进对应 chunk 的 `text` 与 styles 中；不要向 Provider 索要某个具体毫秒对齐画面。

## 模型能力边界

音乐模型由设置固定，`model` 字段不填。每个 item 都要主动满足当前 `create_audio` 工具 schema 对 chunks 数量、单 chunk 时长、计划总时长、styles 数量以及 `contextAdherence` 枚举的要求，不能等服务端报错再回头改。

- 音乐时长不采用用户或平台的固定配置，只等于 Composition Plan 中 chunk 时长之和。输出格式由系统固定为 MP3，不填格式字段。
- styles 必须写成英文；歌词可以用其他语言，但本系统的 BGM cue 默认是纯器乐，不写歌词。
- 不要在 styles、段落文字或方向说明里点名真实艺人、乐队、受版权保护的歌曲，也不要复制歌词；Provider 会以 `bad_composition_plan` 拒绝此类计划。

只采信当前工具声明的模型事实；这些值还会被 registry/schema 硬校验。若工具不可用，或配置的模型与当前计划不兼容，应停止提交并说明缺口，不要猜测、不要截断、不要自行换模型。

## 逐个 chunk 的写法

- `text` 用英文方括号写明段落功能，例如 `[Restrained Tension]`、`[Escalation]`、`[Unresolved Release]`。纯器乐段不写歌词；需要描述演奏行为时，使用明确的音乐术语。
- `positiveStyles` 要具体到流派边界、配器、音区、织体、节奏密度、速度或 BPM、调性/调式、动态、空间与演奏法。第一个 chunk 的 styles 最关键，整条 cue 的总体音色与风格由它奠定。
- `negativeStyles` 用来主动排除错误情绪、错误配器、俗套、过密频段与人声，例如 `vocals`、`choir`、`spoken word`、`trailer hits`、`heroic brass`、`triumphant cadence`。不要指望一个笼统的 `instrumental` 就能解决所有排除项。
- `contextAdherence` 决定该 chunk 对相邻上下文的跟随强度。需要连续主题与自然演化时，通常取 `high`；只有在有意制造明显结构转向时才调低，且整条 cue 的音乐逻辑仍需成立。
- 相邻 chunks 要连成一条听得懂的弧线：建立、转化、加强、耗减、悬置或解决。明确哪些材料保留、哪些参数变化，避免每一段都另起一首新歌。

## 音乐理论与叙事

- 要区分画面表面的情绪与音乐真正应承载的立场：冷静旁观、主观压力、共情支持、程序性控制，或最低存在感。
- 速度、拍号、节拍显著度、音高组织、调式、关键音程、和声语法、终止策略与和声节奏，都应根据叙事来定，而不是机械地跟着每个剪辑点走。
- 配器从故事、时代、空间、对白密度与情绪推导。描述音色时，要交代音区、角色与演奏方式，不要只写“电影感”“高级”“有氛围”。
- 高潮不等于预告片撞击、英雄铜管、凯旋节奏、浪漫弦乐膨胀或俗套终止；除非剧情明确支持，应主动排除这些手法。
- BGM 不替代环境声、拟音、对白或同步音效。不要把画面动作逐字逐句地配成音乐 hit。

## 对白安全与精确合成

- 为对白和旁白保留中频空间，控制打击瞬态、镲片、密集旋律与持续高能占用。
- 每个 item 都要显式填写 `fadeInMs`、`fadeOutMs` 和 `gainDb`。这三项是最终 mixer 的确定性参数，不会发给音乐 Provider。
- `fadeInMs` 与 `fadeOutMs` 均不得超过该 cue 的 Composition Plan 总时长。进入与退出的方式，要与剪辑、对白和原生声音的关系相称。
- 多个 cue 允许重叠；重叠意味着 mixer 会真实叠加独立生成的音乐，只有在确实需要分层、且音乐关系经过设计时才这么做。
- 最终 mixer 会按 `startMs` 放置、按 plan 总时长裁掉编码 padding、在 cue 之间保留静音，并对完成的 BGM 总线统一做对白 ducking。不要试图在 Composition Plan 里补偿这些机械行为。

## 自检清单

- 是否先读了定稿视频提示词与真实 `score_timeline`，再根据剧情决定配乐窗口，而不是先做一条全片音乐？
- 每个 cue 的 `startMs + sum(chunk.durationMs)` 是否都没有越过视频真实 duration？
- cue 与 chunk 的分工是否正确：独立时间窗口才是 cue，同一次连续音乐内部的结构变化才是 chunk？
- 是否主动满足了当前工具声明的 chunks、时长、styles 与枚举限制？
- 第一个 chunk 是否建立了总体声音，后续 chunks 是否延续并做出有目的的变化？
- styles 是否为英文、纯器乐、不含真实艺人/歌曲/版权歌词引用？
- 是否没有承诺 chunk 内逐 beat、逐 hit 的毫秒确定性？
- 是否为对白与原生声音留出了频谱、动态与空间？
- `fadeInMs`、`fadeOutMs`、`gainDb` 与时间线放置是否明确且合理？

## 返回音频生成批次

- 判定不配乐时，使用 `decision: "no_music"` 与空 `items`，并在 `overview` 或 `warnings` 中说明叙事理由。
- 需要配乐时，每个 cue 对应一个 `mediaType: "audio"` item，内含一份完整 `compositionPlan`、绝对 `startMs`、淡入淡出、增益，以及恰好一个 `score_timeline` reference。不要输出根级 `prompt`、`durationSeconds`、`vocalMode`、`genre`、`mood` 或 `bpm`；这些已被 Composition Plan 取代。
- 当前 BGM 默认 `schemaId` 为 `project.bgm_audio`。
- 把确切的 items 交给 `create_audio`，并以确切的 ready 完整视频 Resource 作为 `score_timeline`；绝不把该视频上传给音乐 Provider。全部 cue Resource 就绪后，用同一个视频版本和全部确切 cue 版本（`musicCues`）调用一次 `merge_videos`，交付合成后的视频，而不是散装的 cue 文件。
- 唯一的专业结果是运行时注入 schema 约束的 `outputKind: "audio_generation_batch"` 严格 JSON。机器 Schema 才是字段、必填项与层级的权威；本 Skill 只讲创作方法与 Provider 真实规则，不复制一份可能漂移的 JSON 模板。

## 边界

本 Skill 负责剧情配乐判断、cue 窗口划分、Composition Plan 撰写、混音意图表达，以及按当前工具 schema 填写每个 item 的创作参数；模型由系统配置决定。能力校验、Operation Plan、报价、Task、durable provider invocation、日志错误码、Resource 终态与最终合成，全部由系统既有统一链路负责；不得调用 Provider 的自动 plan/video-to-music 能力，另立第二个配乐决策者。
