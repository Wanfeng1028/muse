# Image Model Adapters (Keyframes and Stills)

Load this file when the task produces stills — keyframes（关键帧）, storyboard panels, first/last-frame pairs（首尾帧）, character or location reference sheets — or when generated stills drift in face, wardrobe, set, or light. This is Step 8 (Keyframe strategy) of the pipeline and the engine behind Mode E, whose emittable form is [keyframe-prompt-template.md](../assets/keyframe-prompt-template.md).

**Staleness warning, before anything else.** The control-surface matrix in §2 describes capability *classes as of writing*, not a live feature list. Vendors ship, rename, and remove controls constantly, a family's base model and its editing model behave nothing alike, and the same model exposes different knobs in a web UI, an app, and an API. Nothing in that table is a fact you can quote to a client — verify against current documentation before you promise a user a control. **Capability snapshot: 2026-08.** Anything older than about two release cycles is a prior, not a fact — confirm on the panel before you rely on it.

## 1. The keyframe is the control point

A video model does not invent your film. Given an input image it mostly re-renders what the still already decided: identity, wardrobe, set dressing, light direction and quality, lens perspective, palette, composition, screen direction. What the text prompt adds on top is motion, camera behavior, timing, and end state — see [ai-video-tool-adapters.md](ai-video-tool-adapters.md). So every attribute you failed to nail in the still is an attribute the video model will guess at, and it will guess differently on every retry. A director who is unhappy with a clip and rewrites the motion prompt for the fourth time is usually fixing the wrong document.

The credit argument is blunt. Across the platforms this file covers, a video generation costs substantially more per attempt than a still and comes back in minutes rather than seconds. Treat that direction as the stable part and the multiple as something to re-check against current pricing for the tools you actually use. Attempt counts are owned by the retry budget in [production-workflow.md](production-workflow.md), and every number there is planning guidance for sizing a schedule, not a measured success rate. Quoting its bands: with the keyframe locked, budget 2–4 clip generations per approved shot on a Green shot, 3–6 on an Amber one, and 6–15 per half on a Red one after splitting — which on a 20-shot Amber-heavy scene is 60–120 clip generations before you count the Red shots. Without a locked keyframe, none of those bands hold and neither do their stop rules, because you are re-rolling identity and motion inside the same generation and cannot tell which one failed. Against that, the stills the same table budgets for keyframe approval — 1–3 on a Green shot, 3–8 on an Amber one — are cheap, and faster in wall-clock time too: you iterate on a still while looking at it, not while waiting for a queue. Rule: never spend a video credit on a still that has not passed the QC gate in §9.

## 2. Control-surface matrix

This matrix describes **capability classes as of writing, not a live feature list.** Vendors ship, rename, and remove controls constantly; a family's base model and its editing model behave nothing alike; and the same model exposes different knobs in a web UI, an app, and an API. Verify against current documentation before you promise a user a control. Where a control is absent, your workaround is §4–§6, not a retry.

Legend, one grade finer than the video matrix in [ai-video-tool-adapters.md](ai-video-tool-adapters.md): `best` first-class and precise, `yes` present and workable, `part` partial, indirect, or setup-dependent, `no` absent or unreliable on the surfaces we looked at — read it as "check", not as "impossible" — and `varies` where surface, tier, and release differ often enough that only the docs can answer.

