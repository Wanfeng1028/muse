---
name: jagz999-motion-graphics
description: >-
  Super-skill for motion-graphics videos in HTML/CSS/JS — the launch-reel / SaaS-explainer look.
  An umbrella over sub-skills for TEXT motion, BACKGROUNDS & GRADIENTS, ELEMENT / SHAPE / PARTICLE
  motion, GLASS & UI accents, PRODUCT composition, SCENE TRANSITIONS, and UI / DATA motion. Holds
  a named "platter" of ~40 reusable moves (each with a render-safe recipe) plus a drop-in building-
  block library (assets/motion.css + motion.js). Use when the user wants to build or restyle an
  animated title, explainer, launch/promo film, or any motion-graphics piece; make headings/scenes
  more dynamic; add moving gradients, drifting shapes, glowing rings/orbs, glass UI, transitions,
  animated charts/counters; match a reference reel; or asks for "the platter of skills / motion
  skills / a menu of effects". Composes with text-motion, kinetic-typography, glass-cards,
  smooth-render, vo-sync.
---

# Motion Graphics — the super-skill

One home for building polished 2D motion-graphics in plain HTML (no After Effects). Distilled from
launch-reel + SaaS-explainer references (Pinterest "2d motion graphics" / "saas promotional video";
YouTube "What a Story", Beyond Motion, Zelios, think3, MotionDesigners.Pro, Nadim Sheikh, Behance).

Two things live here:
1. **[PLATTER.md](PLATTER.md)** — the named menu of ~40 moves, grouped into 7 sub-skill families,
   each with what it looks like, its reference, and a render-safe build.
2. **assets/[motion.css](assets/motion.css) + [motion.js](assets/motion.js)** — drop-in building
   blocks (24 JS helpers + matching classes). Every effect scales by `--R` and is driven by
   **logical time `t`**, so it survives slow-clock capture.

```html
<link rel="stylesheet" href="assets/motion.css">
<script src="assets/motion.js"></script>
```

## Serving "the platter"
When the user asks for **the platter / a menu of motion skills / what effects can you do**, list the
families below with their one-line looks (pull the tables from PLATTER.md). When they ask for a
**family letter** (e.g. "give me the background ones"), list just that group. Then offer to wire any
subset into their piece.

## The sub-skills (families)
| | Family | What it covers | Key moves |
|---|---|---|---|
| **A** | **Text motion** | how words enter & emphasize | Word-Rise · Keyword-Sweep · Gradient-Hero · Scramble-Decode · Ticker-Roll · Motion-Blur-Slide · Mixed-Type · Bold-Key |
| **B** | **Backgrounds & gradients** | the living frame behind everything | Color-Arc+Blobs · Mesh-Wash · Blueprint-Grid · Dot-Matrix · Neon-Path · Starfield |
| **C** | **Elements: shapes / orbs / particles** | things that move in the space | Ring-Ripples · Floating-Rings(Bokeh) · Orb-Bloom · Converge · Metaball-Merge · Gooey-Blobs · Sparkle |
| **D** | **Glass & UI accents** | frosted UI motifs | Glass-Pill · Prompt-Card · Live-Cursor · Card-Float · Focus-Glow-Button · Radar-CTA |
| **E** | **Product & composition** | showing the product | Integrations-Orbit · Icon-Constellation · UI-Screen-Reveal · Avatar-Chips · Card-Stack-Fan |
| **F** | **Scene transitions** | gluing scenes | Shape-Wipe · Iris-Reveal · Mask-Push · Match-Cut · Liquid-Wipe · Dissolve-over-Gradient |
| **G** | **UI & data motion** | product-demo mechanics | Bar-Grow · Line-Draw · Counter-Tick · Card-Deal · Toggle · Cursor-Demo · Notification-Pop |

## How to build a piece (the method the references share)
1. **Pick a living background** (family B) — one palette per scene + slow drift = constant subtle motion.
2. **Give every scene a *different* text entrance** (family A) — identical headings read as a slideshow.
3. **Add one element/particle layer** (C) tuned to the scene's meaning (rings emanate, orbs bloom, blobs drift).
4. **Land the key word** with a Keyword-Sweep or Gradient-Hero; sync its cue to the VO word (see vo-sync).
5. **Transition** with a shape/iris/dissolve (F), not a plain crossfade — the shared gradient persisting already sells it.
6. **For product beats**, choose from UI/data motion (G) + glass/product (D/E): counters tick, bars grow, cards deal, cursor demos.
7. **Render** with smooth-render: play at `rate`, set `--R = 1/rate`, drive JS by logical time.

## The one hard rule (why the recipes look the way they do)
**Never `filter:blur()` or `backdrop-filter:blur()`** — headless Chromium/Edge software-rasterizes
them and capture drops to ~5 fps. Every "soft / frosted / motion-blurred" look in the platter is
faked without blur (radial-gradient falloff, translucent gradient + inset highlight, directional
text-shadow smear, two-circles-plus-bridge instead of an SVG goo filter). See PLATTER.md's footer.


## Production rules (from shipping a real launch video — see PLATTER.md for the full list)
Beyond the blur rule: **width-lock scramble slots** (glyph width jitter reflows the line);
**smear ≤ .15em** (bigger reads as duplicate words); **one static stage background** (backgrounds
inside a camera-transformed world expose black borders on pan/zoom); **neutral shadows on brand
marks** (colored drop-shadows read as bleed); **every transform state carries its positioning
translate**; **cue word reveals to the SFX event times**, not to a linear window.

## Composes with (focused sibling skills)
- **text-motion** — the deep dive on family A (this super-skill's assets are the shared library).
- **kinetic-typography** — word-cascade + hero-push staging.
- **glass-cards** — a card zooms forward to demo itself then falls back (family D, camera-driven).
- **smooth-render** — render the HTML to a sharp MP4 without choppy motion; mux audio.
- **vo-sync** — set each effect's cue time from VO word timestamps so moves land on the spoken word.

## Notes
- Set the palette via `--tm-accent / --tm-accent2 / --tm-warm / --tm-ink / --tm-mute` on `:root`.
- All helpers take logical time `t`; call per-frame updaters from your render/rAF loop, never wall-clock.
- Pause ambient loops when idle: `document.documentElement.classList.toggle('tm-paused', !playing)`.
- This library was distilled from launch-reel / SaaS-explainer references and battle-tested on a
  full 2K documentary-style product launch film (10 scenes, VO-synced, homelab-rendered).
