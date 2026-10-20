# director-kit

Small Remotion pieces for beat-synced promos. `director-kit.tsx` needs `remotion`, React and
`@remotion/layout-utils` (`npx remotion add @remotion/layout-utils`). Copy it into the project's `src/`.

- `HeroObject` + `Stage`: a glossy transparent object slamming onto a dark stage with glow and slow rays. This is the
  look that the two most successful films used. The object is opaque from its first frame; fading it in left empty
  frames after cuts.
- `Slam`: headline that lands letter by letter. Give it `maxWidth` and `fontFamily` and it shrinks long lines with
  `fitText()` instead of clipping. Measure only after the font has loaded (Remotion's `measuring-text` rule).
- `SafeArea` and `SAFE_ZONES`: vertical text area shared by Reels, Shorts and TikTok (x 90-888, y 288-1248 on
  1080x1920). `scripts/safe_zone.py` checks rendered frames against the same numbers.
- `PunchIn`, `Flash`: cut accents. Keep `Flash` at 0.1-0.2; stronger flashes plus blur washed frames out.
- `CountUp`, `LightSweep`, `DepthBackdrop`, `useBeatPulse`, `framesPerBeat`.
- `Demo.tsx`: how the pieces sit on a 120 BPM grid, in 16:9 and 9:16. Adapt it; do not ship it.

These are starting points. Once the user approves a look, copy that film's own components into the next film of the
series; they carry more of the approved look than the kit does.

Checked with remotion 4.0.526, React 19.1, TypeScript 5.8 (`tsc --noEmit`, strict).

