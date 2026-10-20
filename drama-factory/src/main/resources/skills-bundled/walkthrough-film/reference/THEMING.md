# Theming — many skins from one tree

The goal: a second brand, a light version, or a whole new ground is a **URL parameter**, and every
earlier version still renders pixel-identical.

## The switch

```js
// engine.js, at parse time — BEFORE any module reads window.__THEME
const Q = new URLSearchParams(location.search);
const T = Q.get('theme') || 'dark';
window.__VARIANT_B = (T === 'darkorbit');                       // derived feature flags
window.__ORBIT     = (T === 'lightorbit' || window.__VARIANT_B);
window.__THEME     = window.__ORBIT ? 'lightui' : T;            // the CSS theme this variant reuses
for (const c of ['theme-' + window.__THEME].concat(window.__ORBIT ? ['theme-orbit'] : [])) {
  document.body.classList.add(c);
  document.documentElement.classList.add(c);                    // BOTH: see "load order" below
}
```

A variant is therefore two things: a **CSS theme** (which token block applies) and a set of **feature
flags** (which extra code runs). Variant 6 in the source production was "the pale-UI theme + flow
ground + reference text motion", i.e. one CSS theme and two flags — no CSS fork at all.

## Token tables

Declare the complete palette once per theme. Everything else uses `var(--…)`; **no hard-coded ink,
ground or glass value may exist outside the token sheet.**

| token | dark | light | white-UI-on-shifting-ground |
|---|---|---|---|
| `--bg` | `#07050f` + hero glow | `#f7f5fd` + drifting blobs | dynamic: pale ↔ deep (written per frame) |
| `--txt` / `--dim` / `--faint` | `#f6f4ff` / `#b3adcf` / `#7c7794` | `#1c1633` / `#4c4668` / `#7c7794` | dynamic, lerped by phase |
| `--grad` (payoff word) | light-on-dark gradient | dark-on-light gradient | dynamic, switched at phase .5 |
| `--glass-bg` | tint gradient + `rgba(255,255,255,.06)` | tint + `rgba(255,255,255,.55)` | **opaque white** `linear-gradient(180deg,rgba(255,255,255,.96),rgba(255,255,255,.84))` |
| `--glass-border` | `rgba(<accent-pale>,.30)` | `rgba(<accent>,.18)` | `rgba(255,255,255,.9)` |
| `--glass-hi` | `inset 0 1px 0 rgba(255,255,255,.28)` | `inset 0 1px 0 rgba(255,255,255,.8)` | `inset 0 1px 0 #fff, 0 0 0 1px rgba(<accent>,.18)` |
| `--line` / `--line2` | `rgba(255,255,255,.12/.2)` | `rgba(28,22,51,.12/.2)` | dynamic |
| `--ok` / `--bad` | `#22e6a8` / `#fb923c` | `#0ea472` / `#f97316` | light values |
| `--fill` (pills, bars) | `#8b5cf6` | `#7c3aed` | `#7c3aed` |
| `--blur` | `blur(40px) saturate(180%)` | same | `blur(30px) saturate(160%)` |

Extra tokens worth declaring rather than inlining, because section-1 motion writes them onto surfaces:
`--ink-soft` (skeleton bars, redacted blocks), `--ciph` (cipher fragments, carets), `--dot` (window
chrome traffic lights), `--shade0/--shade` (a surface losing its ink), `--hl` (the sweep behind a
kinetic payoff word).

## Card-scoped ink

When the theme puts **white cards on a dark ground** (or the ground changes under fixed cards), the ink
tokens must mean two different things at once. Solve it by re-declaring the ink block **on the surface
element itself**:

```css
html.theme-x .cardink,
html.theme-x .threat-card, html.theme-x .tile, html.theme-x .appwindow {
  --txt:#1c1633; --dim:#4c4668; --faint:#7c7794;
  --line:rgba(28,22,51,.12); --dot:rgba(28,22,51,.22);
  --grad:linear-gradient(100deg,#7c3aed 10%,#6366f1 55%,#a855f7 95%);
}
```

Anything inside such a surface inherits dark ink; anything on the ground inherits the frame ink, which
may be animating. Each file owner adds the rule for **their own** surfaces — a central list rots.

Include the app/dashboard window wrapper in that list: its chrome (title strip, traffic lights) sits on
the white glass, not on the ground.

## The load-order trap (reading theme flags at parse time)

Two failures, both of which look like "the theme half-applied":

1. **A module that runs at load reads `window.__THEME` before the engine set it.** The engine usually
   loads last (it needs the other modules' globals). Any module that branches on the theme must do so
   **inside `draw()`/`update()`**, or the engine must set the flags in a tiny inline script in the HTML
   before any module tag. Same problem for `$`/`$$` helpers defined in the engine: a module executing at
   load must define its own.
2. **A token block declared on a selector that matches both `<html>` and `<body>`.** If a per-frame
   writer sets inline custom properties on `documentElement`, a declaration on `body.theme-x` shadows
   them for the whole subtree and the dynamic tokens appear frozen. Declare the dynamic block on
   `html.theme-x` **only**; keep `body.theme-x` for static rules.

## Per-frame token writing (a ground that changes during the film)

For a ground that shifts phase mid-film, add a module the engine calls before the scene draws:

```js
window.GROUND = { update(gt) { /* pure function of gt */ } };
```

- **Phase** `k(gt) = smoothstep((gt-UP0)/(UP1-UP0)) - smoothstep((gt-DN0)/(DN1-DN0))`, with the window
  edges read from `timing.json` scene starts. One smoothstep per shift; non-overlapping windows make
  the subtraction exact.
- **Ground layers** crossfade by `k` (set A opacity `1-k`, set B opacity `k`) over an element whose own
  background is the interpolated `--bg`, so the composite is opaque at every `k` and the dissolve has no dip.
- **Ink flips fast.** A linear ink lerp holds the text at roughly the ground's own luminance for a few
  tenths of a second in the middle and it reads as a flash of illegibility. Remap: `k' = smoothstep((k-.45)/.2)`
  — the ground crosses over ~3.5 s, the ink over ~0.5 s.
- **Emit hex** for tokens that other modules parse as hex (a `mix()`/`alpha()` helper that slices
  `#rrggbb` will break on `rgb(...)`), and `rgba()` for the ones used as-is.
- **Only write when the phase moves.** `k` is flat for most of the film; skip the writes when
  `k === lastK` so the root's custom properties are not invalidated every frame.
- In any other theme, `update()` is a **no-op and creates no element** — that is what keeps older
  versions byte-identical.

## Assets per theme

Choose the asset at the point of use, from the theme, never at parse time into a module-level const:

```js
const wordmark = (window.__THEME === 'lightui') ? 'wordmark_dark.png' : 'wordmark_white.png';
```

Keep class names and element boxes identical across themes — other modules measure them
(`getBoundingClientRect` on a logo slot to fly a mark into it). Swapping an `<svg>` for an `<img>` is
fine as long as the box and class survive.

## Proving no regression

Any theme round must end with, for every owner:

```bash
node scripts/play.mjs 14                    # default theme  -> errors: 0
THEME=light node scripts/play.mjs 14        # every other shipped theme -> errors: 0
THEME=<new> node scripts/shots.mjs <dir> <your frame times>
node scripts/shots.mjs <dir-old> <one frame in your area>   # LOOK at it: nothing moved
```

Plus a grep for forbidden words (old brand names, banned punctuation) over the files you touched.
