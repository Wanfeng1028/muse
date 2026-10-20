# Negative Prompt Hygiene For IM2

Use this reference when an IM2 prompt contains `Avoid`, `Negative prompt`, `no ...`, old failed-output descriptions, or a long blacklist.

## Principle

Negative words are not neutral. They still put concepts into model attention. A negative block should suppress broad failure classes, not teach the model a gallery of unwanted things.

Use this order:

```text
positive visible target -> material/lighting proof -> clean rendering layer -> compact current-risk avoid block
```

Never use this order:

```text
old failure memory -> long no-list -> weak positive prompt
```

## Keep

Good negatives are broad, reusable, and likely:

- artifact class: `ghost texture`, `latent artifacts`, `hidden watermark-like marks`, `repetitive micro-pattern noise`;
- anatomy/structure failure when people or creatures are present: `malformed anatomy`, `extra fingers`, `melted hands`, `asymmetric eyes`;
- material fake-look: `uniform plastic gloss`, `pasted-on texture`, `milky reflections`, `dirty AO halos`;
- exposure failure: `clipped highlights`, `crushed blacks`, `muddy shadows`;
- composition clutter: `extra subjects`, `unrequested props`, `stray text`, `watermark`.

## Remove Or Convert

Bad negatives are old, specific, or more vivid than the positive prompt:

- old project props, enemies, weapons, locations, colors, palettes, failed styles;
- `not like before`, `no longer`, `instead of the previous image`, `do not make it like X`;
- a forbidden noun that is not naturally likely in the target shot;
- repeated versions of the same constraint;
- negatives that contradict the positive style or material layer.

Conversion rule:

```text
bad negative -> positive visible state + optional broad failure avoid
```

Examples:

| Risky negative | Better positive lock | Optional avoid |
|---|---|---|
| `no blur` | `sharp hero silhouette, clean intentional depth of field` | `no global blur` |
| `no clutter` | `clean negative space, organized background shape groups` | `no background clutter` |
| `no extra people` | `single clearly framed subject, empty surrounding space` | `no extra subjects` |
| `no weapon` | `both hands visible and empty, no held objects` | omit unless weapons are likely |
| `no old blue-purple shadow glow` | `neutral shadow color with controlled cool rim light only on edges` | `no color drift` |
| `no dirty face marks` | `clean natural skin planes, subtle pores only where visible` | `no facial artifact marks` |
| `no text everywhere` | `plain background with protected blank areas` | `no stray text or watermark` |

## IM2 Avoid Block Templates

### Universal clean image

```text
Avoid: ghost texture, latent artifacts, hidden watermark-like marks, repetitive micro-pattern noise, low-contrast residual textures, dirty texture buildup, pasted-on texture.
```

### Portrait / character

```text
Avoid: malformed anatomy, melted hands, extra fingers, asymmetric eyes, facial artifact marks, waxy skin, dirty pore noise, ghost texture, latent artifacts, stray text or watermark.
```

### Dark scene

```text
Avoid: muddy shadows, crushed blacks, noisy bokeh, background artifacts, dirty AO halos, ghost texture, latent artifacts, hidden watermark-like marks.
```

### Product / poster

```text
Avoid: faux watermark, hidden lettering, stray text unless requested, clipped highlights, milky reflections, pasted-on texture, dirty texture buildup, random micro-pattern noise.
```

### Dense fantasy / concept art

```text
Avoid: repeated micro ornaments, random tiny symbols, dirty texture buildup, hidden marks, ghost texture, latent artifacts, muddy background noise, identical roughness across all surfaces.
```

## Retry From A Dirty Output

Do not write: `remove the dirty marks from the previous image`.

Write:

```text
Regenerate the same concept as a clean-slate image: [current subject, pose, composition, style, palette]. Preserve the main design and mood. Rebuild the rendering with clean material separation, balanced detail, realistic detail only, controlled highlights, smooth background tones, and minimal repetitive patterns.
Avoid: ghost texture, latent artifacts, hidden watermark-like marks, dirty texture buildup, repeated micro-pattern noise, muddy shadows, low-contrast residual textures.
```

## Final Check

Before finalizing, answer:

1. Is the desired image stronger than the avoid block?
2. Does every negative target a current likely risk?
3. Did any negative mention an old failure or project-specific noun?
4. Can a negative be replaced with a positive visible state?
5. Is the avoid block short enough to avoid attention dilution?
