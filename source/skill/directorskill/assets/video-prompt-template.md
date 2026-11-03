# Video Motion Prompt Template (Mode F)

Load this file when you are at Step 10 (AI video prompt construction) or the user asked for Mode
F — finished prompts to paste into a generator. The four prompt shapes and their slot orders,
which slots a given model actually reads, and what its UI controls instead of text are owned by
[AI video tool adapters](../references/ai-video-tool-adapters.md). Word choice, word budgets,
banned words, the negative library and the cut order for an over-long prompt are owned by the
[prompt lexicon](../references/prompt-lexicon.md). This file owns the fill-in forms and the
per-prompt self-check.

Every worked example inherits from [director book](director-book-template.md) and
[shot plan](shot-plan-template.md), and animates the stills built in
[keyframe prompt template](keyframe-prompt-template.md): project `Under the Door` (`UTD`), scene
7, 22s, 16:9, five shots — a courier hesitates outside a Republican-era Shanghai apartment door,
slides an envelope under it, and leaves.

## Token economy

The slot order below is S1 in [AI video tool adapters](../references/ai-video-tool-adapters.md),
which owns the four shapes and their slot lists; the word budgets — for image-to-video, roughly
40–80 words — the reasons the order matters, and the cut order for an over-long prompt are owned by
the [prompt lexicon](../references/prompt-lexicon.md). What this table adds is how that budget
divides and when a slot disappears entirely. `Slot` is position in the prompt, not importance: the
action and the end state are the two things the lexicon says never to cut.

| Slot | Content | Share of the budget | Cut it entirely when… |
|---|---|---|---|
| 1 | Camera behavior — one move, one speed, or `locked` | 10–15% | The tool has a camera-motion UI; set it there, not in text |
| 2 | Subject start state, only what the input frame already shows | 10% | Text-to-video: there is no input frame to anchor to |
| 3 | One primary action, with its pace and direction | 32% | Never |
| 4 | One environmental response | 10% | The scene has no movable element |
| 5 | Explicit end state | 15% | Never |
| 6 | Continuity lock — the book's invariants compressed to one clause | 10% | The clip is under 2s and locked |
| 7 | Exclusions — two or three risk classes | 8% | The tool has a real negative field; put them there instead |

Pace belongs inside slot 3 and does not get a slot of its own. A bare pace word floating between
the lock and the exclusions attaches itself to the nearest verb, which is as often the camera as
the subject — say "lowers slowly to his thigh over about two seconds", not "slow motion".

Slots 1–5 come to roughly 80% of an image-to-video prompt. If most of the prompt
re-describes what the input image already proves, you are paying tokens for nothing and diluting
the action. Each filled example below carries its word count — check yours against them, not
against how thorough the prompt feels.

## Slot dictionary

| Bracket | Put in it | Never put in it |
|---|---|---|
| `[camera]` | One named move plus a speed and a distance, or `locked` | A second move; a move the tool controls by slider; "dynamic camera" |
| `[start state]` | A static, checkable body position that matches the input frame | New wardrobe, new props, a new location |
| `[action]` | One transitive verb, its object, a speed, a direction | Interior states: realizes, remembers, feels, struggles, hesitates |
| `[environment]` | One movable element: a shadow, cloth, dust, a light line, breath | A second character; a second action by the subject |
| `[end state]` | A pose or composition you could photograph as a still | "and then he leaves and it fades" — that is two shots |
| `[invariants]` | The book's `ID_`, `LOCK_`, `LIGHT_` strings, compressed to one clause | A full re-description of the input image |
| `[negatives]` | The 2–4 risks specific to this shot, plus only those `NEG_BASE` classes this framing can actually produce, to a combined ceiling of about six — the dilution rule is owned by [prompt lexicon](../references/prompt-lexicon.md) | A wall of negatives copied from another shot; a category ("no modern objects") rather than named instances |
| `[sound]` | Only if the model generates audio: the source, not an adjective | Anything the sound plan owns; see Mode H |

Where the tool has a separate negative field, put the whole of `NEG_BASE` in it — it costs nothing
there. Inline negatives are the ones that have to fight the positive prompt for attention, so
inline only what this framing can actually produce: "no extra people" earns its place in a landing
wide, not in an extreme close-up of a 4cm gap.

## Template 1 — image-to-video, single shot

