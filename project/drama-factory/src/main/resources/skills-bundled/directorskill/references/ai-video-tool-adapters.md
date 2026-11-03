# AI Video Tool Adapters

Load this file when you reach Step 9 (tool adapter selection) or Step 10 (AI video prompt construction), when the user names a video model or says "I'm generating in X", or when a clip has failed and the tool is part of the diagnosis.

**Staleness warning, before anything else.** Both capability matrices below and every per-tool block describe capability *classes as of writing*, not a live feature list. Vendors ship, rename, and remove controls constantly, and different surfaces of the same product expose different ones. Nothing on this page is a fact you can quote to a client — re-check it against current documentation, and read the panel in front of you before you promise a user a control. **Capability snapshot: 2026-08.** Anything older than about two release cycles is a prior, not a fact — confirm on the panel before you rely on it.

## The capability-first rule

Do not memorize tools. Tools rename features, ship new versions, and drop capabilities every few weeks. What is stable is the **set of control surfaces** a tool exposes. So:

1. Ask (or infer) which control surfaces the user's tool exposes: does it take a first frame? a last frame? a character reference? an existing clip as the driving input? does it have a camera slider, a motion-strength number, a negative-prompt field, native audio?
2. Map those surfaces to one of four **prompt shapes** below. The one surface that is not a prompt shape — video-to-video — is chosen here, at this step; see the section after the shapes.
3. Write the prompt in that shape's slot order. Move any instruction into a UI control if a UI control exists for it — a slider always beats an adjective.
4. Only then apply the tool-specific notes.

Corollary: never put the same instruction in two places. If you set a camera slider, delete the camera sentence. If the tool has a negative field, the positive prompt carries zero exclusions. Duplicated instructions produce doubled motion.

## The four prompt shapes

### S1 — Motion-only (image-to-video with a strong first frame)

Use when the still already fixes identity, costume, set, light, and framing. The text writes time, not appearance. This is the default shape for character work.

Slot order:

1. Camera behavior (or "the camera does not move")
2. Subject start state, visible in the frame
3. One primary action, with pace and direction
4. One environmental motion
5. End state — a nameable pose or composition
6. Continuity lock — a stability instruction, never a description
7. Exclusions (only if the tool has no negative field)

Rule: describe change, not appearance. "She wears a red coat" is a description and re-renders the coat; "the coat does not change" is a lock and holds it. Anything the still already fixes gets a lock clause at most.

### S2 — Full description (text-to-video)

Use when there is no input image. The prompt carries the entire frame.

Slot order:

1. Format register (aspect, and one grounded look reference such as "shot on 35mm anamorphic", not "cinematic")
2. Subject with specific, repeatable identity details
3. Location, time of day, weather, atmosphere
4. Primary action
5. Shot size, angle, focal length
6. Camera move (one)
7. Lighting — name the source, not the mood
8. Audio, if the tool generates it
9. Constraints

Rule: slots 5-7 are where mood words creep in. Write geometry and hardware there instead. See [cinematic-language.md](cinematic-language.md) for the vocabulary and [lighting-and-color.md](lighting-and-color.md) for source-naming.

### S3 — Keyframe pair (first + last frame)

Use for controlled transformation, a guaranteed endpoint, or a designed transition between two compositions.

Slot order:

1. Bridge statement: "Starting from the first image and ending on the second image…"
2. The single transformation that connects them (only one: pose, or camera position, or light state)
3. The camera path between the two framings
4. Timing and easing (steady / decelerating into the last frame)
5. What must not change across the interpolation
6. Exclusions (only if the tool has no negative field)

The emittable skeleton for these six slots is the S3 block in SKILL.md Step 10 and Template 2 in [../assets/video-prompt-template.md](../assets/video-prompt-template.md); both fill exactly this list in this order, so a prompt written from either one can be audited against the slots here.

Rule: the model interpolates, it does not reason. If the two frames differ in more than one of {subject pose, camera position, light state}, it will morph rather than move. Too far apart? Build a middle keyframe and make it two clips.

### S4 — Multi-shot timestamped

Use only on tools that respect timestamped segments. Otherwise you get one shot that ignores your structure, or three shots that look like three different films.

Slot order:

1. Global block: style, aspect, palette, per-character identity locks, continuity rules, cut rule
2. Per segment `[mm:ss-mm:ss]`: shot size + angle | action | camera | light or sound cue
3. Global exclusions

Rule: every identity, palette, and lighting fact lives in the global block. Per-segment lines carry action, camera, and at most one light or sound cue — never an identity, wardrobe, palette, or lighting restatement, and never an emotion word. The moment you re-describe a character inside segment 2, the model recasts them.

### The same scene in all four shapes

One beat, written four ways, so you can see what each shape carries and what it drops: *a person stands at a closed apartment door holding something they intend to give away, hesitates, and leaves without knocking.*

S1, motion-only from a keyframe that already shows her at the door (score 3):

```text
The camera is locked. She stands square to the closed door, the folded coat held against her chest
in both hands. She lowers the coat to waist height, slowly, then turns her head left, away from the
door. The overhead strip light flickers once. End with her chin turned off-frame left, the coat
still in both hands. Her face, her clothes, the door, and the corridor light do not change.
```

S2, text-to-video with no input image (score 3):

```text
16:9, shot on 35mm spherical, mild halation on the highlights. A woman in her thirties, dark hair
pinned back, charcoal wool coat, holding a folded grey coat against her chest. Narrow apartment
corridor, late evening, brown carpet, a numbered door. She lowers the folded coat to waist height
and does not knock. Medium shot, eye level, 50mm. The camera is locked. Light is one overhead
fluorescent strip behind her plus a warm gap under the door. Audio: corridor hum, one distant lift
chime, no music. One continuous shot, no cuts, the same face throughout.
```

S3, keyframe pair — frame 1 square to the door, frame 2 three-quarters turned away (score 2):

```text
Starting from the first image and ending on the second image. The only change is her body
orientation: she rotates from square-on to the door to a three-quarter turn away from it. The
camera holds its position and the framing is identical in both frames. Steady, decelerating into
the last frame. Face, hair, both coats, door number, and corridor light are identical throughout.
```

