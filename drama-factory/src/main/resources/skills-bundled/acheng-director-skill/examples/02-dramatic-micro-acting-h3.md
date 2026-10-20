# 文戏对峙｜把钥匙交出来

状态：完整生产卡及提示词已编译；图像仅有随包灰模构图示意，未调用影视生成模型。

- 总时长：20 秒；最大生成窗：10 秒；24 fps。
- 数据真值源：[02-drama.production.json](02-drama.production.json)。
- 声音：现场音；非叙事配乐 N/A。

## 剧情与人物选择

受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手。陆川承认之前拒绝协作，并把钥匙交给她。岑禾以共同行动回应，右腕伤势没有因为情绪转变消失。

A：钥匙是否交出。
B：独断保护转向共同承担。
C：前次事故仅由明确台词提出，本段不擅自补回忆。

五阶段可见弧光：开场攥钥匙保留控制 → 看见包扎手腕承受旧选择代价 → 松开拇指先试探 → 交钥匙承担失去控制 → 停手不夺回，接受一起行动。

## 登记场景与人物

```json
{
  "scenes": [
    {
      "id": "S01",
      "name": "维修室",
      "space": "One desk, east window, west doorway and a fixed brass-key hook",
      "version": "v1",
      "entrances": [
        "west service route"
      ],
      "exits": [
        "east service route"
      ],
      "landmarks": [
        "One desk, east window, west doorway and a fixed brass-key hook"
      ],
      "key_light": "fixed world-east source",
      "prompt_description": "The maintenance room contains one wooden desk, an east-facing window, a west doorway and a brass-key hook on the rear dark wall. Soft east-window light crosses the desk and falls off toward the west wall."
    }
  ],
  "characters": [
    {
      "id": "CHAR_LU",
      "name": "Lu Chuan",
      "height_m": 1.8,
      "identity": "Original design; appearance defined by the production prose, not by a franchise reference",
      "prompt_description": "Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt."
    },
    {
      "id": "CHAR_CEN",
      "name": "Cen He",
      "height_m": 1.7,
      "identity": "Original design; appearance defined by the production prose, not by a franchise reference",
      "prompt_description": "Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers."
    }
  ]
}
```

## 逐镜生产卡

### FILM-S01-SH001｜0.000–10.000 秒

Lu Chuan, an adult operator with a short scar over the right eyebrow and a gray work jacket, sits on the left side of the maintenance desk. Cen He, an adult technician with tied dark hair and an olive coat, holds her empty palm near the brass key in his hand. The single east window lights their cheek planes and the key; the dark wall behind them stays quiet. His previously bandaged right wrist rests on the desk, so his left hand carries the key.

