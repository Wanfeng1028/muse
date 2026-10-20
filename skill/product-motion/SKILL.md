---
name: product-motion
description: >-
  Ways to show the product in a motion-graphics video — composition moves. App icons ring a
  central hub and connect (integrations orbit), icon bubbles float in space (constellation), a
  product screenshot rises/tilts in on a gradient (screen reveal), person/logo social-proof chips
  slide in, and tilted cards fan out in perspective. Use when presenting integrations, an
  ecosystem, a dashboard/UI screenshot, testimonials, or a set of feature cards. Triggers:
  "integrations orbit / hub and spoke", "app icons around a logo", "reveal the product
  screenshot", "avatar chips / social proof", "cards fan out", "show the dashboard".
---

# Product & Composition

Family **E** of the **motion-graphics** super-skill. Drop-in building blocks live in the
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
| E1 | **Integrations Orbit** | app icons ring a center hub + connect | `.tm-orbit + tmOrbit` |
| E2 | **Icon Constellation** | app-icon bubbles float/scatter in space | `tmOrbit(scatter)` |
| E3 | **UI Screen Reveal** | a product screenshot rises/tilts in on a gradient | `.tm-screen` |
| E4 | **Avatar Chips** | person/logo chips slide in as social proof | `.tm-chips` |
| E5 | **Card-Stack Fan** | tilted cards fan out in perspective | `.tm-fan` |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