S4, multi-shot timestamped (each segment scored separately, ≤3 each):

```text
Overall: late evening, narrow apartment corridor, brown carpet, one overhead fluorescent strip.
Woman, mid-thirties, dark hair pinned back, charcoal wool coat, carrying a folded grey coat. Same
face, same coats, same corridor light in every segment. Hard cuts only, no dissolves.
[00:00-00:03] Medium, eye level. She stops at the door and lifts the folded coat slightly. Camera locked.
[00:03-00:06] Close on her free hand rising toward the door, then stopping short. Camera locked.
[00:06-00:10] Wide from down the corridor. She turns and walks away from camera. Slow push in.
```

Note what changes between them: S1 spends nothing on appearance because the still holds it; S2 spends more than half its words there; S3 buys a guaranteed endpoint by permitting exactly one change; S4 buys three shots by giving up per-shot control. Pick the cheapest shape your tool supports.

## Video-to-video: the fifth control surface

Video-to-video takes an existing clip as the driving input instead of a still or a sentence. It is chosen at the **adapter** step, not the prompt-shape step: there is no S5. You still write whichever of S1–S4 the shot wanted, and add one line naming what is held from the source clip and what is replaced.

Two surfaces travel under the one name, and a family often exposes one and not the other:

- **Restyle / relight / regrade / reframe** — the source clip supplies motion, blocking, and timing; the model replaces the look. Reach for it when the take is right and the picture is wrong.
- **Performance transfer** — a driving clip supplies the motion (a face's expression, a body's movement) and a separate reference supplies the subject. Reach for it when the performance is right and the person is wrong.

What it cannot do:

- It cannot invent a new angle. The camera stays where it was, so a restyled wide is still a wide; a shot you wish were closer is a new generation, not a pass.
- It inherits the take's blocking and timing exactly, including the beat that lands half a second late. If the performance is wrong, the source clip is wrong and no restyle reaches it.
- Identity risk moves from generation to conform. The face is no longer being invented, it is being re-rendered frame by frame, so drift arrives as flicker and boil across the take rather than as one wrong face — and it arrives on a clip you already approved, which is what makes it easy to sign off. Check the identity landmark on the first, middle, and last frames of the output, never on a thumbnail.

When a v2v pass is cheaper than rebuilding the keyframe, and when it is not, is repair economics — owned by the cost ladder in [failure-modes.md](failure-modes.md). Read it there rather than re-deriving it from the per-tool budgets on this page.

Worked instance: a 5s clip is approved for performance and comes back beautified — blacks lifted to grey, wet pavement nobody wrote, every source pulled to one white balance. The keyframe is right and the take is right, so rebuilding either throws away work that already passed. Restyle the delivered clip instead, carrying the positive facts from *Night exteriors get beautified* below, hold face, wardrobe, and framing, and check the landmark on the first, middle, and last frames before you conform it.

## Control-surface matrix

This matrix describes **capability classes as of writing, not a live feature list.** Vendors ship, rename, and remove features constantly, and different surfaces of the same product (web UI, app, API) expose different controls. Verify against current documentation before promising a user a specific control — no cell here is a fact you can quote to a client. Legend: `yes` / `part` (exists but limited, or only on some surfaces) / `no` (not exposed on the surfaces we looked at — treat as "check", not as "impossible") / `varies` (differs by surface, tier, or release often enough that only the docs can answer). Length classes are deliberately coarse, because published limits move constantly: `short` is a few seconds, `std` is the common single-generation length most tools default to, `graph` means you set it yourself as frame count over fps. Read the class as a planning bucket, never as a ceiling you can quote.

| Capability | Runway | Veo | Kling 可灵 | Luma | 即梦 / Seedance | 万相 Wanxiang |
|---|---|---|---|---|---|---|
| Text-to-video | yes | yes | yes | yes | yes | yes |
| Image-to-video, first frame | yes | yes | yes | yes | yes | yes |
| Last-frame slot | part | part | yes | yes | yes | yes |
| Keyframe interpolation, 3+ frames | no | no | no | part | part | part |
| Video-to-video, existing clip as driver | yes | varies | part | varies | part | part |
| Character / subject reference | yes | part | part | yes | yes | part |
| Style reference | part | part | part | yes | yes | part |
| Explicit camera-control UI | yes | part | yes | part | part | part |
| Numeric motion strength | yes | no | part | no | yes | part |
| Motion brush / region control | yes | no | yes | no | no | no |
| Native audio | part | yes | part | part | part | part |
| Dialogue + lip-sync | part | yes | yes | no | part | part |
| Single-generation length class | std | std | std | short-std | short-std | std |
| Extend / continue | yes | part | yes | yes | part | part |
| Loop | part | no | no | yes | no | no |
| Multi-shot timestamps | no | part | part | no | part | yes |
| Seed control | yes | part | part | part | yes | yes |
| Negative-prompt field | varies | part | yes | varies | part | yes |
| Aspect-ratio control | yes | yes | yes | yes | yes | yes |

Same legend, same caveat — these are classes as of writing, to be re-checked against current documentation:

| Capability | Sora-class | Hailuo / MiniMax | Pika | Vidu | Midjourney Video | OSS / ComfyUI |
|---|---|---|---|---|---|---|
| Text-to-video | yes | yes | yes | yes | varies | yes |
| Image-to-video, first frame | part | yes | yes | yes | yes | yes |
| Last-frame slot | varies | part | part | yes | no | yes |
| Keyframe interpolation, 3+ frames | no | no | no | part | no | yes |
| Video-to-video, existing clip as driver | part | part | part | varies | no | yes |
| Character / subject reference | part | yes | part | yes | part | yes |
| Style reference | part | part | part | part | part | yes |
| Explicit camera-control UI | no | part | yes | part | no | part |
| Numeric motion strength | no | no | yes | part | part | yes |
| Motion brush / region control | no | no | part | no | no | part |
| Native audio | yes | part | part | part | varies | part |
| Dialogue + lip-sync | yes | part | part | part | varies | part |
| Single-generation length class | std | std | short | short-std | short | graph |
| Extend / continue | part | part | yes | part | yes | yes |
| Loop | part | no | part | no | part | yes |
| Multi-shot timestamps | part | no | no | no | no | no |
| Seed control | varies | part | yes | part | part | yes |
| Negative-prompt field | varies | part | yes | part | part | yes |
| Aspect-ratio control | yes | part | yes | part | part | yes |

