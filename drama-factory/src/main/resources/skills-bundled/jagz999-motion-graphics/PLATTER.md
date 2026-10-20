# The Motion Platter — named recipe catalog

A menu of motion-graphics "moves" distilled from launch-reel / SaaS-promo references
(Pinterest "2d motion graphics", "saas promotional video", Beyond Motion, Zelios, think3,
MotionDesigners.Pro, Nadim Sheikh, Philipp, Behance). Each has a **name**, what it looks
like, the **reference** it came from, and a **render-safe build** (works in the headless-Edge
capture pipeline — see the blur rule at the bottom). Helpers live in `assets/textmotion.js`;
classes in `assets/textmotion.css`.

> When the user asks for "the platter" or "a platter of skills," list these names grouped by
> family with the one-line look, and offer to wire any subset into their piece.

---

## A · Text entrances
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| A1 | **Word-Rise** | words fade + rise, staggered | `tmSplit`+`tmReveal` | baseline |
| A2 | **Keyword Sweep** | a light bar sweeps behind the key word, which stays lit | `.tm-kw`+`tmSweep` | "highlight what matters" |
| A3 | **Gradient Hero** | one big word filled with a color gradient | `.tm-grad` | "Using true", "superpowers" |
| A4 | **Scramble-Decode** | text resolves out of random glyphs | `tmScramble` | cipher reels |
| A5 | **Ticker-Roll** | one slot cycles synonyms vertically | `.tm-ticker`+`tmTicker` | single-word hero swap |
| A6 | **Punch** | word scale-pops in | `.tm-punch`+`tmPunch` | accent beats |
| A7 | **Motion-Blur Slide** ✳ | word streaks in with directional blur, snaps sharp | `.tm-blurin`+`tmBlurIn` | "Meet", "rebuilt" |
| A8 | **Mixed-Type Line** ✳ | one sentence, each word a different font/weight/style | `.tm-mix` wrappers | "So we rebuilt it." |
| A9 | **Bold-Key** ✳ | plain line, the key word simply heavier/brighter | `.tm-boldkey` | "Content **marketing**" |
| A10 | **Serif Statement** ✳ | elegant italic-serif single words, slow holds | `.tm-serif` | "rebuilt." |

## B · Backgrounds & gradients
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| B1 | **Color-Arc + Blobs** | palette shifts per scene; soft blobs drift | `.tm-gradbg`+`tmGrad`+`tmDrift` | mesh/radial reels |
| B2 | **Mesh Wash** ✳ | a soft colored light-sweep glides across frame | `.tm-mesh`+`tmMesh` | "superpowers", "Using true" |
| B3 | **Blueprint Grid** | faint technical line grid | `.tm-grid` | "Introducing" |
| B4 | **Dot Matrix** ✳ | faint dotted grid field | `.tm-dots` | "Create New Agent" |
| B5 | **Neon Path + Travellers** ✳ | glowing curved lines with light-dots running along them | `.tm-path`+`tmTravel` | Philipp "Idea" |

## C · Shapes, orbs & particles
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| C1 | **Ring Ripples** | concentric rings expand outward | `.tm-rings`+`mkRings` | "AI SaaS Animation" |
| C2 | **Floating Rings (Bokeh)** ✳ | outlined circles drift at varied depth, some soft | `.tm-bokeh`+`tmBokeh` | "Content marketing", "Be authentic" |
| C3 | **Orb Bloom** ✳ | a bright ring blooms into a big soft glow orb | `.tm-orb`+`tmOrb` | "Be authentic" |
| C4 | **Converge** ✳ | scattered circles drift inward to a focal point | `tmConverge` | "Be authentic" |
| C5 | **Metaball Merge** ✳ | two circles stretch & fuse into a capsule | `.tm-meta`+`tmMeta` | think3 "Circles in motion" |
| C6 | **Gooey Blobs** ✳ | solid rounded shapes morph & drift | `.tm-goo` | "Visa" blobs |
| C7 | **Sparkle Burst** ✳ | a 4-point star twinkles/pops | `.tm-spark` | "Idea", "Give your users a place" |

## D · Glass & UI accents
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| D1 | **Glass Pill** | frosted status / CTA pill | `.tm-pill` | "Let's go" pill |
| D2 | **Glass Prompt-Card** | frosted input/answer card | `.tm-card` | prompt card |
| D3 | **Live Cursor** | oversized pointer glides & clicks | `tmCursor` | collab cursors |
| D4 | **Glass Card Float** ✳ | frosted product card tilts with parallax | `.tm-float`+`tmFloat` | "Visa" (see `glass-cards` skill) |
| D5 | **Focus-Glow Button** ✳ | glow blooms around a CTA on cue | `.tm-cta` | "Create New Agent" |
| D6 | **Radar CTA** ✳ | concentric rings emanate behind a center button | `.tm-radar` | "Get Started for free" |