| Control surface | MJ | Flux | NanoBanana / Gemini-image | Seedream / 即梦 | Qwen-Image | SDXL + ControlNet | Ideogram | Recraft | Chat-surfaced |
|---|---|---|---|---|---|---|---|---|---|
| Text prompt fidelity (literal adherence) | part | best | best | yes | best | part | yes | yes | yes |
| Image reference / img2img（图生图）with strength dial | yes | best | yes | best | yes | best | yes | yes | part |
| Character reference (identity binding) | yes | part | best | yes | part | best | part | varies | part |
| Style reference | best | yes | part | yes | part | best | yes | best | part |
| Inpainting, masked region（局部重绘） | yes | best | part | best | yes | best | yes | yes | varies |
| Outpainting / extend canvas | yes | best | part | yes | part | best | yes | yes | part |
| Instruction editing ("change only X") | part | best | best | yes | best | part | part | part | yes |
| Multi-image composition (2+ inputs fused) | part | yes | best | yes | yes | yes | varies | varies | yes |
| Aspect ratio parameter | best | best | part | best | best | best | best | best | part |
| Seed control (reproducible) | part | best | varies | yes | best | best | yes | part | no |
| Negative prompt | yes | part | varies | yes | yes | best | yes | part | no |
| Text rendering inside the image | part | yes | yes | yes | best | no | best | best | varies |
| Upscale / detail pass | best | yes | part | yes | part | best | yes | yes | part |

Routing rules that fall out of the matrix:

- Need one face to survive 20 shots: work in the `best` character-reference column (NanoBanana/Gemini-class, or SDXL with a trained LoRA / IP-Adapter). Everything else needs the identity string in §4 doing the heavy lifting.
- Need "same frame, one thing moved" — i.e. first/last pairs: work in the `best` instruction-editing column (Flux edit-class, NanoBanana/Gemini-class, Qwen edit-class). This is the highest-leverage control in the matrix for film work.
- Need reproducibility for A/B testing one prompt word: you need `best` seed. Conversational/chat-surfaced models generally do not give you this; accept it and A/B with reference images instead.
- Need on-screen signage, a period newspaper, a Chinese title card: Ideogram, Recraft, or Qwen-Image. Do not fight a model that cannot spell.
- On some models — fast and distilled variants especially — negatives have no visible effect at all. If yours seem to be doing nothing, test it on one frame and assume they are doing nothing until proven otherwise; then move the exclusion into a positive statement ("bare plaster wall, nothing mounted on it" instead of "no posters"). Vocabulary for both directions lives in [prompt-lexicon.md](prompt-lexicon.md).
- The `Chat-surfaced` column is a class, not a product: any image model you reach through a conversational assistant behaves this way. Instruction editing is its native mode and the numeric surfaces are generally absent — assume nothing to seed and nothing to negate until the surface proves otherwise, and the ratio asked for in words rather than set, so check the delivery ratio on every output. Keep it for edits you can judge by eye.

### Three families, in the same shape as the video blocks

Short blocks for the three classes that carry most stills work in this pipeline, written in the shape the per-tool blocks in [ai-video-tool-adapters.md](ai-video-tool-adapters.md) use. Same caveat as the matrix, and the same decoupling that file states once: each heading names a capability class, and the product carrying it can be renamed, retiered, or withdrawn — confirm it is still offered on the surface the user has before you plan around it, and if it is gone, find whichever product now exposes the same surfaces and read the block against that.

#### Midjourney family

- Surfaces to exploit — `--ar` for the delivery ratio, `--sref` for a look carried across a scene, `--cref` and its weight for a face carried across shots, `--no` for exclusions, and a style-strength control. Parameters, not adjectives.
- Rules — set the ratio with `--ar` and generate native; never crop into the delivery ratio (§8). One `--sref` per scene, pinned early and reused verbatim, or the look re-rolls shot to shot. `--cref` binds a face *family*, which is why the matrix reads `yes` and not `best` — it does not retire the identity string in slot 3 or its checkable landmark. Exclusions go in `--no` as instances, never categories, and the positive prompt stays free of the word "no". Prompt fidelity is `part` here: a long literal slot list gets averaged, so spend words on slots 2–4 and let the flags carry the look.
- Typical failure and fix — the look is beautiful and the shot is wrong; the frame ignores the size, angle, and lens you stated. Fix: cut the prompt back to the slots that decide geometry, move the look onto `--sref`, and stop paying for it in words.

#### NanoBanana / Gemini-image class

