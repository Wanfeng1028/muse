# Source and transfer notes

## Inspectable reference

- Project: [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video)
- Inspected revision: `a048746d25fa0333ca884fb79fe4482b9c89250d`
- [README](https://github.com/mexicat/pdoom-video/blob/a048746d25fa0333ca884fb79fe4482b9c89250d/README.md): architecture, analysis route, preview/export and separate asset rights.
- [ENGINE.md](https://github.com/mexicat/pdoom-video/blob/a048746d25fa0333ca884fb79fe4482b9c89250d/docs/ENGINE.md): time-derived scenes, seeking, sampling, scale and scene authoring.
- [render.ts](https://github.com/mexicat/pdoom-video/blob/a048746d25fa0333ca884fb79fe4482b9c89250d/app/scripts/render.ts): capture commands, resolution, segment frame counts and export audio input.
- [License](https://github.com/mexicat/pdoom-video/blob/a048746d25fa0333ca884fb79fe4482b9c89250d/LICENSE): MIT, copyright 2026 Giacomo Magnanini; music/lyrics/fonts have separate rights as described in the README.

No upstream engine source, creative treatment, songs, lyrics or fonts are
included. This is an independently written workflow package, not an official
upstream release. Its JSON schema and validation code are original to this
package and are not drop-in substitutes for upstream data.

## What transfers

| Observation | Reusable mechanism | Use condition / failure check |
|---|---|---|
| Preview and export share a time-addressable scene evaluator | Use one audio clock and repeatable state | Compare identical-time captures with matching settings; history-dependent state needs reset/replay. |
| Beat, section and lyric data drive the edit | Separate analysis data from scene implementation | Check cues against the selected audio; replacing a track invalidates old timings. |
| Stills, sheets and short clips isolate scene problems | Validate before a costly master render | Stills assess composition; only moving, audio-backed playback can approve sync and motion. |
| Modules reuse engine tooling while the timeline controls order | Separate scene logic from sequencing | Registered windows must cover the intended excerpt; missing entries can produce black output. |
| Physical output scale and logical layout are distinguished | Verify pixels rather than assuming a quality label | Check dimensions and appearance at target scale; 4K labeling alone proves nothing. |

These mechanisms are workflow hypotheses transferred from one inspectable
project, not measured universal efficiency or quality improvements. The
reference's reported machine timings do not predict another machine's render
speed.

## Minimal transfer exercise

Use an original six-second audio excerpt and one simple scene in a chosen
renderer. Hold geometry, resolution, seed and audio fixed. Compare a scene
driven by wall-clock playback accumulation with one evaluated directly from
music time. Render a hit time by direct seek, forward playback and backward
seek. The measure is agreement of matching-time captures on that runtime,
then audible alignment in the exported excerpt. A mismatch refutes repeatability
for that implementation; investigate state and sampling before scaling up.

Only timeline validation is supplied as executable code here. This exercise
requires a renderer and audio supplied by the user; it is not a prerecorded
performance result.