```json
{
  "id": "FILM-S01-SH001",
  "scene_id": "S01",
  "start_frame": 0,
  "end_frame": 240,
  "visual": "Lu Chuan, an adult operator with a short scar over the right eyebrow and a gray work jacket, sits on the left side of the maintenance desk. Cen He, an adult technician with tied dark hair and an olive coat, holds her empty palm near the brass key in his hand. The single east window lights their cheek planes and the key; the dark wall behind them stays quiet. His previously bandaged right wrist rests on the desk, so his left hand carries the key.",
  "camera": {
    "previs_id": "103",
    "lens_mm": 65,
    "sensor_basis": "full-frame equivalent",
    "shutter_angle": 180,
    "movement": "slow controlled push",
    "path": "twenty-centimeter slow push toward the shared desk plane",
    "target": "the visible action and contact plane",
    "adaptation": "project-specific amplitude and speed; source ID is a motion-family reference",
    "description": "The camera advances twenty centimeters in a medium close two-shot, keeping Lu's eyes, both shoulder lines and his left hand visible without a cut."
  },
  "characters": [
    {
      "id": "CHAR_LU",
      "position": [
        0.35,
        0.55
      ],
      "facing": "toward screen right",
      "gaze": "toward Cen He",
      "weapon_hand": "both hands visible and unarmed",
      "weapon_direction": "no weapon present in this scene"
    },
    {
      "id": "CHAR_CEN",
      "position": [
        0.7,
        0.55
      ],
      "facing": "toward screen left",
      "gaze": "toward Lu Chuan",
      "weapon_hand": "both hands visible and unarmed",
      "weapon_direction": "no weapon present in this scene"
    }
  ],
  "features": {
    "core_emotion": true,
    "combat": false,
    "supernatural_vfx": false,
    "colossal": false
  },
  "dialogues": [
    {
      "speaker_id": "S1",
      "speaker_name": "Lu Chuan",
      "language": "Chinese",
      "text": "上次是我没听。现在你来。",
      "delivery": "speaking slowly in a low, slightly rough voice",
      "start": 144,
      "end": 222,
      "voiceover": false
    }
  ],
  "audio": {
    "foley": [
      "Fabric shifts softly at the elbow and the brass key makes one small ring."
    ],
    "low_frequency_hz": null,
    "no_low_frequency_reason": "A quiet desk conversation has no designed bass event."
  },
  "outcome_events": [],
  "state_in": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_LU"
    }
  },
  "state_out": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_LU"
    }
  },
  "performance": {
    "beat_id": "EX-S01-B01",
    "dominant_track": "gaze",
    "tracks": {
      "gaze": {
        "start": 0,
        "end": 66,
        "cue": "Lu's gaze moves from the key to Cen's open hand and then settles on her eyes.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "breath": {
        "start": 36,
        "end": 100,
        "cue": "He interrupts one inhale, swallows once, and releases a longer breath.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "shoulder": {
        "start": 72,
        "end": 132,
        "cue": "His left shoulder slowly drops while the injured right wrist stays supported.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "body_hands": {
        "start": 108,
        "end": 220,
        "cue": "His left thumb releases pressure on the key ring without yet handing it over.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "dialogue": {
        "start": 144,
        "end": 236,
        "cue": "His lips stay closed until the agreed line, then close again after the final word.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      }
    },
    "acting_design": {
      "version": "1.0",
      "mode": "restrained",
      "character_id": "CHAR_LU",
      "objective": "decide whether to transfer responsibility without losing dignity",
      "tactic": "admit the previous refusal, then offer the key as a concrete concession",
      "subtext": "he wants cooperation but tests whether Cen will accept it without taking control by force",
      "trigger": "Cen leaves an empty palm between them instead of reaching for the key",
      "personality_signature": "he lets a practical hand movement speak before he allows his voice to soften",
      "action_units": [
        {
          "start": 0,
          "end": 66,
          "cause": "the empty palm stays available without pressure",
          "action": "moves his gaze from the key to Cen's palm and then to her eyes",
          "gaze": "key, palm, then her eyes",
          "face": "alert at first, then less guarded",
          "follow_through": "keeps the key in the left hand while the injured right wrist remains supported",
          "speech_anchor": "silent",
          "delivery": "hold the first breath for one beat",
          "prop": "the brass key remains in the left hand",
          "camera": "keep the eyes, shoulder line and key in one readable plane",
          "sound": "a small fabric shift follows the gaze change"
        },
        {
          "start": 108,
          "end": 220,
          "cause": "the admission reaches its final clause",
          "action": "loosens the left thumb on the key ring and lets the shoulder drop before speaking",
          "gaze": "steady on Cen's eyes",
          "face": "mouth controlled, jaw no longer clenched",
          "follow_through": "the key stays offered rather than snatched back after the line",
          "speech_anchor": "现在你来",
          "delivery": "low rough voice, slow pace, a short pause before the final clause",
          "prop": "the right wrist remains supported on the desk",
          "camera": "advance twenty centimeters without cutting away from the hand",
          "sound": "the ring gives one small metal click"
        }
      ],
      "motion_arc": {
        "anticipation": "the gaze and thumb prepare the transfer before the voice changes",
        "accent": "the shoulder drops on the offer of responsibility",
        "follow_through": "the key remains visible after the line instead of returning to the fist",
        "settle": "the left hand rests open enough for Cen to receive the key"
      },
      "speech_delivery": {
        "voice_timbre": "a low, slightly rough adult male voice",
        "pace": "slow and deliberate",
        "pitch": "slightly lower on the admission",
        "volume": "quiet indoor conversational volume",
        "pauses": [
          {
            "after_text": "没听。",
            "duration_ms": 220
          }
        ],
        "emphasis": [
          {
            "text": "你来",
            "delivery": "give the pronoun and verb a restrained release"
          }
        ]
      },
      "cut_behavior": [],
      "continuity_in": "the key remains in Lu's left hand and the bandaged right wrist stays supported",
      "continuity_out": "the key is still offered and the left thumb has released pressure",
      "exclusions": [
        "added dialogue",
        "a forceful grab with the injured right wrist",
        "a smile that turns the admission into a joke"
      ]
    }
  },
  "state_description": "Lu's bandaged right wrist is supported on the desk. The brass key is in his left hand; Cen's receiving palm is empty."
}
```

