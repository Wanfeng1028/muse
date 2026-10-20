# H3 声音生产与角色音色合同

## 1. 核心判断

固定角色的默认路线是 `h3-native-reference`，不是让 H3 每段自由发明声音，也不是默认后期覆盖。H3 Ref2VA 可以把 `<Audio N>` 绑定到 `<Subject N> (Sx)`，参考人物的音色和表达生成新台词。

官方资料：

- H3 原生音画、输入数量、时长和语言规格：<https://www.minimax.io/news/minimax-h3-open-source>
- H3 API 的 `reference_audio`、模式互斥和媒体限制：<https://platform.minimax.io/docs/api-reference/video-generation-v2-create>
- 全参考模式的声音绑定和 `reference` / `partially_copy` / `fully_copy`：<https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md>

投产时重新核对这些页面。若最新官方文档变化，以官方为准并更新本合同。

生产总控的 `scripts/h3-official.mjs` 已支持把 `reference_audio` 与图片/视频一起提交到官方 V2 接口；投产步骤、密钥和状态回写见 `references/h3-execution.md`。旧的只支持参考图的接口脚本不能承担固定人物音色路线。

## 2. 四层声音决策

不要用一个 `audio=true` 概括全部声音。每个片段分别决定：

- `dialogueRoute`：对白如何产生。
- `ambienceRoute`：空间底噪与持续环境。
- `foleyRoute`：脚步、衣料、道具和冲击声。
- `musicRoute`：观众听到、人物听不到的配乐。

默认：

```text
dialogue = h3-native-reference
ambience = h3-native
foley = hybrid
music = post
```

H3 可以原生生成音乐，但多段独立生成会造成旋律、调性、速度和响度跳变；系列短剧默认后期铺统一音乐。

## 3. 对白路线选择

### `h3-native-reference`

适合普通人物对白、近景表演和需要自然口型的段落。

要求：

- 角色有已批准声音母版。
- H3 使用 Ref2VA。
- `reference_audio` 与人物图/视频共同输入。
- 提示词明确绑定 Subject、Speaker 和 Audio。
- `retention_analysis` 使用 `reference`，说明不复制原信号，只参考音色和表达。

```text
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

<Audio 1>: reference - the target speaker follows <Audio 1>'s
voice timbre and controlled delivery without copying the original signal.

[Shot 1] <Subject 1> (S1) speaks with restrained anger,
<d>[Chinese]这份合同，我不会签。</d>
```

### `tts-guided-h3`

适合金额、人名、广告词、咒语、付费点台词、哭喊节奏或任何必须逐字准确的表演。

先用固定角色音色生成准确台词音频，再作为 H3 `reference_audio`：

- `fully_copy`：输入音频作为目标完整音轨。
- `partially_copy`：复用对白层或局部，同时允许 H3 增加环境与动作声。
- `reference`：仅借音色和表达，不保证原波形与时长。

需要精确台词时不要误用 `reference`。

### `tts-post`

适合旁白、内心独白、电话音、远处广播、H3 声音失败的返修，或必须采用首帧/尾帧锚定而无法同时使用参考音频的任务。

H3 提示词不得包含同一句 `<d>` 对白。最好让模型不生成叙事性音乐，避免后期分离混合声轨。

### `h3-native-free`

只用于临时样片、无固定身份的群杂声或用户明确接受声音不固定的角色。主要角色不得默认使用。

## 4. 声音母版制作

每位主要说话角色一份稳定母版：

- 官方硬范围 2–15 秒；生产建议 6–12 秒。
- 单人、干声、无音乐、无空间混响、无明显底噪。
- 包含正常语速、完整元音和辅音，不用全程喊叫或耳语。
- 角色的年龄感、音高区间、气息、口音、速度和句尾习惯明确。
- 使用合成、本人拥有、获得许可或获得同意的声音；记录 `rights`。

同一角色跨片段使用同一个文件和 SHA-256。需要愤怒/哭泣/耳语变体时，仍保留同一母版身份，并把变体登记为 `performance-reference`，不要替换母版。

Fish Audio 可作为母版生产器。使用时完整执行 `references/fish-voice.md`：免费 `s2.1-pro-free` 只生成评估资产，正式商业交付前用付费模型重制同一声音资产；普通对白仍优先交给 H3 参考母版原生生成。

## 5. H3 参考预算

当前官方 API 限制意味着：

- 最多三条音频参考，因此最多稳定绑定三套独立声音。
- 参考音频不能单独输入，必须有参考图或参考视频。
- 使用参考音频即进入 Ref2VA，不能再同时使用 `first_frame` / `last_frame`。

四人以上对白场的处理优先级：

1. 按冲突拆成双人或三人关系镜头。
2. 将次要角色放画外并采用后期声音。
3. 群体回应合并为非身份化群声。
4. 不要牺牲主角音色参考去覆盖无关角色。

## 6. 跨段声音连续性

相同参考音频不会自动保证多个独立任务百分之百一致。每个生成片段验收：

- 音色相似度：年龄、共鸣位置、音高、气息。
- 语言准确度：漏字、错字、吞音、口音。
- 表演连续性：前后镜情绪和语速是否衔接。
- 技术连续性：响度、底噪、房间感、左右声像。
- 口型：开口、闭口、停顿和声画切点。

不合格先判断是声音参考、提示词、台词长度还是模型随机性。不要直接多次付费碰运气。

## 7. 禁止的混用

- 同一句台词既保留 H3 原声又叠后期 TTS。
- 把带音乐和多人对话的成片当作单一角色声音母版。
- 声音母版每集更换。
- 给 H3 参考音频，却不在提示词中绑定到具体 Subject/Speaker。
- 计划后期统一配乐，却让每个片段分别生成完整主题音乐。
- 使用无授权真人声音进入商业投产。
