---
name: remotion-particle-film
description: Build and export procedural particle films with Remotion - one deterministic GPU particle population morphing through a scripted act map - including the proxy QA pass and the final master MP4 render. Use for starfield, galaxy, accretion-disk, black-hole and particle-title sequences; not for footage editing, slideshows, or ordinary motion-graphics overlays.
metadata:
  short-description: Build Remotion particle films
---

# Remotion Particle Film

Produce films like the ones in `media/`: tens of thousands of GPU particles, one continuous
camera move, no scene cuts - authored as a pure function of the frame number, checked at low
resolution, and only then rendered full size.

## Two invariants

**Everything derives from the frame number.** `computeFrameState(t)` in `src/timeline.ts` is the
only source of motion: no `Date.now()`, no `Math.random()` at render time, no CSS animation.
Particle jitter comes from a hash of the particle index. This is what makes a QA pass evidence
rather than noise - the same frame always produces the same pixels.

**One population, never scenes.** There is no `<Sequence>` and no per-particle DOM node. The film
is a single vertex buffer whose target distribution changes over time, and each act grows out of
the previous one because every particle interpolates on its own staggered schedule. When a
transition feels flat, widen the blend; a scene cut is almost always the wrong fix.

## Workflow

1. Copy `assets/particle-film-starter/` into a working directory and run `npm i`. It is the exact
   project that produced `media/`, so treat it as a working reference rather than a scaffold.
2. Retarget `src/config.ts` (resolution, fps, particle count, act map, world constants) and
   `src/timeline.ts` (camera, scale, point-size, exposure and bloom tracks).
3. Run the proxy QA pass at quarter scale, before rendering anything full size.
4. Fix what the proxy reveals, then re-run it. Only sign off on the proxy you have actually looked
   at as a contact sheet.
5. Render the master and verify it against the approved proxy.

```powershell
# 3. proxy pass - a 60 s film drops from ~9 min to ~1 min
npx remotion render src/index.ts TianyuanOrigin qa\r01\motion --sequence --scale=0.25 --image-format=png
powershell -File scripts\analyze-frames.ps1 -Dir qa\r01\motion -OutCsv qa\r01\motion.csv

# 5. master + verification
npx remotion render src/index.ts TianyuanOrigin output.mp4 --codec=h264 --crf=16 --pixel-format=yuv420p
powershell -File scripts\verify-export-vs-qa.ps1 -Movie output.mp4 -ReferenceCsv qa\r01\motion.csv
```

Keep `Config.setVideoImageFormat("png")` in `remotion.config.ts`: the intermediate frames carry
one-pixel star dust and JPEG's chroma subsampling smears it into mush.

## Load-bearing details

These are the decisions that separate a good particle film from a grey smear. Each one has a
symptom that is easy to misdiagnose as something else.

- **Bloom threshold is per-act, not global.** A low threshold makes star dust read as stars; the
  same value on the lit hemisphere of the planet blows it into a white blob. Track it like exposure.
- **Motion blur is per-particle, not a post-process.** Accretion and dolly streaks come from
  stretching each point along its own velocity over a short trail window. Without it, fast orbital
  motion strobes no matter how high the frame rate is.
- **Camera tracks must be monotone cubic.** Plain Catmull-Rom overshoots between keys, so the
  camera visibly wobbles backwards in the middle of a move that should only advance.
- **The title is particles, not text.** Sample glyph coverage into target positions (see
  `src/particles/glyph.ts`) and let the swarm fly there. A DOM title laid over the particles reads
  as a different film, and a texture-based font lookup is what keeps it cheap.
- **Point size is in device pixels.** Changing `--scale` changes how bright each point lands, which
  is why the quarter-scale proxy and the master differ by roughly one luma step. That offset is not
  a bug; a change in the *shape* of the curve is.
- **Abrupt is a choice you have to author.** This film switches to absolute black in 0.2 s and its
  brightest frame is the rebirth burst. Record those frame numbers next to the QA CSV so a later
  pass does not "fix" them.

## Environment notes

- A 60 s 1080x1920 film is 3600 frames; at 8x concurrency on 18 cores that is about 9 minutes,
  plus ~1 minute of h264 encoding. Budget the full render as the expensive step and the proxy as
  the cheap one.
- The renderer launches its own bundled Chrome. In a sandboxed shell that spawn fails with
  `spawn EPERM`; run renders with elevated execution rather than trying to work around it.
- No system ffmpeg is needed. Probe, extract and encode with the copy that ships with the CLI at
  `node_modules/@remotion/compositor-<platform>-<arch>/`. Its build is deliberately trimmed, so it
  has `libx264`/`libx265`/`libaom` and image2 in/out but no `rawvideo` muxer and no default encoder
  for the `null` muxer - pass `-c:v` explicitly when decoding to nowhere.
- `public/fonts/` in the starter is intentionally empty. Drop in a CJK-capable bold font named
  `NotoSansSC-Bold.otf` (or repoint `GLYPH_FONT_FILE`) before rendering a title.

## References

- [references/particle-pipeline.md](references/particle-pipeline.md) - WebGL buffers, point
  rendering, bloom/composite and streak shaders. Read before editing `src/particles/`.
- [references/timeline-and-camera.md](references/timeline-and-camera.md) - the act map, staggered
  morphs, and every tuning track with the reasoning behind its numbers. Read before retiming.
- [references/render-and-qa.md](references/render-and-qa.md) - what each QA column means, the
  pass/fail thresholds, and how to cut a web-playable preview from the master.