- Surfaces to exploit — instruction editing on an uploaded image, multi-image composition, character reference. The highest-leverage column in the matrix for film work.
- Rules — phrase every edit as hold-plus-change with the holds named (§4); this is the class §6 assumes when it says derive the last frame rather than write it. Aspect is `part`: the output tends to inherit the input image's shape, so the delivery ratio is decided in the file you upload, not in a parameter. Seed is `varies`, so do not run single-word A/B tests here — A/B with reference images instead. Chain at most 2–3 edits from one master.
- Typical failure and fix — it re-generated instead of editing, background objects shifted, and you no longer have a pair. Fix: flip between the two files to catch it, restate the holds as a list of nameable objects rather than "same everything", and go back to the master instead of editing the edit.

#### Seedream / 即梦 class

- Surfaces to exploit — 图生图 with a strength dial, 局部重绘, reference images, 负向提示, seed, and stills for the 首尾帧 path on the video side.
- Rules — write the whole prompt in Chinese, craft terms included; the culturally specific nouns in [prompt-lexicon.md](prompt-lexicon.md) are the reason this class beats an English-first model on period-Chinese subject matter, and they only resolve in Chinese. Check which way the strength dial points before trusting a number (§6). Exclusions go in 负向提示 as a comma-separated list; keep 不 and 没有 out of the positive prompt.
- Typical failure and fix — the costume is right and the room came back contemporary. Fix: name three period objects and one period light source as positive facts instead of banning a category — F8 in [failure-modes.md](failure-modes.md).

## 3. Keyframe prompt anatomy: nine slots, then constraints

| # | Slot | What it locks | Example fragment |
|---|---|---|---|
| 1 | Shot ID | Your own traceability; ties the still to the shot list and continuity bible | `SC03_SH02.` |
| 2 | Size, angle, lens | Perspective and subject scale — the hardest thing to fix later | `Medium close-up, 85mm equivalent, eye level, slightly camera-right of his centerline.` |
| 3 | Subject identity string | The face. Verbatim, unchanged, every time (§4) | `A 34-year-old Han Chinese man, narrow jaw, deep-set eyes, …` |
| 4 | Pose implying action | Turns a portrait into a frame (§7) | `Half-risen from a wooden stool, weight on the front foot, head already turned to the door.` |
| 5 | Wardrobe and props | Continuity's most common failure after face | `Grey padded cotton jacket, top two frogging buttons undone, chipped white enamel mug in his left hand.` |
| 6 | Location and era | Set, materials, period lock | `Interior of a 1937 Shanghai lilong ground-floor room, whitewashed plaster, dark wood transom.` |
| 7 | Light source and direction | Named source, its side, its ratio — never a mood word | `Single kerosene lamp on the table camera-left, 45° off his nose; 4:1 lit side to shadow side, shadow side clearly darker but still holding detail, fill only from the whitewashed wall camera-right.` |
| 8 | Composition rule | Where he sits in frame and what the frame says | `Frame within frame: doorway occupies the right third; negative space above his head.` |
| 9 | Texture / medium | Grain, halation, palette — the "look" layer | `35mm still photograph, moderate grain, gentle halation on the lamp, warm ochre against cold grey.` |
| — | Constraints | Ratio and exclusions, named as instances | `16:9. No rendered text, no watermark, no plastic, no printed logos, no extra people.` |

Why this order and not another: many models weight early tokens more heavily, and in every model each slot constrains the slots after it. Framing and lens decide how much of the body is visible, which decides how much wardrobe detail matters. Identity must precede pose, because a pose stated first invites the model to build a body and then hang a generic face on it. Pose must precede wardrobe, because clothing renders as drapery over a posture. Light must come after location, because a lamp is only in the room once the room exists. Texture goes last so it modifies everything rather than competing for the subject slot. Constraints go last because in most models they are cleanup, not composition — an exclusion cannot rescue a prompt whose first thirty words already described the wrong shot. And every exclusion names an instance, never a category: "no modern objects" is not resolvable into anything a model can decline to draw, which is the mechanism behind F8 in [failure-modes.md](failure-modes.md), while "no plastic, no printed logos, no rubber soles, no wristwatch" is a list of things it can.

