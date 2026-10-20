# Scenes: timing, look, motion, and the gotchas

## Timing helpers (from `timeBeats`)
- `T(id)` beat start, `E(id)` beat end.
- `F(id, f)` a point inside the spoken part: `F("b04", 0.5)` is halfway through the words. Voiced,
  it snaps to the start of the word at that position.
- `Wd(id, k)` the start of the k-th spoken word (0-based). Use it when a visual must land ON a
  word ("the pill lights up on 'yes'"). Voiced, the index is whisper's word list, which can split
  differently from your text ("ChatGPT" may become "chat GPT", "4,000" may become "4" and ",000"):
  print the words before keying a visual to one.
- `hold` on a beat adds seconds after the line (breathing room after a reveal). `gap` in
  `timeBeats(..., { gap })` is the pause between every voiced line.

## Structure
- `scene(id, fromBeat, toBeat, html)` makes one full-frame layer with a slow push-in and a short
  fade out. Put several beats in one scene when they share a diagram.
- Diagrams that come back later (a pipeline, a graph) are generator functions with an id prefix,
  so the same picture can return with new state.
- Size everything in `cqw`/`cqh` (the root is a size container). GSAP `x`/`y` are pixels: multiply
  by `PX`/`PY` (1cqw and 1cqh in pixels).

## Look (the default theme)
Tokens on `#root`: `--bg` cream, `--surface`, `--fg` ink, `--muted`, `--accent` peach,
`--accent-strong`, `--butter`, `--sage`, `--lilac`. Change them in `engine/core.mjs` for your brand.
- Ink-bordered cards with a flat ink shadow (`.card`), mono uppercase chips, ONE serif italic
  accent word per frame, usually in a peach pill (`<span class="serif pill">`).
- Minimum text: 1cqw for mono labels, 1.3cqw for body. YouTube is watched on phones.
- Chrome: chapter chip top-left, chapter progress rail top-right, subtitles bottom centre.
  Keep scene content between about 9cqh and 86cqh so it clears all three.

## Motion vocabulary (in the page)
`land` (pop in, back.out), `rise` (fade up, staggered), `fade`, `exit` (fade up and out),
`draw` (SVG line draw via dashoffset), `type` (typewriter text), `count` (number count-up).
Entrances `power3.out`; one `back.out` accent per scene; nothing sits dead still.

## Gotchas that cost real time
- Never put a GSAP transform on an element that also has a CSS `transform` (rotated stamps,
  centred pills). Wrap it: CSS rotates the wrapper, GSAP animates the child.
- Tween `x`/`y`/`scale`, never `left`/`top`/`width` (lint error `gsap_non_transform_motion`).
- A later tween on an element uses `to`, never a second `fromTo`: the second `fromTo` renders its
  start state immediately and clobbers the earlier one when the renderer seeks.
- `fromTo` renders immediately at build time. If an element must stay hidden until later, add
  `immediateRender:false` or start it at opacity 0 in CSS.
- SVG lines hidden by dashoffset still leak round caps as dots: no `stroke-linecap:round` on them,
  or keep them at opacity 0 until they draw.
- A flex column with a fixed height squeezes its children: add `flex-shrink:0`.
- An `!important` CSS rule blocks GSAP from changing that property.
- Deterministic only: no `Math.random()` at runtime (use `rng(seed)` at build time), no `Date.now()`,
  no fetches, no infinite repeats.
- `nested_structure_needs_subcomposition` and `timeline_track_too_dense` lint warnings are
  expected with this layout and harmless.
