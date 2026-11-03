# 女性角色身体设计模块

## 生产链集成规则

- 本模块只负责年龄表现、人体骨架、体型、姿态、功能和镜头归一化。
- 输出稳定的 `BodySpec`，不要重写角色姓名、文化身份、服装故事或场景。
- 默认渲染画风由 `00-visual-contract.md` 控制。
- 当已有 CharacterBible 明确锁定体型时，只做一致性审计或目标修复。
- 任何性感、成熟或曲线要求都先通过年龄安全门。
- 结果交给角色资产模块时，只传递人体字段和必要负面约束。

下面保留并整合原专业规范。

---

# Female Character Body Design
Create coherent, production-ready female character body specifications and image-generation prompts. Treat body design as a system of age presentation, skeletal proportions, volume distribution, posture, function, costume, camera, and visual style—not as a list of isolated sexualized adjectives.
## Core Principles
1. Establish age presentation before body shape.
2. Build the skeleton before adding curves, costume, armor, hair, tails, or mechanical equipment.
3. Keep ribcage, abdomen, pelvis, gluteal mass, and thighs structurally continuous.
4. Separate human anatomy from silhouette-extending elements such as rigging, capes, sleeves, hair, wings, and tails.
5. Treat head-count values as approximate visual design ranges, not medical measurements or official franchise statistics.
6. Correct for lens, camera height, pose, footwear, headgear, and perspective before evaluating proportions.
7. Prefer clear, ordered, non-contradictory prompts over keyword accumulation.
8. When referencing an existing game, translate observed design language into generic structural terms. Do not claim an exact official proportion unless the publisher explicitly provides it.
## Safety and Age Gate
Run this gate before any other step.
- Classify the requested presentation as `adult`, `youthful/minor-coded`, or `ambiguous`.
- Treat terms such as `萝莉`, `幼态`, `childlike`, `school-age`, `little girl`, or visibly prepubescent proportions as youthful/minor-coded unless the user clearly requests a compact adult body.
- For youthful/minor-coded characters, allow only non-sexual character design: modest practical clothing, neutral or energetic poses, ordinary camera placement, and no erotic emphasis.
- Do not add cleavage, lingerie, fetishwear, transparent clothing, pin-up posing, breast/hip exaggeration, voyeuristic framing, or sexualized camera angles to youthful/minor-coded characters.
- If the request combines youthful/minor-coded traits with sexualization, refuse that portion and offer a non-sexual youthful design or a clearly adult petite alternative.
- When age is ambiguous and sexualized features are requested, default to a clearly adult character and state that assumption in the BodySpec.
## Research and Evidence Rules
When the user requests analysis of a current game, character, art book, or design trend:
1. Search current official publisher, developer, game, art-book, or setting-material sources first.
2. Use official full-body art or neutral model sheets where available.
3. Distinguish three evidence levels:
   - `official`: explicitly stated by the rights holder.
   - `observed`: directly visible in official art.
   - `inferred`: estimated from perspective-corrected visual comparison.
