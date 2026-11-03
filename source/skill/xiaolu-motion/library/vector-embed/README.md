# vector-embed · 向量 (vector-embed)

Each numbered token unrolls into a strip of 42 colored values, visualizing a token ID being embedded into a high-dimensional vector.

## Source
Ported from 《在我开口之前》(Claude's autonomous short film), `源码/画面/src/s23.js`, scene `S3`, t=12.0-15.5s of the original 60s film. Depends on the shared rendering harness in `../_shared/creative-film-runtime/` (see its README for how scenes are actually rendered — headless Chrome + WebGL2, not this repo's newer `engine/`).

## How it works
The token IDs produced by the numbering phase morph into horizontal heat-strips: each strip has 42 cells, colored by value, functioning as a small heatmap rendering of that token's embedding vector. Every token on screen gets its own strip, unrolling left to right.

## Notes
`s23.js` is shared by three sibling scenes in this library — `word-cut`, `numbering`, and this one — so the full file is duplicated in all three `src/` folders rather than split up. The scene's stated window runs to 15.5s, but the last half-second (15.5-16.0s) is technically the 2D-to-3D hand-off into the next scene (`semantic-starfield`), so the preview is trimmed to 12.3-15.3s to stay clear of both the opening cut and that tail. Motion blur/glow/grain for this scene come from the shared runtime's `post.js`, and have since been generalized into `engine/post.js`.