### FILM-S01-SH002｜10.000–20.000 秒

A medium-close view favors Cen on the right of the wooden desk, with Lu on the left. Cen leaves her open palm between them, with enough distance for Lu to decline. East-window light produces a narrow highlight on the key and a broad shadow across her olive coat.

```json
{
  "id": "FILM-S01-SH002",
  "scene_id": "S01",
  "start_frame": 240,
  "end_frame": 480,
  "visual": "A medium-close view favors Cen on the right of the wooden desk, with Lu on the left. Cen leaves her open palm between them, with enough distance for Lu to decline. East-window light produces a narrow highlight on the key and a broad shadow across her olive coat.",
  "camera": {
    "previs_id": "106",
    "lens_mm": 85,
    "sensor_basis": "full-frame equivalent",
    "shutter_angle": 180,
    "movement": "slow controlled lateral translation",
    "path": "ten-centimeter drift on the south side of the desk",
    "target": "the visible action and contact plane",
    "adaptation": "project-specific amplitude and speed; source ID is a motion-family reference",
    "description": "The camera drifts ten centimeters toward Cen while retaining Lu's hand at the lower edge; the desk and window preserve the same spatial axis."
  },
  "characters": [
    {
      "id": "CHAR_LU",
      "position": [
        0.35,
        0.55
      ],
      "facing": "toward screen right",
      "gaze": "toward Cen He",
      "weapon_hand": "both hands visible and unarmed",
      "weapon_direction": "no weapon present in this scene"
    },
    {
      "id": "CHAR_CEN",
      "position": [
        0.7,
        0.55
      ],
      "facing": "toward screen left",
      "gaze": "toward Lu Chuan",
      "weapon_hand": "both hands visible and unarmed",
      "weapon_direction": "no weapon present in this scene"
    }
  ],
  "features": {
    "core_emotion": true,
    "combat": false,
    "supernatural_vfx": false,
    "colossal": false
  },
  "dialogues": [
    {
      "speaker_id": "S2",
      "speaker_name": "Cen He",
      "language": "Chinese",
      "text": "那就一起把门打开。",
      "delivery": "speaking softly with clear consonants and an even pace",
      "start": 160,
      "end": 224,
      "voiceover": false
    }
  ],
  "audio": {
    "foley": [
      "Fabric shifts softly at the elbow and the brass key makes one small ring."
    ],
    "low_frequency_hz": null,
    "no_low_frequency_reason": "A quiet desk conversation has no designed bass event."
  },
  "outcome_events": [
    "EV_KEY"
  ],
  "state_in": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_LU"
    }
  },
  "state_out": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_CEN"
    }
  },
  "performance": {
    "beat_id": "EX-S01-B02",
    "dominant_track": "body_hands",
    "tracks": {
      "gaze": {
        "start": 0,
        "end": 66,
        "cue": "Cen holds eye contact without widening her eyes or looking at the key.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "breath": {
        "start": 36,
        "end": 100,
        "cue": "Her breath remains quiet, with a small inhale before replying.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "shoulder": {
        "start": 72,
        "end": 132,
        "cue": "Her shoulders relax while her neck remains upright and still.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "body_hands": {
        "start": 108,
        "end": 220,
        "cue": "She keeps the palm open; Lu places the key into it, and she closes her fingers only after contact.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      },
      "dialogue": {
        "start": 144,
        "end": 236,
        "cue": "Her voice stays low and clear; both mouths remain closed after her short answer.",
        "visibility": "medium-close framing includes the face, shoulder line and hands"
      }
    },
    "acting_design": {
      "version": "1.0",
      "mode": "observational",
      "character_id": "CHAR_CEN",
      "objective": "accept the offered responsibility while protecting the shared task",
      "tactic": "keep the palm open until contact, then close it only after the key arrives",
      "subtext": "she accepts the apology without rewarding it with a dramatic reaction",
      "trigger": "Lu's thumb releases the key ring",
      "personality_signature": "she holds eye contact, lets the receiving hand do the emotional work, and answers with a practical invitation",
      "action_units": [
        {
          "start": 0,
          "end": 72,
          "cause": "the key is offered but has not touched her hand",
          "action": "keeps the receiving palm open and her shoulders level",
          "gaze": "on Lu's eyes rather than the key",
          "face": "steady eyes with a small release around the mouth",
          "follow_through": "does not close the fingers before contact",
          "speech_anchor": "silent",
          "delivery": "take one quiet inhale before replying",
          "prop": "the open palm stays between the two people",
          "camera": "retain Lu's hand at the lower edge of frame",
          "sound": "cloth settles at the elbow"
        },
        {
          "start": 72,
          "end": 224,
          "cause": "the brass key reaches the center of the open palm",
          "action": "allows the fingers to close around the key and turns the answer toward cooperation",
          "gaze": "briefly checks the key, then returns to Lu's eyes",
          "face": "calm acceptance without a triumphant smile",
          "follow_through": "keeps the closed hand between them instead of hiding it",
          "speech_anchor": "一起",
          "delivery": "soft clear consonants at an even pace",
          "prop": "the key changes hands only after visible contact",
          "camera": "drift ten centimeters toward her while preserving the desk axis",
          "sound": "one small key ring after the fingers close"
        }
      ],
      "motion_arc": {
        "anticipation": "the empty palm establishes a boundary without reaching",
        "accent": "the fingers close on physical contact with the key",
        "follow_through": "the closed hand stays visible as proof of shared action",
        "settle": "the shoulders relax while the neck remains upright"
      },
      "speech_delivery": {
        "voice_timbre": "a clear adult female voice with an even center",
        "pace": "soft and measured",
        "pitch": "level, with a slight lift on the invitation",
        "volume": "quiet indoor conversational volume",
        "pauses": [
          {
            "after_text": "就",
            "duration_ms": 120
          }
        ],
        "emphasis": [
          {
            "text": "一起",
            "delivery": "make the shared-action word warm but practical"
          }
        ]
      },
      "cut_behavior": [],
      "continuity_in": "the empty palm remains open and the brass key is still held by Lu",
      "continuity_out": "the key rests in Cen's hand and both mouths close after the line",
      "exclusions": [
        "a second phone voice",
        "closing the hand before contact",
        "a triumphant pose that breaks the quiet negotiation"
      ]
    }
  },
  "state_description": "Lu's bandaged right wrist is supported on the desk. The brass key is in his left hand; Cen's receiving palm is empty."
}
```