## E · Product & composition
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| E1 | **Integrations Orbit** ✳ | app icons ring a center hub + connect | `.tm-orbit`+`tmOrbit` | integration-hub reel |
| E2 | **Icon Constellation** ✳ | app-icon bubbles float/scatter in space | `tmOrbit(scatter)` | "Too many deals" |
| E3 | **UI Screen Reveal** ✳ | a product screenshot rises/tilts in on a gradient | `.tm-screen` | "Good evening, …" |
| E4 | **Avatar Chips** ✳ | person/logo chips slide in as social proof | `.tm-chips` | "Marketers" |
| E5 | **Card-Stack Fan** ✳ | tilted cards fan out in perspective | `.tm-fan` | "Discover · Direction · Design" |

## F · Scene transitions (explainer glue) ✳
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| F1 | **Shape Wipe** | a solid shape sweeps across to swap scenes | `.tm-wipe` translate | explainer cuts |
| F2 | **Iris Reveal** | next scene revealed through an expanding circle mask | `.tm-iris` (clip-path circle) | title cards |
| F3 | **Mask Push** | outgoing slides out as a shape pushes incoming in | paired translate | UI walkthroughs |
| F4 | **Match-Cut Morph** | a shape in scene A becomes an element of scene B | shared element, animate size/pos | premium cuts |
| F5 | **Liquid Wipe** | an organic blob mask grows to swap scenes | `.tm-goo` as clip-path | "What a Story" |
| F6 | **Dissolve-over-Gradient** | content cross-fades while the shared gradient persists | `.tm-sc` gating + `.tm-gradbg` | this film |

## G · UI & data motion (product demos) ✳
| # | Name | Looks like | Build | Ref |
|---|---|---|---|---|
| G1 | **Bar-Grow** | chart bars rise from baseline, staggered | `.tm-bar`+`--h` transition | dashboards |
| G2 | **Line-Draw** | an SVG line/path draws on, area fills under | `.tm-draw` stroke-dashoffset | analytics reels |
| G3 | **Counter-Tick** | a number rolls up to its value (odometer) | `tmCount` | metric callouts |
| G4 | **Card Deal** | UI cards slide/stack into place in sequence | `.tm-deal`+stagger | app walkthroughs |
| G5 | **Toggle Switch** | a pill/toggle slides between states | `.tm-toggle` | feature compares |
| G6 | **Cursor Demo** | a cursor drives a real UI (click → state change) | `tmCursor`+state toggles | product demos |
| G7 | **Notification Pop** | toast/badge pops in with a spring | `.tm-punch` variant | "you've got…" beats |

## Extra background/element variants ✳
- **B6 · Starfield Drift** — tiny dots twinkle + parallax (ref: "Alpha" crypto promo) → `.tm-stars`+`tmStars`.
- **C8 · Line-Draw Icon** — an icon strokes itself on (`stroke-dashoffset`) → `.tm-draw`.
- **C9 · Doodle Connector** ✳ — wobbly hand-drawn line links two elements (ref: Kitaabh collage) → `.tm-draw` on a hand-jittered path.
- **G8 · Timeline Scrubber** ✳ — a horizontal date axis with a playhead sliding through years (ref: Kitaabh) → `.tm-timeline`+`tmScrub`.
- **B7 · Texture Overlay** ✳ — a persistent grain / paper / halftone / paint-wash layer over the whole frame for a tactile, "designed" feel (ref: Zelios/Canny painterly showreel; collage halftone) → `.tm-grainwrap` (SVG fractal-noise, static — cheap) + `.tm-halftone` + optional slow-drifting soft color wash. Keep opacity low (.04–.12). *Grain is a static overlay so it's render-cheap; do NOT animate it with `filter`.*

## H · Aesthetic presets (whole-scene looks, from the "What a Story" playlist) ✳
These are *combinations* — a background + element + type recipe that reads as one style.
| # | Name | The recipe | Ref |
|---|---|---|---|
| H1 | **Isometric UI** | UI planes on `rotateX(55deg) rotateZ(-45deg)`, layered + floating, soft long shadow; charts/cards animate on the plane | "Viable" #27 |
| H2 | **Collage / Cutout** | flat color bg + photographic cutouts + torn-paper sticker badges + **doodle connectors** + halftone/paper texture + timeline | "Kitaabh" #72 |
| H3 | **Apple-Minimalist** | huge negative space, ONE shape/word, slow elegant eases, mono/light type, near-black or near-white field | "Apple-Style" #94 |
| H4 | **Crypto / Neon-Glow** | near-black bg + starfield/particles + neon-glow edges + a spinning 3D token/coin + grid horizon | "Alpha" #2, "Ultra.io" NFT drops |
| H5 | **Dashboard Reveal** | a product UI window rises in (UI-Screen-Reveal) then its charts grow, counters tick, rows deal in | most SaaS explainers |

