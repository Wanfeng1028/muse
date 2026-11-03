# Craft: engine, motion rules, gotchas

[templates/scene.html](../templates/scene.html) is the engine plus a small example scene. The patterns below come from a full production (a pinned chat prompt, footage, a transcript trim, a 3D wheel of reels) and are described precisely enough to rebuild.

## The engine

- **`seek(t)` is the only entry point.** It sets every style from `t`. No CSS transitions or animations, no timers, no state carried between frames: any frame renders identically in any order, which is what makes subframe blur, previews and re-renders possible.
- **Springs are closed-form step responses.** A value that changes target many times is a `Track`: one spring per `.to(t, value, ω, ζ)`, summed. ζ 0.82 to 0.9 for UI, 0.95 to 0.98 for the camera, 0.7 only for a deliberate settle (about 4% overshoot). Below 0.7 a spring bounces.
- **World units, no CSS scaling.** A 1000-unit square maps to the frame's short side; `U` is pixels per unit at the current zoom. Every size, radius and font size is recomputed in pixels each frame. A CSS `transform: scale` on anything with text rasterises it blurry; `will-change` makes it worse.
- **Loop or one-shot** (`CONFIG.loop`). A loop sums the current pass and two previous ones so the last frame equals the first, velocity included, and needs every track to return to its start (`close()`); `preview.mjs` checks the seam. A one-shot ends on the end card, with no `close()` at the end and `META.endT` set to when the card lands.
- **The contract** the scripts rely on: `window.seek`, `DUR`, `T`, `META`, `CONFIG`, `CHECKS`, `CUES` and `hitTest`, an element with id `cursor`, and `seek` setting `window._tip` to the pointer tip. Keep them current when the scene changes.

## The grid

- 120 BPM by default, so a beat is 0.5 s. Something happens on every beat; a hold is still "something" if the camera drifts or a playhead runs.
- **Morphs fire on the beat; the pointer arrives before it** (`lead(t)`, about 0.34 s), so the press and the morph land together.
- **Reading holds.** Text that carries the argument stays fully settled for at least 1.5 s, plus about 0.3 s per extra line. A typed prompt holds 1.5 s after the last key. A click stays visibly pressed 0.3 to 0.5 s before what it triggers.
- One gesture per beat. A state that needs two gestures needs two beats.
- Lengthening a moment by whole beats keeps every later hit on the grid. A fraction of a beat goes into the moment itself (start a press earlier), not into shifting everything after it.

## Motion rules

- **One shape, never cut.** Each state is the same element morphing size, radius and color; its content swaps with a short blur. Content that leaves finishes before the next content enters, each with its own window, or the two overlap.
- **Panels open downward from a pinned top edge:** give the panel's height and its centre the same spring at every event, and the top stays still while it grows.
- **The camera frames each state** at 65 to 85% of the frame's width, follows the panel's centre, and pushes in slightly on the beat that carries the argument.
- **The pointer is a real hand.** It travels on springs, dips about 15% on a click, gets out of the way of anything being read, and fades once its job is done. It keeps a constant on-screen size, 64 px in every format, while the world zooms.
- **Direct manipulation.** While a handle is held, its value is read from the pointer; on release it springs from wherever it was. If a drag would go past a limit, resist (`over / (1 + k·over)`) and spring back to the last valid value. Never leave a control at a degenerate value (a trim at 0 s).
- **Two edges, two springs.** An indicator or knob that moves gets a faster spring on its leading edge, so it stretches ahead and re-gathers.
- **Type at phone size.** Body text at least 30 px in a 1440 frame (about 20 px at 1080 wide). A 50-character sentence on one line is near the limit; wrap it or widen the box rather than shrink it.
- **9:16 safe zones.** Social apps cover roughly the top 12% and bottom 20% of a vertical frame with their own UI: keep text and clicks out of those bands.

## Patterns from past productions

- **A box pinned at the top** (a chat prompt that stays while the conversation plays below): draw it in its own space by swapping `U`, `camX`, `camY` and `OFF` while painting it, and set `OFF` so the world centres in the space under it. Give it an exit track if it must leave before the end.
- **Footage** (`frames.py`): `seek(t)` sets `img.src` from `t`; the renderer waits for every image to decode before each capture, or frames come out blank. Crop to the on-screen aspect around the face, and check the whole window for a hand over the face, a look away or a cut.
- **A 3D wheel of cards**: per card `perspective(P) translateZ(-R) rotateY(θ) translateZ(R)`, `z-index` from `cos θ`, backface hidden, side cards dimmed with a flat overlay. The front card's transform is then the identity, so its text stays crisp. Advance one card per beat; land the hero card in front just before the end card.
- **A transcript that a trim edits**: words spread over the clip by character count, so the handle and the highlight agree; each word's highlight follows how much of it the selection keeps; the release snaps the handle to a word boundary. The same text is on screen from the moment the player opens; never swap a subtitle line for it mid-shot.

## Gotchas

- A node hidden on the previous frame measures zero-wide: `txt()` forces `display:block` before measuring. Every element drawn in a frame must also get `show()` in that frame, or it lingers on screen for the whole video.
- A button can be hidden on the exact frame it is clicked (its window ends a frame early): `checks.mjs` catches it as a miss; extend the window past the click.
- `win()` wraps an end time past `DUR` only in a loop. For an element that must stay to the last frame of a one-shot, `enter()` is the simpler call.
- Four subframes comb a fast pointer into separate ghosts; six blur it. `tmix` needs exactly as many weights as subframes.
- Heavy 3D compositing can stall one screenshot past the default 30 s timeout; `render.mjs` waits 120 s and retries.
- Measure a tempo on the music alone, never on a mix with UI sounds: the clicks pull the detected grid.
- Place each UI sound by its measured peak, not its first sample, or a whoosh with a slow attack lands late.
- A loop's soundtrack wraps every tail into bar 1; a one-shot must not, or the end card's chord bleeds into the opening.
- The same person's face never sits under two different identities (two participant IDs, two names). With fewer people than cards, place one person's cards on opposite sides of a wheel so they are never on screen together, and say so.
- A real logo is pasted as its SVG. A wordmark retyped in a font is never exactly the brand.

## Iterating

- Change only what was named. Before touching code, look at the frames at the times the person mentions: "the shot at 10 s" is whatever is on screen at 10 s, not the event scheduled at 10 s.
- "Slower" means longer holds, not slower springs: shift every later event by whole beats and keep the spring constants, which is what keeps the motion fluid.
- The snapshot in `versions/v<N>/`, taken at each delivery, is the way back. Overwriting the only copy of a version that worked makes going back to it a reconstruction.
- Rerun `preview.mjs` and `checks.mjs` after every change, in every format, before rendering. Look at the sheet: the checks prove clicks and overlap, not taste.
- Deliver under new names when the person asks for a new version, and keep the old ones until they say otherwise.