Two hard rules for slot 3: no emotion words and no attractiveness words. "Anxious", "haunted", "beautiful" in the identity slot change the face geometry from generation to generation. Expression belongs to slot 4, described physically ("jaw set, eyes narrowed slightly, mouth closed"). Shot size, angle, and lens vocabulary for slot 2 is owned by [cinematic-language.md](cinematic-language.md); the ratio ladder and quality vocabulary for slot 7 by [lighting-and-color.md](lighting-and-color.md) — use its rungs (1:1, 2:1, 4:1, 8:1, 16:1) and follow its rule of always writing the ratio in words as well as in numbers — in practice the worded version survives generation and the bare colon often does not.

## 4. Character consistency playbook, cheapest first

| Rung | Cost | Holds | Use when |
|---|---|---|---|
| Identity string | free | face family, build, hair, one landmark | always, on every prompt, in every tool |
| Character sheet | ~4 stills once | a ground truth to compare against and to feed as reference | any character in more than 3 shots |
| Reference-image binding | per-generation | face and often wardrobe | tool exposes character reference |
| Seed lock | free | everything, only when nothing else changes | A/B testing one prompt word |
| Instruction editing | 1 generation | everything except the one named change | first/last pairs, wardrobe changes, expression changes |
| Face inpaint | 1–3 generations | repairs one bad frame | a keeper frame with a wrong face |
| Cut around it | free | nothing — it hides the problem | the drift is unfixable and the shot is short or wide |

### Identity string

The spec is not here. Length, the fixed physical facts, the single wardrobe anchor, the banned words, and the worked good/bad pair are owned by the identity string contract in [continuity-bible.md](continuity-bible.md) — read them there, store the string in the character record under that file's `CHAR-slug` grammar, and version it there. What this file adds is only how the string meets the nine slots:

- Paste it **verbatim** into slot 3, every prompt, every tool. Change one word and you have a new person, so it is never paraphrased and never shortened for a close-up.
- Scope. The full string is face plus one wardrobe anchor. Where wardrobe is carried separately in slot 5, slot 3 takes the face-only opening of that same string, unchanged and in the same order — the opening words, not a fresh clause written for this shot.
- The two hard rules for slot 3 above still bind: no emotion words, no attractiveness words. Expression is physical, and it lives in slot 4.
- Insist on at least one checkable landmark — a scar, a mole, a chipped tooth. It is the only clause that proves drift rather than merely suggesting it, and check 1 of the QC gate in §9 is looking for it.

### Character sheet

Generate once, before any shot keyframe:

```text
Character sheet, CHAR-shen. Four views of the same person, evenly spaced left to right: front, three-quarter
left, full profile left, full body front.
[IDENTITY STRING, verbatim]
Neutral expression, relaxed shoulders, arms at sides, no props.
Wardrobe: [garment list exactly as recorded in the continuity bible].
Flat even lighting, no shadow direction, no rim light. Plain mid-grey seamless background.
No lens distortion; each view stands on the same ground line and fills 80% of the canvas height.
16:9. No text, no labels, no watermark, no extra people.
```

Use a wide canvas, not a square one: four views side by side on a 1:1 canvas gives each figure a sliver about a quarter of the canvas width, and the face resolution that comes back is too low to crop as a reference. Honest note: many models drift *between panels on one canvas*. If the four views disagree with each other, generate them as four separate images instead, reusing the same seed and the same reference, and compose the sheet yourself. Then use it three ways: crop the three-quarter head as the reference image for close and medium shots, the full body for wides (a head crop makes the model guess the build), and keep the sheet open as the ground truth for the QC gate. Neutral light and plain background are not aesthetics — they stop the reference from dragging the shot's lighting and set into the new frame.