If the user's tool is not in this matrix, ask three questions and route from the answers: does it take an input image? does it have a last-frame slot? does it have a negative field or a motion number? That is enough to pick a shape.

## Per-tool adapters

Each block has the same nine parts: Best for, Surfaces to exploit, Language, Aspect, Priority, Template, Rules, Typical failure and fix, Budget. The last is a motion-budget **ceiling** — a number on the shared scoring model below, read after the duration multiplier and the modifiers have been applied. Duration is already priced there, so never discount for it a second time in a per-tool rule.

Three rules run across every block, so they are stated once here instead of twelve times:

- Vendor names. Each heading names a capability **class**; the name is shorthand for the class, not a promise that the product is on sale. Products get renamed, folded into a suite, moved behind a different tier, or withdrawn between snapshots. Confirm the product is still offered on the surface the user actually has before you plan a shoot around a block — and if it is gone, the block still routes: find whichever product now exposes that set of surfaces and read the block against it.
- Negative field. Where the surface exposes one, put every exclusion in it and keep the positive prompt free of the word "no". Where no negative field is exposed, convert every exclusion into a positive fact about the frame — "the platform behind her is empty", not "no extra people". Each block's Rules line says which case that family is usually in. Where the matrix reads `part` or `varies` the answer differs by surface and tier, so look at the panel in front of you; if you cannot confirm a field, write the prompt as though there is none, because that version is safe on both.
- Aspect. On image-to-video the input still's ratio governs the output whatever the tool's aspect control says, so the aspect decision is really made at Step 8 and the video tool inherits it — see [image-model-adapters.md](image-model-adapters.md). Each block's Aspect line therefore covers the text-to-video path and names ratio *classes* (landscape / portrait / square), never a preset list, because preset lists change.

### Runway family

- Best for — single-shot image-to-video off a still you already like; motion confined to a region; camera moves set numerically rather than described.
- Surfaces to exploit — motion brush (paint only what moves), camera-control sliders, reference images for identity, seed.
- Language — English, in the positive prompt and in any negative field; the training and the documentation are English-first, and craft terms are more stable in English here than anywhere.
- Aspect — landscape, portrait, and square classes on the text path. On image-to-video the input still's ratio governs, so compose the delivery ratio in the keyframe.
- Priority — subject motion, environmental motion, camera (only if not set by slider), pace, identity lock.
- Template — S1, one sentence per moving element, nothing else.
- Rules — if a camera slider is set, remove every camera word from the text or you get two superimposed moves. The negative field is `varies` here, so unless you can see one on the surface in front of you, convert every exclusion into a positive fact about the frame: "the street behind her stays empty" beats "no extra people". Brush the smallest region that tells the story. Turning a subject around is the most reliable way to get mush (F3 in [failure-modes.md](failure-modes.md)) — a brush does not save a rotation, so restage the turn as two clips or start from a still already part-way through it.
- Typical failure and fix — the whole frame drifts when you only wanted a hand to move. Fix: brush the hand alone, zero the camera slider, delete all camera language.
- Budget — ceiling 5. One brushed region with the camera slider at zero is the cheapest configuration on this page; spend the savings on length, not on a second moving element.

### Veo family

- Best for — picture and sound in one pass; dialogue-carrying shots; prompts written as an actual shot description.
- Surfaces to exploit — native audio, prompt-level timestamps, negative prompt where the API exposes it, image input, reference "ingredients" where the surface offers them.
- Language — English throughout, including the audio sentence and any negative field.
- Aspect — landscape and portrait classes; generate native rather than cropping a landscape result, because this family composes headroom and lead room for the ratio it was told.
- Priority — shot description (size / angle / lens), subject action, camera, light source, audio, constraints.
- Template — S2 with an explicit audio sentence; S4 for multi-shot.
- Rules — write audio as its own sentence naming sources, or expect a score composed under your scene: "Audio: rain on a tin awning, one distant dog, no music." Say "no music" whenever you intend to score in the edit — that is the one licensed negation in a positive prompt on this family, because it lands as an audio instruction rather than as a visual noun. The negative field is `part`: it exists on some API surfaces and not in most consumer ones, so unless you can confirm it, convert every visual exclusion into a positive fact about the frame. One speaker per clip if you need clean lip-sync; see [sound-and-dialogue.md](sound-and-dialogue.md).
- Typical failure and fix — an unrequested orchestral bed plus a camera move you never asked for. Fix: add "no music, no score" and state stillness positively — "the camera is locked and does not move."
- Budget — ceiling 6, but a clip carrying spoken dialogue spends 2 of it before you stage anything, so plan the picture against 4.

### Kling 可灵 family

- Best for — physical action with weight, body mechanics, multi-stage beats, end-frame-controlled transformation.
- Surfaces to exploit — where the UI exposes them: 首尾帧 (first/last frame), 运镜 (camera presets), 运动笔刷 (motion brush), the negative-prompt field, 对口型 (lip-sync) as a second pass, 延长 (extend).
- Language — Chinese, the whole prompt including craft terms (固定镜头, 中景, 逆光硬光), and Chinese in the negative field too. This is a Chinese-UI family; an English prompt is a translation the model has to undo first. Keep an English mirror in the shot plan and mark which one was sent.
- Aspect — landscape, portrait, and square classes on the text path. The 首尾帧 and image-to-video paths inherit the stills you supply, so set 9:16 in the keyframe rather than in the video panel, and never feed a pair whose two frames are different ratios.
- Priority — action progression in order, body mechanics, camera reaction to the motion, end pose, identity lock.
- Template — S1 or S3, with the action written as ordered stages.
- Rules — the negative field is real on this family: put every exclusion there and keep the positive prompt clean. Where a surface or tier does not expose it, convert every exclusion into a positive fact about the frame. Generate silent, then run lip-sync as a separate pass; asking for speech and performance in one generation tends to cost you both. A camera preset plus camera words is a double move — pick one. A body rotation is the most reliable way to get mush (F3 in [failure-modes.md](failure-modes.md)); this family holds weight better than most, but a full turn-around still wants a first/last pair or two clips rather than one prompt.
- Typical failure and fix — the action completes in the first second and the subject then idles or loops. Fix: write three ordered stages with a named end pose ("…ends with his weight fully on the back foot, head still turned"), and shorten the clip.
- Budget — ceiling 6. Because the multiplier already prices length, staged action at length busts the ceiling on arithmetic alone; extend a short clean take rather than asking for one long take.

