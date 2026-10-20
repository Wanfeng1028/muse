# Recipe: screen-dive

A 6 s camera dive, 1080x830 @ 30 fps: a laptop drawn in CSS sits on the
paper background with a line of text on its screen, then the camera pushes
into the screen until the screen is the whole frame and the laptop is gone.
Paper / charcoal / one accent colour, the bundled Korean display face
(NanumSquare ac ExtraBold, same file as `intro-kinetic`). No music bed and no
SFX. Default `CONFIG` is "모션 그래픽" and is the verified reference render.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `screenText` | text | `모션 그래픽` | the screen's text, 170 px at full screen (85 px inside the laptop), one line; shrinks to fit 920 px |
| `diveAt` | seconds | `2` | **1..4.5**, when the camera starts moving (the laptop's entrance takes the first 1 s) |
| `diveDur` | seconds | `2.5` | **0.5..4**, length of the dive; `diveAt + diveDur <= 5.5` (keeps a 0.5 s full-screen hold) |
| `deviceStyle` | `laptop` | `laptop` | the drawn device; `laptop` is the only style today |
| `paper` | `#rrggbb` | `#f2eee6` | background and screen text |
| `charcoal` | `#rrggbb` | `#1e1e1e` | the laptop (lid, bezel, base) |
| `red` | `#rrggbb` | `#e5322d` | the screen; paper text on it must pass `check`'s contrast gate (`#ff5a1f` fails at 2.69:1, `#c0392b` passes) |

## Timeline (`T = diveAt`, `D = diveDur`)

| Element | Window (s) | Default (s) | What happens |
|---------|------------|-------------|--------------|
| `device` | 0 .. T + D | 0.0-4.5 | lid + base rise in (y 40 -> 0, fade, 1 s), hold, dive, then leave the timeline |
| `screen` | 0 .. 6 | 0.0-6.0 | rises with the lid; text appears at 0.4 s; dives; full-screen hold with a slow 4 % push |

The dive is one GSAP `fromTo` (`power3.inOut`) of `x`/`y`/`scale` on both
layers at once, from identity to the transform that maps the glass onto the
whole canvas. That target is read from the static layout (`#glass`
offsets), not typed in. The glass is 540x415, exactly half the canvas at the
same ratio, so the dive lands at scale 2 on whole pixels: at `T + D` the
bezel is entirely off-canvas and the frame edge is pure screen colour. The
screen content is authored at canvas size and shown at `scale(0.5)` inside
the glass, so at the end its net scale is 1 and the text is crisp. The device
layer leaving at `T + D` is a belt-and-braces guarantee that no bezel survives
into the hold; it is already invisible when it goes.

Total is fixed at 6 s. Root and window timing are static attributes written by
the scaffold; never edit them by hand.

## Why direct GSAP, not `cinematic-zoom`

The catalog's `cinematic-zoom` is a shader transition between two scenes:
it would make the dive a cut from one DOM to another. Here the screen is the
same DOM from the first frame to the last, which is what makes the move
continuous, so the template uses no catalog block. A blur assist was not
added: the reference render reads as continuous without it (proof below).

## Proof on the reference build

Two renders of the default and of an alternate config
(`screenText=Hello 새로운 화면 diveAt=1.2 diveDur=3.5 red=#c0392b`) were
frame-identical (framemd5, 180/180). Across the dive the mean absolute
frame-to-frame difference (RGB, 0-255) climbs and falls as one smooth hump
(default: 0.0 at `T`, peak 21.4 at mid-dive, back under 1 by 5.0 s; no
isolated jump, so no flicker or cut), and from `T + D` on every border pixel
of the rendered frame is `red` within codec rounding (max deviation 2).

## Known pitfalls

- **Accent too light for paper text.** The screen text is always paper on
  the accent; a bright orange/red fails `check`'s contrast gate. Pick a darker
  accent rather than overriding the gate.
- **The glass ratio is load-bearing.** The template throws at load if the
  glass is not the canvas ratio: a mismatched ratio would leave bezel bands
  at the end of the dive.
- **Width fit is estimated** (same per-glyph rule as `intro-kinetic`) and only
  shrinks; look at the snapshot for very long lines.
- **No beat grid.** Without a music bed the "every cut on a beat" rule has
  nothing to lock to; timing is in seconds.
