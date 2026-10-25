# AI Automation Society — Visual Identity

Ground truth extracted from `assets/AIS Brand Guideline Small.jpg` and `assets/AIS Logo PNG.png`. Every composition in this project MUST trace its palette, typography, and motion choices back to this file.

## Style Prompt

AI Automation Society is a technical, confident, command-driven brand — "Bloomberg Terminal meets SaaS launch." Compositions should feel like a control room coming online: deep navy canvases, sharp cyan-blue accents, monospaced tickers, clipped motion, and a single warm orange accent used only where contrast matters. Not playful. Not gradient-heavy. Not neon. The mood is precision, urgency, and authority — a community of builders who ship.

## Colors

| Token | Hex | Role |
|---|---|---|
| `--ais-bg` | `#07121c` | Primary background (deep navy) |
| `--ais-surface` | `#0d2031` | Cards, panels, surfaces |
| `--ais-surface-2` | `#195066` | Secondary surface (teal-navy) |
| `--ais-border` | `#252d33` | Borders, dividers, hairlines |
| `--ais-accent` | `#37bdf8` | Primary accent — highlights, numbers, CTAs |
| `--ais-accent-glow` | `#0307ff` | Logo outer glow (75% opacity, 50px blur) |
| `--ais-warn` | `#f09025` | Secondary accent — use sparingly for contrast |
| `--ais-text` | `#ffffff` | Primary text on dark |
| `--ais-text-dim` | `#96a2b6` | Secondary/meta text |

## Typography

- **Roboto Mono (Medium 500)** — monospace. Use for: UI labels, stats, numbers, terminal lines, pill text, URLs, CTAs.
- **Montserrat (Light 300 / Bold 700)** — sans display. Use for: headlines, body copy, taglines. Light 300 for body, Bold 700 for impact.

Pair them — never use only one. Roboto Mono labels above Montserrat headlines is the house pattern.

## Logo

- File: `assets/AIS Logo PNG.png` — white italic "AIS" wordmark with blue outer-glow, transparent bg.
- CSS glow when placed on dark: `filter: drop-shadow(0 0 50px rgba(3, 7, 255, 0.75));`
- Clearspace: half a logo-height of margin on all sides.
- Never recolor. Never stretch. Never add effects beyond the spec glow.

## Motion Rules

- **Entrance only** (per Hyperframes skill rule): every element animates in via `gsap.from()`. Transitions between scenes handle exits.
- **Easing palette:** `power3.out`, `expo.out`, `back.out(1.4)`, `power4.out` for entrances; `power2.in` for hand-offs into transitions; `sine.inOut` for ambient loops.
- **Use at least 3 different eases per scene.** Vary the feel.
- **Duration bands:** snap entrances 0.3–0.5s, headline entrances 0.5–0.8s, ambient drifts 2–4s.
- **Offset first animation** 0.1–0.3s from scene start.
- **Text stagger:** 0.04–0.08s per character for display type, 0.12–0.18s per word for headlines.
- **Numbers:** use GSAP `{innerText: N, snap: {innerText: 1}}` for count-up, add `font-variant-numeric: tabular-nums`.

## Transitions

All CSS (not shader) so scenes stay simple.

| Scene change | Transition | Duration | Ease |
|---|---|---|---|
| 1 → 2 | Zoom through | 0.35s | `power4.inOut` (climax opener) |
| 2 → 3 | Push slide left | 0.35s | `power2.inOut` |
| 3 → 4 | Push slide left | 0.35s | `power2.inOut` |
| 4 → 5 | Blur crossfade | 0.5s | `sine.inOut` (wind-down into CTA) |

Primary = push slide (60%). Accents = zoom through (opener) + blur crossfade (outro).

## Buttons

Rounded pill, transparent fill, 1.5px `--ais-accent` border, Roboto Mono uppercase, 16–18px, 14–18px vertical + 28–36px horizontal padding, subtle inner glow on hover (no hover in rendered video — used for visual weight).

Example: `[ JOIN THE SOCIETY → ]`

## Iconography

Thin stroke, 1.5–2px weight, accent-blue (`#37bdf8`), no fills. Chevron arrows (`»`), screens, charts, hearts, lightbulbs.

## What NOT to Do

1. **No full-screen linear gradients** on dark backgrounds — H.264 banding. Use solid `--ais-bg` + localized radial glow behind focal elements.
2. **No neon pinks, purples, or saturated greens.** The palette is navy + cyan + white + a single warm orange. That's it.
3. **No Arial, Helvetica, Roboto (sans), Inter, or system fonts.** Only Roboto Mono + Montserrat.
4. **No cute icons or illustrations** — the brand is command-center, not playful dashboard.
5. **No `transparent` keyword in gradients** — shader-compatible CSS rule. Use `rgba(7,18,28,0)`.
6. **No `Math.random()` or `Date.now()`** — render determinism. Use seeded PRNG if needed.
7. **No exit animations** on any scene except the final one — transitions handle exits.
8. **No stretching the logo.** Keep aspect ratio. Respect clearspace.

## File References

- `assets/AIS Logo PNG.png` — official logo
- `assets/AIS Brand Guideline Small.jpg` — the one-pager these specs came from
- `assets/brand-tokens.css` — the CSS `:root` vars imported by every composition