### Luma Dream Machine family

- Best for — keyframe-driven transitions, true loops, character-reference binding, chained extends.
- Surfaces to exploit — start and end keyframe slots, character reference binding (an `@`-style tag typed into the prompt, where the UI exposes it), visual style reference, loop toggle, extend.
- Language — English, prompt and reference tags alike.
- Aspect — landscape, portrait, and square classes on the text path; keyframe-driven and loop work inherits the frames you supply, and a first/last pair at two different ratios is a guaranteed morph.
- Priority — character reference, one action, camera tag, environment, endpoint.
- Template — S3.
- Rules — the negative field is `varies` here, so assume there is none unless you can see one and write every exclusion as a positive fact about the frame. Keep both keyframes in one lens family and one light state; what comes back reads as an interpolation between the two frames rather than a re-lit scene, so a light change across the pair usually returns as a cross-fade. A loop only closes if the last frame genuinely matches the first, so design a returning pose. Each extend inherits the previous clip's drift — re-anchor with a fresh keyframe every two or three extends.
- Typical failure and fix — the face morphs across the interpolation. Fix: shrink the gap between keyframes (promote the midpoint to its own clip) and keep head size within roughly 20% between the two frames.
- Budget — ceiling 5, and each extend is scored from scratch against the same 5, so never stack a camera move onto an extend.

### 即梦 Jimeng / Dreamina / Seedance family

- Best for — Chinese-language ideation, first/last-frame work, vertical short-form, fast iteration, period-Chinese subject matter.
- Surfaces to exploit, where the UI exposes them — 首尾帧 (first/last frame), 运动幅度 (motion amplitude), 运镜 (camera presets), 种子 (seed), reference images and 角色参考 (character reference), 负向提示 (negative prompt) on some surfaces, multi-shot on the Seedance side. These surfaces are renamed and reshuffled often; read the panel in front of you rather than this list.
- Language — Chinese, the whole prompt including craft terms (固定镜头, 机位齐腰高度, 逆光), and Chinese in the negative field where one is exposed. Culturally specific nouns are the main reason: 旗袍, 弄堂, 蓑衣 resolve here and their English paraphrases do not.
- Aspect — vertical is first-class on this family: landscape, portrait, and square classes on the text path. The 首尾帧 and image-to-video paths inherit the stills, so a native 9:16 short is composed at Step 8, not chosen here.
- Priority — 镜头 (camera), 主体起始状态 (subject start state), one action, environmental detail, end state, consistency lock.
- Templates — both language variants below.
- Rules — 负向提示 is `part` on this family: it appears on some surfaces and tiers and not on others, and the whole negative strategy inverts on that one fact, so check the panel before you write. **Where the field is exposed, put every exclusion in it as a plain comma-separated list and keep the positive prompt free of 不 and 没有** — the one exception is a withheld action that *is* the beat, as 不敲门 (she does not knock) is in the example below. **Where no negative field is exposed, convert every exclusion into a positive fact about the frame**: 门始终关着 (the door stays closed) rather than 不要开门, 走廊里只有她一个人 (she is the only person in the corridor) rather than 不要出现别人. A negation inside the positive prompt is unreliable here and often summons the noun it names. Concise Chinese generally outperforms verbose English on the Chinese UI; for the working length, see the two windows below. On 运动幅度, the number of steps and the default both change between builds, so do not plan against a specific value: whatever scale your build exposes, set it to the lowest setting that still produces the action, and treat the default as too high for any shot where a face fills more than a third of the frame. Same for length — pick the shortest offered option that fits the action rather than assuming 3s is on the menu. Once a take is close, lock the seed and change exactly one clause per retry.
- Typical failure and fix — the face shifts subtly at high motion amplitude. Fix: lower the amplitude to the lowest setting that still moves, pick the shortest duration option that fits the action, restate 保持同一张脸 (keep the same face).
- Budget — ceiling 5 with a legible face in frame, 8 without one.

Prompt length, as two numbers rather than one. Count every character including punctuation — that is what a character counter in the panel shows you — and treat both as budgets for legibility, not as documented input limits:

- **80–130 characters** when the surface exposes 负向提示 and the exclusions live there. The prompt then carries slots 1-6 of S1 only.
- **130–180 characters** when exclusions must be written inline as slot 7. The extra 50 characters are the exclusion clause and nothing else; if you are over 180, you are re-describing something the input still already proves.

The 中文变体 in [../assets/video-prompt-template.md](../assets/video-prompt-template.md) is 157 characters and carries its exclusions inline, which puts it in the second band; the example below is 91 and carries none, which puts it in the first.

Filled on the door scene, 中文, 91 characters counting punctuation (79 of them Han) — inside the first window above, with exclusions assumed to be living in the negative field (score 3):

```text
固定镜头。她正面对着关着的房门，双手抱着叠好的外套；随后缓慢放低到腰间，
头向左转开，不敲门。头顶灯管闪了一下。结尾停在下巴转向画左、外套仍在手中。
保持同一张脸、同一套衣服、同一光线。
```

The same prompt in English, for the shot plan and for English-first surfaces:

```text
The camera is locked. She stands square to the closed door, the folded coat held in both hands,
then lowers it slowly to waist height and turns her head left, away from the door, without
knocking. The overhead strip light flickers once. End with her chin turned off-frame left and the
coat still in her hands. Same face, same clothes, same light.
```

### 万相 Wanxiang family

