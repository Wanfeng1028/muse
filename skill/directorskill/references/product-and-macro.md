# Product and Macro

Load this file when the subject of the shot is an object rather than a person — a product spot, a packshot, cosmetics, food, drink, fabric, a texture macro, or any brief where a brand mark or a brand colour has to survive to delivery.

The twelve genre defaults live in the Commercial and product block of [genre-playbooks.md](genre-playbooks.md); this file is the depth behind that block. Lighting theory is owned by [lighting-and-color.md](lighting-and-color.md), word-level vocabulary and negative-list discipline by [prompt-lexicon.md](prompt-lexicon.md), optics and depth-of-field arithmetic by [cinematic-language.md](cinematic-language.md), and failure codes by [failure-modes.md](failure-modes.md). This file links to them and extends them for objects; it does not restate them.

## The governing principle: the light moves, not the camera and not the product

Every other decision in product work is downstream of this one. A product shot needs motion — a static frame reads as a photograph and dies on a feed — and there are exactly three things that can supply it: the camera, the product, or the light. Move the camera and the generator must re-derive the object's geometry from a new angle every frame; move the product and it must re-derive geometry *and* re-render the mark on a turning surface. Both are the two things generators reliably break. Move the light and the object's geometry is a constant for the whole clip: only the specular highlight travels, and a travelling highlight is a gradient, which is the single easiest thing in this medium to get right.

So: **the product is static, the camera is locked, and a large soft source travels across it.** State the travel explicitly — direction, and what the highlight does as it passes.

```text
Before: A luxury lipstick rotating slowly on a marble plinth, cinematic product shot, 8K, elegant.
```

```text
After: Static camera, 100mm macro. A closed lipstick bullet stands upright at frame centre on matte charcoal. Nothing moves except the light: a single large soft source above and camera-left travels slowly right, so its rectangular reflection walks down the polished barrel from cap to base and the engraved band catches once as it passes. End with the highlight resting at the base.
```

The rotation in the "before" is the entire risk of the shot; the "after" has none of it and more motion in the frame. The same trade is worked once more, on a watch, in the Product before/after in [prompt-lexicon.md](prompt-lexicon.md).

Corollary for duration: a static product with no legible face in frame sits in the long band of the duration strategy owned by [ai-video-tool-adapters.md](ai-video-tool-adapters.md) — 8–12 s is affordable, because there is no identity to drift. The moment a hand or a face enters, you are back to 3–4 s.

## Lighting a surface, not a shape

A face is a shape: you light it to describe volume, and the key's direction does that job. A product is a **surface**: what the viewer is buying is how the material behaves under light, and volume is secondary. That is why product work is lit with large soft sources and controlled reflections rather than with a key-and-fill grammar — a hard key gives an object one specular dot and a black side, which describes nothing about the material. A large source gives a broad reflection whose *shape* you can design, and the shape of that reflection is the look.

Ratios are still written lit side : shadow side per [lighting-and-color.md](lighting-and-color.md), but on a product they describe the two sides of the object rather than two sides of a face, and the interesting number is usually the background separation instead.

Light the three material classes differently. Getting this wrong is the most common reason a generated product shot looks like a render.

### Specular — metal, lacquer, gloss, polished plastic, a chrome cap

You are not lighting the object. You are lighting **what the object reflects**. A polished surface is a mirror, so its brightness at any point is the brightness of whatever sits at the mirror angle from there. Design the reflected field: a large bright panel positioned so its reflection lands where you want the highlight, and black negative fill where you want the surface to go dark so the silhouette reads against the background.

Prompt it by naming the reflection, not the fixture: `a single large soft source above and camera-left, its rectangular reflection visible as a vertical highlight running down the polished barrel; the camera-right edge held dark against a black surround so the silhouette reads`.

### Transparent — glass, liquid, gel, a serum bottle

Glass is invisible; what you see is the background through it and the edges catching. So you light the background and the edges, never the object. Two schemes, and you must pick one:

- **Bright field.** A lit panel behind the subject. The glass reads as clean dark edge lines against a bright ground. Clinical, catalogue, honest about the liquid's colour.
- **Dark field.** A dark background with narrow bright strips out of frame at left and right raking the edges. The glass reads as bright outlines on black. Premium, dramatic, and the liquid needs its own small source behind it or it goes to black with everything else.

Prompt it: `dark-field lighting, two narrow white strips out of frame left and right raking the bottle's edges so the glass reads as two bright vertical lines against black; a small soft source 40 cm behind lifts the liquid to a readable amber`.

### Matte — powder, cream, fabric, paper, unglazed ceramic

There is no specular to shape, so texture only appears when light **rakes** across the surface at a shallow angle and every grain, ridge and fibre casts a short shadow. Frontal or soft overhead light on a matte surface returns a flat colour patch, which is exactly what a generator produces by default.

Prompt it: `a hard source raking in from camera-left at a shallow angle to the card, so the ridges the applicator left cast short shadows to the right and the stroke reads as relief rather than as a flat patch; no fill on the shadow side`.

### Reflection management

Anything glossy will show the room. On a set that means flagging out the rig and the crew; in generation it means the model *invents* a reflection, and what it invents is a softbox, a window grid, a photographer, or a second copy of the product. Handle it from both directions: say positively what is reflected (`the only thing reflected in the cap is a single soft white rectangle`) and negative the specific instances (`no lighting rig reflected, no photographer reflected, no window grid in the reflection`). Instances, never categories — the category form is the mechanism behind F8.

## Macro reality

**Working distance.** A 100mm macro at life size sits roughly 15 cm from the subject, and the lens barrel then occupies the space the frontal light was going to come from. This is not a detail: it means a macro shot is lit from the side, from behind, or from a shallow raking angle, and a prompt asking for "macro close-up, softly lit from the front" describes a setup that cannot exist. The model resolves the impossibility by inventing a look, which is where plastic-looking macro comes from.

**Depth of field collapses to millimetres.** Using the arithmetic in [cinematic-language.md](cinematic-language.md) — total depth scales as `(distance² × f-number) / focal-length²` — a 100mm at f/2.8 from 0.3 m holds about **1.5 mm**. Stopping down to f/11 buys about 6 mm. A lipstick bullet is 8–10 mm across; a coffee bean is 10 mm; a watch crown is 5 mm. At f/2.8 you cannot hold the whole object, and no amount of prompt language changes that. Distance is the strongest term in the expression, so backing off and cropping in buys depth far faster than stopping down.

**Focus stacking, and what substitutes for it.** Stills photography solves this by shooting ten to forty frames at stepped focus and merging them. Video cannot, and generation cannot at all. The substitutes, in order:

1. Move back and crop. Doubling the subject distance quadruples the depth.
2. Lay the product's readable face nearly parallel to the sensor plane, so the whole face lives in one plane and there is nothing behind it that must be sharp.
3. Accept one sharp plane and design the shot around it — decide which millimetre the viewer must read, and let the rest go.
4. Composite. Shoot or render the product as a stacked still and drop it into a generated environment.

**State which single plane is sharp.** A macro prompt that does not name the sharp plane gets one of two defaults: everything crisp, which looks like a render, or a general blur with spurious circular highlights. Name the plane and the failure of the planes around it — `focus plane on the front face of the barrel; the surface 30 mm behind is unreadably soft; no circular highlights` — following the depth-of-field prompting note in [cinematic-language.md](cinematic-language.md).

## Brand and colour fidelity

A brand hue is a **discrete** constraint — one hex value, signed off — imposed on a generator that samples from a continuous distribution. It will land near the value, it will never land on it, and it will not land in the same place twice, which means a spot generated shot-by-shot fails at the cut even when every individual clip looks acceptable. The same is true of a mark's proportions. Treat both as things you supply, not things you request.

The practical hierarchy, highest stakes first:

