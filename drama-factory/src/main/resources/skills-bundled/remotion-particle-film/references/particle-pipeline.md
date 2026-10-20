# Particle pipeline

Read this before editing `src/particles/`. It describes `engine.ts` (the WebGL2 host) and
`shaders.ts` (the GLSL), in the order data actually flows through them.

## Context and buffers

`ParticleEngine` requests `webgl2` with `antialias: false`, `depth: false`, `preserveDrawingBuffer:
true`. `preserveDrawingBuffer` is not optional: Remotion grabs the canvas after the React commit,
and without it the capture can land on a cleared buffer.

Three static vertex buffers back the whole film, uploaded once and never updated:

| location | attribute | contents |
|---|---|---|
| 0 | `vec4 aSeed` | four independent random values per particle |
| 1 | `float aIndex` | particle index, normalised in the shader |
| 2 | `float aBirth` | one more random value, used for staggering |

Draw call is a single `gl.drawArrays(gl.POINTS, 0, count)` - once per motion-blur tap, at most four
times per frame.

### Hash per (index, channel), not per index

```ts
const hash = (index, channel) => { /* murmix-style integer mix of both inputs */ };
```

Taking four consecutive outputs of a single PRNG stream looks fine for a starfield and is
catastrophic for grouped structure. If you select "which galaxy" from channel 0, the other three
channels are then slices of the same stream position, so they are no longer independent: every
galaxy collapses into a 1-D curve. Hashing `(index, channel)` keeps the channels orthogonal, which
is what lets one buffer hold a planet that is also a galaxy member that is also a glyph sample.

## One vertex program for every act

`POINT_VERT` declares a `statePos(id, seed, idxN, misc, t, out vec3 vel)` that switches on
`uStateA` / `uStateB` and returns a position while writing the particle's velocity out. Position and
velocity come from **the same function** - the streak and the accretion trail are derived from the
velocity the state already computed, so adding a new act automatically gets motion blur for free.

The morph is not a global crossfade:

```
mine  = smoothstep(stagger window)
pos   = mix(statePos(A), statePos(B), w_i)      // w_i is per particle
```

`uStagger` (0.42 in this film) widens the per-particle window around the global `uBlend`, offset by
`aBirth`. Without the stagger the entire population snaps between shapes on one frame and reads as
a cut no matter how long the blend is.

### Field model

Three additive layers, in `statePos` order:

1. **Coherent field** - a smooth noise field that is a function of *world position*, so every planet,
   galaxy and glyph stroke drifts as a whole and keeps its shape. The title arrival damps this layer
   (`uGather`) so the strokes settle instead of boiling.
2. **Micro turbulence** - `uTurbAmp = state.scale * 0.02`, small enough to add life without
   breaking a structure apart. Scale-aware because the subject spans ~2 units (singularity) to
   ~1200 units (galaxy cluster).
3. **Glyph jitter** - `uGlyphJitter = max(sampleSpacing * 0.5, 0.02)`, applied only in the title
   act. Half the mean sample distance breaks up the glyph's pixel grid while keeping strokes crisp;
   anything larger and the characters look eroded, anything smaller and you can see the lattice.

## Motion blur is per-particle

The point pass runs the vertex shader `uTaps` times, each with a different `uTapIndex`, offsetting
the particle along its own velocity by a fraction of the trail window:

```ts
const taps = state.streak > 0.004 || state.swirl > 0.004 ? 4 : 1;
```

Two separate effects ride on this:

- **`uStreak`** - radial stretch for the fast dolly (39.0-43.6 s) and the final plunge
  (48.3-49.68 s). Without it the dolly reads as a static starfield that got bigger.
- **`uSwirl`** - the accretion trail (36.4-49.94 s). Orbital speed is high enough that one point per
  particle per frame strobes; four taps along the orbit turn concentric rings into flowing matter.

The tap count is gated so that the quiet majority of the film costs one draw instead of four.

## Pass chain

| # | target | program | notes |
|---|---|---|---|
| 1 | scene, full res | `POINT_FRAG` | additive, `blendFunc(SRC_ALPHA, ONE)`, no depth test |
| 2 | bloom A, 1/4 res | `BRIGHT_FRAG` | threshold on the max channel, scaled by `1/(1-threshold)` |
| 3 | bloom B/A, 1/4 res | `BLUR_FRAG` | separable 9-tap, horizontal then vertical, twice |
| 4 | canvas | `COMPOSITE_FRAG` | scene + bloom, tone curve, vignette, dither |

The scene target is `RGBA16F` when `EXT_color_buffer_float` is present and `RGBA8` otherwise.
Additive blending into `RGBA8` clips the dense cores to flat white and destroys the falloff, so a
half-float scene target is worth checking for explicitly. `gl.finish()` is called at the end of the
frame so the capture cannot race the GPU.

### Composite

```glsl
col  = scene + bloom * 0.72;
col  = col / (1.0 + col * 0.92);                        // soft roll-off
col *= 1.0 - smoothstep(0.36, 1.12, r) * 0.72;          // vignette
col += vec3(0.004, 0.006, 0.017) * (1.0 - smoothstep(0.0, 0.72, r));
col += (hash(uv, uTime) - 0.5) * (1.3 / 255.0);         // dither
```

The roll-off is what keeps the brightest frames (the rebirth burst) from turning into a flat white
rectangle. The blue-black centre tint, not a background colour, is what stops the empty frames from
looking like a broken render - there is no `<AbsoluteFill>` background doing this work.

The last line is a **frame-varying** ±0.65/255 dither. It is deliberate: the film is 95% dark
gradient and 8-bit quantisation bands badly without it. The cost is real and worth knowing - every
frame carries noise, so the encoder cannot coast, which is most of why the CRF 16 master is ~28 Mbps
rather than the ~8 Mbps a mostly-black film would normally need. It also means `peak_diff` in the QA
CSV never reaches zero. Do not "clean this up" casually.

## Point sprite

```glsl
vec2 c = gl_PointCoord - 0.5;
if (dot(c, c) > 0.25) discard;                 // circular
float core = exp(-d * d * 7.0);
float halo = exp(-d * d * 2.1) * 0.30;
```

One gaussian is not enough: a single tight gaussian looks like a hard pixel, a single wide one looks
like fog. The narrow core plus the wide 30% halo is what makes a point read as a star. Because the
sprite is rasterised in device pixels, its apparent brightness depends on `--scale`, which is the
root cause of the proxy-vs-master luma offset described in `render-and-qa.md`.