*Playlist coverage:* both "What a Story" playlists (~99 + ~97, heavily overlapping — same studio/clients) sort into ~7 buckets — **2D SaaS explainer** (the majority: kinetic type + UI cards + gradients + transitions), **Dashboard/data-viz + infographic** (H5 + family G), **Isometric** (H1), **Collage** (H2), **Crypto/NFT neon** (H4), **Apple-minimalist abstract** (H3), and **3D** (H1/`.tm-spin3d`/`.tm-iso` cover 3D-lite). All are reproducible in-pipeline with families A–G + these presets.

**Out of scope for the HTML/CSS render pipeline** (present in the playlists, but *not* achievable with this toolkit — flag to the user and use real footage / AE / a video model instead): **rigged 2D character animation**, **live-action footage**, and **true 3D scenes** (only 3D-lite via CSS transforms is in-pipeline).

✳ = added in this pass (the rest already shipped in the skill).

## Families at a glance (the "platter")
**A** Text entrances · **B** Backgrounds & gradients · **C** Shapes/orbs/particles ·
**D** Glass & UI accents · **E** Product & composition · **F** Scene transitions · **G** UI & data motion.
~40 named moves. Ask for "the platter" to get this menu; ask for a family letter to get just those.

---

## Render-safety rule (applies to every recipe)
Headless Edge software-rasterizes `filter:blur()` / `backdrop-filter:blur()` → capture drops to
~5 fps. So every "soft/frosted/blurred" look here is faked **without** blur:
- **Softness** → `radial-gradient` falloff (rings, orbs, bokeh) or low-opacity layers.
- **Frosted glass** → semi-transparent gradient fill + 1px light border + inset top highlight (no backdrop-filter).
- **Motion blur** → a short directional `text-shadow`/ghost smear that resolves to none (`tmBlurIn`), not `filter:blur`.
- **Metaball goo** → two circles + a rounded connecting bar (no SVG `feGaussianBlur` goo filter).
All time-driven helpers take **logical time `t`** and all CSS durations scale by `--R`, so motion
stays correct under slow-clock capture.

## A′ · Line dynamics (added from the ETF launch-cut build, Jul 2026)
Whole-LINE behaviors — the line moves as one object, not word-by-word.
| # | Name | Looks like | Build |
|---|---|---|---|
| A11 | **Stamp-Slam** | line slams in like an auditor's stamp (scale 1.55→1 + tilt) | `.tm-stamp`+`.hit` |
| A12 | **Split-Converge** | two halves slide from opposite sides, meet with overshoot | `.tm-half.l/.r`+`.in` |
| A13 | **CRT Flicker-On** | line boots like a terminal (two flickers, then solid) | `.tm-crt`+`.on` |
| A14 | **Tracking-Breathe** | kicker settles from very wide letter-spacing | `.tm-breathe`+`.in` |
| A15 | **Strike-Dismiss** | superseded line gets struck through + dims (pairs with cracked-word) | `.tm-dismiss`+`.struck` |
| A16 | **Cipher-Slot** | ONE word in a stable sentence churns ciphertext then resolves | width-locked slot (see rule below) |
| — | **Living text** | shimmer / breathe / word wave-bob / glow pulse / perpetual ticker keep text alive after entrances | `.tm-shimmer` `.tm-pulse` + JS bob |
| — | **Camera Waypoints** | multi-target zoom choreography (terminal → dashboard → receipt) | waypoint array + easeIO lerp in camFor |

## A″ · Spark-driven text (from the walkthrough-film build, Sep 2026)
Text that belongs to the element travelling through the frame. The reference is a spark-driven
web-animation reel: the spark runs along rings, arcs light behind it, glows bloom where it lands,
and the text is *typed by the spark*. These six moves are that text half; the ground half (rings,
lit arc, landing glow, colour track) is the **mark-driven-ground** skill, which is driven by the
same mark on the same clock. Classes `.tm-*` in `assets/textmotion.css`, helpers in
`assets/textmotion.js` (`tmTypeBuild · tmType · tmTypeSettle · tmTypeCursor · tmEchoInto · tmEcho`).