1. **Generate the environment and the light; composite the real product.** The hero, the packshot, and anything with brand sign-off attached. The product comes from the brand's own asset kit or from a stills shoot; the generator only ever makes the world behind it and the light falling on it.
2. **Shoot the product; generate the environment.** One soft source, a phone or any camera, and a clean plate is enough for a packshot. Cheaper than it sounds and it removes the whole risk class.
3. **Generate both — lowest stakes only.** A texture abstraction, a defocused bottle in the background, a mood plate. Legitimate when nothing colour-critical and no legible mark is in frame. Never as the hero.

Never accept a generated hue as final; grade the composite to the hex instead of asking the model for it. This is the brand-colour cause under F1 and the hand-plus-branded-product entry in the irreducible list, both in [failure-modes.md](failure-modes.md) — flag the hero asset as composite-only at Step 1 intake, before anything is generated. Where the product recurs across shots, its mark, hue and proportions belong in the continuity bible alongside character identity strings ([continuity-bible.md](continuity-bible.md)).

## Text and logo

Never ask a generator for readable type. Not the brand name, not the shade number, not the claim, not the ingredient list. Current models produce type-shaped marks that fail on inspection and fail differently in every clip, and the failure is the single most visible tell in the medium. Three workarounds:

1. **Keep it out of frame.** Shoot the angle where the mark is not visible, crop past it, or turn it away — `the label is turned away from camera` is a positive instruction the model can execute.
2. **Composite it.** Generate a plate with a clean, correctly lit blank area at the right perspective and lay the real logo or type over it in the edit. An end card is a graphics job, not a generation job, and it always was.
3. **Occlude or imply.** A hand, steam, shallow focus or motion blur across the mark. Cheapest, weakest, and only defensible in a non-hero shot.

Do not ask for both directions at once: `no text` in the negatives and a legible logo in the positives are the same request twice, and the model will honour whichever it weights higher.

## The shot grammar of a product spot

Six shots. Most spots use four of them. The durations below are the hold each shot needs to read at a 30 s runtime; at 15 s and 6 s the second-by-second layouts further down govern instead, and every hold compresses to fit them.

| Shot | What it must show | Lens and light | Duration | AI risk | Generate it? |
|---|---|---|---|---|---|
| Hero | The product whole and unambiguous, in one readable silhouette | 85–100mm at its own eye level; large soft source plus one edge kicker; the light travels | 3–5 s | Proportion and mark drift | Environment yes, product composited |
| Texture macro | The material fact the claim rests on — the cream's pull, the powder's grain, the brushed metal | 100mm macro; hard raking source; one named sharp plane | 3–4 s | Invented geometry, spurious bokeh balls | Yes — the best generated shot in the category, provided no mark is in frame |
| Application / use | The product doing its job, on a body or a surface | 50–85mm; soft frontal on skin, raking on the surface | 3–4 s | Highest in this file: fine manipulation, brand mark, and a face all compound | Prefer to shoot. If generated: hand enters already in position, contact under 1.5 s, contact happens on the cut |
| Before / after | The same frame twice with exactly one variable changed | Locked frame, identical light both sides | 2–3 s per side | The model changes everything else too — angle, exposure, face | Only as a first/last-frame pair or two approved stills. Never as one continuous clip |
| Packshot | The product with its mark legible, on brand ground | 100mm, product eye level, controlled specular, no travel | 2–3 s hold | Mark and hue, both fatal | No. Shoot or composite |
| End card | The mark, the claim in type, the call to action | No camera. This is a layout | 2–3 s | Type | No. Graphics in the edit |

## Five material families

### Food

**Breaks:** cut surfaces and steam. A sliced tomato regenerates its seeds every frame, a crumb structure reorganises itself, and models invent steam that rises from nothing and drifts in a direction the frame does not support. **Substitution:** keep the food whole and uncut, put all the motion in the steam, and name the steam's origin point and drift direction. Shoot the food and generate the kitchen behind it if the food is the claim.

### Liquid

**Breaks:** the pour. A pour is a fluid simulation; generators approximate it with a smear that changes volume, detaches from the bottle mouth, and fills a glass whose level never rises. **Substitution:** cut on the pour — bottle tilting, then the filled glass. If it must be shown, keep it under one second, vertical, at a size where the stream is a few pixels wide, and never show it landing.

