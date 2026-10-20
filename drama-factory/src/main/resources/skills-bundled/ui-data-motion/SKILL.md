---
name: ui-data-motion
description: >-
  UI and data animation for product-demo motion graphics — the mechanics of a SaaS/dashboard
  reveal. Chart bars grow from the baseline, an SVG line/area draws itself on, a number rolls up
  to its value (odometer counter), UI cards deal into place, a toggle/tab slides between states,
  a cursor drives a real UI (click → state change), a notification pops in, and a timeline
  playhead slides through dates. Use when animating a dashboard, chart, metric callout, feature
  toggle, or a cursor-driven product walkthrough. Triggers: "animate the chart / bars grow",
  "draw the line graph", "counter / number ticks up", "cards deal in", "toggle switch animation",
  "cursor demo of the UI", "notification pop", "timeline scrubber".
---

# UI & Data Motion

Family **G** of the **motion-graphics** super-skill. Drop-in building blocks live in the
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
| G1 | **Bar-Grow** | chart bars rise from baseline, staggered | `.tm-bar + --h` |
| G2 | **Line-Draw** | an SVG line/path draws on, area fills under | `.tm-draw + tmDraw` |
| G3 | **Counter-Tick** | a number rolls up to its value (odometer) | `tmCount` |
| G4 | **Card Deal** | UI cards slide/stack into place in sequence | `.tm-deal` |
| G5 | **Toggle Switch** | a pill/toggle slides between states | `.tm-toggle` |
| G6 | **Cursor Demo** | a cursor drives a real UI (click → state change) | `tmCursor + state toggles` |
| G7 | **Notification Pop** | toast/badge pops in with a spring | `.tm-punch variant` |
| G8 | **Timeline Scrubber** | a date axis with a playhead sliding through years | `.tm-timeline + tmScrub` |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
