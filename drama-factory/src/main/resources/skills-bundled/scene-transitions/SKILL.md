---
name: scene-transitions
description: >-
  Scene-to-scene transitions for motion-graphics videos — the glue between beats, beyond a plain
  crossfade. A solid shape wipes across to swap scenes, the next scene is revealed through an
  expanding circle (iris), an outgoing scene is pushed out by an incoming shape, a shape in scene
  A morphs into an element of scene B (match-cut), an organic blob mask grows to swap (liquid
  wipe), or content cross-dissolves while a shared gradient persists. Use when cutting between
  scenes feels abrupt or generic, or matching a reel's slick transitions. Triggers: "scene
  transition", "wipe between scenes", "circle/iris reveal", "match cut", "liquid transition",
  "how to transition between sections".
---

# Scene Transitions

Family **F** of the **motion-graphics** super-skill. Drop-in building blocks live in the
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
| F1 | **Shape Wipe** | a solid shape sweeps across to swap scenes | `.tm-wipe` |
| F2 | **Iris Reveal** | next scene revealed through an expanding circle mask | `.tm-iris (clip-path)` |
| F3 | **Mask Push** | outgoing slides out as a shape pushes incoming in | `paired translate` |
| F4 | **Match-Cut Morph** | a shape in scene A becomes an element of scene B | `shared element, animate size/pos` |
| F5 | **Liquid Wipe** | an organic blob mask grows to swap scenes | `.tm-goo as clip-path` |
| F6 | **Dissolve-over-Gradient** | content cross-fades while the shared gradient persists | `.tm-sc gating + .tm-gradbg` |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
