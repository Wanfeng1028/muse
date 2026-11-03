# Recipe: launch-film

A 27 s keynote-style launch film, 1440x1440 @ 30 fps, 54 beats at 120 BPM,
one continuous 2D take: every scene is made out of the previous one (no
crossfade, blur-in or cut). Paper / charcoal / one accent colour; Archivo
(wdth 62-125, weight 800) for the wordmark and display type, Geist for UI.
A cursor drives every change; the camera zooms so each moment fills the
square and the cursor scales with it. Default `CONFIG` = the original
hand-built render and reproduces it pixel for pixel. The last frame equals
the first, so the file loops.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`. All text must
be Latin (Basic Latin + Latin-1: the bundled font subsets); none of it is a
fact the recipe invents, so ask for the user's own words.

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `wordmark` | word | `Create` | **3..9** letters A-Z/a-z, one word; drawn with its period, squeezes into it at beat 0 and springs back at the end |
| `openLabel` | text | `Photos` | <= 16; rises inside the black pill; also the gallery page title and first Safari tab |
| `glassWord` | word | `Glass` | **3..8** letters; the liquid-glass word that melts into the toolbar |
| `photos` | file list | 9 placeholders | **9..12** `.jpg/.png/.webp`; `photos=a.jpg\|b.jpg\|...` copies each to `assets/<basename>` (names must differ). `photos[0]` is the hero (bento, relight), `photos[1]` the wallpaper / landing hero / print; all fill the 3x3 grid, `photos[2..]` the gallery page |
| `lockTime` | `H:MM` | `9:41` | glass clock digits |
| `lockDate` | text | `Monday 9 June` | <= 24 |
| `trackTitle` / `trackArtist` | text | `Untitled` / `Artist` | <= 28 each; the glass music player |
| `landingHeadline` | text | `Your photo, framed.` | <= 40 |
| `productName` | text | `Framed print` | <= 24 |
| `frameColors` | list | `red\|charcoal\|paper` | **2..3** distinct palette names; the molding starts as item 1, the click paints item 2 (also the frame on the wall) |
| `sizes` | list | `S\|M\|L` | **2..4** items, <= 6 chars; the click picks item 2 |
| `orderLabel` | text | `Order print` | <= 18; nav button that flies down into the order button |
| `steps` | list | `Ordered\|Printing\|On its way\|Delivered` | exactly **4**: the four states of the order shape |
| `paper` | `#rrggbb` | `#f2eee6` | warm off-white canvas |
| `charcoal` | `#rrggbb` | `#1e1e1e` | the black UI, every flood |
| `red` | `#rrggbb` | `#e5322d` | accent; must keep **3:1** on both others (refused otherwise) |
| `bpm` | number | `120` | **90..150**; the 54-beat skeleton scales (springs run in beat time) |

The placeholder photos are abstract scenes drawn for this repo
(`scripts/make_photos.py`, palette blends only). They are not the user's
photos: ask for theirs. Photos are user content, so their colours are exempt
from the three-colour rule; everything else on screen is paper, charcoal or
red (glass tint, rims and shadows are those colours at low alpha).

**Golden hour.** The relight is two aligned shots of `photos[0]`: the same
image, the second through a fixed warm colour grade (`#warm`, an
`feColorMatrix`), revealed by a wipe that follows the knob. A user photo
needs no second file.

## Beat map (`B = 60 / bpm`; seconds at 120 BPM)

