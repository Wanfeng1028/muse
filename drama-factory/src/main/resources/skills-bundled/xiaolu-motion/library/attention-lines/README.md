# attention-lines · 注意力连线 (attention-lines)

Elliptical arcs connect every token to a single "NEXT" anchor point, with each arc's width and opacity mapped to that token's attention weight, visualizing self-attention at a glance.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s56.js`, scene `S5`, t=20.0-26.0s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
Every token remaining in the scene draws a curved arc toward a shared "NEXT" node. Arcs from more heavily-attended tokens render thicker and more opaque, so the overall arc fan gives an immediate visual readout of which earlier tokens matter most to producing the next one.

## Notes
`s56.js` is shared with `layered-compute` (the next scene in this library, S6 in the same source file). The tail of this scene's stated window (24.5-26.0s) is the hand-off into layered-compute's 3D "L01" tunnel, so the preview is trimmed to 21.0-24.0s to avoid both the opening and that hand-off. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
