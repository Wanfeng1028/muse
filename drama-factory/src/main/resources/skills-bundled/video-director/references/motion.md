# Motion design

Frame counts at 30 fps: 0.1 s = 3 f, 0.2 s = 6 f, 0.33 s = 10 f, 0.5 s = 15 f, 1 s = 30 f.
Remotion API truth: `~/.claude/skills/remotion-markup/timing.md`, `transitions.md`, `motion-blur.md`,
`light-leaks.md`, `effects.md`, `3d.md`.

Contents
1. Fundamentals in Remotion
2. Easing
3. Springs
4. Durations
5. Entrances, exits, presses
6. Stagger and cascades
7. Kinetic type
8. Seams and transitions
9. Choreography, idle motion and stillness
10. Motion blur
11. Camera
12. Audio-reactive motion
13. Checklist and failure modes
14. Motion tokens by brand energy

---

## 1. Fundamentals in Remotion

- Everything is a pure function of the frame: `useCurrentFrame()` + `interpolate()` / `spring()`. CSS transitions,
  CSS animations, Tailwind animation classes, timers and stateful tweens do not render.
- No `Math.random` or `Date.now`; use `random(seed)`.
- Always clamp: `extrapolateLeft: 'clamp', extrapolateRight: 'clamp'`.
- Scale animations use `output: 'perceptual-scale'` (linear scale reads as decelerating while it grows).
- One writer per transform. Nest wrappers (entrance on the parent, push on the child, camera on the world) instead of
  summing unrelated motions in one transform string.
- Keep timing in named constants (or the timeline data file); stagger = `delay + i * per`; keyframe arrays are
  multi-point `interpolate` with an `easing` array of n−1 items.
- Preview suspect motion at 0.25× in Studio, or with `scripts/strip.sh`; easing flaws invisible at 1× are obvious.

GSAP names in other sources map to Remotion `Easing` as: power1 = `quad`, power2 = `cubic`, power3 = `poly(4)`,
power4 = `poly(5)`, expo = `exp`, sine = `sin`, circ = `circle`, back(s) = `back(s)`, none = `linear`, wrapped in
`Easing.in / out / inOut`. Bezier equivalents for `Easing.bezier`: outCubic (0.33,1,0.68,1), outQuart (0.25,1,0.5,1),
outQuint (0.22,1,0.36,1), outExpo (0.16,1,0.3,1), inQuint (0.64,0,0.78,0), inExpo (0.7,0,0.84,0), inOutQuint
(0.83,0,0.17,1).

## 2. Easing

- `out` for entering, `in` for leaving, `inOut` for moving between two on-screen positions. Ease-in on an entrance
  feels sluggish; ease-out on an exit feels reluctant. Never `inOut` on either side of a cut.
- Easing is the adverb: `exp` out = confident, `sin` inOut = dreamy, `back` out = playful. Choose on purpose.
- Default entrance: `Easing.out(Easing.poly(4))` or a critically damped spring; `poly(5)` / `exp` for punch; `sin` /
  `quad` for calm. About three easing characters per film: one ease and duration per element role (all cards alike,
  all words alike), varied between roles and beats, never per element.
- No `bounce` or `elastic` eases (bounce only for something literally dropping). `back` only in a declared playful
  register, overshoot ≤ 2.
- Linear is right only for mechanical cases: constant-speed travel along a path, the burst phase of a nudge curve, an
  opacity companion of an accelerating exit, phase drivers for sine maths. Linear on an entrance, exit or settle
  position is the generic-AI-video tell.
- Custom easings solved by bisection return ~1e-9 at 0: return exact 0 and 1 at the ends or visibility guards fire
  early.

## 3. Springs

Damping ratio ζ = damping / (2·√(stiffness·mass)). Remotion's default config (100 / 10 / 1) is ζ 0.5: visibly
bouncy. Always pass a config.

| Register | ζ | Feel |
|---|---|---|
| Default | 1.0 | no overshoot, long premium tail |
| Small UI | 0.80 to 0.85 | ~1% overshoot, alive not bouncy |
| Playful (only when the brief says so) | 0.60 to 0.70 | 5 to 10% overshoot |
| Never | below 0.55 | cartoon wobble |

