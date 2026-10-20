---
name: travelling-mark
description: >-
  Make one brand mark (logo, dot, glyph) TRAVEL through a film as a single rigid object: it lifts
  off the product's sidebar logo on a hard cut, flies into a title card on a named path (zip, drop,
  spiral, hops, orbit), lands beside the heading, rides the typed line as a cursor, breathes on the
  hold, and leaves along an exit (inflate, roll, dive) that also opens the next dashboard around the
  logo slot. Also covers the opening "round" (one arc-length-parametrised orbit into the sidebar) and
  the closing "mark as a hole" reveal. Use when a logo should carry the viewer from chapter to
  chapter, when a reference reel has a spark/dot that leads every cut, or when a client says the logo
  must never stretch, squash, split or morph while it moves. Triggers: "the logo travels between
  scenes", "logo flies into the title", "dot that jumps from card to card", "logo lands next to the
  heading", "logo becomes the cursor", "make the logo leave into the dashboard", "logo must stay
  rigid", "the plus/mark path", "logo hole reveal at the end".
---

# Travelling Mark

One rigid mark carries the whole film. Every chapter opens the same way: the previous dashboard is
still on screen, the mark **lifts off its sidebar logo** (measured live, so it starts exactly where
the logo sits), **flies** a named path into a title card, **lands** at a fixed point beside the
heading, the heading appears out of that point, the mark **holds** with a slow breath, and on the
cut it **leaves** along an exit path straight into the logo slot of the next dashboard, which opens
around it. Nothing on the mark ever changes shape; only its position, uniform size and, on one exit,
its rotation. Drop-in maths in `assets/mark.js`; a standalone run in `assets/demo.html`.

Pairs with **mark-driven-ground** (the background draws the same path as rings and lights the arc
behind the mark) and **walkthrough-film** (the timing / render pipeline it lives in).

## The one hard rule
**The mark is rigid.** The container is placed by `left/top/width/height` (always square) and may
carry one whole-mark transform: uniform `scale()` and/or `rotate()`. The image inside is never
transformed. No stretch on the streak, no squash on landing, no dot-morph, no petal split, no
"pieces" entrance. Clients notice every one of those, and they read as cheap. If a path needs
emphasis, use speed, arc height or a landing ring pulse (a separate element), never deformation.

