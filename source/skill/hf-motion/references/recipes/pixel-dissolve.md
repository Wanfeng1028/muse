# Recipe: pixel-dissolve

A 6 s word swap, 1080x830 @ 30 fps: scene A's text holds, then dissolves
cell by cell into scene B's text and B holds to the end. Paper / charcoal /
one accent colour, the bundled Korean display face (NanumSquare ac ExtraBold,
same file as `intro-kinetic`). No music bed and no SFX. Default `CONFIG` is
"어제의 나" -> "오늘의 나" and is the verified reference render.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `textA` | text | `어제의 나` | scene A, 180 px, one line; shrinks to fit 920 px |
| `textB` | text | `오늘의 나` | scene B, same rules |
| `transitionAt` | seconds | `3` | **0.5..4.5**, when the first cell flips |
| `transitionDur` | seconds | `1` | **0.2..3**, first cell to last; `transitionAt + transitionDur <= 5.5` (keeps a 0.5 s hold on B) |
| `pixelSize` | integer px | `40` | **10..200**, cell edge; larger = coarser (40 -> 27x21 = 567 cells) |
| `bgA` | `paper` \| `charcoal` \| `red` | `charcoal` | scene A background; text takes paper on charcoal/red, charcoal on paper |
| `bgB` | same | `paper` | scene B background |
| `paper` | `#rrggbb` | `#f2eee6` | light |
| `charcoal` | `#rrggbb` | `#1e1e1e` | dark |
| `red` | `#rrggbb` | `#e5322d` | accent: the colour each cell flashes on its way to B |

## Timeline (`T = transitionAt`, `D = transitionDur`, `F = 0.2 D`)

| Element | Window (s) | Default (s) | What happens |
|---------|------------|-------------|--------------|
| `sA` | 0 .. T + D | 0.0-4.0 | text A settles (scale 1.08 -> 1, 0.8 s), holds |
| `sB` | T .. 6 | 3.0-6.0 | revealed cell by cell; text B settles over D + 0.5 s |
| `fx` | T .. T + D | 3.0-4.0 | accent cells in flight |

Cell `r` of the seeded order turns accent at `T + r/N (D - F)` and to scene B
`F` later, so at `T + D` every cell shows B and the accent layer is empty.
The reveal is a `clip-path: path(...)` union of the revealed cells on `sB`
(and of the in-flight cells on `fx`), redrawn from one linear tween — no
per-cell DOM nodes. Total is fixed at 6 s. Root and window timing are static
attributes written by the scaffold; never edit them by hand.

## Determinism

The cell order is `mulberry32(719)` driving a Fisher-Yates shuffle — no
unseeded RNG anywhere — so the same `CONFIG` always gives the same frames.
`recipe.mjs` `cellOrder()` is the reference; `index.html` carries the same
code, and `scaffold.selfcheck.sh` fails if the two diverge or if either file
calls an unseeded RNG. Proved on the reference build: two renders of the
default and of an alternate config were frame-identical (framemd5, 180/180).

## Known pitfalls

- **check needs the overlap marked.** A and B share the frame while the cells
  swap; `#textA` / `#textB` carry `data-layout-allow-overlap` and
  `data-layout-allow-occlusion`. Without them `check` fails on
  `content_overlap` / `text_occluded`.
- **Contrast is not audited mid-dissolve.** `draw()` sets
  `data-layout-ignore` on both texts while cells are swapping: check's
  contrast pass takes the median pixel of the text box, so half-revealed B
  read as B's ink on A's colour (`#textB 1:1`, e.g. `transitionAt=2.5
  transitionDur=1.5` at t=3s). Both holds are audited as usual.
- **Accent on an accent background.** With `bgA=red` (or `bgB=red`) the
  flash cells match that background, so the dissolve reads as a straight
  swap on that side. That is the palette rule (three colours only), not a bug.
- **Small cells cost path length, not DOM.** `pixelSize=10` is 108x83 = 8964
  rects in one path per frame; renders stay fast, but below that the grain is
  no longer visible at 1080 px wide, hence the floor.
- **Width fit is estimated** (same per-glyph rule as `intro-kinetic`) and only
  shrinks; look at the snapshot for very long lines.
- **No beat grid.** Without a music bed the "every cut on a beat" rule has
  nothing to lock to; timing is in seconds.
