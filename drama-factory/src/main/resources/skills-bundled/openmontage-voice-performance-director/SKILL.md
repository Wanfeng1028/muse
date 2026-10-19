---
name: openmontage-voice-performance-director
version: "1.0.0"
description: 让 TTS 生成的旁白听起来像被"导演"过而非"朗读"，从剧本到素材生成携带具体的语音表演计划，并通过样片进行验证。
metadata:
  license: AGPL-3.0
---

# 语音表演导演（Voice Performance Director）

只要流水线会用 TTS 生成旁白，就使用本元技能。

目标是让生成的旁白听起来被**导演**过，而不仅仅是被朗读。不要把表现力留作提示词里的“自然朗读”。从剧本到素材生成都要携带具体的语音表演计划，再用样片验证。

## 必需契约

每份旁白主导的剧本都应包含顶层 `voice_performance` 对象，并在 schema 允许的地方包含段落级 `delivery_cues`。

顶层语音表演：

```json
{
  "performance_intent": "温暖、果断的产品旁白，带人类式停顿。",
  "pacing_profile": "conversational",
  "energy_curve": "克制的钩子，中段更温暖，结尾更从容",
  "pause_policy": "铺垫句后短停，反转或重要主张前长停。",
  "provider_notes": {
    "openai": "用 instructions 表达情绪弧线与强调。",
    "google_tts": "当所选声音支持时，使用带 break 标签的 SSML 输入。",
    "elevenlabs": "使用较低 stability 与中等 style 以获得富有表现力的旁白。"
  }
}
```

段落级 delivery cues：

```json
{
  "pace": "measured",
  "energy": "curious",
  "emphasis_words": ["not", "process"],
  "pause_before_seconds": 0.2,
  "pause_after_seconds": 0.7,
  "delivery_note": "先铺垫对比，再在最后一句放慢。",
  "provider_text": "This is not just another tool. <break time=\"0.6s\"/> It is a process."
}
```

## 写作规则

- 写口语，不要写论文语言。优先短句、轻缩写、清晰标点。
- 把静默当结构用。在反转前、意外主张后、最终收束前加停顿。
- 停顿标签要有目的。过多停顿会显得做作且拖沓。
- 避免“自然”“有感染力”“富有表现力”这类泛化指示，除非搭配确切的节奏、强调、停顿或能量提示。
- 每段尽量只给一个表演想法。若一段需要三次情绪转折，就拆段。

## 提供商映射

- OpenAI TTS：发送 `instructions` 时使用 `model: "gpt-4o-mini-tts"`。把情绪弧线、节奏、强调与角色放入 `instructions`；输入文本保持干净但有标点。不要把 `instructions` 发给 `tts-1` 或 `tts-1-hd`。
- Google TTS：仅在需要加 break 标签或其他 SSML 时使用 `input_type: "ssml"`。工具会把它映射到 Google 的 `input.ssml`，并在需要时用 `<speak>...</speak>` 包裹。`speaking_rate` 保持在 Google 支持的 `0.25..2.0` 范围内，pitch 在 `-20..20` 范围内。
- ElevenLabs：用较低 `stability` 获得更多变化，中等 `style` 增加表现力，`speed` 在提供商的 `0.7..1.2` 范围内，`similarity_boost` 保持足够高以保留音色。
- 离线/基础声音：依赖标点、更短句子与显式分段，因为提供商层面的情绪控制可能不可用。

## 样片关卡

批量旁白生成之前：

1. 从表演最敏感的段落生成样片，而不是默认取第一段。
2. 校验声音、节奏、停顿、强调与情绪弧线。
3. 若样片平淡，先调整 `voice_performance` 计划或提供商设置，再生成其余部分。
4. 将批准的样片路径与提供商设置记入素材清单。

## 失败条件

以下视为质量失败：

- 旁白主导的剧本没有 `voice_performance` 计划。
- 段落指示只说“自然朗读”或“有表现力”，没有具体的停顿、强调、节奏或能量提示。
- 样片获批后，TTS 提供商、声音、语速或模型被更改而未重新出样片。
- 在已有结构化 `provider_text` 或 `delivery_cues` 的情况下，最终旁白却用原始剧本文本生成。
