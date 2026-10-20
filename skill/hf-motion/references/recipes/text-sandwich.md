# Recipe: text-sandwich

A 6 s text sandwich, 1080x830 @ 30 fps: a big word rises in letter by letter
over a red base line, then the user's character image crosses the frame
*between* the letters, in front of some and behind others, and the word holds
with a slow push. Paper / charcoal / one accent colour plus the user's own
image, the bundled Korean display face (NanumSquare ac ExtraBold, same file as
`intro-kinetic`). No music bed and no SFX.

## Input asset: the character image

The character is the user's own file and is **never bundled** in this repo
(copyright, size). `characterImage` is a path to it, relative to the current
directory; the scaffold copies it to the project's `assets/character.png`,
which is what the page shows (the browser sniffs the real format, so `.webp`,
`.jpg` and `.gif` work under that name; SVG is refused). When the file is
missing or unreadable the scaffold stops with exit 2, names the path it tried,
and writes nothing. The default `alex.png` therefore only works when such a
file exists where you run the scaffold: ask the user for theirs. A transparent
PNG works best; any size or aspect ratio is contain-fit (never cropped or
stretched) into a 420x620 box.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `word` | text | `MOTION` | 1..12 characters, one line, up to 260 px; shrinks to fit 960 px |
| `characterImage` | path | `alex.png` | the user's `.png`/`.webp`/`.jpg`/`.gif`; copied to `assets/character.png` |
| `direction` | `ltr` / `rtl` | `ltr` | which way the character crosses |
| `passAt` | seconds | `1.5` | **1..4.5**, when the character starts to enter (the letters' entrance takes the first ~1 s) |
| `passDur` | seconds | `2.5` | **0.5..4**, edge-to-edge crossing time; `passAt + passDur <= 5.5` (keeps a 0.5 s hold) |
| `paper` | `#rrggbb` | `#f2eee6` | background |
| `charcoal` | `#rrggbb` | `#1e1e1e` | the word |
| `red` | `#rrggbb` | `#e5322d` | the base line |

## Timeline (`T = passAt`, `D = passDur`)

| Element | Window (s) | Default (s) | What happens |
|---------|------------|-------------|--------------|
| `back` | 0 .. 6 | 0.0-6.0 | every letter rises in (y 90 -> 0, 0.06 s stagger from 0.1 s); the base line draws from 0.3 s; slow 3 % push from `T + D` |
| `character` | T .. T + D | 1.5-4.0 | the image box moves linearly from fully off one edge to fully off the other |
| `front` | 0 .. 6 | 0.0-6.0 | the same word, same tweens, only letters 2, 4, 6, ... visible |

**The sandwich is a z-order, not a mask.** The word is laid out twice in
identical boxes: `back` (z 1) shows every letter, the character sits on z 2,
and `front` (z 3) shows only letters 2, 4, 6, ... (spaces are skipped in the
count), so the character covers the odd ones and is covered by the even ones.
Both copies are built by the same loop and get the same tween, so the front
letters sit exactly on their back copies; nothing is clipped or masked.

Total is fixed at 6 s. Root and window timing are static attributes written by
the scaffold; never edit them by hand.

## Why no catalog block

The catalog's `bottom-up-letters` candidate is only a per-letter entrance; the
sandwich itself is the two-copy z-order above. The rise-in is one GSAP
`from` with a stagger, so the template uses no catalog block.

## Proof on the reference build

The reference build used a throwaway transparent PNG (300x500, a light-blue
figure) generated at test time; no image is committed. Default config and an
alternate (`word=샌드위치 TEXT characterImage=<800x300 PNG> direction=rtl
passAt=1 passDur=3.5 red=#c0392b`): lint 0 errors (only the accepted
`nested_structure_needs_subcomposition` warnings), check passed (Layout 0
issues, Contrast all pass), two renders of each were frame-identical
(framemd5, 180/180), and verify-render printed `[OK]` for video and duration.
In the rendered frames at `T + 0.5D` and `T + 0.75D` both sides of the
sandwich are measurable: letter pixels from the pre-pass frame replaced by
character pixels (default 10561 at 2.75 s) and letter pixels with character
pixels on both sides in the same row (default 7602 at 2.75 s). The wide image
fitted its box without cropping.

## Known pitfalls

- **Contrast depends on the image.** The front letters are `charcoal` over the
  character; a dark character fails `check`'s contrast gate (a mid-blue test
  figure gave 2.89:1). Use a lighter image or a darker `charcoal`; never
  override the gate.
- **Missing asset is a stop, not a fallback.** There is no placeholder
  character; the scaffold refuses rather than render without one.
- **The image's colours are outside the palette rule by nature**; the three
  palette colours still cover everything else on screen.
- **Width fit is estimated** (same per-glyph rule as `intro-kinetic`) and only
  shrinks; look at the snapshot for long words.
- **No beat grid.** Without a music bed the "every cut on a beat" rule has
  nothing to lock to; timing is in seconds.
