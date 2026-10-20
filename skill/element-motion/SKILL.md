---
name: element-motion
description: >-
  Shapes, orbs and particles that move in the frame — the element layer of motion graphics.
  Concentric ring ripples, floating outlined circles at varied depth (bokeh), a small ring that
  blooms into a big glow orb, scattered circles converging to a focal point, two circles that
  stretch and fuse (metaball), morphing solid gooey blobs, sparkle/twinkle bursts, self-drawing
  line icons, and wobbly doodle connectors. Use when adding animated shapes/particles behind or
  around content, giving a scene kinetic texture, or matching a reference's circle/orb/particle
  motion. Triggers: "floating circles / rings", "glowing orb", "particles", "ripples", "metaball
  / liquid merge", "gooey blobs", "sparkle", "draw-on icon", "hand-drawn connector line".
---

# Element Motion (shapes · orbs · particles)

Family **C** of the **motion-graphics** super-skill. Drop-in building blocks live in the
shared library — from any skill in this plugin: `../motion-graphics/assets/motion.css` +
`motion.js`. Every effect scales by `--R` and is driven by **logical time `t`**, so it survives
slow-clock capture (see `smooth-render`).

```html
<link rel="stylesheet" href="../motion-graphics/assets/motion.css">
<script src="../motion-graphics/assets/motion.js"></script>
```

## Moves
| # | Name | Looks like | Build |
|---|---|---|---|
| C1 | **Ring Ripples** | concentric rings expand outward | `.tm-rings + mkRings` |
| C2 | **Floating Rings (Bokeh)** | outlined circles drift at varied depth, some soft | `.tm-bokeh + tmBokeh` |
| C3 | **Orb Bloom** | a bright ring blooms into a big soft glow orb | `.tm-orb + tmOrb` |
| C4 | **Converge** | scattered circles drift inward to a focal point | `tmConverge` |
| C5 | **Metaball Merge** | two circles stretch & fuse into a capsule | `.tm-meta + tmMeta` |
| C6 | **Gooey Blobs** | solid rounded shapes morph & drift | `.tm-goo` |
| C7 | **Sparkle Burst** | a 4-point star twinkles/pops | `.tm-spark` |
| C8 | **Line-Draw Icon** | an icon strokes itself on | `.tm-draw + tmDraw` |
| C9 | **Doodle Connector** | wobbly hand-drawn line links two elements | `.tm-draw on a jittered path` |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
