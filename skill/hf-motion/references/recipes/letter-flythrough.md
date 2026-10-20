# Recipe: letter-flythrough

A 6 s camera fly-through, 1080x830 @ 30 fps: big letters stand on the paper
background, one glyph's counter (the enclosed hole, e.g. the triangle inside
"A") is filled with the accent colour, then the camera zooms into that hole
until it is the whole frame and the next scene's text, which was inside the
hole all along, is full-size. Paper / charcoal / one accent colour, the
bundled Korean display face (NanumSquare ac ExtraBold, same file as
`intro-kinetic`). No music bed and no SFX. Default `CONFIG` is "AI" ->
"프롬프트 한 줄" and is the verified reference render.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `letters` | text | `AI` | **1..6 characters**, drawn as outlines fitted to a 920x600 box; every character must exist in the bundled font |
| `nextText` | text | `프롬프트 한 줄` | the next scene's text, 150 px, one line; shrinks to fit 920 px |
| `diveAt` | seconds | `2` | **1..4.5**, when the camera starts moving (the letters' entrance takes the first 1 s) |
| `diveDur` | seconds | `2` | **0.5..4**, length of the dive; `diveAt + diveDur <= 5.5` (keeps a 0.5 s full-screen hold) |
| `targetGlyphIndex` | integer | `0` | position in `letters` (0-based) of the glyph to fly into; **that glyph must have a counter** |
| `paper` | `#rrggbb` | `#f2eee6` | background and next-scene text |
| `charcoal` | `#rrggbb` | `#1e1e1e` | the letters |
| `red` | `#rrggbb` | `#e5322d` | the hole and the next scene; paper text on it must pass `check`'s contrast gate (`#c0392b` passes) |

### Supported letters

Any character the bundled font draws, as long as the **target** glyph has a
counter (an enclosed hole): Latin `A B D O P Q R a b d e g o p q`, digits
`0 6 8 9` (this face's `4` is open), Hangul syllables with `ㅇ`, `ㅁ`, `ㅂ`, `ㅎ` (e.g. `오`, `몸`) and
so on. The other letters may be anything (`OK`: fly into the `O`, the `K` is
just drawn). The scaffold decides from the font itself, not a list, and
refuses a target with no counter before writing anything:

```
[hf-motion] invalid parameters:
  - letters: 'I' (targetGlyphIndex 0) has no counter to fly into; target a glyph with an enclosed hole (...)
```

When the glyph has several counters (`B`, `8`), the largest one is the target.

## How the hole is found (the design decision)

Two ways were weighed: draw the letters as HTML text and cut the hole with a
mask, or read the glyph outlines from the font. Text + mask cannot say
**where** the hole is: the camera needs its exact shape to land inside it,
and a mask would have to be traced per letter by hand. So the outlines come
from the font:

- `recipe.mjs` holds a small TrueType reader (node stdlib only, no new
  dependency): `cmap` (formats 4/12), `hmtx`, `loca` and `glyf` (simple and
  composite glyphs). At scaffold time it lays the letters out by advance
  width (no kerning) and writes them as SVG paths into the project's
  generated `glyphs.js`, with the target hole and the landing rectangle.
- A counter is a contour wound against the glyph's largest contour (TrueType
  winds holes the opposite way); a glyph with none has no hole.
- The landing rectangle is the largest canvas-ratio rectangle inside the
  hole (grid of centres, binary search on size, two refinements), shrunk to
  90 % so the hole's edge is well past the frame when the dive lands.
- `glyphs.js` is generated, never hand-edited: change `letters` or
  `targetGlyphIndex` and re-run `scaffold.mjs letter-flythrough <dir>
  --update`. The template throws at load when `glyphs.js` was built for other
  letters. The template's own `glyphs.js` is the default's output, and the
  selfcheck holds the two equal.

## Timeline (`T = diveAt`, `D = diveDur`)

| Element | Window (s) | Default (s) | What happens |
|---------|------------|-------------|--------------|
| `letters` | 0 .. T + D | 0.0-4.0 | outlines rise in (y 40 -> 0, fade, 1 s), hold, dive, then leave the timeline |
| `next` | 0 .. 6 | 0.0-6.0 | sits on the landing rect inside the hole; text fades in over the first half of the dive; full-screen hold with a slow 4 % push |

The camera is the SVG `viewBox`, so the outlines stay vector-sharp at any
zoom. One tween drives it (`power2.inOut`): the scale grows exponentially in
progress (constant perceived speed) from 1 to `S = 1080 / rect width`, and
the rect's centre slides to the frame centre on the same ease, so at `T + D`
the landing rect is exactly the frame. The next scene is authored at canvas
size and placed on that rect at scale `1/S`; at `T + D` its net transform is
the identity and the text is crisp. Until then its background is the hole's
accent fill (one fill, so no double-alpha seam); at `T + D` it takes over the
background as the letters leave, pixel-identical.

Total is fixed at 6 s. Root and window timing are static attributes written by
the scaffold; never edit them by hand.

## Why direct GSAP, not `zoom-through-transition` / `cinematic-zoom`

`zoom-through-transition` flies through a card, not a glyph's counter, and
`cinematic-zoom` is a shader cut between two scenes. Here the next scene is
the same DOM inside the hole from the first frame, which is what makes the
move continuous, so the template uses no catalog block.

## Proof on the reference build

Two renders of the default and of an alternate config
(`letters=OK nextText=Hello 다음 장면 diveAt=1.5 diveDur=3 red=#c0392b`)
were frame-identical (framemd5, 180/180); both passed lint (only the accepted
`nested_structure_needs_subcomposition`), check (Layout 0 issues, contrast
pass) and verify-render. Across the dive the mean absolute frame-to-frame
difference (RGB, 0-255) rises and falls as one hump with no isolated spike
(default peak 23.3 at the frame where the last ink leaves the frame; no frame
more than 2.5x its neighbours), and from `T + D` on every border pixel is the
accent within codec rounding (max deviation 2) with the next text on it: no
empty or flat frame anywhere.

## Known pitfalls

- **Small counters zoom far.** A tiny hole makes a fast final push: the `A`
  of "AI" lands at about 13x, the `a` of "Bad" at 16x, the `홍` of a
  six-syllable word at 43x. Fewer letters give bigger holes.
- **Accent too light for paper text.** Same contrast rule as `screen-dive`.
- **No kerning.** Letters are spaced by advance width only; pairs like `AV`
  sit a little loose.
- **Width fit of `nextText` is estimated** (same per-glyph rule as
  `intro-kinetic`) and only shrinks; look at the snapshot for very long lines.
- **No beat grid.** Without a music bed the "every cut on a beat" rule has
  nothing to lock to; timing is in seconds.
