# Recipe: ui-morph

A 14 s seamless loop of UI motion, 1440x1440 @ 30 fps, 120 BPM, 7 bars
(28 beats), something on every beat. One shape, never cut: every state is the
same element morphing its size, radius and colour while its content swaps
with a short blur, and a cursor drives every change with real clicks and
drags. Paper / charcoal / one accent colour, one UI face (Geist). Default
`CONFIG` = the original hand-built cut and reproduces it frame for frame.

Button -> loader -> check -> dynamic island -> music player (play/pause morph)
-> scrub the progress bar -> volume slider that stretches past max -> toggle
-> the knob becomes a liquid tab indicator -> chart that draws itself, with a
hover tooltip -> Cmd K palette -> type to filter -> Enter -> toast -> button.

## Parameters

Every key is a top-level `CONFIG` key; pass it as `key=value`. Text is
**Latin only**: printable ASCII, Latin-1 (e.g. `é è ü ß`) and `‘ ’ “ ” – — • …`,
the glyphs the bundled Geist has. Hangul, CJK or emoji are refused (they would
fall back to another font).

| Key | Type | Default | Limit / note |
|-----|------|---------|--------------|
| `buttonLabel` | text | `Get started` | **1..16** chars; button label (beat 0 and 27), shrinks to fit |
| `trackTitle` | text | `Midnight Drive` | **1..24**; island (beat 4) and player title |
| `trackArtist` | text | `Neon Coast` | **1..24**; player subtitle |
| `tabs` | list | `Daily\|Weekly\|Monthly` | **exactly 3** items, **1..10** chars each |
| `chartTitle` | text | `Active users` | **1..28**; chart heading |
| `chartData` | list | `12\|18\|15\|24\|21\|30\|27` | **6..8** plain non-negative numbers (max 6 digits, 2 decimals), at least one > 0. The tooltip shows the maximum, then the last point (the one before it if the maximum is last) |
| `paletteQuery` | text | `new` | **1..12**; typed into the palette; case-insensitive substring filter |
| `paletteItems` | list | `New project\|Invite people\|Open settings\|Search docs` | **3..5** items, **1..20** chars; the query must match at least one and filter out at least one. The first match is highlighted and "entered" |
| `toastText` | text | `Project created` | **1..24**; toast after Enter |
| `paper` | `#rrggbb` | `#f2eee6` | canvas and the light UI parts |
| `charcoal` | `#rrggbb` | `#1e1e1e` | the shape, the cursor; >= 4.5:1 against `paper` |
| `red` | `#rrggbb` | `#e5322d` | accent (check, toggle on, fills, line, caret); >= 3:1 on both others |
| `bpm` | number | `120` | **90..150**; the 28-beat skeleton scales, total = `28 * 60 / bpm` |

For a frame-exact loop the total must be a whole number of frames:
`50400 / bpm` integer (90, 96, 100, 105, 112, 120, 126, 140, 144, 150).
Other tempos render fine (110 -> 15.27 s, 459 frames) but the seam lands
between frames.

## Timeline (beats; `B = 60 / bpm`; seconds at 120 BPM)

| Beat | s | Cursor | The shape |
|------|---|--------|-----------|
| 0 | 0.0 | clicks the button (rests on it from the loop) | button squishes |
| 1 | 0.5 | drifts off | button -> 104 px circle, label blurs out, spinner in |
| 2 | 1.0 | rests | spinner arc closes into a ring |
| 3 | 1.5 | rests | circle turns red, check draws itself |
| 4 | 2.0 | rests | -> dynamic island (art, title, level bars bounce per beat) |
| 5 | 2.5 | travels to play | -> music player |
| 6 | 3.0 | clicks play | play -> pause morph (vertex lerp), progress starts |
| 7 | 3.5 | travels to the progress knob | progress runs |
| 8 | 4.0 | grabs the knob, drags right | knob grows; progress follows the pointer |
| 9 | 4.5 | releases | knob springs back, playback continues |
| 10 | 5.0 | travels to the volume knob | -> volume slider |
| 11 | 5.5 | grabs, drags to max | volume follows the pointer |
| 12 | 6.0 | drags past max | shape and track stretch (rubber band, left edge anchored) |
| 13 | 6.5 | releases | stretch springs back from where it was |
| 14 | 7.0 | travels to the toggle knob | -> toggle (off) |
| 15 | 7.5 | clicks | toggle flips red; knob edges on different springs (stretch) |
| 16 | 8.0 | travels to tab 1 | -> tab bar; the knob becomes the indicator under tab 2 |
| 17 | 8.5 | clicks tab 1 | indicator slides left, leading edge first |
| 18 | 9.0 | clicks tab 3 | indicator slides right, leading edge first |
| 19 | 9.5 | moves off | tabs open into the chart; line starts drawing |
| 20 | 10.0 | travels to the peak | line finishes, dots pop as it passes |
| 21 | 10.5 | hovers the peak | tooltip + guide line |
| 22 | 11.0 | hovers the last point | tooltip slides, value swaps with a blur |
| 23 | 11.5 | parks | chart collapses into the Cmd K bar (key press) |
| 24 | 12.0 | parks | list opens, query types, rows filter out as they stop matching |
| 25 | 12.5 | parks | first match highlighted, key hint swaps to Enter |
| 26 | 13.0 | heads home | Enter -> toast |
| 27 | 13.5 | arrives on the button | toast -> button; at 28 = 0 the loop clicks again |

