# Motion language: jitter and product presentation

Every helper below is in `studio/src/motion/lib.ts` (from the skill's `engine/`). All are pure functions of `t`.

## The jitter kit (the house style: simple + jitter)
"Jitter" = motion that feels hand-cut and energetic rather than smooth and corporate. Use 2–3 of
these per piece, not all at once.

| Technique | How | Helper |
|---|---|---|
| **On twos** (stop-motion timing) | Hold each pose 2 frames at 24fps (12 drawings/s). Apply to type, stickers, illustrations; keep UI and camera smooth for contrast | `stepped(t, 24, 2)` |
| **Boil** | Static elements shift ±1–3px and rotate ±0.5° every step, seeded | `boil(t, seed, amp)` |
| **Impact shake** | Camera or element shakes for 0.2–0.3s after a hit (stat lands, button pressed, logo slams) | `shake(t, at)` |
| **Snap + motion blur** | Cards fly in fast with blur proportional to speed, settle with a tiny overshoot | `snapIn(t, at)` → `filter: blur()` along the axis |
| **Montage burst** | 4–8 crops of the product at 0.1–0.25s each, slightly rotated or tilted, on a beat run | `montageIndex(t, start, len, n)` |
| **Letter pop** | Letters appear one by one with random scale 0.8–1.2 and rotation ±6°, on twos | `stepped` + `rng` per letter |
| **Hard cut on beat** | No crossfades. Cut, snap, or flash. | beat grid |

Rules: jitter carries **type, stickers and transitions**. UI content stays crisp and readable
(no boil on body text). Shake only on real impacts, max one per ~3s.

## Product presentation patterns (from a Figma design or real UI)
| Pattern | Beat | Notes |
|---|---|---|
| **Kinetic headline** | 1.5–3s | Line-mask word rise (`riseWord`); last phrase in accent; or a jitter letter pop |
| **Typed prompt** | 2–3s | Input field, `typed()` at ~28 cps, caret blink (`caretOn`), send button press + glow |
| **Snap-in card** | 0.5s in | `snapIn`, then content fades in after the card lands (`swapAlpha`) |
| **One container, many states** | 2–6s | Button → loader → success → card: one element springs size/radius/fill (`track`); a cursor causes each change |
| **Cursor narrator** | always | SVG cursor (arrow or pixel); moves on a `track` with the snappy spring; click = scale 0.92 + ripple + click SFX; name tag for multiplayer |
| **Camera over UI** | 2–4s | Place the full screen (a Figma frame export) big; animate translate/scale on springs to push into the region that matters; highlight it (a marker swipe behind the text) |
| **Word swap in a sentence** | 2–3s | "Chat with [X]": the pill resizes on a spring (`track` on width), old word slides up and out, new one slides up and in |
| **Stat hero** | 1.5–2s | Counter rolls up (`track` with the heavy spring + `Math.round`), huge in accent, small caption; shake on land |
| **Stack / list build** | 2–3s | Rows stagger in (`stagger`), the checklist ticks green on beats |
| **Phone / browser mockup** | any | Real screens inside a simple rounded frame; parallax: frame and content on different springs |
| **End card** | 2–3s | One line + logo. The logo resolves by letters typing, or a dot expanding into the mark; URL small under it |

## Pacing
- Something new every 1–3s (jitter pieces) or 2–4s (calm premium)
- Hook in the first 2s: the problem or promise in ≤6 words of huge type, or the most striking
  product moment
- 15–30s for social, 45–60s for a launch film
- Hard cuts on beats; the last frame can loop to the first

## Banned defaults
Centred title on a gradient as the main idea, everything fading in, corner labels and frame
borders, glows on UI chrome, generic particle bursts, invented UI that doesn't exist in the
design, more than one display face and one UI face, more than one accent colour.
