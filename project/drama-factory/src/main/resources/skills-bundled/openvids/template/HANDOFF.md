# Scene handoff contract

The canvas is 1920x1080 at 30fps. The demo lasts 330 frames, or 11 seconds.
`src/timeline.ts` owns durations, computed starts, and scene-local audio cues.
Each scene exports a component without props. `useCurrentFrame()` is scene-local.

## Boundary states

Both neighbors render the listed shared component with default props.
`Camera` is exactly identity on the first and last frame, with zero endpoint velocity.

| Boundary | Outgoing local frame | Incoming local frame | Exact state |
|---|---|---|---|
| S1 to S2 | 89 | 0 | `C.light` background and `<LaunchMeter />` inside `<Camera dur={scene.dur}>`. Label row at x 360, y 594, width 1200. Geist Mono 30, secondaryLight. "Your next release" and "Ready". Ink meter at x 360, y 650, width 1200, height 40, radius 20, progress 1. |
| S2 to S3 | 149 | 0 | `C.light` background and `<HeroMark />` inside `<Camera dur={scene.dur}>`. The default Mark is a 160px SVG at x 880, y 440 in `C.accent`. |
| S3 end | 89 | None | Light background. Product lockup and URL remain visible. |

## Shared design values

`BRAND` in `src/theme.ts` owns the name, URL, palette, fonts, and SVG path.
`Mark` also accepts `path` and `viewBox` props.
Primary text uses Geist. Metadata uses Geist Mono. One italic word per scene uses Instrument Serif.
Lines are 2px. Text is at least 24px. There are no gradients, glows, grain, or opacity-only entrances.
Accent color identifies the product mark, not generic status.
Use `Reveal` for masked entrances and exits. Use `EASE_IN_OUT` for geometry changes.
Do not import one scene from another.

## Verification

Run `python <skillDir>/scripts/check_boundaries.py .` after a scene edit.
The checker renders scene compositions at their exact handoff frames.
Run `npm run timeline` after timing changes and before `python <skillDir>/audio/render.py . audio/score.py`.
The film includes `public/score.wav` only when that file exists.
