# Design system for launch films

Every number here comes from a finished 75-second film, `examples/droid-launch`. Its binding direction is `examples/droid-launch/DIRECTION.md`. Treat the numbers as defaults. Change one only when you can say what it fixes in a rendered still.

The canvas is 1920x1080 at 30 fps, encoded as h264 at crf 16. Sizes are px on that canvas. Durations are frames at 30 fps.

The encoder sets several of the rules. After h264, text under 24px smears, 1px lines vanish, and grain turns into crawling noise and banding.

## Type is big, and nothing is under 24px

Use a geometric sans for statements and a matching mono for anything the product prints: terminal rows, labels, data, and sources. The example uses Geist, Geist Mono, and Instrument Serif italic.

| Token | px | Face and weight | Tracking | Use |
|---|---|---|---|---|
| `numeral` | 200 | sans 600, tabular | -0.05em | hero numbers |
| `display` | 168 | sans 600 | -0.045em, line-height 0.92 | one line per scene at most |
| `headline` | 120 | sans 600 | -0.04em, line-height 1.0 | scene headlines |
| `thesis` | 104 | sans 600 | -0.04em | a single-line thesis |
| `title` | 64 | sans 600 | -0.03em | card titles at hero size |
| `sub` | 44 | sans 500 | -0.02em | the supporting sentence |
| `body` | 36 | sans 500 | -0.01em | sans UI labels |
| `monoLg` | 40 | mono 400 | 0 | terminal prompt |
| `mono` | 30 | mono 400 or 500 | 0 | terminal rows, chart and meter labels |
| `meta` | 26 | mono 400 | 0 | captions, sources, header rows |
| `floor` | 24 | any | 0 | the absolute minimum. Avoid it. |

- Text under 32px reads as UI documentation, not a film. Keep 24 to 30px for meta labels and captions.
- A hero number is 112 to 200px. The draft of the example showed its key benchmark at 40px, and nobody could find it.
- One serif italic accent word per scene at most, at the size of its line. It takes the line's color. It takes the accent color only when that word is the product's point ("Work *didn't.*").
- Every changing number uses `font-variant-numeric: tabular-nums`.
- Sans and mono on the same row share a baseline.

## Grid uses 12 columns and centers on y 520

- 12 columns with a 120px margin, a 24px gutter, and 118px columns. Content lives in x 120 to 1800. The vertical safe area is y 96 to 984.
- Left-aligned headlines start at x 120 exactly. Centered layouts center on x 960.
- The optical center is y 520, not 540. Center a composition between y 500 and 540, never above 480.
- No empty band may be taller than 300px unless it is negative space framing a hero. The example's drafts left the bottom 40 to 50% empty. The fix was to stand objects on a line low in the frame (pricing cards on a bar at y 778).
- Fill a window before you hold it. A terminal that sits 80% empty for 5 seconds is dead air with a border.

## Color is two backgrounds and one accent

The palette has a fixed structure. Swap the hex values per brand, keep the roles, and recheck the contrast numbers.

| Role | Example hex | Rule |
|---|---|---|
| dark background | `#0E0E0C` | one of only two backgrounds |
| light background | `#F4F0E8` | the other background |
| surface on dark | `#1A1A17` | cards, terminals, chips on dark |
| line on dark | `#3A3934` | 2px rules and borders, recessive bar fills |
| secondary text on dark | `#A39E93` | 7.4:1. On light it only means disabled. |
| secondary text on light | `#6E6A62` | 4.9:1. Never on dark. |
| recessed fill on light | `#E6E0D3` | meter tracks. Never lines or text. |
| line on light | `#D6CEBE` | 2px rules and borders on light |
| paper | `#FBF9F4` | paper objects resting on the light background |
| accent | `#EE6018` | the product, and only the product |

- Primary text is the light background color on dark and the dark background color on light.
- Secondary text needs at least 4.5:1 against its background. Low contrast is not "subtle". It is unreadable after encode.
- There is no second accent. No green for success and no red for warnings.

## One accent idea per frame

At any frame, the accent marks one idea. That idea is a single object, plus its own label if it has one.

