---
name: backgrounds-gradients
description: >-
  Living backgrounds & moving gradients for motion-graphics videos — the layer that makes a frame
  feel alive instead of a static slide. Color-arc gradient that shifts per scene with drifting
  blobs, a soft mesh light-wash that glides across, blueprint line grids, dot-matrix fields,
  glowing neon curved paths with travelling light-dots, starfields, and grain/paper/paint texture
  overlays. Use when a scene looks flat or slide-like, when adding a moving gradient behind the
  whole piece, or matching a reference reel's animated background. Triggers: "moving gradient
  background", "gradient that shifts through the video", "make the background alive", "mesh
  gradient wash", "blueprint grid", "dotted background", "neon lines", "starfield", "film grain /
  texture overlay".
---

# Backgrounds & Gradients

Family **B** of the **motion-graphics** super-skill. Drop-in building blocks live in the
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
| B1 | **Color-Arc + Blobs** | palette shifts per scene; soft blobs drift | `.tm-gradbg + tmGrad + tmDrift` |
| B2 | **Mesh Wash** | a soft colored light-sweep glides across the frame | `.tm-mesh + tmMesh` |
| B3 | **Blueprint Grid** | faint technical line grid | `.tm-grid` |
| B4 | **Dot Matrix** | faint dotted grid field | `.tm-dots` |
| B5 | **Neon Path + Travellers** | glowing curved lines with light-dots running along them | `.tm-path + tmTravel` |
| B6 | **Starfield Drift** | tiny dots twinkle + parallax | `.tm-stars + tmStars` |
| B7 | **Texture Overlay** | grain / paper / halftone / paint-wash over the frame | `.tm-grainwrap / .tm-paint / .tm-halftone` |
| B8 | **Colour Flow Track** | the whole frame walks from one chapter's colour to the next, with no visible cut | `C(t)` track + three drifting fields — see below |
| B9 | **Mark-Driven Ground** | rings, a lit arc and a landing glow built around the element travelling through the frame | the `mark-driven-ground` skill |

## Rules that make these render-safe
- **Never `filter:blur()` / `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
  them and capture drops to ~5 fps. Softness is faked with radial-gradient falloff / translucent
  fills / directional text-shadow smears.
- Drive every time-based helper by your render clock's **logical time `t`**, never wall-clock.

## Colour flow track + smooth fields
Family B's other moves change palette **per scene** — the gradient is one colour, then it is another.
That works, but every change is a cut you can see. The alternative is to make the colour a
*continuous function of time* and let the frame arrive at each chapter's colour before the chapter
does.

**The track.** Author a piecewise-linear colour walk `C(t)` through `[time, colour]` pairs placed at
the **chapter midpoints**, not at the boundaries — so each chapter is fully its own colour in the
middle and is already becoming the next one at its end:
```js
const TRACK = [[0,'#c4b5fd'],[46,'#a5c8ff'],[75,'#3b7bf0'],[98,'#c24fc0'],
               [117,'#e06ab8'],[158,'#8c57ff'],[192,'#2bb39a'],[206,'#c4b5fd']];
// C(t): find the pair after t, lerp the two colours per sRGB channel by the position between them
```
**Three fields, one track — lead / current / lag.** Do not paint the whole background `C(t)`: that
is still one colour, just smoothly changing, and it reads as a wash of nothing. Give the frame three
soft fields and offset their sampling:

| field | samples | so that |
|---|---|---|
| lead | `C(t + 12)` | the *next* chapter's colour is already in the frame, arriving from one corner |
| current | `C(t)` | the chapter's own colour holds the middle |
| lag | `C(t − 9)` | the *previous* colour is still leaving from another corner |

Drift each on its own long period (47/53/59 s on x, 61/67/71 s on y) so they never beat against each
other. The change then reads as weather, not as a transition.

**Falloff and blur — the rule that decides whether it looks expensive.**
A field built as a *solid plateau with a hard stop* (`colour 0 55%, transparent 60%`) plus a small
blur looks like a **patch**: you can see exactly where it ends, and more blur only softens the seam.
A field with a **small solid core and a long falloff** — `radial-gradient(closest-side, c 0%, c 14%,
transparent 76%)` — reads as a wash even with **no blur at all**. Fix the falloff first; treat blur
as the last 5 %, and remember it is software-rasterized in headless capture (see the blur rule
above). If you do use it, go big (110–140 px at 2K) rather than tightening the gradient.

**Ground options.**
- *Light:* a pale lavender mist (`#ece8f6`) rather than white — pure white reads as an unfinished
  page, and the fields have nothing to sit on.
- *Dark:* a near-black brand ground (`#07050f`) plus a hero glow. Mid-saturation track colours go
  **grey** on black, so pull every field toward a deep violet (≈55 %) before painting it, and
  **lighten the accent glows toward white** (≈30 %) so they read as light sources rather than paint.

**Strength.** Treat the colour's share of the frame as a dial, not a constant: a 12 %-toward-white
tint at the low end, pure colour at full opacity in the middle, and at the top a 25 % wider field
with the gentle core above — bold enough that type sits *on* the colour rather than near it.

### Implementation
The code for all of it — `C(t)`, the three fields, light/dark grounds and the strength levels — is the
**mark-driven-ground** skill (`../mark-driven-ground/assets/ground.js`, `GROUND.colorAt(t)`), which
also couples the ground to an element travelling through the frame: rings along its flight path, a
lit arc behind it, and a glow where it lands.

## See also
The full menu across all 8 families (A–H, ~56 moves) is the **motion-graphics** master skill and its
[PLATTER.md](../motion-graphics/PLATTER.md). Ask for "the platter" to get the whole menu.