4. Never present an inferred head ratio, height, cup size, waist size, or body measurement as official.
5. Record known distortions: low angle, wide lens, bent knees, heels, platform shoes, headwear, animal ears, hair volume, and cropped feet.
6. Prefer multiple representative characters over one extreme promotional illustration.
## Supported Tasks
Use this skill for:
- Creating a new female character body specification.
- Selecting among multiple body archetypes.
- Converting a rough description into a production prompt.
- Comparing two or more proportion systems.
- Auditing an existing prompt for contradictions.
- Diagnosing distorted anatomy in a generated image.
- Writing a targeted image-edit instruction.
- Creating neutral turnaround or proportion-sheet prompts.
- Translating franchise-inspired visual language into an original, generic design system.
Do not use this skill as a substitute for medical, anthropometric, fitness, or health assessment.
## Input Normalization
Extract or infer these fields. Ask only when a missing field materially changes the result; otherwise use conservative defaults and state them.
```yaml
intent: create | compare | analyze | repair | edit | generate-variants
age_presentation: adult | youthful/minor-coded | ambiguous
role: character function or occupation
archetype: A-I or custom
head_count: approximate head-to-body ratio
height_impression: petite | average | tall | monumental
skeleton:
  shoulder_width: narrow | moderate | broad
  ribcage: compact | balanced | deep
  waist_section: short | balanced | elongated
  pelvis: narrow | balanced | broad | powerful
volume_distribution:
  upper_torso: restrained | balanced | full
  abdomen: flat-natural | soft-natural | athletic
  hips: narrow | balanced | full | powerful
  thighs: slim | soft | full | muscular
  calves: slim | tapered-athletic | muscular
limb_language: compact | balanced | elongated | powerful
pose: neutral | elegant | tactical | dynamic | grounded
function: mobility | ranged-combat | heavy-weapon | ceremonial | civilian
costume: clothing and armor logic
camera: shot size, height, angle, lens, distance
render_style: anime | semi-realistic-anime | stylized-3D | realistic-CG
output_mode: quick | full | prompt-only | critique | edit-instruction
model_target: natural-language | tag-based-diffusion | generic
```
## Measurement Convention
Use `U` as one head unit measured from cranial top to chin.
- Exclude animal ears, hair ornaments, crowns, hats, heels, geta, platforms, and floating bases.
- Measure total skeletal height on a common ground plane.
- For bent poses, estimate the straightened skeleton rather than the visible bounding box.
- Check anatomical landmarks as a chain rather than isolated coordinates:
  `head → clavicle → ribcage → waist → pelvis → crotch → knee → ankle → foot`.
- A head-count value controls vertical rhythm. It does not alone define maturity, attractiveness, weight, or muscularity.
## Archetype Router
| ID | Archetype | Approx. head count | Primary design language | Default age gate |
|---|---|---:|---|---|
| A | Youthful compact / 小巧幼态型 | 5.3-6.0 | larger head, short limbs, low center of gravity | youthful, non-sexual only |
| B | Petite adult / 小型紧凑成年体 | 6.2-6.7 | adult skeleton, compact stature | adult |
| C | Balanced cute / 可爱均衡型 | about 7.0 | approachable, balanced, lightly elongated | adult |
| D | Standard heroine / 标准二游女主型 | 7.4-7.6 | versatile heroic elegance | adult |
| E | Tactical curve / 战术曲线型 | 7.7-7.9 | compact torso, stable pelvis, strong upper thighs | adult |
| F | Elongated aristocratic / 纤长贵族型 | 7.9-8.1 | small head, high waist, long legs, slim core | adult |
| G | Mature soft hourglass / 成熟柔软沙漏型 | 7.9-8.1 | structured ribcage, broad pelvis, continuous soft curves | adult |
| H | Divine statuesque / 超模神性型 | 8.3-8.6 | monumental verticality, extremely long legs | adult |
| I | Athletic amazon / 高大战斗亚马逊型 | 7.8-8.2 | strong shoulder girdle, deep ribcage, powerful limbs | adult |
## Archetype Library
### A — Youthful Compact / 小巧幼态型
Use for non-sexual youthful mages, mascots, mechanics, scouts, and compact fantasy fighters.

Structural DNA:
- Slightly larger rounded head and short midface.
- Short natural neck, narrow shoulders, compact ribcage.
- Straight natural waistline; do not build a mature hourglass.
- Narrow stable pelvis, shorter limbs, low center of gravity.
- Small but coherent hands and feet.
Prompt block:
```text
petite youthful anime character, approximately 5.5-to-6-head-tall proportions, slightly larger rounded head, short midface, short natural neck, narrow shoulders, compact ribcage, straight natural waistline, narrow stable pelvis, shorter coherent limbs, compact legs, low center of gravity, modest practical clothing, cute non-sexual design
```
Mandatory exclusions:
```text
no cleavage, no lingerie, no erotic pose, no mature hourglass exaggeration, no oversized bust, no exaggerated hips, no fetish clothing, no sexualized camera angle, not a toddler, no baby anatomy
```
### B — Petite Adult / 小型紧凑成年体
Use for clearly adult petite engineers, medics, hackers, scouts, pilots, and agile professionals.