### Cosmetics

**Breaks:** the shade and the bullet. The colour *is* the product, so a drifted hue is a wrong product; and the bullet's geometry — the slant, the chamfer, the cap seam — regenerates every clip. **Substitution:** composite the real bullet, and generate the swatch. A cream stroke on a matte card under raking light is the most reliable generated shot in the whole category, and it carries the shade honestly as long as you grade it to the brand hex afterwards rather than asking the model to hit it.

### Fabric

**Breaks:** drape and weave. Seam placement, pattern repeat and the way cloth folds are re-derived every clip. **Substitution:** hold the fabric still and travel the light across it. If it must move, use wind or one slow lift, 2–4 s, one garment, and never a fast turn — the Fashion playbook in [genre-playbooks.md](genre-playbooks.md) has the rest.

### Hard goods

**Breaks:** anything that articulates. A clasp, a screw thread, a sliding lid, a hinge — the model opens it the wrong way, grows an extra part, or passes one solid through another. **Substitution:** show the mechanism as two states on either side of a cut, never as one continuous articulation.

## Vertical spot structures

Both layouts assume the delivery-format precedence rule at the top of [genre-playbooks.md](genre-playbooks.md): vertical outranks the commercial's 30-second runway, so the hook collapses to the front and the claim moves forward with it. Safe margins per the vertical section of [cinematic-language.md](cinematic-language.md) — nothing load-bearing in the top ~12% or bottom ~20%.

**6 seconds (pre-roll, feed):**

| Time | Beat | On screen |
|---|---|---|
| 0.0–0.8 s | Hook | The product already in frame at the largest size it will ever be, light already travelling. No build-up, no logo yet |
| 0.8–2.5 s | The one visible fact | Texture macro or a single application stroke. This is the entire demonstration; there is no second one |
| 2.5–4.5 s | Claim | The claim as a picture, type composited over it; product returns to hero size |
| 4.5–6.0 s | End card | Mark, claim line, call to action, held still |

**15 seconds (feed, 短视频):**

| Time | Beat | On screen |
|---|---|---|
| 0.0–1.5 s | Hook | The problem or the change, before the viewer decides. Product visible by 1.0 s |
| 1.5–3.0 s | First visible change | Something is demonstrably different from second zero. This is the retention checkpoint |
| 3.0–7.0 s | Demonstration | Two or three shots — texture macro, application, result — cutting every 1.2–2 s |
| 7.0–9.0 s | Second visible change | The before/after, or the result restated at a new size |
| 9.0–12.0 s | Claim | Said once and shown once, together |
| 12.0–14.0 s | Packshot | Product with the mark legible, on brand ground |
| 14.0–15.0 s | End card and loop | A last frame that answers the first, so the loop point gives a reason to stay |

## What to shoot instead of generate

The honest table. Read the middle column first.

| The shot | Generate it? | Do this instead | Why |
|---|---|---|---|
| Environment, set, backdrop, surface | Yes | — | No mark, no hue, no geometry that must be held |
| Steam, smoke, dust, atmosphere, sparkle | Yes | — | Cheap, and models are good at it |
| Texture macro, no mark in frame | Yes | — | Material behaviour under raking light is what generation does best |
| Light travelling across a static product | Yes, as the surround | Composite the product into it | Motion with zero geometry risk |
| A face reacting, product out of frame | Yes | — | An ordinary performance shot; 3–5 s per the duration strategy |
| Before/after in one frame | As a first/last-frame pair only | Two approved stills | A continuous clip changes the other variables too |
| Product whole with the mark legible | No | Shoot or composite | Mark proportions are a discrete constraint |
| Brand hue as the point of the shot | No | Shoot, or grade a composite to the hex | F1, brand-colour cause |
| Hand applying or operating the product | Avoid | Shoot it | Compounds fine manipulation, mark, and often a face |
| Pour, splash, articulation, mechanism | Avoid | Shoot it, or cut around it | Physics the model approximates rather than simulates |
| Readable type of any kind | Never | Graphics in the edit | Type-shaped marks fail on inspection, differently every clip |