```ts
export const springs = {
  settle:  { stiffness: 170, damping: 26, mass: 1 }, // ζ ≈ 1.0, ~0.6 s. Default.
  snappy:  { stiffness: 320, damping: 30, mass: 1 }, // ζ ≈ 0.84, ~0.35 s. Chips, small UI.
  heavy:   { stiffness: 120, damping: 24, mass: 1 }, // ζ ≈ 1.1, ~0.8 s. Big type, logo lockups.
  playful: { stiffness: 180, damping: 17, mass: 1 }, // ζ ≈ 0.63, ~8% overshoot. Opt-in only.
} as const;
```

- Response guide: 0.25 to 0.35 s tight snap (small UI), 0.35 to 0.5 s standard entrance, 0.5 to 0.7 s weighted hero
  landing. From a response time r and ζ (mass 1): stiffness = (2π/r)², damping = 4πζ/r.
- A ζ = 1 spring front-loads harder than `poly(4)` out and settles on a longer tail: use it when the settle is the shot
  (wordmark, final lockup).
- Overshooting curves go on transforms only, never on opacity or colour: split opacity onto its own curve.
- Take duration from the physics (`measureSpring({fps, config})`); tune speed with stiffness, not by stretching.
  `Easing.spring({damping: 200})` inside `interpolate` gives a fixed-length push without bounce.
- Big elements rebound slower, small ones snap: reactions scale with implied mass.

## 4. Durations

- Speed is weight: 5 to 9 f energy, 9 to 15 f most content, 15 to 24 f gravity, 24 to 60 f cinematic.
- A single entrance lasts at most ~24 f; a longer build is a stagger, not one slow element.
- Exits run about 75% of the entrance (≈10 f vs 15 f). At a velocity-matched seam the entry is ≥ the exit.
- The hero lands within ~15 f of its scene start. The film's first motion starts 3 to 6 f in.
- After a climax or reveal, keep at least 1 s (2 s if dramatic); a reveal 0.2 s before the cut reads "flashed and gone".
- Final lockups hold longer than transition poses; the last frame is part of the animation. Don't reset to rest or end on
  black unless asked.

## 5. Entrances, exits, presses

- Every arrival has a spatial component (y, x or scale). Opacity alone is forbidden; opacity may be a short companion
  fade or binary for snappy cascades. Default premium entrance: opacity + translateY 40 → 0 + scale 0.94 → 1 on the
  `settle` spring.
- Vary axes across a scene (rise, side, scale, mask). `y: 30, opacity: 0` on everything is the tell.
- Pop: scale 0 → 1 with `poly(4)` out over 12 to 21 f, optional rise ≤ 32 px, origin at the source point. Never hand-key
  a 1.1 midpoint; it double-bounces against the curve.
- Masked text rise: translateY 105% inside `overflow: hidden`, ~55 ms (≈2 f) per word, small rotation optional.
- Exits accelerate away with `in` eases. In a multi-scene film the seam is the exit: no "fade out, pause, next scene".
  Elements may exit inside a scene when content is replaced in place. Only the final scene fades out.
- **Press** on an existing element: near-linear compression (`quad` in) to scale 0.92 (0.88 dramatic, 0.96 subtle;
  never below 0.85) over 3 to 9 f, then an overshooting spring back to 1 over 12 to 27 f, starting exactly where the
  press ended. Press faster than release. This is the one place overshoot belongs in serious films: a force caused it.
  The button must be ≥ 3 to 5% of the frame or the press is invisible.
- Floods (a circle wipe from an object) must clear the farthest corner (distance to the four corners × 1.05) in 9 to 11 f.
- **Before/after**: stagger, never simultaneous. Land the "before" alone for 0.7 to 1 s, then crash the "after" in with
  a caused impact (a heavier spring that may overshoot once, the accent colour washing in over 3 to 6 f, never a
  one-frame flash) and an impact SFX on the landing frame. Design the film around this shot when the product has one.
