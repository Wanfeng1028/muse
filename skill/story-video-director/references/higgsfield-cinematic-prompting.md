# Higgsfield-derived cinematic prompting

Use this reference for action, performance, music-video, spatially complex, unusual-physics, or tightly controlled multi-shot clips. The heuristics were distilled from the open-source prompts and project brief in Higgsfield's [`ZEPHYR Special FINAL` Cinema Studio project](https://higgsfield.ai/generate?projectId=c1864ed3-89e2-42fc-a8b6-d691a21399a1), inspected 2026-08-14. Treat them as provider-agnostic directing methods, not guaranteed syntax for every model.

## Contents

1. Control layers
2. Prompt strictness
3. Input engineering
4. Spatial continuity
5. Camera and optics
6. Action, physics, and atmosphere
7. Audio and music timing
8. Locks and exclusions
9. Failure-driven iteration
10. Compact patterns

## 1. Control layers

Build complex prompts in this order. Omit a layer only when it adds no useful control.

1. **Scene context** — one concise sentence stating the event, emotional purpose, duration, and cinematic register.
2. **Active references** — assign each file one role: identity, costume, location geography, prop, pose, light, audio, or spatial layout. State inheritance and exclusions.
3. **Atmosphere** — describe the environmental system across the whole clip: wind, haze, dust, rain, petals, smoke, crowd motion, or silence.
4. **Location map** — establish landmarks and initial coordinates using frame-relative language such as left/right, foreground/background, center axis, or approximate x-position.
5. **First frame and blocking** — start on the action when appropriate; state who is where, facing which direction, and what is already moving.
6. **Format mode** — choose `SINGLE CONTINUOUS TAKE` or `CONTROLLED MULTI-SHOT SEQUENCE`; state cut policy and real-time/slow-motion policy.
7. **Optics** — specify useful field of view or focal-length ranges, camera height, depth of field, shutter/motion-blur behavior, and whether focal length stays locked within a segment.
8. **Camera** — describe rig feel, path, shake, correction, and relationship to subjects. Use physical language, not adjectives alone.
9. **Action timing** — assign visible actions, camera behavior, impacts, reactions, cuts, and sound to time ranges.
10. **Physics** — state mass, inertia, gravity, contact, recoil, material deformation, cloth/hair/accessory response, and environmental consequences.
11. **Lighting** — define motivated source, direction, contrast, exposure constraints, atmospheric interaction, and any cue-driven change.
12. **Audio** — define dialogue/music/diegetic policy and synchronize important sounds to actions or cuts.
13. **Final frame** — give an editorially usable destination.
14. **Positive locks and negative prompt** — restate the few non-negotiable facts, then exclude plausible failures.

Do not blindly maximize prompt length. A simple insert or reaction shot may need only context, references, camera, timing, audio, final frame, and negatives.

## 2. Prompt strictness

Choose control density from the real risk:

- **Strict choreography**: use for exact geography, dialogue coverage, transformation order, product behavior, stunts, or continuity-critical action. Specify maps, lens/angle per segment, timestamps, physics, and locks.
- **Anchor-point direction**: use when variation is desirable. Dictate identity, opening state, 2–4 key events, physical stakes, and final state, then allow the model freedom in connective camera motion.
- **Loose performance**: use for dance, texture inserts, reactions, or atmospheric cutaways where the performance matters more than exact staging. Keep one hero gesture or beat precisely timed.

If repeated generations preserve object placement but vary camera angles attractively, select and edit the best takes instead of over-constraining every transition.

## 3. Input engineering

When a scene depends on unusual gravity, orientation, pose, scale, reflection, or spatial relationship, change the input before adding more prose.

- Rotate or invert a character/location anchor to bake the required gravity into the source.
- Create a purpose-built start frame for a hanging, prone, underwater, mirrored, or extreme-perspective state.
- Use a positional layout image to communicate relative placement and movement direction even when it is not intended as the finished-film first frame.
- Create state-specific identity anchors when a recurring character has materially different conditions, such as inverted/blood-flushed, soaked, injured, aged, transformed, or helmeted.
- Exclude layout lines, labels, panels, arrows, neutral poses, and guide-background styling from the final film.

Prefer changing the input when the model repeatedly fails the same geometry or physics after two clear prompt attempts.

## 4. Spatial continuity

Pre-choreograph complex action before prompting.

Define:

- fixed landmarks and frame zones;
- subject start positions and facing directions;
- entry and exit paths;
- which objects are fixed, carried, destroyed, or revealed;
- screen direction across cuts;
- what remains visible after each impact;
- the next clip's opening composition when clips connect.

Use layout references as positional guides, not necessarily direct shot inputs. The prompt must say whether the image controls geography only, composition only, or the literal first frame.

For a sequence distributed through an edit, design the standout set piece first, then build earlier clips toward it and later clips from its consequences.

## 5. Camera and optics

Make camera language executable:

- State camera height, distance, path, speed, and subject relationship.
- State whether the shot is handheld, shoulder-mounted, dolly, crane, orbit, vehicle-mounted, body-mounted, or locked.
- For handheld work, describe believable breath, weight shifts, over-correction, reframing, and directional motion blur. Avoid generic `dynamic camera` alone.
- Use wide lenses and low height for speed, scale, looming approach, and spatial immersion.
- Use short telephoto or long focal lengths for compression, isolation, facial detail, and hazy action layers.
- Lock the lens inside each timed segment when spatial stability matters; change focal length only at an explicit cut.
- Pair camera motion with one dramatic job: reveal, pursuit, impact, disorientation, intimacy, or scale.

Avoid incompatible instructions such as `locked-off` plus `fast orbit`, or `tight close-up throughout` plus an unexplained wide establishing beat.

## 6. Action, physics, and atmosphere

Write actions as contact chains:

```text
wind-up → contact → material response → body recoil/follow-through → debris/cloth/environment reaction → recovery or next objective
```

For heavy subjects, give visible proof of mass: planted feet, delayed acceleration, ground compression, structural damage, servo load, recoil, and momentum that continues after impact. For light or agile subjects, show quick center-of-mass shifts, controlled landings, and secondary motion.

Treat atmosphere as a continuous physical system. Wind should move hair, wardrobe, grass, smoke, dust, and loose debris in a compatible direction. Haze should exist across foreground, midground, and background rather than appearing as a flat overlay. Lighting should reveal particles and depth.

Use realism clauses only when relevant and observable: pores, asymmetry, material roughness, lens imperfections, motion blur, edge softness, halation, or film grain. Do not stack named filmmakers or prestige formats as substitutes for staging.

## 7. Audio and music timing

For music-led clips:

- identify the uploaded audio and its job;
- map cuts, choreography, lip-sync, hero gestures, and final pose to musical beats or lyric phrases;
- quote only the exact lyric portion needed for the clip;
- specify whether vocals are lip-synced or merely background music;
- state `no dialogue`, `no subtitles`, or `no on-screen lyrics` when applicable.

For diegetic action, synchronize sounds to visible causes: buckle click, strap snap, footfall, impact, metal strain, breath, wind change, door/hatch release, debris fall. Avoid listing generic sound effects without timing or source.

## 8. Locks and exclusions

End complex prompts with a short **positive-lock summary** containing only the essential contract:

- exact subject count and identity;
- core action order;
- weapon/prop policy;
- location continuity;
- camera mode and duration;
- required physical quality;
- text/subtitle/logo policy.

Positive locks reinforce what must appear. Negative prompts exclude likely alternatives. Do not repeat the entire prompt verbatim.

Useful exclusions include:

- no extra characters, duplicate subjects, teleports, or position swaps;
- no invented exterior/interior views;
- no wrong weapon, costume, creature design, or prop;
- no floaty mass, frictionless contact, or consequence-free impacts;
- no lens drift inside a locked segment;
- no CG/plastic skin when live action is required;
- no reference grids, labels, arrows, studio backgrounds, logos, subtitles, or watermarks.

## 9. Failure-driven iteration

Keep failed takes as diagnostic evidence. Change one control layer at a time.

1. **Wrong orientation/physics** → rotate, invert, or rebuild the input anchor.
2. **Object positions scramble** → add a location map or positional layout reference; simplify movement paths.
3. **Identity drifts** → reduce competing references; strengthen one identity anchor and repeat visible markers.
4. **Camera becomes generic** → add physical path, height, rig behavior, lens, and one dramatic purpose.
5. **Action feels weightless** → rewrite as a contact chain with inertia and environmental consequences.
6. **Too many missed beats** → reduce action count, split the clip, or switch to anchor-point direction.
7. **Prompt becomes contradictory** → remove decorative style clauses before removing spatial, action, or continuity constraints.

## 10. Compact patterns

### Continuous collision course

```text
拍摄模式：单一连续镜头，无剪辑，实时速度。
首帧已在动作中：[主体]从远处沿中心轴冲向低机位镜头。
镜头：低机位广角，摄影机同时向前推进，在主体之间穿行；近身掠过时出现方向性运动模糊和真实手持纠偏。
物理：[步态、质量、地面/尘土反馈]，不得漂浮、瞬移或穿模。
最终画面：摄影机穿过最后一个主体，主体从两侧掠向画外，尘雾留在镜头前。
```

### Controlled multi-shot action

```text
拍摄模式：受控多镜头序列，硬切；每段内部焦段固定。
空间地图：[固定地标、主体起点、敌人入口、退出方向]。
0.0—2.0秒：[建立威胁与转身迎击]。
2.0秒硬切。
2.0—4.5秒：[第一记接触链与环境后果]。
4.5秒硬切。
4.5—7.5秒：[第二动作、完成目标并离场]。
正向锁定：[唯一主体、动作顺序、无武器/指定武器、场景连续、真实质量]。
```

### Unusual gravity

```text
输入策略：使用已旋转/倒置的状态参考锁定重力方向。
场景空间本身保持倒置；人物解除束缚后落向当前结构顶面，并在倒置空间中直立。
头发、服装、悬挂物、液体和尘埃始终服从同一重力方向；状态转换只发生一次。
镜头不切到会破坏方向感的外部正向视角。
```
