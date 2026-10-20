# Prompt Recipes

Use this reference when producing model-ready prompts, variants, negative prompts, or repair prompts.

## Universal Prompt Structure

```text
[Scene type and core subject], [one-sentence thesis or visual tension]. [Composition and camera]. [Spatial layers and scale anchors]. [Architecture/landscape/material logic]. [Cultural or worldbuilding details]. [Lighting, color, atmosphere, weather]. [Human-use details]. [Medium/rendering instruction]. [Aspect ratio or model-specific parameters if requested].
```

## Full Art Direction Prompt

```text
Cinematic environment concept art of [specific place], where [force A] collides with [force B], creating [emotion]. [Camera and composition], with [foreground element] framing [midground focal subject] and [background scale]. The space is designed around [architectural/landscape logic], using [materials] with [aging/weathering behavior]. Cultural details follow [specific design rule], shown through [2-3 grounded motifs]. Lighting is motivated by [source], with [color strategy], [atmosphere], and [weather effect]. Include human-scale evidence of use: [details]. Refined production design, coherent spatial depth, premium but restrained detail, no random ornament.
```

## Photoreal Scene Prompt

```text
Ultra-realistic cinematic scene photograph of [specific place and subject], [time/season/recent event]. [Camera position] with [lens feel], [foreground/midground/background]. Materials include [specific materials] with believable wear, moisture, dust, scratches, repairs, and scale. Lighting comes from [motivated sources], creating [contrast/color mood]. The scene feels lived-in through [human-use details]. Natural atmospheric depth, realistic architecture, physically plausible light, high-end production design.
```

## Game Environment Key Art Prompt

```text
AAA game environment key art of [location], designed for [gameplay/emotional function]. Strong readable silhouette, clear traversal path, [foreground gameplay clue], [midground hero landmark], [background worldbuilding]. Architecture uses [modular/period/cultural logic], with [materials] and [damage/maintenance pattern]. Lighting guides the player toward [focal destination]. Add props that imply [faction/economy/ritual]. High visual clarity, layered depth, memorable landmark design.
```

## Animation Background Prompt

```text
Animated feature-film background painting of [location], [emotional tone]. Clear graphic shapes, elegant value grouping, readable silhouettes, [composition]. The setting combines [design grammar] with [material/color logic]. Use [lighting] and [atmosphere] to create depth while preserving simple shapes. Include [small human-scale details] without clutter. Painterly but precise, warm production design, strong mood.
```

## Luxury / Commercial Scene Prompt

```text
Premium commercial scene design for [brand/product/context], set in [specific place]. The scene communicates [brand values] through [spatial design], [materials], and [lighting]. Composition places [product/hero area] as the clean focal point with generous negative space. Use [surface finish], [architectural rhythm], [accent color], and [practical set dressing]. Refined, expensive, tactile, restrained, no clutter, no fake text.
```

## Repair Prompt

Use when improving a weak prompt or image:

```text
Revise the scene to make [focal idea] unmistakable. Strengthen [composition issue] by [specific change]. Replace generic decoration with [grounded design rule]. Make lighting physically motivated from [source]. Add scale through [human/object anchor]. Reduce clutter and preserve [negative space/focal silhouette]. Keep [elements that worked].
```

## Negative Prompt Patterns

Use only what applies:

```text
avoid generic fantasy/sci-fi clutter, random cultural mashup, incoherent architecture, impossible lighting, flat perspective, no scale reference, unreadable focal point, overdecorated surfaces, fake readable text, plastic materials, over-sharpened details, oversaturated colors, floating objects, inconsistent shadows, theme-park stereotypes
```

## Variant Set

When the user asks for options, produce 3-4 variants with one axis changed:

- Spatial grammar: intimate courtyard, monumental axis, labyrinth market, vertical megastructure.
- Lighting: overcast realism, backlit reveal, chiaroscuro, practical neon/firelight.
- Cultural synthesis: dominant Eastern space with Western material accent, dominant Western civic order with Eastern threshold ritual, local vernacular with near-future infrastructure.
- Mood: sacred quiet, tense survival, luxury calm, decayed grandeur, everyday warmth.

Keep the thesis constant unless the user asks for new concepts.