- Best for — text-to-video with aesthetic controls, structured multi-shot descriptions, Chinese-language subject matter, and a working negative field.
- Surfaces to exploit, where the surface you are on exposes them — t2v and i2v, 首尾帧, negative prompt, seed, style/aesthetic controls, overall-plus-numbered-shots multi-shot input.
- Language — Chinese, the whole prompt including craft terms, and Chinese in the negative field. The multi-shot 整体描述 block is Chinese too; mixing an English identity lock into a Chinese overall block is the fastest way to have it ignored.
- Aspect — landscape and portrait classes on the text path; image-to-video and 首尾帧 inherit the stills.
- Priority — text-to-video: subject, scene, motion, aesthetic control, style. Image-to-video: motion and camera only.
- Templates — S2 for t2v; S4 for multi-shot.
- Rules — the negative field is real on this family: every exclusion goes there and the positive prompt stays clean. For image-to-video, strip every adjective describing something the image already shows; contradicting adjectives make it re-render the subject. In multi-shot, identity and palette locks belong in the overall block only, and so does the negative list — a per-segment exclusion is read as a segment topic.
- Typical failure and fix — shots 2 and 3 look like a different film. Fix: move identity, palette, and light into the overall block; reduce each shot line to action plus camera.
- Budget — ceiling 6 for a single shot. In a multi-shot prompt score each segment on its own against a ceiling of 3, because every segment is drawing on one shared generation pass.

Filled on the door scene. Note that every identity and lighting fact sits in 整体描述 and none of it repeats in the numbered shots:

```text
整体描述：夜晚，狭窄的公寓走廊，棕色地毯，头顶一支日光灯管。三十多岁女性，深色头发挽起，
炭灰色羊毛大衣，手里抱着一件叠好的灰外套。全片保持同一张脸、同一套衣服、同一走廊光线。只用硬切。
镜头 1 [0-3s]：中景 平视 她在门前停下，把叠好的外套微微抬起 固定镜头。
镜头 2 [3-6s]：特写 她空着的手抬向门板，又停住 固定镜头。
镜头 3 [6-10s]：远景 她转身背对镜头走开 缓慢推近。
```

English mirror for the shot plan (send the 中文 version to the tool):

```text
Overall: night, narrow apartment corridor, brown carpet, one overhead fluorescent strip. Woman in
her thirties, dark hair pinned up, charcoal wool coat, carrying a folded grey coat. Same face, same
clothes, same corridor light throughout. Hard cuts only.
Shot 1 [0-3s]: medium, eye level, she stops at the door and lifts the folded coat slightly, camera locked.
Shot 2 [3-6s]: close-up, her free hand rises toward the door and stops, camera locked.
Shot 3 [6-10s]: wide, she turns and walks away from camera, slow push in.
```

### Sora-class

- Best for — text-to-video with native sound and dense environmental detail, and concept exploration where you can tolerate the model directing itself.
- Surfaces to exploit — the prompt, image or cameo reference where exposed, aspect ratio, remix. Very few numeric knobs.
- Language — English, prompt and audio sentence alike.
- Aspect — landscape, portrait, and square classes, usually chosen before generation rather than exposed as a field you can revise; portrait is well supported, so generate native for vertical rather than cropping.
- Priority — single-shot instruction, shot description, action, camera, sound, what stays fixed.
- Template — S2, with the single-shot instruction in the first sentence.
- Rules — the negative field is `varies` and is absent on most consumer surfaces, so write every exclusion as a positive fact about the frame; this family in particular reads a bare negation as a topic and renders it. The behaviour to plan around, as of the snapshot date at the top of this file, is a tendency to cut to new angles unbidden; a release can retire it, so before you spend the single-shot instruction across a whole shot list, generate one clip without it and see whether the model still cuts. While it does, if you need one continuous take, say so first: "One continuous shot. No cuts, no angle changes." Write the soundscape explicitly or it invents dialogue and music. With little or no seed control, reproducibility comes from prompt precision, not from re-rolling.
- Typical failure and fix — your one shot comes back as a three-shot mini-scene. Fix: single-shot instruction up front, exactly one action, and a duration sized to that one action.
- Budget — ceiling 5 if you want single-shot control. Whatever you leave unspent, the model spends on cuts you did not ask for.

### Hailuo / MiniMax family

- Best for — subject consistency from a single portrait; action that resolves in one beat; bracketed camera instructions where the director-style variant supports them.
- Surfaces to exploit — subject reference from one clean portrait, bracketed camera commands where available, image-to-video.
- Language — match the surface you are on: the domestic UI wants Chinese including craft terms, the international one wants English. Do not mix — a Chinese subject description inside an English prompt on the international surface binds weakly. Bracketed camera commands stay in whichever language the documentation for that surface writes them in.
- Aspect — often fixed by model and tier rather than chosen, so treat it as `part`: on image-to-video the input still decides, which is the reliable lever, and for a native vertical short that is the one you use.
- Priority — subject reference, camera bracket, action, environment, end state.
- Template — bracketed camera commands inline, at the sentence they govern.
- Rules — the negative field is `part`: unless you can see one on your surface, write every exclusion as a positive fact about the frame. Where bracketed commands are supported they tend to land more reliably than prose camera description; use at most two per clip. The subject reference wants a frontal portrait, even light, no occlusion, no extreme expression.
- Typical failure and fix — the face over-performs, cycling through exaggerated expressions. Fix: name an expression endpoint instead of an emotion — "ends on a small held half-smile", not "she looks happy".
- Budget — ceiling 5; two bracketed camera commands already spend 1-2 of it.

```text
[Push in] She stands at the counter, hands flat on the wood, and slowly raises her eyes to the door.
[Static shot] She holds the look. Steam drifts from the cup beside her. Ends with her jaw set.
```

### Pika family

- Best for — very short clips built on a single action, parameterized control, effect-driven shots, cheap iteration.
- Surfaces to exploit — parameter flags for motion strength, negative prompt, seed, aspect, camera; region modification; extend.
- Language — English, prose and flags alike.
- Aspect — an explicit aspect flag is exposed on the text path; set it rather than cropping. Image-to-video inherits the still.
- Priority — subject and action, camera parameter, motion strength, negatives.
- Template — a short prose sentence followed by flags; keep prose under about 25 words.
- Rules — the negative flag is real here: every exclusion goes in it and the 25-word prose sentence carries none. Parameters beat adjectives every time: set motion numerically rather than writing "subtle motion". Use the lowest motion setting for anything with a face. Extends compound artifacts, so extend at most once from a clean take.
- Typical failure and fix — the clip is three seconds and the action never completes. Fix: choose an action that genuinely fits three seconds — a look, a turn, a reach — and put the follow-through in the extend.
- Budget — ceiling 4.

