# Timeline and camera

Read this before retiming the film. `src/timeline.ts` is the only place motion is decided, and
`src/config.ts` holds the constants it reads.

## Act map

Twelve acts over 60 s at 60 fps. The act list is a target-distribution schedule, not a cut list -
`resolveStates(t)` returns `{a, b, w}` and nothing else in the film knows what an "act" is.

| s | act | distribution |
|---|---|---|
| 0.0-6.5 | I | deep star shell, camera flying through it |
| 6.5-9.0 | II | ring |
| 9.0-12.0 | | nested rings |
| 12.0-15.5 | III | particle sphere |
| 15.5-22.0 | IV | 64 planets |
| 22.0-25.5 | V | one spiral galaxy |
| 25.5-30.0 | VI | 361 galaxies |
| 30.0-38.0 | VII | 19x19 board |
| 38.0-50.0 | VIII | black hole + accretion flow |
| 50.6-53.6 | IX/X | singularity |
| 53.6-56.2 | XI | rebirth wave |
| 56.2-60.0 | XII | particle title |

### The blend window is asymmetric

```ts
const lo = s.start - s.blend * 0.65;
const hi = s.start + s.blend * 0.35;
```

The morph is centred *before* the act's nominal start, so a structure has already wound itself
together by the time the act "begins". Moving `blend` to a symmetric window is the single easiest
way to make the film look late and mushy: the new shape arrives after the audience expects it.

`resolveStates` falls through to `{a: state, b: state, w: 1}` for the settled stretches, so a
frame outside any blend window costs one branch.

## Monotone cubic tracks

`buildTrack([[t, v], ...])` returns an interpolator using a Fritsch-Carlson-style limiter: secants
per interval, then tangents clamped so that no segment overshoots its endpoints.

This matters more than it sounds. With plain Catmull-Rom, a key sequence like the pull-back at
22-30 s overshoots between keys and the camera visibly drifts *backwards* for a few frames in the
middle of a move that should only be receding. The clamp costs one loop and removes the class of bug
entirely. When you add a key, the invariant to preserve is that the track only reverses direction
where you actually intended a reversal.

## The tracks

All six live in `timeline.ts` and are sampled per frame; `computeFrameState(t)` assembles them.

| track | shape | why |
|---|---|---|
| `CAMERA_DISTANCE` | 760 -> 120 through act III, out to 3400 for the board, hard dolly to 520 at 43 s, plunge to 40 at 49.7 s, out to 1150 for the title | one continuous move; the 43 s overshoot exists so the whole accretion vortex fits in frame |
| `CAMERA_FOV` | 45 deg, opening to 60 deg during the dolly | sold as a lens change rather than a speed change |
| `SCENE_SCALE` | 620 at the starfield, 28 on the planet, 1200 on the title | drives turbulence amplitude and flow scale |
| `POINT_SIZE` | 2.0-2.7 px, rising to 3.6 px at the rebirth | the subject spans 2 to 1200 world units; constant screen size keeps it coherent |
| `EXPOSURE` | 0.55 -> 1.25, spikes to 1.35 at the plunge | recovers the dim opening without blowing the burst |
| `BLOOM_THRESHOLD` | 0.14 at the starfield, 0.30 on the planet, 0.16 on the last beat | see below |

### Bloom threshold is per-act

This is the value most worth copying. A low threshold (0.14) gives star dust a halo and makes it read
as stars. Applied unchanged to the lit hemisphere of the particle planet, the same threshold turns
the planet into a white blob, because the planet's lit side is a few hundred densely packed points
rather than a few isolated ones. Track it like exposure, per act.

### Handheld drift, and where it must stop

```ts
const locked = smoothRange(time, 5.6, 7.2) * (1 - smoothRange(time, 15.2, 17.6));
const drift  = (1 - smoothRange(time, 36.5, 43.0)) * (1 - locked);
```

Two counter-sinusoids multiplied into the camera position give the "handheld" feel. It is switched
off for the collapse and the planet build (so the structure forms dead centre) and again before the
dolly (so the rush stays clean). Drift left on during a locked move is a common way to make a
deliberate shot look sloppy.

## Deliberate discontinuity

Three places in this film are *supposed* to be abrupt. Write their frame numbers down when you QA,
or a later pass will "fix" them.

| frames | s | what |
|---|---|---|
| ~2982-2994 | 49.7-49.9 | opacity switches to 0 in 0.2 s - the frame is switched off, not faded |
| 2994-3063 | 49.9-51.05 | absolute black; `luma` bottoms at ~1.12 |
| 3217 | 53.62 | rebirth burst, the brightest frame in the film (`luma` ~70) |

The singularity is not scaled in; `reveal = pow(clamp((t - 51.05) / 2.35), 4.5)` lights particles one
at a time, so one point appears first and the full core only exists at the end of the growth window.
The `4.5` exponent is doing the work - a linear reveal looks like a fade-in ball.

The final beat is equally restrained: `gather` contracts the whole title for 0.5 s, `burst` rolls the
highlight off over the next ~0.5 s, and `finalFade` closes the last 0.12 s. Nothing is picked out and
nothing explodes.

## Retiming without breaking it

- Change `blend` before you change `start`. Widening a blend repairs a flat transition; moving an
  act boundary usually just moves the problem.
- Keep the camera keys monotone in the intended direction, then let the limiter handle the rest.
- Four constants in `config.ts` are load-bearing for the world scale and are referenced by the state
  functions: `SPHERE_RADIUS`, `HORIZON_RADIUS`, `DISK_OUTER`, `PLANET_COUNT` / `GALAXY_COUNT` /
  `GRID_N`. Changing resolution or particle count does not require touching them.
- `TEXT_QUAD_WIDTH` is derived from `FINAL_DIST` and the frame aspect so the title always fills 86%
  of the width. If you change the aspect ratio, do not hardcode a replacement - the derivation is
  what keeps the title the same size in frame.
