# Rhythm, transitions, camera

Evidence: the author's lab cards T01, T04, T08 (rhythm), T10 + T04 (transitions), T09
(camera). Tiers: `evidence-and-instruments.md` §Tiers.

## §1 Rhythm source — pick ONE primary

| Source | Rule | Tier |
|---|---|---|
| Music | Section CHANGES on bar lines (C08 bar-level R 0.918, n=14); motion inside a section need not be on the beat (C08 R 0.34) | measured (T04) |
| Narration / lyrics | The most violent frame of a section's transition within ±0.15 s of the new section's first line start (sources: 0.00-0.14 s after the start; C11 C13 C14 p < 0.0005, C20 p 0.012) | unvalidated (T08) |
| Both present | Change on lines; do not also hard-lock bars (C14) | measured |

Beat alignment for motion and cuts (T01):
- Measure the music's real BPM (`scripts/beatgrid.py`); a declared BPM can be wrong (C06).
- Put the PEAK velocity of a motion on the beat; start it ~30-40 ms early (~2 frames at
  60 fps). Verified (r2, 3 runs each): peak -14..+4 ms with the rule vs +37..+60 ms without;
  it moves the mean onto the beat, it does not make every hit tighter.
- Hard cuts exactly on the beat (C06 spread ±12 ms); section lengths in powers of two beats
  (2-2-4-2-2-8-4-4-4).
- Lock only strong beats (bar or phrase starts); the cap N on hard locks is UNSET (the
  round that would set it was closed unrun, author 2026-09-30). Readability beats a lock.
- Annotate every locked event in the generated HTML: `// beat-locked: <t>s`, and a header
  `// beat-grid: <BPM> BPM, <beats_per_bar>/4, offset <s> s`, so measurement can compare
  claimed and measured locks.
- Music-only films. With a voice, the time anchor is the line, not the beat.

## §2 Transition kinds

| Kind | Numbers (30 fps frame counts from sources) | Fits |
|---|---|---|
| Dim to ground (C07) | whole frame 0.20 s down, ~0.17 s empty, headline per character ~0.3 s, UI fades in; anchor never moves; <= 0.7 s total | fixed-skeleton product tour; tone fit not judged (not the same device as the dark dim OVERLAY in `whole-film-rules.md` §2); for a calm film the fade is the safe default |
| Blur swap (C08) | old blur + fade + slide 0.10 s, new blur-to-sharp 0.07 s, cards rise ~0.2 s; ~0.35 s | fastest; product tour |
| Black wipe card (C09) | wipe in 0.37 s, words masked up ~0.3 s, hold ~2 s, wipe out | chapter cards |
| Shape to shape (T10) | below | profile reel, UI morph, illustrated story |
| Fade | — | disturbs least (author, r12) |

One transition kind for a whole product tour (an ad may use more, whole-film §3 still applies); 3-4 kinds for a data showreel. The dim
transition in an imitation stretched its empty frame to 0.4-0.5 s and left an empty product
window: cap empty time at 0.2 s and fade the window out fully (r3).

## §3 Shape to shape (T10) — measured, unvalidated by imitation

The dominant shape before the transition BECOMES the dominant shape after it, on the same
spot, so the eye never leaves that point.

```
anchor        : centroid drift <= 0.02 of the frame diagonal for a UI shape (C05),
                <= 0.065 for an illustrated subject (C03)
size / outline: free to change a lot (C05 area ratio 0.18-0.67) as long as it is the same spot
continuity    : the shape is on screen and changing in EVERY frame of the morph; no frame missing it,
                no frame where its contrast to the ground collapses (< 0.4 of the ends), no single
                frame carrying > 0.83 of the total change
morph length  : UI shapes 0.15-0.25 s; illustrated subjects 0.33-0.67 s
ground        : constant through the morph; a one-frame ground swap reads as a cut
pairing       : pick shapes that already share a centre and rough extent (band->band, disc->disc)
```

Ways to build it (names only, not measured in the lab; check the library's current docs):
SVG path interpolation (equal point counts), FLIP layout animation, shared-element
transitions (`view-transition-name`, `layoutId`). In a frame-rendered film, compute every
style from `t` (closed-form springs, `element-motion-params.md`); do not
rely on the browser's live tweening.

Dim-to-ground + fixed skeleton (C07) and shape-to-shape are two different roads, not two
spellings of one device.

## §4 Camera moves (T09) — measured on 2 cross-checked films, unvalidated

A camera move = one transform on a container holding two or more unrelated elements, so
the whole picture pushes, pulls, pans or rotates. An element growing, shrinking or sliding
in is NOT a camera move. A page scroll or shrink-to-card driven by the on-screen operation
is a TRANSITION, not a camera move (author 2026-09-30).

Decide the goal first: guide the eye to a subject; change section; show the product
screen; opening lead-in; ambience (slow drift, no information). Parameters differ by goal:

- Punctuation: 1.1-1.7 s, x1.7-x1.8 push (or x0.55 pull), ease-out (C09).
- Breathing: 3.5-4.5 s, x1.3 push or x0.75-x0.8 pull, near-linear; a slow pull is common
  at the end (C14).
- Measurable floor: zoom >= 0.03/s (ln scale per second), pan >= 0.02 frame widths/s,
  rotation >= 2 deg/s. A 1%/s drift reads as still: call it "breathing", never "a camera move".
- Build: one `.stage` wrapping everything, `transform: translate() scale() rotate()`,
  `transform-origin` on the target; `ln s(t) = ln(S) * ease(u)` per frame from `t`, never a
  CSS transition. three.js: `zoom`/`fov` = uniform scale (no parallax); a dolly gives
  parallax. Raster text blurs when pushed: draw at the largest scale or keep vectors.
- Verify with `scripts/camflow.py`: the move appears in `moves`, `scale_x` in range,
  `explained` >= 0.5; look at frames for any run flagged `at_boundary`.