Structural DNA:
- Mature adult face and adult landmark placement.
- Compact torso with adult shoulders and pelvis.
- Legs near half of total height.
- Compact limbs with proportionate adult hands and feet.
Prompt block:
```text
clearly adult petite woman, compact 6.2-to-6.7-head-tall stylized anatomy, mature adult facial structure, short compact torso, anatomically adult shoulders and pelvis, waist slightly above the midpoint, compact limbs, proportionate adult hands and feet, low center of gravity, agile professional silhouette, not childlike
```
### C — Balanced Cute / 可爱均衡型
Use for idols, maids, nurses, assistants, civilian outfits, light units, and approachable heroines.

Structural DNA:
- Moderately sized anime head and soft adult face.
- Compact but not shortened torso.
- Balanced shoulder-to-pelvis relationship.
- Legs slightly longer than realistic average.
- Soft thighs and naturally tapered calves.
Prompt block:
```text
adult woman, balanced 7-head-tall anime anatomy, soft oval adult face, moderately sized head, compact ribcage, gently defined natural waist, balanced shoulders and pelvis, legs slightly longer than the torso, softly rounded thighs, natural knees, tapered calves, approachable elegant silhouette
```
### D — Standard Heroine / 标准二游女主型
Use as the default for swordswomen, fantasy leads, tactical protagonists, shrine maidens, and general game heroines.

Structural DNA:
- Small but not tiny head and elegant neck.
- Moderate-to-narrow shoulders and compact upper torso.
- Clearly defined natural waist and stable adult pelvis.
- Long femurs, knees slightly below the visual midpoint, tapered lower legs.
Prompt block:
```text
adult heroine, 7.5-head-tall refined anime proportions, small but not tiny head, elegant neck, moderately narrow shoulders, compact upper torso, clearly defined natural waist, stable adult pelvis, long femurs, anatomically placed knees, long tapered lower legs, graceful heroic full-body silhouette
```
### E — Tactical Curve / 战术曲线型
Use for rifle users, machine gunners, cyber-combat characters, fitted tactical uniforms, and rear-view combat poses.

Structural DNA:
- Compact structured ribcage and short waist section.
- Stable pelvis with continuous abdomen-to-hip transition.
- Full upper thighs with readable adductor and glute-to-thigh structure.
- Long femurs and tapered athletic calves.
- Enough body mass and hand size to support weapons.
Prompt block:
```text
adult tactical heroine, 7.8-head-tall stylized anatomy, compact structured ribcage, short waist section, moderate shoulders, strong stable pelvis, continuous abdomen-to-hip transition, full anatomically coherent upper thighs, long femurs, tapered athletic calves, balanced hourglass silhouette, physically capable of carrying heavy weapons
```
Mandatory exclusions:
```text
no impossible wasp waist, no collapsed ribcage, no detached hips, no balloon thighs, no broken lumbar spine, no forced thigh gap, no tiny feet, no pelvis disconnected from torso
```
### F — Elongated Aristocratic / 纤长贵族型
Use for naval-fantasy heroines, formal dresses, long hair, capes, ceremonial uniforms, and large external rigging.

Structural DNA:
- Small refined head, long neck, narrow graceful shoulders.
- Elongated torso and high natural waist.
- Slender but adult pelvis.
- Very long thighs and calves with delicate ankles.
- Keep the central body slim; expand the outer silhouette with costume or equipment.
Prompt block:
```text
statuesque adult woman, elegant 8-head-tall anime proportions, small refined head, long neck, narrow graceful shoulders, elongated torso with a high natural waist, slender but adult pelvis, very long legs, long thighs, long tapered calves, delicate ankles, poised aristocratic posture, slim central body framed by expansive hair, cape, sleeves, skirt or mechanical rigging
```
### G — Mature Soft Hourglass / 成熟柔软沙漏型
Use for mature leaders, queens, teachers, formal characters, heavy naval units, and luxurious silhouettes.