- Logo reveal from a line: scaleY 0.014 → 1 like an eye opening. Never crossfade a drawn version into the PNG (grey
  ghost).

## 6. Stagger and cascades

- What moves first reads as most important: stagger by importance, not DOM order; overlap entrances, don't queue them.
- Per item `min(4 f, 15 f / N)` for words and cards, 6 f only for 2 to 3 big blocks; total ≤ 15 f per beat. Above ~9
  items, switch to a wipe or sweep.
- **Waterfall entry** (title cards, openers): one direction (default from below), each element starts within ±2 f of the
  previous one settling, gaps shrink across the cascade, opacity binary at start, `poly(5)` out.

| Weight | y offset | duration | overlap |
|---|---|---|---|
| anchor / heavy | 60 to 80 px | 5 to 6 f | 0 to 2 f gap |
| normal word | 40 to 50 px | 4 to 5 f | 1 f overlap |
| light / punctuation | 30 to 48 px | 3 to 4 f | 1 to 2 f overlap |

- Per-word slide decay mimics a camera settling: 80 → 60 → 50 → 25 → 12 px across words, onsets from VO word times.
- **Nudge curve** (moving a composed group, no cut): ramp ~10% of distance in ~20% of time, burst ~65% in ~18%, tail ~25%
  in ~62%; reveal new content during the burst. If it smacks to a stop, lengthen the tail.

```ts
interpolate(f, [0, 0.2 * T, 0.38 * T, T], [0, 0.1 * D, 0.75 * D, D], {
  easing: [Easing.in(Easing.poly(4)), Easing.linear, Easing.out(Easing.poly(5))],
  extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
});
```

- N elements moving repeatedly at once: amplitude ≤ default / √N, and stagger their periods.

## 7. Kinetic type

- One onset array drives every phrase and accent. Phrase onsets 1.2 to 1.8 s apart (under 0.8 frantic, over 2.5 loses
  the pulse). Each phrase a different entrance axis (scale + blur slam 1.5 → 1 with 16 → 0 px blur; side snap from
  x −320; rise + rotate from y 90 with 6°). Attacks 11 to 18 f that resolve before the next beat; exits ≤ 8 f; at least
  three easings; exactly one accent hue; display face 150 px+ and heavy.
- Zoom-through only on headlines and short phrases, never body text.
- Never blur text while it is being read: blur the approach, land sharp, hold.
- Text that moves internally moves glyphs or masked bands and preserves line boxes and final fit.
- Counters: `tabular-nums`; scale may grow with value for escalating emphasis.
- A word lights on its start frame, never before.
- Flat-but-competent kinetic type usually means one reused entrance helper: give each phrase its own entrance.

## 8. Seams and transitions

### The vector law
- **Axis**: x stays x, y stays y, Z stays Z across a cut.
- **Direction**: never mirror. On Z, direction is the sign of the scale change (growing = push, shrinking = pull). A
  receding exit answered by a grow-from-small entrance is the most common violation.
- **Speed**: the entry's initial velocity matches the exit's final velocity.
- **Phase**: the cut lands mid-motion on both sides. Settling before the cut or starting from rest after it is a dead beat.

### The current
Pick one dominant direction per film (example default: leftward) for ordinary seams. Other vectors are reserved and
mean something: upward = elevation or conclusion; Z forward = deeper into the same thought; Z backward = arrival,
something bigger lands; scale burst outward = leaving a world. Never two consecutive seams in opposing directions; a
direction change needs a visible cause or a chapter boundary.

### Carriers
The eye follows objects. The strongest seams hand a concrete carrier across at matched position and velocity: a cursor
mid-path, a container that docks into the next layout, a mark that flies into its slot, the word group of a waterfall
cut. With no natural carrier, the scene heroes carry it (partial travel plus an early fade). Write a seam ledger before
building (cut frame, exit and entry axis with signed direction, carrier, technique). If a row mismatches, fix the plan,
not the easing. Edits to a scene's first or last second, or a VO regen, reopen that seam.