### Reference-image binding, seed lock, instruction editing

Where a character-reference control exists, feed the sheet crop and start mid-scale on whatever dial the tool exposes, then tune by symptom in one direction only: if the new frame inherits the sheet's flat frontal light or its neutral pose, lower it one step; if the face reads as a relative rather than the same person, raise it one step. Two steps in each direction is the whole search. Log the value you settle on next to the character record so every later shot uses it. Reference binding constrains the face, not the wardrobe or the era — keep slots 5 and 6 written out.

Seed lock reproduces an image only when every other input is byte-identical: same model version, same prompt string down to the comma, same sampler and steps and dimensions. Change one word and the seed hands you a different person, which is the opposite of what people expect. So seeds are a tool for isolating one variable ("does adding *rain-darkened collar* change the composition?"), not a consistency mechanism. Record them anyway — the continuity bible has a field.

Instruction editing is the highest-leverage control on the matrix. Phrase it as hold-plus-change, and name the holds explicitly:

```text
Keep everything identical: same face, same grey padded jacket, same room, same lamp position, same framing,
same grain. Change only this: his head is turned 30° toward camera-left and his eyes are open, looking down.
Do not change the background, the composition, or the lighting.
```

中文 UI variant of the same template, for 即梦 / Seedream-class tools:

```text
保持完全不变：同一张脸、同一件灰色棉袄、同一个房间、煤油灯位置不变、构图不变、颗粒感不变。
只改这一处：他的头向左转 30 度，眼睛睁开，视线向下。
不要改动背景、构图或光线。
```

Verify it actually edited rather than re-generated: flip between the two images. If a background object shifted, the model re-rendered the world and you do not have a pair. Edit passes commonly accumulate a small crop or scale drift that is invisible in one hop and obvious in four, so chain at most 2–3 edits from one master before regenerating from the master.

### Face inpaint, and when to stop

Face inpaint（局部重绘）is repair, not production. Mask the head with a generous feather, supply the identity string alone plus the light direction, and run at low denoise — roughly 0.25–0.4 where the tool exposes a 0–1 dial, enough to rebuild features without repainting the skull. Two things go wrong: the repaired face is sharper than the rest of the frame (match grain and add the same halation), and the repaired face is lit from the wrong side (restate slot 7 in the inpaint prompt, every time).

When to accept drift: measure the head, not the shot name. A standing figure runs about seven and a half head-heights, so a head occupying under roughly 10% of frame height means the figure is full-length or wider, and at that size the audience is reading silhouette and wardrobe, not features. Accept the drift there, and accept it on any face on screen under about 1.5 seconds. Inside that — anything from a medium-wide in, where the head is 15% of frame height or more — drift is visible and must be fixed. When it is visible and you cannot fix it, cut around it: restage as an over-the-shoulder, a profile, a silhouette against the practical, a shot from behind, or a hands-and-prop insert that carries the same story beat. See [blocking-and-staging.md](blocking-and-staging.md) for restaging options and [failure-modes.md](failure-modes.md) for the symptom-to-fix table.

## 5. Location consistency playbook

