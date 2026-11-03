---
name: mark-driven-ground
description: >-
  A background that is built AROUND the element travelling through the frame — a logo, a dot, a
  cursor. Per-beat path rings centred on the landing point, the flight path drawn on the ground,
  a lit arc that follows the mark and collapses into the landing, a wide soft glow that blooms
  where it lands and settles for the rest of the chapter, and a colour TRACK that walks the whole
  frame from one chapter's colour to the next. Use when a background feels decorative rather than
  connected to the motion, when each section needs its own colour without a visible cut, or when
  a reference reel has a spark/dot that the background reacts to. Triggers: "background that
  follows the logo", "rings the dot travels along", "glow where it lands", "colour changes per
  chapter", "smooth flowing colour fields", "make the background react to the travelling element",
  "the background should know where the mark is", "spark-driven background".
---

# Mark-Driven Ground

Family **B** of the **motion-graphics** super-skill, but a different idea from the rest of it: the
other background moves are *ambient* — they drift whether or not anything else happens. This one is
**coupled to a travelling element**. Everything on the ground is derived from where the mark starts,
where it lands, and when.

The result is that a title card stops being "text on a gradient" and becomes one event: a mark flies
in, the ground draws the route it took, the light follows it, and where it stops the whole frame
takes that section's colour and keeps it until the next mark lifts off.

Drop-in: `assets/ground.js` + `assets/ground.css`. Standalone demo: `assets/demo.html`
(open it directly, `file://` is fine; `?t=2.1`, `?theme=dark`).

```html
<link rel="stylesheet" href="assets/ground.css">
<script src="assets/ground.js"></script>
<script>
GROUND.init({
  stage: document.querySelector('#stage'),   // the ground is inserted as its first child
  w: 2560, h: 1440,                          // the design space; all coordinates are px in this grid
  theme: 'light',                            // 'light' | 'dark'
  track: [[0,'#c4b5fd'],[46,'#a5c8ff'],[75,'#3b7bf0'],[117,'#e06ab8'],[158,'#8c57ff']],
  marks: {
    one: {S:{x:318,y:274}, LP:{x:557,y:764}, acc:'#3b7bf0', path:'zip',   t0:46.2, dur:2.4, end:74.8},
    two: {S:{x:318,y:274}, LP:{x:555,y:765}, acc:'#c24fc0', path:'drop',  t0:74.8, dur:2.4, end:98.1}
  }
});
</script>
```
Then, once per frame, from **your** clock:
```js
GROUND.update(t);                 // one frame of ground
const m = GROUND.markAt(t);       // {x,y,size,acc,id} — position YOUR mark from the same sampler
```
`GROUND.update` is a **pure function of `t`**: no timers, no rAF inside, no frame-to-frame state.
Drawn twice with the same `t` it produces the same pixels, so seek-and-shoot rendering
(`smooth-render`) is frame-exact — and any one scene renders identically whether or not the scene
before it was ever played.

---

## The method