- The accent always means the product. Never use it for competitors, limits, warnings, generic UI, or decoration.
- Bad news stays neutral. In the example, the rate limits fill to 100% in cream on ink. Orange arrives in the next scene as the answer.
- When a scene has many product objects, pick the one that carries the beat. The example's terminal draft had an orange border, chevron, cursor, five underlines, and five checks at once. The fix turned the border to the line color and the progress fills to cream, so only the five completion checks and the prompt chevron stayed orange.
- Run the squint test on every hero still. Blur your eyes. You should see exactly one orange shape or cluster.

## Lines are 2px and depth is one shadow

- Every rule, border, and connector is 2px. 1px is banned.
- Draw borders on morphing rectangles as `box-shadow: inset 0 0 0 2px <color>`, so the border never changes the box size during a morph.
- Radii: chips 18, cards 20 to 24, windows 28, meters half their height, bars 12.
- Surfaces on dark get a surface fill and a 2px line-colored inset border. No shadows on dark.
- Paper objects on light get the paper fill, a 2px line border, and the film's one shadow, `0 1px 2px rgba(14,14,12,0.06), 0 18px 40px -18px rgba(14,14,12,0.28)`.
- Hero meters are 40px tall. Meters inside cards are 12px. Nothing is thinner than 12px. Dots and nodes are at least 12px. Status glyphs are mono 34.
- No gradients, vignettes, noise, grain, blur, or glow. The reference look is flat and exact.

## The camera is a push-in that is identity at both ends

Each scene wraps its content, not its background fill, in one camera layer. The camera scales up toward a hero point and comes back to exactly 1.0.

```tsx
const t = frame / (dur - 1);
const b = (1 - Math.cos(2 * Math.PI * t)) / 2;
const transform = `scale(${1 + amount * b})`;
```

`b` and its slope are both 0 on frame 0 and on frame `dur - 1`. The boundary frames are pixel-exact, and the cut carries no zoom hitch because the velocity is zero on both sides.

- `amount` is 0.012 to 0.016. Use 0 when the scene already zooms on its own, as the example's logo spin does.
- `transform-origin` is the scene's hero point.
- For parallax, put captions and meta in a sibling camera at `amount` 0.008. Never nest cameras.
- No pans, tilts, 3D swoops, or rack-focus blur.

## Motion timing

One easing family covers the whole film.

| Move | Frames | Easing | Rule |
|---|---|---|---|
| enter | 21 (18 to 27) | expo-out, `cubic-bezier(0.16, 1, 0.3, 1)` | always a masked move |
| exit | 14 | ease-in, `cubic-bezier(0.7, 0, 0.84, 0)` | through a mask or off a frame edge |
| morph | 30 to 36 | ease-in-out, `cubic-bezier(0.65, 0, 0.35, 1)` | animate left, top, width, height, radius |
| stagger | 3 to 4 between items | same as the move | at most 5 items per chain |
| hero hold | 24 or more | none | only the camera moves |
| text hold | words x 5 + 12 or more | none | a 4-word headline holds 32 frames |
| state change | 8 to 14 | ease-in-out | grey-out, color swap |
| spring | as needed | damping 200, stiffness 120 to 300 | critically damped, no overshoot |

- An entrance is a move through a mask, out of an on-screen object, or in from a frame edge. Opacity-only entrances are banned.
- Exits are faster than entrances.
- Never `scale()` a DOM rectangle beyond 1.5x. It blurs and distorts radii and borders. Animate its geometry instead. `scale()` is fine on SVG and on text.
- Stagger larger sets by row or by column, not item by item.
- A counter runs on the same curve as the bar or meter it describes and locks on the same frame.
- Constant rotation is allowed only for spinners and a logo mark. Nothing else moves linearly.
- A color or state change takes 8 to 14 frames and never replaces motion.
- No more than 12 consecutive frames may pass with only the camera moving. The exception is one designated freeze per film. Pass it to `motion_scan.py --allow`.
- Picture events land on audio cue frames exactly. Keep cues in one timeline file that both the video and the audio build read (`examples/droid-launch/src/timeline.ts`). Check each cue by rendering frame `cue - 1` and frame `cue`.

## Hand off each cut with a shared component at default props

The last frame of scene N equals frame 0 of scene N+1 by construction, not by eye. Scenes never crossfade.