### Velocity matching
`Easing.in(Easing.poly(n))` over D px in T frames ends at n·D/T px per frame; `Easing.out(Easing.poly(n))` starts at
n·D/T. Match n·D/T on both sides. If the entry runs longer, scale its distance: D_entry = D_exit · T_entry / T_exit.

```tsx
// Velocity-matched hard cut, travelling left. Use plain <Series> (no TransitionSeries.Transition: presentations
// overlap both scenes, which breaks the one-side-visible rule). Paint an opaque canvas-coloured AbsoluteFill under
// the Series, or the mid-seam frame flashes the page colour.
const SEAM_EXIT = 10;
const SEAM_ENTRY = 12;
const D_EXIT = 0.12 * width;                       // ~230 px at 1920
const D_ENTRY = (D_EXIT * SEAM_ENTRY) / SEAM_EXIT;  // keeps 5·D/T equal on both sides
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

// Scene A (durationInFrames = dA): accelerate out, die on the last frame
const t0 = dA - SEAM_EXIT;
const exitX = interpolate(frame, [t0, dA], [0, -D_EXIT], { ...clamp, easing: Easing.in(Easing.poly(5)) });
const exitOpacity = interpolate(frame, [t0, dA - 1], [1, 0], { ...clamp, easing: Easing.in(Easing.cubic) });
const exitBlur = interpolate(frame, [t0, dA], [0, 8], { ...clamp, easing: Easing.in(Easing.poly(5)) });

// Scene B: start at peak speed in the same direction, decelerate
const entryX = interpolate(frame, [0, SEAM_ENTRY], [D_ENTRY, 0], { ...clamp, easing: Easing.out(Easing.poly(5)) });
const entryOpacity = interpolate(frame, [0, SEAM_ENTRY * 0.6], [0.35, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
const entryBlur = interpolate(frame, [0, SEAM_ENTRY], [8, 0], { ...clamp, easing: Easing.out(Easing.poly(5)) });
// Apply transform and filter to the scene wrapper, never to children. Keep scene B's own element entrances out of
// the seam window, or match their direction.
```

The template ships this as `src/lib/seam.ts`.

### Technique catalogue

| Technique | Use for | Exit | Entry |
|---|---|---|---|
| Cut the curve (default) | ordinary boundaries, in the current | x 0 → −230 px, `poly(5)` in, 6 to 12 f, opacity reaches 0 on the cut frame | x +230 → 0, `poly(5)` out, ≥ exit, ignites at 0.35 opacity |
| Zoom-through (push) | deeper into the same thought, headline swap | scale 1 → 1.2, blur 0 → 10 px, `poly(4)` in, 6 f; opacity 1 → 0.15 on its own linear curve | from scale 0.75, blur 10, opacity 0.15 → 1, `exp` out, 15 f |
| Inverse zoom (pull) | arrival or payoff only | scale 1 → 0.8, blur 10, ~6 f | from scale 1.25 → 1, `exp` out, ~15 f |
| Waterfall cut | big text to big text, word by word | each word ~10 f `poly(5)` in, fade ~5 f, reading-order stagger ~0.7 f | words from x +230, start at 0.35 opacity, `poly(5)` out ~9 f, decaying gaps |
| Rack-focus blur cut | same surface, state swap; the one cut you want seen | fully opaque, blur rises `cubic` in | swap at peak blur 8 to 12 px with ~1.06 scale; at most one per ~8 s |

- Z sign table: push = exit 1 → 1.2 and entry 0.75 → 1 (both growing); pull = exit 1 → 0.8 and entry 1.25 → 1 (both
  shrinking). For ~15 f after a Z cut, the incoming scene's own entrances must arrive composed or match the sign.
- Seam blur by subject size: text 10 px (20 px smears letterforms); full-frame surfaces 18 to 20 px. Same blur and
  opacity on both sides at the swap frame. Blur the wrapper, never blur and fade one element on one curve, never blur a
  video element directly.

### Choosing transitions
- Transition = relationship: crossfade "this continues", hard cut "wake up" or register shift, slow dissolve "drift with
  me", push "next point".
