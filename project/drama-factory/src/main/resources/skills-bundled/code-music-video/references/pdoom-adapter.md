# Optional reference engine: pdoom-video

Source: [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video), inspected
at [`a048746`](https://github.com/mexicat/pdoom-video/tree/a048746d25fa0333ca884fb79fe4482b9c89250d).
Read its current `README.md`, `docs/ENGINE.md`, `app/scripts/render.ts` and
project manifest before executing. This package does not vendor the engine.

## Capability mapping

| Skill concept | Inspected upstream implementation |
|---|---|
| Runtime | Bun + Vite, TypeScript + Three.js |
| Shared clock | `Frame.t`, scene-local `lt`/`p`, `src/timeline.ts` |
| Audio cues | `data/audio.json`; `src/engine/audio.ts` beats, sections, envelopes and onset helpers |
| Lyric cues | `data/lyrics.json`; `src/engine/lyrics.ts` line/word helpers |
| Scene | A `Scene` subclass in `app/src/scenes/`, `init()` then `render(f,out)` |
| Seeking/sampling | Pure time-derived state by default; stateful reset/replay requires fixed samples |
| Preview | Vite browser application and time seek controls |
| Export | `app/scripts/render.ts`, headless Chrome, FFmpeg/libx264 |
| Resolution | Logical 1920×1080; scale 2 renders physical 3840×2160 |

The upstream JSON is **not** the v1 interchange in this package. Translate the
required information to its native layout and update audio loading, lyrics,
scene registration and timeline together. Keep original data separately until
the new track's preview works. Upstream scene-worker editing restrictions are
team conventions, not universal limits on the new project's owner.

In the inspected revision, the exporter hard-codes `audio/pdoom.mp3` in
`app/scripts/render.ts`. Replace that export input as well as the preview's
audio source and analysis data; changing only browser playback leaves the
export attached to the old track.

## Representative commands

Run from the chosen engine checkout's `app/` directory, after authorized setup
and confirmation of the actual CLI. `--only` requires a real registered entry
ID; leaving it out uses the whole current timeline.

```sh
bunx vite --port 5173
bun scripts/render.ts stills --t 0.5,1.0,2.5 --out ../out/check
bun scripts/render.ts sheet --from 0 --to 6 --n 12 --cols 4 --out ../out/check/sheet.png
bun scripts/render.ts video --from 0 --to 6 --samples 4 --out ../out/check/clip.mp4
bun scripts/render.ts video --samples auto --shutter 0.2 --out ../out/master.mp4
```

For high-resolution delivery, upstream exposes `--scale 2`; test the target
scene and memory/per-frame cost before starting a full render. Its inspected
defaults are 16:9 and 60 fps; the video CLI exposes `--fps`, but an alternative
rate still needs a sample/scene check. Arbitrary aspect ratios require engine
changes, not just a flag.

The inspected script computes segment frame counts as
`round(to * fps) - round(from * fps)`, not the generic v1 `ceil(duration * fps)`
convention. Pass frame-aligned boundaries and verify actual counts. It also
exposes `--noaudio` for video-only segments; mux one approved audio track after
joining when that fits the production plan.

Use a render server with live reload disabled, or the renderer's documented
private-server path. Export renders must wait for asset readiness. Honor
linear/HDR render targets and the engine's logical/physical pixel distinction;
switching scale without adapting text atlases or shaders can change appearance.
Check scene-error reports and the FFmpeg exit status, then inspect the encoded
file. A printed output path does not establish a successful export.

## Verification status

The upstream documentation and license were inspected. This Skill's validator
and sample are exercised locally. No upstream full-MV render, Windows engine
compatibility, real-time preview throughput or 4K performance is certified by
this package. Measure those in the actual production environment.
