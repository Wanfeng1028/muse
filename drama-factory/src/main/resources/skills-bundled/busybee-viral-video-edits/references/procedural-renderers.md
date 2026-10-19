# Procedural Shader Renderers (headless GPU)

Offline audio-reactive GLSL rendering with Python + moderngl. This is how tunnels, portals, kaleidoscopes, starbursts, and hero title pieces are made — and how they get fused with real footage. Bundled, runnable implementations: `scripts/procedural/render_*.py` (dream_portal, hyper_kaleido, hyper_space_jump, color_tunnel, glass_bloom, fractal_neon, neon_cathedral, mandala, portal_weave, shader_pack) plus `footage_fx.py` and `subject_fx.py`.

## The skeleton (identical across every renderer)

```python
import moderngl, numpy as np, subprocess
ctx = moderngl.create_standalone_context()           # headless, Metal-backed on macOS
fbo = ctx.framebuffer(color_attachments=[ctx.texture((W, H), 3)]); fbo.use()
prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
vao  = ctx.vertex_array(prog, [(ctx.buffer(np.array([-1,-1, 3,-1, -1,3], "f4")), "2f", "in_pos")])
ff = subprocess.Popen(["ffmpeg","-y","-hide_banner","-loglevel","error",
    "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
    "-vf","vflip","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
    str(out)], stdin=subprocess.PIPE)
for i in range(n_frames):
    prog["uTime"].value  = i / FPS
    prog["uPulse"].value = float(env[i])            # onset envelope (song-analysis.md §5)
    vao.render()
    ff.stdin.write(fbo.read(components=3))
```

- VERT is a trivial fullscreen-triangle pass; all work happens in a `#version 330` fragment shader.
- **`-vf vflip` is mandatory** — GL renders y-up.
- Standard CLI: `--audio --start --dur --out --fps 30 --w 1080 --h 1920`, plus `--still --t` for single-frame art-direction checks. Add a still mode to every renderer; check stills before rendering video.
- Integrated uniforms that *surge on hits*: accumulate `uCamZ`/`uFlow`/`uRoll` by `dt * (base + k*pulse)` per frame; `uPhase = i/(n-1)` for slow palette morphs.
- Timeline keyframes (drop / breakdown / second-drop times) are hardcoded per-song per-window in the script — derive them from the section analysis of the exact render window.

## GLSL house library

`hash13`/`hash21`, value-noise `vnoise`, `fbm` (4–5 octaves with a domain-rotation matrix between octaves), iq cosine palettes `pal(t,a,b,c,d) = a + b*cos(6.2831*(c*t+d))`. Log-polar mapping is the workhorse for tunnels/mandalas (bands scroll outward and self-nest into an iris).

## House color finish (end of every fragment shader)

```glsl
col = acc * 1.35 / (1.0 + acc);                       // Reinhard-ish tonemap
float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
col = mix(vec3(l), col, 1.3);                          // saturation lift
col = pow(col, vec3(0.4545));                          // gamma out
```

## THE ART-DIRECTION LAW: near-black base + emissive neon

Learned twice independently (kaleido and space-jump both washed out pastel on first attempt): relief-lit or dense-band procedural fields read "carpet"/"pastel mush" unless the base is **near-black** with **emissive neon ring/streak families** carving the light. Concretely: widen dark gaps to ~50% of the field, let noise carve intensity (`I = profile * pow(streak, 1.5+) * gradient`), keep black moats between color families, and punch saturation. If a frame still looks flat: increase depth separation and darken the periphery before adding any detail.

## Audio reactivity mapping (proven assignments)

- **Onsets** → punch-zoom, white-hot flash, flow/rotation kicks, fold morphs.
- **Bass** → core bloom, inner-rim heat.
- **Integrated energy** → tunnel/travel speed.
- Keep these as SEPARATE normalized control signals (bass / energy / high / transient) — never one loudness scalar. Keep onset event channels unsmoothed; smooth only the continuous followers.

## Fusing procedural with real footage (the endgame)

`render_portal_weave.py` pattern — footage and the procedural world in ONE shader pass:

```
render_portal_weave.py --base base.mp4 --audio song.wav --start 108.47 --dur 15 \
    --cuts "1.72,3.44,5.15" --phi ramp|breath|rush --out weave.mp4
```

- The base cut (real clips, beat-locked, built first) is decoded into `uSrc` (ffmpeg rawvideo pipe, cover-cropped `scale=W:H:force_original_aspect_ratio=increase,crop=W:H,fps=FPS`).
- The tunnel is raymarched in the same fragment shader — shared palette, tonemap, spark field — so footage and FX are fused per-pixel, not layered.
- `--cuts` = the exact segment boundaries the builder computed; each cut drives an in-shader warp punch (`k = exp(-secondsSinceCut * 8.0)` → zoom + chromatic split). Sync by construction.
- `--phi` = immersion curve (how much the procedural world swallows the frame): `ramp` steady, `breath` energy-following, `rush` hot start; always land the finale (e.g. event-horizon floor `clip((t-0.86)/0.12, 0, 1)*0.97` in normalized time).

For multi-look samplers: render each look to `seg_KK_<mode>.silent.mp4` with a `drawtext` mode label, concat-demux, mux audio once.

## Hero pieces (Black Sun Engine pattern)

For a standalone procedural hero video, write a design doc first (see design-docs.md) with: named depth layers (≥3 distinguishable), a 5-phase motion timeline over the exact duration, separate audio control signals, and a Quality Standard acceptance list. Finish stack: filmic tonemap, dithering (kills banding in near-black gradients), bloom, supersample + Lanczos downscale. Verify per the doc: compile → still frames at mandated timestamps → contact sheet → full render → inspect at full size AND phone scale → ffprobe → watch the whole file.

## TouchDesigner lane (live/real-time variant)

When the target is TouchDesigner instead of offline moderngl: build everything from source-controlled Python scripts (never fragile UI clicks). Conventions: a `td_controls` constantCHOP holds every tunable; audio features come from an audiospectrumCHOP (fftsize 1024) shaped as separate bands (bass 40–180Hz, energy 40–10kHz, high 2.5–9kHz, transient = positive energy delta) with compression `1 - exp(-raw*gain*sensitivity)` then `pow(v, gamma)`; onset events fire on threshold + cooldown frames. Fragment shaders are GLSL 460 wrapped in `TDOutputSwizzle(...)`, uniforms bound by expression to the control/feature CHOPs. Delivery is gated by a diagnostics report (operators exist, uniforms bound, shader compiled, resolution, audio source real vs synthetic fallback, node errors, timeline playing) written atomically — record honest offline/live status, never fabricate refresh proof. The second-pass VFX contract: the clean cut is locked (`do_not_change_selects_or_music_timing`, source media read-only); enhancement passes need before/after evidence and a promotion gate (promote / reject / await-evidence), with per-recipe reject rules (readability of subject/face/caption/action must not drop).
