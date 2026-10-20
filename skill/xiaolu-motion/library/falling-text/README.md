# falling-text · 落字 (falling-text)

The sampled glyph 凉 flies in and slams into center-screen with a gold/amber/persimmon gradient and expanding impact rings — the heaviest motion-blur moment in the film.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s910.js`, scene `S9`, t=40.0-44.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The winning character sampled in `dice-roll` is rendered as a single large glyph that accelerates in and impacts dead-center exactly at t=40.0s, triggering a warm gold/amber/persimmon gradient fill and concentric impact rings that expand outward from the point of contact.

## Notes
`s910.js` is shared with `live-montage` (the next scene in this library, S10 in the same source file). Unlike the other entries' previews, this one intentionally opens right at t=40.0s rather than after a settling buffer, because the impact at that exact instant is the entire point of the scene; the preview runs 40.0-43.0s. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