1. For each cut, name the one object both scenes show. If there is none, the boundary is a solid background.
2. Put that object in the shared components file. Its geometry constants and default props equal the handoff state.
3. Scene N morphs into the component and renders it with default props on its last frame, after a hold of 12 frames or fewer.
4. Scene N+1 renders the same component with default props on frame 0, then moves.
5. Both scenes render it inside their camera, which is identity on those frames.
6. Record every boundary in a handoff table with exact geometry and colors (`examples/droid-launch/HANDOFF.md`).
7. Render the last frame of N and frame 0 of N+1, and compare them pixel for pixel.

A shared container keeps its children registered to their original coordinates while its outer rectangle morphs. A collapse then clips the content like a closing shutter instead of squashing it. The example's `TerminalFrame` does this.

Example boundaries from the film:

| Cut | Shared state |
|---|---|
| S2 to S3 | five model chips, 300x84, at y 200, on dark |
| S3 to S4 | terminal window 1440x840 at (240,120), radius 28, 2px accent border, header row drawn |
| S4 to S5 | a 1440x4 accent line at (240,778) |
| S5 to S6 | the usage meter, 1200x40 at (360,412), full, on light |
| S6 to S7 | a 200px accent ⊕ at (960,540) |
| S1 to S2, S7 to S8 | solid dark background |

A solid-background boundary is dead air. Keep it to 8 frames or fewer, and start the next scene's first reveal on frame 0.

## What reads as premium

- Scale. Headlines are 120px or more, hero numbers 112 to 200px, and terminal text 30 to 40px.
- Few things at once. One hero per scene and at most 5 items per stagger chain.
- Exactness. Events land on the cue frame. Edges sit on x 120 or on a shared axis. Mixed type shares a baseline.
- Continuity. Every element answers "where did it come from, and where does it go". It enters from something on screen or a masked edge, and it leaves the same way.
- Stillness. Heroes hold for at least 24 frames with only the camera moving. One full freeze with silence lands harder than any effect.
- Real UI. Recreations use real product strings, paths, and commands at mono 30 to 40. They have no window traffic lights and no fake chrome.
- Real data. Every number comes from a source or from the pipeline that made the film. A preview shows a placeholder dash for a missing value, never a fake zero.

## Slop blacklist

Any one of these fails review.

1. Glow, bloom, gradient, vignette, grain, noise, blur, light leak, lens flare, particles, or confetti.
2. Bounce, overshoot, elastic, wobble, or "pop" scale-ups above 1.0.
3. Opacity-only entrances, crossfades, or per-word fades. Typewriter text anywhere except a recreated prompt.
4. Text under 24px, 1px lines, the light-background secondary color used on dark, or low contrast used to look subtle.
5. The accent on anything that is not the product, or two accent ideas in one frame.
6. Emoji, stock icons, window traffic-light dots, fake competitor logos, sparkles, or "AI" glyphs.
7. `scale()` on a DOM rectangle above 1.5x, 3D perspective swoops, or random tilts.
8. Everything moving at once, staggers of more than 5 identical items, or elements that appear from nowhere.
9. Invented facts: dates, benchmarks, prices, or features not in the facts sheet. Placeholder data shown as real.
10. More than 12 frames of dead air outside the designated holds, or a composition that leaves a 40% empty band.

## Taste checklist

Each scene designer verifies every item with rendered stills before handing off.

- [ ] I rendered at least 12 stills per scene: frame 0, the last frame, every cue frame, and the hero frame.
- [ ] At 25% size (480px wide), every word is legible and the hero reads in 1 second.
- [ ] The squint test shows exactly one accent idea per frame.
- [ ] Every element has an answer to "where did it come from, and where does it go".
- [ ] The composition centers between y 500 and 540. No empty band exceeds 300px unless it frames a hero.
- [ ] Left edges sit on x 120 or on a shared axis. Sans and mono on one row share a baseline.
- [ ] Every text hold is at least words x 5 + 12 frames. Every hero holds at least 24 frames.
- [ ] Frame 0 and the last frame match the handoff table exactly, rendered from the shared component with default props inside the camera.
- [ ] Exits are faster than entrances. Morphs use ease-in-out. Nothing moves linearly except spinners and the logo.
- [ ] Every visual cue lands on its frame. Frame `cue - 1` and frame `cue` differ as intended.
- [ ] Every number on screen traces to the facts sheet or to the pipeline's data file.
- [ ] The type check passes (`npx tsc -p .` in the example).