- Budget: one primary for 60 to 70% of boundaries plus 1 to 2 accents; 2 to 3 types per film. Shared-element morphs
  don't count.
- The default boundary is a velocity-matched cut. Crossfades are allowed as the declared primary of a calm or premium
  film, for wind-down and outro, or for a "replacement" beat; never as the unexamined default. Hard cuts on downbeats or
  register shifts are legitimate accents; an unmotivated static-to-static jump cut is not.
- By energy: calm (wellness, luxury) blur crossfade 15 to 24 f `sin` inOut; medium (SaaS, explainer) push 9 to 15 f
  `cubic`/`poly(4)`; high (launch, sports) zoom-through 5 to 9 f `poly(5)`/`exp`.
- By position: opening = most distinctive (12 to 18 f); between related points = the primary; topic change = something
  different; climax = boldest accent; outro = slowest, crossfade or dip to colour 18 to 30 f.
- Hand-rolled options (8 to 14 f): whip pan (background translates ~1500 px in 6 f with 8 px blur, cut hidden
  mid-whip), scale-through, a brand-colour mask wipe with the cut behind it.
- Avoid transitions with repeating geometric patterns (tile grids, hex cells, dot arrays), star irises, lens flares,
  door hinges.
- Remotion: `TransitionSeries.Transition` (fade, slide, wipe, flip, clockWipe) overlaps scenes and shortens the timeline
  by its length; `TransitionSeries.Overlay` (light leak, 20 to 30 f) sits on the cut without shortening and cannot be
  adjacent to a transition or another overlay. Time presentations with `springTiming({config: {damping: 200}})`. Light
  leaks need `Config.setChromiumOpenGlRenderer("angle")`.

## 9. Choreography, idle motion and stillness

- Scene phases: build (0 to 30%, staggered, not a dump), breathe (30 to 70%, filled with story), resolve (70 to 100%).
- Rhythm inside a scene: HIT → hold (15 to 20 f) → build → HIT.
- Causal chains: click → squash → release → flight → impact → recoil → reveal. Effects start on the causing frame.
- One thing moves at a time unless a single driver moves everything.
- Keep one element alive across a handoff rather than crossfading a substitute (the button carries its label into the
  page).
- Avoid large mask or clip changes while the same hero surface is also travelling; reveal after the move settles.
- **Idle motion**: no breathing, floating, pulsing or drifting on content as a default; it reads as "the video is
  waiting". Fix an under-filled shot in this order: a staged reveal on a VO cue → a camera move with intent → a
  camera-level micro drift (2 to 8 px x, 1 to 4 px y, x:y frequency ratio ~1.3, one writer) → as a last resort one
  bounded breath on a single held hero (scale ±0.008 to 0.015, period 1.5 to 3 s, starting after the entrance settles,
  fading to zero over the last 20% before a seam). Ken Burns on photos and a slow push on the end card are fine.
- **Stillness**: element-level holds are good (reading holds, 9 to 22 f dramatic pauses); at least three per film.
  Contrast reads expensive; constant motion reads amateur. A fully frozen frame mid-film for over ~1 s is a planning bug.
- A beat-locked camera pulse (≈0.7% scale per beat, stronger on downbeats) keeps music-led films alive without wobble
  (template `src/lib/beat.ts`). Whole-frame beat impacts (frame-wide pumps, shakes, flashes) at most 3 per film, on the
  strongest hits, ≥ 16 beats apart; everything else on the beat moves only the hero layer. "The shot shakes with the
  rhythm" is a real client complaint.
- **No element fully still for more than ~3 s** after entering: give it a motion that is the verb being spoken (data
  flows, rows type, a gate opens), never decorative floating. Then let the last element settle and hold 30 to 45 frames
  before the exit, with no camera move in that tail. Measured test: content-area mean grey change under 0.35 at 320×180
  counts as a still frame.
- **Anti-slideshow minimum for narrated films**: an extremely slow push or pull on every scene (1.00 → 1.04 to 1.06), and
  motion continuing in the same direction across every boundary. A short overlapped motion-matched transition (12 to 16 f
  lead/tail, same direction both sides) is an acceptable alternative to the zero-overlap cut in narrated explainers.
  Repeating one transition reads more coherent than using six; save a black-slam cut for the single biggest reversal.