### Vidu family

- Best for — binding several references at once (character, prop, and location from separate images) into one shot.
- Surfaces to exploit — multi-image reference binding, start and end frames, t2v and i2v.
- Language — the UI ships in both; write in the language of the surface you are on, and keep the reference-role labels in that same language so the binding phrase and the reference list match.
- Aspect — landscape and portrait classes on the text path; reference-bound and first/last work inherits the frames you supply, so bring every bound reference in at the delivery ratio.
- Priority — reference roles, the interaction between them, camera, end state.
- Template — S1 or S3 with each reference named by role.
- Rules — the negative field is `part`: where it is not exposed, convert every exclusion into a positive fact about the frame. Label references explicitly in the prompt ("the woman from reference 1 lifts the lantern from reference 2"). Background references tend to bind more weakly than subject references, so describe the location in words as well. Give bound characters clearly different hair, silhouette, and costume value.
- Typical failure and fix — two bound characters converge on one face. Fix: increase visual distinctness between the references and separate the characters in depth in the described blocking; see [blocking-and-staging.md](blocking-and-staging.md).
- Budget — ceiling 5. The global `+1 per bound reference beyond the first` modifier already prices the binding, so do not also lower the ceiling; three bound references leave almost nothing for camera.

### Midjourney Video

- Best for — animating a still whose look you want preserved above everything else.
- Surfaces to exploit — image-first animation, a low/high motion setting rather than a numeric one, extend.
- Language — English.
- Aspect — inherited from the still, and only from the still: this family has no meaningful aspect decision of its own, so the delivery ratio is composed at Step 8 and the animation pass follows it.
- Priority — what moves, how much, nothing else.
- Template — S1 with slots 3 and 4 only: one subject motion, one environmental motion. Leave the camera slot empty rather than filling it with words the tool will not honour.
- Rules — the negative field is `part` on the animation pass and should be assumed inert: put the exclusion in the still instead, where the image model does have one, and write the video prompt as positive facts only. Treat it as a look-preserver, not a director. Low motion for any shot containing a face; high motion only for environment, weather, or abstract texture. Prose camera direction tends to land weakly here, so do not plan camera-led shots on this surface; if the panel has grown a camera control since the snapshot date, that is the first claim to retest — one clip — before you route a camera-led shot back to it. Assume you are budgeting a full sound pass in the edit, and check the current documentation before promising anyone a native audio track.
- Typical failure and fix — you ask for a dolly-in and get a generic slow drift. Fix: bake the camera position into the still (generate the framing you want) and use video only for micro-motion; or move that shot to a tool with camera control.
- Budget — ceiling 3.

### Open-source / ComfyUI class (Wan, HunyuanVideo, LTX)

- Best for — repeatability, exact seeds, LoRA-locked identity, first-last-frame nodes, and any control you are willing to build yourself.
- Surfaces to exploit — seed, CFG, sampler and steps, the flow-shift control where the model exposes one, LoRA strength, first-last-frame nodes, pose/depth/edge conditioning, masks, frame count and fps.
- Language — decided by the text encoder the graph loads, not by you: English for most, while Chinese-native bases (Wan, Hunyuan) take Chinese directly and lose less on culturally specific nouns. Check which encoder is in the graph before assuming, and never switch language mid-comparison.
- Aspect — you set width and height as numbers, so any ratio you want; stay near the base model's training resolutions, because composition degrades before motion does when you stray far from them.
- Priority — the conditioning graph first, the prompt second. Prompt wording matters less here than anywhere else on this page.
- Template — S1 or S3 text, plus a recorded graph.
- Rules — negative conditioning is real and separately weighted here, so every exclusion goes in the negative node and the positive prompt carries none. Fix the seed and change one node per iteration; log the graph hash alongside the shot ID in the [continuity bible](continuity-bible.md). Duration is `frame_count / fps` — decide it as a number, not a wish. Pose or depth conditioning buys back motion budget that prompt words cannot.
- Typical failure and fix — frame 1 is excellent and quality degrades steadily past the midpoint. Fix: fewer frames per pass and chain them, or lower the motion conditioning strength.
- Budget — ceiling 6, raised to roughly 8 when motion is driven by pose or depth conditioning instead of by words: the conditioning supplies geometry the model would otherwise have to invent, which is what the budget was paying for.

## Cross-tool behaviours to plan around

These are model-class behaviours, not one vendor's bug. They appear on every surface in the matrices above, so they are not repeated in the per-tool blocks — check them whenever the shot matches, whatever tool the user named.

### Night exteriors get beautified

Ask for a night exterior and most models return a nicer night than the one you asked for: shadows lifted until the blacks read grey, every source pulled toward one white balance, wet reflective pavement nobody wrote, fog or haze, and volumetric beams off every practical. It is the commonest reason a night plan comes back looking like a car commercial. It happens in the still and again in the clip, so suppress it in both the keyframe prompt and the video prompt or the video model will simply re-beautify a keyframe you approved.

Counter it positively, in the prompt itself:

- Name every source separately with its own colour and its own side — "sodium vapour from camera-left, cold mercury from camera-right, mixed colour temperatures, never balanced to each other". Unified grade is what the model defaults to when you name one light or none.
- State the ground: "dry pavement", "matte asphalt, no standing water", if the street is dry. Wet street is the single most-added element.
- Ask for noise: "deep black shadows with visible grain in them". Grain is what stops a model reading crushed blacks as an error to fix and lifting them.
- Give the frame its own darkness budget — say which part of the frame is allowed to be unreadable, or the model will make all of it readable.

Where a negative field is exposed, six targeted items suppress most of it: `fog`, `volumetric light beams`, `lens flare`, `wet reflective pavement`, `unified colour grade`, `warm cozy lighting`. Take only the ones this frame could actually produce — a bloated field dilutes each term ([prompt-lexicon.md](prompt-lexicon.md) owns the selection rule). Where no negative field is exposed, do not translate that list into "no fog, no flare" in the positive prompt; write the positive facts above instead, because naming the noun is how you get it.