Structural DNA:
- Small elegant head and complete load-bearing ribcage.
- Defined but plausible waist with natural abdominal volume.
- Broad adult pelvis and continuous torso-to-hip curve.
- Softly full hips and thighs while retaining long legs.
Prompt block:
```text
mature adult woman, 8-head-tall soft hourglass anatomy, small elegant head, full natural upper torso supported by a structured ribcage, defined but anatomically plausible waist, natural abdominal volume, broad stable adult pelvis, softly full hips and thighs, smooth continuous torso-to-hip curves, long legs, relaxed confident posture, luxurious feminine silhouette
```
### H — Divine Statuesque / 超模神性型
Use for goddesses, supreme-rarity units, faction leaders, sacred warriors, and monumental key art.

Structural DNA:
- Very small refined head and long neck.
- High-set waist and narrow elongated torso.
- Legs occupy roughly 56-58% of visual body height.
- Extremely long femurs, low elegant knees, slender ankles.
- Requires controlled camera perspective.
Prompt block:
```text
divine statuesque adult heroine, 8.5-head-tall idealized anime anatomy, very small refined head, long elegant neck, high-set waist, narrow elongated torso, extremely long legs occupying about 57 percent of total height, long femurs, low elegant knee placement, slender ankles, controlled graceful curves, monumental feminine silhouette
```
Camera lock:
```text
full-body proportion study, eye-level camera, 70mm equivalent lens, moderate camera distance, minimal perspective distortion, no wide-angle stretching, no extreme low-angle leg exaggeration
```
### I — Athletic Amazon / 高大战斗亚马逊型
Use for heavy weapons, greatswords, powered armor, dragons, valkyries, and physically dominant warriors.

Structural DNA:
- Strong shoulder girdle and developed upper back.
- Deep ribcage and firm natural waist.
- Broad stable pelvis, powerful glutes, quadriceps, and hamstrings.
- Long athletic legs, substantial forearms, hands, and feet.
Prompt block:
```text
tall adult warrior woman, 8-head-tall athletic anatomy, strong shoulder girdle, developed upper back, deep ribcage, firm natural waist, stable broad pelvis, powerful glutes and thighs, readable quadriceps and hamstring structure, long athletic legs, substantial forearms and hands, heroic grounded stance, strong distinctly feminine silhouette
```
## Custom Archetype Blending
Blend at most two primary archetypes unless the user explicitly requests a complex hybrid.