| Beat | s | Cursor | Shape / scene |
|------|---|--------|---------------|
| 0 | 0.0 | rests | wordmark squeezes into its period (wdth 125 -> 62, then scale) |
| 1 | 0.5 | - | the period grows into the black pill |
| 2 | 1.0 | glides to the pill | `openLabel` rises inside the pill out of a mask line |
| 3 | 1.5 | **click** | pill becomes a circle; six iris blades close over the label |
| 4 | 2.0 | - | iris snaps open onto `photos[0]` |
| 5 | 2.5 | - | circle becomes a square |
| 6 | 3.0 | - | square shrinks to a grid tile |
| 7 | 3.5 | - | plus tiles unfold from behind it (paper-map hinges) |
| 8 | 4.0 | - | corner tiles unfold |
| 9 | 4.5 | to the hero tile | grid reflows into a bento |
| 10 | 5.0 | over the hero | (hover) |
| 11 | 5.5 | **click** | camera zooms into the hero tile |
| 12 | 6.0 | - | **drop**: the tile fills the frame exactly on the beat |
| 13 | 6.5 | - | glass word pops in letter by letter |
| 14 | 7.0 | - | letters melt (goo) into a glass droplet |
| 15 | 7.5 | to the adjust icon | droplet stretches into a glass toolbar, icons pop |
| 16 | 8.0 | **click** adjust | camera leans in |
| 17 | 8.5 | to the knob | toolbar becomes a slider, the adjust icon becomes the knob |
| 18 | 9.0 | **press** knob | knob turns into a glass lens while held |
| 19-20 | 9.5-10.0 | **drag** | wipe relights day -> golden hour under the lens |
| 21 | 10.5 | **release** | lens lifts into a glass orb |
| 22 | 11.0 | - | `photos[1]` opens inside the orb as a circle |
| 23 | 11.5 | - | orb expands into the lock screen; camera fills with it |
| 24 | 12.0 | to the home bar | glass clock digits pop, date rises |
| 25 | 12.5 | **swipe up** | home bar stretches into the glass music player |
| 26 | 13.0 | - | pull back into a phone; the bezel grows out of the screen edge |
| 27 | 13.5 | **drag** island | Dynamic Island stretches like liquid toward the cursor |
| 28 | 14.0 | release | it pinches off and flies over (camera widens) |
| 29 | 14.5 | - | the blob grows into a Mac window |
| 30 | 15.0 | to the wallpaper | its cover rolls up like a blind into the title bar (Safari gallery) |
| 31 | 15.5 | **long-press** | red ring fills |
| 32 | 16.0 | **drag** | the wallpaper lifts as a card and travels to the second tab |
| 33 | 16.5 | over the tab | the page pushes in (landing page) |
| 34 | 17.0 | **drop** | the card becomes the hero; headline rises |
| 35 | 17.5 | **scroll** | page scrolls, hero becomes the print; camera fills with the window |
| 36 | 18.0 | - | mat and molding grow out of the photo's edge |
| 37 | 18.5 | to a swatch | product name rises, swatches and size chips pop |
| 38 | 19.0 | **click** colour | the new frame colour paints across |
| 39 | 19.5 | **click** size | the chip fills |
| 40 | 20.0 | **click** nav button | it flies down into the order button |
| 41 | 20.5 | **click** order | camera onto the button |
| 42 | 21.0 | - | black shape: circle, `steps[0]` + check |
| 43-44 | 21.5-22.0 | - | pill: `steps[1]`, % counts, bar draws |
| 45-46 | 22.5-23.0 | - | card: `steps[2]`, pins pop, van drives the route |
| 47 | 23.5 | to the circle | circle: `steps[3]` + check |
| 48 | 24.0 | **click** | the circle floods the frame (0.35 s, past the corners) |
| 49 | 24.5 | - | holds black (the scene changes under it) |
| 50 | 25.0 | to the print | black contracts into the framed print on the wall |
| 50.5 | 25.25 | **click** | the same iris opens onto the print |
| 51.5 | 25.75 | **click** | it closes again |
| 51.9 | 25.95 | **click** | the frame floods the screen (0.3 s) |
| 52.3 | 26.15 | returns to rest | the black contracts into the pill (0.3 s) |
| 52.9-53 | 26.45-26.5 | - | pill -> period; letters spring back out, settled by 53.91 |
| 54 = 0 | 27.0 | rests | loop: the last frame (27 - 1/30 s) equals frame 0 |

Root `data-duration`, `#film` and `<audio id="music">` timing are static
attributes the scaffold writes from `bpm` (54 beats); never edit them by hand
(`scaffold.mjs --update`). Music: kick every beat (soft in the open, full
from the drop, quiet in the wall breakdown, full again on beat 53), the drop
on beat 12, synthesized UI sounds on the cursor's beats; no fade, so it loops.

## How it is built (one file, a pure function of time)

- One SVG; one GSAP tween drives a proxy whose setter calls `render(beat)`
  (the runtime seeks with events suppressed, so `onUpdate` is not used).
  Every attribute is computed from time inside that call: no CSS
  transitions, no timers, no state between frames.
- Every animated value is a track `[v0, [beat, value, kind], ...]` and its
  value is the **sum of one response per change**: a closed-form spring step
  response (time in beats, so the skeleton scales with `bpm`), an eased
  segment that lands exactly, or an instant set. Springs snap to their
  target once the envelope is below 1e-5, which is what makes the last frame
  equal the first.
- Helpers: `glass()`, `iris()`, the goo filter, the flood (one screen-space
  shape), the camera (`[cx, cy, zoom]` track) and the cursor (screen-space
  track; targets in the world are converted with the camera at that beat;
  anything dragged follows the cursor).
- **Liquid glass:** each glass element holds its own clone (`<use>`) of the
  scene behind it (the photo layer, or the lock-screen wallpaper), masked by
  the glass shape. The filter blurs that shape's alpha into a distance-like
  field, takes its gradient (two offset differences) as the displacement
  map, runs three `feDisplacementMap`s at 1.00 / 1.07 / 1.14 scale and keeps
  R, G, B from one each (chromatic edges), and adds a paper rim light from
  the map's top-left / bottom-right slopes, a paper (or charcoal) tint and a
  soft charcoal shadow.