## GPT Image 2 / 2.5 可直接复制提示词

按主体、媒介、构图、光材、密度、受控细节、当前风险顺序编译。执行尺寸和采样设置留给实际出图入口。

参考图：不需要，可纯文字生成。

```text
Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt. Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers. Create one live-action medium-close two-person keyframe in the maintenance room. Lu Chuan, an adult man with a short scar above his right eyebrow and a gray woven work jacket, sits on the left; his bandaged right wrist rests on the desk, and his left hand holds one brass key. Cen He, an adult woman with tied dark hair and an olive coat, sits on the right with an empty palm held between them. Capture the single moment before Lu releases the key. Use a 65 mm equivalent lens from the south side, showing eyes, shoulders and both hands together. One east window casts soft directional light across their cheek planes; a weak wall reflection leaves the shadow side readable. Skin has broad soft highlights, cloth folds retain fibrous edges only near the hands, and the brass key catches a narrow highlight. The rear wall and key hook remain quiet low-frequency shapes. Preserve identity, hand ownership, the bandage and the room geometry. Avoid waxy faces, extra hands and ghost texture.
```


## DRAMA_SEG01｜H3 T2VA 完整提示词

```text
integrated_multimodal_description:
Motion language: live_action at 24 fps, exposed on ones. Timing principle: let a small preparatory change precede the decisive hand action and hold the resulting state. Camera principle: keep the eye-line, receiving hand and prop contact readable before drifting closer. Staging principle: preserve the desk axis, left-right positions and the injured wrist limitation. Sound principle: keep room tone continuous and make each key contact a local foley event. Cut language: continuous.
This is a self-contained production instruction and must be readable without the production file, an earlier segment, or a hidden character bible. For every shot, explicitly state: the medium and visible subject appearance, screen position and facing; the current environment, landmarks and light direction; the exact starting pose, prop ownership, contact points and state; the factual trigger for each change; the chronological action, reaction and physical consequence; the camera framing, lens, movement type, direction, path, amplitude, speed and target; the source and timing of dialogue, foley, room tone and breath; the exact held state at the end and what can continue into the next shot. Render objective, social strategy and subtext as observable gaze, breath, posture, hand, facial and voice behavior. Keep cause and effect physically, spatially, temporally and socially coherent. Do not replace a visible action with a vague adjective, skip the transition between beats, collapse preparation, accent, follow-through or settle into one verb, or invent dialogue, objects, voices, cuts or state changes that are not written below.
[Shot 1] Live-action cinematic staging uses restrained facial movement and natural cloth response. Write this shot as a complete independent instruction: restate who is visible and where they are, the environment and light, the start state, the trigger, the ordered action and reaction, the camera path and speed, synchronized sound, and the resulting held state. Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt. Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers. The maintenance room contains one wooden desk, an east-facing window, a west doorway and a brass-key hook on the rear dark wall. Soft east-window light crosses the desk and falls off toward the west wall. At the start of this shot: Lu's bandaged right wrist is supported on the desk. The brass key is in his left hand; Cen's receiving palm is empty. The acting design's continuity-out is visible before the shot ends: the key is still offered and the left thumb has released pressure Lu Chuan, an adult operator with a short scar over the right eyebrow and a gray work jacket, sits on the left side of the maintenance desk. Cen He, an adult technician with tied dark hair and an olive coat, holds her empty palm near the brass key in his hand. The single east window lights their cheek planes and the key; the dark wall behind them stays quiet. His previously bandaged right wrist rests on the desk, so his left hand carries the key. The camera advances twenty centimeters in a medium close two-shot, keeping Lu's eyes, both shoulder lines and his left hand visible without a cut. The camera uses a 65 mm lens under the full-frame equivalent convention, with a 180-degree shutter-angle convention; movement: slow controlled push; path: twenty-centimeter slow push toward the shared desk plane; target: the visible action and contact plane. At shot entry, Lu Chuan has normalized screen anchor x=0.35, y=0.55 (left-to-right and top-to-bottom); facing toward screen right; gaze toward Cen He; hand or weapon state: both hands visible and unarmed; weapon direction or absence: no weapon present in this scene. At shot entry, Cen He has normalized screen anchor x=0.7, y=0.55 (left-to-right and top-to-bottom); facing toward screen left; gaze toward Lu Chuan; hand or weapon state: both hands visible and unarmed; weapon direction or absence: no weapon present in this scene. During 0.000–2.750 seconds within this shot: Lu's gaze moves from the key to Cen's open hand and then settles on her eyes. Visibility: medium-close framing includes the face, shoulder line and hands During 1.500–4.167 seconds within this shot: He interrupts one inhale, swallows once, and releases a longer breath. Visibility: medium-close framing includes the face, shoulder line and hands During 3.000–5.500 seconds within this shot: His left shoulder slowly drops while the injured right wrist stays supported. Visibility: medium-close framing includes the face, shoulder line and hands During 4.500–9.167 seconds within this shot: His left thumb releases pressure on the key ring without yet handing it over. Visibility: medium-close framing includes the face, shoulder line and hands During 6.000–9.833 seconds within this shot: His lips stay closed until the agreed line, then close again after the final word. Visibility: medium-close framing includes the face, shoulder line and hands The performance uses restrained acting. Immediate objective: decide whether to transfer responsibility without losing dignity. Tactic: admit the previous refusal, then offer the key as a concrete concession. Social subtext: he wants cooperation but tests whether Cen will accept it without taking control by force. Trigger: Cen leaves an empty palm between them instead of reaching for the key. Visible personality signature: he lets a practical hand movement speak before he allows his voice to soften. During 0.000–2.750 seconds within this shot, because the empty palm stays available without pressure, the character moves his gaze from the key to Cen's palm and then to her eyes. Gaze: key, palm, then her eyes. Face: alert at first, then less guarded. Follow-through: keeps the key in the left hand while the injured right wrist remains supported. Delivery: hold the first breath for one beat. Prop continuity: the brass key remains in the left hand. Camera: keep the eyes, shoulder line and key in one readable plane. Coupled sound: a small fabric shift follows the gaze change. During 4.500–9.167 seconds within this shot, because the admission reaches its final clause, the character loosens the left thumb on the key ring and lets the shoulder drop before speaking. Gaze: steady on Cen's eyes. Face: mouth controlled, jaw no longer clenched. Follow-through: the key stays offered rather than snatched back after the line. Delivery: low rough voice, slow pace, a short pause before the final clause. The movement punctuates the source phrase at characters 8 through 11 of spoken line 1 in this shot (a performance cue, not an additional utterance). Prop continuity: the right wrist remains supported on the desk. Camera: advance twenty centimeters without cutting away from the hand. Coupled sound: the ring gives one small metal click. The motion phrase has this arc: anticipation—the gaze and thumb prepare the transfer before the voice changes; accent—the shoulder drops on the offer of responsibility; follow-through—the key remains visible after the line instead of returning to the fist; settle—the left hand rests open enough for Cen to receive the key. Voice delivery uses a low, slightly rough adult male voice, slow and deliberate, slightly lower on the admission and quiet indoor conversational volume. Pause after the source phrase at characters 5 through 7 of spoken line 1 in this shot (a performance cue, not an additional utterance) for 220 milliseconds. Emphasize the source phrase at characters 10 through 11 of spoken line 1 in this shot (a performance cue, not an additional utterance) with give the pronoun and verb a restrained release. Continuity in: the key remains in Lu's left hand and the bandaged right wrist stays supported. Continuity out: the key is still offered and the left thumb has released pressure. Avoid added dialogue. Avoid a forceful grab with the injured right wrist. Avoid a smile that turns the admission into a joke. Fabric shifts softly at the elbow and the brass key makes one small ring. During 6.000–9.250 seconds within this shot, Lu Chuan (S1), speaking slowly in a low, slightly rough voice, says: <d>[Chinese] 上次是我没听。现在你来。</d> Keep every word intelligible: synchronize visible mouth shapes to the original words, preserve the written pauses and emphasis, and keep competing action noise below the voice unless the production data explicitly requires overlap. At the end of this shot, carry forward these recorded constraints: Lu Chuan remains in the stabilized or treated injury state; preserve the described functional limitations; the brass key remains with Lu Chuan.

overall_soundscape:
Quiet ventilation and distant rain remain under breathing, a sleeve brushing the desk and the small ring of a brass key.

non_diegetic_music:
N/A
```


