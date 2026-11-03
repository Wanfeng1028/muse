# Integrated FX Grammar

The single most important craft rule in this system, learned from direct client feedback and repeated rejection/acceptance cycles. Read this before adding ANY effect to an edit.

## The Rule

Effects and live footage must never be separate. No beat-alternating between full-frame FX segments and full-frame real clips — that reads as two videos spliced together. Every effect must be anchored to one of three things:

1. **The subject's matte** — echo bodies, rim glow, gesture-emitted particles, style transforms confined to the person.
2. **Scene geometry** — sky replacement, portals in the sky, screens corner-pinned with renders, water/ground reacting, light bleeding around real edges.
3. **The shot's own pixels** — kaleido/mirror built from the live frame, displacement, highlight smears, time-ripples of the frame's own history.

Procedural renders (tunnels, portals, starbursts) enter shots as **in-scene elements** — through skies, screens, doorways, viewfinders, reflections — never as standalone cutaway segments. The quality bar: the subject stays in nearly every frame and effects happen TO them.

## Failure modes that must never be repeated (all field-observed)

- Many mismatched handheld clips stitched at beat boundaries read as chaos even with a shared visual motif.
- An untracked screen-blended element placed at per-shot positions reads as a **sticker**, not an object in the scene.
- Per-shot one-off looks (one warm-washed shot among naturals) break cohesion.
- Pure restraint (soft grade, one gentle effect) reads as **washed out and boring** — rejected as hard as tackiness. See cinematic-grade.md for the calibrated formula.

**Standing priority: looking good beats following parameters.** If the requested footage or structure fights quality, change the structure and say so.

## The preferred construction for emotional pieces

ONE continuous shot + photometric transformation driven by the song's envelopes — grade ramp, bloom, light arrival. Seams are impossible by construction; emotion comes from lyric + light + one human in a landscape. Use this lane when the goal is to move the viewer rather than demo FX.

## Person mattes (the anchoring mechanism)

Per-frame person masks come from **Apple Vision** (`VNGenerateForegroundInstanceMaskRequest`, macOS 14+), not rembg:

- A small Swift tool: AVAssetReader decodes every frame (BGRA) → Vision foreground-instance mask → 8-bit grayscale PNG per frame, named `proposal_%06d.png`. Empty matte when no instance found. Compile: `swiftc source.swift -O -framework AVFoundation -framework Vision -framework CoreImage -framework ImageIO -o mattegen`; run: `mattegen <source.mp4> <proposal_dir>`.
- Python fallback adds temporal robustness: `cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 21, 3, ...)` warps the previous mask forward when Vision misses a frame.
- **Matte quality gates** (enforce before using): mean coverage in [0.02, 0.90]; max coverage jump between frames ≤ 0.20; max run of low-coverage frames ≤ 2; max non-person island ≤ 0.005 of frame. Coverage = fraction of pixels > 8/255.
- In shaders, threshold with `smoothstep(0.30, 0.70, matte)`. Rim/edge effects trace a 4-tap gradient of the matte; halos come from dilated matte samples on a 6-point circle.
- Watch for false positives (e.g. wall art matting as "person") — inspect mattes per clip and blacklist bad sources as foreground.

Bundled implementation: `scripts/matte/generate_local_person_matte.swift` (the Vision matte generator) and `scripts/matte/media_contract.py` (the quality-gate thresholds as code).

## Three build architectures (choose per edit)

**(A) Segment-render → concat → post-graph** (ffmpeg only). Each shot rendered to its own mp4 with cover-crop, concat demuxer joins with `-c copy`, one `filter_complex` applies the house grade + flash accents, audio muxed last. Best for cut-driven edits without per-pixel FX. Cover-crop + HDR-safe ingest:

```
[if HDR] zscale=t=linear:npl=100,tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p,
fps=30,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,
setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=12
```

Detect HDR by probing `color_transfer/pix_fmt` for `arib-std-b67`/`smpte2084`/`10le`. `tpad=stop_mode=clone` freeze-extends short clips so the music grid never shortens; verify with `ffprobe -count_frames` and re-pad if needed.

**(B) Frame-pipe numpy** (true per-pixel integrated FX). Decode ffmpeg → rawvideo rgb24 → numpy loop mutates each (H,W,3) frame → pipe into encode ffmpeg stdin (`-f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 30 -i - ... -c:v libx264 -crf 17`). This is where matte-anchored effects live.

**(C) In-shader fusion** (moderngl GLSL — the deepest integration). Footage decoded into a GPU texture and the procedural world raymarched in the SAME fragment shader — shared palette, tonemap, spark field; cuts land as in-shader warp punches. See procedural-renderers.md.

The proven pipeline for matte-anchored builds: (1) render a clean graded `base.mp4` (locked cut, no FX) → (2) generate Vision mattes ON the base → (3) drive effects from a per-frame effects table → (4) mux the original audio. Because mattes are made on the locked cut, every effect is pixel-registered by construction. Re-deriving onsets from the base's own audio track gives perfect sync for the FX pass.

## Compositing gotchas (hard-won)

- **Screen blends must run in RGB** (`format=gbrp`): in YUV, black has chroma 128 and screening floods the frame magenta. Do opacity as an RGB `lutrgb` multiply.
- A composited element (portal disc etc.) needs: feathered alpha (radial mask via generated PGM + `alphamerge`), growth/position continuity across shots (e.g. 150→900px across the arc), and ideally a **reflection** (flipped/blurred copy in water) or **edge wrap** (blurred element light bleeding in from frame periphery through a radial mask) to bed it into the scene.
- Enter a full-FX moment through a continuous camera move, never a cut: crop-expression dolly toward the sky then `xfade` into the tunnel ("dolly-through").
- Put the subject INTO the FX world too (matted darkened silhouette inside the tunnel bore) so both worlds share pixels.

## Subject-FX vocabulary (GPU, matte-keyed — proven modes)

All follow `col = mix(effect_world, src, matte)` — subject reconstructed from real pixels riding on the transformed world. Keep a ring buffer of the last 24 frames AND last 24 mattes as `sampler2DArray`s (`uHist`, `uMhist`) so trails/echoes affect only where the subject *was*:

- world_ripple (background time-bends via history indexed by radial sine; subject crisp)
- echo_clones (tinted onion-skin ghosts at fixed lags, e.g. 6/13/20 frames)
- neon_rim (matte-edge outline + halo, world dimmed to luma)
- bg_kaleido (6-fold polar fold of background only)
- subject_prism (RGB split + banded glitch, matte-masked, gated on the beat pulse)
- style flicker: the subject cycling visual styles (pixel/vector/paper/chrome/thermal/…) on the half-beat while the environment stays real
- subject↔world SWAP: subject pixelated on real world alternating with real subject on pixelated world, as hard snaps on beats
- beat stamps / multitude: frozen copies of the subject persist across cuts (dimmed ~0.5 per cut), clones spawn every half-beat from the drop, army decays at the landing so the subject ends alone

The last three are the client's favorites. Cohesion rule: pick ONE effect language (family) per cut and escalate it with song structure. Within that language, the specific mode may vary per shot (separation on verse shots, prism on the pre-drop close-up, echo-bloom once on the drop) — that's variation inside a language, which is fine. What breaks cohesion is per-shot one-offs from DIFFERENT languages (one kaleido shot, one warm-wash shot, one glitch shot).