- Location plate（场景底板）. Before any shot with people in it, generate the empty set at the master angle and approve it. No characters, no action. The plate is now the truth for materials, wall color, furniture positions, and light. Every other frame in that location is derived from the plate by editing or img2img, never written from scratch. Store it under the `LOC-slug` / `plate-wide` names defined in [continuity-bible.md](continuity-bible.md).
- Location sheet, three angles. Master (the widest useful view), reverse (roughly 180° opposite, which will show the wall behind camera in the master), and a profile or 90° cross-angle. Generate the reverse and cross-angle *from the master plate* via instruction editing where the tool allows it, so shared surfaces carry over.
- Light direction in room coordinates, not camera coordinates. This is the technique that makes multi-angle work. Write the source once as a fact about the room — "the single window is on the east wall; mid-morning sun enters hard at 30° elevation" — then translate it per angle instead of restating it. In a master shooting toward the south wall, the east window falls on the camera's left and shadows run camera-right. In the 180° reverse, now shooting toward the north wall, that same window is on the camera's right — not its left — and shadows run camera-left; the side flips because the camera turned, the window never moved. Only in the cross-angle from the east side looking west is the source behind camera, giving frontal light with shadows falling away from lens. Writing "key from camera-left" in both the master and its reverse is the single most common multi-angle error: it silently moves the window across the room, the reverse reads as a different room at a different hour, and no video model will reconcile them. Same discipline as screen direction, which is owned by [cinematic-language.md](cinematic-language.md).
- Adding a character into a plate. Inpaint or instruction-edit them in; do not re-prompt the room. State three things the model routinely drops: the light on them ("lit by the same kerosene lamp camera-left, 4:1 lit side to shadow side, shadow side clearly darker but still holding detail"), the contact ("boots flat on the floorboards, shadow falling to camera-right"), and the occlusion ("he occludes the lower half of the doorway"). Missing contact is why composited figures look pasted.
- Era lock. Carry a matched positive and negative clause per period location, stored with the location record:

```text
Positive: 1937 Shanghai lilong interior — whitewashed plaster, dark stained wood transom, enamel basin,
kerosene lamp, hand-painted paper calendar.
Negative: no moulded plastic, no electric light fixtures, no printed logos or modern typography,
no stainless steel, no aluminium or vinyl frames.
```

Five items, inside the four-to-six negative budget in [prompt-lexicon.md](prompt-lexicon.md) — a longer list dilutes rather than tightens. An era negative that names *materials and manufacturing processes* holds up better than one that names objects ("no phones"), because the anachronisms that actually arrive are the ones you did not think to name; a material class catches all of them at once.

## 6. First/last frame pairs

The rule: generate the first frame properly, approve it, then **derive** the last frame from the approved file. Use instruction editing where available; otherwise img2img with the same prompt and only slot 4 rewritten, at roughly 0.25–0.4 on a 0–1 denoise dial — enough to move a head or a hand, low enough to leave the room alone. Check which way the dial points before trusting the number: some UIs label it "denoise" (higher means more change) and others label the same control "image strength" or 参考强度 with the sense inverted (higher means less change). Move it on one test frame and see which direction the room drifts.

Why writing the last frame from scratch usually fails: it starts from different noise, so it re-rolls every variable you did not state — the microstructure of the face, the fold pattern of fabric, the exact placement of background objects, the falloff of the lamp, the grain. The video model then has to invent a transition between two subtly different worlds. It does this in one of three ugly ways: a cross-dissolve, a face that morphs mid-clip, or a background that breathes. A 2% shift in a background object's position reads on screen as a camera bump.

Second rule, the pair-scope test: if more than one of {one body part moved, one object moved, one light changed} differs between A and B, you do not have a pair — you have two shots. Split them.

Worked pair — SC05_SH03, a man on a night bus registers something outside the window.

```text
Frame A (generated fresh, all nine slots):
SC05_SH03. Medium shot, 50mm equivalent, eye level, from the aisle seat opposite.
[IDENTITY STRING]. He sits slumped against the window, temple resting on the cold glass, both hands in his
lap, eyes open and unfocused. Dark wool overcoat, collar up, a folded paper ticket between two fingers.
Interior of a city bus at night, moulded plastic seatbacks, wet window glass. Sole light is the strip of
ceiling fluorescent above and slightly behind him, plus intermittent orange sodium streetlight raking in from
camera-left through the window. Off-center left third, empty seats receding to the right. 35mm photograph,
heavy shadow, cool cyan against sodium orange. 16:9. No text, no watermark, no extra people.

Frame B (instruction edit of Frame A — never re-prompted):
Keep everything identical: same face, same overcoat and collar, same ticket, same bus interior, same seat
positions, same ceiling fluorescent, same window reflections, same grain and color. Change only this: his
head has lifted 15° off the glass and turned toward the window, and his eyes are focused. Do not change the
framing, the background, or the lighting.
```

