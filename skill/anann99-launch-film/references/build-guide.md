# Scene build guide (copy to `BUILD_GUIDE.md` in the project; every builder reads it fully)

Project: `<project>/video`. Remotion 4, React 19, TypeScript. 1920×1080 @ 30 fps.

## Read first
- `../STORYBOARD.md`: your scenes' exact copy, timing, assets and hits. Copy is **verbatim**.
- `../BRIEF.md`: brand, positioning, proof rules and the asset inventory.
- `src/design/primitives.tsx`, `src/design/tokens.ts`, `src/design/fonts.ts`: the shared toolkit.

## File ownership (parallel builders: this matters)
- You own **only** `src/scenes/SNN.tsx` for your scene IDs. You may also create helpers named `src/scenes/parts/SNN_*.tsx` that only you import.
- **Do NOT edit:**
  - `src/design/*`
  - `src/timeline.ts`, `src/film.ts`
  - `src/Main.tsx`, `src/Root.tsx`
  - `src/scenes/index.ts`, `src/entries/*`
  - `scenes.json`
  - other scenes' files
- If a primitive is missing or buggy, write a local version in your own parts file and report it. The director fixes shared code centrally.
- Keep the export name and signature: `export const SNN: React.FC<SceneProps> = ({ dur, start }) => …`.
- **Resuming:** if your file already contains real (non-placeholder) work, you are resuming after an interruption. Continue from it.

## Timing conventions
- `useCurrentFrame()` is **local** (0 = your scene's start).
- Convert storyboard absolute seconds with `at(abs, start)` from `../timeline`. Example: a scene starting at 16.0 s puts t = 16.5 s at local frame 15.
- `dur` is the Sequence length your scene is authored against: nominal length + 10-frame TAIL (no tail for the last scene).
- **Hand-offs are handled by `Main.tsx`:**
  - `dip` (default): your whole layer blurs out over the last ~7 frames before your nominal end, and the next scene rises in. So your content must be **complete and legible by (nominal end − 0.25 s)**, and nothing important should start in your first ~6 frames.
  - `xfade`: you keep running under the next scene's fade-in. Use it only when both scenes share a background.
  - `cut`: you end on the boundary. Resolve to black yourself if needed.
- Wrap content in `<SceneEnvelope dur={dur} inDur={10} outDur={0}>`. Use `inDur={0}` for scenes that start on a **CUT**.
- **Beats.** At 120 BPM a beat is 15 frames. Land every hit exactly on the storyboard times: word pops, card pops, counters *landing*, clicks.
- **Deterministic only.** Use `interpolate` / `spring` / `prog()`. No CSS transitions or animations, no `Date`, no `Math.random` (use `rnd(seed)`).

## Toolkit cheatsheet (`src/design/primitives.tsx`)
- **Backgrounds:**
  - `Backdrop` (tone `'base' | 'brand' | 'app'`): glow + dot field + grain + vignette.
  - Also `DotField`, `Glow`, `Grain`, `Vignette`.
- **Type:**
  - `Words text="It reads [your stack]." start size …` gives kinetic words; `[bracketed]` words get the pill highlight, and trailing punctuation stays tight. Supports `exitAt`/`exitDur`.
  - Also `MonoLabel` (step labels), `Pill`, `CountUp`, `Typewriter`.
- **Product UI:** `AppWindow` + `ShotView` + `focusAt`.
  - Captures are 3840×2160 = 2× of a 1920×1080 viewport.
  - `<ShotView src="shots/x.png" pw ph focus={rect}>` frames `rect` (viewport coords, cover-fit). Stay at ≤ ~2.2× zoom for sharpness.
  - Children of `ShotView` are overlays in the same viewport coordinates and follow the camera: `Spotlight`, `FocusRing`, your own divs.
  - **Element boxes:** `public/shots/<name>.rects.json` holds `{tag, kind, text, x, y, w, h}` per element. Example: `jq '.[] | select(.text|test("Accept"))' public/shots/review.rects.json`.
  - **Typing:** reveal `<input>_typed.png` over `<input>_blank.png` inside the textarea rect with a left-to-right clip and a caret at the wipe edge. Same geometry gives a pixel-exact result.
- **Lines:** `Connector d progress dashed id` (draw-on dashed SVG path).
- **Brand:** `BrandMark size draw fill` (logo outline-draw then fill, from `logo.ts`).
- **Cursor:** `Cursor keys=[{f,x,y,click}]` (pointer with click ripple).
- **Helpers:** `prog(frame, a, b, ease)`, `mix`, `lerpRect`, `EASE.{out,inOut,in,soft,snap}`, colours `C.*`, fonts `FONT.{sans,mono,serif,pixel}`, `TYPE.*`.
- **Springs:** use `spring({ frame, fps, config: { damping: 14, stiffness: 140 } })` for pops with overshoot.

## Render-check loop (mandatory)
```bash
cd <project>/video
node tools/stills.mjs SNN 0,30,60,90,120 0.5    # specific local frames, or 'auto' for 8 evenly spaced
npx tsc --noEmit -p .                            # errors in files you don't own aren't yours
```
- The stills tool bundles ONLY your scene (`src/entries/SNN.tsx`) and writes `out/stills/SNN/f###.png` plus a 2-column `sheet.jpg`.
- **Read the sheet and look at it critically.**
- Render the exact hit frames to verify sync, and consecutive frames (f, f+1, f+2) around fast moves to check smoothness.

## Quality bar
- **Composition:** one clear focal point per frame, generous negative space, nothing inside the 96 px safe margin, at most two caption lines.
- **Type:**
  - Captions: `FONT.sans` 56–96 px, weight 400–500, tracking −0.02em, `C.text`.
  - Step labels: `MonoLabel`, muted.
  - Numbers: tabular figures.
- **Product windows:**
  - Slight 3D tilt and a slow continuous dolly (scale 1.00 → 1.03); the camera is never fully static.
  - Push-ins ease in and out over ≥ 30 frames. Show only the part of the UI the story is about.
  - Key UI text ≥ 20 px on screen when it matters.
  - Keep demo-tenant numbers out of focus and never in headline type.
- **Rebuilt UI cards:** `C.surface` fill, 1px `C.border`, radius 14, mono 20–24 px uppercase micro-labels. Status: `C.accent` = good, `C.faint` = dimmed, `C.bad` at 70% = failed.
- **Motion:** ease-out entrances, small spring overshoot on pops, 2–4 frame staggers. Only slow drifts may be linear.
- **Readability:** every caption stays fully visible ≥ 0.35 s per word. Swap captions in place (blur-exit, then rise-in), never overlapping.

## Done when
- The scene matches the storyboard beat-for-beat, and stills at every hit time look polished.
- It typechecks, and `node tools/stills.mjs SNN auto` produces a clean sheet.
- You return: what you built, the hit frames you verified, and known issues.