## Anatomy of one chapter (times are scene-local, title cards are 2.4–3.2 s)
| beat | when | what |
|---|---|---|
| Hard cut | 0 | The previous dashboard is never shown during the title. In `enter()` measure `S = centre of .side-logo` (its size `s`), then clip the dashboard away. |
| Flight | 0 → 0.7 | `pathAt(kind, p, LP, S)`, `p = lt/0.7`. Size eases `S.s → 250` with `ez(min(1, 2.5p))` so it grows early and lands at full size. |
| Landing | 0.7 | `LP = {x: heading.left − 170, y: heading.centreY}` (measured once from the card's final layout). Optional ring pulse: a 2 px circle 0→420 px, opacity .9→0 over .35 s, centred on LP. |
| Heading | 0.62 → | Words spring out of LP (`eb` back-ease, 50 ms stagger, each word translates from `LP.x − word.cx`), or the typewriter with the mark as cursor (below). |
| Hold | land+.32 → cut−.1 | Breath: `scale(1 + sin((lt − t0)·3.2) · .02 · (1 − ez(seg(lt, dur−.6, dur−.1))))`. Phase 0 at `t0` so there is no jump; amplitude dies before the cut so every exit starts from scale 1. |
| Exit | chapter 0 → 0.7 | Drawn as an OVERLAY on the chapter's first .7 s (`titleExit(chapter, lt)`), from LP to the next dashboard's logo centre `G` (measured live), size `250 → G.s`. |

## Entrance paths (`p ∈ [0,1]`, S start, LP landing) — in `assets/mark.js`
- **zip** — straight lerp on `eo(p)` with a 260 px sine lift: `y −= sin(pπ)·260`.
- **drop** — first 30 %: rise off S to `y = −300` above the frame while x eases to LP.x; then fall on `q²`, a 240 px bounce, a 70 px settle. Reads as "dropped from the sky".
- **spiral** — angle `1.1π → 3.6π`, radius `|S−LP| → 0` on `eo`, flattened ×0.6 in y; the first third blends from S with `ez(min(1,3p))` so the spiral starts where the mark actually is.
- **hops** — x lerps S→LP, `y −= |sin(3πp)| · lerp(340, 90, p)`: three hops that shrink.
- **orbit** — angle `.9π → 2.55π` on `eo`, radius `|S−LP| → 0` on `ez`, flattened ×0.5, blended in over the first quarter.
Pick one per chapter; repeat a path at most twice in a film. Every path is a pure function of `p`: seeking to any frame gives the same picture.

## Exit paths (`px = lt/0.7`, from LP to the logo slot G of the next page)
- **inflate** — the mark grows `250 → 6400 px` on `ez(seg(px,0,.42))` (it swallows the frame), then from .48 shrinks `6400 → G.s` into the slot while the dashboard is revealed behind it (clip `inset(0 100% 0 0)` released at .48). The heading is gone under the inflation; nothing else moves.
- **roll** — the whole mark **rotates −540°** along a bouncing arc (`y −= |sin(1.5πq)| · 220 · (1 − q/2)`) into the slot; the dashboard opens as a circle `clip-path: circle(60 → 3400 px at G)` on `eo(seg(px,0,.9))`. Rotation only: the glyph stays whole.
- **dive** — a single 380 px arc into the slot; the dashboard fades `opacity eo(seg(px,.1,.8))` and scales `.94 → 1` around it.
Once the exit is done the sidebar logo is the mark; the film's logo is now the product's logo. That hand-off is the whole trick.

## The mark as cursor (typewriter title cards)
After landing the mark **hops** to the end of the typed line (`eo`, .27 s, arcing 240 px over the words so it never crosses text it just wrote), shrinks to the cursor size (180 px on the hop's own ease), **rides** 24 px past the right edge of the last visible letter (continuous between letters, so the ride is smooth), and inside the payoff word rides the pill's wiping edge instead. When typing ends it hops back to LP (`ez`, .35 s) and regrows to 250, well before the cut, so the hold breath and every exit are untouched. See `text-motion` A″ for the letters and pill.

## The opening round (before the first dashboard)
The mark's first flight is one clockwise round on a drifting, shrinking ellipse: angle `−80° → 230°`,
radii `1120×360 → 260×110`, centre `(1280,660)` → the point that puts θ = 230° exactly on the sidebar
glyph centre G; drift and shrink weighted `e³` so the ellipse stays large through the first half
(clears the headline) and spirals into the slot in the second. Re-parametrise by **arc length**
(`orbitArcE`, 120-segment numeric integration, pure) so the mark moves at constant speed along the curve.

## The closing hole
The end reverses the trick: the ground closes in with the **mark cut out of it** (an SVG mask built
from the union of the mark's paths, filled black on a white rect so overlapping shapes union), the
previous scene lives inside the hole as it shrinks onto the lockup box, the colour mark fades in over
the hole, the wordmark slides in, the address lands, and the picture **holds** to the cut.

## Measuring, not hard-coding
- `S` is measured in `enter()` from the live sidebar logo rect; `G` in the exit from the next page's logo. If the rail moves, the mark still lifts off the right pixel.
- `LP` is measured once per card from the heading's final layout (`measure(id)` caches it). Anything that later re-renders the heading (per-letter spans) must produce the same box, or LP drifts and the background rings (which are hard-coded from the same measurements) no longer match.
- If a background module needs the paths without the DOM (per-scene renders never see the title before the chapter), export the sampler: `window.MARK = {pathAt, T_IN, S_LAND}` and freeze `S`/`LP` in a table measured once.

## Pitfalls
1. **Zero-length leading dash paints a dot** with `stroke-linecap: round` when a path is used for a lit arc (`dasharray "0 tail win"`). Use one dash plus a negative `dashoffset`.
2. **Landing squash / streak stretch** looked slick in the first cut and were removed at client request. Rigid from day one.
3. A **`pieces` / petal split** entrance breaks the rigid rule even if each piece is rigid.
4. Start the breath at phase 0 and kill its amplitude before the cut, or the exit jumps.
5. Cursor hops must **arc over the line**, and the cursor must be smaller than the landed mark, or it sits on the words.
6. The hard cut needs the dashboard **clipped from lt 0**; hiding after the first frame flashes the template.
7. Seek-order: `enter()` runs on scene change, so a shots tool jumping straight into a chapter never saw the title. Anything the chapter needs from the title (S, LP) must be measurable on its own.