- Shot guards: no more than 1.5 s of empty stage before the first anchored motion; the main visual enters within 10
  frames of a cut; a word-anchored landing closer than 0.7 s to the shot's end gets eaten by the transition, so move it.
- **Pace, measured**: client notes on pace only ever said "slower, hold longer", never "too slow". Make version 1 a notch
  slower: the wordmark holds ≥ 1 s after landing, batch animations end with 0.5 s of stillness, the opening subject's
  action runs ≥ 3 s, simulated typing and clicking at real human speed. Speed comes from acceleration within a batch
  (dealing cards), not from short holds.
- One hero in the opener with a complete arc beats a crowd. The finale is the energy peak; first drafts of endings are
  almost always too timid. One animation technique stars only once per film; a shot that adds no new information goes.
- Glints and light sweeps: at most once, on the hero, clipped by its radius. Glow only on the subject plus at most one
  current focus; supporting elements never glow; on exit the glow dies first, then the element fades. The most expensive
  set piece appears at most twice per film.
- Counting animations show every intermediate value: counting 1995 → 1998 puts 1996 and 1997 on screen legibly. If the
  in-betweens could read as unsourced facts, blur them while counting or don't count.

## 10. Motion blur

- Blur is shutter smear, not polish. Blur only snaps: slams, whips, hard position cuts, spins, scale punches moving
  ≥ ~30 px per frame and a large fraction of the element's width; 1 to 3 per film.
- Never blur: slow travel, fades, colour changes, text being read, drifts and parallax, whole static scenes.
- Blur peaks at peak speed and resolves to 0 at the settle (same window and ease as the position). Lingering blur reads
  as a focus pull. Directional blur for lateral moves; symmetric only for depth and scale moves.
- Peak 8 to 30 px on an element (default ~18), 18 to 20 px on a full frame.
- Remotion: `<HtmlInCanvasMotionBlur samples={8} shutterAngle={180}>` (needs Remotion ≥ 4.0.529; see
  `remotion-markup/motion-blur.md`). 180° default, up to 360° for a deliberate slam. Fewer than 6 samples on a fast move
  ghosts. `Trail` only for a deliberate echo look (2 to 4 text-free ghosts at 0.3 to 0.6 opacity).
- Put the blur wrapper inside each scene, never around the Series: sub-frame samples would blend both sides of a cut.
- Thin type (under ~120 px or below weight 800) and busy backdrops swallow the smear.

## 11. Camera

- The camera is one transform on a world wrapper with keys [frame, zoom, x, y], eased segments, zoom in perceptual scale.
  Never zoom in and straight back out.
- Multi-phase 2D camera: wide (0.88 to 0.96) → focus (0.98 to 1.02) → push (1.04 to 1.15); each later phase settles
  deeper; `cubic`/`poly(4)` out or `cubic` inOut. Springs and back eases on a camera feel uncomfortable. Scale below 1
  needs `overflow: hidden`.
- Zooming into an off-centre target: scale plus counter-translate, dividing the offset by the current scale.
- 3D flights: perspective 800 to 1200 px, set once; world 2 to 4× the frame; props at translateZ 80 to 300 px for
  parallax; rotateX 30 to 55° (|rx| ≤ 65, |ry| ≤ 30 or planes go edge-on). Dives and landings `poly(5)` out over 0.6 to
  1 s; repositioning `cubic` inOut 1.2 to 2 s; holds ≥ 0.8 s between legs; reads happen at near-flat landings held ≥ 1 s.
  No filter, opacity or overflow on the preserve-3d world (it flattens). Vary the leg verbs; four identical pushes read as
  a slideshow. Official guide: `remotion-markup/3d.md`.
- Depth of field: 3 to 6 px blur per depth step, off-focus layers dimmed to ~0.55, focus pulls 0.5 to 1.2 s, the focal
  layer at 0 blur.
