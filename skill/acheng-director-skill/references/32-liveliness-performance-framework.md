# 32｜灵动表演与个性化运动语言合同

## 这类提示词为什么生动

示例不是把“灵动、夸张、有个性”当成形容词塞进模型，而是把一段表演写成一个可播放的因果系统：

`人物目标 → 社交策略/潜台词 → 触发事实 → 可见泄露 → 主动控制 → 动作重音 → 跟随与收势 → 对白节拍 → 镜头/声音承接 → 下一镜尾态`

它同时约束五种连续性：

1. **身份连续性**：Subject、Picture、Audio分别定义可复用内容、具体帧和声音来源；引用标签不代替人物的外观正文。
2. **意图连续性**：人物不是“做动作”，而是在对某个对象争取、隐藏、压迫、试探或让渡某种关系位置。
3. **运动连续性**：每个动作有预备（anticipation）、重音（accent）、跟随（follow-through）和收势（settle/hold）。动作有方向、力度、时机和尾态，不能随机挥手。
4. **语言连续性**：对白按语义片段绑定声线、速度、音高、音量、停顿和重读；手势为词意或社会策略服务，不新增台词。
5. **剪辑连续性**：切点写明是否硬切、声音是否跨切、动作是否跨切、入点和出点状态；跨切台词仍以`utterance_id`和逐段`<scenetrans>`校验。

动画示例中的“animated on twos and threes at 24 fps”“direct hard cuts”“voice continuing across the cut”是**媒介和时间规则**，不是氛围形容词。它们必须进入`segments[].motion_profile`，而不是只留在一个风格标题里。

## 生产字段

只有需要这种因果表演的镜头才启用`shots[].performance.acting_design`。静态观察、克制对话和旧版五轨不必伪造夸张动作。

```json
{
  "version": "1.0",
  "mode": "expressive",
  "character_id": "CHAR_X",
  "objective": "win a concrete concession from the person on the phone",
  "tactic": "turn confidence into a promise of shared profit",
  "subtext": "she is testing whether the listener will accept her new status",
  "trigger": "the other person agrees to hear the proposal",
  "personality_signature": "she lifts her chin before a challenge, cuts the air with a flat hand, and makes generous arcs when describing a reward",
  "action_units": [
    {
      "start": 0,
      "end": 24,
      "cause": "the laugh has finished but the listener has not answered",
      "action": "opens her eyes, tilts her head, and lets a smug half-smile replace the laugh",
      "gaze": "toward the window rather than the phone",
      "face": "eyes narrow after opening; the chin rises one small degree",
      "follow_through": "the phone stays fixed at the left ear as the smile settles",
      "speech_anchor": "silent",
      "delivery": "hold the breath for one beat before the first word",
      "prop": "the phone remains in the left hand",
      "camera": "keep the eyes, phone and shoulder line readable",
      "sound": "the laugh decays into room tone and a small jacket rustle"
    },
    {
      "start": 24,
      "end": 72,
      "cause": "she reaches the phrase that removes the listener's doubt",
      "action": "raises the free right hand and slices it down flat once",
      "gaze": "fixed through the glass toward the cliff",
      "face": "smug mouth, brows relaxed, no panic",
      "follow_through": "the hand stops low instead of wobbling; the tail flicks once",
      "speech_anchor": "没错，",
      "delivery": "hard consonants, forceful onset, then a short pause",
      "camera": "hold the close view until the end of the phrase",
      "sound": "one clean sleeve snap, with no phone voice"
    }
  ],
  "motion_arc": {
    "anticipation": "the chin and shoulder prepare before the hand moves",
    "accent": "the flat-hand slice lands exactly on the decisive word",
    "follow_through": "the tail and jacket finish the hand's direction after the stop",
    "settle": "the hand lowers to the hip and the smug pose holds until the end"
  },
  "speech_delivery": {
    "voice_timbre": "use the supplied adult female voice-timbre reference without copying its signal",
    "pace": "confident medium pace with a brief pause before the payoff",
    "pitch": "slightly raised on the promise, then lower on the final claim",
    "volume": "forceful but still indoor and conversational",
    "pauses": [{"after_text": "没错，", "duration_ms": 180}],
    "emphasis": [{"text": "监督", "delivery": "give the noun a dry, self-awarding stress"}]
  },
  "cut_behavior": [{
    "at": 24,
    "type": "hard_cut",
    "audio_carries": true,
    "action_carries": true,
    "entry_state": "the sentence is already in progress and the left hand has just released the phone-side pose",
    "exit_state": "the back close-up receives the continuing voice before the right hand completes its downward slice"
  }],
  "continuity_in": "the supplied first frame's laugh, phone placement and room-side composition remain unchanged",
  "continuity_out": "the phone stays at the left ear; the tail and right hand finish in the smug held pose",
  "exclusions": [
    "invented phone dialogue",
    "new costume details",
    "a neutral expression that erases the social tactic"
  ]
}
```