```text
[Camera]. Starting from the input image, [subject] is [start state], then [one primary action
with speed and direction]. [Environment element] [moves how]. End with [explicit end state].
Maintain [invariants]. Avoid [negatives].
```

Filled — `UTD_SC07_SH02`, 5s, from `UTD_SC07_SH02_v03_kf-first.png`. The input frame has the hand
down, because that is where shot 01 left it; the raised knuckles are what this clip has to produce:

```text
Locked camera. His right hand rises until the knuckles stop 3cm short of the wood, holds about one
second, then lowers slowly to his thigh over about two seconds. The knuckles never touch the door.
His breath shows once against the cold rim behind him. End with the hand at his thigh, still facing
the door, the envelope still up at chest in his left hand. Same face, cap, jacket and satchel side;
same bulb camera-left. Avoid: the hand touching the door, knocking, the door opening, a second
person, rendered text.
```

91 words, just over the lexicon's 40–80 band, and two of them are the whole shot: `3cm short` and
`never touch`. If the tool truncates, the breath clause goes first. There is also no separate
start-state clause, because the action names the limb the frame already shows at rest — slot 2
earns its tokens only when the input frame leaves it ambiguous which part of the body moves. What
is *not* in it is the rest of the identity string and the whole room; the input frame proves both,
and re-describing them is the most common way a prompt starves its own action.

中文变体 / Chinese-UI variant, same shot:

```text
固定镜头。他的右手抬起，指节停在距门板3厘米处，停约1秒，再用约2秒缓慢放下到大腿旁。
指节始终不碰到门。他的呼吸在身后的冷调轮廓光上出现一次。结尾停在：右手垂在大腿旁，
仍正对着门，信封仍举在左手胸前。保持同一张脸、帽子、棉袄、左肩挎带；灯泡仍在镜头左侧。
避免：手碰到门、敲门、门被打开、出现第二个人、画面出现文字。
```

## Template 2 — first frame + last frame

Use when the change has a designed endpoint, and always for the scene's highest-risk shot. The
two frames must be one action apart; if you cannot describe the bridge in a single clause, split
the shot.

```text
Use the first image as the opening frame and the second image as the closing frame. The shot
travels from [first-frame state] to [last-frame state] through [one continuous action].
Camera [one move with distance and duration, or locked]. Motion is [pace word].
Preserve [invariants]. No [negatives].
```

A pair prompt should be *shorter* than a single-frame one, not longer: both ends are already
photographs, so the text pays only for the bridge between them. Describing the two stills back to
the tool is the classic way to waste a keyframe pair.

It is also the one generation you order at cut length rather than at cut length plus a handle:
both ends are pinned by approved stills, so there is no ramp-in to discard and no drift-out to
trim. That is the single licensed exception to the handle rule in
[editing and assembly](../references/editing-and-assembly.md), and it does not extend to a
dialogue take built as a pair — the performance happens between the two frames, which is exactly
where the drift is.

Filled — `UTD_SC07_SH04`, 6s, the scene's one moving shot and its highest-failure clip:

```text
Use the first image as the opening frame and the second image as the closing frame. Between them,
one continuous feed-and-push: the envelope slides under the door, then two fingers push it the last
few centimetres until the fingertips meet the wood, with no stall between the two halves. Camera
dollies in 25cm over the full six seconds, one direction, no reverse, no reframe. Preserve the same
courier, satchel on the left shoulder, the door chip at frame-right, the bulb camera-left. No third
hand, no bending or tearing of the paper, no envelope visible at the end.
```

97 words, and the last sentence is three negatives — correct here and nowhere else in this scene.
This is the plan's one `Red` shot, and each of the three names a failure it has already been graded
as likely to produce.

## Template 3 — text-to-video

No input frame, so you pay for description. Everything a keyframe would have proven now has to be
written, and identity is the part that will not hold from words alone — expect more retries per
usable second, and prefer this mode for plates, inserts, and shots with no face.

```text
[Format, aspect, stock/finish]. [Subject with concrete identity and wardrobe]. [Location, era,
time of day]. [One primary action with speed and direction]. [Shot size, angle, camera move].
[Named light source, side, ratio]. [Composition and depth]. [Sound if supported]. [Negatives].
```

Filled — `UTD_SC07_SH03`, 3s, the one shot in the scene with no face in it, which is exactly why it
can survive text-to-video:

```text
16:9, 35mm film stock, fine grain, low saturation. The 4cm gap under a dark-stained apartment
door, worn red floor tile, dark-green wainscot above; a third-floor landing in 1937 Shanghai,
winter. No figure except the toe of one cloth shoe at the bottom edge, motionless. A shadow
crosses the warm light line under the door from inside, right to left, over about two seconds, and
the line is unbroken again. Extreme close-up, head-on, camera 15cm off the floor, 85mm, locked.
The only light in frame is the spill from the room behind the door; the near side of frame is
three stops under. No rendered text or numerals, no watermark, no second foot, the door never
opens.
```

116 words, inside the lexicon's 60–120 text-to-video band. Read against Template 1 it shows where
the extra 25 went: format, era, materials, and light source — every line the input frame would
otherwise have supplied for free.

## Template 4 — multi-shot / timestamped

Only for models that honor timestamps. Put the invariants once in the `Overall` line, never
inside each shot: per-shot repetition eats tokens and invites contradiction. Note that a
timestamped block gives up per-shot control of duration and cut point, so use it for previs or a
social cutdown, not for the deliverable when the shot plan has named cut frames.

```text
Overall: [era, location, palette, stock, identity keywords, continuity rules].
[00:00-00:0X] Shot 1: [size/angle]. [one action]. Camera [move]. Sound: [source].
[00:0X-00:0Y] Shot 2: [size/angle]. [one action]. Camera [move]. Sound: [source].
[00:0Y-00:0Z] Shot 3: [size/angle]. [one action]. Camera [move]. Sound: [source].
```

Filled — `UTD_SC07` as a 12s three-shot previs block:

```text
Overall: third-floor landing of a 1937 Shanghai lilong apartment block, peeling dark-green
wainscot to waist height, cracked cream plaster, worn red floor tile, dark-stained door with a
chipped lower-left corner, a stairwell window at the head of the stairs opposite the door. One
bare filament bulb hanging over the stairhead, warm and hard, 5:1 lit side to shadow side; a thin
warm line spills from
the 4cm gap under the door. Low saturation, high contrast in the lower third; the envelope is the
only pure white. One character only: a 19-year-old Chinese man with a narrow jaw, deep-set eyes
under a low brow, a 2 cm scar through the left eyebrow, black hair clipped short and shaved high at
the neck, in a grey padded cotton jacket buttoned to the throat with one bone button missing at the
collar; wool cap pushed back, canvas satchel on the left shoulder. Same face and wardrobe in every
shot. No rendered text or numerals, no rubber soles, no wristwatch, the
door never opens.
[00:00-00:04] Shot 1: wide, high 15 degrees, 35mm. He climbs into frame, crosses the landing in
three steps and stops squared to the door 60cm out, envelope up at chest. Camera locked. Sound:
cloth shoes on tile, stairwell reverb.
[00:04-00:09] Shot 2: medium close-up, eye level, 50mm, bulb camera-left raking his face. He
raises his right hand, the knuckles stop 3cm short of the wood, he swallows, the hand lowers to
his thigh. Camera locked. Sound: a muffled radio behind the door, no intelligible words.
[00:09-00:12] Shot 3: extreme close-up, head-on, camera 15cm off the floor, 85mm, on the 4cm gap
and its warm light line; the bulb is out of frame here and the line is the only light. A shadow
crosses the line from inside, right to left, and the line is unbroken again. Camera locked. Sound:
a chair scrapes behind the door.
```

Note what moved into the shot lines: camera height in cm, and the key direction. Heights go in cm
so a reader never parses them as a second focal length, and key direction is camera-relative, so it
is false the moment a setup changes — it cannot live in the `Overall` block with the invariants.

## Template 5 — continuation / extend

For tools that extend a clip from its final frame. An extend continues one shot; it cannot cross a
cut, because the new footage inherits the old framing, and asking it to change setup produces a
morph rather than an edit. If the next thing on the timeline is a different size, angle or camera
height, that is a new generation, not an extension. The extend model also sees the tail of the
video and not your original prompt, so restate the invariants and start from the **observed** last
frame, not the one you intended.

```text
Continue from the final frame of the previous clip. [Subject] is [observed end state, described
as a still]. Now [the single next action, with speed and direction]. Camera [same behavior as
before, or explicitly: camera behavior changes to X]. Preserve [invariants]. Do not restart, do
not reset the pose, do not cut. Avoid [negatives].
```

Filled — `UTD_SC07_SH05`, extending its own first 3s. The EWS was generated up to the moment he
leaves frame; the extension is the hold that the shot exists for. Same setup, same lens, same
camera height — which is what makes it an extension and not a second shot:

```text
Continue from the final frame of the previous clip. The landing is empty; he has just dropped out
of frame at the bottom of the stairs. Over about one second a shadow crosses the warm line under
the door from inside, right to left, and the line is unbroken again. Camera stays locked exactly as
before; it does not pan down after him. Preserve the worn red tile, the door chip, the bulb
camera-left, and the grain. Do not restart, do not reset, do not cut. Avoid: the door opening, a
figure re-entering frame, the warm line going dark.
```

99 words, and an extension always runs longer than the shot it continues, because it pays for two
things a fresh generation does not: a description of what the observed last frame contains, and the
do-not-restart clause. Everything else should come out. The identity string, for one, is absent on
purpose — there is no person in this extension, so `ID_COURIER` would be dead tokens at best and an
invitation to put him back in frame at worst. Preserve what is still in the picture: here the room,
the light and the texture.

## Template 6 — dialogue shot

Only for models that generate speech. Label speakers by a visual attribute, never by a pronoun
and never by a name the model cannot see. Keep each line inside the clip's speakable budget —
roughly 2.5 English words or 4.5 Chinese characters per second, and the clip must also carry
pre-roll before the first word and a hold after the last. Rates and the clip-length formula are
owned by [sound and dialogue](../references/sound-and-dialogue.md); the sheet that records the
per-line decision is [sound plan template](sound-plan-template.md).

```text
[Camera]. [Shot size on the speaker]. [Speaker A: visual label, vocal register, volume]:
"[line]". [A's visible behavior while speaking — mouth, breath, gaze, hands].
[Then Speaker B: visual label, vocal register]: "[line]". [B's visible behavior].
Lip movement must match the spoken line. Preserve [invariants]. Avoid [negatives].
```

Filled — a shot from the following scene, where the letter is finally read aloud:

```text
Locked camera, medium close-up, eye level, 50mm, on a woman in her fifties seated at a table by a
window. Woman in a dark quilted jacket, grey hair pinned back, reading aloud from a single sheet,
voice low and even, no tremor: 「他没有敲门。」 Her eyes stay on the page, her jaw moves only as
far as the words require, her free hand flat on the table. No other voice is heard. Lip movement
must match the spoken line and stops the moment the line ends. Preserve the same face, the quilted
jacket, the window light from camera-left, the 1937 interior. Avoid: a second speaker, the camera
pushing in, subtitles burned into the frame, the paper changing shape.
```

Scene 7 itself has no speech at all — the book's sound direction allows only a muffled radio with
no intelligible words — which is why this example had to come from the scene after it. When a scene
is written that way, do not let a speech-capable model fill the silence. Any prompt that puts a
face in speaking range gets `no speech, no lip movement` in its negatives; the `SH02` prompt above
does not need it only because the shot never opens his mouth.

## Per-prompt self-check

Run on every prompt before you send it. Five questions, and the failure each one prevents.

- [ ] **One action.** Count the objectives, not the verbs. One gesture with a named stop is one
  action — rise, stop 3cm short, lower is a single aborted knock, and a swallow or a breath inside
  it is texture. Two objectives is two clips. (Guards F4.)
- [ ] **One camera move.** Count camera verbs. More than one, or a move plus "dynamic"? Cut to
  one, or lock it. Check it against the book's move budget. (Guards F6.)
- [ ] **Explicit end state.** Could you photograph the last sentence as a still? If not, rewrite
  it as a pose or a composition. (Guards F5.)
- [ ] **Invariants present.** The `ID_`, `LOCK_`, and `LIGHT_` strings, compressed but not
  reworded, plus the scene's checkable anchor. (Guards F1, F7, F8, F12.)
- [ ] **Negatives matched to real risk.** Name the condition in this shot that makes each one
  plausible — including the `NEG_BASE` classes, which you select from rather than paste whole.
  Cannot name it? Delete it. About six classes is the ceiling: every unearned negative dilutes
  the ones that matter, and a category ("no modern objects") dilutes without ever resolving into
  anything the model can withhold. (Guards F8, F9, F11.)

Two more that cost nothing: no adjective is doing work a noun could do better, and nothing in the
prompt merely re-describes the input image. Symptom-to-cause lookup for anything that comes back
wrong is in [failure modes](../references/failure-modes.md); scoring and gating are in
[qc checklist](qc-checklist.md).
