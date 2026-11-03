# Scene handoff contract

Canvas 1920x1080 @ 30fps. Each scene is `src/scenes/S<n>.tsx`, default-exporting a React
component with no props. Inside, `useCurrentFrame()` is scene-local (0..dur-1).
Timing lives in `src/timeline.ts` (`SCENES`, `CUES`). Visual events MUST land exactly on cue
frames — audio is synthesized against them. Read `DIRECTION.md` before touching a scene.

Use ONLY `src/theme.ts` (`C`, `F`, `T`, `TRACK`, `GRID`, `colX`, `HAIR`, `SHADOW_PAPER`, `DUR`,
`tween`, `settle`, `lerp`, `EASE_*`) and `src/components.tsx` (Fill, Camera, Rotor, ModelChip,
chipX, CHIP, MODELS, Meter, Headline, Accent, Reveal, TerminalFrame, TERM, HorizonBar, BAR,
StandardUsage, USAGE, PlusMark, PLUS). Never import other scenes. No new dependencies.
No images other than the rotor. Scene designers do not edit theme.ts / components.tsx.

## Style rules (non-negotiable)
- Palette: cream `#F4F0E8`, ink `#0E0E0C`, orange `#EE6018`. Orange always means Droid.
- Motion: expo-out (`tween`) or critically damped springs (`settle`). No bounce, no overshoot,
  no linear moves except constant rotation. See DIRECTION.md for durations.
- No crossfades between scenes; no fade-in-per-word; no glows, gradients, grain, particles,
  emoji, stock icons. Nothing smaller than 24px. Lines are 2px (`HAIR`).
- Every element enters from something already on screen or a masked edge (use `Reveal`).

## Boundary states (first frame of scene N must equal last frame of scene N-1)
Render the listed component with its DEFAULT props, inside `<Camera>` (which is exactly
identity on frame 0 and frame dur-1), and nothing else.

| Boundary | Exact state |
|---|---|
| S1 → S2 | Solid `C.ink` full frame, nothing else. (S1 reaches full ink by frame 172.) |
| S2 → S3 | `C.ink` bg; the 5 `ModelChip`s (MODELS order, `dark`) at `left=chipX(i)`, `top=CHIP.y` (=200). CHIP is now 300x84, gap 28, radius 18, 32px label; row spans x 154..1766. Nothing else. |
| S3 → S4 | `C.ink` bg; `<TerminalFrame />` with defaults: rect x 240, y 120, w 1440, h 840, radius 28, fill `C.inkSoft`, 2px inset border `C.orange`, chrome = 1 (header "droid   ~/acme-api" mono 26 at local (64,40) and a 2px `C.inkLine` rule at local top 104 from x 64 to 1376). Nothing else. |
| S4 → S5 | `C.ink` bg; `<HorizonBar />`: left 240, top 778, w 1440, h 4, radius 2, fill `C.orange`. Nothing else. |
| S5 → S6 | `C.cream` bg; `<StandardUsage />` with defaults: label row left 360, top 356, w 1200, h 36, mono 30, `C.graphite`, "Standard usage" left / "100%" right; Meter x 360, y 412, w 1200, h 40, radius 20, progress 1, track `C.creamDeep`, fill `C.ink`. Nothing else. |
| S6 → S7 | `C.cream` bg; `<PlusMark />` with defaults: centered (960,540), 200px, 8px stroke circle fully drawn, cross bars 120 x 8 with rounded ends, all `C.orange`. Nothing else. |
| S7 → S8 | Solid `C.ink` full frame. (S7 reaches full ink by frame 230.) |
| S8 end  | Solid `C.ink`. |