That pair gives a video model exactly one thing to interpolate — a head lift — which is the amount of change a 3–4 second clip can absorb without inventing anything. Hand the same tool two independently generated frames of the same idea and you will get a morph.

## 7. Storyboard panel rules

A panel earns its place only if it does one of five jobs: implies a motion about to begin, shows a motion just completed, delivers a reveal, states a power relationship, or plants a clue. If you cannot name which one, the panel is a portrait and it will animate into a slideshow. Name the job in your shot notes; the video prompt then has something to continue.

Prompt-side techniques for making a still imply motion — each is a physical fact, not an adjective:

| Technique | Prompt fragment |
|---|---|
| Weight shift | `weight fully on the back foot, front heel lifted off the floor` |
| Mid-stride | `caught mid-stride, rear foot at toe-off, neither foot flat` |
| Garment lag | `coat hem swung 20° behind her direction of travel, scarf trailing` |
| Gaze off-frame | `looking at something just outside the right edge of frame, head not yet turned` |
| Object in flight | `the cup has left her fingers, 10cm above the table, not yet tipped` |
| Unstable contact | `the ladder's left foot lifted 3cm off the floor, tilting` |
| Interrupted reach | `his hand 5cm from the door handle, fingers already spread` |
| Residue of past motion | `the curtain still displaced, the door 15° open and swinging inward` |

Weak panel prompt: `a woman walking down a hotel hallway, cinematic, dramatic lighting`. Strong: `a woman mid-stride down a hotel hallway, rear foot at toe-off, coat hem swung behind her, gaze fixed on a doorway just outside the right frame edge; sole light from wall sconces every 3m, hard falloff between them`. The second one has a next frame implied in it; the first does not.

## 8. Aspect ratio and framing parameters

Generate native to the delivery ratio. Models condition on canvas shape: the same words at 9:16 produce a tighter body crop, more headroom compression, and different background scale than at 16:9. A frame composed for 16:9 has its horizon, headroom, and lead room placed for 16:9, and cropping destroys exactly those decisions. Ratio-as-meaning is owned by [cinematic-language.md](cinematic-language.md); this section is only about the parameter.

The arithmetic that people get wrong: a 9:16 crop taken from a 16:9 frame keeps only 31.6% of the frame width — call it the central third. Symmetrically, a 16:9 crop from a 9:16 frame keeps 31.6% of the height. In pixels, center-cropping a 1920x1080 still to 9:16 yields 607x1080, which then needs a 1.78x upscale to reach 1080x1920. That upscale lands on the face.

If you genuinely must deliver two ratios from one generation, do it deliberately: generate at the wider ratio, and put the safe zone in slot 8 of the prompt — `subject and their eyeline both inside the central third of the frame width; nothing story-critical outside it`. Then check the crop before generating video, not after. The better answer for most projects is two native generations sharing an identity string and a location plate: same character, same set, two compositions, both correctly framed. Also confirm your still resolution meets or exceeds what the target video tool ingests — feeding an upscaled still to a video model reproduces the upscaling artifacts in motion, where they shimmer.

## 9. Keyframe QC gate

Run this before spending any video credit on a still. This is the reasoned form, kept here for why each check exists. The form you actually emit to a user about to generate is the tick-box gate in [keyframe-prompt-template.md](../assets/keyframe-prompt-template.md), and clip-level and sequence-level gates are in [qc-checklist.md](../assets/qc-checklist.md) — do not re-derive either here, and where the two lists have drifted apart, the tick-box gate is the one that ships.