- **Iris:** 6 blades around a hexagonal aperture; blade i = vertices v_i,
  v_i+1, the extension of edge i past v_i+1, the extension of edge i-1 past
  v_i and the short arc between them; the hexagon twists as it closes.
- **Goo:** blur + alpha threshold, then the source composited atop (droplet,
  island, glass word melt).
- **Wordmark squeeze:** every letter moves toward the period by the same
  factor and its drawn width follows: the wdth axis narrows (125 -> 62,
  per-letter widths measured at seven wdth values) and scaleX does the rest,
  so the letters stay touching.
- Re-basing (camera and world reset) happens only where it is invisible: at
  beat 12 (the zoomed tile and the full-frame photo are the same pixels) and
  under full black at 48.7 and 52.3.
- The last letter spring starts on beat 53 and is exact (snapped) by 53.91,
  inside the last frame at every allowed tempo (90..150 BPM).

## Verification specifics

- Snapshot times, one per beat for review: `(b + 0.5) * 60 / bpm` for
  b = 0..53 (at 120 BPM `0.25,0.75,...,26.75`), plus `0` and
  `total - 1/30` for the loop, plus `34.88 * 60 / bpm` (16.35 at 128 BPM,
  17.44 at 120) where `landingHeadline` is whole: at beat 34.5 it is still
  rising behind the hero. Read every frame: strings exactly as
  confirmed, no tofu, the shape of each beat as in the table.
- Accepted lint warnings: `composition_file_too_large` and
  `nested_structure_needs_subcomposition` on `#film` (single file on purpose
  so one `CONFIG` drives everything). `check` must pass with 0 layout
  errors; contrast 12/12. The tab labels and the nav wordmark carry
  `data-layout-allow-overlap` (two masked copies of one label; the page
  push).
- `verify-render.py renders/video.mp4 --duration <total> --bpm <bpm>
  --width 1440 --height 1440`: h264 1440x1440 30/1, aac, duration, peak
  (the bed is normalised to -1 dBFS), kick grid.
- Loop: the frame at `total - 1/30` must equal frame 0 (pixel max diff 0).

## Known pitfalls (from the original build)

- **feImage maps are ignored by `feDisplacementMap` in Chromium.** Both an
  element reference and a data-URL image (e.g. a canvas distance field)
  render as an untouched source, so the brief's "SVG feImage displacement
  map" and "canvas distance field per glyph" could not be used as given.
  The map is derived in-filter from the glass shape's own alpha instead
  (same for glyphs, the droplet and the rounded rects, so it also follows
  every morph). `backdrop-filter: url()` is not used either: the clone is.
- **feImage of an element is offset** by the filter region's origin in
  Chromium; another reason not to use it.
- **`arithmetic` composites touch alpha too.** `k2*a + k3*b + k4` with
  `k4 = 0.5` halves the alpha; the gradient is built as `0.5*a + 0.5*(1-b)`
  so alpha stays 1.
- **Glass edges tinted by transparent samples.** The clone is masked by the
  shape dilated by the displacement range and the filter erodes the alpha
  back, so no displaced sample is transparent.
- **Thin glass streaks.** A 48 px slider with the toolbar's displacement
  smeared the photo grain; the displacement scale follows the shape height.
- **Text in a morphing shape.** Every label and icon in the order shape sits
  in its own clipped group and slides in/out through the shape's edge; a
  label that only moves stays visible as the shape grows.
- **Floods** overscale past the corners and take 0.6-0.7 beat (0.3-0.35 s at
  120) with a sine in-out ease (peak speed 1.57x the mean; an ease-out or a
  cubic in-out changed half the frame in one frame: the render's
  frame-difference check found a 140/255 jump on the contraction). Scene
  changes happen only under full black.
- **A `set` must apply on its own beat**; otherwise a frame landing exactly
  on that beat shows the previous shape for one frame.
- **Heading from a collapsing chord.** The van's angle came from a 2-unit
  look-ahead that collapsed at the end of the route and snapped it upright in
  one frame; the chord is now clamped inside the path.
- **Hidden copies still fail contrast.** The paper copy of a tab label under
  the paper active tab read as 1:1; it is clipped to the complement of the
  active tab (even-odd path) instead of being covered.
- **Photos must decode before the timeline registers** (every `<image>` load
  is awaited, an error stops the build with the photo's path).
- **Wall footage** is not used: the wall is procedural (paper, soft charcoal
  plant shadows as a pure function of time). A real wall clip (`wall=<mp4>`)
  is a possible future parameter, out of scope.
- **No motion blur.** Rendered at 30 fps through the official CLI only.