## DRAMA_SEG02｜H3 T2VA 完整提示词

```text
integrated_multimodal_description:
Motion language: live_action at 24 fps, exposed on ones. Timing principle: let a small preparatory change precede the decisive hand action and hold the resulting state. Camera principle: keep the eye-line, receiving hand and prop contact readable before drifting closer. Staging principle: preserve the desk axis, left-right positions and the injured wrist limitation. Sound principle: keep room tone continuous and make each key contact a local foley event. Cut language: continuous.
This is a self-contained production instruction and must be readable without the production file, an earlier segment, or a hidden character bible. For every shot, explicitly state: the medium and visible subject appearance, screen position and facing; the current environment, landmarks and light direction; the exact starting pose, prop ownership, contact points and state; the factual trigger for each change; the chronological action, reaction and physical consequence; the camera framing, lens, movement type, direction, path, amplitude, speed and target; the source and timing of dialogue, foley, room tone and breath; the exact held state at the end and what can continue into the next shot. Render objective, social strategy and subtext as observable gaze, breath, posture, hand, facial and voice behavior. Keep cause and effect physically, spatially, temporally and socially coherent. Do not replace a visible action with a vague adjective, skip the transition between beats, collapse preparation, accent, follow-through or settle into one verb, or invent dialogue, objects, voices, cuts or state changes that are not written below.
[Shot 1] Live-action cinematic staging uses restrained facial movement and natural cloth response. Write this shot as a complete independent instruction: restate who is visible and where they are, the environment and light, the start state, the trigger, the ordered action and reaction, the camera path and speed, synchronized sound, and the resulting held state. Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt. Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers. The maintenance room contains one wooden desk, an east-facing window, a west doorway and a brass-key hook on the rear dark wall. Soft east-window light crosses the desk and falls off toward the west wall. At the start of this shot: Lu's bandaged right wrist is supported on the desk. The brass key is in his left hand; Cen's receiving palm is empty. The acting design's continuity-out is visible before the shot ends: the key rests in Cen's hand and both mouths close after the line A medium-close view favors Cen on the right of the wooden desk, with Lu on the left. Cen leaves her open palm between them, with enough distance for Lu to decline. East-window light produces a narrow highlight on the key and a broad shadow across her olive coat. The camera drifts ten centimeters toward Cen while retaining Lu's hand at the lower edge; the desk and window preserve the same spatial axis. The camera uses a 85 mm lens under the full-frame equivalent convention, with a 180-degree shutter-angle convention; movement: slow controlled lateral translation; path: ten-centimeter drift on the south side of the desk; target: the visible action and contact plane. At shot entry, Lu Chuan has normalized screen anchor x=0.35, y=0.55 (left-to-right and top-to-bottom); facing toward screen right; gaze toward Cen He; hand or weapon state: both hands visible and unarmed; weapon direction or absence: no weapon present in this scene. At shot entry, Cen He has normalized screen anchor x=0.7, y=0.55 (left-to-right and top-to-bottom); facing toward screen left; gaze toward Lu Chuan; hand or weapon state: both hands visible and unarmed; weapon direction or absence: no weapon present in this scene. During 0.000–2.750 seconds within this shot: Cen holds eye contact without widening her eyes or looking at the key. Visibility: medium-close framing includes the face, shoulder line and hands During 1.500–4.167 seconds within this shot: Her breath remains quiet, with a small inhale before replying. Visibility: medium-close framing includes the face, shoulder line and hands During 3.000–5.500 seconds within this shot: Her shoulders relax while her neck remains upright and still. Visibility: medium-close framing includes the face, shoulder line and hands During 4.500–9.167 seconds within this shot: She keeps the palm open; Lu places the key into it, and she closes her fingers only after contact. Visibility: medium-close framing includes the face, shoulder line and hands During 6.000–9.833 seconds within this shot: Her voice stays low and clear; both mouths remain closed after her short answer. Visibility: medium-close framing includes the face, shoulder line and hands The performance uses observational acting. Immediate objective: accept the offered responsibility while protecting the shared task. Tactic: keep the palm open until contact, then close it only after the key arrives. Social subtext: she accepts the apology without rewarding it with a dramatic reaction. Trigger: Lu's thumb releases the key ring. Visible personality signature: she holds eye contact, lets the receiving hand do the emotional work, and answers with a practical invitation. During 0.000–3.000 seconds within this shot, because the key is offered but has not touched her hand, the character keeps the receiving palm open and her shoulders level. Gaze: on Lu's eyes rather than the key. Face: steady eyes with a small release around the mouth. Follow-through: does not close the fingers before contact. Delivery: take one quiet inhale before replying. Prop continuity: the open palm stays between the two people. Camera: retain Lu's hand at the lower edge of frame. Coupled sound: cloth settles at the elbow. During 3.000–9.333 seconds within this shot, because the brass key reaches the center of the open palm, the character allows the fingers to close around the key and turns the answer toward cooperation. Gaze: briefly checks the key, then returns to Lu's eyes. Face: calm acceptance without a triumphant smile. Follow-through: keeps the closed hand between them instead of hiding it. Delivery: soft clear consonants at an even pace. The movement punctuates the source phrase at characters 3 through 4 of spoken line 1 in this shot (a performance cue, not an additional utterance). Prop continuity: the key changes hands only after visible contact. Camera: drift ten centimeters toward her while preserving the desk axis. Coupled sound: one small key ring after the fingers close. The motion phrase has this arc: anticipation—the empty palm establishes a boundary without reaching; accent—the fingers close on physical contact with the key; follow-through—the closed hand stays visible as proof of shared action; settle—the shoulders relax while the neck remains upright. Voice delivery uses a clear adult female voice with an even center, soft and measured, level, with a slight lift on the invitation and quiet indoor conversational volume. Pause after the source phrase at characters 2 through 2 of spoken line 1 in this shot (a performance cue, not an additional utterance) for 120 milliseconds. Emphasize the source phrase at characters 3 through 4 of spoken line 1 in this shot (a performance cue, not an additional utterance) with make the shared-action word warm but practical. Continuity in: the empty palm remains open and the brass key is still held by Lu. Continuity out: the key rests in Cen's hand and both mouths close after the line. Avoid a second phone voice. Avoid closing the hand before contact. Avoid a triumphant pose that breaks the quiet negotiation. Fabric shifts softly at the elbow and the brass key makes one small ring. During 6.667–9.333 seconds within this shot, Cen He (S1), speaking softly with clear consonants and an even pace, says: <d>[Chinese] 那就一起把门打开。</d> Keep every word intelligible: synchronize visible mouth shapes to the original words, preserve the written pauses and emphasis, and keep competing action noise below the voice unless the production data explicitly requires overlap. At local shot time 00:07.917, the recorded state change is: Lu visibly places the brass key in Cen's open palm. At the end of this shot, carry forward these recorded constraints: Lu Chuan remains in the stabilized or treated injury state; preserve the described functional limitations; the brass key remains with Cen He.

overall_soundscape:
Quiet ventilation and distant rain remain under breathing, a sleeve brushing the desk and the small ring of a brass key.

non_diegetic_music:
N/A
```

## 场记末尾回写

```json
{
  "initial": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_LU"
    }
  },
  "events": [
    {
      "id": "EV_KEY",
      "frame": 430,
      "shot_id": "FILM-S01-SH002",
      "domain": "prop",
      "target": "BRASS_KEY",
      "before": "CHAR_LU",
      "after": "CHAR_CEN",
      "reason": "Lu visibly places the brass key in Cen's open palm."
    }
  ],
  "final": {
    "characters": {
      "CHAR_LU": {
        "ammo": 0,
        "trauma_phase": 1
      },
      "CHAR_CEN": {
        "ammo": 0,
        "trauma_phase": null
      }
    },
    "scenes": {
      "S01": 0
    },
    "props": {
      "BRASS_KEY": "CHAR_CEN"
    }
  }
}
```

## 结果验收

运行 audit_storyboard_quality.py 检查当前数据。实际生成后逐帧看身份、接触、主光、伤势和道具；音轨核对对白与频谱。未生成时视觉及声学实测保持 UNVERIFIED。