- Parallax: three layers at 0.3×, 0.6× and 1× of one camera value.
- Music-locked punches: about +0.012 scale per beat and +0.03 per bar after the drop, with exponential decay.
- Shake only for impact or panic: a brief, higher-frequency drift window.

## 12. Audio-reactive motion

- Audio supplies timing and intensity; the brand supplies the visual vocabulary. Never in brand films: equaliser bars,
  spectrum analysers, waveform displays, strobing on beats, rainbow cycling, pulsing orbs.
- Text or logo pulse ≤ 3 to 6% scale, glow ≤ ~30%; shapes and backgrounds 10 to 30%. Bass → scale swell, treble →
  glow or contrast, amplitude → lift, opacity or colour.
- Remotion: `useWindowedAudioData` + `visualizeAudio` (see `remotion-markup/audio-visualization.md`).

## 13. Checklist and failure modes

- [ ] Seam ledger written; ordinary seams ride the current; reserved vectors spent on meaning; no ping-pong.
- [ ] Every seam: exit still moving at the cut, entry mid-flight, same axis and direction, speed matched, one side
      visible per frame, Z sign kept, opaque background behind.
- [ ] No linear position easing on entrances, exits or settles; every interpolate clamped; scale in perceptual scale.
- [ ] Springs ζ ≥ 0.7 unless the brief is playful; no bounce or elastic.
- [ ] Stagger ≤ 15 f per beat, in importance order, overlapping.
- [ ] No idle wobble filling time; each scene names its sustained-motion route; stillness before the climax.
- [ ] Motion blur only on 1 to 3 snaps, never on read text, never across a cut.
- [ ] Strips around every fast move checked; watched at 0.25× where in doubt.

| Symptom | Cause | Fix |
|---|---|---|
| The eye's momentum dies at every cut | scenes authored in isolation, settle before cut | seam ledger, cut mid-motion |
| White flash at seams on a dark film | summed opacity < 1 over a transparent page | opaque background under the Series |
| Z seam feels like a hiccup | incoming grow-from-small fights a pull | arrive composed or match the sign |
| Glitchy text at a zoom seam | 20 px blur on text | 10 px for text |
| Still moving at the end | idle loops running into the transition | fade the loop's amplitude or remove it |
| Cheap and bouncy | bounce or back eases, ζ < 0.55 | ζ ≥ 0.72 springs |
| Group slide smacks to a stop | single inOut ease | three-phase nudge curve |
| Soft mush instead of speed | blur on slow moves | blur only snaps |
| Pop at a hard cut | a linear fade still at 40 to 57% on the last frame | `1 − (n/N)^1.5` over 6 to 12 f, reaching 0 on the cut |
| Empty first frame of an entrance | fade starting at 0 | start entrances around 25 to 57% opacity |
| Slide-up crosses the caption band | 300 px vertical travel | ≤ 120 px, or enter sideways |
| The end fade eats the last line | ending fade overlaps the last caption | last caption starts ≥ 30 f before the fade |

## 14. Motion tokens by brand energy

Pick one token set per film from the nearest preset and use it for entrances, transitions and holds (one brand, one
motion voice). Durations at 30 fps.

| Brand type | Main duration | Entrance ease | Overshoot | Squash |
|---|---|---|---|---|
| Trust (fintech, B2B) | ~21 f | `bezier(0, 0, 0.2, 1)` | none | none |
| Premium (luxury) | ~48 f | `bezier(0.4, 0, 0.6, 1)` | ≤ 1.02 | none |
| Bold (sport, startup) | ~18 f | `bezier(0.16, 1, 0.3, 1)` | 1.12 | 0.25 |
| Playful (consumer, kids) | ~27 f | `bezier(0.34, 1.56, 0.64, 1)` | 1.08 | 0.18 |
| Calm (health, education) | ~42 f | symmetric inOut | none | ≤ 0.04 |
| Friendly (small business) | ~26 f | `bezier(0.25, 0.46, 0.45, 0.94)` | 1.04 | 0.08 |

Overshoot here applies to transforms only (§3), and the playful row is still bound by the ζ ≥ 0.55 floor for springs.