Per **beat** (one mark's flight + the chapter it opens):

1. **Measure S and LP once.** `S` = where the mark lifts off (usually the previous scene's logo
   slot); `LP` = where it lands (usually a fixed offset left of the heading's first line). Measure
   them once in the real layout and then **hard-code them into a table**. Do not re-measure per
   render — that is what makes a single-scene render match the full-film render.
2. **Draw the route.** Sample the mark's own path function at 120 points into an SVG `path`, and add
   **two circles centred on LP**: radius `R = |S − LP|` (the flight distance) and `0.62 R`. The
   rings are literally the geometry of the flight, so they always feel placed rather than decorative.
3. **Light the arc behind the mark.** One stroke, the section's colour, with a dash *window* that
   ends where the mark is and runs `0.32 · L` behind it. After the landing the window's tail slides
   forward into the head over 1 s while the stroke fades — the light is absorbed by the landing.
4. **Bloom the glow.** A wide soft field of the section's colour rides the mark during the flight,
   blooms bigger at the landing, then over 2.2 s **settles down-left**, clear of the headline, and
   drifts there for the whole chapter. The *previous* chapter's field stays at its own landing point
   and fades over this beat + 4 s, so two colours overlap for a few seconds instead of cutting.
5. **Between beats, run the track.** Outside the chapters three fields carry `C(t+lead)` / `C(t)` /
   `C(t−lag)` — the next colour is already arriving on one field while the last one is still leaving.

Everything else on the ground (a pale dot grid with a brightness wave, a few slow orbit rings) is
ambient texture that never changes with the mark. It exists so the frame is not empty between beats.

---

## The maths

All eases are one-shot functions of the beat's local time `lt = t − t0`. `T_IN` is the flight
duration (`flight`, default 0.7 s), `dur` the title beat, `end` the moment the chapter hands over.

```
smoothstep(u)  = x·x·(3 − 2x),  x = clamp(u,0,1)      // the only ease that needs to be exact
seg(t,a,b)     = clamp((t − a)/(b − a), 0, 1)
lerp(a,b,p)    = a + (b − a)·p
```

**k phases** — the four that matter, all independent, none of them cumulative:

| phase | formula | drives |
|---|---|---|
| flight | `pe = clamp(lt / T_IN, 0, 1)` | the mark's position on the path, the arc head |
| ring in / out | `fin = min(1, lt/.5)`, `fout = clamp((end − t)/.6, 0, 1)` | ring opacity `(inBeat ? .55 : .30)·fin·fout` |
| bloom | `e = smoothstep((lt − T_IN)/.7)` | glow diameter `.66w → .86w` |
| settle | `e2 = smoothstep((t − (t0+dur))/2.2)` | glow centre `LP → LP + (−.102w, +.299h)` |

**Dasharray window (the lit arc).** `L` = `path.getTotalLength()`, measured **once** per mark:
```
head = pe · L
tail = max(0, head − 0.32·L)
if (lt > T_IN) { q = min(1,(lt − T_IN)/1); tail = lerp(tail, head, q); opacity = 1 − q }

stroke-dasharray  = (head − tail) + " " + 2L      // ONE dash, longer gap than the path
stroke-dashoffset = −tail                        // push it along to sit behind the mark
```
Write it this way, **not** as `"0 tail win 2L"`: a zero-length leading dash with
`stroke-linecap:round` paints a visible dot at the start of the path.

**The colour track `C(t)`.** A piecewise-linear walk through `[time, colour]` pairs placed at the
**chapter midpoints** (not the boundaries — you want each chapter to be *fully* its colour in the
middle and already becoming the next one at its end):
```
C(t): find the pair i with t ≤ track[i][0];
      return mixHex(track[i−1][1], track[i][1], (t − track[i−1][0]) / (track[i][0] − track[i−1][0]))
```
**Colour lerp** is per-channel in sRGB — good enough at these saturations, and it is what keeps the
fields cheap (one `radial-gradient` string per field per frame, no canvas, no filters):
```
mixHex(a,b,p) = '#' + a.channels.map((v,i) => round(v + (b.channels[i] − v)·p)).hex()
```
**Three fields, one track.** Field 0 carries `C(t + lead)` (12 s ahead), field 1 `C(t)`, field 2
`C(t − lag)` (9 s behind). Give them different drift periods (47/53/59 s on x, 61/67/71 s on y) so
they never beat against each other.

**Rings and glow sizes** are fractions of the design width so the ground scales to any stage:
flight glow `.43w → .66w`, landing `.86w`, ambient field `.66w`, ring stroke `w/640`, arc stroke
`w/160`, dot grid `w/53`, wave tile `1.64w`.

---

## The dot grid and its wave

The grid is two identical layers: `.mg-dots` (resting, ~22 % alpha) and `.mg-wave` (the same dots at
~55 %) behind a `linear-gradient` mask a single tile wide. Only `mask-position` animates — one tile
per period (12 s), so it repeats exactly:
```js
maskPosition = ((t / 12) % 1) * tile + 'px 0px'
```
**The dots themselves never move.** Translating the grid reads as the camera moving; moving the mask
reads as light passing through a fixed field, which is what you want under a travelling mark.

---

## Dark and light

| | light ground | dark ground |
|---|---|---|
| ground | `#f7f5fd` (or a slightly deeper lavender mist `#ece8f6` — white reads as "unfinished page") | `#07050f` + a hero glow `radial-gradient(110% 70% at 50% 122%, …)` |
| ink | dark on the ground, dark inside white cards | light on the ground, **dark inside white cards** (see `glass-cards`, card-scoped ink) |
| rings | `rgba(124,58,237,.16)` | `rgba(196,181,253,.22)`, and ring opacity ×1.6 — thin violet lines vanish on black |
| track colours | as authored, or 12 % toward white at low strength | pulled 55 % toward a deep violet (`darkPull`), otherwise mid-saturation hues go **grey** on black |
| product glows | pure accent | lightened ~30 % toward white (`glowLift`) so they read as *light*, not as paint |

Set `theme:'dark'` and both the CSS variant and those numeric defaults switch together;
override any of them (`bg`, `darkPull`, `darkPullAmt`, `glowLift`) per project.

## Strength levels

`strength: 1…4` — how much of the frame the colour owns:

| level | fields | reads as |
|---|---|---|
| 1 | colour softened 12 % toward white, opacity .8 | a **tint**; the ground still reads as paper |
| 2 | pure colour, opacity .9 | colour, still clearly a background |
| 3 | pure colour, opacity 1 | the default: the frame is in the section's colour |
| 4 | +25 % field diameter, a 14 % solid core then a long fade | **bold**: the colour is the subject, type sits on it |

Level 4 is the one that needs the gentle falloff (below) — at that size a hard-edged field is
unmissable.

---

## Pitfalls (each of these cost a re-render)

- **Smooth vs patchy.** A field built as a *solid plateau* with a hard stop (`colour 0 55%,
  transparent 60%`) plus a small blur looks like a **patch** at any size — you can see where it ends.
  A field with a **small core and a long falloff** (`colour 0%, colour 14%, transparent 76%`) reads as
  a wash even with no blur at all. Fix the falloff first; blur is the last 5 %.
- **Blur is optional and expensive.** The production build used `blur(110–140px)`, but headless
  Chromium/Edge software-rasterizes `filter:blur()` and capture drops to ~5 fps. This module defaults
  to `blur: 0` and gets its softness from the gradient. Only pass `blur` if your renderer can afford
  it — and if you do, *increase* it rather than tightening the gradient.
- **Swap geometry only at opacity 0.** Change the path `d` and the circles' `cx/cy/r` while the rings
  are still fading in (the first .5 s of a beat). A swap at full opacity is a visible jump.
- **`getTotalLength()` once per mark**, cached. Per frame it is a layout read in the middle of a
  paint-only loop.
- **Zero-length dash + round cap = a dot.** See the dasharray note above.
- **Park the glow clear of the text.** Left where it lands, the field sits exactly under the heading
  and washes it out. The 2.2 s settle to down-left exists for that reason alone — pick the direction
  that is empty in *your* layout.
- **Don't rewrite custom properties every frame** if the value has not moved. Quantise driving values
  to 1/1000 and skip the write when unchanged; at 8-bit colour depth the output is identical and you
  stop invalidating the whole tree.
- **No wall clock, no timers, no easing that reads the previous frame.** Anything stateful makes
  scrubbing and rendering disagree, and makes a per-scene render differ from the full pass.
- **One ground element, under everything.** Insert it as the stage's first child and let the content
  sit above it. Grounds composited *inside* a camera-transformed world expose their edges on any
  pan or zoom.

---

## Composes with

- **text-motion / kinetic-typography** — the mark that drives this ground is usually also the
  **cursor** of a typewriter headline (see "A″ · Spark-driven text" in
  `../motion-graphics/PLATTER.md`). `GROUND.markAt(t)` and the typewriter's cursor position are the
  same object: hand the cursor point to your mark between the landing and the end of the typing, and
  the ground keeps drawing around it for free.
- **glass-cards** — white glass floating on this ground is the pairing it was built for; keep the
  card ink dark (`.lcard.white`).
- **backgrounds-gradients** — the ambient family B moves; this skill is the coupled version, and
  that skill's "Colour flow track + smooth fields" section points back here.
- **smooth-render** — the reason everything here is a pure function of `t`.
- **vo-sync** — set each mark's `t0` from the VO cue so the flight lands on the spoken section name.

## API

| call | does |
|---|---|
| `GROUND.init(cfg)` | builds the ground inside `cfg.stage` and returns the API |
| `GROUND.update(t)` | draws one frame |
| `GROUND.markAt(t)` | `{x, y, size, acc, id, landed, p}` or `null` — position your own mark |
| `GROUND.colorAt(t)` | the track colour at `t` (use it to tint anything else in the frame) |
| `GROUND.fit()` | re-scale to the stage (also automatic via `ResizeObserver`) |
| `GROUND.destroy()` | remove it |

`cfg`: `stage`, `w`, `h`, `theme`, `marks`, `track`, `strength`, `blur`, `lead`, `lag`, `flight`,
`dur`, `arc`, `bg`, `glowLift`, `darkPull`, `darkPullAmt`, `ambient`, `settle`, `wavePeriod`,
`grid`, `waveTile`, `fields`, `rings`, `dots`, `wave`.
Each mark: `{S, LP, acc, path, t0, dur, flight, end, size0, size1}`; `path` is one of
`line · zip · drop · spiral · hops · orbit` or your own `(p, LP, S) => {x, y}`.