Use this syntax:
```text
[70% primary archetype] + [30% secondary archetype]
```
Examples:
- `D70 + E30`: standard heroine with stronger tactical thighs and shorter waist.
- `F70 + G30`: elongated aristocratic frame with softer mature volume.
- `I70 + H30`: powerful warrior with monumental vertical elegance.
- `B70 + C30`: petite adult with a softer approachable silhouette.
Never blend A with mature sexualized archetypes. For a small adult with mature styling, use B rather than A.
## Function-First Corrections
Apply role constraints after selecting the archetype.
- Heavy weapon: increase hand size, forearm mass, stance width, foot contact, and shoulder stability.
- Speed/agility: reduce distal mass, keep pelvis stable, use compact torso and clear directional lean.
- Ceremonial role: emphasize vertical posture, long neck, controlled gesture, and external silhouette.
- Ranged tactical role: ensure stock-to-shoulder contact, elbow clearance, pelvis balance, and readable trigger hand.
- Sword role: align wrist, guard, blade, shoulders, and center of gravity; avoid floating weapons.
- Large rigging/wings/tails: keep them outside the skeletal body and use them as counterweight, not anatomy.
## Camera Normalization
Before judging or generating proportions, define the camera.
### Neutral proportion sheet
```text
full-body neutral proportion sheet, eye-level camera, 70mm-to-100mm equivalent lens, minimal perspective distortion, orthographic-like presentation, both feet on the same ground plane, head and feet fully visible, plain background
```
### Heroic key art
```text
full-body heroic shot, slightly low camera angle, 35mm-to-50mm equivalent lens, controlled perspective, moderate camera distance, no fisheye distortion, head, feet and weapon fully visible
```
### Prevent leg distortion
```text
natural leg perspective, no ultra-wide lens, no extreme low angle, no oversized foreground feet, no stretched femurs, no excessively low knee placement
```
When analyzing an existing image, separate `designed proportion` from `projected proportion` caused by the lens and pose.
## Prompt Compiler
Compile prompts in this order:
1. Purpose and output type.
2. Character identity and explicit age presentation.
3. Archetype and head-count range.
4. Skeleton: shoulders, ribcage, waist section, pelvis.
5. Volume distribution: abdomen, hips, thighs, calves.
6. Pose, weight distribution, hands, and functional action.
7. Costume and external silhouette elements.
8. Camera, framing, lens, and perspective constraints.
9. Lighting, environment, and rendering style.
10. Fixed constraints and negative constraints.
### Natural-language image model adapter
Use 1-3 coherent paragraphs. Prioritize purpose, main subject, action, location, style, framing, lighting, and the few constraints that must not drift. Repeat only the most critical fixed attributes.
### Tag-based diffusion adapter
Order comma-separated tags from global to local:
```text
quality/style, age/identity, archetype/head count, skeleton, volume distribution, pose/action, costume/equipment, camera/composition, lighting, environment
```
Put anatomical failure modes in a separate negative prompt.
### Image-edit adapter
Use an invariant/change structure:
```text
Change only: [specific body proportion, limb, pose, or camera issue].
Keep exactly the same: [identity, face, hair, costume, colors, lighting, background, composition, accessories].
Target anatomy: [precise corrected BodySpec fragment].
Do not introduce: [new objects, outfit changes, extra limbs, altered expression, unwanted crop].
```
## Standard Output Formats
### Quick Mode
Return:
1. Selected archetype and why.
2. One compact positive prompt.
3. One compact negative prompt.
4. One camera line.
### Full Mode
Return exactly these sections:
```markdown
## Design Intent
## Assumptions and Evidence Level
## BodySpec
## Proportion Rationale
## Positive Prompt — Chinese
## Positive Prompt — English
## Camera and Composition
## Negative Prompt
## Anatomy QA
## Optional Variants
```
### Critique Mode
Return:
```markdown
## Observed Proportion
## Perspective Distortion
## Structural Problems
## Highest-Priority Fixes
## Corrected BodySpec
## Repair Prompt
## Preserve List
```
### Comparison Mode
Compare no more than five archetypes in one table unless the user explicitly requests a full matrix. Include visual effect, role fit, likely failure mode, and camera sensitivity.
## Anatomy Quality Assurance
Score each item `0`, `1`, or `2`.
- Age presentation is internally consistent.
- Head-count and landmark rhythm match the selected archetype.
- Ribcage is present and supports the upper torso.
- Abdomen connects ribcage to pelvis without collapse.
- Pelvis connects continuously to hips and thighs.
- Shoulders, elbows, wrists, hands, knees, ankles, and feet are coherent.
- Pose has a believable center of gravity and ground contact.
- Equipment can be physically held, worn, or balanced.
- Camera perspective does not unintentionally override the intended proportion.
- Costume, hair, tails, wings, and rigging remain separate from anatomy.
- Prompt contains no contradictory age, proportion, pose, or camera instructions.
- Safety gate is satisfied.
Maximum score: 24.
- `22-24`: production-ready.
- `18-21`: usable after targeted refinement.
- `14-17`: revise anatomy or camera before delivery.
- `<14`: rebuild from the skeletal scaffold.
Do not claim a score above 21 when the full body, feet, or critical joints are not visible.
## Common Failure Diagnosis
| Symptom | Likely cause | Correction |
|---|---|---|
| Waist looks severed | ribcage omitted; waist adjective over-weighted | add structured ribcage, natural abdomen, stable pelvis |
| Hips look attached separately | pelvis and femur chain missing | specify continuous torso-to-pelvis and hip-to-thigh transition |
| Legs become absurdly long | high head count plus low-angle wide lens | raise camera, lengthen lens, reduce head count or leg-share instruction |
| Character looks childlike | large head, short limbs, small hands/feet, round face combined | specify clearly adult face, adult shoulders/pelvis, adult hands/feet |
| Petite adult becomes tall | model equates elegance with long legs | lock 6.2-6.7 heads, compact limbs, eye-level lens |
| Tactical body becomes inflated | isolated `wide hips/thick thighs` tags | use stable pelvis, adductor volume, tapered calves, functional stance |
| Athletic character looks masculine by accident | only shoulder/muscle terms used | retain adult pelvis, controlled waist, feminine facial and silhouette cues |
| Weapon floats or bends | grip and action chain unspecified | define hand, wrist, guard, blade path, shoulder, and center of gravity |
| Feet are tiny | beauty tags override structure | require proportionate feet, stable ground contact, visible soles/footwear |
| External gear merges into body | silhouette elements not separated | state body core first; place gear outside and behind the anatomy |
## Worked Examples
### Adult fox swordswoman
```yaml
age_presentation: adult
archetype: D70 + F30
head_count: 7.7
skeleton: {shoulder_width: narrow, ribcage: compact, waist_section: balanced, pelvis: balanced}
volume_distribution: {upper_torso: balanced, abdomen: flat-natural, hips: balanced, thighs: soft, calves: slim}
function: mobility
camera: full-body heroic, slightly low, 50mm equivalent
```
Prompt core:
```text
adult fox swordswoman, refined 7.7-head-tall semi-realistic anime anatomy, small elegant head, narrow shoulders, compact structured ribcage, natural waist, stable adult pelvis, long femurs and tapered lower legs, balanced heroic silhouette; large fox tails expand behind the body as external counterweight, coherent sword grip, full body and blade visible, controlled 50mm heroic perspective
```
### Tactical heavy gunner
```yaml
age_presentation: adult
archetype: E70 + I30
head_count: 7.9
skeleton: {shoulder_width: moderate, ribcage: deep, waist_section: short, pelvis: broad}
volume_distribution: {upper_torso: balanced, abdomen: athletic, hips: powerful, thighs: muscular, calves: tapered-athletic}
function: heavy-weapon
```
Prompt core:
```text
adult tactical heavy gunner, 7.9-head-tall powerful anime anatomy, deep structured ribcage, moderate strong shoulders, short natural waist, broad stable pelvis, powerful continuous glute-to-thigh structure, long athletic legs, substantial forearms, hands and boots, grounded firing stance physically supporting a heavy weapon
```
### Youthful fantasy mage
```yaml
age_presentation: youthful/minor-coded
archetype: A
head_count: 5.7
function: ceremonial
safety: non-sexual only
```
Prompt core:
```text
petite youthful fantasy mage, 5.7-head-tall anime proportions, slightly larger rounded head, short midface, narrow shoulders, compact ribcage, straight natural waistline, narrow stable pelvis, shorter coherent limbs, low center of gravity, layered modest mage clothing, energetic non-sexual pose, ordinary eye-level camera
```
## Final Delivery Checklist
Before responding:
- Confirm the age gate.
- Name the selected archetype or blend.
- State inferred assumptions.
- Keep anatomical instructions internally consistent.
- Lock camera and crop when proportions matter.
- Separate body core from costume/equipment silhouette.
- Include only useful negative constraints.
- Run the 24-point QA.
- Clearly label official facts, visual observations, and inferences.
- Never imply that these ranges are official standards of any referenced franchise.
## Provenance and Maintenance
This skill follows the Agent Skills pattern of YAML metadata plus a Markdown workflow. It is designed as a self-contained playbook with explicit inputs, ordered steps, output formats, guardrails, and final checks.

The archetype ranges are original visual-design abstractions derived from comparative study of stylized female game characters and publicly described official art/setting collections. They are not extracted official measurements. Representative source families include official Azur Lane anniversary art collections and official GODDESS OF VICTORY: NIKKE art and setting books, which document character visuals, costumes, design drafts, weapons, and setting material.

For image prompting, prefer clear subject, purpose, action, location, style, framing, lighting, and explicit invariants. Revise one targeted element at a time when editing.

Version: 1.0.0  
Updated: 2026-07-22
