---
name: aesthetic-presets
description: >-
  Whole-scene aesthetic presets for motion-graphics videos — combinations of background + element
  + type that read as one recognizable style. Isometric UI (planes on a 30° grid, floating, long
  shadow), collage/cutout (flat color + photo cutouts + torn-paper stickers + doodle connectors +
  halftone + timeline), Apple-minimalist (huge negative space, one shape/word, slow eases, thin
  type), crypto/neon-glow (near-black + starfield + neon edges + spinning 3D token), and
  dashboard-reveal (UI window rises in, charts grow, counters tick). Use when you want a named
  look for a whole scene/video, or matching a specific reference style. Triggers: "isometric
  style", "collage / cutout animation", "Apple-style minimalist", "crypto / web3 neon look",
  "dashboard reveal", "make it look like [that style]".
---

# Aesthetic Presets (whole-scene looks)

Family **H** of the **motion-graphics** super-skill. Drop-in building blocks live in the
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
| H1 | **Isometric UI** | UI planes on rotateX(55) rotateZ(-45), layered + floating | `.tm-iso .plane` |
| H2 | **Collage / Cutout** | flat bg + cutouts + torn-paper stickers + doodle + halftone + timeline | `.tm-sticker + .tm-halftone + .tm-draw + .tm-timeline` |
| H3 | **Apple-Minimalist** | huge negative space, ONE shape/word, slow eases, thin type | `.tm-min` |
| H4 | **Crypto / Neon-Glow** | near-black + starfield + neon edges + spinning 3D token | `.tm-neon + .tm-spin3d + .tm-stars` |
| H5 | **Dashboard Reveal** | UI window rises in, then charts grow, counters tick, rows deal | `.tm-screen + family G` |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