| # | Name | Looks like | Render-safe recipe | Asset |
|---|---|---|---|---|
| A17 | **Typewriter with settling tracking** | the line types out, each new letter arriving slightly wide and closing up behind the edge | build the line ONCE in its final layout as `.tm-tw` words of `.tm-tl` letters; per frame set opacity and a **translateX accumulator** (`+.18em` easing to 0 over .25 s) — transforms only, so the row never reflows or re-wraps; step `min(.035, 1.1/N)` caps any line at 1.1 s | `tmTypeBuild` + `tmType` |
| A18 | **Mark/dot as cursor** | the travelling element rides at the end of the typed line, then eases back to its resting point | `tmTypeCursor(el,t)` returns the typing edge (letter right-edges measured once, interpolated *between* boxes so the ride is smooth) — lerp your mark from its landing point to that edge on an ease-out, arc it over the line with a sine, shrink it to cursor size, then return on an ease-in-out | `tmTypeCursor` |
| A19 | **Highlighter pill on the payoff word** | the last word lands inside a solid product-colour pill, white letters, the pill wiping in from its left edge | wrap the run in `.tm-pay` with an `.tm-pw` pill behind it; animate `clip-path:inset(0 var(--wipe) 0 0)` 100 %→0 over .3 s from the run's FIRST letter; letters go flat white — no gradient text on a colour pill | `.tm-pay` / `--wipe` |
| A20 | **Ghost echoes** | two faint copies above and two below the landed word, sliding outward and fading | `.tm-gz` absolutely-positioned copies at ∓1.05em and ∓2.1em, opacity .10 inner / .06 outer → 0 while translating 40 px further out over .6 s; absolute, so they never touch the line's layout | `tmEchoInto` + `tmEcho` |
| A21 | **Tilt-settle landing** | the payoff run arrives a few degrees off and straightens as it completes | `rotate(6deg × (1 − easeOut(p)))` over .35 s on the run's wrapper, started on the SAME instant as the pill wipe — the pill draws in tilted and squares up as the word finishes | `tmType` (`o.deg`) |
| A22 | **VO-anchored per-word typing** | the line types left to right but each word still starts exactly on the spoken word | give each word its VO time (`[{w:'every',at:1.42},…]`); letters run at the typing step *inside* the word, so the tempo reads as a typewriter while the line never leaves the voice | `tmTypeBuild(el, words)` |

```js
tmTypeBuild(line, [{w:'Block',at:0},{w:'it,',at:.31},{w:'in',at:.52},
                   {w:'real',at:.64},{w:'time.',at:.88}], {pay:[4,4], echo:true});
// per frame, from your logical clock:
tmType(line, t);
const c = tmTypeCursor(line, t, {space: stage});   // ride your mark to {x,y}, then ease it home
```
**Why it holds together:** the pill, the tilt and the echoes all key off the *payoff run's own
letters* (first letter → wipe + tilt, last letter → echoes), so retiming or rewording the line
re-times the whole move for free. And because the cursor is read from the same measured letter
boxes the ground's landing point came from, the mark, the text and the background stay in register
with no shared state.

## Production rules (paid for in re-renders — do not relearn)
1. **Width-lock scramble slots.** Cipher glyphs vary in width → the whole sentence reflows every cycle and "the words move." Lock the slot to the EXACT resolved-word width, measured via a hidden clone appended to the heading (live-element measures can return 0 pre-layout; retry per-frame until >0; avoid unit-guess fallbacks — an oversized fallback = visible extra gaps around the word).
2. **Motion-blur smear ≤ .15em.** Bigger text-shadow offsets read as DUPLICATE words at hero sizes, not blur.
3. **One static stage background.** Never composite bright backgrounds inside the camera-transformed world — any pan/zoom can expose the world edge (black border). Put a single oversized static background UNDER the world; only elements ride the camera.
4. **Neutral logo shadows.** Colored drop-shadows (purple/mint) around white lockups read as color bleed/fringing. Use dark neutral shadows on brand marks.
5. **Transform states must carry positioning.** If an element is centered by `translateX(-50%)`, every animation state (including JS-set transforms like breathing) must include it, or the element jumps half-off-screen.
6. **Cue words to the SFX events, not vice versa.** Read the sfx event JSON (tick times) and reveal each word exactly on its tick; a linear reveal window drifts ~0.3s off the sounds.
7. **Never type with `letter-spacing`.** Animating tracking on the line re-lays it out every
   frame: the words crawl and a long line can re-wrap mid-type. Carry the settling tracking on
   per-letter `translateX` instead (A17) — the boxes never move, only the paint.
8. **Measure letter boxes once, after `document.fonts.ready`.** A live measure before layout
   returns 0 and a zero right-edge parks the cursor at the line's start; cache the rects on the
   element and retry next frame if they come back empty.
9. **A zero-length dash with a round linecap paints a dot.** Writing a travelling stroke window as
   `"0 tail win 2L"` leaves a cap-sized dot at the path's origin. Use one dash plus a negative
   `stroke-dashoffset` instead (see `mark-driven-ground`).