Budget note: the shots you do generate here are mostly no-face, which puts them in the low retry bands. Plan against the per-band figures in [production-workflow.md](production-workflow.md) — planning guidance, not measurement — and hold every keyframe to the gate before spending a video generation. Handle lengths are owned by [editing-and-assembly.md](editing-and-assembly.md).

## Worked prompts

Full-description shape (S2) throughout; for the slot order and the shape definitions see [ai-video-tool-adapters.md](ai-video-tool-adapters.md), and for the fillable form [../assets/video-prompt-template.md](../assets/video-prompt-template.md). Negatives name instances only, kept inside the combined ceiling in [prompt-lexicon.md](prompt-lexicon.md).

### 1. Lipstick hero, light travelling — English

```text
Static camera, 100mm macro equivalent, product at its own eye level, 9:16. A closed lipstick bullet stands upright at frame centre on a matte charcoal surface, occupying the middle third of frame height. Nothing moves except the light: a single large soft source above and camera-left travels slowly right across the shot, so its rectangular reflection walks down the polished barrel from cap to base, and the engraved band at the base catches once as it passes. The camera-right edge of the barrel stays dark against a black surround so the silhouette reads. Focus plane on the front face of the barrel; the surface 30 mm behind is unreadably soft. End with the highlight resting at the base, the frame otherwise identical to the first frame. No hand in frame, no lighting rig reflected in the barrel, no printed text, no second lipstick, no circular highlights.
```

### 2. 同一颗镜头的中文原生写法

```text
固定镜头，100mm 微距，产品与自身视平线齐，9:16 竖幅。一支合盖口红竖立在画面中央的哑光炭灰台面上，占画面高度中间三分之一。全片只有光在动：一盏大面积柔光源从左上方缓慢向右移动，矩形反光沿抛光管身从盖端走到底端，经过底部刻纹时闪一次。管身右缘始终压暗，衬在黑色环境里让轮廓立住。对焦面在管身正面，其后 30mm 处完全虚化。结束时高光停在底端，画面与首帧一致。画面中没有手，管身上不出现灯具倒影，没有文字，没有第二支口红，没有圆形光斑。
```

Written native rather than translated word by word, per the Chinese-UI rule in [prompt-lexicon.md](prompt-lexicon.md). The bullet itself is composited in afterwards; what this prompt is really buying is the surface, the travel of the light, and the black surround.

### 3. Cream swatch, matte raking light — the texture macro

```text
Static camera, 100mm macro, top-down, 9:16. A single stroke of cream lipstick lies across a matte white card, running from the upper third of frame to the lower third. A hard source rakes in from camera-left at a shallow angle to the card, so the ridges the applicator left cast short shadows to the right and the stroke reads as relief rather than as a flat colour patch. Across the shot the source moves 20 cm further left: the shadows lengthen and the ridged texture becomes more pronounced. Card, stroke and camera do not move. Focus plane on the stroke's near edge. End on the longest shadows. No hand, no applicator, no printed text, no lighting rig reflected, no glitter.
```

Grade the stroke to the brand hex in the edit. Do not ask for the shade by name.

### 4. Glass serum bottle, dark field

```text
Static camera, 85mm, product at its own eye level, 9:16. A clear glass serum bottle stands centre frame against black. Dark-field lighting: two narrow white strips out of frame at left and right rake the bottle's edges, so the glass reads as two bright vertical lines and the body stays dark and transparent. Behind the bottle and 40 cm back, a small soft source brightens slowly across the shot, so the liquid inside lifts from black to a readable amber and the meniscus becomes visible. Nothing else changes; bottle and camera are locked. Focus plane on the front glass. End with the liquid fully lit and the two edge lines unchanged. No label, no printed text, no hand, no lighting rig reflected in the glass, no bubbles appearing.
```

The label is deliberately absent, not forbidden by accident: this plate is built to have a real label composited onto it.