Only `#stage`, `#scene` and `#music` carry timing attributes (all `0 .. total`),
written by the scaffold from `timing()`. Camera zoom per state is part of the
skeleton (`STATES` table in `index.html`). Music: kick every beat, hat every
off-beat, one pad chord per bar, a quiet UI tap on beats
0 3 6 8 9 11 13 15 17 18 21 22 23 26 (`TAPS` in `recipe.mjs`); tails past the
end are folded onto the start, so the audio loops too. No plugin SFX.

Snapshot times: one per beat at `k * B + 0.7 * B`, k = 0..27; at 120 BPM
`0.35,0.85,1.35,...,13.85` (`0.35 + 0.5k`). Add `0` and the total for the
loop check.

## How it is built

- **One clock.** GSAP tweens a setter `clock.t` from 0 to the total; the
  setter calls `render(t)`, which computes every style from `t`. No CSS
  transitions, no timers, nothing carried between frames.
- **Springs are closed-form.** A damped step response
  (zeta 0.8..0.9, overshoot at most 1.5%). A value that changes target many
  times is `base + sum(delta_i * (S(t - s_i) + S(t + T - s_i)))`: one spring per
  change, plus the same change from the previous loop. Every track must end on
  its base value (the template throws otherwise), so `value(T) == value(0)`
  with the velocity, and the loop has no seam.
- **Content windows** are springs too: content enters 0.08 s after the morph
  starts and leaves in 0.1 s when the next one begins, with a blur of
  `8 * (1 - opacity)` px, so swapped text never overlaps.
- **Direct manipulation**: while the pointer is down the value is a function of
  the pointer's position (scrub, volume, stretch); on release it springs back
  from the value it had.
- **Two-edge knob**: the toggle knob / tab indicator is `left`/`right` edges on
  separate tracks; the edge moving in the travel direction uses the fast spring.
  Active tab labels are a charcoal twin of the labels clipped to the indicator.

## Known pitfalls (from the original build)

- **No `will-change` on anything the camera scales.** The camera is a CSS
  `scale()` on `#cam`; with `will-change` Chrome keeps the text raster from one
  scale and zoomed frames go soft. The selfcheck refuses it in the template.
- **Text swap timing.** Text inside a morphing container needs its own
  enter/exit window or the old and new labels overlap mid-morph. The tooltip
  value and the Cmd K / Enter hint use the same windows.
- **Loop equality.** Proven by snapshot: `t=0` and `t=total` are pixel-identical
  (max diff 0); the last rendered frame (`total - 1/30`) differs from frame 0
  by an ordinary one-frame step with the cursor at rest. Any new tween must be
  a track that returns to its base, or a window that wraps (the button's runs
  from beat 27 to beat 29 = beat 1 of the next loop).
- **Do not drive the clock from `onUpdate`.** The runtime seeks with events
  suppressed; a callback leaves stale frames. It is a tweened setter.
- **Filter vs. list opening.** A row that stops matching on the first
  keystroke must not hide before the list has opened (a later spring target
  would win); hide times are clamped after the open.
- **Camera lag.** The camera spring is slower than the shape; a much smaller
  zoom right after a wide state can push the shape past the frame edge for a
  few frames. Keep neighbouring zooms close when changing `STATES`.
- **Intentional overlap.** The clipped tab-label twin and collapsing palette
  rows carry `data-layout-allow-overlap`, otherwise `check` reports
  `content_overlap`.
- **Lint warnings accepted** (see `verification.md`):
  `composition_file_too_large` and `nested_structure_needs_subcomposition`
  (`#scene`); single file on purpose so one `CONFIG` drives everything.
- **Colour mixing during springs** (shape charcoal <-> red, highlight fade)
  briefly blends palette colours; that is the transition, not a fourth colour.
- **Font.** `assets/fonts/geist/Geist-Variable.woff2` (copied from `templates/_shared`) (SIL OFL 1.1, `OFL.txt` beside
  it) ships in this template, not `_shared`; `snapshot` must report
  `Fonts: 1 loaded`.