Night-register style lenses carry their own additions to this set — see the `negative_prompt_adds` block in [19_michael_mann.md](director_styles/19_michael_mann.md), which extends this section rather than replacing it.

## The motion budget

Every clip has one finite budget of motion. Subject motion, camera motion, environmental motion, and duration all draw on the same pool. Exceed it and the model spends coherence instead: faces warp, hands multiply, costumes change, geometry slides. It is the single most useful predictor of whether a prompt will fail.

Score a clip before you generate it.

| Component | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Subject motion | none | breath, blink, head turn | walk in frame, reach, sit/stand | run, fall, fight, full turn |
| Camera motion | locked | slow single axis (push, pan ≤15°) | dolly with reframe, handheld follow | orbit, crane, whip, multi-axis |
| Environment motion | still | one element (rain, hair, curtain) | two elements or a small crowd | fire + smoke + crowd + water |

Apply it in this order, and only this order, or two scores stop being comparable:

1. Sum the three component rows, 0-3 each. Charge every motion once — a scattering crowd is the environment row, not also three extra people.
2. Multiply by duration: `×1.0` for ≤5s, `×1.3` for 6-10s, `×1.6` for >10s.
3. Then add the modifiers: `+1` per additional person with an independent action, `+1` if a face occupies more than a third of the frame (charged once, however many faces), `+1` if hands perform fine manipulation, `+1` per bound reference beyond the first.

Ceilings on the final number: **4** for close character work, **6** for medium and wide shots with people, **8** for environment, product, or anything with no legible face. Where an adapter block above states a per-tool ceiling, that one wins.

Reconciling with the style lenses: the `motion_budget` field in a director style module's `风格参数` block is the **camera row of this table only**, not the whole score — `none` = 0, `low` = 1, `medium` = 2, `high` = 3. A high-motion lens has therefore already spent 3 on camera before you stage anything, and must buy it back from the subject or environment rows.

### Worked example — over budget and rebalanced

Over budget:

```text
A woman in a red qipao runs down a rainy alley as paper lanterns swing overhead and a crowd
scatters behind her; the camera orbits her and cranes up to reveal the whole street. 10 seconds.
```

Score: subject 3 (run) + camera 3 (orbit plus crane) + environment 3 (rain, swinging lanterns, scattering crowd) = 9; ×1.3 for 10s = 11.7; `+1` because the orbit holds her face large in frame through the first half = **12.7** against a ceiling of 6. The scattering crowd is already paid for in the environment row and is not charged a second time as extra people. It will warp, and the fix is not a better adjective, it is two clips.

Rebalanced as clip A — 5s, subject 2 + camera 0 + environment 2 = **4** against a ceiling of 6, with no face modifier at this size:

```text
Medium shot, the camera is locked. She stops at the mouth of the alley, chest heaving, and turns
her head left to look back the way she came. Rain falls steadily; one paper lantern swings above
her. End with her eyes fixed off-frame left, breath still ragged. Same face, same red qipao,
same wet alley, same lantern light.
```

Rebalanced as clip B — 5s, subject 3 + camera 1 + environment 1 = **5** against a ceiling of 8, because she runs away from camera and no face stays legible:

```text
Wide shot, the camera pushes in slowly along one axis. She runs away from camera down the alley
into the depth of the frame. Rain streaks the foreground; the alley behind her is already empty.
End with her small at the far end, still moving. Same red qipao, same lantern light.
```

Note that the camera in B is a slow single-axis move, worth 1, not the crane in the original, which the table prices at 3 — swapping the move is most of the saving. Face load now lives in A where the camera is locked, and travel lives in B where no face is legible. Both come in under their ceilings, and cutting A to B buys a size change you would not have had from one clip.

### Worked example — a two-hander

Over budget: two men argue across a table, both gesturing, handheld camera whipping between them, candle flickering, ten seconds of dialogue. Score: subject 2 + camera 3 (whip) + environment 1 (candle) = 6; ×1.3 for 10s = 7.8; `+1` for the second man acting independently and `+1` for a face over a third of frame = **9.8** against a ceiling of 4.

Rebalanced: shoot singles. Clip A is a locked medium of the first man speaking, candle flickering, 5s: subject 2 + camera 0 + environment 1 = 3. Clip B is a locked medium of the second man listening and then answering, 4s: the same 3. Both sit well inside the ceiling of 6, and you have gained real coverage instead of one unusable whip-pan. Shoot the two singles from opposite sides of the axis so the eyelines oppose — two singles from the same side gives you two men looking the same way ([cinematic-language.md](cinematic-language.md) owns the geometry). Cut logic lives in [editing-and-assembly.md](editing-and-assembly.md).

## Duration strategy

- Why short beats long for character work. Identity error accumulates with frame index, so the earliest seconds are almost always the cleanest frames in a generation. For a face-carrying shot, generate 3-5s. For hands doing something specific, 3-4s. Generating 10s to use 4 costs more, not less, once you count retries; see [production-workflow.md](production-workflow.md).
- Where longer is safe. No legible human face; one dominant environmental motion; locked or very slow camera; product, landscape, weather, abstract texture, or a slow reveal with nothing structurally complex to warp. These tolerate 8-12s comfortably.
- Splitting one action across two clips. Find the **pivot** — the instant of commitment, the moment the outcome becomes inevitable. Clip A ends *at* the pivot with the motion still in progress; clip B starts *just after* it, already in motion. Change the angle by at least 30°, or — if the camera stays on the same axis — the shot size by at least two steps, so the cut reads as coverage rather than as a glitch (the 30-degree rule, owned by [cinematic-language.md](cinematic-language.md); one size step on an unchanged axis reads as a stutter, not a cut). Where B is the same angle at a different size, build its first frame by cropping and re-rendering A's last frame, so light and costume carry across for free. Where B is a genuinely new angle that crop is not available — generate a fresh still and carry the identity, costume, and light values over from the [continuity bible](continuity-bible.md).
- Worked split. Intended action: "he opens the door and steps into the hallway." Pivot = the latch releasing. Clip A, insert on his hand and forearm, locked, 3s: the hand closes on the handle, turns it, and the door begins to swing, ending with the door edge just clear of the jamb — subject 2 + camera 0 + environment 0, `+1` for fine hand work, so 3. Clip B, wide from inside the hallway, locked, 4s: the door swings toward camera and he steps through into frame, ending stopped and facing down the hall — subject 2 + camera 0 + environment 1 for the door, so 3. Cut on the door's motion. Two easy clips replace one hard one. Note that A and B sit on opposite sides of the door, which in a wider A would be a line crossing; an insert this tight carries no screen direction, so the reverse reads clean.
- Extend versus regenerate. Extend when the last frame of the take is clean and the continuation is low-motion. Regenerate from a new keyframe when the last frame already shows drift — extends inherit and amplify every existing artifact.