`speech_anchor`必须是本镜已确认对白的精确子串；`silent`表示此动作没有发声。动作单元可以重叠，编译器按起始帧排序，不强行把眼、呼吸、手势排成生理定律。每个单元仍须回答“因为什么、做了什么、怎样收住”。

## `motion_profile`

当任一镜头启用`acting_design`时，同一独立生成段必须有`segments[].motion_profile`：

```json
{
  "version": "1.0",
  "medium": "2d_cel",
  "fps": 24,
  "exposure": "twos_and_threes",
  "timing_principle": "hold readable poses, then use one clean accent instead of continuous noise",
  "camera_principle": "protect the eye-line and let a hard cut reveal a new social angle",
  "staging_principle": "keep the window, desk, chair and tail in a stable spatial axis",
  "sound_principle": "carry the speaker's voice across the cut while physical foley remains local",
  "cut_style": "hard_cut"
}
```

它可以表达赛璐璐、真人、三维、定格或混合媒体；不得把“24 fps、twos”硬编码到所有题材。`medium`、曝光方式和剪辑风格由项目选择。

## 编译与验收

- `performance_liveliness`机器门检查字段完整性、动作窗口、对白锚点、跨切`utterance_id`、参考声线边界和段内运动规则。
- H3编译器把动作单元、运动弧、语气节拍、切点和排除项写入`integrated_multimodal_description`或Ref2VA的`detailed_description`；每个段仍重建主体、场景和开场状态。
- 角色的目标/潜台词是导演分析，不应替代可见证据；可见表情、凝视、重心、手势、道具接触、声线和尾态必须同时存在。
- 复杂多人反应仍按一个主导`acting_design`绑定一个镜头；另一个决定性反应应拆镜或创建另一个可追踪节拍，不把多个心理状态拼成“大家都很灵动”。
- 通过机器门只说明提示词结构完整。脸部自然度、个性是否成立、动作是否过量、声音是否真实连贯，必须在真实生成后逐帧和听音验收。

## 常见失败与修正

| 失败 | 修正 |
|---|---|
| 只写“生动、夸张、有个性” | 写稳定的行为签名，并让本镜动作兑现它 |
| 只列动作，不写触发 | 每个动作单元补`cause`和`objective/tactic` |
| 手势与对白无关 | 用精确`speech_anchor`绑定语义词，保留停顿和重读 |
| 连续挥手导致噪声 | 用预备→重音→跟随→收势，最多保留一个主动作和一个泄露点 |
| 切镜后人物像重置 | 写`entry_state/exit_state`，并用跨切对白合同验证声音来源 |
| 把参考音频当成电话另一端说话 | 只声明声线参考；电话另一端无声，除非另有上传声音源与剧本对白 |
| 用管理代号代替可见事实 | 内部身份ID、身材/配方代号必须展开；合法 H3 `(S1)` 发声标签保留并局部绑定对白，不得当成禁用代号删除 |