```markdown
Keyframe QC gate — 12 checks. Any FAIL means regenerate or edit the still, not the video prompt.

1. Identity string appears verbatim, and the character's unique landmark is visible and correct.
2. No emotion or attractiveness words in the identity slot; expression is described physically in the pose slot.
3. Every named garment and prop is present, correct in color, and in the correct state (buttoned, wet, torn).
4. The light source is named and its direction matches the location plate; shadows fall on the opposite side.
5. Light quality and ratio match the other approved keyframes in this scene.
6. Apparent perspective matches the stated focal length (no wide-angle nose on an 85mm close-up).
7. Eyeline and screen direction agree with the shot list; subject sits inside the delivery-ratio safe zone.
8. The frame performs one of the five panel jobs — name it: begin / completed / reveal / power / clue.
9. Anatomy sweep: finger count, pupils and eyelines, and hands in real contact with props, not through them.
10. Era sweep: no forbidden material, fixture, logo, or text anywhere in frame, including reflections.
11. Generated native to the delivery aspect ratio, at or above the video tool's ingest resolution — not cropped.
12. If this is a first/last pair: flip between the two frames; only the intended element differs.
```

Failures 4, 6, and 9 are the ones that survive into video and cannot be repaired there. Symptom-to-cause routing for anything that slips through is in [failure-modes.md](failure-modes.md); retry budgets and versioning in [production-workflow.md](production-workflow.md).

## 10. Before / after keyframe prompts

Pair 1 — identity that survives twenty shots.

```text
Before: close-up of a beautiful young woman looking worried in a dark room, cinematic, moody, 8K
After:  SC02_SH07. Close-up, 85mm equivalent, eye level. A 26-year-old woman, broad cheekbones, round chin,
        heavy-lidded grey eyes, a small mole below the right eye, dark brown hair pinned back with two
        loose strands. Brow drawn together, jaw set, mouth closed. Grey wool cardigan, top button missing.
        Single candle on the table camera-right, 30° below eye level; 8:1 lit side to shadow side, shadow
        side nearly black with only the edge of the cheek catching light, no bounce card. Negative space
        camera-left. 35mm photograph, fine grain. 16:9. No rendered text, no watermark.
```

Changed: the impression ("beautiful", "worried") became the face-only opening of an identity recipe, with a checkable landmark — the mole — plus a physically-described expression. The mood adjectives that were re-rolling the face are gone, and the light is a named source at a stated angle, on a rung of the ratio ladder, written in words as well as numbers.

Pair 2 — a portrait becomes a frame.

```text
Before: a man standing at the top of a staircase looking down, tense atmosphere
After:  SC04_SH01. Wide shot, 28mm equivalent, low angle from three floors below, camera looking straight
        up the stairwell. [IDENTITY STRING]. His weight is on the back foot, the front foot already
        extended over the top tread with the heel raised, right hand still on the newel post but the
        fingers loosening; head angled down over the rail, past the lens. Sole light is a landing window
        above him, hard, raking down the well. He is on the upper-right third; the receding spiral of
        rails fills the frame between him and camera. 16:9. No text, no watermark, no extra people.
```

Changed: "standing... looking down" is a resting pose with nowhere to go, so the clip holds it and calls that a shot. Weight on the back foot, a lifted heel, and a loosening grip are a descent that has already started; the model has somewhere to go.

Pair 3 — a last frame that is actually a pair.

```text
Before (written from scratch): the same woman now standing by the window, having got up from the chair,
        same room, same style, cinematic continuity
After  (edited from the approved first frame): Keep everything identical: same face, same grey cardigan
        with the missing button, same room, same candle position and intensity, same framing, same grain.
        Change only this: her head has turned 25° to camera-right and her chin lifted slightly. Do not
        change the background, the composition, or the lighting.
```

Changed: two things at once. The move shrank from "crossed the room and changed pose" (two shots, not a pair) to a single head turn, and the frame is now derived from the approved file instead of re-rolled from noise — so nothing in the background can drift.
