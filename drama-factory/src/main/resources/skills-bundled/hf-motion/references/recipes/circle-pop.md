# Recipe: circle-pop

A 6 s scene change, 1080x830 @ 30 fps: scene A's text holds, then a circle
pops out of `popOrigin` (overshooting once), grows until it covers the frame
and **is** scene B's background — text B pops in on it while it fills, so
there is no cut and no bare frame. Paper / charcoal / red, the bundled Korean
display face (NanumSquare ac ExtraBold, same file as `intro-kinetic`). No
music bed and no SFX. Default `CONFIG` is "아이디어" -> "완성된 영상" and is
the verified reference render.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `textA` | text | `아이디어` | scene A, 180 px, one line; shrinks to fit 920 px |
| `textB` | text | `완성된 영상` | scene B, same rules |
| `transitionAt` | seconds | `3` | **0.5..4**, when the circle starts; B keeps >= 1.1 s after full cover |
| `popOrigin` | `center` \| `x,y` | `center` | where the circle starts, as frame fractions 0..1 (`0.15,0.8` = lower left) |
| `popColor` | `paper` \| `charcoal` \| `red` | `red` | circle = scene B background; text B takes paper on charcoal/red, charcoal on paper |
| `overshoot` | number | `1.15` | **1..1.5**, peak of the pop (and of text B's scale) over its rest size; clamped again at runtime |
| `paper` | `#rrggbb` | `#f2eee6` | light; scene A's background (charcoal instead when `popColor=paper`) |
| `charcoal` | `#rrggbb` | `#1e1e1e` | dark |
| `red` | `#rrggbb` | `#e5322d` | accent |

## Timeline (`T = transitionAt`, POP 0.4 s, FILL 0.5 s)

| Element | Window (s) | Default (s) | What happens |
|---------|------------|-------------|--------------|
| `sA` | 0 .. T + 0.9 | 0.0-3.9 | text A settles (scale 1.08 -> 1, 0.8 s), holds until covered |
| `sB` | T .. 6 | 3.0-6.0 | `clip-path: circle()` grows from `popOrigin`; text B pops in from T + 0.4 |

Circle radius `t` s after `T` (`R0 = 0.25 min(W, H)` = 207 px, `RC` = the
distance from the origin to the farthest corner):

| Phase | t (s) | Radius |
|-------|-------|--------|
| pop up | 0 .. 0.24 | 0 -> `R0 * overshoot` (cubic out) |
| settle | 0.24 .. 0.4 | -> `R0` (sine in-out) |
| fill | 0.4 .. 0.9 | `R0` -> `RC` (quad in); from 0.9 the clip is removed |

Text B: opacity 0 -> 1 and scale 0.7 -> `overshoot` over 0.33 s from T + 0.4,
then -> 1 over 0.22 s. Total is fixed at 6 s; root and window timing are
static attributes written by the scaffold — never edit them by hand.

## Seek safety and determinism

The circle is one linear progress tween redrawn by `radius(t)`, which returns
exactly 0 for `t <= 0` and exactly `RC` for `t >= 0.9`, so a seek to any
frame lands on the same value however the timeline got there. The overshoot
lives inside the tween, never past its ends; text B's overshoot is two
explicit `fromTo` tweens for the same reason. `scaffold.selfcheck.sh`
evaluates the template's `radius()` at and past both boundaries, checks its
peak equals `R0 * overshoot`, and pins its `POP` / `FILL` to `recipe.mjs`.
No RNG. Proved on the reference build: two renders of the default and of an
alternate config were frame-identical (framemd5, 180/180).

The catalog block `transitions-scale` was checked first: it is a 15 s
1920x1080 showcase of zoom transitions, not a circular reveal, so the circle
is written directly in GSAP.

## Known pitfalls

- **check needs the overlap marked.** A and B share the frame while the
  circle grows; `#textA` / `#textB` carry `data-layout-allow-overlap` and
  `data-layout-allow-occlusion`. Without them `check` fails on
  `content_overlap` / `text_occluded`.
- **Contrast is not audited while the circle grows.** `draw()` sets
  `data-layout-ignore` on both texts while the circle is partial: check's
  contrast pass takes the median pixel of the text box, so text straddling
  the edge read against the other scene's colour (`#textB 1:1` at
  `transitionAt=2.5`, t=3s). Both holds are audited as usual.
- **A corner origin covers later.** `RC` from a corner is ~1.4x the centre
  value, so the fill accelerates harder; the circle edge sweeps text A for
  longer. Look at the `T + 0.7` snapshot.
- **`popColor=paper`** flips scene A to charcoal so the circle stays visible.
- **Width fit is estimated** (same per-glyph rule as `intro-kinetic`) and only
  shrinks; look at the snapshot for very long lines.
- **No beat grid.** Without a music bed the "every cut on a beat" rule has
  nothing to lock to; timing is in seconds.
