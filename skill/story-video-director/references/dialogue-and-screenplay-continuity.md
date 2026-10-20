# Dialogue and screenplay continuity

Use this reference for acted narrative, workplace drama, comedy, interviews reconstructed as scenes, or any project in which named characters speak.

## 1. Write drama before prompts

Adapt prose into scenes with causality, not illustrated summary. Each scene needs:

- a character who wants something now;
- another person, rule, fact, or fear blocking it;
- a visible tactic: evade, pressure, flatter, challenge, stall, conceal, test, or concede;
- a turn that changes status, knowledge, leverage, or the next action;
- behavior that carries part of the meaning so dialogue does not explain everything.

Before finalizing, test every line: why does this character say it, why now, why to this person, and what changes after it? If another character could say the line without changing the scene, rewrite it in the speaker's own logic or remove it.

Give recurring speakers a compact voice card in the screenplay or director brief:

```text
周启明｜目标：尽快看到可量化结果｜策略：压截止日期、把复杂问题改写成数字｜语言：短句、反问、很少承认不确定｜回避：法律和组织责任
高峰｜目标：保住销售部门的解释权｜策略：质疑口径、把风险推回流程｜语言：表面配合、句子留后门｜回避：直接说害怕裁员
```

Dialogue quality is not dialogue quantity. Prefer interruption, silence, a glance, an empty cup, an unfinished sentence, or a character acting against their words when that is more cinematic.

## 2. Establish one source of truth

The screenplay owns story meaning. `dialogue-ledger.json` owns the exact rendered wording and speaker assignment. Clip prompts must be derived from the ledger, never from memory or a loose synopsis.

Recommended schema:

```json
{
  "version": 1,
  "language": "zh-CN",
  "characters": [
    {"id": "chen-mo", "name": "陈默", "voice": "31岁男声，克制，语速中等"},
    {"id": "he-shifu", "name": "何师傅", "voice": "57岁男声，低沉，慢半拍"}
  ],
  "clips": [
    {
      "id": "clip-01",
      "utterances": [
        {
          "id": "c01-u01",
          "speaker_id": "he-shifu",
          "speaker_name": "何师傅",
          "addressee": "陈默",
          "text": "卡过期了。",
          "start_seconds": 4.0,
          "end_seconds": 5.2,
          "delivery": "平静陈述，不带嘲讽",
          "visibility": "on_screen",
          "production_path": "generated_sync"
        }
      ]
    }
  ]
}
```

Rules:

- Use one stable character ID and exact display name throughout screenplay, ledger, manifest, prompt, asset map, and QA notes.
- Give every utterance a globally unique ID.
- Preserve exact punctuation and wording between ledger and prompt.
- `start_seconds < end_seconds <= clip duration`; utterances must not overlap unless deliberate overlap is explicitly designed.
- Do not put non-spoken actions, sound effects, labels, or delivery notes in `text`.
- Use `visibility: off_screen` only when the dramatic purpose requires it; state the sound source and ensure no visible character mouths the line.
- Set `production_path` per utterance to `generated_sync`, `post_sync`, or `sound_led`. For `post_sync`, also track the approved audio file and final absolute timeline when available; for `sound_led`, record the visible coverage and the speaker's physical location.

## 3. Canonical prompt form

Use one line per utterance inside the timed beat:

```text
4.0—5.2秒｜[c01-u01] 说话人：何师傅；受话人：陈默；何师傅在画面右侧清晰可见，嘴唇与普通话同步，低沉平静地说：{卡过期了。} 陈默全程闭嘴，只抬眼看他。镜头保持何师傅单人中近景，不切到陈默口型。
```

Before the timed beats, add a compact lock:

```text
对白与声源锁定：本段只有何师傅和陈默。c01-u01只属于何师傅；何师傅发声时陈默闭嘴。两人声线固定，不交换台词，不替对方动嘴，不增加画外音。
```

If both characters speak, separate coverage:

```text
4.0—5.2秒｜[c02-u01] 说话人：陈默；受话人：何师傅；陈默单人近景说：{我在里面上班。} 何师傅在虚焦前景，闭嘴。
6.0—7.5秒｜[c02-u02] 说话人：何师傅；受话人：陈默；切何师傅反打，他说：{公司的人都有工牌。} 陈默离画且不发声。
```

Prefer no more than two speakers and two short utterances in one generated clip. When a line exchange needs faster timing, split it into adjacent clips rather than compressing speaker ownership. Reaction shots may continue after a line, but braces appear only once.

The canonical visible-speaker form is a **plan**, not a reliable lip-sync command. If the provider repeatedly fails on a speaking face, use a shorter single-speaker shot, a verified dedicated post-sync pass, or a motivated reaction/detail shot with clear sound source. Never claim the native generator produced accurate mouth shapes before inspecting the rendered clip at normal speed.

## 4. Avoid ambiguous constructions

Bad:

```text
门口回头：{你没问我们平时怎么活。}
何师傅看门又看他。{AI能开门吗？}
周总：{法务不懂AI。} 陈默：{他们懂法院。}
最终画面：陈默：{他们懂法院。}
```

Problems: missing speaker name, action used as a speaker label, two speakers compressed into one beat, and dialogue duplicated in the final-frame instruction.

Good:

```text
9.0—10.4秒｜[c14-u02] 说话人：周启明；受话人：陈默；周启明单人近景，略抬下巴说：{法务不懂AI。} 陈默离画、闭嘴。
11.0—12.2秒｜[c14-u03] 说话人：陈默；受话人：周启明；切陈默稳定近景，他停半拍说：{他们懂法院。} 周启明离画、闭嘴。
最终画面：陈默说完后保持目光，嘴唇闭合；镜头静止0.8秒。
```

## 5. Timing and performance

Estimate spoken Chinese from the actual `text`, not from repeated prompt braces. A normal dramatic delivery is usually 3–4.5 Chinese characters per second, then add breathing, listening, and reaction time. Short sharp replies still need a lead-in and a visible finish.

Do not direct every line as `自然说`. Specify the playable action or subtext: tests him, stalls for time, suppresses a smile, refuses to accept the premise, or asks while already knowing the answer. Avoid emotional adjectives that cannot be performed visibly.

## 6. Preflight and rendered QA

Before paid generation, audit every clip:

1. Ledger speaker exists in the character list and appears in the clip references when on screen.
2. Prompt contains the exact utterance ID, speaker name, addressee, and text once.
3. No dialogue braces exist outside canonical utterance lines.
4. Speaker and listener have explicit mouth states and non-overlapping time ranges.
5. Camera coverage makes the sound source unambiguous.
6. Final frame describes post-speech pose with closed mouth and contains no braces.

After rendering, inspect or transcribe each utterance and record pass/fail for:

- correct words;
- correct speaker face;
- correct voice identity;
- speaker lip sync;
- listener mouth closed;
- no duplicated or invented line;
- timing and edit continuity.

Check onset and offset in context: the mouth should begin with the audible syllables, stop when speech ends, and not continue “talking” through the listener's reaction. Speech-to-text can check wording but cannot certify lip movement. Review the actual mouth and audio together; record timecodes of mismatches and the repair path.

Wrong-speaker dialogue is a hard failure. Regenerate that clip with simpler coverage, fewer simultaneous faces, a stronger speaker close-up, or one utterance per clip. Do not repair the story by accepting the reassignment.