## Language choice

- Use Chinese when the tool's primary UI and documentation are Chinese (即梦 / Dreamina, 可灵, 万相, and most domestic short-form tools), and especially when the subject matter is culturally specific. Terms like 旗袍, 弄堂, 灯笼, 蓑衣, 皮影 resolve far more reliably in Chinese than through an English paraphrase, and Chinese is more compact per unit of meaning, which matters under a prompt-length cap.
- Use English when the tool's training and documentation are English-first (Runway, Veo, Luma, Sora-class, Pika, Midjourney), and for technical camera and lighting terms *inside an otherwise English or mixed-language prompt* — focal lengths, `dolly in`, `rack focus`, `key light`, `f/2` are more stable in English there, because caption corpora carry them in English.
- Mixed-language prompts, and where they are actually right. On an English-first tool with culturally specific subject matter, write subject, costume, set, and the untranslatable nouns in Chinese and keep camera and lighting terms in English inside the same prompt. On a Chinese-UI tool — 即梦 / Dreamina, 可灵, 万相 — do not do this: the whole prompt is Chinese, craft terms included (固定镜头, 逆光硬光, 中景, 机位齐腰高度), which is what every 中文 example on this page and in [../assets/video-prompt-template.md](../assets/video-prompt-template.md) shows, and what [prompt-lexicon.md](prompt-lexicon.md) means by writing native Chinese rather than translating word by word. Each per-tool block above states which case that family is in.
- Never write the whole prompt twice in one field — the duplicate competes with the original and dilutes every clause. Keep a mirror in the other language in your shot plan for team review, and mark which one was actually sent.
- Retry discipline. Once a take is close, do not switch prompt languages between retries. A language switch changes every token and invalidates the comparison. Change one clause, in the same language, and keep the seed.

## Negative constraints

Only tool-specific behavior lives here. The full negative-prompt library, EN/中文 pairs, and banned-word list are owned by [prompt-lexicon.md](prompt-lexicon.md) — do not duplicate them into a prompt from memory, read them from there.

- Tools that expose a real negative field (at the time of writing: Kling, 万相, Pika, open-source graphs, and Veo/Vidu on some surfaces — confirm on the surface in front of you): put every exclusion in the field, keep the positive prompt free of the word "no". Four to six targeted items beat a wall of thirty; a bloated negative field dilutes each term and can suppress things you wanted.
- Tools with no negative field, or where you cannot confirm one is exposed on the surface you are using (Runway, Luma, most consumer surfaces, Sora-class depending on the surface): convert each exclusion into a positive fact about the frame. "No extra people" becomes "the platform behind her is empty". "No text" becomes "the shop signage is blank cloth". Negation words inside a positive prompt are unreliable and sometimes summon the thing.
- Never negate what the image already prevents. On image-to-video, exclusions about costume, era, or set are wasted tokens — the still already holds them. Reserve exclusions for temporal failures: identity change, extra limbs, camera behavior, scene cuts.

## Decision table — user statement to prompt shape

| The user says | Route to | Slots to fill |
|---|---|---|
| "I have a keyframe I like, make it move" | S1 | camera, start state, one action, one environment element, end state, identity lock |
| "No images yet, generate from text" | S2 | format, subject, place/time, action, size/angle/lens, one move, light source, audio, constraints |
| "I have a start and end image" | S3 | bridge line, single transformation, camera path, easing, what must not change, exclusions if there is no negative field |
| Names a tool and a shot, says nothing about assets | S1 by default | assume image-to-video for any shot with a person, say so in one line, and append a two-line S2 variant; assume S2 only for plates, inserts, and shots with no legible face |
| "It supports timestamps / I want a sequence in one go" | S4 | global block with identity locks, then action + camera per segment |
| "My tool has a camera slider" | S1, camera slot empty | set the move in the UI, delete all camera words from text |
| "My tool has a motion brush" | S1, restricted | brush only the moving region, zero the global motion control |
| "My tool has a negative field" | any shape | move all exclusions out of the positive prompt into the field |
| "My tool has no negative field" | any shape | rewrite each exclusion as a positive statement about the frame |
| "It generates audio" | S2 or S4 | add an audio sentence naming sources; say "no music" if scoring later |
| "I need the character to look the same across shots" | S1 or S3 | bind a reference, lock the seed, log both in the continuity bible |
| "It keeps cutting to other angles" | S2 | put "one continuous shot, no cuts" first; drop to one action |
| "The clip is too short for my action" | S1 twice | split at the pivot; between clips change the angle by ≥30°, or by two size steps if the axis is unchanged |
| "I already have the clip, the look is wrong" | no shape change | video-to-video at the adapter step: hold the take, replace the look, then check identity on first, middle, and last frames |
| "It came out warped / melty" | rescore | run the motion budget; cut the highest-scoring component first |
| "It looks like a slideshow" | S1 | the still lacks implied motion — regenerate the keyframe mid-action, see [image-model-adapters.md](image-model-adapters.md) |
| "I don't know what my tool supports" | ask 3 questions | input image? last-frame slot? negative field or motion number? |

For symptom-driven repair beyond the table above, use [failure-modes.md](failure-modes.md). For the finished prompt-pack format, use [../assets/video-prompt-template.md](../assets/video-prompt-template.md).
